# -*- coding: utf-8 -*-
"""魔流 · 5 表读写层（6.0.0 引入；6.1.0 收敛为真列）

把两个账本对象（``TagStateStore`` / ``FileGroupStore``）的**存储后端**换成插件专属库
（见 ``db.py``），**对象 API 与业务代码完全不变**：

    TagStateStore  ← 写 mf_seed 台账列（state/title/taken_by/…） + mf_resource.identity（身份）
    FileGroupStore ← 写 mf_resource（资源/入库列）            + mf_seed 组员列（in_group/m_*）

6.1.0 起：**单值字段一律真列**，JSON 兜底（``rt`` / ``mmbr`` / ``library`` / ``extra``）
降级为**影子**——只写不读（读时仅当兜底），留着是为了「回滚到 6.0.0 还能读」，7.0.0 连列一起删。
老库的新列由 ``_ensure_columns()`` 自愈补上；历史数据由 ``backfill_columns()``
（``features/migrate.py`` 的收敛阶段调用）一次性从影子搬进真列。
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, inspect as sa_inspect, select, text, update

from . import db as mfdb
from . import tables as T
from .tags import (GROUPS_KEY, STATE_BONUS, STATE_BRUSH, STATE_KEY, STATE_SILENT,
                   FileGroupStore, TagStateStore)
from .common import task_is_participating

# 台账真列（6.1.0 从 rt 收敛）
_SEED_COLS = ("state", "title", "reason", "asset", "taken_by", "taken_at", "lease_until",
              "verify_at", "verify_n", "crossseed", "downloader", "ts", "created")
# 组员真列（6.1.0 从 mmbr 收敛）
_MEMBER_COLS = ("m_added", "m_progress", "m_downloaded", "m_downloader", "m_state")
# 入库真列（6.1.0 从 library 收敛）
_LIB_COLS = ("in_library", "lib_first_at", "lib_updated", "lib_path", "lib_media_id")
# 7.0.0 待削：这些历史死字段不再进 rec（连影子都不会有）
# ★ 注意 ``asset_recheck``/``asset_recheck_at`` **不在**死字段里：features/assets.py 仍在读写它，
#   误归入死字段会直接搞坏「库内资产复核」。（旧写法把它们列进来，是错的，从未生效所以没爆。）
DEAD_FIELDS = ("origin", "origin_state", "origin_sub", "migrated", "magicized",
               "magicized_at", "rehomed_at", "mp_promoted_at")
_DEAD_SET = frozenset(DEAD_FIELDS)
LEGACY_MIRROR_SEC = 15.0     # 双写旧 kv 键的节流间隔（回滚保险）
_SCHEMA_LOCK = threading.Lock()   # 结构自愈串行化（启动瞬间多 worker 抢建列会撞 DuplicateColumn）

# ★ 7.0.0 标签退役：这些列不再被 ORM 声明，启动时如果还在则 DROP COLUMN（PG）。
#   顺序与 db.py SeedRow 旧声明一致（仅供人看，不是强制顺序）。
_RETIRED_COLS = frozenset((
    "state", "title", "reason", "asset", "taken_by", "taken_at", "lease_until",
    "verify_at", "verify_n", "crossseed", "downloader", "ts", "created",
    "in_group", "m_added", "m_progress", "m_downloaded", "m_downloader", "m_state",
    "mmbr", "rt",
))


def norm_res_id(value: Any) -> str:
    """资源主键归一：老键 ``fp:<hash>`` ↔ 行主键 ``<hash>``。"""
    s = str(value or "").strip()
    return s[3:] if s.startswith("fp:") else s


def group_key(resource_id: str) -> str:
    """资源主键 → 老 group id（``fp:<hash>``，业务代码里到处这么拼，必须保持）。"""
    return f"fp:{resource_id}"


def ledger_ready(plugin: Any) -> bool:
    """是否可以用 5 表后端：迁移已完成戳 + 官方插件库可用。"""
    try:
        if not plugin.get_data(T.MARKER_KEY):
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        plugin.get_database()
    except Exception:  # noqa: BLE001
        return False
    return True


class LedgerBackend:
    """整包 dict ↔ 5 张表。所有写操作加锁（MP 是多线程跑的）。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self._lock = threading.RLock()
        self._seeds: Optional[Dict[str, Dict[str, Any]]] = None
        self._seed_prev: Dict[str, Dict[str, Any]] = {}
        self._groups: Optional[Dict[str, Dict[str, Any]]] = None
        self._group_prev: Dict[str, Dict[str, Any]] = {}
        self._site_by_name: Dict[str, int] = {}
        self._name_by_id: Dict[int, str] = {}
        self._site_at = 0.0
        self._schema_checked = False
        self._legacy_at: Dict[str, float] = {}

    # ------------------------------------------------------------ 基础设施

    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(msg, level)
        except Exception:  # noqa: BLE001
            pass

    def _session(self):
        return self.plugin.get_database().session()

    def ensure_schema(self) -> bool:
        """结构自愈：表缺了补建，列缺了补加（直接升到 6.1+ 的老库也能站起来）。

        ★ 并发护栏：启动瞬间会有多个 worker 同时首次触及账本 → 不加锁会并发
        ``ALTER TABLE ADD COLUMN`` 撞车（DuplicateColumn）。用模块级锁串行，
        并且单列用 SAVEPOINT 隔离（PG 上一句报错会把整个事务打成 aborted）。
        """
        if self._schema_checked:
            return True
        with _SCHEMA_LOCK:
            if self._schema_checked:
                return True
            try:
                mfdb.Base.metadata.create_all(self.plugin.get_database().engine)
            except Exception as err:  # noqa: BLE001
                self._log(f"账本:建表失败:{err}", "error")
                return False
            try:
                self._ensure_columns()
            except Exception as err:  # noqa: BLE001
                self._log(f"账本:补列失败:{err}", "error")
                return False
            self._schema_checked = True
            return True

    def _ensure_columns(self) -> None:
        """补列：``create_all`` 只建表不改表，这里比对后 ``ALTER TABLE ADD COLUMN``。

        单列独立 SAVEPOINT：已存在/并发抢建 → 跳过而不是把整轮搞挂。
        """
        added: List[str] = []
        sess = self._session()
        try:
            conn = sess.connection()
            insp = sa_inspect(conn)
            for model in mfdb.ALL_MODELS:
                table = model.__table__
                try:
                    have = {c["name"] for c in insp.get_columns(table.name)}
                except Exception:  # noqa: BLE001
                    continue
                for col in table.columns:
                    if col.name in have:
                        continue
                    ddl = col.type.compile(dialect=conn.dialect)
                    try:
                        with conn.begin_nested():          # SAVEPOINT：单列失败不污染事务
                            conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))
                        added.append(f"{table.name}.{col.name}")
                    except Exception as err:  # noqa: BLE001
                        msg = str(err).lower()
                        if "already exists" in msg or "duplicate" in msg:
                            added.append(f"{table.name}.{col.name}(已有)")
                            continue
                        self._log(f"账本:补列 {table.name}.{col.name} 跳过:{err}", "warning")
                # ★ 7.0.0 影子退役：清理不再使用的列（反向补列）；表中存在但 ORM 未声明则 DROP。
                #   PG 直接 DROP COLUMN 即可（SQLite 不支持但本部署用 PG）。
                #   ⚠️ 必须在 for 循环【内】——table/have/declared 每张表各自结算，
                #      放循环外只会作用到最后一张表（TaskRow），退役列永远清不掉。
                try:
                    declared = {c.name for c in table.columns}
                    for col_name in sorted(have - declared):
                        if col_name in _RETIRED_COLS:
                            try:
                                with conn.begin_nested():
                                    conn.execute(text(
                                        f"ALTER TABLE {table.name} DROP COLUMN IF EXISTS {col_name}"))
                                added.append(f"{table.name}.{col_name}(退役 DROP)")
                            except Exception as err:  # noqa: BLE001
                                self._log(
                                    f"账本:退役列 {table.name}.{col_name} DROP 失败:{err}", "warning")
                except Exception as err:  # noqa: BLE001
                    self._log(f"账本:退役列扫描失败:{err}", "warning")
            if added:
                sess.commit()
                self._log(f"账本:补列 {len(added)} 个（结构自愈）{'/'.join(added[:6])}"
                          f"{'…' if len(added) > 6 else ''}")
        finally:
            sess.close()

    # ------------------------------------------------------------ 站点索引

    def _site_names(self) -> Dict[int, str]:
        if time.time() - self._site_at < 60.0 and self._name_by_id:
            return self._name_by_id
        try:
            sess = self._session()
            try:
                rows = sess.execute(select(mfdb.SiteRow.site_id, mfdb.SiteRow.name)).all()
            finally:
                sess.close()
        except Exception:  # noqa: BLE001
            return self._name_by_id
        self._name_by_id = {int(r[0]): str(r[1] or "") for r in rows if r[0] is not None}
        self._site_by_name = {v.strip().lower(): k for k, v in self._name_by_id.items() if v.strip()}
        self._site_at = time.time()
        return self._name_by_id

    def _site_id(self, name: str, *, create: bool = True) -> Optional[int]:
        key = str(name or "").strip()
        if not key:
            return None
        self._site_names()
        sid = self._site_by_name.get(key.lower())
        if sid is not None or not create:
            return sid
        try:                                     # 新站点：补一行，保持引用完整
            sess = self._session()
            try:
                top = sess.execute(select(mfdb.SiteRow.site_id).order_by(mfdb.SiteRow.site_id.desc()).limit(1)).scalar()
                sid = int(top or 0) + 1
                now = time.time()
                sess.merge(mfdb.SiteRow(site_id=sid, name=key, created=now, updated=now))
                sess.commit()
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:补站点「{key}」失败:{err}", "warning")
            return None
        self._name_by_id[sid] = key
        self._site_by_name[key.lower()] = sid
        return sid

    def _task_name(self, task_id: Any) -> str:
        cfg = (getattr(self.plugin, "_task_configs", {}) or {}).get(str(task_id or ""))
        return str(getattr(cfg, "name", "") or "") if cfg is not None else ""

    def _task_state(self, task_id: Any) -> str:
        """任务 id → 职务（刷流/魔力/静默）。7.0.0 退役 state 列后，职务由任务推导。

        ★ 关键：任务被停止（遣散）→ 静默，不看 task_type。只有 running/seeding
          （participating）才算在岗（刷流/魔力）。否则 stopped 任务的种会被误算成在岗。
        """
        cfg = (getattr(self.plugin, "_task_configs", {}) or {}).get(str(task_id or ""))
        if cfg is None:
            return STATE_SILENT
        if not task_is_participating(cfg):
            return STATE_SILENT
        return STATE_BRUSH if str(getattr(cfg, "task_type", "") or "") == "brush" else STATE_BONUS

    def _task_id(self, name: str) -> Optional[str]:
        key = str(name or "").strip().lower()
        if not key:
            return None
        for tid, cfg in (getattr(self.plugin, "_task_configs", {}) or {}).items():
            if str(tid).lower() == key or str(getattr(cfg, "name", "") or "").strip().lower() == key:
                return str(tid)
        return None

    def _mirror_legacy(self, key: str, value: Any) -> None:
        """双写旧 kv 键（节流）——回滚保险，7.0.0 删。"""
        now = time.time()
        if now - float(self._legacy_at.get(key) or 0.0) < LEGACY_MIRROR_SEC:
            return
        self._legacy_at[key] = now
        try:
            self.plugin.save_data(key=key, value=value)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 字段映射（读）

    def _rec_from_seed(self, s: Any, names: Dict[int, str]) -> Dict[str, Any]:
        """一行种子 → 台账 rec（★ 7.0.0 重写：只读 ORM 声明列）。

        退役的旧真列（state/title/reason/asset/taken_*/verify_*/crossseed/downloader/ts/created）
        不再读出 —— 它们已经被 DROP，SQLAlchemy 访问会报 AttributeError。身份走 resource。
        """
        rec: Dict[str, Any] = {}
        rec["site"] = names.get(s.site_id) or ""
        if s.task_id:
            rec["task"] = self._task_name(s.task_id) or ""
        if s.resource_id:
            rec["fp"] = s.resource_id
        if s.published_at is not None:
            rec["published_at"] = s.published_at
        if s.vfy_miss:
            rec["miss"] = int(s.vfy_miss)
        if s.updated is not None:
            rec["updated"] = s.updated
        return rec

    @staticmethod
    def _member_rec(s: Any, names: Dict[int, str]) -> Dict[str, Any]:
        """一行种子的组员字段（★ 7.0.0 重写：只读 ORM 声明列）。

        退役的组员真列（in_group/m_*/mmbr）不再读出。
        """
        m: Dict[str, Any] = {}
        m["site"] = names.get(s.site_id) or ""
        if s.resource_id:
            m["fp"] = s.resource_id
        return m

    def _rec_from_resource(self, r: Any, members: Dict[str, Dict[str, Any]],
                           names: Dict[int, str]) -> Dict[str, Any]:
        """一行资源 → 资源账本 rec（真列优先，影子兜底）。"""
        rec: Dict[str, Any] = dict(r.extra or {})       # 影子打底（历史兜底，实测空）
        rec["created"] = r.created
        rec["updated"] = r.updated
        rec["size_gb"] = r.size_gb
        rec["files_shared"] = bool(r.files_shared)
        rec["source_hash"] = r.source_hash or ""
        rec["source_site"] = names.get(r.source_site_id) or r.source_site_name or rec.get("source_site") or ""
        rec["members"] = dict(members or {})           # 已按资源 id 取好的成员表
        lib: Dict[str, Any] = dict(r.library or {})     # 影子打底
        for col, key in (("in_library", "in_library"), ("lib_first_at", "first_at"),
                         ("lib_updated", "updated"), ("lib_path", "path"), ("lib_media_id", "media_id")):
            v = getattr(r, col, None)
            if v is not None:
                lib[key] = bool(v) if col == "in_library" else v
        rec["library"] = lib
        if r.identity:
            rec["identity"] = r.identity
            rec["identity_at"] = r.identity_at
            rec["identity_by"] = r.identity_by
        if r.hrs:
            hr = dict(r.hrs[0] or {})
            hr.pop("site_id", None)
            rec["hr"] = hr
        if r.rating is not None:
            rec["rating"] = r.rating
        return rec

    # ------------------------------------------------------------ 字段映射（写）

    def seed_row(self, h: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
        """台账 rec → mf_seed 整行（★ 7.0.0 重写：只写真列）。

        退役的真列（state/title/reason/asset/taken_*/verify_*/crossseed/downloader/ts/created）
        不再写入。状态/身份/H&R 走 resource；进度/体积/做种时长走下载器实况。
        """
        site_name = str(rec.get("site") or "").strip()
        sid = self._site_id(site_name)
        task_name = str(rec.get("task") or "").strip()
        tid = self._task_id(task_name)
        rid = norm_res_id(rec.get("fp")).lower()
        return {
            "hash": str(h).lower(),
            "site_id": sid,
            "resource_id": rid or None,
            "task_id": tid,
            "published_at": rec.get("published_at"),
            "vfy_miss": int(rec.get("miss") or 0),
            "updated": rec.get("updated") or now,
        }

    def _member_patch(self, h: str, rid: Optional[str], m: Dict[str, Any],
                      now: float) -> Dict[str, Any]:
        """组员字段 → mf_seed 组员列（★ 7.0.0 重写：只写核心列）。

        组员的体积/进度/状态走 resource.members；这里只保留 hash↔resource_id 关联。
        """
        patch: Dict[str, Any] = {
            "hash": str(h).lower(),
            "resource_id": (str(rid).lower() or None) if rid else None,
            "updated": now,
        }
        site_name = str((m or {}).get("site") or "").strip()
        sid = self._site_id(site_name) if site_name else None
        if sid:
            patch["site_id"] = sid
        return patch

    def res_row(self, rid: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
        hr = rec.get("hr") or {}
        hrs: List[Dict[str, Any]] = []
        if isinstance(hr, dict) and hr:
            item = dict(hr)
            site_name = str(item.get("site") or "").strip()
            if site_name:
                item["site_id"] = self._site_id(site_name)
                item.pop("site", None)
            hrs = [item]
        src_site = str(rec.get("source_site") or "").strip()
        src_id = self._site_id(src_site) if src_site else None
        lib = rec.get("library") or {}
        row: Dict[str, Any] = {
            "resource_id": rid,
            "grouped": True,
            "size_gb": rec.get("size_gb"),
            "files_shared": bool(rec.get("files_shared")),
            "source_hash": str(rec.get("source_hash") or "").lower() or None,
            "hrs": hrs,
            "created": rec.get("created") or now,
            "updated": rec.get("updated") or now,
        }
        if src_id or not src_site:
            row["source_site_id"] = src_id
        else:
            row["source_site_name"] = src_site     # 关联不上 → 单列兜底
        # 入库真列
        row["in_library"] = None if lib.get("in_library") is None else bool(lib.get("in_library"))
        row["lib_first_at"] = lib.get("first_at")
        row["lib_updated"] = lib.get("updated")
        row["lib_path"] = lib.get("path") or None
        row["lib_media_id"] = str(lib.get("media_id") or "") or None
        row["library"] = dict(lib)                 # 影子
        row["extra"] = {}
        if rec.get("identity"):
            row["identity"] = str(rec["identity"])
            row["identity_at"] = rec.get("identity_at")
            row["identity_by"] = rec.get("identity_by")
        if rec.get("rating") is not None:
            row["rating"] = rec.get("rating")
        return row

    # ------------------------------------------------------------ 种子账本

    def load_seeds(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if self._seeds is None:
                self._seeds = self._read_seeds()
                self._seed_prev = copy.deepcopy(self._seeds)
            return self._seeds

    def _read_seeds(self) -> Dict[str, Dict[str, Any]]:
        names = self._site_names()
        try:
            sess = self._session()
            try:
                seeds = sess.execute(select(mfdb.SeedRow)).scalars().all()
                res = {}
                for r in sess.execute(select(mfdb.ResourceRow)).scalars().all():
                    res[r.resource_id] = r
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:读种子表失败:{err}", "error")
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for s in seeds:
            h = str(s.hash or "").lower()
            if not h:
                continue
            rec = self._rec_from_seed(s, names)
            # ★ 7.0.0：state/taken_by 列已退役，职务/归属从 task_id 推导
            #   （task_id 空 = 静默不在岗；非空 = 按任务类型刷流/魔力）
            if s.task_id:
                rec["taken_by"] = str(s.task_id)
                rec["state"] = self._task_state(s.task_id)
            else:
                rec["state"] = STATE_SILENT
            if s.resource_id:                      # 身份/体积/评分顺资源表（种子不存）
                rr = res.get(s.resource_id)
                if rr is not None:
                    if not rec.get("sub") and rr.identity:
                        rec["sub"] = rr.identity
                        if rr.identity_at:
                            rec.setdefault("identity_at", rr.identity_at)
                    if rec.get("size_gb") is None and rr.size_gb is not None:
                        rec["size_gb"] = rr.size_gb
                    if rec.get("rating") is None and rr.rating is not None:
                        rec["rating"] = rr.rating
            out[h] = rec
        return out

    def save_seeds(self, data: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            base = self._seed_prev if self._seed_prev else self._read_seeds()
            now = time.time()
            changed = [h for h, rec in (data or {}).items() if base.get(h) != rec]
            removed = [h for h in base if h not in (data or {})]
            if changed or removed:
                try:
                    sess = self._session()
                    try:
                        for h in changed:
                            rec = data.get(h) or {}
                            sess.merge(mfdb.SeedRow(**self.seed_row(h, rec, now)))
                            self._touch_resource(sess, rec, now)
                        if removed:
                            sess.execute(delete(mfdb.SeedRow).where(mfdb.SeedRow.hash.in_(removed)))
                        sess.commit()
                    finally:
                        sess.close()
                except Exception as err:  # noqa: BLE001
                    self._log(f"账本:写种子表失败:{err}", "error")
                    return
            self._seeds = dict(data or {})
            self._seed_prev = copy.deepcopy(self._seeds)
            self._mirror_legacy("tag_state", self._seeds)

    def _touch_resource(self, sess: Any, rec: Dict[str, Any], now: float) -> None:
        """种子的身份/体积 → 资源表（资源表仍是身份的唯一真值源）。"""
        rid = norm_res_id(rec.get("fp")).lower()
        if not rid:
            return
        patch: Dict[str, Any] = {"resource_id": rid}
        if rec.get("sub"):
            patch["identity"] = str(rec["sub"])
            patch["identity_at"] = rec.get("identity_at") or now
        if rec.get("size_gb") is not None:
            patch["size_gb"] = rec.get("size_gb")
        if rec.get("rating") is not None:
            patch["rating"] = rec.get("rating")
        if len(patch) > 1:
            sess.merge(mfdb.ResourceRow(**patch))

    # ------------------------------------------------------------ 资源账本

    def load_groups(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if self._groups is None:
                self._groups = self._read_groups()
                self._group_prev = copy.deepcopy(self._groups)
            return self._groups

    def _read_groups(self) -> Dict[str, Dict[str, Any]]:
        names = self._site_names()
        try:
            sess = self._session()
            try:
                resources = sess.execute(select(mfdb.ResourceRow)).scalars().all()
                seeds = sess.execute(select(mfdb.SeedRow)).scalars().all()
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:读资源表失败:{err}", "error")
            return {}
        members: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for s in seeds:
            if not s.resource_id:
                continue
            members.setdefault(s.resource_id, {})[str(s.hash).lower()] = self._member_rec(s, names)
        out: Dict[str, Dict[str, Any]] = {}
        for r in resources:
            if not r.grouped:                       # 只有「下完成组」的才算资源账本
                continue
            mem = members.get(r.resource_id) or {}
            if not mem:
                continue                            # 没成员 = 不是一个组（含「摘完成员」后的空壳）
            out[group_key(r.resource_id)] = self._rec_from_resource(r, mem, names)
        return out

    def save_groups(self, data: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            base = self._group_prev if self._group_prev else self._read_groups()
            now = time.time()
            changed = [g for g, rec in (data or {}).items() if base.get(g) != rec]
            removed = [g for g in base if g not in (data or {})]
            if changed or removed:
                try:
                    sess = self._session()
                    try:
                        for gid in changed:
                            rec = data.get(gid) or {}
                            rid = norm_res_id(gid).lower()
                            if not rid:
                                continue
                            sess.merge(mfdb.ResourceRow(**self.res_row(rid, rec, now)))
                            self._sync_members(sess, rid, rec.get("members") or {},
                                               (base.get(gid) or {}).get("members") or {}, now)
                        for gid in removed:                     # 整个组没了 → 资源行按引用情况保留
                            rid = norm_res_id(gid).lower()
                            if not rid:
                                continue
                            left = sess.execute(select(func.count()).select_from(mfdb.SeedRow)
                                                .where(mfdb.SeedRow.resource_id == rid)).scalar()
                            if left:
                                continue      # 还有种子指着它 → 资源行留着（身份/体积别丢）
                            sess.execute(delete(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id == rid))
                        sess.commit()
                    finally:
                        sess.close()
                except Exception as err:  # noqa: BLE001
                    self._log(f"账本:写资源表失败:{err}", "error")
                    return
            self._groups = dict(data or {})
            self._group_prev = copy.deepcopy(self._groups)
            self._mirror_legacy("tag_groups", self._groups)

    def _sync_members(self, sess: Any, rid: str, members: Dict[str, Any],
                      prev: Dict[str, Any], now: float) -> None:
        """组员 → mf_seed 组员列（组员的唯一主人；不碰台账列）。"""
        for h, m in (members or {}).items():
            if not isinstance(m, dict):
                continue
            if prev.get(h) == m and prev.get(h) is not None:
                continue                                  # 组员没变，跳过（省一写）
            sess.merge(mfdb.SeedRow(**self._member_patch(str(h), rid, m, now)))
        for h in (prev or {}):
            if h not in (members or {}):                  # 退出资源 → 摘 resource_id（7.0.0：无组员列）
                sess.execute(update(mfdb.SeedRow).where(mfdb.SeedRow.hash == str(h).lower())
                             .values(resource_id=None))

    # ------------------------------------------------------------ 收敛回填（6.1.0）

    def backfill_columns(self) -> Dict[str, int]:
        """影子 JSON（rt/mmbr/library/extra）→ 真列。幂等，**影子不删**。

        读用 ``_rec_from_seed``/``_rec_from_resource``（影子打底 + 真列覆盖），
        写用 ``seed_row``/``_member_patch``/``res_row``（真列为主 + 影子照写），
        所以「读→写」一次就是回填，且能反复跑（第二遍零差异）。
        """
        n_seed = n_mem = n_res = 0
        now = time.time()
        with self._lock:
            names = self._site_names()
            sess = self._session()
            try:
                seeds = sess.execute(select(mfdb.SeedRow)).scalars().all()
                for i, s in enumerate(seeds, 1):
                    h = str(s.hash or "").lower()
                    rec = self._rec_from_seed(s, names)
                    row = self.seed_row(h, rec, now)
                    touched = False
                    for k, v in row.items():
                        if getattr(s, k, None) != v:
                            setattr(s, k, v)
                            touched = True
                    if touched:
                        n_seed += 1
                    if s.resource_id:                     # 7.0.0：组员信息完全从 resource 推
                        m = self._member_rec(s, names)
                        patch = self._member_patch(h, s.resource_id, m, now)
                        patch.pop("updated", None)
                        touched = False
                        for k, v in patch.items():
                            if getattr(s, k, None) != v:
                                setattr(s, k, v)
                                touched = True
                        if touched:
                            n_mem += 1
                    if i % 800 == 0:
                        sess.commit()
                for r in sess.execute(select(mfdb.ResourceRow)).scalars().all():
                    rec = self._rec_from_resource(r, {}, names)
                    if rec.get("size_gb") is None:
                        rec["size_gb"] = None
                    row = self.res_row(r.resource_id, rec, now)
                    row.pop("library", None)              # 影子保持原样
                    row.pop("extra", None)
                    row.pop("grouped", None)              # 不因回填把「只有种子脸」的资源变成组
                    touched = False
                    for k, v in row.items():
                        if getattr(r, k, None) != v:
                            setattr(r, k, v)
                            touched = True
                    if touched:
                        n_res += 1
                sess.commit()
            except Exception as err:  # noqa: BLE001
                self._log(f"账本收敛:回填出错:{err}", "error")
                raise
            finally:
                sess.close()
            self._seeds = None                        # 缓存作废（下次重读）
            self._groups = None
            self._seed_prev = {}
            self._group_prev = {}
        return {"seed": n_seed, "member": n_mem, "resource": n_res, "total_seed": len(seeds)}


class SeedLedgerStore(TagStateStore):
    """``tag_state`` 的 5 表后端（API 完全不变）。"""

    def __init__(self, backend: LedgerBackend, log: Any = None) -> None:
        self.backend = backend
        super().__init__(get_data=lambda key: backend.load_seeds(),
                         save_data=lambda key, value: (backend.save_seeds(value) if key == STATE_KEY else backend.plugin.save_data(key=key, value=value)),
                         log=log)


class ResourceLedgerStore(FileGroupStore):
    """``tag_groups`` 的 5 表后端（API 完全不变）。"""

    def __init__(self, backend: LedgerBackend, log: Any = None) -> None:
        self.backend = backend
        super().__init__(get_data=lambda key: backend.load_groups() if key == GROUPS_KEY else backend.plugin.get_data(key),
                         save_data=lambda key, value: (backend.save_groups(value) if key == GROUPS_KEY else backend.plugin.save_data(key=key, value=value)),
                         log=log)


def get_backend(plugin: Any) -> LedgerBackend:
    """取本插件的读写后端（热重载后重建，数据从库里来，不丢）。"""
    be = getattr(plugin, "_ledger_backend", None)
    if be is None:
        be = LedgerBackend(plugin)
        be.ensure_schema()
        plugin._ledger_backend = be
    return be
