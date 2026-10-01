# -*- coding: utf-8 -*-
"""魔流 · tags —— 标签账本（状态标签 + 文件组引用计数）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


from app.schemas import Response

from ..downloader_ops import (
    TorrentInfo,
)
from ..fingerprint import fingerprint
from ..models import (
    MagicFlowTagMigratePayload,
    MagicFlowTagStatePayload,
)
from ..crossseed import (
    CROSSSEED_TAG,
)
from ..tags import (
    ASSET_TAGS,
    DUTY_STATES,
    FileGroupStore,
    KEEP_FOREIGN_TAGS,
    LEASE_TTL,
    MARK_HR,
    MARK_REUSE,
    asset_origin_sub,
    identity_of,
    is_asset_tags,
    STATE_BONUS,
    STATE_BRUSH,
    STATE_RECOMMEND,
    STATE_SILENT,
    SUB_NEW,
    SUB_PLAIN,
    SUB_RESOURCE,
    TagStateStore,
    is_magicflow_tag,
    parse_tag,
    retag,
    set_site_names as _tags_set_site_names,
    tag_for,
)


from ..common import (
    MEDIA_ASSET_HISTORY_TTL,
    MEDIA_ASSET_TAGS,
    MagicFlowTaskConfig,
    TAG_NEW_TIMEOUT,
    TAG_SNAPSHOT_INTERVAL,
    TAG_SNAPSHOT_TTL,
    TAG_SNAPSHOT_STALE_MAX,
    _has_media_asset_tag,
    _torrent_hash,
)


class TagsMixin:
    """tags 功能集（原 MagicFlow 方法原样搬入）。"""

    def _media_asset_hashes(self, torrents: List[Any], task: Optional["MagicFlowTaskConfig"] = None) -> Set[str]:
        """媒体资产价值闸门:返回「删种时永不删除」的种子 hash 集合。

        两层判据(并集):
          1. 标签命中 ``MEDIA_ASSET_TAGS``(已整理 / 辅种)--最直接;
          2. 命中 MoviePilot「下载历史」(覆盖手动下的、尚未整理入库的资源)。
        下载历史集合按任务托管种**批量**查询并短缓存(``MEDIA_ASSET_HISTORY_TTL``),
        避免每轮都打 DB。任何查询失败都只记 debug、不阻断删种流程。
        """
        hashes: Set[str] = set()
        cand: List[str] = []
        # 任务级自定义「永不删除标签」(叠加在 MEDIA_ASSET_TAGS 之上)
        extra_tags: Set[str] = set()
        if task is not None:
            _extra_raw = str(getattr(task, "delete_except_tags", "") or "")
            extra_tags = {s.strip() for s in _extra_raw.replace(",", ",").split(",") if s.strip()}
        _ledger: Dict[str, Any] = {}
        try:
            _ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            _ledger = {}
        for t in torrents or []:
            h = _torrent_hash(t)
            if not h:
                continue
            cand.append(h)
            if _has_media_asset_tag(t, extra_tags):
                # ★ 推荐流程复核「不达标」的（asset_recheck=fail）→ 不再当库内资产保护
                try:
                    if str((_ledger.get(str(h).lower()) or {}).get("asset_recheck") or "") == "fail":
                        continue
                except Exception:  # noqa: BLE001
                    pass
                hashes.add(h)
                continue
            # ★ 账本库记（魔流自己的真值源）：MP 标签被清理/被别的插件改坏也不丢库内身份
            try:
                _rec = _ledger.get(str(h).lower()) or {}
                if bool(_rec.get("asset")) and str(_rec.get("asset_recheck") or "") != "fail":
                    hashes.add(h)
            except Exception:  # noqa: BLE001
                pass
        if not cand:
            return hashes
        now = time.time()
        cache = getattr(self, "_asset_hist_cache", None)
        if cache is None:
            cache = self._asset_hist_cache = {}
        uniq = sorted(set(cand))
        key = str(len(uniq)) + ":" + ":".join(uniq[:200])
        hit = cache.get("__data__")
        if not (hit and (now - float(hit.get("ts", 0))) < MEDIA_ASSET_HISTORY_TTL and hit.get("key") == key):
            hist: Set[str] = set()
            try:
                from app.db.oper.downloadhistory import DownloadHistoryOper  # noqa: WPS433
                recs = DownloadHistoryOper().get_by_hashes(uniq) or {}
                for h in recs:
                    if h:
                        hist.add(str(h).lower())
            except Exception as err:
                self._dbg(f"下载历史查询失败(忽略): {err}")
            hit = cache["__data__"] = {"ts": time.time(), "key": key, "hist": hist}
        hashes |= set(hit.get("hist") or set())
        # 只统计「本任务托管范围内」的资产(避免把无关 hash 也算进去)
        return {h for h in hashes if h in set(uniq)}

    def _tag_snapshot_ctx(self):
        """快照缓存 + 锁（惰性初始化，两个取快照入口共用）。"""
        cache = getattr(self, "_tag_snapshot_cache", None)
        lock = getattr(self, "_tag_snapshot_lock", None)
        if cache is None or lock is None:
            cache = self._tag_snapshot_cache = {}
            lock = self._tag_snapshot_lock = threading.Lock()
        return cache, lock

    def _tag_snapshot_fetch(self, downloader_name: str = "qbittorrent") -> Dict[str, List[Any]]:
        """真正去下载器拉一次全量标签快照（单飞：同一下载器并发只拉一次），并写缓存。"""
        cache, lock = self._tag_snapshot_ctx()
        with lock:
            hit = cache.get(downloader_name)
            if hit and (time.time() - float(hit.get("ts", 0))) < TAG_SNAPSHOT_TTL:
                return hit.get("groups") or {}
            groups: Dict[str, List[Any]] = {}
            try:
                dl = self._get_downloader(downloader_name)
                if dl and dl.is_available:
                    groups, _err = dl.get_torrents_by_tag()
            except Exception as err:
                self._log(f"标签快照获取失败: {err}", "warning")
            cache[downloader_name] = {"ts": time.time(), "groups": groups}
            return groups

    def _tag_snapshot(self, downloader_name: str = "qbittorrent") -> Dict[str, List[Any]]:
        """下载器「全部种子按标签分组」快照（阻塞式：需要最新值时用）。

        **一次拉取全部种子**(qB 一次 torrents_info)供所有任务共用,替代旧的
        「每任务各调 get_torrents(tags=[tag])(= 各自全量拉取)」。
        TTL 内命中缓存;**过期就同步重拉** —— 所以刷流 / 标签审计 / 推荐这类
        「要拿它做决定/写账本」的路径走这里（宁慢一刻，不拿旧数据做决策）。
        纯展示路径请用 `_tag_snapshot_view`。
        """
        cache, _lock = self._tag_snapshot_ctx()
        hit = cache.get(downloader_name)
        if hit and (time.time() - float(hit.get("ts", 0))) < TAG_SNAPSHOT_TTL:
            return hit.get("groups") or {}
        return self._tag_snapshot_fetch(downloader_name)

    def _tag_snapshot_view(self, downloader_name: str = "qbittorrent") -> Dict[str, List[Any]]:
        """展示用快照：**stale-while-revalidate**（过期先返回旧值 + 后台单飞刷新）。

        只有「完全没有缓存」或「过期太久（> TAG_SNAPSHOT_STALE_MAX）」才阻塞。
        总览 / 任务列表这类纯展示路径走这里 —— 界面不再为 qB 全量拉取买单。
        """
        cache, _lock = self._tag_snapshot_ctx()
        hit = cache.get(downloader_name)
        if hit:
            age = time.time() - float(hit.get("ts", 0))
            if age < TAG_SNAPSHOT_TTL:
                return hit.get("groups") or {}
            if age < TAG_SNAPSHOT_STALE_MAX:
                self._spawn_tag_snapshot_refresh(downloader_name)
                return hit.get("groups") or {}
        return self._tag_snapshot_fetch(downloader_name)

    def _spawn_tag_snapshot_refresh(self, downloader_name: str = "qbittorrent") -> None:
        """后台单飞刷新标签快照（同一个下载器同时只跑一个刷新线程）。"""
        busy = getattr(self, "_tag_snapshot_refreshing", None)
        if busy is None:
            busy = self._tag_snapshot_refreshing = set()
        if downloader_name in busy:
            return
        busy.add(downloader_name)

        def _worker() -> None:
            try:
                self._tag_snapshot_fetch(downloader_name)
            except Exception as err:  # noqa: BLE001
                self._log(f"标签快照后台刷新失败: {err}", "warning")
            finally:
                busy.discard(downloader_name)

        try:
            threading.Thread(target=_worker, name=f"mf-tagsnap-{downloader_name}", daemon=True).start()
        except Exception:  # noqa: BLE001
            busy.discard(downloader_name)

    # ---------------------------------------------------------
    # 标签模型（3.13.0）
    # ---------------------------------------------------------

    def _new_tag_state(self) -> TagStateStore:
        """建状态账本对象：账本已迁到 5 表的部署走插件库，否则继续用旧 kv。"""
        try:
            from ..ledger import SeedLedgerStore, get_backend, ledger_ready
            if ledger_ready(self):
                return SeedLedgerStore(get_backend(self), log=self._log)
        except Exception as err:  # noqa: BLE001
            self._log(f"标签:5 表后端不可用，回退旧 kv:{err}", "warning")
        return TagStateStore(get_data=self.get_data, save_data=self.save_data, log=self._log)

    def _new_tag_groups(self) -> FileGroupStore:
        """建资源账本对象：同上。"""
        try:
            from ..ledger import ResourceLedgerStore, get_backend, ledger_ready
            if ledger_ready(self):
                return ResourceLedgerStore(get_backend(self), log=self._log)
        except Exception as err:  # noqa: BLE001
            self._log(f"标签:5 表后端不可用，回退旧 kv:{err}", "warning")
        return FileGroupStore(get_data=self.get_data, save_data=self.save_data, log=self._log)

    def _tag_state(self) -> TagStateStore:
        """状态账本（真值源）。★ 进程级单例，与 ``_site_rules`` 同款防热重载整表覆盖。"""
        obj = getattr(self, "_tag_state_obj", None)
        if obj is not None:
            return obj
        try:
            import sys as _sys
            import types as _types

            _key = "__magicflow_shared__"
            mod = _sys.modules.get(_key)
            if mod is None:
                mod = _types.ModuleType(_key)
                _sys.modules[_key] = mod
            # ★ 幂等补齐所有共享属性：任一入口先建了模块，都不能少了 lock
            #   （踩过：__init__ 只建 instances/counters → persistence.__new__ 里 sh.lock 直接 AttributeError，插件加载失败）
            for _attr, _factory in (("instances", dict), ("counters", dict), ("lock", threading.Lock)):
                if not hasattr(mod, _attr):
                    setattr(mod, _attr, _factory())
            obj = mod.instances.get("tag_state")
            # ★ 热重载后模块里是「新的类」，但单例还是「旧类的实例」→ 方法可能缺失。
            #   校验过类型，不匹配就重建（否则新加的方法永远 AttributeError）。
            if obj is not None and not isinstance(obj, TagStateStore):
                obj = None
            if obj is None:
                obj = self._new_tag_state()
                mod.instances["tag_state"] = obj
        except Exception:  # noqa: BLE001
            obj = self._new_tag_state()
        self._tag_state_obj = obj
        return obj

    def _tag_groups(self) -> FileGroupStore:
        """文件组账本（多站引用计数）。进程级单例，同上。"""
        obj = getattr(self, "_tag_groups_obj", None)
        if obj is not None:
            return obj
        try:
            import sys as _sys
            import types as _types

            _key = "__magicflow_shared__"
            mod = _sys.modules.get(_key)
            if mod is None:
                mod = _types.ModuleType(_key)
                _sys.modules[_key] = mod
            # ★ 幂等补齐所有共享属性：任一入口先建了模块，都不能少了 lock
            #   （踩过：__init__ 只建 instances/counters → persistence.__new__ 里 sh.lock 直接 AttributeError，插件加载失败）
            for _attr, _factory in (("instances", dict), ("counters", dict), ("lock", threading.Lock)):
                if not hasattr(mod, _attr):
                    setattr(mod, _attr, _factory())
            obj = mod.instances.get("tag_groups")
            if obj is not None and not isinstance(obj, FileGroupStore):
                obj = None
            if obj is None:
                obj = self._new_tag_groups()
                mod.instances["tag_groups"] = obj
        except Exception:  # noqa: BLE001
            obj = self._new_tag_groups()
        self._tag_groups_obj = obj
        return obj

    def _task_site_state(self, task: Any) -> Tuple[str, str]:
        """任务对应的「站点 + 状态」：刷流任务 → 刷流，其余 → 魔力。"""
        site = str(getattr(task, "site_name", "") or "").strip()
        state = STATE_BRUSH if str(getattr(task, "task_type", "bonus") or "bonus").lower() == "brush" else STATE_BONUS
        return site, state

    def _task_tag(self, task: Any) -> str:
        """任务对应的新命名标签（站点级）。"""
        site, state = self._task_site_state(task)
        return tag_for(site, state)

    def _task_tags(self, task: Any) -> List[str]:
        """任务查找用的标签集合（新命名 + 兼容旧 brush_tag）。"""
        out: List[str] = []
        try:
            nt = self._task_tag(task)
        except Exception:  # noqa: BLE001
            nt = ""
        if nt:
            out.append(nt)
        old = str(getattr(task, "brush_tag", "") or "").strip()
        if old and old not in out:
            out.append(old)
        return out

    def _tag_assign(
        self,
        task: Any,
        hashes: Any,
        *,
        sub: str = "",
        reason: str = "",
    ) -> int:
        """★ 把种子归到任务名下 = **贴职务标签** + 写账本（claim）。返回成功数。

        ★ 5.0.0：只加**职务**（刷流/魔力），**身份标签原样保留**（上班不改身份）。
        没有身份的老种/新种 → 库内资产 → 资源，其余 → 新。
        """
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        site, state = self._task_site_state(task)
        if state == STATE_SILENT:
            pass
        store = self._tag_state()
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        ok_n = 0
        skipped = 0
        _tid = str(getattr(task, "id", "") or "")
        _now = time.time()
        fn = getattr(downloader, "replace_torrent_tags", None)
        snap = self._tag_all_torrents()
        for h in hs:
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            # ★ 归属唯一：别人持有**未过期**租约的种不抢（显式「交棒/批量转移」走另一条路）
            _rec0 = store.get(hh) or {}
            _own0 = str(_rec0.get("taken_by") or "")
            if _own0 and _own0 != _tid and float(_rec0.get("lease_until") or 0) > _now:
                skipped += 1
                continue
            live = snap.get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            # ★ 身份：现网标签 → 账本 → （库内资产 ? 资源 : 新）
            _i_site, _i_sub = identity_of(cur)
            _ident = str(sub or "") or _i_sub or str(_rec0.get("sub") or "") \
                or (SUB_RESOURCE if (bool(_rec0.get("asset")) or is_asset_tags(cur)) else SUB_NEW)
            _ident = _ident or SUB_NEW
            target_site = site or _i_site
            target = tag_for(target_site, state)
            new_tags = retag(cur, site=target_site, state=state, sub=_ident) \
                if cur else [tag_for(target_site, STATE_SILENT, _ident), target]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            rec = {
                "site": target_site, "state": state, "sub": _ident,
                "taken_by": _tid,
                "task": str(getattr(task, "name", "") or ""),
                "taken_at": _now, "lease_until": _now + float(LEASE_TTL),
                "title": str(getattr(live, "title", "") or "") if live is not None else "",
                "size_gb": float(getattr(live, "size_gb", 0) or 0) if live is not None else 0.0,
            }
            try:
                store.claim(hh, str(getattr(task, "id", "") or ""), state=state, site=target_site)
                store.put(hh, rec)
            except Exception:  # noqa: BLE001
                try:
                    store.put(hh, rec)
                except Exception:  # noqa: BLE001
                    pass
            ok_n += 1
        if ok_n and reason:
            self._dbg(f"标签模型:任务「{getattr(task, 'name', '')}」接管 {ok_n} 个 → {target}（{reason}）")
        if skipped:
            self._dbg(f"标签模型:任务「{getattr(task, 'name', '')}」跳过 {skipped} 个（归别人）")
        return ok_n

    def _tag_release(self, task: Any, hashes: Any, *, reason: str = "") -> int:
        """★ 任务退下 → **只摘职务标签**（身份原样保留），返回成功数。

        ★ 5.0.0：上班前是资源/普通，下班还是资源/普通 —— 不再有「按 origin 退回」。
        """
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        store = self._tag_state()
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        tid = str(getattr(task, "id", "") or "")
        fn = getattr(downloader, "replace_torrent_tags", None)
        n = 0
        snap = self._tag_all_torrents()
        for h in hs:
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            rec = store.get(hh) or {}
            if str(rec.get("taken_by") or "") not in ("", tid):
                continue  # 被别人占着，不抢
            live = snap.get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            sub = str(rec.get("sub") or "") or _i_sub \
                or (SUB_RESOURCE if bool(rec.get("asset")) else SUB_PLAIN)
            site = str(rec.get("site") or "") or _i_site or self._torrent_site_name(cur)
            target = tag_for(site, STATE_SILENT, sub)
            new_tags = retag(cur, site=site, state=STATE_SILENT, sub=sub) if cur else [target]
            if cur and sorted(new_tags) == sorted(cur):
                done = True  # 标签已就位：只账本销账，不再打 qB
            else:
                try:
                    done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
                except Exception:  # noqa: BLE001
                    done = False
            if done:
                try:
                    store.release(hh, task_id=tid)
                except Exception as _rerr:  # noqa: BLE001
                    self._log(f"标签账本释放失败 {hh[:8]}:{_rerr}", "warning")
                n += 1
        if n and reason:
            self._dbg(f"标签模型:任务「{getattr(task, 'name', '')}」退下 {n} 个（{reason}）")
        return n

    def rehome_verdicts(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 归位：把「账本里已有分拣结论、身份却还停在『新』」的种按结论归位。

        起因（Master 2026-09-30 00:48「去上个班回来身份还变了」）：
        旧代码在占位上班时把回退目标 origin 写成默认「新」，把分拣已下的结论覆盖了。
        身份/职务分离（5.0.0）后不再会产生这种漂移 —— 本方法只用于**一次性修数据**。
        """
        store = self._tag_state()
        snap = self._tag_all_torrents() or {}
        dl = self._get_downloader()
        rep: Dict[str, Any] = {"apply": bool(apply), "scanned": 0, "pending": 0,
                               "moved": 0, "failed": 0, "items": []}
        cap = int(limit or 0)
        for h, rec in list((store.items() or {}).items()):
            hh = str(h or "").strip().lower()
            if str(rec.get("state") or "") != STATE_SILENT:
                continue
            if str(rec.get("sub") or "") != SUB_NEW:
                continue
            _reason = str(rec.get("reason") or "")
            if "分拣" not in _reason and not bool(rec.get("asset")):
                continue
            _target = SUB_RESOURCE if (bool(rec.get("asset")) or "资源" in _reason) else SUB_PLAIN
            rep["scanned"] = int(rep["scanned"]) + 1
            rep["pending"] = int(rep["pending"]) + 1
            if len(rep["items"]) < 20:
                rep["items"].append({"hash": hh[:12], "site": rec.get("site") or "",
                                     "to": _target, "reason": _reason[:40]})
            if not apply:
                continue
            if cap and int(rep["moved"]) >= cap:
                continue
            live = snap.get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            site = str(rec.get("site") or "") or self._torrent_site_name(cur)
            try:
                if cur:
                    _new = retag(cur, site=site, state=STATE_SILENT, sub=_target)
                    fn = getattr(dl, "replace_torrent_tags", None) if dl is not None else None
                    if callable(fn) and not fn(hh, _new):
                        rep["failed"] = int(rep["failed"]) + 1
                        continue
                store.put(hh, {"site": site, "state": STATE_SILENT, "sub": _target,
                               "reason": _reason + "｜归位", "rehomed_at": time.time()})
                rep["moved"] = int(rep["moved"]) + 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"归位失败 {hh[:12]}:{err}", "warning")
        if apply and rep["moved"]:
            self._log(f"魔流:身份归位:{rep['moved']} 个（原有分拣结论、身份却停在『新』）")
        return rep

    def _tag_site_names(self) -> List[str]:
        """已知站点短名（用于解析 ``魔流-<站点>-<状态>`` 里带连字符的站点）。"""
        names: List[str] = []
        try:
            for it in self._list_sites() or []:
                nm = str((it or {}).get("name") or "").strip()
                if nm and nm not in names:
                    names.append(nm)
        except Exception:  # noqa: BLE001
            pass
        for task in self._task_configs.values():
            nm = str(getattr(task, "site_name", "") or "").strip()
            if nm and nm not in names:
                names.append(nm)
        return names

    def _tag_sync_names(self) -> None:
        try:
            _tags_set_site_names(self._tag_site_names())
        except Exception:  # noqa: BLE001
            pass

    def _torrent_site_name(self, tags: Any, fallback: str = "") -> str:
        """从种子标签里找站点短名（qB 里通常带一个裸站点标签，如 ``财神``）。"""
        known = self._tag_site_names()
        tagset = [str(t).strip() for t in (tags or [])]
        for t in tagset:
            if t in known:
                return t
        for t in tagset:
            parsed = parse_tag(t)
            if parsed and parsed.get("site"):
                return parsed["site"]
        return str(fallback or "").strip()

    def _tag_all_torrents(self) -> Dict[str, Any]:
        """一次快照：hash -> TorrentInfo。

        ★ 复用插件级 ``_tag_snapshot``（带 TTL 缓存 + 单飞），避免批量改标签时
        每个 hash 都全量拉一次 qB（迁移 600+ 种子时曾是分钟级耗时主因）。
        """
        try:
            groups = self._tag_snapshot()
        except Exception:  # noqa: BLE001
            return {}
        out: Dict[str, Any] = {}
        for rows in (groups or {}).values():
            for t in rows or []:
                h = str(getattr(t, "hash", "") or "").lower()
                if h:
                    out[h] = t
        return out

    def _tag_migration_plan(self) -> Dict[str, Any]:
        """算出「老标签 → 新标签」的迁移计划（不落盘）。"""
        self._tag_sync_names()
        torrents = self._tag_all_torrents()
        task_tag_map: Dict[str, Dict[str, str]] = {}
        for task in self._task_configs.values():
            tag = str(getattr(task, "brush_tag", "") or "").strip()
            if not tag:
                continue
            tier = "brush" if str(getattr(task, "task_type", "bonus") or "bonus").lower() == "brush" else "bonus"
            task_tag_map[tag] = {
                "site": str(getattr(task, "site_name", "") or "").strip(),
                "state": STATE_BRUSH if tier == "brush" else STATE_BONUS,
                "task": str(getattr(task, "name", "") or ""),
            }
        rec_tag = str(self._recommend_cfg.get("tag", "魔流-推荐") or "魔流-推荐")
        # ★ 特殊标签不动：跨站来源份沿用 CROSSSEED_TAG（H&R 保护账本认它），推荐沿用 recommend 的 tag。
        try:
            cs_hashes = set(self._crossseed_source_hashes() or set())
        except Exception:  # noqa: BLE001
            cs_hashes = set()
        plan: List[Dict[str, Any]] = []
        for h, t in torrents.items():
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            mf_tags = [x for x in tags if is_magicflow_tag(x)]
            if not mf_tags:
                continue
            site = self._torrent_site_name(tags)
            state, sub, src = "", "", ""
            for x in mf_tags:
                hit = task_tag_map.get(x)
                if hit:
                    state, src = hit["state"], f"任务「{hit['task']}」"
                    site = site or hit["site"]
                    break
            if h in cs_hashes:
                state, sub, src = STATE_SILENT, SUB_RESOURCE, "跨站来源份"
                remove = [x for x in mf_tags if x != CROSSSEED_TAG]
                if CROSSSEED_TAG in tags and not remove:
                    continue
                plan.append({
                    "hash": h,
                    "title": str(getattr(t, "title", "") or "")[:120],
                    "site": site,
                    "state": state,
                    "sub": sub,
                    "source": src,
                    "special": "crossseed",
                    "remove": remove,
                    "add": CROSSSEED_TAG,
                    "tags": tags,
                })
                continue
            keep_extra = [t for t in (rec_tag, MARK_REUSE, MARK_HR) if t in mf_tags]
            if not state and CROSSSEED_TAG in mf_tags:
                state, sub, src = STATE_SILENT, SUB_RESOURCE, "跨站来源份"
            if not state:
                # ★ 5.0.0：身份 + 职务两标签并存 → **职务优先**（否则会把在岗的种当成静默）
                parsed = None
                for x in mf_tags:
                    _pp = parse_tag(x)
                    if _pp and _pp.get("state") in DUTY_STATES:
                        parsed = _pp
                        break
                if parsed is None:
                    for x in mf_tags:
                        parsed = parse_tag(x)
                        if parsed and parsed.get("state"):
                            break
                if parsed and parsed.get("state"):
                    state, sub, src = parsed["state"], parsed.get("sub", ""), "已是新标签"
                else:
                    state, sub, src = STATE_BONUS, "", "老魔力标签"
            if not site:
                state, src = (state, src)
            new_tag = tag_for(site, state, sub)
            old_new = [x for x in mf_tags if x != new_tag and x not in keep_extra]
            if not old_new and new_tag in tags:
                continue
            plan.append({
                "hash": h,
                "title": str(getattr(t, "title", "") or "")[:120],
                "site": site,
                "state": state,
                "sub": sub,
                "source": src,
                "remove": old_new,
                "add": new_tag,
                "tags": tags,
            })
        by_state: Dict[str, int] = {}
        for p in plan:
            key = p["state"] + (f"-{p['sub']}" if p["sub"] else "")
            by_state[key] = by_state.get(key, 0) + 1
        return {"total": len(plan), "by_state": by_state, "samples": plan[:20], "plan": plan}

    def _tag_migrate_apply(self, plan: Any, *, limit: int = 0) -> Dict[str, Any]:
        """执行迁移：改标签 + 写状态账本。"""
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return {"ok": False, "error": "下载器不可用"}
        store = self._tag_state()
        done = 0
        failed = 0
        for item in plan or []:
            if limit and done >= limit:
                break
            h = str(item.get("hash") or "").lower()
            if not h:
                continue
            tags = [str(x).strip() for x in (item.get("tags") or [])]
            new_tags = [x for x in tags if x not in set(item.get("remove") or [])]
            add = str(item.get("add") or "")
            if add and add not in new_tags:
                new_tags.append(add)
            try:
                fn = getattr(downloader, "replace_torrent_tags", None)
                ok = fn(h, new_tags) if callable(fn) else downloader.set_torrent_tags(h, new_tags)
                if not ok:
                    failed += 1
                    continue
            except Exception:  # noqa: BLE001
                failed += 1
                continue
            _tags_now = [str(x).strip() for x in (item.get("tags") or [])]
            _is_asset = is_asset_tags(_tags_now)
            store.put(h, {
                "site": item.get("site") or "",
                "state": item.get("state") or STATE_SILENT,
                "sub": item.get("sub") or asset_origin_sub(_tags_now),
                "asset": _is_asset,
                "title": item.get("title") or "",
                "migrated": True,
            })
            done += 1
        return {"ok": True, "migrated": done, "failed": failed}

    # ---------------------------------------------------------
    # 魔流化（Master 2026-09-29 23:07）：存量「非魔流」种一次性归入魔流标签
    #   规则：全部走**推荐标准** → 魔流-<站点>-静默-<资源|普通>；旧站点/刷流标签摘掉。
    #   「推荐推的是资源，不是种」→ 同一**资源**（文件组）一起判定、一起打标。
    # ---------------------------------------------------------

    def _mp_source_promote(self) -> Dict[str, Any]:
        """★ MP 来源的种若被归成「普通」→ 提为「资源」。

        Master 2026-09-29 23:55：订阅里 MP 自己下的片子，不知它给打了什么标，
        这种**直接放进资源**。证据：种子带 `MOVIEPILOT`（MP 给自家添加的种打的标记）。
        """
        try:
            _dl = self._get_downloader()
            idx = _dl.get_all_torrents_index() if _dl is not None else {}
        except Exception:  # noqa: BLE001
            idx = {}
        st = self._tag_state()
        rep: Dict[str, Any] = {"ok": True, "candidates": 0, "promoted": 0, "failed": 0, "samples": []}
        for h, t in (idx or {}).items():
            hh = str(h or "").lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if "MOVIEPILOT" not in tags:
                continue
            _p = None
            for x in tags:
                _q = parse_tag(x)
                if _q and _q.get("sub") == SUB_PLAIN:
                    _p = _q
                    break
            if not _p:
                continue
            rep["candidates"] = int(rep["candidates"]) + 1
            _site = str(_p.get("site") or "")
            _new = retag(tags, site=_site, state=STATE_SILENT, sub=SUB_RESOURCE, keep_foreign=False)
            if "MOVIEPILOT" not in _new:
                _new.append("MOVIEPILOT")
            if len(rep["samples"]) < 10:
                rep["samples"].append({"hash": hh[:12], "site": _site, "old": tags, "new": _new})
            try:
                _fn = getattr(_dl, "replace_torrent_tags", None)
                if not (callable(_fn) and _fn(hh, _new)):
                    rep["failed"] = int(rep["failed"]) + 1
                    continue
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"MP来源提资源失败 {hh[:12]}:{err}", "warning")
                continue
            rep["promoted"] = int(rep["promoted"]) + 1
            try:
                rec = dict(st.get(hh) or {})
                rec.update({"site": _site, "state": STATE_SILENT, "sub": SUB_RESOURCE,
                            "reason": "MP 来源(订阅/自下) → 直接资源",
                            "mp_promoted_at": time.time()})
                st.put(hh, rec)
            except Exception as err:  # noqa: BLE001
                self._dbg(f"MP来源提资源:账本写入失败 {hh[:12]}:{err}")
        return rep

    def traffic_audit(self) -> Dict[str, Any]:
        """★ 未知流量审计（Master 2026-09-30 00:01「不能有未知流量」）。

        未知 = 在下载器里、且**没有魔流标签**的种 —— 即不由我们管控的挂种/刷流行为。
        另回报单种上传限速分布（单种不限流后应为「不限」）。
        """
        out: Dict[str, Any] = {"ok": True, "total": 0, "managed": 0, "unknown": [],
                              "uploading": 0, "unknown_uploading": 0, "upload_limit": {}}
        try:
            _dl = self._get_downloader()
        except Exception as err:  # noqa: BLE001
            out["ok"], out["error"] = False, str(err)
            return out
        if _dl is None:
            out["ok"], out["error"] = False, "下载器不可用"
            return out
        _stats = getattr(_dl, "upload_limit_stats", None)
        if callable(_stats):
            try:
                out["upload_limit"] = _stats()
            except Exception:  # noqa: BLE001
                pass
        try:
            idx = _dl.get_all_torrents_index() or {}
        except Exception as err:  # noqa: BLE001
            out["ok"], out["error"] = False, str(err)
            return out
        for h, t in idx.items():
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            hh = str(h or "").lower()
            up = float(getattr(t, "upload_speed", 0.0) or 0.0) / 1048576.0
            out["total"] = int(out["total"]) + 1
            if up > 0:
                out["uploading"] = int(out["uploading"]) + 1
            if any(is_magicflow_tag(x) for x in tags):
                out["managed"] = int(out["managed"]) + 1
                continue
            if up > 0:
                out["unknown_uploading"] = int(out["unknown_uploading"]) + 1
            if len(out["unknown"]) < 50:
                out["unknown"].append({
                    "hash": hh[:12],
                    "name": str(getattr(t, "title", "") or "")[:60],
                    "tags": tags,
                    "up_mbps": round(up, 3),
                    "state": str(getattr(t, "state", "") or ""),
                })
        return out

    def _tag_hygiene_round(self, *, force: bool = False, ttl: float = 0.0) -> Dict[str, Any]:
        """★ 标签主权巡检（Master 2026-09-29 23:41 / 23:55）。

        一轮做完三件事（幂等、可重复跑）：
          1. **摘其他标签**：别的插件/人私下挂的种、历史遗留标签 → 只留 `魔流-*`
             （+ MP 自己的 `MOVIEPILOT`），带 `已整理/辅种` 的**先记账本**再摘。
          2. **归流**：没魔流标签 / 没站点的种 → 按推荐标准归入 `魔流-<站>-静默-<资源|普通>`
             （MP 来源直接进资源）。
          3. **提资源**：已带魔流标签但被归成「普通」的 MP 来源种 → 提为「资源」。

        频控：默认 900s 一次（Check 每轮都调，靠这里节流）。
        """
        now = time.time()
        _ttl = float(ttl or getattr(self, "_tag_hygiene_ttl", 0) or 300.0)
        _last = float(getattr(self, "_tag_hygiene_last", 0) or 0)
        if not force and (now - _last) < _ttl:
            return {"ok": True, "skipped": True, "age": round(now - _last, 1)}
        self._tag_hygiene_last = now
        out: Dict[str, Any] = {"ok": True, "cleaned": 0, "adopted": 0, "promoted": 0,
                              "assets": 0, "failed": 0, "unknown_uploading": 0}
        try:  # ⓿ 未知流量审计（没魔流标签的种 = 不由我们管控的行为）
            _ta = self.traffic_audit()
            out["total"] = int(_ta.get("total") or 0)
            out["managed"] = int(_ta.get("managed") or 0)
            out["unknown"] = int(len(_ta.get("unknown") or []))
            out["unknown_uploading"] = int(_ta.get("unknown_uploading") or 0)
            if out["unknown_uploading"]:
                self._log(f"标签巡检:⚠️ 发现 {out['unknown_uploading']} 个「未知流量」种"
                          f"（无魔流标签且在上传）→ 立即归流", "warning")
        except Exception as err:  # noqa: BLE001
            self._dbg(f"标签巡检:未知流量审计异常: {err}")
        try:  # ① 摘其他标签
            cp = self._tag_clean_plan(limit=0)
            if cp.get("total"):
                r = self._tag_clean_apply(cp.get("plan") or [], limit=0)
                out["cleaned"] = int(r.get("cleaned") or 0)
                out["assets"] = int(r.get("asset_adopted") or 0)
                out["failed"] = int(out["failed"]) + int(r.get("failed") or 0)
        except Exception as err:  # noqa: BLE001
            self._log(f"魔流:标签巡检(清理)异常: {err}", "warning")
        try:  # ② 归流（新出现的种一律进管控）
            mp = self._magicize_plan(limit=0)
            if mp.get("total"):
                r2 = self._magicize_apply(mp.get("plan") or [], limit=0)
                out["adopted"] = int(r2.get("magicized") or 0)
                out["failed"] = int(out["failed"]) + int(r2.get("failed") or 0)
        except Exception as err:  # noqa: BLE001
            self._log(f"魔流:标签巡检(归流)异常: {err}", "warning")
        try:  # ③ MP 来源提「资源」
            pr = self._mp_source_promote()
            out["promoted"] = int(pr.get("promoted") or 0)
            out["failed"] = int(out["failed"]) + int(pr.get("failed") or 0)
        except Exception as err:  # noqa: BLE001
            self._log(f"魔流:标签巡检(提资源)异常: {err}", "warning")
        if out["cleaned"] or out["adopted"] or out["promoted"] or out["unknown_uploading"]:
            self._log(f"魔流:标签巡检 → 摘其他标签 {out['cleaned']} · 新纳管 {out['adopted']}"
                      f" · MP 来源提资源 {out['promoted']} · 未知流量 {out['unknown_uploading']}"
                      f"（失败 {out['failed']}）")
        return out

    def _tag_clean_plan(self, *, limit: int = 0) -> Dict[str, Any]:
        """算「摘掉所有非魔流标签」的清单（★ 标签主权）。

        Master 2026-09-29 23:41「减少其他 tag，确保所有种子的行为都在我们管控下」。
        规则：
          - 保留所有 ``魔流-*`` 标签
          - 保留 ``KEEP_FOREIGN_TAGS``（MP 自己的标记，属我方系统）
          - 其余一律摘（``已整理``/``辅种``/裸站点名/``刷流-x``/``魔力-x``/``静默-x``/其它插件塞的）
          - **先记账本再摘**：带 ``已整理/辅种`` 的种先写魔流账本 ``asset=True``，
            否则摘完就丢了库内身份（保护靠账本，不再靠 MP 标签）
        """
        snap = self._tag_all_torrents()
        try:  # 标签快照不含无标签种 → 合并全量索引（★ 实时优先：新鲜数据覆盖缓存快照）
            _dl0 = self._get_downloader()
            _allidx = _dl0.get_all_torrents_index() if _dl0 is not None else {}
            if _allidx:
                snap = {**snap, **_allidx}
        except Exception:  # noqa: BLE001
            pass
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        cap = int(limit or 0)
        items: List[Dict[str, Any]] = []
        assets = 0
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            foreign = [x for x in tags if x and (not is_magicflow_tag(x)) and x not in KEEP_FOREIGN_TAGS]
            _ws = [x for x in tags if x and x != x.strip()]   # ★ 带前后空白的标签（写坏的名字）→ 重写到干净名
            if not foreign and not _ws:
                continue
            _is_asset = any(str(x).strip() in ASSET_TAGS for x in foreign)
            if _is_asset:
                assets += 1
            if cap and len(items) >= cap:
                continue
            _drop = foreign + [x for x in _ws if x not in foreign]
            items.append({
                "hash": hh, "remove": _drop,
                "tags": tags,
                "new_tags": [x for x in tags if x not in _drop] + [x.strip() for x in _ws if x.strip()],
                "asset": _is_asset, "in_ledger": hh in ledger,
            })
        return {
            "ok": True, "scanned": len(snap or {}), "total": len(items), "assets": assets,
            "moved": sum(1 for i in items if i["in_ledger"]),
            "samples": [{k: i.get(k) for k in ("hash", "remove", "new_tags")} for i in items[:20]],
            "plan": items,
        }

    def _tag_clean_apply(self, plan: Any, *, limit: int = 0) -> Dict[str, Any]:
        """执行标签清理：先记账本（资产）→ 再写回只留魔流标签。"""
        st = self._tag_state()
        rep: Dict[str, Any] = {"ok": True, "cleaned": 0, "failed": 0, "asset_adopted": 0, "skipped": 0}
        cap = int(limit or 0)
        _dl_cache: Dict[str, Any] = {}
        for it in (plan or []):
            hh = str(it.get("hash") or "").strip().lower()
            if not hh:
                continue
            if cap and int(rep["cleaned"]) >= cap:
                rep["skipped"] = int(rep["skipped"]) + 1
                continue
            if it.get("asset"):  # ★ 先保身份：记进魔流账本
                try:
                    st.set_asset(hh, True, sub=SUB_RESOURCE)
                    rep["asset_adopted"] = int(rep["asset_adopted"]) + 1
                except Exception:  # noqa: BLE001
                    pass
            try:
                _dn = str((st.get(hh) or {}).get("downloader") or "qbittorrent")
                _dl = _dl_cache.get(_dn)
                if _dn not in _dl_cache:
                    _dl = _dl_cache[_dn] = self._get_downloader(_dn)
                _fn = getattr(_dl, "replace_torrent_tags", None) if _dl is not None else None
                if callable(_fn) and _fn(hh, list(it.get("new_tags") or [])):
                    rep["cleaned"] = int(rep["cleaned"]) + 1
                else:
                    rep["failed"] = int(rep["failed"]) + 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"标签清理失败 {hh[:12]}:{err}", "warning")
        return rep

    def _magicize_site(self, torrent: Any, tags: Any, title: Any = "", hash_string: str = "") -> Tuple[str, str]:
        """站点判定：标签/标题后缀 → 老式 ``刷流-x/魔力-x/静默-x`` 标签 → 种子 tracker 域名。"""
        site, dom = self._guess_site_of_torrent(tags, title)
        if site:
            return site, dom
        # ② 老式带前缀标签（``刷流-咖啡`` 这类）
        try:
            known = self._tag_site_names() or []
        except Exception:  # noqa: BLE001
            known = []
        for x in [str(t).strip() for t in (tags or [])]:
            for pfx in ("刷流-", "魔力-", "静默-"):
                if x.startswith(pfx):
                    cand = x[len(pfx):].strip()
                    if cand and cand in known:
                        try:
                            return cand, str(self._site_domain_by_name(cand) or "")
                        except Exception:  # noqa: BLE001
                            return cand, ""
        trk = str(getattr(torrent, "tracker", "") or "") if torrent is not None else ""
        host = ""
        try:
            from urllib.parse import urlparse
            host = str(urlparse(trk).hostname or "").lower()
        except Exception:  # noqa: BLE001
            host = ""
        if not host:
            _m = re.search(r"([a-z0-9.-]+\.[a-z]{2,})", trk.lower()) if trk else None
            host = _m.group(1) if _m else ""
        if not host and hash_string:  # ③ 逐 hash 兜底（qB tracker 字段常为空）
            try:
                host = str(self._get_downloader().tracker_domain(hash_string) or "")
            except Exception:  # noqa: BLE001
                host = ""
        if host:
            try:
                for it in self._list_sites() or []:
                    d = str((it or {}).get("domain") or "").lower().strip()
                    nm = str((it or {}).get("name") or "")
                    if d and nm and (d.split(":")[0] in host or host in d):
                        return nm, d
            except Exception:  # noqa: BLE001
                pass
        # ④ 实在认不出来：用 tracker 域名当站点名（比空好，且不丢信息）
        return (host, host) if host else ("", "")

    def _magicize_scope(self, snap: Dict[str, Any], *, site_filter: str = "") -> Dict[str, List[str]]:
        """圈出「非魔流」种：一个魔流标签都没有；按资源组归桶。

        另含「無站点名的老魔流静默标签」（如 ``魔流-静默-普通``）—— 靠 tracker 补齐站点。
        """
        try:
            files = self._tag_groups()
        except Exception:  # noqa: BLE001
            files = None
        _site_filter = str(site_filter or "").strip()
        buckets: Dict[str, List[str]] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            _mf = [x for x in tags if is_magicflow_tag(x)]
            if _mf:
                _parsed = [parse_tag(x) for x in _mf]
                _hassite = any(p and p.get("site") for p in _parsed)
                _sitelss = any(
                    p and not p.get("site") and p.get("state") == STATE_SILENT and p.get("sub")
                    for p in _parsed
                )
                if _hassite or not _sitelss:
                    continue  # 已是魔流（且站点已定/不是静默状态标签），不动
            if _site_filter:
                _site, _dom = self._magicize_site(t, tags, getattr(t, "title", None) or getattr(t, "name", ""), hh)
                if _site != _site_filter:
                    continue
            gid = ""
            if files is not None:
                try:
                    gid = files.group_of(hh)
                except Exception:  # noqa: BLE001
                    gid = ""
            buckets.setdefault(str(gid) or ("h:" + hh), []).append(hh)
        return buckets

    def _magicize_plan(self, *, limit: int = 0, budget: float = 900.0, site_filter: str = "") -> Dict[str, Any]:
        """算出「非魔流种 → 魔流标签」的魔流化计划（不落盘）。

        判定标准（与静默池分拣/资源复核同一套）：
          - 识别到 + 够格（评分>门槛 或 榜单/订阅）→ ``静默-资源``
          - 识别到 + 有评分 + 不够格 → ``静默-普通``
          - 识别不到 / 无评分（没数据 ≠ 差）→ ``静默-普通``（记录原因，不计入「不够格」）
        同资源（文件组）内已有魔流成员 → 直接沿用该成员的判定（不重复评估）。
        """
        self._tag_sync_names()
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        snap = self._tag_all_torrents()
        # ★ 标签快照**不含无标签种子**（qB 按 tag 分组时丢弃）—— 魔流化要盖全量，
        #   所以合并一次「全部种子索引」（全量拉取，仅在魔流化这种批量场景用）。
        #   ★ 实时优先：新鲜数据覆盖可能过期的标签快照（否则同一批会反复重做）。
        try:
            _dl0 = self._get_downloader()
            _allidx = _dl0.get_all_torrents_index() if _dl0 is not None else {}
            if _allidx:
                snap = {**snap, **_allidx}
        except Exception:  # noqa: BLE001
            pass
        try:
            engine = self._get_recommend_engine()
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "reason": f"推荐引擎不可用:{err}", "plan": [], "total": 0}
        try:  # 豆瓣预算（防风控）
            engine.begin_round(int(cfg.get("douban_max_per_run") or 0))
        except Exception:  # noqa: BLE001
            pass
        buckets = self._magicize_scope(snap, site_filter=site_filter)
        st = self._tag_state()
        plan: List[Dict[str, Any]] = []
        stats: Dict[str, Any] = {
            "ok": True, "groups": len(buckets),
            "torrents": sum(len(v) for v in buckets.values()),
            "resource": 0, "plain": 0, "recognized": 0, "unrecognized": 0,
            "unrated": 0, "asset_keep": 0, "asset_fail": 0, "reused": 0, "mp_source": 0,
            "limited": False, "sites": {}, "samples": [],
        }
        # ★ MP 自己下的（订阅/手动/别的 MP 插件经 MP 添加）→ MP 会给种子打 `MOVIEPILOT`
        #   （`app/runtime/config.py` 的 TORRENT_TAG），另用 MP 下载历史兜底。
        #   Master 2026-09-29 23:55：「订阅他自己下的电影…这种我们得直接放进资源」。
        _mp_hist: Set[str] = set()
        try:
            from app.db.oper.downloadhistory import DownloadHistoryOper  # noqa: WPS433
            _recs = DownloadHistoryOper().get_by_hashes(list(snap.keys())) or {}
            _mp_hist = {str(k).lower() for k in (_recs or {}) if k}
        except Exception as err:  # noqa: BLE001
            self._dbg(f"MP 下载历史查询失败(忽略): {err}")
        cap = int(limit or 0)
        _deadline = time.time() + float(budget or 0)
        _used = 0
        for gid, members in buckets.items():
            if budget and time.time() > _deadline:
                stats["limited"] = True
                break
            if cap and _used >= cap:
                stats["limited"] = True
                break
            _used += 1
            rep_h = members[0]
            rep_t = snap.get(rep_h)
            title = str(getattr(rep_t, "title", "") or getattr(rep_t, "name", "") or "")
            site, _dom = self._magicize_site(
                rep_t, getattr(rep_t, "tags", None), title, rep_h
            )
            # ---- 同资源已有魔流成员 → 沿用它的状态（资源级判定，不重复评估）
            sub = ""
            verdict = ""
            rating = None
            reason = ""
            try:
                _allsame = self._tag_all_torrents()
            except Exception:  # noqa: BLE001
                _allsame = snap
            if not str(gid).startswith("h:"):
                try:
                    _gs = set(str(x).lower() for x in (self._tag_groups().items().get(gid, {}) or {}).get("members", {}))
                except Exception:  # noqa: BLE001
                    _gs = set()
                for _mh in _gs:
                    _mt = _allsame.get(_mh)
                    if _mt is None:
                        continue
                    for _x in (getattr(_mt, "tags", None) or []):
                        _p = parse_tag(str(_x))
                        if _p and _p.get("sub") in (SUB_RESOURCE, SUB_PLAIN):
                            sub, verdict, reason = _p["sub"], "沿用", f"同资源 {str(_mh)[:8]}"
                            site = site or _p.get("site") or ""
                            break
                    if sub:
                        break
            # ---- 资源级评估（识别 + 评分）
            _rep_tags = [str(x).strip() for x in (getattr(rep_t, "tags", None) or [])]
            _mp_src = ("MOVIEPILOT" in _rep_tags) or (rep_h in _mp_hist)
            if not sub and _mp_src:
                # MP 来源（订阅/自己下的）→ 直接拿「资源」，不走评分（Master 2026-09-29 23:55）
                stats["mp_source"] = int(stats.get("mp_source") or 0) + 1
                sub, verdict, reason = SUB_RESOURCE, "资源", "MP 来源(订阅/自下)"
            if not sub:
                like: Dict[str, Any] = {"recognized": False}
                if title:
                    try:
                        like = engine.evaluate(title, with_poster=False)
                    except Exception:  # noqa: BLE001
                        like = {"recognized": False}
                rating = like.get("rating")
                if not like.get("recognized"):
                    stats["unrecognized"] += 1
                    sub, verdict, reason = SUB_PLAIN, "普通", "未识别"
                else:
                    stats["recognized"] += 1
                    try:
                        _rt = float(rating or 0)
                    except (TypeError, ValueError):
                        _rt = 0.0
                    if self._recommend_worth(like, cfg):
                        sub, verdict = SUB_RESOURCE, "资源"
                        reason = "评分 %.1f" % _rt + ("·在榜" if like.get("in_chart") else "") + ("·订阅" if like.get("in_subscribe") else "")
                    elif _rt <= 0:
                        stats["unrated"] += 1
                        sub, verdict, reason = SUB_PLAIN, "普通", "无评分(没数据)"
                    else:
                        sub, verdict, reason = SUB_PLAIN, "普通", "评分 %.1f 未达标" % _rt
            else:
                stats["reused"] += 1
            if not site:
                site = ""
            add = tag_for(site, STATE_SILENT, sub)
            _items: List[Dict[str, Any]] = []
            _legacy = {x for x in (site,) if x} | {
                "%s-%s" % (_p, site) for _p in ("刷流", "魔力", "静默") if site
            }
            for hh in members:
                t = snap.get(hh)
                tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])] if t is not None else []
                cur = st.get(hh) or {}
                s2, _d2 = self._magicize_site(t, getattr(t, "tags", None) if t is not None else None,
                                              (getattr(t, "title", "") if t is not None else ""), hh)
                _site2 = s2 or site
                _add2 = tag_for(_site2, STATE_SILENT, sub)
                _legacy2 = {x for x in (_site2,) if x} | {
                    "%s-%s" % (_p, _site2) for _p in ("刷流", "魔力", "静默") if _site2
                }
                _keep = [x for x in tags if (not is_magicflow_tag(x)) and x not in _legacy2]
                _new = _keep + ([_add2] if _add2 not in _keep else [])
                _remove = [x for x in tags if x not in _new]
                if not _remove and _add2 in tags:
                    continue  # 已就位
                _items.append({"hash": hh, "site": _site2, "add": _add2, "remove": _remove,
                               "tags": tags, "new_tags": _new,
                               "asset": is_asset_tags(tags),
                               "in_ledger": bool(cur)})
                key = "%s|%s" % (_site2 or "-", sub)
                stats["sites"][key] = int(stats["sites"].get(key) or 0) + 1
            if sub == SUB_RESOURCE:
                stats["resource"] += 1
            else:
                stats["plain"] += 1
            stats["asset_keep"] += sum(1 for x in _items if x["asset"] and sub == SUB_RESOURCE)
            stats["asset_fail"] += sum(1 for x in _items if x["asset"] and sub == SUB_PLAIN and "未达标" in str(reason or ""))
            if len(stats["samples"]) < 20:
                stats["samples"].append({"title": title[:70], "site": site or "-",
                                         "verdict": verdict or sub, "reason": reason,
                                         "rating": rating, "members": len(members)})
            plan.append({
                "group": gid, "title": title, "site": site, "sub": sub,
                "verdict": verdict or sub, "reason": reason, "rating": rating,
                "items": _items,
            })
        stats["total"] = sum(len(p["items"]) for p in plan)
        stats["plan"] = plan
        return stats

    def _magicize_apply(self, plan: Any, *, limit: int = 0) -> Dict[str, Any]:
        """执行魔流化：改标签 + 写状态账本（origin=静默，asset 沿用 MP 资产标）。"""
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return {"ok": False, "error": "下载器不可用"}
        fn = getattr(downloader, "replace_torrent_tags", None)
        st = self._tag_state()
        done = failed = skipped = 0
        cap = int(limit or 0)
        _by_site: Dict[str, int] = {}
        for res in plan or []:
            sub = str(res.get("sub") or SUB_PLAIN)
            for item in (res.get("items") or []):
                if cap and done >= cap:
                    skipped += 1
                    continue
                hh = str(item.get("hash") or "").lower()
                if not hh:
                    continue
                ok = False
                try:
                    ok = bool(fn(hh, item.get("new_tags") or [])) if callable(fn) else False
                except Exception as err:  # noqa: BLE001
                    self._log(f"魔流化:打标失败 {hh[:12]}:{err}", "warning")
                    ok = False
                if not ok:
                    failed += 1
                    continue
                done += 1
                _key = str(item.get("site") or "-")
                _by_site[_key] = int(_by_site.get(_key) or 0) + 1
                rec: Dict[str, Any] = {
                    "site": item.get("site") or "",
                    "state": STATE_SILENT,
                    "sub": sub,
                    "asset": bool(item.get("asset")),
                    "title": str(res.get("title") or "")[:200],
                    "magicized": True,
                    "magicized_at": time.time(),
                    "reason": f"魔流化:{res.get('verdict')}({res.get('reason')})",
                }
                if res.get("rating") is not None:
                    rec["rating"] = res.get("rating")
                # 库内资产若「识别到 + 有评分 + 未达标」→ 记复核失败（与资源复核同口径）
                if bool(item.get("asset")) and str(res.get("verdict")) == "普通":
                    _rr = str(res.get("reason") or "")
                    if "未识别" not in _rr and "无评分" not in _rr and sub == SUB_PLAIN:
                        rec["asset_recheck"] = "fail"
                        rec["asset_recheck_at"] = time.time()
                elif bool(item.get("asset")):
                    rec["asset_recheck"] = "keep"
                    rec["asset_recheck_at"] = time.time()
                try:
                    st.put(hh, rec)
                except Exception as err:  # noqa: BLE001
                    self._log(f"魔流化:账本写入失败 {hh[:12]}:{err}", "warning")
        if done:
            self._log(f"魔流:{'魔流化'}完成 {done} 个种（失败 {failed}，站点 {len(_by_site)}）")
        return {"ok": True, "magicized": done, "failed": failed, "skipped": skipped,
                "by_site": _by_site}

    def get_tag_model(
        self,
        action: str = "status",
        hash: str = "",
        state: str = "",
        site: str = "",
        limit: int = 20,
    ) -> Response:
        """标签模型：状态账本 / 文件组 / 分拣规则 / 迁移计划。"""
        self._tag_sync_names()
        store = self._tag_state()
        groups = self._tag_groups()
        act = str(action or "status").strip().lower()
        if act == "state":
            h = str(hash or "").strip().lower()
            if not h:
                return Response(success=False, message="缺少 hash")
            live = self._tag_all_torrents().get(h)
            return Response(success=True, message="ok", data={
                "ledger": store.get(h),
                "tags": list(getattr(live, "tags", []) or []) if live else [],
                "group_id": groups.group_of(h),
            })
        if act == "list":
            hs = store.hashes_by_state(state=state, site=site)
            items = store.items()
            return Response(success=True, message="ok", data={
                "total": len(hs),
                "items": [{ "hash": h, **{k: items[h].get(k) for k in ("site", "state", "sub", "taken_by", "origin_sub", "title", "size_gb", "asset")}} for h in hs[:max(1, int(limit or 20))]],
            })
        if act == "resource":
            if str(hash or "").strip():
                gid = str(hash).strip()
                rec = groups.items().get(gid) or {}
                return Response(success=True, message="ok", data={"group_id": gid, "resource": rec})
            rows = groups.resources(limit=int(limit or 0) if str(limit).isdigit() else 0)
            return Response(success=True, message=f"资源 {len(rows)} 个", data={
                "count": len(groups.items()), "multi": groups.stats().get("multi_site_groups", 0),
                "items": rows[: max(1, int(limit)) if str(limit).isdigit() and int(limit) > 0 else 50],
            })
        if act in ("triage", "silent", "triage_apply"):
            _ap = act == "triage_apply"
            info = self._silent_triage(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(
                    f"静默池分拣 {info.get('scanned')} 个 → 推荐 {info.get('promoted')} · "
                    f"普通 {info.get('plain')}（欠H&R {info.get('waiting_hr')}）"
                ),
                data=info,
            )
        if act in ("purge", "purge_incomplete", "purge_apply"):
            _ap = act == "purge_apply"
            info = self._silent_purge_incomplete(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"静默池未下完 {info.get('pending')} 个 → 删除 {info.get('deleted')} 个"
                         + ("" if _ap else "（预演，未删）")),
                data=info,
            )
        if act in ("hr", "hr_guard", "hr_apply"):
            _ap = act == "hr_apply"
            info = self._hr_guard_tick(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"H&R 统一管理:欠 {info.get('obligated')} 个 → 打标 {info.get('tagged')} · "
                         f"强拉起 {info.get('resumed')} · 结清摘标 {info.get('cleared')} · "
                         f"松绑 {info.get('released')}"
                         + ("" if _ap else "（预演）")),
                data=info,
            )
        if act in ("plain", "plain_sweep", "plain_apply"):
            _ap = act == "plain_apply"
            info = self._silent_plain_sweep(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"静默-普通 待清 {info.get('pending')} 个（保护 {info.get('protected')}）→ "
                         f"删除 {info.get('deleted')} 个" + ("" if _ap else "（预演）")),
                data=info,
            )
        if act in ("expire_downgrade", "expire_apply"):
            _ap = act == "expire_apply"
            info = self._recommend_downgrade_expired(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"推荐过期待降级 {info.get('downgraded')} 个"
                         + ("" if _ap else "（预演）")),
                data=info,
            )
        if act in ("verify", "verify_marks", "verify_apply"):
            _ap = act == "verify_apply"
            info = self._silent_verify_marks(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"静默池辅种待校验 {info.get('pending')} 个 → recheck {info.get('checked')} 个"
                         + ("" if _ap else "（预演）")),
                data=info,
            )
        if act in ("resume", "keep_seed", "resume_apply"):
            _ap = act == "resume_apply"
            info = self._silent_resume_tick(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"H&R 保挂:静默 {info.get('silent')} · 欠H&R {info.get('hr_pending')}"
                         f" → 强制挂种 {info.get('resumed')} 个（非H&R {info.get('nonhr')} 不动）"
                         + ("" if _ap else "（预演）")),
                data=info,
            )
        if act in ("settle", "settle_idle"):
            info = self._settle_disabled_tasks(apply=True)
            return Response(success=True, message=f"已遣散退回静默 {info.get('settled')} 个", data=info)
        if act == "settle_plan":
            info = self._settle_disabled_tasks(apply=False)
            return Response(success=True, message=f"待遣散 {info.get('pending')} 个", data=info)
        if act in ("rehome", "rehome_apply"):
            _ap2 = act == "rehome_apply"
            _ri = self.rehome_verdicts(apply=_ap2, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"身份归位 {_ri.get('moved')} 个" if _ap2 else f"待归位 {_ri.get('pending')} 个"),
                data=_ri,
            )
        if act in ("fp", "fingerprint"):
            _lim = int(limit) if str(limit).isdigit() else 0
            return Response(success=True, message="特征码补录完成", data=self.backfill_fingerprints(limit=_lim))
        if act in ("syncres", "resource_sync"):
            return Response(success=True, message="资源账本已刷新", data=self.sync_resources(apply=True))
        if act in ("assets_recheck", "assets_recheck_apply", "recheck"):
            _ap = act in ("assets_recheck_apply", "recheck")
            info = self._assets_recheck(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"已入库资源过推荐流程:复核 {info.get('resources')} 组 · 达标 {info.get('qualified')}"
                         f" · 不达标 {info.get('unqualified')} · 未识别 {info.get('unrecognized')}"
                         f" · 无评分(豁免) {info.get('unrated')}"
                         f" · 已转普通 {info.get('downgraded')} · 回升资源 {info.get('restored')}"
                         + ("" if _ap else "（预演，未动）")),
                data=info,
            )
        if act in ("asset_untag", "asset_untag_apply"):
            _ap = act == "asset_untag_apply"
            info = self._asset_untag(apply=_ap, limit=int(limit or 0))
            return Response(
                success=True,
                message=(f"假「已整理/辅种」:带标 {info.get('scanned')} · 已在库(留) {info.get('kept_inlib')}"
                         f" · 待摘 {info.get('fake')} · 已摘 {info.get('removed')}"
                         + ("" if _ap else "（预演，未动 qB）")),
                data=info,
            )
        if act == "asset":
            info = self.sync_tag_assets(apply=True)
            return Response(success=True, message=f"库内资产 {info.get('asset')} 个（更新 {info.get('changed')}）", data=info)
        if act == "expire":
            moved = store.expire_new(timeout=float(self._tags_cfg.get("new_timeout") or TAG_NEW_TIMEOUT))
            return Response(success=True, message=f"静默-新超时归普通 {len(moved)} 个", data={"moved": moved})
        if act == "snapshot":
            info = store.snapshot()
            return Response(success=True, message="已落快照", data=info)
        if act in ("magicize", "magicize_plan", "magicize_apply"):
            _ap = act == "magicize_apply"
            info = self._magicize_plan(limit=limit, site_filter=site)
            if not info.get("ok"):
                return Response(success=False, message=str(info.get("reason") or "魔流化预演失败"), data=info)
            if not _ap:
                return Response(
                    success=True,
                    message=(f"魔流化预演：非魔流 {info['torrents']} 个种 / {info['groups']} 个资源"
                             f" → 资源 {info['resource']} 组 · 普通 {info['plain']} 组"
                             f"（未识别 {info['unrecognized']} · 无评分 {info['unrated']}）"),
                    data={k: v for k, v in info.items() if k != "plan"},
                )
            res = self._magicize_apply(info.get("plan") or [], limit=limit)
            return Response(
                success=bool(res.get("ok")),
                message=(f"魔流化完成：改标 {res.get('magicized')} 个种（失败 {res.get('failed')}，跳过 {res.get('skipped')}）"
                         + (f" / 计划 {info['total']} 个" if info.get("total") else "")),
                data={"plan_summary": {k: v for k, v in info.items() if k != "plan"}, "applied": res},
            )
        if act == "hygiene":
            info = self._tag_hygiene_round(force=True)
            return Response(
                success=bool(info.get("ok")),
                message=(f"标签主权巡检：摘其他标签 {info.get('cleaned')} · 新纳管 {info.get('adopted')}"
                         f" · MP 来源提资源 {info.get('promoted')}（失败 {info.get('failed')}）"),
                data=info,
            )
        if act in ("clean", "clean_plan", "clean_apply"):
            _ap = act == "clean_apply"
            info = self._tag_clean_plan(limit=int(limit or 0))
            if not _ap:
                return Response(
                    success=True,
                    message=(f"标签清理预演：待摘 {info['total']} 个种的「其他标签」"
                             f"（其中库内资产 {info['assets']} 个，会先记账本再摘）"),
                    data={k: v for k, v in info.items() if k != "plan"},
                )
            res = self._tag_clean_apply(info.get("plan") or [], limit=int(limit or 0))
            return Response(
                success=bool(res.get("ok")),
                message=(f"标签清理完成：清 {res.get('cleaned')} 个种（失败 {res.get('failed')}"
                         f"，记入库内账本 {res.get('asset_adopted')}）"),
                data={"plan_summary": {k: v for k, v in info.items() if k != "plan"}, "applied": res},
            )
        if act == "migrate":
            plan = self._tag_migration_plan()
            return Response(success=True, message=f"待迁移 {plan['total']} 个", data={
                "total": plan["total"], "by_state": plan["by_state"],
                "samples": [{k: s.get(k) for k in ("title", "site", "state", "sub", "source", "remove", "add")} for s in plan["samples"]],
            })
        # default: status
        items = store.items()
        snap = store.snapshots()
        return Response(success=True, message="ok", data={
            "enabled": bool(self._tags_cfg.get("enabled", True)),
            "new_timeout_hours": round(float(self._tags_cfg.get("new_timeout") or 0) / 3600.0, 2),
            "snapshot_interval_hours": round(float(self._tags_cfg.get("snapshot_interval") or 0) / 3600.0, 2),
            "ledger_count": len(items),
            "by_state": store.stats(),
            "stale": store.stale_count(),
            "unowned": sum(1 for r in items.values()
                           if not str(r.get("taken_by") or "")
                           and str(r.get("state") or "") in DUTY_STATES),
            "assets": {"count": sum(1 for r in items.values() if r.get("asset")),
                       "size_gb": round(sum(float(r.get("size_gb") or 0) for r in items.values() if r.get("asset")), 2)},
            "groups": groups.stats(),
            "snapshots": [{"ts": s.get("ts"), "count": s.get("count")} for s in snap],
            "site_names": self._tag_site_names(),
            "sort_rules": [dict(r) for r in (self._tags_cfg.get("rules") or [])],
            "states": [STATE_BRUSH, STATE_BONUS, STATE_SILENT, STATE_RECOMMEND],
            "subs": [SUB_NEW, SUB_RESOURCE, SUB_PLAIN],
        })

    def set_tag_state(self, payload: MagicFlowTagStatePayload) -> Response:
        """手动设置种子状态：改标签 + 写账本（两处一起，失败回滚标签）。"""
        h = str(getattr(payload, "hash", "") or "").strip().lower()
        state = str(getattr(payload, "state", "") or "").strip()
        sub = str(getattr(payload, "sub", "") or "").strip()
        if not h or not state:
            return Response(success=False, message="需要 hash 与 state")
        if state not in (STATE_BRUSH, STATE_BONUS, STATE_SILENT, STATE_RECOMMEND):
            return Response(success=False, message=f"非法状态：{state}")
        if state == STATE_SILENT and not sub:
            sub = SUB_PLAIN
        store = self._tag_state()
        live = self._tag_all_torrents().get(h)
        if live is None:
            return Response(success=False, message="下载器里找不到该种子")
        site = self._torrent_site_name(getattr(live, "tags", None)) or str(getattr(payload, "site", "") or "")
        old_tags = [str(x).strip() for x in (getattr(live, "tags", None) or [])]
        # ★ 5.0.0：手动改状态只改**职务**，身份自动沿用（除非显式给了 sub）
        _i_site, _i_sub = identity_of(old_tags)
        if not sub:
            sub = _i_sub or (SUB_RESOURCE if is_asset_tags(old_tags) else SUB_NEW)
        site = site or _i_site
        new_tags = retag(old_tags, site=site, state=state, sub=sub)
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return Response(success=False, message="下载器不可用")
        fn = getattr(downloader, "replace_torrent_tags", None)
        ok = fn(h, new_tags) if callable(fn) else downloader.set_torrent_tags(h, new_tags)
        if not ok:
            return Response(success=False, message="标签写入失败")
        store.put(h, {
            "site": site, "state": state, "sub": sub,
            "manual": True, "title": str(getattr(live, "title", "") or ""),
            "size_gb": float(getattr(live, "size_gb", 0) or 0),
        })
        return Response(success=True, message=f"已设为 {tag_for(site, state, sub)}", data={
            "hash": h, "site": site, "state": state, "sub": sub, "tags": new_tags,
        })

    def migrate_tags(self, payload: MagicFlowTagMigratePayload) -> Response:
        """老标签迁移到新命名（默认 dry-run，``apply=true`` 才落盘）。"""
        plan = self._tag_migration_plan()
        if not bool(getattr(payload, "apply", False)):
            return Response(success=True, message=f"预演：待迁移 {plan['total']} 个（未执行）", data={
                "dry_run": True, "total": plan["total"], "by_state": plan["by_state"],
                "samples": [{k: s.get(k) for k in ("title", "site", "state", "sub", "source", "remove", "add")} for s in plan["samples"]],
            })
        res = self._tag_migrate_apply(plan["plan"])
        return Response(success=bool(res.get("ok")), message=f"迁移完成：{res.get('migrated')} 个（失败 {res.get('failed')}）", data=res)

    def tags_watch(self) -> None:
        """标签账本维护（worker）：状态账本快照/对账 · 资源账本 · 特征码补录 · 停止任务退静默。

        注：**静默池本身的托管**（清理/保挂/分拣/H&R/校验）已迁到常驻 worker「静默托管」``silent_host``。
        """
        try:
            store = self._tag_state()
            try:
                finfo = self.backfill_fingerprints(limit=40)
                if finfo.get("got"):
                    self._dbg(f"标签维护:特征码补录 {finfo.get('got')} 个（余 {finfo.get('remaining')}）")
            except Exception as err:  # noqa: BLE001
                self._log(f"标签维护:特征码补录失败:{err}", "warning")
            try:
                sinfo = self._settle_disabled_tasks(apply=True)
                if sinfo.get("settled"):
                    self._log(f"魔流:标签维护:停止任务退回静默 {sinfo.get('settled')} 个"
                              f"（{len([x for x in sinfo.get('tasks') or [] if x.get('settled')])} 个任务）")
            except Exception as err:  # noqa: BLE001
                self._log(f"标签维护:停止任务退静默失败:{err}", "warning")
            try:
                _live = list(self._tag_all_torrents().keys())
                rinfo2 = store.reconcile(_live)
                if rinfo2.get("dropped"):
                    self._log(f"魔流:标签维护:账本对账销账 {rinfo2.get('dropped')} 条僵尸记录"
                              f"（待销账 {rinfo2.get('pending')}）")
            except Exception as err:  # noqa: BLE001
                self._log(f"标签维护:账本对账失败:{err}", "warning")
            try:
                rinfo = self.sync_resources(apply=True)
                if rinfo.get("resources"):
                    self._log(f"魔流:标签维护:资源账本 {rinfo.get('resources')} 个"
                              f"（多样 {rinfo.get('multi')} · 入库 {rinfo.get('in_library')} · H&R 账单 {rinfo.get('hr_bills')}）")
            except Exception as err:  # noqa: BLE001
                self._log(f"标签维护:资源同步失败:{err}", "warning")
            interval = float(self._tags_cfg.get("snapshot_interval") or TAG_SNAPSHOT_INTERVAL)
            now = time.time()
            if interval > 0 and (now - float(getattr(self, "_tag_last_snapshot", 0) or 0)) >= interval:
                info = store.snapshot()
                self._tag_last_snapshot = now
                self._dbg(f"魔流:标签维护:状态账本快照完成（{info.get('count')} 条）")
        except Exception as err:  # noqa: BLE001
            self._log(f"标签维护异常:{err}", "warning")
