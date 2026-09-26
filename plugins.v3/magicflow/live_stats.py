"""站点实时数据抓取 + 站点流量监控。

背景：MoviePilot 的站点账号数据（上传 / 下载 / 分享率 / 魔力 / 做种数）由 MP 自己的
「站点数据刷新」定时任务写入数据库（默认 **6 小时**一轮）。对"展示"够用，但魔流是拿它
**做决策**的（任务目标达标、救号分享率、兑换提醒、下载量异常增长），滞后 6 小时就是真偏差。

本模块直接抓**站点自身的用户栏页**（NexusPHP `index.php`），解析出**实时值**：

    分享率 / 上传 / 下载 / 当前做种 / 当前下载 / 每小时魔力 / 当前魔力

- 站点级缓存（默认 240s，可配）+ **single-flight**（同站并发只抓一次）+ 失败冷却；
- 抓不到时返回 `ok=False`，由调用方回退 MoviePilot 的数据（可选 + 回退）；
- 维护**采样环形缓冲**（内存 + 插件 data 持久化），据此算上传/下载速率与净增，
  供「站点流量监控」判定：Δ下载超阈值 → 告警（免费种不吃下载，涨下载=吃到促销尾巴）。

security：cookie 只发给该站点自己的域名；不落盘、不外传、不写日志。
"""
from __future__ import annotations

import html as _html
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# 采样历史：每站保留多少个点（按 240s 一点 ≈ 8 小时）
SAMPLE_MAX = 120
# 速率默认窗口（秒）
RATE_WINDOW_SEC = 3600.0
# 抓取默认 TTL（秒）——与候选列表抓取同口径，避免站点吃力
DEFAULT_TTL = 240.0
# 抓取失败后的站点级冷却（秒）
FAIL_COOLDOWN = 180.0
# 站点用户栏页（NexusPHP 通用）
DEFAULT_PAGE = "/index.php"
# ★ 站点「每日访问次数已达上限」页面特征（实测 PTT：用户等级控制量 300PV/天）
PV_LIMIT_MARKERS = ("访问次数已达上限", "访问次数已达", "今日访问次数", "PV")
# 命中访问上限后的封禁时长：到次日凌晨 + 这个宽限（秒）
PV_BLOCK_GRACE = 600.0
# 「正在下载」列表页（NexusPHP 通用，带促销标记）
LEECH_PAGE = "/getusertorrentlist.php?type=leeching&userid={uid}"
# 回退页：站点没getusertorrentlist 时用 userdetails 的「当前下载」表
LEECH_PAGE_ALT = "/userdetails.php?id={uid}"
# 正在下载列表的缓存（秒）—— 只在告警时抓，抓完短缓存避免连环请求
LEECH_TTL = 120.0

_SIZE_UNITS = {
    "B": 1.0,
    "K": 1024.0, "KB": 1024.0, "KIB": 1024.0,
    "M": 1024.0 ** 2, "MB": 1024.0 ** 2, "MIB": 1024.0 ** 2,
    "G": 1024.0 ** 3, "GB": 1024.0 ** 3, "GIB": 1024.0 ** 3,
    "T": 1024.0 ** 4, "TB": 1024.0 ** 4, "TIB": 1024.0 ** 4,
    "P": 1024.0 ** 5, "PB": 1024.0 ** 5, "PIB": 1024.0 ** 5,
}

_TAG_RE = re.compile(r"<[^>]+>")


def parse_size(text: Any) -> float:
    """'100.91GB' / '1,024.5 MB' → 字节数（float）。解析不出来返回 0.0。"""
    if text is None:
        return 0.0
    s = str(text).strip().replace(",", "").replace(" ", "")
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([KMGTP]?I?B?)$", s, re.IGNORECASE)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except (TypeError, ValueError):
        return 0.0
    unit = (m.group(2) or "B").strip().upper()
    mult = _SIZE_UNITS.get(unit)
    if mult is None:
        mult = _SIZE_UNITS.get(unit.rstrip("B")) if unit.endswith("B") else None
    return val * float(mult or 1.0)


def _to_text(raw: str) -> str:
    """HTML → 纯文本（去标签 + 反转义 + 归空白，保留 ⬆/⬇ 这类符号）。"""
    s = _TAG_RE.sub(" ", str(raw or ""))
    s = _html.unescape(s)
    s = s.replace("\xa0", " ").replace("\u3000", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def _first_num(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(str(m.group(1)).replace(",", ""))
    except (TypeError, ValueError, IndexError):
        return None


def parse_uid(raw: str) -> Optional[int]:
    """从任意站点页里抠出自己的 uid（`userdetails.php?id=116940` / `userid=116940`）。"""
    s = str(raw or "")
    m = re.search(r"userdetails\.php\?id=(\d+)", s)
    if not m:
        m = re.search(r"[?&]userid=(\d+)", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _is_free_promotion(cls: str, text: str) -> bool:
    """促销标记 → 是否「完全免费」（免费 / 2X免费 都算免费；50%免费 **不算**）。"""
    c = str(cls or "").lower()
    t = str(text or "").strip()
    if any(k in c for k in ("halfdown", "50pct", "30pct", "25pct", "1down")) or "%" in t:
        return False
    return bool("free" in c or ("免费" in t and "%" not in t))


def parse_leeching_rows(raw: str) -> List[Dict[str, Any]]:
    """解析「正在下载」列表 → [{tid, name, size, size_text, promotion, free}]（同 tid 去重）。"""
    s = str(raw or "")
    out: Dict[str, Dict[str, Any]] = {}
    pattern = re.compile(
        r"details\.php\?id=(\d+)[^>]*title=[\"']([^\"']+)[\"']",
        re.S | re.I,
    )
    for m in pattern.finditer(s):
        tid = str(m.group(1))
        # 取本行往后一段作为「行块」：标题格 + 紧跟的大小格（不同模板列数不同，只看第一个带单位的大小）
        block = s[m.start(): m.start() + 900]
        # 促销标记只认**标题格**（第一个 </td> 之前），避免扫到下一行
        title_cell = block.split("</td>")[0]
        pm = re.search(r"class=[\"']promotion\s*([a-z0-9_\- ]+)[\"']", title_cell, re.I)
        cls = (pm.group(1) if pm else "").strip()
        tm = re.search(r">\s*([^<>]{1,24}?)\s*</font>", title_cell)
        ptext = tm.group(1) if tm else ""
        sm = re.search(r"\b(\d[\d.,]*\s*[KMGTP]?i?B)\b", block, re.I)
        size_text = sm.group(1) if sm else ""
        if tid in out:
            continue
        out[tid] = {
            "tid": tid,
            "name": _html.unescape(str(m.group(2))).strip(),
            "size_text": size_text.strip(),
            "size": parse_size(size_text),
            "promotion": (ptext or cls).strip(),
            "free": _is_free_promotion(cls, ptext),
        }
    return list(out.values())


def parse_user_bar(raw: str) -> Dict[str, Any]:
    """解析 NexusPHP 用户栏 → {ratio, upload, download, seeding, leeching, bonus_per_hour, bonus}。

    容错：不同站点/模板字段名不同（上传 / 上传量、魔力值(x 魔力/小时) / x 魔力/小时），
    解析不出的字段为 None（**不猜值**），由调用方决定是否回退。
    只在**要求冒号/括号紧邻数字**的位置取值，避开页面公告里的「分享率低于…」等说明文字。
    """
    text = _to_text(raw)
    out: Dict[str, Any] = {
        "ratio": None,
        "upload": None,
        "download": None,
        "seeding": None,
        "leeching": None,
        "bonus_per_hour": None,
        "bonus": None,
        "uid": parse_uid(raw),
    }
    # 分享率（也兼容 "分享率 0.35"）
    val = _first_num(r"分享率[：:]\s*([0-9]+(?:\.[0-9]+)?)", text)
    if val is not None:
        out["ratio"] = val
    # 上传 / 下载（要求 "上传：100.91GB" 这种紧邻形式）
    m = re.search(r"上传(?:量)?[：:]\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["upload"] = parse_size(m.group(1))
    m = re.search(r"下载(?:量)?[：:]\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["download"] = parse_size(m.group(1))
    # 每小时魔力：魔力值(77.12魔力/小时) / 77.12 魔力/小时
    val = _first_num(r"魔力值?\(?\s*([0-9][0-9.,]*)\s*魔力?\s*/\s*(?:小时|時|h)", text)
    if val is None:
        val = _first_num(r"每小时\s*([0-9][0-9.,]*)\s*个?魔力", text)
    if val is not None:
        out["bonus_per_hour"] = val
    # 当前魔力：形如 "魔力值(77.12魔力/小时)[使用&说明]：4001.1"
    _tail = text
    _m = re.search(r"魔力值?\([^)]*\)", text)
    val = None
    if _m:
        val = _first_num(r"[^0-9]{0,40}?([0-9][0-9,]*(?:\.[0-9]+)?)", text[_m.end():])
    if val is None:
        val = _first_num(r"魔力值[^0-9]{0,30}?([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    if val is not None:
        out["bonus"] = val
    # 做种 / 下载数：优先抓 title 属性（"当前做种"），再退回 ⬆/⬇ 记法
    raw_s = str(raw or "")
    m = re.search(r"title\s*=\s*[\"']?(?:当前做种|做种中|做种)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["seeding"] = int(m.group(1))
    m = re.search(r"title\s*=\s*[\"']?(?:当前下载|下载中)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["leeching"] = int(m.group(1))
    if out["seeding"] is None:
        val = _first_num(r"⬆\s*([0-9]+)", text)
        if val is None:
            val = _first_num(r"(?:做种中|正在做种|做种)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["seeding"] = int(val)
    if out["leeching"] is None:
        val = _first_num(r"⬇\s*([0-9]+)", text)
        if val is None:
            val = _first_num(r"(?:下载中|正在下载)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["leeching"] = int(val)
    if out["ratio"] in (None, 0.0) and (out["upload"] or 0) > 0 and (out["download"] or 0) > 0:
        out["ratio"] = round(float(out["upload"]) / float(out["download"]), 3)
    return out


def is_pv_limited(text: Any) -> bool:
    """页面是否就是「今日访问次数已达上限」的拦截页。"""
    t = str(text or "")
    if not t or len(t) > 2000:
        return False
    return ("访问次数已达上限" in t) or ("访问次数已达" in t and "上限" in t)


def next_day_ts(now: Optional[float] = None) -> float:
    """下一个本地整点凌晨（+宽限）的时间戳。"""
    t = float(now if now is not None else time.time())
    local = time.localtime(t)
    nxt = time.mktime(
        (local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, -1)
    ) + 86400.0
    return nxt + PV_BLOCK_GRACE


def _norm_title(text: Any) -> frozenset:
    """标题归一化：小写、去 [组名]、非字母数字/汉字都当分隔符、去年代 → 词集合。"""
    s = str(text or "").lower()
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\b(19[0-9]{2}|20[0-9]{2})\b", " ", s)
    return frozenset(t for t in s.split() if len(t) > 1)


def title_match(a: Any, b: Any) -> bool:
    """两个标题是否同一 Release（处理「点 vs 空格」「站上带年代」这类差异）。

    规则：① 归一化后词集合完全相同 → 是；② Jaccard ≥ 0.8 → 是；
    ③ 弱一些但重叠过半且双方都不是空 → 交/并 ≥ 0.5。绝不靠猜。
    """
    sa, sb = _norm_title(a), _norm_title(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    inter = len(sa & sb)
    union = len(sa | sb)
    if union <= 0:
        return False
    j = inter / union
    return j >= 0.8 or (inter >= 3 and j >= 0.5)


class LiveStats:
    """站点实时数据 + 采样历史（速率/净增/告警判定）。"""

    def __init__(self, plugin: Any, ttl: float = DEFAULT_TTL) -> None:
        self._plugin = plugin
        self.ttl = float(ttl or DEFAULT_TTL)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._cooldown: Dict[str, float] = {}
        self._samples: Dict[str, List[List[float]]] = {}
        self._loaded = False
        self._leech: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._pv_block: Dict[str, float] = {}
        self._pv_loaded = False

    # ---------------------------------------------------------------- 抓取
    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self._plugin._log(f"[站点实时] {msg}", level)
        except Exception:  # noqa: BLE001
            pass

    def _site(self, site_id: int) -> Any:
        try:
            return self._plugin._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            return None

    def _get_text(self, site_id: int, page: str) -> Tuple[str, Optional[str], int]:
        """用站点 cookie 抓一页正文。返回 (text, error, status)。异常一律吞掉。"""
        site = self._site(site_id)
        if not site:
            return "", "站点不存在", 0
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        if not base:
            return "", "站点地址为空", 0
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return "", f"SDK 不可用: {err}", 0
        url = f"{base}/{str(page or DEFAULT_PAGE).lstrip('/')}"
        try:
            req = RequestUtils(
                cookies=getattr(site, "cookie", None),
                ua=getattr(site, "ua", None),
                timeout=30,
                referer=f"{base}/",
            )
            resp = req.get_res(url)
        except Exception as err:  # noqa: BLE001
            return "", f"请求失败: {err}", 0
        if resp is None:
            return "", "无响应", 0
        status = int(getattr(resp, "status_code", 0) or 0)
        try:
            raw = resp.content or b""
        except Exception:  # noqa: BLE001
            raw = b""
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", "ignore")
        if status >= 400 or not text:
            return "", f"HTTP {status}", status
        if is_pv_limited(text):
            return "", "站点每日访问次数已达上限", status
        return text, None, status

    def _fetch_once(self, site_id: int, page: str = DEFAULT_PAGE) -> Dict[str, Any]:
        """真抓一次（无缓存）。返回 {ok, ...}；异常一律 ok=False（绝不抛出）。"""
        site = self._site(site_id)
        if not site:
            return {"ok": False, "error": "站点不存在"}
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        text, err, status = self._get_text(site_id, page)
        if err:
            if "访问次数已达上限" in str(err):
                return {"ok": False, "pv_limited": True, "error": err, "status": status}
            return {"ok": False, "error": err, "status": status}
        url = f"{base}/{str(page or DEFAULT_PAGE).lstrip('/')}"
        parsed = parse_user_bar(text)
        got = [k for k, v in parsed.items() if v not in (None, 0.0)]
        if not got:
            return {"ok": False, "error": "用户栏未解析出字段（可能未登录/模板不同）", "status": status}
        out = {"ok": True, "site_id": int(site_id), "url": url, "status": status, "ts": time.time()}
        out.update(parsed)
        out["fields"] = got
        return out

    def leeching(self, site_id: int, force: bool = False) -> Dict[str, Any]:
        """抓「正在下载」列表（带促销标记）→ {ok, uid, rows, url}。

        供「下载量异常增长 → 清除非免费下载种」使用。短缓存（LEECH_TTL）避免连环请求。
        """
        if not site_id:
            return {"ok": False, "error": "缺少 site_id"}
        key = str(int(site_id))
        now = time.time()
        hit = self._leech.get(key)
        if hit and not force and (now - float(hit[0])) < LEECH_TTL:
            return dict(hit[1])
        live = self.get(site_id)
        uid = live.get("uid")
        if not uid:
            text, err, _st = self._get_text(site_id, DEFAULT_PAGE)
            uid = parse_uid(text) if not err else None
        if not uid:
            res = {"ok": False, "error": "未解析出 uid"}
            self._leech[key] = (now, res)
            return dict(res)
        page = LEECH_PAGE.format(uid=int(uid))
        text, err, status = self._get_text(site_id, page)
        rows: List[Dict[str, Any]] = []
        if not err:
            rows = parse_leeching_rows(text)
        if not rows and not err:
            # 回退：站点可能没有 getusertorrentlist，改用 userdetails.php 的「当前下载」表
            alt = LEECH_PAGE_ALT.format(uid=int(uid))
            text2, err2, _st2 = self._get_text(site_id, alt)
            if not err2:
                rows = parse_leeching_rows(text2)
                if rows:
                    page = alt
        if err and not rows:
            if "访问次数已达上限" in str(err):
                self._pv_block_site(int(site_id), str(err))
            res = {"ok": False, "error": err, "uid": int(uid), "pv_limited": "访问次数已达上限" in str(err)}
            self._leech[key] = (now, res)
            return dict(res)
        res = {
            "ok": True,
            "uid": int(uid),
            "page": page,
            "rows": rows,
            "ts": time.time(),
        }
        self._leech[key] = (now, res)
        return dict(res)

    # ---------------------------------------------------------------- 访问上限
    def _load_pv(self) -> None:
        if self._pv_loaded:
            return
        self._pv_loaded = True
        try:
            data = self._plugin.get_data("live_pv_block")
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            now = time.time()
            for k, v in data.items():
                try:
                    ts = float(v)
                except (TypeError, ValueError):
                    continue
                if ts > now:
                    self._pv_block[str(k)] = ts

    def pv_blocked_until(self, site_id: int) -> float:
        """该站点因「每日访问上限」被封到的绝对时间戳（0 = 未封）。"""
        self._load_pv()
        return float(self._pv_block.get(str(int(site_id)), 0.0) or 0.0)

    def _pv_block_site(self, site_id: int, reason: str = "访问次数已达上限") -> float:
        self._load_pv()
        until = next_day_ts()
        self._pv_block[str(int(site_id))] = until
        try:
            self._plugin.save_data("live_pv_block", dict(self._pv_block))
        except Exception:  # noqa: BLE001
            pass
        self._log(
            f"站点 {site_id} {reason}（今日已用完配额）→ 暂停抓取至 "
            f"{time.strftime('%m-%d %H:%M', time.localtime(until))}",
            "warning",
        )
        return until

    def get(self, site_id: int, force: bool = False, page: str = DEFAULT_PAGE) -> Dict[str, Any]:
        """带缓存 + single-flight 的实时数据。抓不到时**返回上次成功值并标记 stale**。"""
        if not site_id:
            return {"ok": False, "error": "缺少 site_id"}
        key = str(int(site_id))
        now = time.time()
        until = self.pv_blocked_until(int(site_id))
        if until > now:
            hit0 = self._cache.get(key)
            if hit0:
                out = dict(hit0)
                out.update({
                    "cached": True,
                    "stale": True,
                    "pv_limited": True,
                    "error": "站点每日访问次数已达上限",
                })
                return out
            return {
                "ok": False,
                "pv_limited": True,
                "error": "站点每日访问次数已达上限",
                "until": until,
            }
        hit = self._cache.get(key)
        if hit and not force and (now - float(hit.get("_at", 0))) < self.ttl:
            out = dict(hit)
            out["cached"] = True
            return out
        if not force and float(self._cooldown.get(key, 0)) > now:
            if hit:
                out = dict(hit)
                out.update({"cached": True, "stale": True, "error": out.get("error") or "冷却中"})
                return out
            return {"ok": False, "error": "冷却中"}
        lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            hit = self._cache.get(key)
            if hit and not force and (time.time() - float(hit.get("_at", 0))) < self.ttl:
                out = dict(hit)
                out["cached"] = True
                return out
            res = self._fetch_once(int(site_id), page=page)
            res["_at"] = time.time()
            if res.get("ok"):
                self._cooldown.pop(key, None)
                self._cache[key] = res
                self._push_sample(key, res)
                self._save_samples()
            else:
                self._cooldown[key] = time.time() + FAIL_COOLDOWN
                if res.get("pv_limited"):
                    self._pv_block_site(int(site_id), str(res.get("error") or "访问次数已达上限"))
                else:
                    self._log(f"站点 {site_id} 实时数据抓取失败：{res.get('error')}", "warning")
                if hit:  # 回退上次成功值（标记 stale）
                    out = dict(hit)
                    out.update({"cached": True, "stale": True, "error": res.get("error")})
                    return out
            return dict(res)

    # ---------------------------------------------------------------- 采样历史
    def _load_samples(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            data = self._plugin.get_data("live_samples")
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for k, rows in data.items():
                if isinstance(rows, list):
                    cleaned: List[List[float]] = []
                    for row in rows[-SAMPLE_MAX:]:
                        if isinstance(row, (list, tuple)) and len(row) >= 6:
                            try:
                                cleaned.append([float(x) for x in row[:6]])
                            except (TypeError, ValueError):
                                continue
                    if cleaned:
                        self._samples[str(k)] = cleaned

    def _save_samples(self) -> None:
        try:
            self._plugin.save_data("live_samples", {k: v[-SAMPLE_MAX:] for k, v in self._samples.items()})
        except Exception:  # noqa: BLE001
            pass

    def _push_sample(self, key: str, res: Dict[str, Any]) -> None:
        self._load_samples()
        row = [
            float(res.get("ts") or time.time()),
            float(res.get("upload") or 0.0),
            float(res.get("download") or 0.0),
            float(res.get("seeding") or 0.0),
            float(res.get("leeching") or 0.0),
            float(res.get("bonus") or 0.0),
        ]
        rows = self._samples.setdefault(key, [])
        # 相邻采样若站点数据没变（同一秒/完全一致）就跳过，避免速率被"零间隔"污染
        if rows and row[0] - rows[-1][0] < 30:
            rows[-1] = row
        else:
            rows.append(row)
        if len(rows) > SAMPLE_MAX:
            del rows[: len(rows) - SAMPLE_MAX]

    def history(self, site_id: int) -> List[List[float]]:
        self._load_samples()
        return list(self._samples.get(str(int(site_id)), []))

    def rates(self, site_id: int, window: float = RATE_WINDOW_SEC) -> Dict[str, Any]:
        """按采样历史算速率/净增（窗口内首末两点差）。"""
        rows = self.history(site_id)
        out = {
            "ok": False, "span_sec": 0.0, "samples": len(rows),
            "up_bps": 0.0, "down_bps": 0.0, "up_mb_min": 0.0, "down_mb_min": 0.0,
            "d_up": 0.0, "d_down": 0.0, "d_bonus": 0.0,
        }
        if len(rows) < 2:
            return out
        last = rows[-1]
        cutoff = last[0] - float(window or RATE_WINDOW_SEC)
        first = rows[0]
        for row in rows:
            if row[0] >= cutoff:
                first = row
                break
        span = float(last[0] - first[0])
        if span <= 0:
            return out
        d_up = float(last[1] - first[1])
        d_down = float(last[2] - first[2])
        d_bonus = float(last[5] - first[5])
        out.update({
            "ok": True, "span_sec": span, "samples": len(rows),
            "d_up": d_up, "d_down": d_down, "d_bonus": d_bonus,
            "up_bps": max(0.0, d_up / span), "down_bps": max(0.0, d_down / span),
            "up_mb_min": max(0.0, d_up / span) * 60.0 / (1024 ** 2),
            "down_mb_min": max(0.0, d_down / span) * 60.0 / (1024 ** 2),
        })
        return out

    # ---------------------------------------------------------------- 监控判定
    def evaluate(
        self,
        site_id: int,
        cfg: Optional[Dict[str, Any]] = None,
        live: Optional[Dict[str, Any]] = None,
        local_managed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """产出告警列表（纯函数式判断，不做任何写操作）。"""
        cfg = cfg or {}
        live = live if live is not None else self.get(site_id)
        rates = self.rates(site_id)
        alerts: List[Dict[str, Any]] = []
        if not live.get("ok"):
            if live.get("pv_limited"):
                alerts0 = [{
                    "kind": "pv_limit",
                    "level": "warn",
                    "text": (
                        "站点「每日访问次数已达上限」→ 已暂停抓取（含刷流浏览）至明日凌晨；"
                        "说明抓得太频，建议拉长选种/采样间隔"
                    ),
                }]
                return {"ok": False, "alerts": alerts0, "level": "warn", "rates": rates, "live": live}
            return {"ok": False, "alerts": [], "rates": rates, "live": live}

        # ① 下载量增长（唯一真危险信号：免费种不吃下载）
        thr_mb = float(cfg.get("download_alert_mb") or 50.0)
        down_mb_min = float(rates.get("down_mb_min") or 0.0)
        if rates.get("ok") and down_mb_min >= thr_mb:
            alerts.append({
                "kind": "download_rising",
                "level": "warn",
                "text": (
                    f"下载量在涨：近 {rates['span_sec'] / 60:.0f} 分钟 "
                    f"+{rates['d_down'] / (1024 ** 3):.2f}GB（≈{down_mb_min:.1f}MB/分钟）"
                    f"—— 可能有非免费/促销过期的种在跑"
                ),
            })
        # ② 分享率低于目标线
        tgt = float(cfg.get("ratio_target") or 0.0)
        ratio = live.get("ratio")
        if tgt > 0 and ratio is not None and float(ratio) < tgt:
            need = tgt * float(live.get("download") or 0.0) - float(live.get("upload") or 0.0)
            alerts.append({
                "kind": "ratio_low",
                "level": "warn",
                "text": (
                    f"分享率 {float(ratio):.3f} < 目标 {tgt:.2f}"
                    + (f"，还差 {max(0.0, need) / (1024 ** 3):.1f}GB 上传" if need > 0 else "")
                ),
            })
        # ③ 魔力够档（可提醒去兑换）
        bonus = float(live.get("bonus") or 0.0)
        if bonus >= 2000:
            alerts.append({
                "kind": "bonus_ready",
                "level": "info",
                "text": f"当前魔力 {bonus:.0f} ≥ 2000，可兑换 10GB 上传（留够考核余量再换）",
            })
        elif bonus >= 1200:
            alerts.append({
                "kind": "bonus_ready",
                "level": "info",
                "text": f"当前魔力 {bonus:.0f} ≥ 1200，可兑换 5GB 上传（留够考核余量再换）",
            })
        # ④ 站点视角做种数 vs 本地托管数
        if local_managed is not None and live.get("seeding") is not None:
            try:
                site_seed = int(live.get("seeding") or 0)
                local_seed = int(local_managed or 0)
            except (TypeError, ValueError):
                site_seed = local_seed = 0
            if local_seed >= 5 and site_seed * 2 < local_seed:
                alerts.append({
                    "kind": "seeding_mismatch",
                    "level": "warn",
                    "text": f"站内只认 {site_seed} 个做种，本地托管 {local_seed} 个 → 可能有种子未 announce/被暂停",
                })
        level = "info"
        for a in alerts:
            if a.get("level") == "warn":
                level = "warn"
                break
        return {"ok": True, "alerts": alerts, "level": level, "rates": rates, "live": live}

    def snapshot(
        self,
        site_id: int,
        cfg: Optional[Dict[str, Any]] = None,
        local_managed: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """实时数据 + 速率 + 告警 的组合快照（供 API 展示/看门狗使用）。"""
        live = self.get(site_id, force=force)
        ev = self.evaluate(site_id, cfg=cfg, live=live, local_managed=local_managed)
        return {
            "live": live,
            "rates": ev.get("rates") or {},
            "alerts": ev.get("alerts") or [],
            "level": ev.get("level") or "ok",
        }
