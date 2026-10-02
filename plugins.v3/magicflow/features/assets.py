# -*- coding: utf-8 -*-
"""魔流 · assets —— 库内资产识别（已整理/入库，只读判定）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List


from ..crossseed import (
    search_key,
)
from ..tags import (
    is_asset_tags,
    STATE_SILENT,
    SUB_NEW,
    SUB_RESOURCE,
    is_magicflow_tag,
)


from ..common import (
    MEDIA_ASSET_TAGS,
)


class AssetsMixin:
    """assets 功能集（原 MagicFlow 方法原样搬入）。"""

    def _assets_recheck(self, *, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 给「已整理（在库）」的资源**过一遍推荐流程**（Master 2026-09-28 07:57）。

        背景：qB 里 326 个种带「已整理」标、文件确实进了影视库，但**「入库」不等于「够格」**
        —— 上次那批整理行为不一定符合我们的资源标准。这里用推荐引擎（评分/榜单/订阅）复核：

        - **够格** → 保持「静默-资源」（记 ``asset_recheck=keep``）
        - **不够格** → 降为「静默-普通」（记 ``asset_recheck=fail``）→ 此后**不再享受库内资产保护**
          （库里的硬链接文件不受影响，删的只是做种副本）

        识别不出来的资源**不动**（保持现状）。
        """
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        try:
            groups = self._tag_groups()
        except Exception:  # noqa: BLE001
            groups = None
        snap = self._tag_all_torrents() or {}
        buckets: Dict[str, List[str]] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if not is_asset_tags(tags):
                continue
            gid = ""
            if groups is not None:
                try:
                    gid = groups.group_of(hh)
                except Exception:  # noqa: BLE001
                    gid = ""
            buckets.setdefault(gid or ("h:" + hh), []).append(hh)
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "resources": len(buckets),
                               "seeds": sum(len(v) for v in buckets.values()),
                               "qualified": 0, "unqualified": 0, "unrecognized": 0,
                               "downgraded": 0, "failed": 0, "unrated": 0, "restored": 0,
                               "skip_no_ledger": 0, "skip_state": 0,
                               "samples_fail": [], "samples_keep": [], "samples_unrated": []}
        try:
            engine = self._get_recommend_engine()
        except Exception as err:  # noqa: BLE001
            rep["ok"] = False
            rep["reason"] = f"推荐引擎不可用:{err}"
            return rep
        st = self._tag_state()
        _cache: Dict[str, Any] = {}
        _limit = int(limit or 0)
        try:  # 豆瓣评分源：本轮预算（防风控，超了就回退 TMDB）
            engine.begin_round(int(cfg.get("douban_max_per_run") or 0))
        except Exception:  # noqa: BLE001
            pass
        for gid, members in buckets.items():
            t0 = snap.get(members[0])
            title = str(getattr(t0, "title", "") or "") if t0 is not None else ""
            if title not in _cache:
                try:
                    _cache[title] = (engine.evaluate(title, with_poster=False) if title
                                     else {"recognized": False})
                except Exception:  # noqa: BLE001
                    _cache[title] = {"recognized": False}
            like = _cache.get(title) or {}
            if not like.get("recognized"):
                rep["unrecognized"] += 1
                continue
            _row = {"name": title[:70], "media": like.get("title"), "year": like.get("year"),
                    "rating": like.get("rating"), "seeds": len(members), "group": gid[:36]}
            if self._recommend_worth(like, cfg):
                rep["qualified"] += 1
                if len(rep["samples_keep"]) < 12:
                    rep["samples_keep"].append(_row)
                if apply:
                    for hh in members:
                        try:
                            _was = str((st.get(hh) or {}).get("asset_recheck") or "")
                            st.put(hh, {"asset_recheck": "keep", "asset_recheck_at": time.time()})
                            # ★ 双向：上一轮被判「不达标」的，这次达标了就放回「静默-资源」
                            if _was == "fail":
                                self._silent_to_resource(hh)
                                rep["restored"] = int(rep.get("restored") or 0) + 1
                        except Exception:  # noqa: BLE001
                            continue
                continue
            rep["unqualified"] += 1
            try:
                _rtf = float(like.get("rating") or 0)
            except (TypeError, ValueError):
                _rtf = 0.0
            if _rtf <= 0:
                # ★ TMDB 无评分（没数据 ≠ 差）→ 豁免不动（Master 2026-09-28 08:33 同意）
                rep["unrated"] += 1
                if len(rep["samples_unrated"]) < 12:
                    rep["samples_unrated"].append(_row)
                continue
            if len(rep["samples_fail"]) < 15:
                rep["samples_fail"].append(_row)
            if not apply or (_limit and rep["downgraded"] >= _limit):
                continue
            for hh in members:
                try:
                    cur = st.get(hh) or {}
                    if not cur:
                        rep["skip_no_ledger"] = int(rep.get("skip_no_ledger") or 0) + 1
                        continue
                    if str(cur.get("state") or "") != STATE_SILENT:
                        rep["skip_state"] = int(rep.get("skip_state") or 0) + 1
                        continue
                    okd = self._silent_to_plain(hh)
                    st.put(hh, {"asset_recheck": "fail", "asset_recheck_at": time.time()})
                    if okd:
                        rep["downgraded"] += 1
                    else:
                        rep["failed"] += 1
                except Exception as err:  # noqa: BLE001
                    rep["failed"] += 1
                    self._log(f"资源复核:降级失败 {hh[:12]}:{err}", "warning")
        if rep["downgraded"]:
            self._log(f"资源复核:复核 {rep['resources']} 组 → 达标 {rep['qualified']} · "
                      f"不达标 {rep['unqualified']}（已转普通 {rep['downgraded']}）")
        return rep

    def _asset_untag(self, *, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 摘掉**假**「已整理 / 辅种」标（Master 2026-09-28「你整理下」）。

        现状（实测）：qB 里 326 个种子带「已整理」且**必然成对带「辅种」**；这两个标
        **不是本插件写的**（我们只读，见 ``tags.py``），抽查在影视库里**根本没有对应文件**
        → 不是可靠的入库证据，却让一批种永久豁免删除、还干扰 ``sync_tag_assets`` 的证据链。

        安全的摘法：**只摘「账本里该资源没有库记」的**（有库记的留着无害）；
        不动账本 ``asset`` 标记（保持现状保护口径），只清 qB 标签，可回滚（保留快照）。
        """
        groups = self._tag_groups()
        gdata = groups.items() or {}
        snap = self._tag_all_torrents() or {}
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "scanned": 0, "managed": 0,
                               "kept_inlib": 0, "fake": 0, "removed": 0, "failed": 0, "samples": []}
        _limit = int(limit or 0)
        _dl_cache: Dict[str, Any] = {}
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if not any(x in MEDIA_ASSET_TAGS for x in tags):
                continue
            rep["scanned"] += 1
            try:
                gid = groups.group_of(hh)
            except Exception:  # noqa: BLE001
                gid = ""
            if not gid:
                continue
            rep["managed"] += 1
            inlib = bool(((gdata.get(gid) or {}).get("library") or {}).get("in_library"))
            if inlib:
                rep["kept_inlib"] += 1
                continue
            rep["fake"] += 1
            if len(rep["samples"]) < 20:
                rep["samples"].append({"hash": hh[:12], "group": gid[:40], "tags": tags})
            if not apply:
                continue
            if _limit and rep["removed"] >= _limit:
                continue
            try:
                _dn = str((self._tag_state().get(hh) or {}).get("downloader") or "qbittorrent")
                if _dn not in _dl_cache:
                    _dl_cache[_dn] = self._get_downloader(_dn)
                _dl = _dl_cache.get(_dn)
                _fn = getattr(_dl, "replace_torrent_tags", None) if _dl is not None else None
                _new = [x for x in tags if x not in MEDIA_ASSET_TAGS]
                if callable(_fn) and _fn(hh, _new):
                    rep["removed"] += 1
                else:
                    rep["failed"] += 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"资产摘标失败 {hh[:12]}:{err}", "warning")
        return rep

    def sync_tag_assets(self, *, apply: bool = False) -> Dict[str, Any]:
        """★ 建立/刷新「库内资产」记录（真·库记）。

        证据 = 种子上 MP 写的 ``已整理`` / ``辅种`` 标签（本部署 MP 的
        downloadhistory / transferhistory / downloadfiles 三张表都是 0 行，不可依赖）。
        资产 → 账本 ``asset=True`` 且 ``origin_sub=资源``；非资产 → ``asset=False``。
        """
        store = self._tag_state()
        snap = self._tag_all_torrents()
        data = store.items()
        asset = non = changed = 0
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if hh not in data:
                continue
            is_a = is_asset_tags(tags)
            if is_a:
                asset += 1
            else:
                non += 1
            rec = data.get(hh) or {}
            if bool(rec.get("asset")) == is_a:
                continue
            # ★ 标签主权（Master 2026-09-29）：真值源已迁到魔流账本；
            #   MP 标签只是「证据输入」之一 → **只升不降**（摘掉标签后不会把库内身份抹掉）。
            if not is_a and bool(rec.get("asset")):
                continue
            changed += 1
            if apply:
                store.set_asset(hh, is_a, sub=(SUB_RESOURCE if is_a else SUB_NEW))
        return {"ok": True, "applied": bool(apply), "asset": asset, "non_asset": non,
                "changed": changed, "ledger": len(data)}

    def _resource_gid(self, title: Any, size_gb: Any, fp: Any = "") -> str:
        """资源 ID：**优先用文件特征码**（同内容 = 同资源），没有特征码时退回「关键词|体积档」。"""
        _fp = str(fp or "").strip()
        if _fp:
            return f"fp:{_fp}"
        t = search_key(title, 40).lower()
        try:
            sz = round(float(size_gb or 0.0), 1)
        except (TypeError, ValueError):
            sz = 0.0
        return f"{t}|{sz}"

    def sync_resources(self, *, apply: bool = False) -> Dict[str, Any]:
        """★ 建/刷 资源账本（Master 20:38 模型）：资源 1 : N 种子。

        - 资源有 **来源站**（真下回来的那个站）与 **H&R 账单**（靠来源站的种子挂种结清）
        - 资源有 **库记**（命中 ``已整理``/``辅种`` → 该资源已入库）
        - **只有下完的才有资源**（``progress >= 1``）；没下完的只有种子
        """
        if not bool(self._tags_cfg.get("enabled", True)):
            return {"ok": False, "reason": "标签模型未启用"}
        store = self._tag_groups()
        ledger = self._tag_state().items()
        snap = self._tag_all_torrents()
        stat: Dict[str, Any] = {"ok": True, "applied": bool(apply), "resources": 0,
                                "members": 0, "multi": 0, "in_library": 0, "hr_bills": 0}
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            rec = ledger.get(hh)
            if not rec:
                continue
            title = getattr(t, "name", "") or rec.get("title") or ""
            size = float(getattr(t, "size_gb", 0) or rec.get("size_gb") or 0.0)
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except (TypeError, ValueError):
                prog = 1.0
            _fp = str(rec.get("fp") or "").strip()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            gid = self._resource_gid(title, size, _fp)
            stat["members"] = int(stat["members"]) + 1
            if _fp:
                stat["with_fp"] = int(stat.get("with_fp") or 0) + 1
            if apply:
                store.add_member(gid, hh, site=rec.get("site") or "", size_gb=size,
                                 downloaded=prog >= 0.999, progress=prog,
                                 state=rec.get("state") or "", fp=_fp)
                if (is_asset_tags(tags) or bool(rec.get("asset"))) and store.set_library(gid, True):
                    stat["in_library"] = int(stat["in_library"]) + 1
                # ★ 资源身份（Master 2026-09-30）：入库/推荐过 → 资源；种子身份跟它走
                if is_asset_tags(tags) or bool(rec.get("asset")):
                    store.set_identity(gid, SUB_RESOURCE, by="sync")
        # 来源站 + H&R 账单：跨站来源份账本里的义务挂到「资源」上
        try:
            srcs = self._crossseed_sources().items()
        except Exception:  # noqa: BLE001
            srcs = {}
        for sib, srec in (srcs or {}).items():
            if not isinstance(srec, dict):
                continue
            _sib_fp = str((ledger.get(str(sib).lower()) or {}).get("fp") or "")
            gid = self._resource_gid(srec.get("title"), srec.get("size_gb"), _sib_fp)
            _site_group_site = str(srec.get("site_b") or srec.get("site_b_domain") or "")
            a_hash = str(srec.get("a_hash") or "").strip().lower()
            # 来源站优先级：来源份记录 → 种子标签/标题后缀 → 账本站点（账本可能被同站纳管改错）
            _site = str(srec.get("site_b") or srec.get("site_b_domain") or "")
            if not _site:
                # 兜底：按种子标签 / 标题后缀（@HDFans 之类）猜
                _live = snap.get(str(sib).lower())
                _site, _dom = self._guess_site_of_torrent(
                    getattr(_live, "tags", None), srec.get("title")
                )
                if _site and not srec.get("site_b"):
                    srec["site_b"] = _site
                    try:
                        self._crossseed_sources().put(str(sib).lower(), {"site_b": _site, "site_b_domain": _dom})
                    except Exception:  # noqa: BLE001
                        pass
                    stat["hr_site_fixed"] = int(stat.get("hr_site_fixed") or 0) + 1
            if not _site:
                _site = str((ledger.get(str(sib).lower()) or {}).get("site") or "")
            if not _site and a_hash:
                _site = str((ledger.get(a_hash) or {}).get("site") or "")
            if apply:
                store.add_member(gid, str(sib).lower(), site=_site_group_site,
                                 size_gb=float(srec.get("size_gb") or 0.0), downloaded=True,
                                 fp=str((ledger.get(str(sib).lower()) or {}).get("fp") or ""))
                if a_hash:
                    store.add_member(gid, a_hash, site=str(srec.get("site_a") or ""),
                                     size_gb=float(srec.get("size_gb") or 0.0), downloaded=True,
                                     fp=str((ledger.get(a_hash) or {}).get("fp") or ""))
                store.set_hr(gid, site=_site,
                             required_hours=float(srec.get("hours") or 0.0),
                             need_hours=float(srec.get("need_hours") or 0.0),
                             by_hash=str(sib).lower())
            stat["hr_bills"] = int(stat["hr_bills"]) + 1
        if apply:
            try:
                _pend_n = len(store.pending_library())
                _flushed = store.flush_pending_library()
                if _pend_n:
                    stat["lib_pending"] = _pend_n
                if _flushed:
                    stat["lib_pending_applied"] = _flushed
                    self._log(f"库记:补齐待办 {_flushed} 条")
            except Exception:  # noqa: BLE001
                pass
        info = store.stats()
        stat["resources"] = info.get("groups") or 0
        stat["multi"] = info.get("multi_site_groups") or 0
        try:
            stat["in_library"] = sum(
                1 for r in store.items().values() if (r.get("library") or {}).get("in_library")
            )
            stat["hr_bills"] = sum(
                1 for r in store.items().values() if (r.get("hr") or {}).get("by_hash")
            )
            stat["hr_settled"] = sum(
                1 for r in store.items().values() if (r.get("hr") or {}).get("settled")
            )
        except Exception:  # noqa: BLE001
            pass
        return stat

    def backfill_fingerprints(self, *, limit: int = 0) -> Dict[str, Any]:
        """给托管种补文件特征码（``branding``：资源按特征码归并、辅种配对直接用）。

        ``limit=0`` = 全部补齐（一次 HTTP/种，本地 qB 很快）；否则只补前 N 个。
        """
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return {"ok": False, "reason": "下载器不可用"}
        store = self._tag_state()
        ledger = store.items()
        snap = self._tag_all_torrents()
        todo = [h for h, t in snap.items()
                if str(h).lower() in ledger
                and not str((ledger.get(str(h).lower()) or {}).get("fp") or "").strip()]
        if limit and limit > 0:
            todo = todo[:int(limit)]
        got = fail = 0
        for h in todo:
            try:
                fp = downloader.get_torrent_fingerprint(str(h).lower())
            except Exception:  # noqa: BLE001
                fp = None
            if fp:
                store.put(str(h).lower(), {"fp": fp})
                got += 1
            else:
                fail += 1
        if got:
            self.sync_resources(apply=True)
        return {"ok": True, "checked": len(todo), "got": got, "failed": fail,
                "remaining": max(0, len([h for h in snap if str(h).lower() in ledger]) - len(
                    [h for h in ledger if str((ledger.get(h) or {}).get('fp') or "").strip()]) - got)}
