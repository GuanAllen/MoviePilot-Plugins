"""魔流豆瓣评分源（douban.py）

为什么自己接
------------
MoviePilot 自带 **豆瓣模块**（``app/modules/douban``），但本部署实测：全局
``RECOGNIZE_SOURCE=themoviedb``，豆瓣模块的**按名字搜索**返回空
（``魔流`` 日志：``开始使用名称 X 匹配豆瓣信息 … 未匹配到豆瓣媒体信息``），
于是评分只能拿到 TMDB 的 ``vote_average``——对国产剧 / 综艺 / 老片经常是 0 或口径不符。

而豆瓣自己那套 ``frodo`` 接口（MP 用的同一套 apiKey/secret + HMAC 签名）是**通的**，
所以这里自带一个轻量客户端：**按名字搜 → 取豆瓣评分**。

设计要点（Master 2026-09-28 09:06 选「A」）
---------------------------------------
- **只读**：只查评分，不写任何东西；
- **带缓存**：命中 30 天、未命中/无评分 3 天（内存 + 插件 ``save_data`` 持久化，reload 不丢）；
- **限速**：请求间最小间隔 1.5s + 每轮预算（默认 60 次），超预算本轮直接回退 TMDB（防风控）；
- **失败退化**：任何异常都返回 None，调用方回退 TMDB，绝不阻断主流程。
"""
import base64
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# MP 主程序同款（公开在 jxxghp/MoviePilot app/modules/douban/apiv2.py）
_API_KEY = "0dad551ec0f84ed02907ff5c42e8ec70"
_API_SECRET = "bf7dddc7c9cfe6f7"
_BASE = "https://frodo.douban.com"
_SEARCH_PATH = "/api/v2/search/weixin"
_UA = (
    "api-client/1 com.douban.frodo/7.22.0.beta9(231) Android/23 product/Mate 40 vendor/HUAWEI "
    "model/Mate 40 brand/HUAWEI rom/android network/wifi platform/AndroidPad"
)

COOLDOWN_403 = 1800.0           # 被豆瓣风控（403/429）后，静默多久不再请求（实测 8 分钟 ~130 次就被封 IP）
COOLDOWN_ERR = 60.0             # 其它网络错误后的短冷却
HIT_TTL = 30 * 24 * 3600.0      # 有评分：30 天
MISS_TTL = 3 * 24 * 3600.0      # 没搜到 / 没开分：3 天
MIN_INTERVAL = 20.0             # 两次真实请求之间的最小间隔（秒）——豆瓣限流很凶，宁可慢
CACHE_KEY = "douban_rating_cache"
CACHE_MAX = 6000                # 持久化条数上限

_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def _norm(s: Any) -> str:
    return _NORM_RE.sub("", str(s or "").lower())


class DoubanRating:
    """豆瓣评分查询（带缓存 / 限速 / 预算 / 结果匹配）。"""

    def __init__(self, plugin: Any = None) -> None:
        self.plugin = plugin
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
        self._last_at = 0.0
        self._budget = 0            # 本轮剩余可查次数（0 = 不限）
        self._round_new = 0
        self._budget_skipped = 0
        self._blocked_until = 0.0
        self._loaded = False

    # ---------- 基础设施 ----------
    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(msg, level)
        except Exception:  # noqa: BLE001
            pass

    def _load(self) -> None:
        """从插件数据里恢复缓存（只做一次）。"""
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = self.plugin.get_data(CACHE_KEY)  # type: ignore[union-attr]
            if isinstance(raw, str):
                raw = json.loads(raw)
            if isinstance(raw, dict):
                now = time.time()
                for k, v in raw.items():
                    try:
                        ts, val = float(v[0]), v[1]
                    except Exception:  # noqa: BLE001
                        continue
                    if now - ts < max(HIT_TTL, MISS_TTL):
                        self._cache[str(k)] = (ts, val if isinstance(val, dict) else None)
        except Exception:  # noqa: BLE001
            pass

    def _save(self) -> None:
        try:
            items = sorted(self._cache.items(), key=lambda kv: kv[1][0], reverse=True)[:CACHE_MAX]
            self.plugin.save_data(key=CACHE_KEY, value={k: [v[0], v[1]] for k, v in items})  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    # ---------- 豆瓣 frodo ----------
    @staticmethod
    def _sign(path: str, ts: str) -> str:
        raw = "&".join(["GET", urllib.parse.quote(path, safe=""), ts])
        return base64.b64encode(
            hmac.new(_API_SECRET.encode(), raw.encode(), hashlib.sha1).digest()
        ).decode()

    def _http(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ts = time.strftime("%Y%m%d")
        q = dict(params)
        q.update({"apiKey": _API_KEY, "os_rom": "android", "_ts": ts, "_sig": self._sign(path, ts)})
        url = _BASE + path + "?" + urllib.parse.urlencode(q)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=12) as resp:
                if int(getattr(resp, "status", 200)) != 200:
                    self._cool(int(getattr(resp, "status", 0)))
                    return None
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as err:  # noqa: PERF203
            self._cool(int(getattr(err, "code", 0)))
            self._log(f"魔流:豆瓣查询被拒({err}) → 冷却 {int(self._blocked_until - time.time())}s", "warning")
            return None
        except Exception as err:  # noqa: BLE001
            self._blocked_until = max(self._blocked_until, time.time() + COOLDOWN_ERR)
            self._log(f"魔流:豆瓣查询失败({type(err).__name__}:{err})", "warning")
            return None

    def _cool(self, code: int = 0) -> None:
        """被风控就静默一段时间（403/429 长冷却，其它短冷却）。"""
        _sec = COOLDOWN_403 if code in (403, 429) else COOLDOWN_ERR
        self._blocked_until = max(self._blocked_until, time.time() + _sec)

    # ---------- 对外 ----------
    def begin_round(self, max_new: int = 0) -> None:
        """开始一轮（重置预算）。``max_new<=0`` = 不限。"""
        with self._lock:
            self._load()
            self._budget = int(max_new or 0)
            self._round_new = 0
            self._budget_skipped = 0

    def purge_negatives(self) -> int:
        """清掉缓存里的「未命中 / 未开分」条目（修复前被 403 污染的那些）。返回清掉的条数。"""
        with self._lock:
            self._load()
            bad = [k for k, v in self._cache.items() if not v[1]]
            for k in bad:
                self._cache.pop(k, None)
            if bad:
                self._save()
            return len(bad)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"cache": len(self._cache), "round_new": self._round_new,
                    "budget": self._budget, "budget_skipped": self._budget_skipped}

    def search(self, keyword: str, count: int = 6) -> Optional[List[Dict[str, Any]]]:
        """按关键字搜豆瓣 → 规范化候选列表。

        ★ 返回 ``None`` = **请求失败**（风控/网络），与 ``[]``（真的没结果）区分开——
        失败不能进缓存，否则一次 403 会污染 3 天。
        """
        data = self._http(_SEARCH_PATH, {"q": keyword, "start": 0, "count": count})
        if data is None:
            return None
        out: List[Dict[str, Any]] = []
        for it in ((data or {}).get("items") or []):
            tgt = it.get("target") or {}
            title = str(tgt.get("title") or "").strip()
            if not title:
                continue
            rating = tgt.get("rating") if isinstance(tgt.get("rating"), dict) else {}
            try:
                val = float(rating.get("value") or 0)
            except (TypeError, ValueError):
                val = 0.0
            out.append({
                "id": str(tgt.get("id") or ""),
                "title": title,
                "year": str(tgt.get("year") or ""),
                "rating": val,
                "votes": int(rating.get("count") or 0),
                "subtitle": str(tgt.get("card_subtitle") or ""),
            })
        return out

    @staticmethod
    def _pick(cands: List[Dict[str, Any]], title: str, year: str = "") -> Optional[Dict[str, Any]]:
        """从候选里挑最像的那个（标题 + 年份）。"""
        cands = cands or []
        want = _norm(title)
        if not want:
            return None
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        for c in cands:
            got = _norm(c.get("title"))
            if not got:
                continue
            score = 0
            if got == want:
                score += 10
            elif want in got or got in want:
                score += 5
            else:
                continue
            cy = str(c.get("year") or "")
            if year and cy:
                if cy == str(year):
                    score += 4
                else:
                    try:
                        if abs(int(cy) - int(str(year))) <= 1:
                            score += 2
                        else:
                            score -= 3
                    except (TypeError, ValueError):
                        pass
            elif not year and cy:
                score += 1
            if float(c.get("rating") or 0) > 0:
                score += 1
            if score > best_score:
                best_score, best = score, c
        return best

    def lookup(self, title: str, year: Any = "", *, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """查一部作品的豆瓣评分。

        返回 ``{"title","year","rating","votes","id","subtitle","ts"}``；
        搜不到 / 没开分返回 ``None``（同样进缓存，避免反复打豆瓣）。
        """
        key = f"{_norm(title)}|{str(year or '')}"
        if not _norm(title):
            return None
        with self._lock:
            self._load()
            if use_cache:
                hit = self._cache.get(key)
                if hit:
                    ts, val = hit
                    ttl = HIT_TTL if (val and float(val.get("rating") or 0) > 0) else MISS_TTL
                    if time.time() - ts < ttl:
                        return val
            # 风控冷却中 → 直接回退（不查、不写缓存）
            if time.time() < self._blocked_until:
                self._budget_skipped += 1
                return None
            # 预算（按「缓存未命中」的真实请求计数）
            if self._budget and self._round_new >= self._budget:
                self._budget_skipped += 1
                return None
            wait = MIN_INTERVAL - (time.time() - self._last_at)
        if wait > 0:
            time.sleep(min(wait, MIN_INTERVAL))
        q = f"{title} {year}".strip() if year else str(title)
        cands = self.search(q)
        if cands is None:  # 请求失败（风控/网络）→ 不写缓存，直接回退 TMDB
            with self._lock:
                self._last_at = time.time()
                self._round_new += 1
            return None
        best = self._pick(cands, title, str(year or ""))
        val: Optional[Dict[str, Any]] = None
        if best:
            val = dict(best)
            val["ts"] = time.time()
        with self._lock:
            self._last_at = time.time()
            self._round_new += 1
            self._cache[key] = (time.time(), val)
            if len(self._cache) % 25 == 0:
                self._save()
        return val


_client: Optional[DoubanRating] = None
_client_lock = threading.Lock()


def get_client(plugin: Any = None) -> DoubanRating:
    """进程内单例（跟着插件实例走）。"""
    global _client
    with _client_lock:
        if _client is None or getattr(_client, "plugin", None) is None and plugin is not None:
            _client = DoubanRating(plugin)
        elif plugin is not None:
            _client.plugin = plugin
    return _client
