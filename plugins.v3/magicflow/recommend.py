"""
MagicFlow 刷流种甄别与推荐（recommend.py）

背景：我们是**影视管理类**插件——下了的资源除了「刷魔力/刷流」，还有「看 / 收藏」的价值。
刷流/魔力任务大量复用「同 hash 的库内资源」（``已整理`` tag，由媒体资产价值闸门保护）；
本模块负责对**非资产**的刷流种做价值甄别：

    识别(片名) → 豆瓣评分 + 榜单/热映/命中订阅 → 值得则「推荐」；否则「临时种」

只依赖 MoviePilot 稳定插件接口（``app.sdk`` / ``app.chain`` / ``app.db.oper``），
且全部**惰性 import + 容错**：任何一步失败都退化（返回空/False），绝不阻断主流程。
"""
import re
import threading
import time
from typing import Any, Dict, Optional, Set

# 榜单/订阅索引缓存 TTL（秒）
CHART_TTL = 12 * 3600.0
SUBSCRIBE_TTL = 600.0

_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def _norm(s: Any) -> str:
    """标题规范化（去标点/空格、小写），用于跨源匹配。"""
    return _NORM_RE.sub("", str(s or "").lower())


def recognize(name: str) -> Optional[Any]:
    """识别种子名 → ``MediaInfo``（失败 / 非影视返回 None）。"""
    if not name:
        return None
    try:
        from app.sdk.media import MetaInfo  # type: ignore  # noqa: WPS433
        from app.chain.media import MediaChain  # type: ignore  # noqa: WPS433

        return MediaChain().recognize_by_meta(MetaInfo(name))
    except Exception:
        return None


class RecommendEngine:
    """推荐甄别引擎：识别 + 评分 + 榜单/订阅命中（带缓存、线程安全）。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._lock = threading.Lock()
        self._chart: Dict[str, Any] = {"ts": 0.0, "keys": set()}
        self._subs: Dict[str, Any] = {"ts": 0.0, "keys": set()}

    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(msg, level)
        except Exception:
            pass

    @staticmethod
    def _keys_of(info: Any) -> Set[str]:
        """把一个 MediaInfo/Subscribe 归一成可比较的标识键集合。"""
        keys: Set[str] = set()
        for attr in ("douban_id", "tmdb_id", "imdb_id"):
            v = getattr(info, attr, None)
            if v:
                keys.add(f"{attr}:{v}")
        ms, mid = getattr(info, "media_source", None), getattr(info, "media_id", None)
        if ms and mid:
            keys.add(f"sid:{ms}_{mid}")
        title = _norm(getattr(info, "title", None) or getattr(info, "name", None))
        year = str(getattr(info, "year", "") or "")
        if title:
            keys.add(f"t:{title}")
            if year:
                keys.add(f"ty:{title}:{year}")
        return keys

    def _chart_keys(self) -> Set[str]:
        now = time.time()
        if self._chart["ts"] and now - float(self._chart["ts"]) < CHART_TTL:
            return self._chart["keys"]
        with self._lock:
            if self._chart["ts"] and time.time() - float(self._chart["ts"]) < CHART_TTL:
                return self._chart["keys"]
            keys: Set[str] = set()
            try:
                from app.chain.douban import DoubanChain  # type: ignore  # noqa: WPS433
                dc = DoubanChain()
                for fn in (
                    dc.movie_top250, dc.movie_showing, dc.movie_hot,
                    dc.tv_hot, dc.tv_weekly_chinese, dc.tv_weekly_global,
                ):
                    try:
                        for m in (fn() or []):
                            keys |= self._keys_of(m)
                    except Exception:
                        continue
            except Exception as err:  # noqa: BLE001
                self._log(f"豆瓣榜单索引构建失败（忽略）: {err}", "warning")
            self._chart = {"ts": time.time(), "keys": keys}
            return keys

    def _subscribe_keys(self) -> Set[str]:
        now = time.time()
        if self._subs["ts"] and now - float(self._subs["ts"]) < SUBSCRIBE_TTL:
            return self._subs["keys"]
        keys: Set[str] = set()
        try:
            from app.db.oper.subscribe import SubscribeOper  # type: ignore  # noqa: WPS433
            for s in (SubscribeOper().list() or []):
                keys |= self._keys_of(s)
        except Exception as err:  # noqa: BLE001
            self._log(f"订阅索引构建失败（忽略）: {err}", "warning")
        self._subs = {"ts": time.time(), "keys": keys}
        return keys

    def subscribed_titles(self) -> Set[str]:
        """当前订阅的「归一化标题」集合（供刷流选种排除；从 ``_subscribe_keys`` 的 ``t:`` 键提取）。"""
        titles: Set[str] = set()
        for k in self._subscribe_keys():
            if isinstance(k, str) and k.startswith("t:") and len(k) > 2:
                titles.add(k[2:])
        return titles

    def evaluate(self, name: str) -> Dict[str, Any]:
        """甄别一个种子名。始终不抛异常；``recognized=False`` 表示识别不出/非影视。"""
        out: Dict[str, Any] = {"recognized": False}
        info = recognize(name)
        if not info:
            return out
        try:
            rating = float(getattr(info, "vote_average", 0) or 0)
        except Exception:  # noqa: BLE001
            rating = 0.0
        keys = self._keys_of(info)
        mtype = getattr(getattr(info, "type", None), "value", None) or str(
            getattr(info, "type", "") or ""
        )
        out.update(
            {
                "recognized": True,
                "title": getattr(info, "title", None),
                "year": getattr(info, "year", None),
                "type": mtype,
                "media_source": getattr(info, "media_source", None),
                "media_id": getattr(info, "media_id", None),
                "douban_id": getattr(info, "douban_id", None),
                "tmdb_id": getattr(info, "tmdb_id", None),
                "rating": rating,
                "in_chart": bool(keys & self._chart_keys()),
                "in_subscribe": bool(keys & self._subscribe_keys()),
            }
        )
        return out
