# -*- coding: utf-8 -*-
"""魔流 · ondemand —— 点播口子（MODEL.md §1「权威来源 1 = Master 主动声明」）。

流程（与 MODEL.md §1 一致）：
  输入片名 / 豆瓣·TMDB·IMDB 链接
    → **识别唯一资源**（``recognize`` / 按 id 识别）
    → 搜索选源（**免费优先**，其次做种数）
    → 下载
    → **直接转「资源」**（不观察、不分拣）。

实现上复用既有链路：``_mp_search_title``（MP 自带搜索）取候选、``_crossseed_torrent_bytes``
取 .torrent 字节、``downloader.add_torrent`` 落盘，最后只把「身份」这一步从自动扫描
换成手动指定 —— 下载中的 hash 记进 ``ondemand_pending``，一旦形成资源组
（``ResourceLedgerStore``）就 ``set_identity(资源)`` 并摘掉待办；在此期间分拣
（``_silent_triage``）**跳过**这些种，保证「不观察、不分拣」。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set

from app.schemas import Response

from ..recommend import recognize
from ..persistence import OperationItem
from ..tags import SUB_NEW, SUB_RESOURCE, STATE_ONDEMAND, STATE_SILENT, duty_of, identity_of, retag, tag_for
from ..sitestore import slot_callbacks
from ..fingerprint import info_hash

# 运行时导入（只有 MoviePilot 环境有 app.sdk）：离线单测无 app 包 → 退回标准 logging
logger = logging.getLogger("magicflow")
try:  # noqa: BLE001
    from app.sdk.logging import logger as _mp_logger  # noqa: WPS433
    logger = _mp_logger
except Exception:  # noqa: BLE001
    pass

_DOUBAN_RE = re.compile(r"movie\.douban\.com/subject/(\d+)")
_TMDB_RE = re.compile(r"themoviedb\.org/(?:movie|tv)/(\d+)")
_IMDB_RE = re.compile(r"imdb\.com/title/(tt\d+)")

# 最近一次搜索结果的短时缓存（秒）：让「选某一条」不必把站点再搜一遍（原搜索要 60~75s）
_OD_CACHE_TTL = 600

# ★ 17.1.1：``/agent/ondemand/add`` 找不到 pick 时的**续页上限**（搜第 0..N-1 页）。
#   根因：MP ``search_by_title(page=)`` 一次只给一页，pick 排在**第 2+ 页**时原来永远命中不了
#   （``/agent/ondemand/search`` 翻页看得到、add 却说「候选未命中」）。逐页过 PV 闸，有界。
_OD_ADD_MAX_PAGES = 3


def _od_is_free(dv: Any) -> bool:
    """下载因子是否「免费」。

    ★ 坑：不能写成 `float(dv or 1) <= 0` —— ``dv=0``（免费）会被 `or` 吃成 1。
    ``None``/异常 = 未如 → 按「不免费」处理。
    """
    try:
        v = 1.0 if dv is None else float(dv)
    except Exception:  # noqa: BLE001
        v = 1.0
    return v <= 0.0


def _od_iso(ts: Any) -> Optional[str]:
    """裸 epoch 秒 → ISO8601（带本地时区偏移）。

    ★ 干净清单口径：时间一律 ISO8601 字符串（AI 免换算）；缺/非法/``<=0`` → ``None``（**留值不留空洞**）。
    """
    try:
        v = float(ts or 0.0)
    except (TypeError, ValueError):
        return None
    if v <= 0.0:
        return None
    try:
        return datetime.fromtimestamp(v, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


_OD_KEY = "ondemand_pending"
# 17.1.0: ondemand history = persisted record slot (mf_run table).
_OD_HIST_KEY = "ondemand_history"
_OD_HIST_KEEP = 500


class OnDemandMixin:
    """点播：手动指定资源 → 搜索选源 → 下载 → 直接转「资源」。"""

    # ------------------------------------------------------------ 待办账

    # ------------------------------------------------------------ 搜索结果短时缓存

    def _ondemand_cache_get(self, raw: str, sites: List[int]) -> Optional[List[Dict[str, Any]]]:
        c = getattr(self, "_od_last", None)
        if not c:
            return None
        if time.time() - float(c.get("ts") or 0) > _OD_CACHE_TTL:
            return None
        if str(c.get("raw") or "") != str(raw or ""):
            return None
        if sorted(int(x) for x in (c.get("sites") or [])) != sorted(int(x) for x in (sites or [])):
            return None
        return list(c.get("rows") or [])

    def _ondemand_cache_put(self, raw: str, sites: List[int], rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        self._od_last = {
            "raw": str(raw or ""), "sites": [int(x) for x in (sites or [])],
            "rows": list(rows), "ts": time.time(),
        }

    def _ondemand_all(self) -> Dict[str, Dict[str, Any]]:
        try:
            rows = slot_callbacks(self, _OD_KEY)[0]() or {}
            return {str(k).lower(): dict(v or {}) for k, v in rows.items()}
        except Exception:  # noqa: BLE001
            return {}

    def _od_inflight_set(self) -> Set[str]:
        """★ 15.8.3（Master「下完之前别暂停」）：点播 in-flight hash 集。

        提供给 ``SilentGateMixin._silent_audit`` / ``_silent_enforce_pause`` 走单点过滤，
        避免 silent.py 跨域 self 调用（棘轮阻挡）。下完之后移出本集合，恢复静默闸管辖。
        """
        try:
            return {str(k).strip().lower() for k in (self._ondemand_all() or {})}
        except Exception:  # noqa: BLE001
            return set()

    def _ondemand_is_pending(self, h: str) -> bool:
        return str(h or "").lower() in self._ondemand_all()

    def _ondemand_mark(self, h: str, info: Dict[str, Any]) -> None:
        rows = self._ondemand_all()
        rows[str(h or "").lower()] = dict(info or {}, ts=time.time())
        try:
            slot_callbacks(self, _OD_KEY)[1](value=rows)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:待办落盘失败 {e}", "warning")

    def _ondemand_unmark(self, h: str) -> None:
        rows = self._ondemand_all()
        if rows.pop(str(h or "").lower(), None) is not None:
            try:
                slot_callbacks(self, _OD_KEY)[1](value=rows)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ 15.8.4 点播伪任务（__ondemand__）

    def _od_assign(self, hashes: Any, *, site: str = "", sub: str = "", reason: str = "") -> int:
        """★ 15.8.4：把「点播在途」的种挂到 ``__ondemand__`` 伪任务（职务=点播）。

        贴职务标签（身份轴 ``魔流-<站>-静默-<子类>`` 永久保留）+ 写账本（``taken_by=__ondemand__``）。
        效果：账本 ``state=点播`` ≠ 静默 → 静默池的**暂停闸**与**清理闸**
        （``_silent_purge_incomplete`` / ``_silent_drop_incomplete_now`` / ``_silent_audit``）双双跳过
        → 「没下完的点播种」不再被当静默半成品删/暂停。**不动下载状态**（正在下，不 pause、不 force_start）。
        幂等：已 ``taken_by=__ondemand__`` 的跳过。
        """
        from ..common import ONDEMAND_TASK_ID, ONDEMAND_TASK_NAME  # 惰性导入（离线测试不碰 common）
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        hs = [str(h or "").strip().lower() for h in hs if str(h or "").strip()]
        if not hs:
            return 0
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        store = self._tag_state()
        fn = getattr(downloader, "replace_torrent_tags", None)
        snap = self._tag_all_torrents()
        n = 0
        _now = time.time()
        for h in hs:
            hh = str(h or "").strip().lower()
            _rec0 = store.get(hh) or {}
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            _sub = str(sub or "") or str(_rec0.get("sub") or "") or _i_sub or SUB_RESOURCE
            _site = str(site or "") or str(_rec0.get("site") or "") or _i_site \
                or self._torrent_site_name(cur, "")
            # ★ 15.8.6：幂等 = 账本已挂 **且** qB 职务标签在位。
            #   只看账本会在「加种 ↔ qB 登记」抢跑时漏写标签、事后又永不补回。
            if str(_rec0.get("taken_by") or "") == ONDEMAND_TASK_ID \
                    and duty_of(cur)[1] == STATE_ONDEMAND:
                continue  # 已挂点播宿主且标签在位
            if cur:
                new_tags = retag(cur, site=_site, state=STATE_ONDEMAND, sub=_sub)
            else:
                new_tags = [tag_for(_site, STATE_SILENT, _sub), tag_for(_site, STATE_ONDEMAND)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {
                    "site": _site, "state": STATE_ONDEMAND, "sub": _sub,
                    "taken_by": ONDEMAND_TASK_ID, "task": ONDEMAND_TASK_NAME,
                    "taken_at": _now, "lease_until": 0,
                    "title": str(getattr(live, "title", "") or "") if live is not None else "",
                })
            except Exception:  # noqa: BLE001
                pass
            n += 1
        if n:
            self._log(f"点播:挂 __ondemand__ {n} 个（{reason or '在途'}）")
        return n

    def _od_release(self, hashes: Any, *, reason: str = "") -> int:
        """★ 15.8.4：点播结算（下完转资源）后，把种从 ``__ondemand__`` 释放回静默。

        退「点播」职务标签 + 清账本 ``taken_by/task`` → 回静默闸管辖（此后按资源身份入池 paused）。
        """
        from ..common import ONDEMAND_TASK_ID  # 惰性导入
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        hs = [str(h or "").strip().lower() for h in hs if str(h or "").strip()]
        if not hs:
            return 0
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        store = self._tag_state()
        fn = getattr(downloader, "replace_torrent_tags", None)
        snap = self._tag_all_torrents()
        n = 0
        _now = time.time()
        for h in hs:
            hh = str(h or "").strip().lower()
            _rec = store.get(hh) or {}
            if str(_rec.get("taken_by") or "") not in ("", ONDEMAND_TASK_ID):
                continue  # 已被别的宿主接管，不抢
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            _sub = str(_rec.get("sub") or "") or _i_sub or SUB_RESOURCE
            _site = str(_rec.get("site") or "") or _i_site or self._torrent_site_name(cur, "")
            new_tags = retag(cur, site=_site, state=STATE_SILENT, sub=_sub) \
                if cur else [tag_for(_site, STATE_SILENT, _sub)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {
                    "site": _site, "state": STATE_SILENT, "sub": _sub,
                    "taken_by": "", "task": "", "lease_until": 0,
                    "od_released_at": _now, "od_released_reason": str(reason or ""),
                })
            except Exception:  # noqa: BLE001
                pass
            n += 1
        if n:
            try:
                self._silent_pause_gate(hs)
            except Exception:  # noqa: BLE001
                pass
            self._log(f"点播:释放 __ondemand__ {n} 个（{reason or '结算'}）")
        return n

    def _ondemand_duty_reconcile(self) -> Dict[str, int]:
        """★ 15.8.4：点播「点播」职务对账（每 Check 轮一次，廉价）。

        ① pending 里未挂 ``__ondemand__`` 的 → 补挂（防漏）；
        ② 挂了 ``__ondemand__`` 但已不在 pending（已结算/被移除）的 → 释放回静默（防占）。
        """
        from ..common import ONDEMAND_TASK_ID  # 惰性导入
        pend = set((self._ondemand_all() or {}).keys())
        try:
            items = self._tag_state().items() or {}
        except Exception:  # noqa: BLE001
            return {"assigned": 0, "released": 0}
        # ★ 15.8.6：把**所有** pending 交给 ``_od_assign``——它按「账本已挂 **且** qB 职务标签
        #   在位」幂等过滤（治「加种抢先于 qB 登记」的漏标），本函数不再自带快照。
        to_assign = list(pend)
        to_release = [th for th, rec in items.items()
                      if str((rec or {}).get("taken_by") or "") == ONDEMAND_TASK_ID and th not in pend]
        a = self._od_assign(to_assign, reason="对账补挂") if to_assign else 0
        r = self._od_release(to_release, reason="对账释放") if to_release else 0
        return {"assigned": a, "released": r}

    # ------------------------------------------------------------ 第 1 步：识别

    @staticmethod
    def _ondemand_parse(query: str) -> Dict[str, str]:
        q = str(query or "").strip()
        out = {"query": q, "keyword": q, "doubanid": "", "tmdbid": "", "imdbid": ""}
        for pat, key in (
            (_DOUBAN_RE, "doubanid"), (_TMDB_RE, "tmdbid"), (_IMDB_RE, "imdbid"),
        ):
            m = pat.search(q)
            if m:
                out[key] = m.group(1)
                out["keyword"] = ""
        return out

    def _ondemand_media(self, q: Dict[str, str]) -> Optional[Any]:
        """识别唯一资源：片名走默认识别链；链接按 id 识别。"""
        kw = str(q.get("keyword") or "").strip()
        if kw:
            return recognize(kw)
        kwargs: Dict[str, Any] = {}
        if q.get("doubanid"):
            kwargs["doubanid"] = q["doubanid"]
        if q.get("tmdbid"):
            kwargs["tmdbid"] = q["tmdbid"]
        if q.get("imdbid"):
            kwargs["imdbid"] = q["imdbid"]
        if not kwargs:
            return None
        try:
            from app.chain.media import MediaChain  # noqa: WPS433
            return MediaChain().recognize_media(**kwargs)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:按 id 识别失败 {kwargs}: {e}", "warning")
            return None

    # ------------------------------------------------------------ 第 2 步：搜索

    def _ondemand_sites(self, task: Any = None, site_ids: str = "") -> List[int]:
        """候选站点集合：显式 site_ids > **全部已配置站点**。

        ★ 2026-10-01（Master「点播入口一定要挂在任务下么」）：点播**不再依赖任务**。
        此前不选任务 = 「所有启用任务的站点」（下拉却写着「全部站点」，名不副实）；
        现在不勾站点 = **MP 里所有站点**，``task`` 只决定保存目录，不再限定搜索范围。

        :param task: 兼容旧签名；**不再**用于限定站点（只影响保存目录，见 ``_ondemand_default_save_path``）。
        """
        ids: List[int] = []
        for x in str(site_ids or "").replace("，", ",").split(","):
            try:
                _i = int(str(x).strip())
            except Exception:  # noqa: BLE001
                continue
            if _i and _i not in ids:
                ids.append(_i)
        if ids:
            return ids
        try:
            for it in self._list_sites() or []:
                _i = int((it or {}).get("id") or 0)
                if _i and _i not in ids:
                    ids.append(_i)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:列出站点失败: {e}", "warning")
        return ids

    def _ondemand_search(self, keyword: str, site_ids: List[int],
                         page: int = 0) -> List[Dict[str, Any]]:
        """搜候选（**不过滤免费**，点播要的是这个资源本身）。

        ★ 17.1.1：``page`` 透传给 MP ``search_by_title(page=)`` —— MP 一次只回一页，
        要多页由调用方续（见 ``_ondemand_find_pick``）。每页各自过 PV 闸与计费。
        """
        kw = str(keyword or "").strip()
        ids = [i for i in (site_ids or []) if i]
        if not kw or not ids:
            return []
        try:
            pg = max(0, int(page or 0))
        except (TypeError, ValueError):
            pg = 0
        allowed = [
            i for i in ids
            if not self._pv_block_reason(i) and self._pv_allow(i, "ondemand", want=1)
        ]
        if not allowed:
            self._log("点播:候选站点 PV 预算不足/已封，跳过检索", "warning")
            return []
        try:
            hits = self._mp_search_title(kw, allowed, page=pg)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:MP 搜索失败: {e}", "warning")
            hits = []
        finally:
            for i in allowed:
                self._pv_spend(i, "ondemand", 1)
        rows: List[Dict[str, Any]] = []
        for ti in hits or []:
            r = self._od_row_from_ti(ti)
            if r:
                rows.append(r)
        self._log(f"点播:MP 搜索「{kw}」page={pg} {len(allowed)} 站 → 候选 {len(rows)} 条")
        return rows

    def _ondemand_find_pick(self, title: str, year: str, sites: List[int],
                            pick: str) -> List[Dict[str, Any]]:
        """★ 17.1.1：**逐页搜到 pick 命中为止**（有界 + 逐页过 PV 闸），返回「到此为止已见过的候选」。

        根因（Master 2026-10-10 报）：``_ondemand_add`` 原来只搜 MP 的**第 1 页**，
        候选排在第 2+ 页时永远命中不了 → 「搜索翻页看得到、add 加不进去」（真缺口：能看不能下）。

        边界（别拉爆站点 PV）：
        - 每关键词最多 ``_OD_ADD_MAX_PAGES`` 页（第 0..N-1 页），命中即停（**不多搜一页**）；
        - 某页**空**（无结果 / PV 闸停 / PV 预算不足）→ 判为页尾，停止续页；
        - 第一个关键词有货就不再试「片名+年份」（与改前 `_ondemand_add` 的口径一致）。
        """
        want = str(pick or "").strip()
        acc: Dict[str, Dict[str, Any]] = {}
        keys = [str(title or "").strip()]
        if str(year or "").strip():
            keys.append("%s %s" % (keys[0], str(year).strip()))
        for kw in keys:
            if not kw:
                continue
            for pg in range(_OD_ADD_MAX_PAGES):
                # 异常不私吞（同改前：直接冒到 ``/agent/ondemand/add`` 的错误回报），
                # 且 ``_ondemand_search`` 内部已记「MP 搜索失败」日志 —— 这里不再重复记。
                rows = self._ondemand_search(kw, sites, page=pg) or []
                for r in rows:
                    acc[str(r.get("enclosure") or "")] = r
                if any(str(r.get("enclosure") or "") == want for r in rows):
                    return list(acc.values())
                if not rows:
                    break          # 页尾（或 PV 闸停）→ 本关键词不再续页
            if acc:
                break              # 第一个关键词有货：不再试「片名+年份」
        return list(acc.values())

    # ------------------------------------------------------------ §3 搜索自描述（★ 15.9.0）

    @staticmethod
    def _od_row_from_ti(ti: Any) -> Optional[Dict[str, Any]]:
        """TorrentInfo（对象 / dict）→ 点播候选行（只读归一，真值源 = MP 的 TorrentInfo）。"""
        def _g(k: str, d: Any = None) -> Any:
            if isinstance(ti, dict):
                return ti.get(k, d)
            return getattr(ti, k, d)

        url = str(_g("enclosure", "") or "")
        if not url:
            return None
        _dv = _g("downloadvolumefactor", None)
        try:
            dv = 1.0 if _dv is None else float(_dv)
        except Exception:  # noqa: BLE001
            dv = 1.0

        def _int(k: str, d: int = 0) -> int:
            try:
                return int(_g(k, d) or 0)
            except Exception:  # noqa: BLE001
                return d

        try:
            size = float(_g("size", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            size = 0.0
        return {
            "title": str(_g("title", "") or ""),
            "size": size,
            "seeders": _int("seeders"),
            "peers": _int("peers"),
            "enclosure": url,
            "page_url": str(_g("page_url", "") or ""),
            "site": _int("site"),
            "site_name": str(_g("site_name", "") or ""),
            "site_cookie": _g("site_cookie", None),
            "site_ua": _g("site_ua", None),
            "site_proxy": bool(_g("site_proxy", False)),
            "downloadvolumefactor": dv,
            "free": dv <= 0.0,
            "counted_gb": round(size / 1e9 * dv, 2),
            "hit_and_run": bool(_g("hit_and_run", False)),
        }

    @staticmethod
    def _od_decode_source(source: str):
        """MP 续页令牌（``base64([site, keyword, search_id])``）→ ``(site:int, keyword:str)``（解不出 → ``(0, "")``）。"""
        try:
            from app.chain.search.manual import decode_source  # noqa: WPS433
            site, keyword, _sid = decode_source(str(source or ""))
            return (int(site) if str(site).isdigit() else 0), str(keyword or "")
        except Exception:  # noqa: BLE001
            return 0, ""

    @classmethod
    def _od_source_site(cls, source: str) -> int:
        """从 MP 续页令牌解出站点 id（解不出→0）。"""
        return cls._od_decode_source(source)[0]

    @classmethod
    def _od_source_fact(cls, raw: Any) -> Dict[str, Any]:
        """MP 单页分页来源事实 → 统一 ``sources[]`` 条目（§3.3）。**不平定义，只归一**。"""
        raw = raw if isinstance(raw, dict) else {}
        err = raw.get("error")
        err = str(err) if err else None
        if not err:
            outcome = "ok"
        elif "超时" in err or "timeout" in err.lower():
            outcome = "timeout"
        else:
            outcome = "error"
        tok = str(raw.get("source") or "")
        site: Any = cls._od_source_site(tok)
        if not site:
            site = None
        return {
            "source": tok,
            "site": site,
            "site_name": str(raw.get("site_name") or ""),
            "page": int(raw.get("page") or 0),
            "can_continue": bool(raw.get("can_continue")),
            "outcome": outcome,
            "error": err,
            "note": "",
        }

    async def _ondemand_search_sources(self, keyword: str, site_ids: List[int],
                                       page: int = 0, source: str = "") -> Dict[str, Any]:
        """★ 15.9.0 §3：点播候选 + **每站事实** —— **直接透传 MP 原生单页分页**。

        MP v3.1.2 自带 ``SearchChain().search_page_events(params=…)``（``app/chain/search/manual.py``）：

        - **客户端指定单页**（``page``），MP **不自留**分页进度；
        - 每个来源回 ``{source, site_name, page, can_continue, error}``，与我们的 ``sources[]`` 同构；
        - ``source`` 是**续页令牌**（回传它 + ``page=N+1`` 即续该站下一页；含 ``search_id`` 隔离本轮）；
        - 上限 ``MAX_SEARCH_PAGES=100``；复用 MP 的站点流控 / 别名回退 / 识别 / 过滤。

        我们**不做第二真值源**：类型判定 / 分页能力 / 别名 / 过滤全部听 MP。
        """
        kw = str(keyword or "").strip()
        pg = 0
        try:
            pg = max(0, int(page or 0))
        except (TypeError, ValueError):
            pg = 0
        src = str(source or "").strip()
        ids: List[int] = []
        for i in (site_ids or []):
            try:
                _i = int(i)
            except (TypeError, ValueError):
                continue
            if _i and _i not in ids:
                ids.append(_i)
        out: Dict[str, Any] = {
            "keyword": kw, "page": pg, "source": src, "sites": ids,
            "sources": [], "candidates": [], "total_items": 0, "candidate_items": 0,
        }
        if not kw and not src:
            return out
        # 站点集合 + PV 闸（与 ``_ondemand_search`` 同源；续页只针对令牌里的那个站）
        target_ids = ids or self._ondemand_sites()
        pkw = kw
        if src:
            _s, _kw = self._od_decode_source(src)
            target_ids = [_s] if _s else []
            pkw = _kw or kw   # 续页：MP 的 ``_prepare_page`` 仍需 ``keyword`` 在场（随后会被令牌覆盖）
            out["keyword"] = pkw
        allowed = [i for i in target_ids
                   if not self._pv_block_reason(i) and self._pv_allow(i, "ondemand", want=1)]
        if not allowed:
            self._log("点播:搜索站点 PV 预算不足/已封，跳过", "warning")
            return out
        out["sites"] = allowed
        params: Dict[str, Any] = {"page": pg}
        if src:
            params["source"] = src
            params["keyword"] = pkw
        else:
            params["keyword"] = kw
            params["sites"] = allowed
        try:
            from app.chain.search import SearchChain  # noqa: WPS433
            chain = SearchChain()
            ev = getattr(chain, "search_page_events", None)
            if not callable(ev):
                raise RuntimeError("当前 MP 无 search_page_events（需 v3.1.2+）")
            facts: List[Dict[str, Any]] = []
            items: List[Any] = []
            try:
                async for event in ev(params=params):
                    et = str((event or {}).get("type") or "")
                    if et == "error":
                        raise RuntimeError(str(event.get("message") or "搜索失败"))
                    if et == "replace":
                        raw = event.get("sources")
                        if raw:
                            facts = [self._od_source_fact(x) for x in raw]
                        items = list(event.get("items") or [])
                        try:
                            out["total_items"] = int(event.get("total_items") or 0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            out["candidate_items"] = int(event.get("candidate_items") or 0)
                        except (TypeError, ValueError):
                            pass
                    elif et == "done":
                        raw = event.get("sources")
                        if raw:
                            facts = [self._od_source_fact(x) for x in raw]
            finally:
                for i in allowed:
                    self._pv_spend(i, "ondemand", 1)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:MP 分页搜索失败: {e}", "warning")
            raise
        out["sources"] = facts
        rows: List[Dict[str, Any]] = []
        for it in items:
            ti = it.get("torrent_info") if isinstance(it, dict) else None
            if ti is None and isinstance(it, dict):
                ti = it
            r = self._od_row_from_ti(ti) if ti is not None else None
            if r:
                rows.append(r)
        out["candidates"] = sorted(rows, key=lambda r: (
            0 if _od_is_free(r.get("downloadvolumefactor")) else 1,
            -int(r.get("seeders", 0) or 0), -float(r.get("size", 0.0) or 0.0)))
        self._log(f"点播:MP 分页搜索「{kw or '(续页)'}」page={pg} → 来源 {len(facts)} / 候选 {len(rows)}")
        # ★ 17.1.1：本轮候选喂给「最近一次搜索」短时缓存 —— 让 /agent/ondemand/search →
        #   /agent/ondemand/add 真正衔接（add 命中即秒回，不再自己重搜一页 / 白烧 PV）。
        #   键 = 生效关键词（续页时取自令牌）+ 实际检索站点，与 add 的 ``_ondemand_cache_get`` 同口径。
        self._ondemand_cache_put(str(out.get("keyword") or ""), allowed, out["candidates"])
        return out

    def _ondemand_pick(self, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """选源：**免费优先** → 做种数多 → 体积大。"""
        if not rows:
            return None

        def _k(r: Dict[str, Any]) -> tuple:
            try:
                free = 1 if _od_is_free(r.get("downloadvolumefactor")) else 0
            except Exception:  # noqa: BLE001
                free = 0
            return (free, int(r.get("seeders", 0) or 0), float(r.get("size", 0.0) or 0.0))

        return max(rows, key=_k)

    # ------------------------------------------------------------ 第 3 步：下载

    def _ondemand_default_save_path(self) -> str:
        """未选任务（或任务没配保存目录）时的兜底目录：

        ① 插件设置「默认任务模板」的 ``save_path``；② 下载器（qB）全局 ``save_path``。
        （★ Master 报过：任务选「（全部站点）」时点下载 → 报「没填下载目录」。）
        """
        try:
            p = str((getattr(self, "_defaults", {}) or {}).get("save_path") or "").strip()
            if p:
                return p
        except Exception:  # noqa: BLE001
            pass
        try:
            res = self.get_downloader_prefs()
            data = getattr(res, "data", None) or {}
            p = str((data or {}).get("save_path") or "").strip()
            if p:
                return p
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _ondemand_download(self, row: Dict[str, Any], task: Any = None,
                           title: str = "", year: str = "") -> Dict[str, Any]:
        dl = self._get_downloader("qbittorrent")
        if dl is None or not getattr(dl, "is_available", False):
            return {"ok": False, "message": "下载器不可用"}
        content = self._crossseed_torrent_bytes(SimpleNamespace(**row))
        if not content:
            return {"ok": False, "message": "取 .torrent 失败（PV 闸门/站点拒绝）"}
        site_name = str(row.get("site_name") or "")
        save_path = str(getattr(task, "save_path", "") or "") if task is not None else ""
        if not save_path:
            save_path = self._ondemand_default_save_path()
        if not save_path:
            return {"ok": False, "message": "没有可用的保存目录：请在弹窗上方选一个任务，或到「设置 → 下载目录」填「任务保存目录」"}
        # ★ 15.8.6：**加种时就同时打「身份 + 职务」两个标签**——否则紧随其后的
        #   ``_od_assign`` 会在「qB 还没登记这颗新种」时写标签失败（竞态），
        #   「点播」职务标签要等下一轮对账才补上。
        if site_name:
            tag = ", ".join([tag_for(site_name, STATE_SILENT, SUB_RESOURCE),
                             tag_for(site_name, STATE_ONDEMAND)])
        else:
            tag = ""
        # ★ 10.2.0 下载即开账：只传域名（绝不传展示名），拿不到就留空
        try:
            _dom = self._site_domain_by_name(site_name) or ""
        except Exception:  # noqa: BLE001
            _dom = ""
        try:
            hs, err = dl.add_torrent(content=content, download_dir=save_path, tag=tag,
                                     site_domain=_dom,
                                     hit_and_run=bool(row.get("hit_and_run")))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"添加失败: {e}"}
        if not hs:
            # ★ 16.0.2：重复（qB 已有该种）→ 用内容算出的 infohash 复用，仍补 mark/assign（幂等收养）
            try:
                _h = str(info_hash(content) or "").lower()
            except Exception:  # noqa: BLE001
                _h = ""
            if _h and _h in (self._tag_all_torrents() or {}):
                h = _h
            else:
                return {"ok": False, "message": f"添加失败: {err or '未知'}"}
        else:
            h = str(hs[0] if isinstance(hs, (list, tuple)) else hs).lower()
        # ★ 15.8.4：加种即挂 __ondemand__ 伪任务（职务=点播）→ 未下完不被静默池删/暂停
        try:
            self._od_assign([h], site=site_name, sub=SUB_RESOURCE, reason="加种")
        except Exception as _oae:  # noqa: BLE001
            self._log(f"点播:挂伪任务失败 {h[:12]}: {_oae}", "warning")
        # ★ 16.0.1：同时写「点播 inflight」槽 → 静默闸 _silent_audit 跳过
        #   （只靠 _od_assign 写账本会撞「qB 还没登记新种」的竞态 → 在途种被判违规补暂停）
        try:
            self._ondemand_mark(h, {
                "title": str(row.get("title") or ""),
                "site": site_name,
                "site_id": int(row.get("site") or 0),
                "free": _od_is_free(row.get("downloadvolumefactor")),
                "hit_and_run": bool(row.get("hit_and_run")),
            })
        except Exception as _ome:  # noqa: BLE001
            self._log(f"点播:inflight 槽落盘失败 {h[:12]}: {_ome}", "warning")
        # 17.1.0：点播时落一条历史记录（清单只读它，此后不再现算/回查）
        try:
            _odf = _od_is_free(row.get("downloadvolumefactor"))
            _ods = site_name or str(int(row.get("site") or 0))
            self._ondemand_history_put(h, {
                "title": str(title or row.get("title") or ""),
                "year": str(year or ""),
                "site": site_name,
                "site_id": int(row.get("site") or 0),
                "free": _odf,
                "hit_and_run": bool(row.get("hit_and_run")),
                "size_gb": round(float(row.get("size") or 0.0) / (1024 ** 3), 3),
                "source_note": f"源 {_ods}" + ("·免费" if _odf else ""),
                "stage": "downloading",
                "added_at": time.time(),
                "settled_at": 0.0,
                "in_library": False,
            })
        except Exception as _ohe:  # noqa: BLE001
            logger.warning(f"魔流点播历史写入跳过 {h[:12]}: {_ohe}")
        return {
            "ok": True, "hash": h, "tag": tag,
            "site": int(row.get("site") or 0), "save_path": save_path,
        }

    def _ondemand_add(self, query: str = "", site_ids: str = "", pick: str = "",
                      task_id: str = "", apply: bool = True) -> Dict[str, Any]:
        """★ 16.0.0：**只按 AI 指定的源加种**（绝不自动选源）。

        与 `on_demand`（自动优选）区分：本方法要求 `pick` = 候选 `enclosure`，
        命中即下这条；未命中 → 如实回报「候选未命中，请先 search」，
        **不调** `_ondemand_pick`（选源权归 AI）。

        ★ 17.1.1：找 pick 由 ``_ondemand_find_pick`` 分页续搜（前 ``_OD_ADD_MAX_PAGES`` 页，有界），
        不再只认第 1 页 —— 修「搜索翻页看得到、add 加不进去」。
        """
        q = self._ondemand_parse(query)
        if not q["query"]:
            return {"ok": False, "message": "缺少 query（片名或链接）"}
        task = self._get_task_config(task_id) if task_id else None
        sites = self._ondemand_sites(task, site_ids)
        if not sites:
            return {"ok": False, "message": "没有可搜的站点（site_ids / 任务站点均为空）"}
        pick = str(pick or "").strip()
        if not pick:
            return {"ok": False, "message": "缺少 pick（候选 enclosure / 下载链接）"}
        title = year = ""
        rows = self._ondemand_cache_get(q["query"], sites) or []
        if not rows:
            media = self._ondemand_media(q)
            if media is not None:
                try:
                    title = str(getattr(media, "title", "") or "")
                    year = str(getattr(media, "year", "") or "")
                except Exception:  # noqa: BLE001
                    title, year = "", ""
            if not title:
                title = q["keyword"] or q["query"]
            # ★ 17.1.1：命中失败不再只看 MP 第 1 页 —— 逐页续搜（有界）到 pick 命中/页尾/上限
            rows = self._ondemand_find_pick(title, year, sites, pick)
            self._ondemand_cache_put(q["query"], sites, rows)
        row = next((r for r in rows if str(r.get("enclosure") or "") == pick), None)
        if row is None:
            return {"ok": False, "message": "候选未命中，请先 search（已续搜前 %d 页，候选可能更靠后）"
                                            % _OD_ADD_MAX_PAGES}
        save_path = (str(getattr(task, "save_path", "") or "") if task is not None else "")\
            or self._ondemand_default_save_path()
        plan = {
            "title": row.get("title") or "",
            "size": row.get("size"),
            "downloadvolumefactor": row.get("downloadvolumefactor"),
            "free": _od_is_free(row.get("downloadvolumefactor")),
            "hit_and_run": bool(row.get("hit_and_run")),
            "counted_gb": round(float(row.get("size") or 0.0) / 1e9
                                * float(row.get("downloadvolumefactor") or 0.0), 2),
            "save_path": save_path,
            "site": row.get("site_name") or row.get("site") or "",
        }
        if not apply:
            return {"ok": True, "applied": False, "dry_run": True, "plan": plan}
        res = self._ondemand_download(row, task, title=title, year=year)
        if not res.get("ok"):
            return {"ok": False, "message": str(res.get("message") or "下载失败"), "plan": plan}
        return {"ok": True, "applied": True, "hash": res.get("hash") or "", "plan": plan}

    # ------------------------------------------------------------ 结算（下载完 → 资源）

    def _ondemand_settle(self, task: Any = None) -> Dict[str, int]:
        """把已形成资源组的点播种子**直接转「资源」**（不观察、不分拣）。"""
        # ★ 15.8.4：先对账「点播」职务（补挂漏的 / 释放已结算的），再干活
        try:
            _rc = self._ondemand_duty_reconcile()
            if _rc.get("assigned") or _rc.get("released"):
                self._log(f"点播:职务对账 补挂 {_rc.get('assigned')} / 释放 {_rc.get('released')}")
        except Exception as _rce:  # noqa: BLE001
            self._log(f"点播:职务对账异常: {_rce}", "warning")
        pend = self._ondemand_all()
        if not pend:
            return {"settled": 0}
        try:
            files = self._tag_groups()
        except Exception:  # noqa: BLE001
            return {"settled": 0}
        snap = self._tag_all_torrents() or {}
        done = 0
        for h, info in list(pend.items()):
            t = snap.get(h)
            if t is None:
                continue   # 还没进下载器（或已被移走）→ 继续等
            # ★ 必须等**下载完成**才结算：进度没到 100% 就整理入库，会把半截文件
            #   硬链接进媒体库（MP 整理的是文件不是种子，不管下没下完）。
            try:
                _prog = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                _prog = 0.0
            if _prog < 0.999:
                continue
            gid = ""
            try:
                gid = files.group_of(h)
            except Exception:  # noqa: BLE001
                gid = ""
            if not gid:
                continue   # 资源组还没建立 → 等对账/纳管
            try:
                files.set_identity(gid, SUB_RESOURCE, by="ondemand")
            except Exception as e:  # noqa: BLE001
                self._log(f"点播:转资源失败 {h[:12]}: {e}", "warning")
                continue
            self._ondemand_unmark(h)
            # ★ 15.8.4：转资源即退「点播」职务 → 交回静默闸管辖
            try:
                self._od_release([h], reason="结算转资源")
            except Exception:  # noqa: BLE001
                pass
            done += 1
            _title = str(info.get("title") or info.get("media") or "")
            self._log(f"点播:转「资源」 {h[:12]} 「{_title}」")
            # ★ 2026-10-01：点播是「我要看这部片」→ 转资源后**顺手整理入库**
            #   （MP 手动整理：transfer_type=link → 硬链接进媒体库，种子照旧做种，不删不移）
            _ok_import = self._ondemand_import(h, gid, _title)
            # 17.1.0：点播历史记录 → 已转「资源」（落盘记录，清单只读它）
            self._ondemand_history_update(h, stage="resource", settled_at=time.time(),
                                          in_library=bool(_ok_import))
            # ★ 11.11.0：转资源后入池即暂停（静默硬不变量；任务纳管时才做种）
            try:
                self._silent_pause_gate(h)
            except Exception:  # noqa: BLE001
                pass
        return {"settled": done}

    def _ondemand_import(self, h: str, gid: str = "", title: str = "") -> bool:
        """点播种转「资源」后整理入库（复用推荐链路的 MP ``TransferChain.manual_transfer``）。

        识别失败/取种失败都只记日志、**不阻断**（文件留在下载目录，可下次再整理）。
        """
        _h = str(h or "").lower()
        if not _h:
            return False
        try:
            ok, msg = self._recommend_import(_h, {"title": str(title or ""), "group_id": str(gid or "")})
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:整理入库异常 {_h[:12]}: {e}", "warning")
            return False
        self._log(
            f"点播:整理入库 {_h[:12]} 「{title}」→ {'完成' if ok else '未整理'} {msg or ''}".rstrip()
        )
        return bool(ok)

    # ------------------------------------------------------------ 清单（进度 + 历史）

    def _ondemand_snapshot(self) -> Dict[str, Any]:
        """qB 快照（hash → TorrentInfo）；拿不到就退化为空（清单不报错）。"""
        try:
            return self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            return {}

    def _ondemand_seed_rec(self, h: str) -> Dict[str, Any]:
        """读种子账本行（真值源 ``SeedLedgerStore``）：state/sub/in_library/identity_at。"""
        try:
            return self._tag_state().get(str(h or "").lower()) or {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------ 点播历史（17.1.0 落盘记录）

    @staticmethod
    def _ondemand_hist_title(title: str) -> str:
        """历史行的展示名：把 journal 里的「点播 xxx」前缀去掉（仅一次性迁移用）。"""
        t = str(title or "").strip()
        if t.startswith("点播"):
            t = t[len("点播"):].strip()
        return t

    @staticmethod
    def _ondemand_hist_site(reason: str) -> str:
        """从 journal 的 reason（如「源 财神·免费」）回填站点名（仅一次性迁移用）。"""
        r = str(reason or "").strip()
        if r.startswith("源"):
            r = r[len("源"):].strip()
        for sep in ("·", " ", "，", ","):
            if sep in r:
                r = r.split(sep)[0].strip()
                break
        return r


    def _ondemand_history_read(self, limit: int = _OD_HIST_KEEP) -> List[Dict[str, Any]]:
        """读点播历史记录（新 → 旧）。

        17.1.0（Master 2026-10-13：「没必要动态，做个记录就好」）：真值源 = ondemand_history 槽
        （mf_run 表，点播时**落一条记录**）—— 清单只读它，**不再**每次动态拼 journal + 现况回查。
        """
        try:
            data = slot_callbacks(self, _OD_HIST_KEY)[0]() or {}
        except Exception:  # noqa: BLE001
            data = {}
        rows = (data.get("rows") if isinstance(data, dict) else data) or []
        rows = [r for r in rows if isinstance(r, dict)]
        rows.sort(key=lambda r: float(r.get("added_at") or 0.0), reverse=True)
        try:
            n = max(1, min(int(limit or _OD_HIST_KEEP), _OD_HIST_KEEP))
        except (TypeError, ValueError):
            n = _OD_HIST_KEEP
        return rows[:n]

    def _ondemand_history_save(self, rows: List[Dict[str, Any]]) -> None:
        """写点播历史记录（保留最近 _OD_HIST_KEEP 条）。"""
        try:
            slot_callbacks(self, _OD_HIST_KEY)[1](value={"seeded": True, "rows": list(rows or [])[:_OD_HIST_KEEP]})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史落盘失败（忽略）：{e}")

    def _ondemand_history_put(self, h: str, fields: Dict[str, Any]) -> None:
        """17.1.0：点播时落一条历史记录（按 hash 幂等；新记录置顶）。"""
        hh = str(h or "").strip().lower()
        if not hh:
            return
        try:
            rows = [r for r in self._ondemand_history_read() if str(r.get("hash") or "") != hh]
            rec: Dict[str, Any] = {"hash": hh}
            rec.update({k: v for k, v in dict(fields or {}).items() if v is not None})
            rows.insert(0, rec)
            self._ondemand_history_save(rows)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史写入失败（忽略）：{e}")

    def _ondemand_history_update(self, h: str, **fields: Any) -> None:
        """更新一条历史记录（结算转「资源」/ 撤单标 removed）。"""
        hh = str(h or "").strip().lower()
        if not hh:
            return
        try:
            rows = self._ondemand_history_read()
            for r in rows:
                if str(r.get("hash") or "") != hh:
                    continue
                r.update({k: v for k, v in fields.items() if v is not None})
                self._ondemand_history_save(rows)
                return
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史更新失败（忽略）：{e}")

    def _ondemand_history_backfill(self) -> None:
        """★ 17.1.0 一次性迁移：槽还没落过记录时，把 journal 里已有的点播记录灌成落盘记录。

        只跑一次（写回时置 seeded 标记）；此后清单只看落盘记录，不再回看 journal / 现况回查。
        """
        try:
            data = slot_callbacks(self, _OD_HIST_KEY)[0]() or {}
        except Exception:  # noqa: BLE001
            data = {}
        if isinstance(data, dict) and data.get("seeded"):
            return
        rows: List[Dict[str, Any]] = []
        try:
            recs = self._store.journal.list_recent(limit=5000) if self._store is not None else []
        except Exception:  # noqa: BLE001
            recs = []
        try:
            snap = self._ondemand_snapshot()
        except Exception:  # noqa: BLE001
            snap = {}
        for r in recs:
            for it in (getattr(r, "items", None) or []):
                if str(getattr(it, "source", "") or "") != "ondemand":
                    continue
                h = str(getattr(it, "hash", "") or "").lower()
                if not h or any(str(x.get("hash") or "") == h for x in rows):
                    continue
                rec = self._ondemand_seed_rec(h)
                inlib = bool((rec or {}).get("in_library"))
                sub = str((rec or {}).get("sub") or "")
                size_gb = 0.0
                try:
                    size_gb = float(getattr(it, "size_gb", 0) or 0.0)
                except (TypeError, ValueError):
                    size_gb = 0.0
                if not size_gb and snap.get(h) is not None:
                    try:
                        size_gb = float(getattr(snap.get(h), "size_gb", 0) or 0.0)
                    except (TypeError, ValueError):
                        size_gb = 0.0
                _reason = str(getattr(it, "reason", "") or "")
                rows.append({
                    "hash": h,
                    "title": self._ondemand_hist_title(str(getattr(it, "title", "") or "")),
                    "year": "",
                    "site": str((rec or {}).get("site") or "") or self._ondemand_hist_site(_reason),
                    "site_id": 0,
                    "free": bool((rec or {}).get("free")),
                    "hit_and_run": bool((rec or {}).get("hit_and_run")),
                    "size_gb": round(size_gb, 3),
                    "source_note": _reason,
                    "stage": "resource" if (sub == SUB_RESOURCE or inlib) else "gone",
                    "added_at": float(getattr(r, "created_at", 0) or 0.0),
                    "settled_at": float((rec or {}).get("identity_at") or 0.0),
                    "in_library": inlib,
                })
        self._ondemand_history_save(rows)


    def _ondemand_inflight_row(self, h: str, info: Dict[str, Any], t: Any, rec: Dict[str, Any]) -> Dict[str, Any]:
        """进行中一行（干净清单 Item）：身份 + qB 进度。

        ★ 15.9.0 换皮：字段与历史行**同构**（stage / percent / downloaded_gb / ISO 时间…）。
        内部 ``_ts`` 仅用于排序，出清单前会剥掉。
        """
        base_ts = info.get("ts") or 0.0
        row: Dict[str, Any] = {
            "hash": h,
            "module": "ondemand",
            "stage": "gone", "stage_text": "已不在下载器",
            "title": str(info.get("title") or info.get("media") or ""),
            "year": str(info.get("year") or ""),
            "site": str(info.get("site") or ""),
            "progress": 0.0, "percent": 0.0, "state": "",
            "size_gb": 0.0, "downloaded_gb": 0.0, "left_gb": 0.0,
            "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": bool(info.get("free")),
            "hit_and_run": bool(info.get("hit_and_run")),
            "in_qb": t is not None,
            "in_library": bool((rec or {}).get("in_library")),
            "save_path": "",
            "added_at": _od_iso(base_ts),
            "settled_at": _od_iso((rec or {}).get("identity_at")),
            "source_note": "",
            "_ts": float(base_ts or 0.0),
        }
        if t is None:
            return row
        prog = float(getattr(t, "progress", 0) or 0.0)
        size_gb = float(getattr(t, "size_gb", 0) or 0.0)
        spd = float(getattr(t, "download_speed", 0) or 0.0)
        left_gb = max(0.0, size_gb * (1.0 - prog))
        row.update({
            "progress": round(prog, 4),
            "percent": round(prog * 100.0, 2),
            "state": str(getattr(t, "state", "") or ""),
            "size_gb": round(size_gb, 3),
            "downloaded_gb": round(size_gb * prog, 3),
            "left_gb": round(left_gb, 3),
            "speed": round(spd, 1),
            "ratio": round(float(getattr(t, "ratio", 0) or 0.0), 3),
            "save_path": str(getattr(t, "save_path", "") or ""),
        })
        if prog < 0.999:
            row["stage"] = "downloading"
            row["stage_text"] = "下载中"
            if spd > 0:
                row["eta_s"] = int(left_gb * (1024 ** 3) / spd)
        elif str((rec or {}).get("sub") or "") == SUB_RESOURCE:
            row["stage"] = "resource"
            row["stage_text"] = "已转「资源」"
        else:
            row["stage"] = "settling"
            row["stage_text"] = "已下完，待转「资源」"
        return row

    def _ondemand_hist_row(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """历史一行（干净清单 Item）：**只读落盘记录**。

        17.1.0：不再动态拼 journal / 现况回查（qB、账本）—— 行内一切取自 ondemand_history
        记录；stage 由记录定：resource = 已转「资源」；其余 = 已结案。字段与进行中行**同构**。
        """
        stage = str(rec.get("stage") or "gone")
        size_gb = round(float(rec.get("size_gb") or 0.0), 3)
        if stage == "resource":
            stage_text = "已转「资源」" + ("·已入库" if rec.get("in_library") else "")
        else:
            stage_text = "已结案"
        return {
            "hash": str(rec.get("hash") or ""),
            "module": "ondemand",
            "stage": "resource" if stage == "resource" else "gone",
            "stage_text": stage_text,
            "title": str(rec.get("title") or ""),
            "year": str(rec.get("year") or ""),
            "site": str(rec.get("site") or ""),
            "progress": 1.0 if stage == "resource" else 0.0,
            "percent": 100.0 if stage == "resource" else 0.0,
            "state": "",
            "size_gb": size_gb,
            "downloaded_gb": size_gb if stage == "resource" else 0.0,
            "left_gb": 0.0,
            "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": bool(rec.get("free")),
            "hit_and_run": bool(rec.get("hit_and_run")),
            "in_qb": False,
            "in_library": bool(rec.get("in_library")),
            "save_path": "",
            "added_at": _od_iso(rec.get("added_at")),
            "settled_at": _od_iso(rec.get("settled_at")),
            "source_note": str(rec.get("source_note") or ""),
            "_ts": float(rec.get("added_at") or 0.0),
        }

    def _ondemand_items(self, limit: int = 50) -> Dict[str, Any]:
        """点播干净清单：**单列表** items[]（进行中+历史**同构**）+ totals。

        真值源（只读）：
          - 进行中 = ondemand_pending（mf_seed.pending）× qB 快照（进度/状态/速度）；
          - 历史 = **点播历史落盘记录**（ondemand_history 槽；点播时写、结算/撤单时更新）
            —— 17.1.0 起不再动态拼 journal + 现况回查。
        """
        try:
            cap = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            cap = 50
        self._ondemand_history_backfill()   # 17.1.0：一次性把已有 journal 点播灌成落盘记录
        pend = self._ondemand_all()
        snap = self._ondemand_snapshot()
        rows: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for h, info in pend.items():
            seen.add(h)
            rows.append(self._ondemand_inflight_row(h, info, snap.get(h), self._ondemand_seed_rec(h)))
        for rec in self._ondemand_history_read():
            h = str(rec.get("hash") or "").lower()
            if not h or h in seen:
                continue
            if str(rec.get("stage") or "") == "removed":
                continue   # 本线撤单过 → 点播窗口不展示
            seen.add(h)
            rows.append(self._ondemand_hist_row(rec))
        rows.sort(key=lambda x: float(x.get("_ts") or 0.0), reverse=True)
        rows = rows[:cap]
        for x in rows:                      # 内部排序键不出清单
            x.pop("_ts", None)
        totals = {
            "count": len(rows),
            "downloading": sum(1 for r in rows if r.get("stage") == "downloading"),
            "settling": sum(1 for r in rows if r.get("stage") == "settling"),
            "resource": sum(1 for r in rows if r.get("stage") == "resource"),
            "gone": sum(1 for r in rows if r.get("stage") == "gone"),
            "left_gb": round(sum(float(r.get("left_gb") or 0.0) for r in rows), 3),
        }
        return {"items": rows, "totals": totals}

    # ------------------------------------------------------------ 操作（行内：暂停/继续/移除）

    _OD_ACTS = ("pause", "resume", "remove")

    def _ondemand_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """点播「进行中」的行内操作：``pause`` / ``resume`` / ``remove``（只读清单之外的唯一写口）。

        ★ 15.9.0 回执统一：**恒**返回 ``{ok, hash, action, message, blocked}``（5 键齐全）。
        ``remove`` **走唯一删除闸门**（``DownloaderAdapter.delete_torrents``）：欠 H&R /
        跨站来源份 / 已认领 / 手动保留 **一律硬拦**（fail-closed，不绕过）——被拦时
        ``ok=false``、``blocked=true`` 并附原因，前端如实展示。
        删种**同时删文件**（未完成的下载无保留价值，避免又添孤儿文件）。
        """
        h = str(hash or "").strip().lower()
        act = str(action or "").strip().lower()

        def _rep(ok: bool, msg: str, *, blocked: bool = False) -> Dict[str, Any]:
            return {"ok": bool(ok), "hash": h, "action": act,
                    "message": str(msg or ""), "blocked": bool(blocked)}

        if not h:
            return _rep(False, "缺少 hash")
        if act not in self._OD_ACTS:
            return _rep(False, f"未知操作:{action}")
        pend = self._ondemand_all()
        if h not in pend:
            return _rep(False, "该种不在点播进行中（可能已完成/已移除）")
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"下载器不可用:{e}")
        if dl is None or not getattr(dl, "is_available", False):
            return _rep(False, "下载器不可用")
        if act in ("pause", "resume"):
            try:
                n, err = (dl.pause_torrents([h]) if act == "pause" else dl.resume_torrents([h]))
            except Exception as e:  # noqa: BLE001
                return _rep(False, f"{act} 失败:{e}")
            if err or not n:
                return _rep(False, f"{act} 失败:{err or '未命中'}")
            self._log(f"点播:{'暂停' if act == 'pause' else '继续'} {h[:12]}")
            return _rep(True, "已暂停" if act == "pause" else "已继续")
        # ---- remove：唯一删除闸门（不绕过）
        try:
            n, err = dl.delete_torrents(hashes=[h], delete_file=True,
                                        reason="点播移除（进行中）", source="ondemand")
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"移除失败:{e}")
        if not n:
            return _rep(False, err or "被删除闸门拦下（欠 H&R / 受保护），未移除", blocked=True)
        self._ondemand_unmark(h)
        # 17.1.0：撤单 → 历史记录标 removed（点播窗口不再展示）
        self._ondemand_history_update(h, stage="removed", removed_at=time.time())
        self._log(f"点播:移除 {h[:12]}（删种+删文件）")
        return _rep(True, "已移除（删种+删文件）")

    # ------------------------------------------------------------ API

    def ondemand_act(self, hash: str = "", action: str = "") -> Response:
        """``POST /ondemand/act`` —— 点播行内操作（pause / resume / remove）。"""
        try:
            rep = self._ondemand_act(hash=hash, action=action)
            return Response(success=bool(rep.get("ok")), message=str(rep.get("message") or ""), data=rep)
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"点播操作失败:{e}")

    def ondemand_items(self, limit: int = 50) -> Response:
        """``GET /ondemand/items`` —— 点播清单（进行中带进度 + 历史）。只读。"""
        try:
            return Response(success=True, data=self._ondemand_items(limit=limit))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"读取点播清单失败:{e}")

    def on_demand(
        self,
        query: str = "",
        task_id: str = "",
        site_ids: str = "",
        apply: bool = True,
        pick: str = "",
    ) -> Response:
        """POST /ondemand：点播（片名 / 豆瓣·TMDB·IMDB 链接）→ 直接转「资源」。

        ``pick`` = 候选的 ``enclosure``（下载链接）：**手动指定源**，不做自动优选；
        命中最近一次搜索缓存则直接下（秒回），缓存过期/不匹配就如实报错让前端重搜。
        """
        q = self._ondemand_parse(query)
        if not q["query"]:
            return Response(success=False, message="缺少 query（片名或链接）")
        task = self._get_task_config(task_id) if task_id else None
        sites = self._ondemand_sites(task, site_ids)
        if not sites:
            return Response(success=False, message="没有可搜的站点（site_ids / 任务站点均为空）")
        pick = str(pick or "").strip()
        media = None
        title = year = ""
        rows: List[Dict[str, Any]] = []
        if pick:
            # ★ 手动选源：优先吃上次搜索结果（命中则秒回，不必再搜一次）
            title = q["keyword"] or q["query"]
            rows = self._ondemand_cache_get(q["query"], sites) or []
        if not rows:
            # 未指定来源 / 手动指定但缓存失效 → 正常识别 + 搜索
            media = self._ondemand_media(q)
            if media is not None and not title:
                try:
                    title = str(getattr(media, "title", "") or "")
                    year = str(getattr(media, "year", "") or "")
                except Exception:  # noqa: BLE001
                    title, year = "", ""
            if not title:
                # ★ 识别不到（如 TMDB 不可达）**不阻断**：Master 的「主动声明」本身已是最硬信号（§1），
                #   识别只用来拼搜索关键词 → 退回原串（可直接粘种子名）。
                title = q["keyword"] or q["query"]
            keyword = title
            rows = self._ondemand_search(keyword, sites)
            if not rows and year:
                rows = self._ondemand_search(f"{title} {year}", sites)
            self._ondemand_cache_put(q["query"], sites, rows)
        auto = self._ondemand_pick(rows)
        picked: Optional[Dict[str, Any]] = None
        if pick:
            picked = next((r for r in rows if str(r.get("enclosure") or "") == pick), None)
            if picked is None:
                return Response(success=False, message="指定的候选不在本次搜索结果里（列表可能已刷新）")
        else:
            picked = auto
        out: Dict[str, Any] = {
            "resource": {"title": title, "year": year,
                         "recognized": media is not None,
                         "media_source": getattr(media, "media_source", None) and str(
                             getattr(getattr(media, "media_source"), "value", getattr(media, "media_source"))),
                         "media_id": str(getattr(media, "media_id", "") or "")},
            "sites": sites,
            "save_path": (str(getattr(task, "save_path", "") or "") if task is not None else "")
                         or self._ondemand_default_save_path(),
            "candidates": sorted(rows, key=lambda r: (
                0 if _od_is_free(r.get("downloadvolumefactor")) else 1,
                -int(r.get("seeders", 0) or 0), -float(r.get("size", 0.0) or 0.0)))[:20],
            "picked": picked,
            "auto_pick": (auto or {}).get("enclosure") or "",
            "manual": bool(pick),
        }
        if not picked:
            return Response(success=False, message="没搜到可用候选（免费优先）", data=out)
        if not apply:
            out["applied"] = False
            return Response(success=True, message="预览（apply=false，未下载）", data=out)
        res = self._ondemand_download(picked, task, title=title, year=year)
        out["applied"] = True
        out["added"] = res.get("hash") or ""
        if not res.get("ok"):
            return Response(success=False, message=str(res.get("message") or "下载失败"), data=out)
        self._ondemand_mark(str(res.get("hash") or ""), {
            "title": picked.get("title") or "",
            "media": title, "year": year,
            "site": picked.get("site_name") or "",
            "site_id": picked.get("site") or 0,
            "free": _od_is_free(picked.get("downloadvolumefactor")),
            "hit_and_run": bool(picked.get("hit_and_run")),
        })
        try:
            self._store.journal.record(
                task_id=(task.id if task is not None else ""), kind="selection",
                items=[OperationItem(
                    hash=str(res.get("hash") or ""), title=f"点播 {title} {year}".strip(),
                    reason=f"源 {picked.get('site_name') or picked.get('site')}"
                           + ("·免费" if _od_is_free(picked.get("downloadvolumefactor")) else ""),
                    source="ondemand",
                )],
            )
        except Exception:  # noqa: BLE001
            pass
        self._log(
            f"点播:「{title}」{year} → 下 {str(res.get('hash'))[:12]}"
            f"（{picked.get('site_name') or picked.get('site')}·"
            + ("免费" if _od_is_free(picked.get("downloadvolumefactor")) else "计流量") + "）"
        )
        return Response(success=True, message=f"已点播：{title}（下载中，完成后直接转「资源」）", data=out)
