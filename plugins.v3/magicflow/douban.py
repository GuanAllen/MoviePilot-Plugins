"""魔流豆瓣评分源（HTTP 客户端版）。

评分数据与抓取/风控/缓存都搬到独立服务 **magicflow-douban** 里了
（本项目外，Docker 容器 `magicflow-douban:18789`，与 MoviePilot 同网络）。

本模块只负责：
1. 从插件配置读服务地址（``douban_service_url``，默认 ``http://magicflow-douban:18789``）；
2. 发 HTTP 请求 → 拿评分；
3. **服务不可用时返回 None**，调用方自动回退 TMDB（绝不阻断主流程）。

历史：v3.22.x 曾在插件内自带 frodo 客户端 + 本地快照（449 行），
因豆瓣按 IP 强限流 + 维护成本高，v3.23.0 拆成独立服务。
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_SERVICE_URL = os.environ.get("MAGICFLOW_DOUBAN_URL", "http://magicflow-douban:18789")
HTTP_TIMEOUT = float(os.environ.get("MAGICFLOW_DOUBAN_TIMEOUT", "6"))

_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

_PLUGIN_REGISTRY: Dict[int, "DoubanRating"] = {}
_REG_LOCK = threading.Lock()


def _norm(s: Any) -> str:
    """标题归一化（与服务端 & 旧快照实现保持一致）。"""
    return _NORM_RE.sub("", str(s or "").lower())


class DoubanRating:
    """magicflow-douban HTTP 客户端（每插件实例单例）。"""

    def __init__(self, plugin: Any = None, base_url: str = ""):
        self._plugin = plugin
        self._base = (base_url or self._cfg_url() or DEFAULT_SERVICE_URL).rstrip("/")
        self._round_new = 0
        self._lock = threading.RLock()
        self._last_err = ""
        self._last_ok = 0.0
        self._errors = 0

    # ---------- config ----------
    def _cfg_url(self) -> str:
        try:
            cfg = getattr(self._plugin, "_recommend_cfg", None) or {}
            return str(cfg.get("douban_service_url") or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    # ---------- http ----------
    def _req(self, path: str, method: str = "GET", body: Optional[dict] = None,
             timeout: float = HTTP_TIMEOUT) -> Optional[dict]:
        url = f"{self._base}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "{}")
            self._last_ok = time.time()
            return payload
        except Exception as err:  # noqa: BLE001
            self._last_err = f"{type(err).__name__}:{err}"
            self._errors += 1
            return None

    # ---------- public API（与旧实现兼容）----------
    def lookup(self, title: str, year: Any = "", *, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        if not _norm(title):
            return None
        payload = self._req("/search?" + urllib.parse.urlencode({"title": title or "", "year": year or ""}))
        if not payload:
            return None
        hit = payload.get("hit")
        if not hit:
            return None
        out = dict(hit)
        out.setdefault("source", "magicflow-douban")
        out["snapshot"] = True  # 兼容旧调用方的字段语义：来自本地库
        return out

    def lookup_batch(self, items: List[dict]) -> List[Optional[Dict[str, Any]]]:
        payload = self._req("/search_batch", method="POST",
                            body={"items": [{"title": i.get("title"), "year": i.get("year")} for i in items]})
        if not payload:
            return [None] * len(items)
        out = []
        for r in payload.get("results") or []:
            h = r.get("hit")
            if h:
                h = dict(h)
                h.setdefault("source", "magicflow-douban")
                h["snapshot"] = True
            out.append(h)
        return out

    def search(self, keyword: str, count: int = 6) -> Optional[List[dict]]:
        """本地服务不支持关键词模糊搜索，返回 None（调用方按「无结果」处理）。"""
        return None

    def begin_round(self, max_new: int = 0) -> None:
        with self._lock:
            self._round_new = 0

    def purge_negatives(self) -> int:
        payload = self._req("/cache/purge?only_negative=true", method="POST")
        if not payload:
            return 0
        return int(payload.get("purged") or 0)

    def refresh_snapshot(self) -> int:
        payload = self._req("/reload", method="POST")
        if not payload:
            return 0
        return int(payload.get("reloaded") or 0)

    def snapshot_stats(self) -> Dict[str, Any]:
        payload = self._req("/stats") or {}
        return {"total": int(payload.get("records") or 0), "cache": payload.get("cache") or {},
                "service": self._base, "ok": bool(payload)}

    def _snapshot_lookup(self, title: str, year: Any = "") -> Optional[Dict[str, Any]]:
        return self.lookup(title, year)

    def stats(self) -> Dict[str, Any]:
        st = self.snapshot_stats()
        st.update({"errors": self._errors, "last_error": self._last_err,
                   "last_ok": self._last_ok, "url": self._base})
        return st


def get_client(plugin: Any = None) -> DoubanRating:
    """按插件实例取单例客户端。"""
    key = id(plugin) if plugin is not None else 0
    with _REG_LOCK:
        cli = _PLUGIN_REGISTRY.get(key)
        if cli is None:
            cli = DoubanRating(plugin)
            _PLUGIN_REGISTRY[key] = cli
        else:
            # 配置可能改了服务地址 → 刷新
            new_base = cli._cfg_url()
            if new_base and new_base.rstrip("/") != cli._base:
                cli._base = new_base.rstrip("/")
        return cli
