# -*- coding: utf-8 -*-
"""魔流 · events —— 事件订阅（传输完成等，外部事件入口）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
import time
from datetime import datetime
from typing import Any, Dict, List


from .. import common  # noqa: F401
from ..common import (
    _mf_eventmanager,
    _mf_on_event,
    site_guard,
)

# ★ 站点事件合并窗口（秒）：MP 落一次 CookieCloud 同步会连发十几条 site.updated，
#   合并成一次确认。确认动作是本地全量比对、幂等，跑多了只是白费 CPU。
SITE_EV_MERGE_SEC = 2.0


class EventsMixin:
    """events 功能集（原 MagicFlow 方法原样搬入）。"""

    # ★ 19.12.51：装饰器已移到插件主类（``__init__.py`` 的 ``MagicFlow._on_*``）。
    #   MP v3.2.2 按 handler 的**声明类名**取运行实例，声明在 mixin 上会被静默跳过。
    def _on_transfer_complete(self, event: Any = None) -> None:
        """★ 整理完成 → 写「库记」。

        权威来源：MP 广播的 ``transfer.complete``（payload 带 ``download_hash`` 与
        ``transferinfo`` 最终路径/整理方式），**不靠路径猜目录**。
        """
        try:
            _ev0 = getattr(self, "_lib_events", None)
            if not isinstance(_ev0, dict):
                _ev0 = {}
            _ev0["received"] = int(_ev0.get("received") or 0) + 1
            _ev0["last_hash"] = str((getattr(event, "event_data", None) or {}).get("download_hash") or "")[:16]
            _ev0["last_ts"] = time.time()
            self._lib_events = _ev0
        except Exception:  # noqa: BLE001
            pass
        if not common._mf_active_is(self):
            try:
                self._log("库记:忽略整理完成事件(非活跃实例)")
            except Exception:  # noqa: BLE001
                pass
            return
        if not getattr(self, "_enabled", False):
            return
        try:
            data = getattr(event, "event_data", None) or {}
            h = str((data or {}).get("download_hash") or "").strip().lower()
            if not h:
                return
            ti = (data or {}).get("transferinfo")
            if ti is not None and not bool(getattr(ti, "success", True)):
                return
            item = getattr(ti, "target_diritem", None) or getattr(ti, "target_item", None)
            path = str(getattr(item, "path", "") or "")
            if not path:
                path = str(getattr((data or {}).get("fileitem"), "path", "") or "")
            mi = (data or {}).get("mediainfo")
            media_id = str(getattr(mi, "tmdb_id", "") or getattr(mi, "media_id", "") or "")
            ttype = str(getattr(ti, "transfer_type", "") or "")
            groups = self._tag_groups()
            gid = groups.queue_library(h, path=path, media_id=media_id)
            try:
                self._tag_state().set_asset(h, sub="资源")
            except Exception:  # noqa: BLE001
                pass
            if gid:
                self._log(f"库记:整理完成 {h[:12]} → 资源 {gid[:46]} 路径 {path or '-'} 方式 {ttype or '-'}")
                # ★ 入库即转「静默-资源」（不等下一轮分拣）
                try:
                    self._promote_resource(gid)
                except Exception as err:  # noqa: BLE001
                    self._log(f"库记:入库即转失败 {h[:12]}:{err}", "warning")
            else:
                self._log(f"库记:整理完成 {h[:12]} 尚未纳管,已记待办(路径 {path or '-'})")
        except Exception as err:  # noqa: BLE001
            self._log(f"库记:处理整理完成事件失败:{err}", "warning")

    # ------------------------------------------------------------------
    # ★ 站点变更事件（2026-11-10）：把「MP 侧删站要等 30 分钟对账周期」压到秒级
    # ------------------------------------------------------------------

    # ★ 19.12.51：装饰器已移到插件主类（``__init__.py`` 的 ``MagicFlow._on_*``）。
    #   MP v3.2.2 按 handler 的**声明类名**取运行实例，声明在 mixin 上会被静默跳过。
    def _on_site_updated(self, event: Any = None) -> None:
        """MP 站点**新增/修改/CookieCloud 同步**（事件名复用 site.updated）。"""
        self._site_event_note("updated", event)

    # ★ 19.12.51：装饰器已移到插件主类（``__init__.py`` 的 ``MagicFlow._on_*``）。
    #   MP v3.2.2 按 handler 的**声明类名**取运行实例，声明在 mixin 上会被静默跳过。
    def _on_site_deleted(self, event: Any = None) -> None:
        """MP 站点删除（载荷只有 ``{site_id}``；清空全部是 ``{site_id: "*"}``）。"""
        self._site_event_note("deleted", event)

    # ★ 19.12.51：装饰器已移到插件主类（``__init__.py`` 的 ``MagicFlow._on_*``）。
    #   MP v3.2.2 按 handler 的**声明类名**取运行实例，声明在 mixin 上会被静默跳过。
    def _on_site_refreshed(self, event: Any = None) -> None:
        """MP 站点用户数据刷新（做种量/分享率），**不代表建删站**。"""
        self._site_event_note("refreshed", event)

    def _site_event_note(self, kind: str, event: Any = None) -> None:
        """站点事件统一入口：记账 → 作废缓存 → （必要时）回查确认。

        契约：
          * **只当触发器，绝不信载荷**。MP 的载荷天生残缺：建站是 ``site.updated
            {domain}``（无 site_id），删站是 ``site.deleted {site_id}``（无域名，且站点行
            已删、事后查不回域名）。所以动作固定为「作废 60s 缓存 → 回查 MP 站点表 →
            全量比对」，真值永远是 ``mp_sites()``，事件只决定「什么时候查」。
          * **不阻塞宿主**：MP 把广播事件投到线程池且吞异常，所以这里做 DB 比对拖不了
            建站/删站接口；反过来我们抛异常也不会影响 MP。
          * **时间窗合并 + 非阻塞锁**：CookieCloud 一次同步连发十几条，只确认一次；
            已有确认在跑就直接跳过 —— 它读的是最新状态，跳过不丢信息。
          * ``refreshed`` 只作废缓存就返回（与建删站无关，别拿它跑全量比对）。
        """
        data = getattr(event, "event_data", None)
        if not isinstance(data, dict):
            data = {}
        _st = getattr(self, "_site_events", None)
        if not isinstance(_st, dict):
            _st = {}
        _st["received"] = int(_st.get("received") or 0) + 1
        _st["n_" + kind] = int(_st.get("n_" + kind) or 0) + 1
        _st["last_kind"] = kind
        _st["last_data"] = {k: data.get(k) for k in ("site_id", "domain", "name", "site_url")
                            if data.get(k) is not None}
        _st["last_ts"] = time.time()
        self._site_events = _st

        # 事件在 MP 事务提交之后才发 → 此刻旧缓存必然过期
        try:
            _inv = getattr(site_guard(self), "invalidate", None)
            if callable(_inv):
                _inv()
        except Exception:  # noqa: BLE001
            pass

        if kind == "refreshed":
            return
        if not common._mf_active_is(self):
            return                      # 热重载的旧实例只记账，不动手
        if not getattr(self, "_enabled", False):
            return
        if not self._site_ev_claim():
            return
        try:
            self._site_ev_confirm(kind, data)
        finally:
            self._site_ev_release()

    def _site_ev_claim(self) -> bool:
        """抢「确认」执行权（非阻塞锁 + 时间窗合并）。成功返回 True，调用方负责 release。"""
        lk = getattr(self, "_site_ev_lock", None)
        if lk is None:
            lk = self._site_ev_lock = threading.Lock()
        if not lk.acquire(blocking=False):
            return False
        now = time.time()
        if now - float(getattr(self, "_site_ev_at", 0.0) or 0.0) < SITE_EV_MERGE_SEC:
            lk.release()
            return False
        self._site_ev_at = now
        return True

    def _site_ev_release(self) -> None:
        """释放确认锁（任何异常都不能让锁卡死）。"""
        lk = getattr(self, "_site_ev_lock", None)
        if lk is None:
            return
        try:
            lk.release()
        except Exception:  # noqa: BLE001
            pass

    def _site_ev_confirm(self, kind: str, data: Dict[str, Any]) -> None:
        """回查 MP 站点表 + 全量比对（幂等）。只读比对 + 复用既有 ``site_deleted_mark``。"""
        from .siteops import _as_int, dom_norm, site_deleted_mark, site_references

        t0 = time.time()
        rec: Dict[str, Any] = {"kind": kind, "at": t0}
        try:
            r = site_deleted_mark(self) or {}
            marked = int(r.get("marked") or 0)
            cleared = int(r.get("cleared") or 0)
            rec["mark"] = {k: r.get(k) for k in ("ok", "marked", "cleared", "skipped", "error")
                           if r.get(k) not in (None, 0, "", False)}
            names = [str(x) for x in (r.get("sites") or [])][:5]
            if marked or cleared:
                self._log(
                    f"站点事件({kind})：MP 侧已删 {marked} 个已标记 / {cleared} 个已复活"
                    + (f"（{'、'.join(names)}）" if names else ""),
                    "warning" if marked else "info",
                )
            elif kind == "deleted" and str(data.get("site_id")) != "*":
                # 接不住的信号：MP 说删了，但台账里没有能对上这个 id 的行
                # （删站事件不带域名，站点行又已消失 → 只能靠 mp_site_id 认）
                self._log(
                    f"站点事件(deleted)：MP 报告 site_id={data.get('site_id')} 已删，"
                    f"但台账没有能对上该 id 的行（事件载荷无域名，需先补 mp_site_id/别名表）",
                    "warning",
                )

            # 新建站可见性：MP 有、所有站点引用都认不出 → 只记账，**不建行**
            mp = site_guard(self).mp_sites() or {}
            refs = site_references(self) or {}
            known_ids, known_doms = set(), set()
            for ent in refs.values():
                sid = _as_int((ent or {}).get("mp_site_id"))
                if sid:
                    known_ids.add(sid)
                d = dom_norm((ent or {}).get("domain"))
                if d:
                    known_doms.add(d)
            fresh: List[Dict[str, Any]] = []
            for sid, v in (mp or {}).items():
                if sid in known_ids:
                    continue
                d = dom_norm((v or {}).get("domain"))
                if d and d in known_doms:
                    continue
                fresh.append({"mp_site_id": sid, "domain": d,
                              "name": str((v or {}).get("name") or "")})
            rec["mp_total"] = len(mp or {})
            if fresh:
                rec["new_count"] = len(fresh)
                rec["new_sites"] = fresh[:20]
                _nm = "、".join(f"{x['name'] or x['domain']}(id={x['mp_site_id']})" for x in fresh[:5])
                self._log(f"站点事件({kind})：MP 新增 {len(fresh)} 个站点尚未纳管（{_nm}）", "info")
        except Exception as err:  # noqa: BLE001
            rec["error"] = str(err)[:200]
            self._log(f"站点事件确认失败({kind}):{err}", "warning")
        rec["ms"] = int((time.time() - t0) * 1000)
        _st = getattr(self, "_site_events", None)
        if not isinstance(_st, dict):
            _st = {}
        _st["last_confirm"] = rec
        self._site_events = _st

    @staticmethod
    def _event_handlers(etype: Any) -> List[Any]:
        """从事件总线内部取出某事件的订阅列表（诊断用，尽力而为）。"""
        em = _mf_eventmanager
        if em is None:
            return []
        cands = []
        for attr in ("_EventManager__dispatcher", "_dispatcher"):
            obj = getattr(em, attr, None)
            if obj is not None:
                cands.append(obj)
        cands.append(em)
        for obj in cands:
            for rattr in ("_registry", "registry", "_EventRegistry__registry"):
                reg = getattr(obj, rattr, None)
                if reg is None:
                    continue
                for m in ("broadcast_snapshot", "snapshot"):
                    fn = getattr(reg, m, None)
                    if callable(fn):
                        try:
                            return list(fn(etype))
                        except Exception:  # noqa: BLE001
                            continue
        return []
