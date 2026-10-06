# -*- coding: utf-8 -*-
"""魔流 · debug —— 调试端点（只读观测，不产生动作）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List


from app.schemas import Response
from app.sdk.events import Event

from ..downloader_ops import (
    _kv,
)
from ..fingerprint import fingerprint, info_hash, total_size
from ..collect import api_channel as _api_channel_of
from ..crossseed import (
    pick_source,
    search_key,
    size_close,
    title_like,
)
from ..recommend import _norm
from ..dtier import TierCache


from .. import common  # noqa: F401
from ..common import (
    CROSSSEED_EXTRA_SCAN,
    SITE_FETCH_TTL,
    _MFEventType,
    _MF_EVENTS_READY,
    _mf_eventmanager,
    _torrent_entries_digest,
)


def _jsonable(value: Any, depth: int = 0) -> Any:
    """把 qB 客户端返回的自定义类型压成纯 JSON（TagList/CategoryDict 等）。"""
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, depth + 1) for v in value]
    for attr in ("to_list", "as_list"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return _jsonable(fn(), depth + 1)
            except Exception:  # noqa: BLE001
                pass
    return str(value)

class DebugMixin:
    """debug 功能集（原 MagicFlow 方法原样搬入）。"""
    _jsonable = staticmethod(_jsonable)  # 模块级函数别名

    # ------------------------------------------------------------------
    # 云盘归档(夸克冷库):API
    # ------------------------------------------------------------------
    def debug_cloud_get(self, path: str = "") -> Response:
        """诊断:`/api/fs/get` 原始响应 + stat 结果。"""
        try:
            return Response(success=True, data=self._get_cloud_engine().client().debug_get(path))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def debug_cloud_put(self, path: str = "", size: int = 1024) -> Response:
        """诊断:容器内直接 PUT 到 OpenList,返回各变体结果。"""
        try:
            return Response(success=True, data=self._get_cloud_engine().client().debug_put(path, size))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def debug_mp_search(self, keyword: str = "", sites: str = "") -> Response:
        """诊断:直接调 MoviePilot 自带搜索,看签名兼容性与免费/有源命中。

        ``GET /debug/mpsearch?keyword=xxx&sites=8,9``——**会消耗 1 PV/站**，只在排查时手动调。
        """
        kw = str(keyword or "").strip()
        if not kw:
            return Response(success=False, message="keyword 必填")
        ids: List[int] = []
        for part in str(sites or "").split(","):
            part = part.strip()
            if part.isdigit() and int(part) not in ids:
                ids.append(int(part))
        if not ids:
            return Response(success=False, message="sites 必填(逗号分隔站点 id)")
        info: Dict[str, Any] = {"keyword": kw, "sites": ids}
        try:
            from app.chain.search import SearchChain  # noqa: WPS433
            import inspect  # noqa: WPS433

            fn = getattr(SearchChain(), "search_by_title", None)
            if fn is None:
                return Response(success=False, message="当前 MP 无 SearchChain.search_by_title")
            params = list(inspect.signature(fn).parameters.keys())
            info["params"] = params
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"签名探测失败:{err}")
        if "sites" not in params:
            return Response(success=False, message=f"该版本 search_by_title 不支持 sites:{params}")
        try:
            hits = self._mp_search_title(kw, ids)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"搜索失败:{err}")
        finally:
            for i in ids:
                self._pv_spend(i, "crossseed", 1)
        info["hits"] = len(hits)
        rows: List[Dict[str, Any]] = []
        for ti in hits:
            _dv = getattr(ti, "downloadvolumefactor", None)
            try:
                dv = None if _dv is None else float(_dv)
            except Exception:  # noqa: BLE001
                dv = None
            try:
                sd = int(getattr(ti, "seeders", 0) or 0)
            except Exception:  # noqa: BLE001
                sd = 0
            rows.append({
                "title": str(getattr(ti, "title", "") or "")[:80],
                "site": getattr(ti, "site", None),
                "site_name": getattr(ti, "site_name", None),
                "dv": dv,
                "seeders": sd,
                "size": getattr(ti, "size", None),
                "enclosure": str(getattr(ti, "enclosure", "") or "")[:100],
            })
        info["free_count"] = sum(1 for r in rows if r["dv"] is not None and r["dv"] <= 0.0)
        info["free_with_seeders"] = sum(
            1 for r in rows if r["dv"] is not None and r["dv"] <= 0.0 and r["seeders"] >= 1
        )
        info["sample"] = rows[:10]
        return Response(success=True, message="OK", data=info)

    def debug_cache(self, drop: str = "", prefix: str = "", dump: str = "") -> Response:
        """诊断/维护:查看或丢弃**站点抓取缓存**(TierCache region=cands)。

        - ``GET /debug/cache``               → 列出当前热层里的 key
        - ``GET /debug/cache?drop=<key>``    → 丢弃该 key(下一轮强制重抓)
        - ``GET /debug/cache?prefix=hdfans.org|`` → 丢弃同前缀的 key
        - ``GET /debug/cache?dump=<key>``    → 看该 key 命中的条数 + 前 5 条摘要
        """
        cache = self._cache_cands()
        hot = getattr(cache, "_hot", {}) or {}
        keys = sorted(str(k) for k in list(hot.keys()))
        if drop:
            cache.delete(str(drop))
            return Response(success=True, message=f"已丢弃缓存 {drop}", data={"dropped": drop})
        if prefix:
            hit = [k for k in keys if k.startswith(str(prefix))]
            for k in hit:
                cache.delete(k)
            return Response(
                success=True, message=f"已丢弃 {len(hit)} 个同前缀缓存", data={"dropped": hit}
            )
        if dump:
            val = cache.get(str(dump), SITE_FETCH_TTL)
            items = list(val or [])
            rows: List[Dict[str, Any]] = []
            for c in items[:5]:
                rows.append({
                    "title": str(getattr(c, "title", "") or "")[:70],
                    "is_free": bool(getattr(c, "is_free", False)),
                    "dv": getattr(c, "downloadvolumefactor", None),
                    "seeders": getattr(c, "seeders", None),
                    "leechers": getattr(c, "leechers", None),
                    "size_gb": round(float(getattr(c, "size_gb", 0) or 0), 2),
                })
            _nf = sum(1 for c in items if not bool(getattr(c, "is_free", False)))
            return Response(
                success=True,
                message=f"命中 {len(items)} 条(非免费 {_nf})",
                data={"count": len(items), "non_free": _nf, "sample": rows},
            )
        return Response(success=True, message=f"热层 {len(keys)} 个 key", data={"keys": keys})

    def debug_crossseed(
        self, task: str = "", n: int = 3, add: bool = False, force_main: bool = True,
        dump: bool = False,
    ) -> Response:
        """诊断:拿某任务的候选**当成「本站非免费」**跑一遍跨站选源链路(dry-run)。

        ``GET /debug/crossseed?task=<id>&n=3[&add=true]``

        站点全免费时也能验（把免费候选假设为非免费）：
          - 每个候选在本站取 1 次 .torrent（1 PV）→ 算特征码
          - 调 MP 搜索到各候选源站 → 免费且有源的行
          - 算「同一 Release」→ 命中哪站、特征码对不对
        ``add=true`` 才真的发起他站下载（默认只报告，不动下载器）。
        """
        tid = str(task or "").strip()
        if not tid:
            return Response(success=False, message="task 必填(任务 id)")
        cfg = self._task_configs.get(tid)
        if cfg is None:
            return Response(success=False, message=f"任务不存在:{tid}")
        n = max(1, min(int(n or 3), CROSSSEED_EXTRA_SCAN))
        out: Dict[str, Any] = {"task": tid, "name": getattr(cfg, "name", ""), "add": bool(add)}
        downloader = self._get_downloader(str(getattr(cfg, "downloader", "") or "qbittorrent"))
        if downloader is None or not downloader.is_available:
            return Response(success=False, message="下载器不可用", data=out)
        cands = self._fetch_site_candidates(
            cfg, pages=1, start_page=0, force_main=bool(force_main)
        ) or []
        out["candidates"] = len(cands)
        if not cands:
            return Response(success=False, message="没抓到候选(站点不可达/封/PV 尽)", data=out)
        # 挑「上传潜力」大的：优先本站**非免费**（跨站才有意义）、下载人数多、体积从小到大
        try:
            cands = sorted(
                cands,
                key=lambda c: (
                    0 if not bool(getattr(c, "is_free", False)) else 1,
                    -int(getattr(c, "leechers", 0) or 0),
                    float(getattr(c, "size_gb", 0.0) or 0.0),
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        sid = int(getattr(cfg, "site_id", 0) or 0)
        ids = self._crossseed_site_ids(cfg)[: max(int(getattr(cfg, "crossseed_max_sites", 6) or 6), 1)]
        out["source_sites"] = ids
        items: List[Dict[str, Any]] = []
        for cand in cands[: max(n * 3, n)]:
            if len(items) >= n:
                break
            url = str(getattr(cand, "enclosure", "") or "")
            if not url:
                continue
            item: Dict[str, Any] = {
                "title": str(getattr(cand, "title", "") or "")[:90],
                "size_gb": round(float(getattr(cand, "size_gb", 0.0) or 0.0), 2),
                "leechers": int(getattr(cand, "leechers", 0) or 0),
                "is_free_on_a": bool(getattr(cand, "is_free", False)),
                "a_hash": "",
                "mp_search": None,
                "source": None,
                "note": "",
            }
            if sid and (self._pv_block_reason(sid) or not self._pv_allow(sid, "crossseed", want=1)):
                item["note"] = "本站 PV 预算不足/已封,停"
                items.append(item)
                break
            raw = None
            try:
                raw = downloader.fetch_torrent_bytes(
                    url,
                    cookie=getattr(cand, "site_cookie", None),
                    user_agent=getattr(cand, "site_ua", None),
                    referer=str(getattr(cand, "page_url", "") or "") or None,
                )
            except Exception as err:  # noqa: BLE001
                item["note"] = f"本站取种异常:{err}"
            finally:
                if sid:
                    self._pv_spend(sid, "crossseed", 1)
            if not raw:
                item["note"] = item["note"] or "本站取种失败"
                items.append(item)
                continue
            try:
                cand.raw = raw
                cand.real_hash = (info_hash(raw) or "").lower()
            except Exception:  # noqa: BLE001
                cand.real_hash = ""
            item["a_hash"] = cand.real_hash
            kw = search_key(str(getattr(cand, "title", "") or ""))
            item["keyword"] = kw
            rows = self._crossseed_search_rows(kw, ids) if (kw and ids) else []
            item["mp_search"] = len(rows)
            if not rows:
                item["note"] = item["note"] or "MP 搜索:他站无免费且有源的同名种"
                items.append(item)
                continue
            src_count: Dict[str, int] = {}
            for r in rows:
                k = str(getattr(r, "site_name", "") or getattr(r, "site", ""))
                src_count[k] = src_count.get(k, 0) + 1
            item["rows_by_site"] = src_count
            try:
                fp = fingerprint(raw)
            except Exception:  # noqa: BLE001
                fp = None
            # ★ dump=1：把「同名同体积但特征码不同」拆开看 —— 是「根目录名不同」（文件清单一致，
            #   理论上可辅种，需软链/改名）还是「真的是另一个 Release」。只对首个候选做，避免多花 PV。
            if dump and not out.get("dump"):
                out["dump"] = {"a": _torrent_entries_digest(raw), "rows": []}
                _matched = 0
                for _r in rows:
                    if _matched >= 3:
                        break
                    if not title_like(
                        str(getattr(_r, "title", "") or ""), str(getattr(cand, "title", "") or "")
                    ):
                        continue
                    if not size_close(
                        getattr(_r, "size", 0), int(getattr(cand, "size", 0) or 0)
                    ):
                        continue
                    _matched += 1
                    try:
                        _tb = self._crossseed_torrent_bytes(_r)
                    except Exception as _e:  # noqa: BLE001
                        out["dump"]["rows"].append({"err": str(_e)})
                        continue
                    if not _tb:
                        out["dump"]["rows"].append({"err": "取种失败"})
                        continue
                    _d2 = _torrent_entries_digest(_tb)
                    _d2["site"] = str(getattr(_r, "site_name", "") or "")
                    _d2["title"] = str(getattr(_r, "title", "") or "")[:90]
                    _d2["full_match"] = bool(_d2.get("fp") and _d2.get("fp") == fp)
                    _d2["inner_match"] = bool(
                        _d2.get("inner_fp") and _d2.get("inner_fp") == out["dump"]["a"].get("inner_fp")
                    )
                    out["dump"]["rows"].append(_d2)
                items.append(item)
                out["items"] = items
                out["dump"]["a"]["title"] = str(getattr(cand, "title", "") or "")[:90]
                return Response(success=True, data=out)
            self._crossseed_downloader = str(getattr(cfg, "downloader", "") or "qbittorrent")
            hit = pick_source(
                title=getattr(cand, "title", ""),
                size_bytes=int(getattr(cand, "size", 0) or 0),
                fp=fp,
                rows_provider=lambda _kw: rows,
                torrent_bytes=self._crossseed_torrent_bytes,
                log=self._log,
            )
            if not hit:
                item["note"] = item["note"] or "有免费同名种但特征码不同(非同一 Release)"
                items.append(item)
                continue
            item["source"] = {
                "site": hit.get("site"),
                "site_name": hit.get("site_name"),
                "title": str(getattr(hit.get("row"), "title", "") or "")[:90],
                "size": getattr(hit.get("row"), "size", None),
                "seeders": getattr(hit.get("row"), "seeders", None),
            }
            if add:
                try:
                    _acq = self._acquire_source(cfg, cand, downloader, allow_cross_site=True)
                    sib = _acq.get("sib_hash") or ""
                    item["started"] = sib
                    item["note"] = "已发起他站下载" if sib else (f"未发起:{_acq.get('reason') or '无免费副本'}")
                except Exception as err:  # noqa: BLE001
                    item["note"] = f"发起异常:{err}"
            else:
                item["note"] = "dry-run:命中可跨站(未发起)"
            items.append(item)
        out["items"] = items
        return Response(success=True, message="OK", data=out)

    def debug_recognize(self, name: str = "", source: str = "") -> Response:
        """诊断:识别一个种子名并返回评分/榜单/订阅命中 + 是否已在影视库(只读)。

        ``source``（可选）= 强制识别源（``douban`` / ``themoviedb`` / ``bangumi``…），
        用于多源对比：本机 MP 全局 ``RECOGNIZE_SOURCE`` = themoviedb，所以默认拿的是 TMDB 分。
        """
        try:
            info = self._get_recommend_engine().evaluate(name or "", source=str(source or ""))
            try:
                info["in_library"] = self._recommend_in_library(info)
                info["media_key"] = self._recommend_media_key(
                    {"source": info.get("media_source"), "id": info.get("media_id")}, info
                )
            except Exception:  # noqa: BLE001
                pass
            return Response(success=True, data=info)
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e))

    def debug_douban(self, name: str = "", year: str = "", keyword: str = "", count: int = 6,
                     action: str = "", flush_snapshot: bool = False) -> Response:
        """诊断:直接查豆瓣评分源（自带 frodo 客户端）。

        - ``name``+``year``：走正式查询（带缓存/限速/匹配），返回命中结果；
        - ``keyword``：原样列候选（调试匹配规则用）。
        """
        try:
            from ..douban import get_client  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"豆瓣模块不可用:{err}")
        cli = get_client(self)
        try:
            if str(action or "") == "purge_neg":
                n = cli.purge_negatives()
                return Response(success=True, message=f"已清掉 {n} 条「未命中/未开分」缓存", data=cli.stats())
            if flush_snapshot:
                cli.refresh_snapshot()
                return Response(success=True, message=f"已重读快照: {cli.snapshot_stats()['total']} 条", data=cli.stats())
            if str(action or "") == "snap_test":
                # 诊断：单独查 snapshot（不查 cache/live）
                from ..douban import _norm
                _ss = cli.snapshot_stats()
                _hit = cli._snapshot_lookup(name or "", year or "")
                return Response(success=True, message=f"snap_test: norm={repr(_norm(name))} snapshot_total={_ss['total']} hit={'Y' if _hit else 'N'}",
                                data={"norm": _norm(name or ""), "hit": _hit, "stats": _ss})
            if keyword:
                # ★ 评分源已拆为独立服务（只做「标题/年份」精确匹配），不再支持关键词模糊搜索
                return Response(success=True, message="本地评分服务不支持关键词模糊搜索（请用 name/year 精确查）",
                                data={"candidates": [], "stats": cli.stats()})
            hit = cli.lookup(name or "", year or "")
            if not hit:
                return Response(success=True, message="未命中/未开分（已进缓存，不重复查）",
                                data={"hit": None, "stats": cli.stats()})
            return Response(success=True, message=f"豆瓣 {hit.get('rating')} 分", data={"hit": hit, "stats": cli.stats()})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def debug_recommend_run(self, task_id: str = "") -> Response:
        """诊断:立即对一个任务跑一轮推荐甄别(不指定则 round-robin 一个)。"""
        try:
            if task_id:
                task = self._get_task_config(task_id)
                if not task:
                    return Response(success=False, message="任务不存在")
                self._recommend_scan_task(task)
            else:
                self.recommend_scan()
            store = getattr(self._store, "recommend", None)
            items = store.list() if store else []
            return Response(success=True, data={"total": len(items), "items": items})
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e))

    def debug_delete_gate(self, hashes: str = "") -> Response:
        """诊断:查询**删除闸门** —— 传 ``hashes``（逗号分隔）返回其中被硬保护拦截的子集。

        用途（Master 2026-10-05「删除令出一门」）：删前/排障时直接问一句
        「这几个 hash 能不能删、为什么不能」。
        """
        hs = [h.strip().lower() for h in str(hashes or "").split(",") if h.strip()]
        try:
            why = dict(self._delete_gate_detail(hs))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"闸门计算失败: {e}", data={})
        # ★ 11.12.0：把「账单直查断言」也算进硬拦（与物理删除同口径：不只是闸门推导链）
        _ba: Dict[str, str] = {}
        try:
            _bad = getattr(self, "_delete_bill_assert", None)
            if callable(_bad):
                _ba = dict(_bad(hs) or {})
        except Exception as e:  # noqa: BLE001
            _ba = {h: f"账单断言异常:{e}" for h in hs}
        for h, r in _ba.items():
            why.setdefault(h, r)
        # ★ 11.12.0：熔断状态（只读探针，不消耗窗口）
        _brk: Dict[str, Any] = {}
        try:
            _bk = getattr(self, "_delete_breaker_check", None)
            if callable(_bk):
                _, _brk = _bk([], reason="debug_probe", source="debug")
        except Exception as e:  # noqa: BLE001
            _brk = {"error": str(e)}
        blocked = sorted(why.keys())
        _bs = set(blocked)
        return Response(
            success=True,
            message=f"删除闸门: 输入 {len(hs)} 个 → 硬保护拦截 {len(blocked)} 个",
            data={
                "input": hs,
                "blocked": blocked,
                "why": why,
                "bill_assert": _ba,
                "breaker": _brk,
                "allowed": [h for h in hs if h not in _bs],
                "log_path": str(self._deletions_log_path() or ""),
            },
        )

    def debug_swap(self, task_id: str = "", apply: int = 0, force: int = 0) -> Response:
        """诊断:自动换种干跑（``apply=0`` 只出计划，不落盘；``force=1`` 忽略开关/触发/冷却，仅干跑）。"""
        _force = bool(force)
        if _force:
            apply = 0   # 强制只用于观察，绝不落盘
        try:
            ids = [task_id] if task_id else list(self._task_configs.keys())
        except Exception:  # noqa: BLE001
            ids = []
        rows: List[Dict[str, Any]] = []
        for tid in ids:
            task = self._get_task_config(tid)
            if not task:
                continue
            try:
                dl = self._get_downloader(task.downloader)
                if not dl or not dl.is_available:
                    rows.append({"task": task.name, "id": tid, "error": "下载器不可用"})
                    continue
                plan = self._swap_round(task, dl, apply=bool(apply), force=_force)
            except Exception as e:  # noqa: BLE001
                rows.append({"task": task.name, "id": tid, "error": f"{type(e).__name__}: {e}"})
                continue
            rows.append({
                "task": task.name,
                "id": tid,
                "type": getattr(task, "task_type", ""),
                "mode": getattr(task, "run_mode", ""),
                "ok": bool(plan.get("ok")),
                "reason": plan.get("reason"),
                "trigger": plan.get("trigger"),
                "triggered": bool(plan.get("triggered")),
                "active": plan.get("active"),
                "hard_n": plan.get("hard_n"),
                "soft_n": plan.get("soft_n"),
                "skipped_big": plan.get("skipped_big"),
                "resumed": plan.get("resumed"),
                "a_total": plan.get("a_total"),
                "net": plan.get("net"),
                "applied": plan.get("applied"),
                "pairs": [
                    {
                        "in": str(getattr(p["cand"], "title", ""))[:90],
                        "in_size": round(float(getattr(p["cand"], "size_gb", 0) or 0), 2),
                        "in_seeders": int(getattr(p["cand"], "seeders", 0) or 0),
                        "out": str(getattr(p["victim"], "title", ""))[:90],
                        "out_size": round(float(getattr(p["victim"], "size_gb", 0) or 0), 2),
                        "out_seeders": int(getattr(p["victim"], "seeders", 0) or 0),
                        "k": int(p.get("k") or 1),
                        "outs": [
                            {
                                "title": str(getattr(x, "title", ""))[:90],
                                "size": round(float(getattr(x, "size_gb", 0) or 0), 2),
                            }
                            for x in (p.get("victims") or ([p["victim"]] if p.get("victim") else []))
                        ],
                        "net": round(float(p["net"]), 3),
                    }
                    for p in (plan.get("pairs") or [])
                ],
            })
        return Response(success=True, data={"apply": bool(apply), "tasks": rows})

    def debug_qb_torrents(self, downloader: str = "qbittorrent") -> Response:
        """诊断:列出指定下载器的全部种子并按标签分组(只读)。"""
        try:
            dl = self._get_downloader(downloader or "qbittorrent")
            if not dl or not dl.is_available:
                return Response(success=False, message=f"下载器不可用: {downloader}")
            torrents, error = dl.get_torrents()
            if error:
                return Response(success=False, message=str(error))
            from collections import Counter
            tag_count: Counter = Counter()
            by_tag: Dict[str, List[Dict[str, Any]]] = {}
            rows: List[Dict[str, Any]] = []
            for t in (torrents or []):
                tags = getattr(t, "tags", None) or []
                if isinstance(tags, str):
                    tags = [x.strip() for x in tags.split(",") if x.strip()]
                tags = list(tags)
                state = str(getattr(t, "state", "") or "")
                item = {
                    "hash": getattr(t, "hash", ""),
                    "name": getattr(t, "title", ""),
                    "tags": tags,
                    "state": state,
                    "size_gb": round(float(getattr(t, "size_gb", 0) or 0), 2),
                    "progress": round(float(getattr(t, "progress", 0) or 0), 3),
                }
                rows.append(item)
                for tg in (tags or ["<无标签>"]):
                    tag_count[tg] += 1
                    by_tag.setdefault(tg, []).append(item)
            return Response(success=True, data={
                "total": len(rows),
                "tag_counts": dict(tag_count.most_common()),
                "by_tag": by_tag,
            })
        except Exception as err:
            return Response(success=False, message=str(err))

    def debug_emit_transfer(self, hash: str = "", path: str = "", media_id: str = "", ok: int = 1,
                            clear: int = 0, via: str = "bus") -> Response:
        """诊断：投递/直调 TransferComplete（验证事件订阅 + 库记落地）。

        - ``via=bus``（默认）经事件总线投递；``via=direct`` 直接调用处理器
        - ``clear=1`` 清掉该 hash 所属资源的库记（测试还原用）
        - ``media_id=__inspect__`` 查看订阅状态（处理器、活跃实例、收到次数）
        """
        if not _MF_EVENTS_READY or _mf_eventmanager is None or _MFEventType is None:
            return Response(success=False, message="事件总线不可用")
        _h = str(hash or "").strip().lower()
        if str(media_id or "").strip() == "__inspect__":
            try:
                _ids = [str(hid) for hid, _ in self._event_handlers(_MFEventType.TransferComplete)]
            except Exception:  # noqa: BLE001
                _ids = []
            return Response(success=True, message="ok", data=self._jsonable({
                "handlers": _ids,
                "registered": "app.plugins.magicflow.MagicFlow._on_transfer_complete" in _ids,
                "active_is_self": common._mf_active_is(self),
                "enabled": bool(getattr(self, "_enabled", False)),
                "lib_events": dict(getattr(self, "_lib_events", {}) or {}),
            }))
        if clear:
            _g0 = self._tag_groups()
            _gid0 = _g0.group_of(_h)
            _ok0 = _g0.set_library(_gid0, False) if _gid0 else False
            return Response(success=True, message="已清库记",
                            data=self._jsonable({"group_of_hash": _gid0, "cleared": _ok0}))
        from types import SimpleNamespace as _NS
        from app.runtime.events import Event as _Ev
        _p = str(path or "")
        ti = _NS(success=bool(ok), transfer_type="hardlink", need_scrape=False,
                 target_diritem=_NS(path=_p, name="", storage="local"),
                 target_item=_NS(path=_p, name="", storage="local"),
                 file_count=1, total_size=0, file_list=[], file_list_new=[])
        mi = _NS(tmdb_id=str(media_id or ""), media_id=str(media_id or ""), title="debug")
        payload = {
            "fileitem": _NS(path=_p, name="", storage="local"),
            "meta": None,
            "mediainfo": mi,
            "transferinfo": ti,
            "downloader": str(getattr(self, "_downloader_name", "") or ""),
            "download_hash": _h,
            "transfer_history_id": None,
        }
        mode = str(via or "bus").strip().lower()
        if mode == "cleanup":
            import os as _os2
            _dir = "/config/plugins/MagicFlow"
            _names = ("event_probe.log", "dispatch_trace.log", "put_trace.log", "q_trace.log")
            _out: Dict[str, Any] = {}
            for _n in _names:
                try:
                    _os2.remove(_os2.path.join(_dir, _n))
                    _out[_n] = "removed"
                except FileNotFoundError:
                    _out[_n] = "absent"
                except Exception as err:  # noqa: BLE001
                    _out[_n] = f"err:{err}"
            return Response(success=True, message="cleanup", data=self._jsonable(_out))
        report: Dict[str, Any] = {"hash": _h, "path": _p, "via": mode}
        # send_event 的第一个参数是**事件类型**（不是 Event 实例）
        if mode == "direct":
            try:
                self._on_transfer_complete(_Ev(_MFEventType.TransferComplete, payload))
                report["direct"] = "ok"
            except Exception as err:  # noqa: BLE001
                report["direct"] = f"err:{err}"
        else:
            try:
                _mf_eventmanager.send_event(_MFEventType.TransferComplete, payload)
                report["bus"] = "sent"
            except Exception as err:  # noqa: BLE001
                report["bus"] = f"err:{err}"
            time.sleep(2.5)
        _g = self._tag_groups()
        _gid = _g.group_of(_h)
        _lib = ((_g.items().get(_gid) or {}).get("library") or {}) if _gid else {}
        report.update({"group_of_hash": _gid, "library": _lib,
                       "pending_has_hash": _h in _g.pending_library()})
        return Response(success=True, message="已投递", data=self._jsonable(report))

    def debug_read_file(self, path: str = "", grep: str = "", limit: int = 200000,
                        offset: int = 0) -> Response:
        """诊断：只读读取容器内文本文件（白名单前缀），可选按行 grep。"""
        import os as _os

        p2 = str(path or "").strip()
        if not p2:
            return Response(success=False, message="缺少 path")
        if not any(p2.startswith(x) for x in ("/app/", "/config/", "/core/")):
            return Response(success=False, message="路径不在白名单(/app /config /core)")
        try:
            if not _os.path.isfile(p2):
                return Response(success=False, message="不是文件或不存在")
            size = _os.path.getsize(p2)
            cap = max(1000, min(int(limit or 200000), 500000))
            with open(p2, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(cap)
            lines = text.splitlines()
            if grep:
                kw = str(grep)
                hits = [(i + 1, ln) for i, ln in enumerate(lines) if kw in ln]
                return Response(success=True, message="ok", data=self._jsonable({
                    "path": p2, "size": size, "total_lines": len(lines),
                    "grep": kw, "hits": [{"line": i, "text": t[:400]} for i, t in hits[:60]],
                }))
            _off = max(0, int(offset or 0))
            return Response(success=True, message="ok", data=self._jsonable({
                "path": p2, "size": size, "total_lines": len(lines), "offset": _off,
                "content": "\n".join(lines[_off:_off + 400]),
            }))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取失败:{err}")

    def debug_fs(self, path: str = "", list: int = 0, path2: str = "") -> Response:
        """诊断：路径元数据（是否硬链接/在不在库）。只读。"""
        import os as _os

        def _one(pp: str) -> Dict[str, Any]:
            p2 = str(pp or "")
            if not p2:
                return {}
            info: Dict[str, Any] = {"path": p2}
            try:
                st = _os.stat(p2)
                info.update({
                    "exists": True, "is_dir": _os.path.isdir(p2),
                    "size": st.st_size, "dev": st.st_dev, "ino": st.st_ino, "nlink": st.st_nlink,
                    "mtime": st.st_mtime,
                })
                if _os.path.islink(p2):
                    info["symlink_to"] = _os.readlink(p2)
            except FileNotFoundError:
                info["exists"] = False
            except Exception as err:  # noqa: BLE001
                info["error"] = str(err)
            return info

        out: Dict[str, Any] = {"a": _one(path)}
        if path2:
            out["b"] = _one(path2)
            try:
                out["same_inode"] = (_os.stat(str(path)).st_ino == _os.stat(str(path2)).st_ino) if out["a"].get("exists") and out["b"].get("exists") else None
            except Exception:  # noqa: BLE001
                out["same_inode"] = None
        if list and out["a"].get("exists"):
            try:
                names = sorted(_os.listdir(str(path)))[: int(list)]
                out["entries"] = [{"name": n, "is_dir": _os.path.isdir(_os.path.join(str(path), n))} for n in names]
                out["total_entries"] = len(_os.listdir(str(path)))
            except Exception as err:  # noqa: BLE001
                out["list_error"] = str(err)
        return Response(success=True, message="ok", data=self._jsonable(out))

    def debug_traffic(self) -> Response:
        """诊断：未知流量审计（无魔流标签的种 + 单种限速分布）。"""
        data = self.traffic_audit()
        _u = int(data.get("unknown_uploading") or 0)
        return Response(success=bool(data.get("ok")), message=(
            f"流量审计:共 {data.get('total')} 种 / 纳管 {data.get('managed')}"
            f" / 未知 {len(data.get('unknown') or [])}（其中在上传 {_u}）"
        ), data=data)

    def debug_seed_limit(self) -> Response:
        """诊断：立即给**我们管控的**种套单种限速（按档），其他种不动；回报前后档位分布。"""
        downloader = self._get_downloader()
        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}
        if downloader is not None and callable(getattr(downloader, "upload_limit_stats", None)):
            try:
                before = downloader.upload_limit_stats()
            except Exception:  # noqa: BLE001
                before = {}
        self._apply_seed_upload_limit(force=True)
        if downloader is not None and callable(getattr(downloader, "upload_limit_stats", None)):
            try:
                after = downloader.upload_limit_stats()
            except Exception:  # noqa: BLE001
                after = {}
        return Response(success=True, message="已给我们管控的种按档套用单种限速（其他种不动）", data={
            "before": before,
            "after": after,
        })

    def debug_qb_info(self, path: str = "", hash: str = "", limit: int = 1, audit: str = "",
                      tag: str = "", filt: str = "") -> Response:
        """诊断：看看 qB 里还有哪些**可用信息**（只读）。

        ``path`` 给定时直接透传 GET 该 qB API 路径（白名单前缀 ``/api/v2/``），
        便于现场翻字段；不给则返回一份「能拿到什么」的概览。
        """
        downloader = self._get_downloader("qbittorrent")
        qbc = getattr(downloader, "_qb_client", lambda: None)() if downloader else None
        if qbc is None:
            return Response(success=False, message=" qBittorrent 客户端不可用")
        out: Dict[str, Any] = {}
        if str(audit or "").strip().lower() in ("trackers", "empty", "1", "true"):
            limit_n = int(limit or 0) or 60
            rows: List[Dict[str, Any]] = []
            try:
                for t in qbc.torrents_info() or []:
                    if str(t.get("tracker") or ""):
                        continue
                    if len(rows) >= limit_n:
                        break
                    h = str(t.get("hash") or "")
                    doms: List[str] = []
                    try:
                        for x in qbc.torrents_trackers(torrent_hash=h) or []:
                            u = str(x.get("url") or "")
                            if u.startswith("**"):
                                continue
                            m2 = re.search(r"https?://([^/]+)/", u)
                            if m2:
                                doms.append(m2.group(1).lower())
                    except Exception:  # noqa: BLE001
                        pass
                    rows.append({
                        "hash": h, "name": str(t.get("name") or "")[:60],
                        "tags": str(t.get("tags") or ""), "category": str(t.get("category") or ""),
                        "save_path": str(t.get("save_path") or ""),
                        "size_gb": round(float(t.get("size") or 0) / 1024 ** 3, 2),
                        "progress": t.get("progress"), "state": t.get("state"),
                        "magnet": str(t.get("magnet_uri") or "")[:80],
                        "announce_domains": doms,
                    })
            except Exception as err:  # noqa: BLE001
                return Response(success=False, message=f"审计失败:{err}")
            agg: Dict[str, int] = {}
            for r in rows:
                key = ",".join(sorted(set(r["announce_domains"]))) or "(也无公告)"
                agg[key] = agg.get(key, 0) + 1
            return Response(success=True, message="ok", data=self._jsonable({
                "empty_tracker_total_inspected": len(rows),
                "by_announce_domain": dict(sorted(agg.items(), key=lambda x: -x[1])[:12]),
                "samples": rows[:15],
            }))
        _pt = str(path or "").strip()
        if _pt.startswith("/api/v2/") or _pt == "introspect":
            try:
                if _pt == "introspect":
                    import inspect as _ins
                    _t = type(qbc)
                    try:
                        _sig = str(_ins.signature(_t._get))
                    except Exception as _ie:  # noqa: BLE001
                        _sig = f"sig_err:{_ie}"
                    return Response(success=True, message="ok", data=self._jsonable({
                        "mro": [c.__name__ for c in _t.__mro__],
                        "get_sig": _sig,
                        "attrs": [a for a in dir(qbc) if any(x in a.lower() for x in (
                            "session", "url", "host", "port", "request"))],
                        "version": str(getattr(qbc, "app_version", "")),
                    }))
                _p = _pt
                if _p.startswith("/api/v2/"):
                    _p = _p[len("/api/v2/"):]
                _qs: Dict[str, Any] = {}
                if "?" in _p:
                    _p, _raw = _p.split("?", 1)
                    for _kv in _raw.split("&"):
                        if "=" in _kv:
                            _k, _v = _kv.split("=", 1)
                            _qs[_k] = _v
                if hash:
                    _qs["hash"] = str(hash)
                if tag:
                    _qs["tag"] = str(tag)
                if filt:
                    _qs["filter"] = str(filt)
                _ps = _p.strip("/")
                if _ps == "torrents/info":
                    data = qbc.torrents_info(**_qs)
                else:
                    fn = getattr(qbc, "_get", None)
                    data = fn(_p) if callable(fn) else None
                if hasattr(data, "json"):
                    try:
                        data = data.json()
                    except Exception:  # noqa: BLE001
                        data = None
                if data is None:
                    return Response(success=False, message=f"qB 返回空(path={_p})")
                # qbittorrentapi 返回的是自定义容器（TorrentDictionaryList 等），
                # 直接交给 _jsonable 会被 str() 化 → 这里先规整成纯 dict/list
                if not isinstance(data, (dict, str, int, float, bool)) and hasattr(data, "__iter__"):
                    try:
                        data = [dict(x) if hasattr(x, "keys") else x for x in data]
                    except Exception:  # noqa: BLE001
                        pass
                return Response(success=True, message="ok", data=self._jsonable({
                    "path": _p, "query": _qs,
                    "count": len(data) if hasattr(data, "__len__") else None,
                    "result": data}))
            except Exception as err:  # noqa: BLE001
                return Response(success=False, message=f"qB 查询失败:{err}")
        for key, attr in (("version", "app_version"), ("webapi", "app_web_api_version")):
            fn = getattr(qbc, attr, None)
            try:
                out[key] = str(fn() if callable(fn) else fn or "")
            except Exception:  # noqa: BLE001
                pass
        try:
            info = qbc.torrents_info() or []
            out["torrents"] = len(info)
            row = None
            for t in info:
                if hash and str(t.get("hash", "")).lower() == str(hash).lower():
                    row = dict(t)
                    break
            if row is None and info:
                row = dict(info[0])
            if row:
                out["sample_fields"] = sorted(row.keys())
                out["sample"] = {k: row.get(k) for k in (
                    "hash", "name", "size", "total_size", "progress", "ratio", "uploaded", "downloaded",
                    "seeding_time", "time_active", "added_on", "completion_on", "last_activity",
                    "num_seeds", "num_complete", "num_leechs", "num_incomplete", "dl_speed", "up_speed",
                    "eta", "state", "category", "tags", "save_path", "content_path", "tracker",
                    "trackers_count", "amount_left", "availability", "priority", "up_limit", "dl_limit",
                    "ratio_limit", "seeding_time_limit", "inactive_seeding_time_limit", "auto_managed",
                )}
                try:
                    out["sample_files"] = len(qbc.torrents_files(torrent_hash=row.get("hash")) or [])
                    out["sample_trackers"] = [
                        {"url": x.get("url"), "status": x.get("status"), "msg": x.get("msg")}
                        for x in (qbc.torrents_trackers(torrent_hash=row.get("hash")) or [])[:6]
                    ]
                except Exception:  # noqa: BLE001
                    pass
        except Exception as err:  # noqa: BLE001
            out["torrents_error"] = str(err)
        # ★ 聚合视角：站点归属（按 tracker 域名）/ 目录分布 / 限速档 / 分享率限制
        try:
            rows = qbc.torrents_info() or []
            # ★ qB 的 `tracker` 字段会为空（实测 138/922），但 `torrents_trackers`
            #   能解析出站点 → audit=site 时按需逐种兜底（默认走便宜路径）
            _want_site = str(audit or "").strip().lower() == "site"
            _fix_n = 0

            def _norm_dom(url: str) -> str:
                _u = str(url or "")
                _m2 = re.search(r"https?://([^/]+)/", _u)
                _d = (_m2.group(1) if _m2 else _u).lower().split(":")[0]
                for _pre in ("tracker.", "www."):
                    if _d.startswith(_pre) and len(_d) > len(_pre) + 3:
                        _d = _d[len(_pre):]
                return _d

            _dom_name: Dict[str, str] = {}
            try:
                for _si in self._list_sites():
                    _dd = _norm_dom(_si.get("domain") or "")
                    _nm = str(_si.get("name") or "").strip()
                    if _dd and _nm:
                        _dom_name[_dd] = _nm
            except Exception:  # noqa: BLE001
                pass
            _by_site: Dict[str, int] = {}
            _by_dom: Dict[str, int] = {}
            _by_path: Dict[str, int] = {}
            _lim: Dict[str, int] = {}
            _seedlim: Dict[str, int] = {}
            _nocomplete: Dict[str, int] = {}
            for t in rows:
                _tr = str(t.get("tracker") or "")
                _m = re.search(r"https?://([^/]+)/", _tr)
                _dom = (_m.group(1) if _m else "").lower()
                if not _dom and _want_site:
                    try:
                        for _x in qbc.torrents_trackers(torrent_hash=str(t.get("hash") or "")) or []:
                            _u = str(_x.get("url") or "")
                            if _u.startswith("**"):
                                continue
                            _dom = _norm_dom(_u)
                            if _dom:
                                _fix_n += 1
                                break
                    except Exception:  # noqa: BLE001
                        pass
                _by_dom[_dom or "-"] = _by_dom.get(_dom or "-", 0) + 1
                _nd = _norm_dom(_dom) if _dom else ""
                _key = _dom_name.get(_nd, "")
                if not _key and _nd:
                    for _kd, _nm in _dom_name.items():
                        if _kd.endswith(_nd) or _nd.endswith(_kd):
                            _key = _nm
                            break
                _label = _key or _dom or "-"
                _by_site[_label] = _by_site.get(_label, 0) + 1
                _sp = str(t.get("save_path") or "-")
                _by_path[_sp] = _by_path.get(_sp, 0) + 1
                _lim[str(t.get("up_limit") or 0)] = _lim.get(str(t.get("up_limit") or 0), 0) + 1
                _seedlim[str(t.get("seeding_time_limit") or 0)] = _seedlim.get(str(t.get("seeding_time_limit") or 0), 0) + 1
                _nc = int(t.get("num_complete") or 0)
                _b = "0" if _nc <= 0 else ("1-5" if _nc <= 5 else ("6-20" if _nc <= 20 else ("21-50" if _nc <= 50 else "50+")))
                _nocomplete[_b] = _nocomplete.get(_b, 0) + 1
            out["by_tracker_domain"] = dict(sorted(_by_dom.items(), key=lambda x: -x[1])[:15])
            out["by_site_name"] = dict(sorted(_by_site.items(), key=lambda x: -x[1])[:15])
            out["site_resolved_by_trackers_list"] = _fix_n
            out["by_save_path"] = dict(sorted(_by_path.items(), key=lambda x: -x[1])[:10])
            out["by_up_limit"] = dict(sorted(_lim.items(), key=lambda x: -x[1])[:8])
            out["by_seeding_time_limit"] = dict(sorted(_seedlim.items(), key=lambda x: -x[1])[:8])
            out["num_complete_buckets"] = _nocomplete
            _st: Dict[str, int] = {}
            for t in rows:
                _s = str(t.get("state") or "-")
                _st[_s] = _st.get(_s, 0) + 1
            out["by_state"] = dict(sorted(_st.items(), key=lambda x: -x[1])[:12])
        except Exception as err:  # noqa: BLE001
            out["aggregate_error"] = str(err)
        try:
            prefs = qbc.app_preferences() or {}
            out["preferences_keys"] = sorted(prefs.keys())
            out["preferences_subset"] = {k: prefs.get(k) for k in (
                "save_path", "temp_path", "temp_path_enabled", "max_active_downloads", "max_active_torrents",
                "max_active_uploads", "max_ratio", "max_ratio_enabled", "max_seeding_time",
                "max_seeding_time_enabled", "queueing_enabled", "dht", "pex", "lsd", "upnp",
                "listen_port", "proxy_type", "announce_to_all_trackers", "announce_ip",
            )}
        except Exception:  # noqa: BLE001
            pass
        for name, fn in (("categories", qbc.torrents_categories), ("tags", qbc.torrents_tags)):
            try:
                out[name] = fn()
            except Exception:  # noqa: BLE001
                pass
        try:
            out["sync_maindata_keys"] = sorted((qbc.sync_maindata() or {}).keys())
        except Exception:  # noqa: BLE001
            pass
        return Response(success=True, message="ok", data=self._jsonable(out))

    def debug_collect(self) -> Response:
        """采集模块观测：谁在抓、抓什么、花了几 PV、命中率、worker 注册原因。"""
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        try:
            return Response(success=True, message="ok", data=self._jsonable(c.observe()))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取失败: {err}")

    def debug_np_main(self, site_id: int = 15, pages: int = 3) -> Response:
        """临时诊断：同一页在 browse 通道 / debug 通道 抓到的内容与自解析结果对比。"""
        try:
            return self._debug_np_main_inner(site_id, pages)
        except Exception as _e:  # noqa: BLE001
            import traceback as _tb

            return Response(success=False, message=f"{type(_e).__name__}: {_e}\n{_tb.format_exc()[-1200:]}")

    def _debug_np_main_inner(self, site_id: int = 15, pages: int = 3) -> Response:
        """临时诊断：同一页在 browse 通道 / debug 通道 抓到的内容与自解析结果对比。"""
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        sid = int(site_id or 0)
        site = self._get_site(sid)
        if not site:
            return Response(success=False, message="站点不存在")
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        from ..fetcher import SiteFetcher as _SF

        fetcher = _SF()
        cli = c.http.client(sid, kind="browse")
        rows = []
        for p in range(max(int(pages), 1)):
            url = f"{base}/torrents.php?incldead=1&page={p}"
            r1 = cli.get_res(url)
            t1 = str(getattr(r1, "text", "") or "")
            f2 = c.http.text(sid, url, kind="debug", ttl=0.0)
            t2 = str(getattr(f2, "text", "") or "")
            dom = getattr(site, "domain", "") or base
            p1 = fetcher._parse_np_rows(t1, dom, base, getattr(site, "cookie", None), getattr(site, "ua", None))
            p2 = fetcher._parse_np_rows(t2, dom, base, getattr(site, "cookie", None), getattr(site, "ua", None))
            rows.append({
                "page": p,
                "browse_len": len(t1), "browse_free_cls": t1.count("pro_free"),
                "browse_50cls": t1.count("pro_50pctdown"),
                "browse_parsed": len(p1), "browse_nonfree": sum(1 for x in p1 if not x.is_free),
                "debug_len": len(t2), "debug_free_cls": t2.count("pro_free"),
                "debug_50cls": t2.count("pro_50pctdown"),
                "debug_parsed": len(p2), "debug_nonfree": sum(1 for x in p2 if not x.is_free),
            })
        import inspect as _ins

        _src = ""
        try:
            _src = _ins.getsource(type(fetcher)._parse_np_rows)
        except Exception:  # noqa: BLE001
            pass
        _p2 = fetcher._parse_np_rows(t2, dom, base, getattr(site, "cookie", None), getattr(site, "ua", None))
        import sys as _sys

        _F = _sys.modules.get(type(fetcher).__module__)
        _diag = {
            "module_file": getattr(_F, "__file__", "") or type(fetcher).__module__,
            "has_50pctdown": "pro_50pctdown" in getattr(_F, "_NP_PRO_CLASSES", {}),
            "src_has_daoxiangyu": "剩余时间" in _src,
            "src_has_rule_verdict": "promo_rule_verdict" in _src,
            "rules_count": len(getattr(_F, "_SITE_FREE_RULES", {}) or {}),
            "rules_keys": list(getattr(_F, "_SITE_FREE_RULES", {}).keys())[:30],
            "rules_for_dstudio": getattr(_F, "_site_free_rules_for", lambda _d: "NOFUNC")("dstudio.me"),
            "verdict_sample": getattr(_F, "promo_rule_verdict", lambda *a, **k: "NOFUNC")(
                "dstudio.me", 2.5, "Kians Bizarre B and B 2025 S02E08 1080p NF W"
            ),
            "sample_p2": [
                {"t": x.title[:40], "dv": x.downloadvolumefactor, "vf": x.volume_factor, "free": x.is_free}
                for x in _p2[:3]
            ],
        }
        return Response(success=True, data={"site_id": sid, "diag": _diag, "rows": rows})

    def debug_candidates(self, site_id: int = 9, pages: int = 1) -> Response:
        """★ 3.44.0 诊断：API 站（馒头）候选列表（标题/大小/免费/做种人数）。"""
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        sid = int(site_id or 0)
        if not c.is_api_site(sid):
            return Response(success=False, message=f"站点 {sid} 不是 API 鉴权站（仅馒头）")
        cands = self._api_candidates_for_site(sid, pages=int(pages or 1))
        items = [
            {
                "tid": str(getattr(x, "api_tid", "") or ""),
                "title": str(getattr(x, "title", "") or "")[:80],
                "size_gb": round(float(getattr(x, "size_gb", 0.0) or 0.0), 2),
                "is_free": bool(getattr(x, "is_free", False)),
                "double_free": bool(getattr(x, "is_double_free", False)),
                "dvf": float(getattr(x, "downloadvolumefactor", 1.0) or 0.0),
                "uvf": float(getattr(x, "uploadvolumefactor", 1.0) or 0.0),
                "seeders": int(getattr(x, "seeders", 0) or 0),
                "leechers": int(getattr(x, "leechers", 0) or 0),
                "age_weeks": round(float(getattr(x, "age_weeks", 0.0) or 0.0), 2),
                "free_until": str(getattr(x, "free_until", "") or ""),
                "free_remaining_h": (
                    round(float(getattr(x, "free_remaining_sec", -1.0) or -1.0) / 3600.0, 2)
                    if float(getattr(x, "free_remaining_sec", -1.0) or -1.0) >= 0
                    else None
                ),
            }
            for x in cands[:200]
        ]
        return Response(
            success=True,
            data={
                "site_id": sid,
                "count": len(cands),
                "free_count": sum(1 for x in cands if getattr(x, "is_free", False)),
                "items": items,
            },
        )

    def debug_api(self, site_id: int = 16, action: str = "profile", keyword: str = "", tid: str = "", page: int = 1, size: int = 20, hashes: str = "") -> Response:
        """★ 3.45.0 诊断：任意 **API 通道**站点的后台 API。

        ``action`` = ``profile`` / ``list``（叶PT 公开种表）/ ``search``（馒头）/ ``detail`` /
        ``dl``（取下载凭证，只回 has_url）/ ``hash``（piecesHash 反查，逗号分隔）。
        **不打印任何密钥/凭证**。
        """
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        sid = int(site_id or 0)
        site = self._get_site(sid)
        if site is None:
            return Response(success=False, message=f"站点 {sid} 不存在")
        try:
            tname = str(_api_channel_of(site)[0] or "")
        except Exception:  # noqa: BLE001
            tname = ""
        if not c.is_api_site(sid):
            return Response(success=False, message=f"站点 {sid}({getattr(site, 'name', '')}) 不是 API 通道站（或未配置 Key）")
        view = c.site(sid)
        act = str(action or "profile").strip().lower()
        out: Dict[str, Any] = {"ok": False, "channel": tname}
        if act == "profile":
            out = dict(view.api_profile(force=True))
            out["channel"] = tname
        elif act == "list":
            r = view.api_list(page=int(page), size=int(size), promo="free", force=True)
            rows = r.get("rows") or []
            out = {
                "ok": bool(r.get("ok")),
                "channel": tname,
                "source": r.get("source"),
                "error": r.get("error"),
                "count": len(rows),
                "items": [
                    {
                        "tid": str(x.get("id") or ""),
                        "title": str(x.get("showName") or "")[:48],
                        "size_gb": round(float(x.get("fileSize") or 0) / 1073741824.0, 2),
                        "seeders": x.get("seedNum"),
                        "leechers": x.get("leechNum"),
                        "promo": x.get("downloadPromotion"),
                        "free_until": x.get("downloadPromotionEndTime"),
                        "hr": bool(x.get("hrPunishEnable")),
                        "listed": x.get("listingTime"),
                    }
                    for x in rows[:20]
                    if isinstance(x, dict)
                ],
            }
        elif act == "search":
            r = view.api_search(keyword, page=int(page), size=int(size), force=True)
            rows = r.get("rows") or []
            out = {
                "ok": bool(r.get("ok")),
                "channel": tname,
                "error": r.get("error"),
                "total": r.get("total"),
                "count": len(rows),
            }
        elif act == "dl":
            if not tid:
                return Response(success=False, message="dl 需要 tid")
            r = view.api_dl_token(tid, force=True)
            out = {"ok": bool(r.get("ok")), "channel": tname, "has_url": bool(r.get("url")), "error": r.get("error")}
        elif act == "hash":
            lst = [h for h in str(hashes or "").split(",") if h.strip()]
            r = view.api_hashes(lst, force=True)
            out = {"ok": bool(r.get("ok")), "channel": tname, "matched": len(r.get("map") or {}), "error": r.get("error")}
        else:
            return Response(success=False, message=f"未知 action: {act}")
        return Response(success=bool(out.get("ok")), data=out, message=out.get("error"))

    def debug_mteam_api(
        self,
        site_id: int = 9,
        action: str = "profile",
        keyword: str = "",
        tid: str = "",
        page: int = 1,
        size: int = 20,
    ) -> Response:
        """★ 3.43.0 诊断：馒头（API 鉴权站）API 通道。

        ``action`` = ``profile``(魔力/分享率) / ``search``(候选+促销+热度) /
        ``detail``(单种详情) / ``dl``(签名下载直链)。**不打印任何密钥**。
        """
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        sid = int(site_id or 0)
        if not c.is_api_site(sid):
            return Response(success=False, message=f"站点 {sid} 不是 API 鉴权站（仅馒头）")
        view = c.site(sid)
        act = str(action or "profile").strip().lower()
        if act == "profile":
            out = view.api_profile(force=True)
        elif act == "search":
            out = view.api_search(keyword, page=int(page), size=int(size), force=True)
        elif act == "detail":
            if not tid:
                return Response(success=False, message="detail 需要 tid")
            d = view.api_detail(tid, force=True)
            if d.get("ok"):
                raw = d.get("data") or {}
                st = raw.get("status") if isinstance(raw.get("status"), dict) else {}
                out = {
                    "ok": True,
                    "source": "api",
                    "tid": str(raw.get("id") or tid),
                    "name": raw.get("name"),
                    "size": raw.get("size"),
                    "numfiles": raw.get("numfiles"),
                    "labels": raw.get("labelsNew") or raw.get("labels"),
                    "douban": raw.get("doubanRating"),
                    "imdb": raw.get("imdbRating"),
                    "discount": st.get("discount"),
                    "discount_end": st.get("discountEndTime"),
                    "topping_level": st.get("toppingLevel"),
                    "promotion_rule": st.get("promotionRule"),
                    "seeders": st.get("seeders"),
                    "leechers": st.get("leechers"),
                    "status": st.get("status"),
                }
            else:
                out = d
        elif act == "dl":
            if not tid:
                return Response(success=False, message="dl 需要 tid")
            r = view.api_dl_token(tid, force=True)
            out = {"ok": bool(r.get("ok")), "source": "api", "has_url": bool(r.get("url")), "error": r.get("error")}
        else:
            return Response(success=False, message=f"未知 action: {act}")
        return Response(success=bool(out.get("ok")), data=out, message=out.get("error"))

    def debug_fetch_page(self, site_id: int = 0, url: str = "", limit: int = 8000) -> Response:
        """诊断:用站点 cookie 抓取**该站点域名下**的页面,返回文本片段(只读)。

        安全:必须指定 ``site_id``,且请求地址必须属于该站点域名,防止
        cookie 被带到外站(cookie 外带 / SSRF)。
        """
        if not url:
            return Response(success=False, message="缺少 url")
        if not site_id:
            return Response(success=False, message="必须指定 site_id(仅允许抓取该站点域名)")
        site = self._get_site(int(site_id))
        if not site:
            return Response(success=False, message="站点不存在")
        if not self._url_allowed_for_site(url, site):
            return Response(success=False, message="仅允许抓取该站点域名下的页面")
        # ★ 3.38.0：调试抓页也走采集模块（唯一出口 + 配额闸门 + 观测登记）
        c = self._collect_ref()
        if c is None:
            return Response(success=False, message="采集模块未就绪")
        res = c.http.text(int(site_id), url, kind="debug", ttl=0.0)
        if not res.ok:
            return Response(success=False, message=res.error or "抓取失败")
        text = res.text
        return Response(success=True, data={
            "url": url,
            "status": int(res.status or 0),
            "cached": bool(res.cached),
            "cost": int(res.cost or 0),
            "length": len(text),
            "text": text[: max(0, int(limit))],
        })

    def debug_recommend_reset(self) -> Response:
        """诊断:清空推荐甄别结果(仅测试/重置用)。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        try:
            return Response(success=True, data={"cleared": store.clear()})
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e))
