"""魔流 · 站点签到 / 模拟登录（3.6.0）。

借鉴 MoviePilot「站点自动签到」插件（thsrite / autosignin）的做法：
  · 通用签到 = 带站点 Cookie GET `attendance.php`（NexusPHP 访问即签到）；
  · 结果识别 = 未登录（密码框 / login.php）→ Cookie 失效；
              命中 `已签|签到已得|签到成功|每日签到` → 成功（或今日已签）；
  · 通用登录 = 带 Cookie GET 站点首页做「模拟登录」保活，并按结果刷新 MoviePilot 站点数据；
  · 失败文案命中「重试关键词」（默认 `错误|失败`）→ 重试一次；
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

SIGNIN_PAGE = "attendance.php"
HOME_PAGE = "index.php"
KEEP_DAYS = 7
DEFAULT_RETRY_KEYWORD = "错误|失败"
DEFAULT_QUEUE = 5

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

    def _get_text(self, site_id: Any, page: str) -> Tuple[str, Optional[str], int]:
        """复用站点实时抓取层（带 Cookie / UA / 超时 / PV 识别）。"""
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
    def _is_logged_in(text: str) -> bool:
        """优先用宿主 SiteUtils；失败回退正则。"""
        try:
            from app.sdk.network import SiteUtils  # noqa: WPS433

            return bool(SiteUtils.is_logged_in(text))
        except Exception:  # noqa: BLE001
            return bool(LOGGED_IN_RE.search(text or ""))

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
    ) -> Dict[str, Any]:
        row = {
            "ok": bool(ok),
            "message": str(message or ""),
            "ts": time.time(),
            "time": datetime.now().strftime("%H:%M:%S"),
            "skipped": bool(skipped),
        }
        if bonus:
            row["bonus"] = float(bonus)
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
        if self._is_api_site(site):
            return self._store_result("sign", site_id, name, True, "API 站点无签到页（跳过）", skipped=True)
        text, err, status = self._get_text(site_id, SIGNIN_PAGE)
        if not text:
            msg = f"签到失败：{err or ('HTTP %s' % status)}"
            return self._store_result("sign", site_id, name, False, msg)
        if PV_LIMIT_RE.search(text):
            return self._store_result("sign", site_id, name, False, "站点每日访问次数已达上限（今日不再尝试）")
        m = SIGNED_RE.search(text)
        if m or any(t in text for t in SIGNED_TEXTS):
            bonus = None
            if m:
                try:
                    bonus = float(m.group(1).replace(",", ""))
                except Exception:  # noqa: BLE001
                    bonus = None
            already = "已签" in text or m is not None
            msg = "今日已签到（+%s 魔力）" % int(bonus) if (already and bonus) else ("今日已签到" if already else "签到成功")
            return self._store_result("sign", site_id, name, True, msg, bonus=bonus)
        if LOGIN_HINT_RE.search(text) and not self._is_logged_in(text):
            return self._store_result("sign", site_id, name, False, "Cookie 已失效或未登录")
        return self._store_result("sign", site_id, name, True, "已执行（未识别到结果文案，可去站点确认）")

    # ---------------------------------------------------------------- 登录
    def login(self, site_id: Any) -> Dict[str, Any]:
        site = self._site(site_id)
        name = _site_name(site, site_id)
        if not site:
            return {"site_id": site_id, "site_name": name, "ok": False, "message": "站点不存在"}
        if self._is_api_site(site):
            return self._store_result("login", site_id, name, True, "API 站点（跳过）", skipped=True)
        started = time.time()
        text, err, status = self._get_text(site_id, HOME_PAGE)
        if not text:
            msg = f"模拟登录失败：{err or ('HTTP %s' % status)}"
            return self._store_result("login", site_id, name, False, msg)
        if PV_LIMIT_RE.search(text):
            return self._store_result("login", site_id, name, False, "站点每日访问次数已达上限（今日不再尝试）")
        if not self._is_logged_in(text):
            return self._store_result("login", site_id, name, False, "Cookie 已失效或未登录")
        self._refresh_site(site, seconds=int(time.time() - started))
        return self._store_result("login", site_id, name, True, "模拟登录成功（站点数据已刷新）")

    # ---------------------------------------------------------------- 跑批
    def _do(self, kind: str, site_id: Any, retry_keyword: str = "") -> Dict[str, Any]:
        fn = self.checkin if kind == "sign" else self.login
        res = fn(site_id)
        kw = str(retry_keyword or "").strip()
        if kw and not res.get("ok"):
            try:
                hit = bool(re.search(kw, str(res.get("message") or "")))
            except Exception:  # noqa: BLE001
                hit = False
            if hit:
                time.sleep(3)
                res = fn(site_id)
                res["retried"] = True
        return res

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
            with ThreadPoolExecutor(max_workers=min(len(todo), queue)) as pool:
                for res in pool.map(lambda s: self._do(kind, s, kw), todo):
                    results.append(res)
        done = [r for r in results if not r.get("skipped")]
        ok_n = sum(1 for r in done if r.get("ok"))
        fail_n = len(done) - ok_n
        lines = []
        for r in done:
            flag = "✅" if r.get("ok") else "❌"
            lines.append(f"{flag} {r.get('site_name') or r.get('site_id')}：{r.get('message')}")
        summary = {"total": len(results), "ok": ok_n, "fail": fail_n, "skipped": len(results) - len(done)}
        if lines:
            try:
                from .persistence import OperationItem  # noqa: WPS433

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
