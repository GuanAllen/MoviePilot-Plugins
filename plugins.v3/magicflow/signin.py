"""魔流 · 站点签到 / 模拟登录（3.6.0）。

借鉴 MoviePilot「站点自动签到」插件（thsrite / autosignin）的做法：
  · 通用签到 = 带站点 Cookie GET `attendance.php`（NexusPHP 访问即签到）；
  · 结果识别 = 未登录（密码框 / login.php）→ Cookie 失效；
              命中 `已签|签到已得|签到成功|每日签到` → 成功（或今日已签）；
  · 通用登录 = 带 Cookie GET 站点首页做「模拟登录」保活，并按结果刷新 MoviePilot 站点数据；
  · 失败文案命中「重试关键词」（默认 `错误|失败`）→ **当天延后重试**（默认只补 1 次，间隔 ~20~30 分钟），
    且重试同样吃 PV 闸门（预算/熔断/当日上限）——不搞隔壁那种「失败立刻再打一次」；
  · Cookie 失效 → 发 `PluginAction site_refresh`，让站点自动登录去刷 Cookie（同隔壁）；
  · 专用处理器（21 个站）的请求也要过采集模块的配额闸门（`collect.budget`）；
  · 站点多选：想签几个签几个（`signin_sites` / `signin_login_sites`）；
  · 结果按「日期 × 站点」落库（保留 7 天），前端出状态表。

比它更省的地方：
  · 命中站点「每日访问上限（PV）」→ 该站当日不再尝试（免得越试越锁）；
  · 同一站当天已成功签到 → 不再重复请求（一天最多 1 次请求/站）；
  · API 类站点（如馒头）没有 attendance 页 → 直接标记「不支持」，不浪费请求。
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .collect import parse_signin
from .persistence import OperationItem

SIGNIN_PAGE = "attendance.php"
HOME_PAGE = "index.php"
KEEP_DAYS = 7
DEFAULT_RETRY_KEYWORD = "错误|失败"
DEFAULT_QUEUE = 5
# ★ 失败重试（按我们的 PV 节奏，不是隔壁的「失败立刻再打」）：
#   - 每天每站最多 2 次尝试（首次 + 1 次重试）→ 与 collect.KIND_DAY_CAP["signin"] 对齐；
#   - 两次之间至少隔 RETRY_GAP 分钟（再叠 0~RETRY_JITTER 分钟抖动），错峰不扎堆。
RETRY_KEY = "signin_retry"
RETRY_MAX_ATTEMPTS = 2
RETRY_GAP_MINUTES = 20.0
RETRY_JITTER_MINUTES = 10.0

LOGIN_HINT_RE = re.compile(
    r"login\.php|takelogin\.php|type=[\"']password[\"']|name=[\"']password[\"']",
    re.I,
)
SIGNED_RE = re.compile(r"签到已得\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
SIGNED_TEXTS = ("已签到", "签到已得", "每日签到", "签到成功", "簽到成功", "已经签到", "已签")
LOGGED_IN_RE = re.compile(r"logout|mybonus|usercp|userdetails", re.I)
PV_LIMIT_RE = re.compile(r"访问次数已达上限|已达今日上限|每日访问次数|今日访问")
API_SITE_DOMAINS = ("m-team", "mteam", "api.")


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _site_name(site: Any, site_id: Any) -> str:
    return str(getattr(site, "name", "") or getattr(site, "domain", "") or site_id)


class SigninEngine:
    """站点签到 / 模拟登录引擎（无状态；结果落插件数据）。"""

    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    # ---------------------------------------------------------------- 基础
    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self._plugin._log(f"[签到] {msg}", level)
        except Exception:  # noqa: BLE001
            pass

    def _site(self, site_id: Any) -> Any:
        try:
            return self._plugin._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            return None

    # ---------------------------------------------------- 专用处理器（5.1.0）
    def _handler(self, site: Any) -> Any:
        """按域名匹配站点专用处理器（命中返回类，否则 None）。"""
        if not site:
            return None
        try:
            from . import signin_sites  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            self._log(f"签到处理器包不可用：{err}", "warning")
            return None
        url = str(getattr(site, "url", "") or getattr(site, "domain", "") or "")
        try:
            return signin_sites.find(url)
        except Exception as err:  # noqa: BLE001
            self._log(f"匹配签到处理器失败（{url}）：{err}", "debug")
            return None

    def _site_ctx(self, site: Any) -> Dict[str, Any]:
        """构造处理器要的站点信息字典（与 autosignin 的 site_info 同键）。"""
        def _s(key: str) -> str:
            return str(getattr(site, key, "") or "").strip()

        timeout = int(getattr(site, "timeout", 0) or 0)
        ctx = {
            "id": getattr(site, "id", None),
            "name": _s("name"),
            "url": _s("url"),
            "domain": _s("domain"),
            "cookie": _s("cookie"),
            "ua": _s("ua"),
            "token": _s("token"),
            "apikey": _s("apikey"),
            "proxy": bool(getattr(site, "proxy", 0)),
            "render": bool(getattr(site, "render", 0)),
            "timeout": timeout or None,
        }
        # ★ API 通道信息（馒头 x-api-key / 叶PT Authorization）：处理器可直接用
        try:
            from .collect import api_base, api_channel, is_api_site  # noqa: WPS433

            ctx["api_base"] = api_base(site)
            tname, cfg = api_channel(site)
            ctx["api_channel"] = tname
            ctx["api_auth"] = dict((cfg or {}).get("auth") or {})
            ctx["is_api_site"] = is_api_site(site)
        except Exception as err:  # noqa: BLE001
            self._log(f"构造 API 通道信息失败：{err}", "debug")
        return ctx

    def _run_handler(self, kind: str, site: Any, handler: Any, site_id: Any, name: str) -> Dict[str, Any]:
        """调用专用处理器并落库。★ 请求同样过配额闸门（闸门拒了就不发）。"""
        ctx = self._site_ctx(site)
        hname = getattr(handler, "__name__", "handler")
        allow, why = self._budget_allow(site_id)
        if not allow:
            return self._store_result(kind, site_id, name, False, f"[专用] 未执行：{why}", skipped=True, handler=hname)
        try:
            fn = handler().signin if kind == "sign" else handler().login
            ok, msg = fn(ctx)
        except Exception as err:  # noqa: BLE001
            ok, msg = False, f"{'签到' if kind == 'sign' else '模拟登录'}失败：{err}"
        self._budget_spend(site_id)
        msg = str(msg or ("成功" if ok else "失败"))
        return self._store_result(kind, site_id, name, bool(ok), f"[专用] {msg}", handler=hname)

    def _get_text(self, site_id: Any, page: str, kind: str = "signin") -> Tuple[str, Optional[str], int]:
        """抓站点页（★ 3.38.0：站点请求只出自采集模块 collect，配额/熔断都在那边）。"""
        c = getattr(self._plugin, "collect", None)
        if c is not None:
            try:
                res = c.site(int(site_id)).page(page, kind=str(kind or "signin"), ttl=0.0)
                if res.ok:
                    return res.text, None, int(res.status or 200)
                return "", res.error or "抓取失败", int(res.status or 0)
            except Exception as err:  # noqa: BLE001
                return "", f"采集模块异常: {err}", 0
        live = getattr(self._plugin, "_live", None)
        if live is not None:
            try:
                return live._get_text(int(site_id), page)
            except Exception as err:  # noqa: BLE001
                return "", f"请求失败: {err}", 0
        return "", "站点抓取组件不可用", 0

    @staticmethod
    def _is_api_site(site: Any) -> bool:
        host = f"{getattr(site, 'domain', '') or ''} {getattr(site, 'url', '') or ''}".lower()
        return any(k in host for k in API_SITE_DOMAINS)

    @staticmethod
    def _collect_is_api(site: Any) -> bool:
        """采集模块口径的「API 鉴权站」（看站点配置里鉴权字段是否真有值）。"""
        try:
            from .collect import is_api_site  # noqa: WPS433

            return bool(is_api_site(site))
        except Exception:  # noqa: BLE001
            return False

    def _api_ping(self, site_id: Any) -> Tuple[bool, str]:
        """API 鉴权站的「保活」（等效签到）：走采集模块的后台 API 档案。"""
        c = getattr(self._plugin, "collect", None)
        if c is None:
            return False, "采集模块不可用"
        try:
            got = c.site(int(site_id)).user_bar() or {}
        except Exception as err:  # noqa: BLE001
            return False, f"采集模块异常: {err}"
        if not got.get("ok"):
            return False, str(got.get("error") or "抓取失败")
        if not got.get("logged_in") and not (got.get("ratio") or got.get("bonus")):
            return False, "密钥/Cookie 已失效"
        return True, "后台 API 保活成功（站点数据已刷新）"


    def _refresh_site(self, site: Any, seconds: int = 0) -> None:
        """告诉 MoviePilot「这个站刚访问成功」→ 顺带刷新站点数据/在线状态。"""
        domain = str(getattr(site, "domain", "") or "")
        if not domain:
            return
        try:
            from app.db.site_oper import SiteOper  # noqa: WPS433

            SiteOper().success(domain=domain, seconds=int(seconds or 0))
        except Exception as err:  # noqa: BLE001
            self._log(f"刷新站点状态失败（{domain}）：{err}", "debug")

    # ---------------------------------------------------------------- 记录
    def records(self) -> Dict[str, Any]:
        try:
            data = self._plugin.get_data("signin_records") or {}
        except Exception:  # noqa: BLE001
            data = {}
        return data if isinstance(data, dict) else {}

    def _save_records(self, data: Dict[str, Any]) -> None:
        # 只留最近 KEEP_DAYS 天
        try:
            keep = sorted([str(k) for k in data.keys()])[-KEEP_DAYS:]
            data = {k: data[k] for k in keep}
        except Exception:  # noqa: BLE001
            pass
        try:
            self._plugin.save_data("signin_records", data)
        except Exception as err:  # noqa: BLE001
            self._log(f"签到结果落库失败：{err}", "warning")

    def _store_result(
        self,
        kind: str,
        site_id: Any,
        site_name: str,
        ok: bool,
        message: str,
        bonus: Optional[float] = None,
        skipped: bool = False,
        handler: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = {
            "ok": bool(ok),
            "message": str(message or ""),
            "ts": time.time(),
            "time": datetime.now().strftime("%H:%M:%S"),
            "skipped": bool(skipped),
        }
        if handler:
            row["handler"] = str(handler)
        row["site_id"] = site_id
        row["site_name"] = site_name
        if bonus:
            row["bonus"] = float(bonus)
        # ★ 先把「今天已成功过」的历史读出来：**成功记录不被后来的失败/上限盖掉**
        try:
            _prev = ((self.records().get(_now_date(), {}) or {}).get(str(site_id), {}) or {}).get(kind) or {}
        except Exception:  # noqa: BLE001
            _prev = {}
        if _prev.get("ok") and not ok:
            # 今日该动作已经成功过：本次结果（常见：配额/次数上限、又试了一次）不当失败，保留成功
            self._log(f"{site_name} 今日已成功，忽略本次结果：{message}", "debug")
            if "Cookie" in str(message):
                try:
                    self._trigger_site_refresh(site_id)
                except Exception:  # noqa: BLE001
                    pass
            keep = dict(_prev)
            keep["attempt"] = str(message or "")[:160]
            keep["attempt_time"] = datetime.now().strftime("%H:%M:%S")
            return keep
        # ★ Cookie/密钥失效 → 发 site_refresh（同隔壁），让站点自动登录去刷 Cookie
        if not ok and ("Cookie 已失效" in str(message) or "密钥/Cookie 已失效" in str(message)):
            try:
                self._trigger_site_refresh(site_id)
            except Exception:  # noqa: BLE001
                pass
        try:
            data = self.records()
            day = data.setdefault(_now_date(), {})
            site_row = day.setdefault(str(site_id), {})
            site_row[kind] = row
            site_row["site_name"] = site_name
            self._save_records(data)
        except Exception as err:  # noqa: BLE001
            self._log(f"签到记录写入失败：{err}", "debug")
        return row

    def already_done(self, kind: str, site_id: Any) -> Optional[Dict[str, Any]]:
        """今天这个站这个动作是否已成功过（成功才跳过；失败允许重试）。"""
        try:
            row = (self.records().get(_now_date(), {}).get(str(site_id), {}) or {}).get(kind) or {}
        except Exception:  # noqa: BLE001
            return None
        return row if row.get("ok") else None

    # ---------------------------------------------------------------- 签到
    def checkin(self, site_id: Any) -> Dict[str, Any]:
        site = self._site(site_id)
        name = _site_name(site, site_id)
        if not site:
            return {"site_id": site_id, "site_name": name, "ok": False, "message": "站点不存在"}
        # ① API 鉴权站（馒头 / 叶PT）：没有 attendance 页 → 用后台 API 保活（等效「签到」）
        if self._collect_is_api(site) or self._is_api_site(site):
            ok, msg = self._api_ping(site_id)
            return self._store_result("sign", site_id, name, ok, f"API 站（无签到页）:{msg}")
        # ② 站点专用处理器（HDSky OCR / U2 随机 / CHD·HDChina 表单 …）
        h = self._handler(site)
        if h is not None:
            return self._run_handler("sign", site, h, site_id, name)
        text, err, status = self._get_text(site_id, SIGNIN_PAGE)
        if not text:
            err_s = str(err or ("HTTP %s" % status))
            # ★ 配额类（次数上限/预算不足）是「今天不再试」，不是签到失败 → 标 skipped（不刷红）
            if any(k in err_s for k in ("已达上限", "预算不足", "每日访问次数", "今日访问")):
                return self._store_result("sign", site_id, name, False, f"未执行：{err_s}", skipped=True)
            return self._store_result("sign", site_id, name, False, f"签到失败：{err_s}")
        # ★ 3.38.0：页面 → 事实的解析归采集模块（这里只做"该不该记/怎么记"的判断）
        got = parse_signin(text)
        if got.get("pv_limited"):
            return self._store_result("sign", site_id, name, False, "站点每日访问次数已达上限（今日不再尝试）")
        if got.get("cookie_dead"):
            return self._store_result("sign", site_id, name, False, "Cookie 已失效或未登录")
        if got.get("signed"):
            bonus = got.get("bonus")
            already = bool(got.get("already"))
            msg = "今日已签到（+%s 魔力）" % int(bonus) if (already and bonus) else (
                "今日已签到" if already else "签到成功"
            )
            return self._store_result("sign", site_id, name, True, msg, bonus=bonus)
        return self._store_result("sign", site_id, name, True, "已执行（未识别到结果文案，可去站点确认）")

    # ---------------------------------------------------------------- 登录
    def login(self, site_id: Any) -> Dict[str, Any]:
        site = self._site(site_id)
        name = _site_name(site, site_id)
        if not site:
            return {"site_id": site_id, "site_name": name, "ok": False, "message": "站点不存在"}
        # 站点专用处理器：API 站（馒头等）先交给采集通道（走后台 API），
        # 采集拿不到时再用专用处理器兜底。
        h = self._handler(site)
        started = time.time()
        # ★ 3.38.0「顺便」：用户栏页（index.php）本来每轮就被站点实时抓（kind=live），
        #   这里直接读同一份事实 → 保活零额外 PV；TTL 内没有才真抓一次（同一 URL，仍只 1 次）。
        c = getattr(self._plugin, "collect", None)
        got: Dict[str, Any] = {}
        if c is not None:
            try:
                got = c.site(int(site_id)).user_bar() or {}
            except Exception as err:  # noqa: BLE001
                got = {"ok": False, "error": f"采集模块异常: {err}"}
        if not got.get("ok"):
            # 采集通道拿不到 → 有专用处理器就用它兜底
            if h is not None:
                return self._run_handler("login", site, h, site_id, name)
            msg = f"模拟登录失败：{got.get('error') or '抓取失败'}"
            return self._store_result("login", site_id, name, False, msg)
        if not got.get("logged_in") and not (got.get("ratio") or got.get("bonus")):
            return self._store_result("login", site_id, name, False, "Cookie 已失效或未登录")
        self._refresh_site(site, seconds=int(time.time() - started))
        return self._store_result("login", site_id, name, True, "模拟登录成功（站点数据已刷新）")

    # ---------------------------------------------------------------- 跑批
    def _do(self, kind: str, site_id: Any, retry_keyword: str = "") -> Dict[str, Any]:
        """跑一个站点的一次动作（★ 不再「失败立刻重试」——重试由 _plan_retries 延后排期）。"""
        fn = self.checkin if kind == "sign" else self.login
        return fn(site_id)

    # ---------------------------------------------------------------- 配额闸门
    def _budget(self) -> Any:
        return getattr(getattr(self._plugin, "collect", None), "budget", None)

    def _budget_allow(self, site_id: Any, kind: str = "signin") -> Tuple[bool, str]:
        """专用处理器的请求也要过配额闸门（预算 / 熔断 / 当日上限）。"""
        b = self._budget()
        if b is None:
            return True, ""
        try:
            allow, why = b.allow(site_id, kind, 1)
            try:
                used = b.day_used(site_id, kind)
            except Exception:  # noqa: BLE001
                used = -1
            self._log(f"配额闸门 site={site_id} kind={kind} used={used} allow={allow} {why}", "debug")
            return allow, why
        except Exception as err:  # noqa: BLE001
            self._log(f"配额闸门异常（site={site_id}）：{err}", "warning")
            return True, ""

    def _budget_spend(self, site_id: Any, kind: str = "signin") -> None:
        b = self._budget()
        if b is None:
            return
        try:
            b.spend(site_id, kind, 1)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 重试计划
    def _retry_state(self) -> Dict[str, Any]:
        try:
            data = self._plugin.get_data(RETRY_KEY) or {}
        except Exception:  # noqa: BLE001
            data = {}
        return data if isinstance(data, dict) else {}

    def _save_retry_state(self, bucket: Dict[str, Any]) -> None:
        """只留今天——重试计划天然是「当日」的。"""
        try:
            self._plugin.save_data(RETRY_KEY, {_now_date(): dict(bucket or {})})
        except Exception as err:  # noqa: BLE001
            self._log(f"重试计划落库失败：{err}", "debug")

    def _plan_retries(self, kind: str, results: List[Dict[str, Any]], retry_keyword: str) -> None:
        """跑完一轮后重排失败重试计划：成功清掉；命中关键词的延后一次（间隔+抖动，最多 2 次/天）。"""
        if kind != "sign":
            return
        day = _now_date()
        bucket = dict(self._retry_state().get(day) or {})
        kw = str(retry_keyword or "").strip()
        now = time.time()
        for r in results or []:
            sid = str(r.get("site_id") or "")
            if not sid:
                continue
            if r.get("ok"):
                bucket.pop(sid, None)
                continue
            if r.get("skipped"):
                continue
            msg = str(r.get("message") or "")
            try:
                hit = bool(re.search(kw, msg)) if kw else True
            except Exception:  # noqa: BLE001
                hit = True
            # ★ 配额类失败重试没意义（次数上限/预算不足/未执行/熔断）→ 直接放弃，不排重试
            if any(k in msg for k in ("已达上限", "预算不足", "未执行", "熔断", "每日访问次数")):
                bucket.pop(sid, None)
                continue
            prev = int((bucket.get(sid) or {}).get("tries") or 0)
            tries = prev + 1
            if hit and tries < RETRY_MAX_ATTEMPTS:
                import random as _r  # noqa: WPS433

                delay = (RETRY_GAP_MINUTES + _r.uniform(0.0, RETRY_JITTER_MINUTES)) * 60.0
                bucket[sid] = {
                    "tries": tries,
                    "next": round(now + delay, 1),
                    "next_at": time.strftime("%H:%M", time.localtime(now + delay)),
                    "last": msg[:120],
                }
                self._log(f"失败待重试：站点 {sid}（第 {tries} 次，{bucket[sid]['next_at']} 再试）— {msg[:60]}", "debug")
            else:
                bucket.pop(sid, None)
        self._save_retry_state(bucket)

    def retry_due(self) -> List[str]:
        """到点该补一次的签到站点（登录不排重试——登录本身是保活，失败下一轮再说）。"""
        day = _now_date()
        bucket = self._retry_state().get(day) or {}
        now = time.time()
        out: List[str] = []
        for sid, info in (bucket or {}).items():
            try:
                if int((info or {}).get("tries") or 0) >= RETRY_MAX_ATTEMPTS:
                    continue
                if float((info or {}).get("next") or 0) <= now:
                    out.append(str(sid))
            except Exception:  # noqa: BLE001
                continue
        return out

    def retry_plan_view(self) -> Dict[str, Any]:
        """给状态接口看的重试计划（省得前端看不见「在等重试」）。"""
        day = _now_date()
        return dict(self._retry_state().get(day) or {})

    # ---------------------------------------------------------------- 事件
    def _trigger_site_refresh(self, site_id: Any) -> None:
        """Cookie 失效 → 发 `PluginAction site_refresh`（同隔壁），让站点自动登录去刷 Cookie。"""
        try:
            from .common import _MF_EVENTS_READY, _MFEventType, _mf_eventmanager  # noqa: WPS433
        except Exception:  # noqa: BLE001
            return
        if not _MF_EVENTS_READY or _mf_eventmanager is None or _MFEventType is None:
            return
        try:
            _mf_eventmanager.send_event(_MFEventType.PluginAction, {"site_id": int(site_id), "action": "site_refresh"})
            self._log(f"站点 {site_id} Cookie 失效 → 已触发 site_refresh", "info")
        except Exception as err:  # noqa: BLE001
            self._log(f"触发 site_refresh 失败（站点 {site_id}）：{err}", "debug")

    def run(
        self,
        kind: str = "sign",
        site_ids: Optional[List[Any]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        cfg = getattr(self._plugin, "_signin_cfg", {}) or {}
        kind = "login" if str(kind) == "login" else "sign"
        label = "签到" if kind == "sign" else "登录"
        if not cfg.get("enabled") and not force:
            return {"ok": False, "message": "签到功能未启用", "results": []}
        ids: List[Any] = list(site_ids or (cfg.get("sites") if kind == "sign" else cfg.get("login_sites")) or [])
        ids = [i for i in ids if str(i).strip()]
        if not ids:
            return {"ok": False, "message": f"未选择{label}站点", "results": []}
        results: List[Dict[str, Any]] = []
        for sid in ids:
            if not force and self.already_done(kind, sid):
                site = self._site(sid)
                results.append({
                    "site_id": sid,
                    "site_name": _site_name(site, sid),
                    "ok": True,
                    "skipped": True,
                    "message": f"今日已{label}（跳过）",
                })
                continue
            results.append({"_id": sid})
        todo = [r["_id"] for r in results if "_id" in r]
        results = [r for r in results if "_id" not in r]
        if todo:
            queue = max(1, int(cfg.get("queue") or DEFAULT_QUEUE))
            kw = str(cfg.get("retry_keyword") or "")
            # ★ 站间随机间隔：**错峰提交**（3~6s），避免一次性 burst 打爆站点或触发 PV 限制。
            #   （旧实现「先全部 submit 再 sleep」既没防住 burst，又会因结果无 site_id 报 KeyError）
            import random as _r
            _delay_range = (3.0, 6.0)
            _pending: List[Tuple[Any, Any]] = []
            with ThreadPoolExecutor(max_workers=min(len(todo), queue)) as pool:
                for _i, _sid in enumerate(todo):
                    _pending.append((_sid, pool.submit(self._do, kind, _sid, kw)))
                    if _i < len(todo) - 1:
                        time.sleep(_r.uniform(*_delay_range))
                for _sid, _fut in _pending:
                    try:
                        _res = _fut.result()
                    except Exception as _err:  # noqa: BLE001
                        _res = {"ok": False, "message": f"执行异常：{_err}"}
                    if not isinstance(_res, dict):
                        _res = {"ok": False, "message": str(_res)}
                    _res.setdefault("site_id", _sid)
                    results.append(_res)
        done = [r for r in results if not r.get("skipped")]
        ok_n = sum(1 for r in done if r.get("ok"))
        fail_n = len(done) - ok_n
        lines = []
        for r in done:
            flag = "✅" if r.get("ok") else "❌"
            lines.append(f"{flag} {r.get('site_name') or r.get('site_id')}：{r.get('message')}")
        summary = {"total": len(results), "ok": ok_n, "fail": fail_n, "skipped": len(results) - len(done)}
        # ★ 重试排期：失败且命中关键词 → 当天延后补一次（按 PV 节奏：间隔+抖动、最多 2 次/天）
        try:
            self._plan_retries(kind, results, kw)
        except Exception as err:  # noqa: BLE001
            self._log(f"重试排期失败：{err}", "debug")
        if lines:
            try:
                self._plugin._store.journal.record(
                    task_id="signin",
                    kind="signin",
                    items=[OperationItem(hash=f"signin:{kind}", title=l, source=kind) for l in lines],
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"签到流水写入失败：{err}", "debug")
        notify = bool(cfg.get("notify", True))
        if notify and done:
            try:
                head = "魔流·站点签到" if kind == "sign" else "魔流·站点登录"
                self._plugin.post_message(
                    title=head,
                    text=f"{label}完成：成功 {ok_n} / 失败 {fail_n}\n" + "\n".join(lines[:15]),
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"签到通知发送失败：{err}", "warning")
        return {"ok": True, "kind": kind, "summary": summary, "results": results}

    def state(self, days: int = KEEP_DAYS) -> Dict[str, Any]:
        """给前端的状态汇总：站点（含今日结果）+ 近 N 天记录表。"""
        cfg = getattr(self._plugin, "_signin_cfg", {}) or {}
        data = self.records()
        today = data.get(_now_date(), {}) or {}
        out_sites: List[Dict[str, Any]] = []
        sign_ids = [str(x) for x in (cfg.get("sites") or [])]
        login_ids = [str(x) for x in (cfg.get("login_sites") or [])]
        for sid in sorted(set(sign_ids + login_ids), key=lambda x: int(x) if str(x).isdigit() else 0):
            site = self._site(sid)
            row = today.get(sid, {}) or {}
            out_sites.append({
                "site_id": sid,
                "site_name": _site_name(site, sid) or row.get("site_name", ""),
                "domain": str(getattr(site, "domain", "") or ""),
                "sign": bool(sid in sign_ids),
                "login": bool(sid in login_ids),
                "signin": row.get("sign"),
                "login_result": row.get("login"),
                "checked": bool(site and getattr(site, "cookie", None)),
                "handler": getattr(self._handler(site), "__name__", "") if site else "",
            })
        keep = max(1, int(days or KEEP_DAYS))
        dates = sorted(data.keys())[-keep:]
        table = []
        for d in dates:
            row = {"date": d, "sites": data.get(d, {})}
            table.append(row)
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "notify": bool(cfg.get("notify", True)),
            "sites": out_sites,
            "records": table,
            "today": _now_date(),
            "retry": self.retry_plan_view(),
            "ts": time.time(),
        }

    # ---------------------------------------------------------------- 调度
    def should_run_now(self) -> bool:
        """到点才跑：默认只在 9:00–23:00 之间（站点签到没必要半夜跑）。"""
        cfg = getattr(self._plugin, "_signin_cfg", {}) or {}
        hour = datetime.now().hour
        start = int(cfg.get("window_start", 9) or 0)
        end = int(cfg.get("window_end", 23) or 24)
        return start <= hour < end
