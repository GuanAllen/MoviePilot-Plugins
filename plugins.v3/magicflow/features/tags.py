# -*- coding: utf-8 -*-
"""魔流 · tags —— 标签账本（状态标签 + 文件组引用计数）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

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
    FileGroupStore,
    LEASE_TTL,
    asset_origin_sub,
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
                obj = TagStateStore(get_data=self.get_data, save_data=self.save_data, log=self._log)
                mod.instances["tag_state"] = obj
        except Exception:  # noqa: BLE001
            obj = TagStateStore(get_data=self.get_data, save_data=self.save_data, log=self._log)
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
                obj = FileGroupStore(get_data=self.get_data, save_data=self.save_data, log=self._log)
                mod.instances["tag_groups"] = obj
        except Exception:  # noqa: BLE001
            obj = FileGroupStore(get_data=self.get_data, save_data=self.save_data, log=self._log)
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
        origin_sub: str = SUB_NEW,
        reason: str = "",
    ) -> int:
        """★ 把种子归到任务名下：真替换标签 + 写状态账本（claim）。返回成功数。"""
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        site, state = self._task_site_state(task)
        if state == STATE_SILENT:
            pass
        target = tag_for(site, state, sub)
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
            new_tags = retag(cur, site=site, state=state, sub=sub) if cur else [target]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            rec = {
                "site": site, "state": state, "sub": sub,
                "taken_by": _tid,
                "task": str(getattr(task, "name", "") or ""),
                "taken_at": _now, "lease_until": _now + float(LEASE_TTL),
                "origin_state": STATE_SILENT, "origin_sub": origin_sub or SUB_NEW,
                "title": str(getattr(live, "title", "") or "") if live is not None else "",
                "size_gb": float(getattr(live, "size_gb", 0) or 0) if live is not None else 0.0,
            }
            try:
                store.claim(hh, str(getattr(task, "id", "") or ""), state=state, site=site)
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
        """★ 任务退出：按账本 origin 退回（刷流→静默-新/资源等），返回成功数。"""
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
            site = str(rec.get("site") or "") or self._torrent_site_name(
                getattr(snap.get(hh), "tags", None)
            )
            o_state = str(rec.get("origin_state") or STATE_SILENT)
            o_sub = str(rec.get("origin_sub") or (SUB_NEW if o_state == STATE_SILENT else ""))
            live = snap.get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            # 老记录（迁移期写入）origin 直接等于任务态 → 退回时按静默处理（库内资产→资源，其余→新）
            if o_state in (STATE_BRUSH, STATE_BONUS):
                o_state = STATE_SILENT
                _is_asset = any(x in ("已整理", "辅种") for x in cur)
                o_sub = SUB_RESOURCE if _is_asset else (o_sub if o_sub in (SUB_NEW, SUB_PLAIN) else SUB_NEW)
            elif o_state == STATE_SILENT and o_sub not in (SUB_NEW, SUB_RESOURCE, SUB_PLAIN):
                o_sub = SUB_RESOURCE if any(x in ("已整理", "辅种") for x in cur) else SUB_NEW
            target = tag_for(site, o_state, o_sub)
            new_tags = retag(cur, site=site, state=o_state, sub=o_sub) if cur else [target]
            if cur and sorted(new_tags) == sorted(cur):
                done = True  # 标签已就位：只账本销账，不再打 qB
            else:
                try:
                    done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
                except Exception:  # noqa: BLE001
                    done = False
            if done:
                try:
                    # 先把归一化后的 origin 写回，release 才会退回正确的静默子类
                    store.put(hh, {"origin_state": o_state, "origin_sub": o_sub})
                    store.release(hh, task_id=tid)
                except Exception as _rerr:  # noqa: BLE001
                    self._log(f"标签账本释放失败 {hh[:8]}:{_rerr}", "warning")
                n += 1
        if n and reason:
            self._dbg(f"标签模型:任务「{getattr(task, 'name', '')}」退回 {n} 个（{reason}）")
        return n

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
            keep_extra = [rec_tag] if rec_tag in mf_tags else []
            if not state and CROSSSEED_TAG in mf_tags:
                state, sub, src = STATE_SILENT, SUB_RESOURCE, "跨站来源份"
            if not state:
                parsed = None
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
                "sub": item.get("sub") or "",
                # ★ origin = 真正的「静默态」：退回时才知道该回哪儿（别写任务态，否则退回是空操作）
                "origin_state": STATE_SILENT,
                "origin_sub": asset_origin_sub(_tags_now),
                "asset": _is_asset,
                "title": item.get("title") or "",
                "migrated": True,
            })
            done += 1
        return {"ok": True, "migrated": done, "failed": failed}

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
            return Response(success=True, message=f"停止任务退回静默 {info.get('settled')} 个", data=info)
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
                           and str(r.get("state") or "") in (STATE_BRUSH, STATE_BONUS)),
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
        if state != STATE_SILENT:
            sub = ""
        elif not sub:
            sub = SUB_PLAIN
        store = self._tag_state()
        live = self._tag_all_torrents().get(h)
        if live is None:
            return Response(success=False, message="下载器里找不到该种子")
        site = self._torrent_site_name(getattr(live, "tags", None)) or str(getattr(payload, "site", "") or "")
        old_tags = [str(x).strip() for x in (getattr(live, "tags", None) or [])]
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
            "origin_state": state, "origin_sub": sub,
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
