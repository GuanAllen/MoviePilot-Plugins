# -*- coding: utf-8 -*-
"""魔流 · hr —— H&R 义务守护（强挂/松绑、结清摘标）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple


from ..tags import (
    MARK_REUSE,
    MARK_HR,
    SUB_PLAIN,
    SUB_RESOURCE,
    SUB_NEW,
    DUTY_STATES,
    STATE_HR,
    STATE_SILENT,
    identity_of,
    is_library_asset,
    is_reuse_copy,
    retag,
    tag_for,
)
from .hrbills import (
    HR_BILLS_ENFORCE,
    BILL_STATE_ACTIVE,
    BILL_STATE_SETTLED,
    BILL_STATE_VOID,
    RULE_SITE_HR,
    RULE_HIT_AND_RUN,
)
from ..downloader_ops import seed_hours_for_hr
from ..common import hr_incomplete, hr_complete_ratio_of


class HrMixin:
    """hr 功能集（原 MagicFlow 方法原样搬入）。"""

    def _resource_source_index(self) -> Dict[str, Tuple[str, str, bool, List[Dict[str, Any]]]]:
        """``{种子 hash: (来源站名, 来源种 hash, 主账单已结清?, 该资源全部账单)}`` —— 资源账（债）反查索引，30s TTL。

        ★ 9.0.0：H&R 债挂在**资源**上（``mf_resource`` 的 ``source_site_id``/``source_hash``），
        本索引把「某个种 → 它所属资源的来源站 / 来源种」摊平，供 ``_hr_obligation`` 逐种查。
        ★ 10.0.0：账单**按站分账**（``hrs``）。同一资源可在多个站各有 H&R 债 → 每张账单的
        ``by_hash``（该站的还债名片）映射到 (该站, 该名片种, 该账单是否结清)；没有自己账单的
        成员落到**主账单**（来源站/来源种）。
        """
        now = time.time()
        cache = getattr(self, "_hr_residx_cache", None)
        if isinstance(cache, tuple) and (now - float(cache[0] or 0)) < 30.0:
            return cache[1]
        out: Dict[str, Tuple[str, str, bool, List[Dict[str, Any]]]] = {}
        try:
            _items = self._tag_groups().items() or {}
        except Exception:  # noqa: BLE001
            _items = {}
        for _gid, rec in _items.items():
            if not isinstance(rec, dict):
                continue
            members = rec.get("members") or {}
            if not members:
                continue
            src_hash = str(rec.get("source_hash") or "").strip().lower()
            src_site = str(rec.get("source_site") or "").strip()
            bills = rec.get("hrs") or {}
            if not isinstance(bills, dict) or not bills:
                _h0 = rec.get("hr")
                bills = {str((_h0 or {}).get("site") or "_"): _h0} if isinstance(_h0, dict) and _h0 else {}
            _blist = [dict(b) for b in bills.values() if isinstance(b, dict)]
            _main = next((b for b in _blist
                          if str(b.get("by_hash") or "").strip().lower() == src_hash and src_hash), None)
            if _main is None and _blist:
                _main = _blist[0]
            _main_site = str((_main or {}).get("site") or "").strip() or src_site
            _main_hash = str((_main or {}).get("by_hash") or "").strip().lower() or src_hash
            _main_settled = bool((_main or {}).get("settled"))
            _own: Dict[str, Dict[str, Any]] = {}
            for b in _blist:
                _bh = str(b.get("by_hash") or "").strip().lower()
                if _bh:
                    _own[_bh] = b
            for _mh in members:
                mh = str(_mh).strip().lower()
                b = _own.get(mh)
                if b:
                    out[mh] = (str(b.get("site") or "").strip() or _main_site, mh,
                               bool(b.get("settled")), _blist)
                else:
                    out[mh] = (_main_site, _main_hash, _main_settled, _blist)
        # ★ 别把「空索引」缓存住：热重载/冷缓存瞬间 items() 可能为空 →
        #   若缓存空集，会在 30s 内把一切都当「无资源」放行（闸门就形同虚设）。
        if out:
            self._hr_residx_cache = (now, out)
        return out

    def _hr_domain(self, site: str, torrent: Any) -> str:
        """尽量解出该种的**域名**：传入站点名 → 账本 site → 标签推断 → tracker。"""
        def _norm(x: Any) -> str:
            s = str(x or "").strip()
            if not s:
                return ""
            try:
                return str(self._site_domain_by_name(s) or s).strip().lower()
            except Exception:  # noqa: BLE001
                return s.lower()
        dom = _norm(site)
        if dom:
            return dom
        _h = str(getattr(torrent, "hash", "") or "").strip().lower()
        if _h:
            try:
                rec = dict(self._tag_state() or {}).get(_h) or {}
                dom = _norm(rec.get("site"))
            except Exception:  # noqa: BLE001
                dom = ""
        if not dom:
            try:
                dom = _norm(self._torrent_site_name(list(getattr(torrent, "tags", None) or []), ""))
            except Exception:  # noqa: BLE001
                dom = ""
        if dom:
            return dom
        try:
            tr = str(getattr(torrent, "tracker", "") or "").strip().lower()
            return tr.split("://")[-1].split("/")[0].split(":")[0].strip()
        except Exception:  # noqa: BLE001
            return ""

    def _hr_due_hours(self, need: float) -> float:
        """★ 14.0.0 **统一口径**：H&R「做满」阈值 = ``need_h + 安全垫(margin)``。

        账单状态机（``features/hrbills.py::_hr_bill_deadline``/结清判定）用 ``need_h + margin`` 判结清；
        闸门 / 清种候选 / 静默结清（本文件 ``_hr_obligation*`` + ``silent._silent_hr_clear``）
        必须**同源**——否则会出现「账单仍 active（欠 H&R）、闸门已判不欠 → 删种」的假违约
        （2026-10-07 CARPT 3 条 ``plugin_deleted`` + ``gate_bug`` 的根因）。
        """
        try:
            margin = float(self._hr_margin_hours() or 0.0)
        except Exception:  # noqa: BLE001
            margin = 0.0
        return float(need or 0.0) + max(0.0, margin)

    def _hr_incomplete_of(self, site: str, torrent: Any) -> bool:
        """★ 15.5.1：该种「未达完成度」？（阈值 = 站点覆盖 > 全局默认；见 ``common.hr_incomplete``）。

        站点域从 ``_hr_domain(site, torrent)`` 推（推不出来 → 用全局默认）。
        """
        try:
            dom = self._hr_domain(site, torrent)
        except Exception:  # noqa: BLE001
            dom = ""
        try:
            return hr_incomplete(torrent, hr_complete_ratio_of(self, dom))
        except Exception:  # noqa: BLE001
            return False

    def _hr_obligation_by_seed(self, site: str, torrent: Any) -> Tuple[bool, float, float, str]:
        """种子级兜底：该种**自己所在站点**明确有 H&R → 按它自己的做种时长判。

        ★ 只有站点规则**明确 True**（或种子自带 H&R 标记）才算；站点规则未知 → **绝不猜**
        （2026-10-05：YemaPT 那种误判就是「未知保守」造出来的）。

        ★ 11.11.1：复用/补源副本（非真实下载）→ 本站不欠 H&R。
        """
        # ★ 15.5.0（Master 16:19「没有下完的内容没有 h&r」）：未完成 → 无 H&R 义务。
        if self._hr_incomplete_of(site, torrent):
            return False, 0.0, 0.0, "未下载完成(无 H&R 义务)"
        try:
            _tags = [str(x) for x in (getattr(torrent, "tags", None) or [])]
            if is_reuse_copy(_tags):
                return False, 0.0, 0.0, "复用/补源副本(非真实下载)"
        except Exception:  # noqa: BLE001
            pass
        dom = self._hr_domain(site, torrent)
        if not dom:
            return False, 0.0, 0.0, "站点未知"
        try:
            hr_flag = self._site_hr_flag(dom)
        except Exception:  # noqa: BLE001
            hr_flag = None
        try:
            thr = True if bool(getattr(torrent, "hit_and_run", False)) else None
        except Exception:  # noqa: BLE001
            thr = None
        if not (hr_flag is True or thr is True):
            return False, 0.0, 0.0, f"本站({dom})无H&R规则"
        try:
            need = float(self._crossseed_seed_need_hours(dom) or 0.0)
        except Exception:  # noqa: BLE001
            need = 0.0
        if need <= 0:
            try:
                need = float(self._crossseed_seed_hours_detail(dom)[0] or 0.0)
            except Exception:  # noqa: BLE001
                need = 0.0
        if need <= 0:
            need = 24.0
        try:
            seeded = seed_hours_for_hr(torrent)
        except Exception:  # noqa: BLE001
            seeded = 0.0
        return (seeded + 1e-6 < self._hr_due_hours(need)), float(need), seeded, f"本站规则({dom})"

    def _hr_obligation(self, site: str, torrent: Any, snap: Any = None) -> Tuple[bool, float, float, str]:
        """该种是否**欠 H&R**：``(欠?, 要求小时, 已挂小时, 来源)``。

        ★ 性能（P0）：``snap`` = 本轮已拉好的 qB 全量快照（``{hash: TorrentInfo}``）。
        调用方在同一轮内把这份快照**显式传下来**即可复用（不再逐种重拉）；
        不传（默认 None）则照旧自己拉 —— 向后兼容，旧调用点无需全改。

        ★ 9.0.0（Master 2026-10-05「H&R 记录在资源表 · 用**来源站种子**的 seedingtime 判断」）：
        主口径 = 债挂在**资源**上（``mf_resource.source_site_id``/``source_hash``），还债靠**来源站那个种**：
        ``种 → 资源 → 来源站 + 来源种 → 来源站规则 hr → 来源种在 qB 的 seeding_time``。

        ★ 9.0.1 兜底（2026-10-05 血泪）：资源账可能缺、或来源站记错（实测 CARPT 的种资源来源
        记成了「咖啡」→ 判不欠 → 被刷魔「低效换种」删掉，而站点 myhr 页明确列它欠 H&R）。
        所以：**资源级说欠 → 欠**；否则再按**该种自己所在站点**明确有 H&R 且自己没挂够 → 也欠。
        站点规则未知 → 不猜（两种口径都不猜）。

        ★ 11.11.1：复用/补源副本（非真实下载）→ 三路（资源/账单/种子级）全部短路，不欠。

        ★ 14.0.0：所有四路的「做满」比较统一走 ``_hr_due_hours(need) = need + margin``，
        与账单状态机同源（避免「账单还欠、闸门已放行」的假违约）。
        """
        # ★ 15.5.0（Master 16:19「没有下完的内容没有 h&r」）：未完成 → 无 H&R 义务。
        #   未下载完成 = 未达站点 H&R 触发阈（阈值可站点级覆盖），三/四路都不算欠。
        if self._hr_incomplete_of(site, torrent):
            return False, 0.0, 0.0, "未下载完成(无 H&R 义务)"
        # ★ 11.11.1：复用/补源副本不继承资源的来源站 H&R 债（副本自己不是真实下载）。
        try:
            _tags = [str(x) for x in (getattr(torrent, "tags", None) or [])]
            if is_reuse_copy(_tags):
                return False, 0.0, 0.0, "复用/补源副本(非真实下载)"
        except Exception:  # noqa: BLE001
            pass
        _h = str(getattr(torrent, "hash", "") or "").strip().lower()
        src_site, src_hash, settled = "", "", False
        _bills: List[Dict[str, Any]] = []
        try:
            _ent = self._resource_source_index().get(_h)
            if _ent:
                src_site, src_hash, settled = _ent[0], _ent[1], _ent[2]
                _bills = list(_ent[3] or []) if len(_ent) > 3 else []
        except Exception:  # noqa: BLE001
            pass
        _r: Tuple[bool, float, float, str] = (False, 0.0, 0.0, "")
        if src_hash and not settled:
            site_ = src_site or site
            dom = self._site_domain_by_name(site_) or str(site_ or "")
            _src_t = None
            if snap is not None:
                _src_t = snap.get(src_hash)
            else:
                try:
                    _src_t = (self._tag_all_torrents() or {}).get(src_hash)
                except Exception:  # noqa: BLE001
                    _src_t = None
                _note = getattr(self, "_decision_round_note_pull", None)
                if callable(_note):
                    _note()
            try:
                thr = True if (_src_t is not None and bool(getattr(_src_t, "hit_and_run", False))) else None
            except Exception:  # noqa: BLE001
                thr = None
            try:
                protect, hours, src = self._crossseed_hr_decision(dom, thr)
            except Exception:  # noqa: BLE001
                protect, hours, src = False, 0.0, "err"
            if protect:
                need = 0.0
                try:
                    need = float(self._crossseed_seed_need_hours(dom) or 0.0)
                except Exception:  # noqa: BLE001
                    need = 0.0
                if need <= 0:
                    need = float(hours or 0.0)
                try:
                    seeded = seed_hours_for_hr(_src_t) if _src_t is not None else 0.0
                except Exception:  # noqa: BLE001
                    seeded = 0.0
                if need > 0:
                    _r = (seeded + 1e-6 < self._hr_due_hours(need), float(need), seeded, f"来源站/{src}")
            else:
                _r = (False, 0.0, 0.0, src)
        if _r[0]:
            return _r
        # ★ 10.0.0：资源上「其它站的未结账单」也要拦（同一内容被多站下载 → 每站各欠一份，互不顶替）
        for _b in (_bills or []):
            try:
                if _b.get("settled"):
                    continue
                _bs = str(_b.get("site") or "").strip()
                if not _bs:
                    continue
                _bd = self._site_domain_by_name(_bs) or _bs
                _bp, _bh2, _bsrc = self._crossseed_hr_decision(_bd, None)
                if not _bp:
                    continue
                try:
                    _bneed = float(_b.get("need_hours") or _b.get("required_hours") or _bh2 or 0.0)
                except (TypeError, ValueError):
                    _bneed = 0.0
                if _bneed <= 0:
                    _bneed = 24.0
                _bseed = float(_b.get("seeded_seconds") or 0.0) / 3600.0
                if _bseed + 1e-6 < self._hr_due_hours(_bneed):
                    return True, float(_bneed), float(_bseed), f"账单({_bs})/{_bsrc}"
            except Exception:  # noqa: BLE001
                continue
        # ★ 11.0.0 第二阶段：第三来源 —— 自下载 H&R 账单（``hr_bills.json``）。
        #   只**增**保护：active 且规则已知（非 unknown）且没挂够 → 欠；
        #   settled / void / pending / unknown → 本条不产生欠债（未知站不保护，Master 红线）。
        #   账单读取出任何异常 → 视为「无账单」，回退原判定，绝不能让保护变少或闸门抛错。
        if HR_BILLS_ENFORCE:
            try:
                _hrbill = self._hrbills_store().get(_h)
                if isinstance(_hrbill, dict) \
                        and str(_hrbill.get("state") or "") == BILL_STATE_ACTIVE \
                        and str(_hrbill.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                    _bneed = float(_hrbill.get("need_h") or 24.0)
                    _bseed = float(_hrbill.get("seeded_h") or 0.0)
                    if _bseed + 1e-6 < self._hr_due_hours(_bneed):
                        return True, _bneed, _bseed, "hrbill"
            except Exception:  # noqa: BLE001
                pass
        # 兜底（种子级）
        _s = self._hr_obligation_by_seed(site, torrent)
        if _s[0]:
            return _s
        if src_hash and settled:
            return False, 0.0, 0.0, "账单已结清"
        if not src_hash:
            return _s if _s[3] else (False, 0.0, 0.0, "无资源/无来源账")
        return _r if _r[3] else (False, 0.0, 0.0, "不欠")

    def _hr_owed_by_site(self) -> Dict[str, Dict[str, float]]:
        """各站点「欠 H&R」的已完成种子数 / 还需小时数（300s 缓存）。

        站点级口径（H&R 是**账号级**风险，不按任务切分）：同一站点所有种子
        （含静默池 / 跨站来源份）一起统计。

        ★ 性能（6.1.4）：这是**展示路径**（只给 /status 算数字），却曾经：
          ① 用阻塞式 `_tag_all_torrents()` 拉快照 —— 快照一过期，9 个任务统计线程
             全堵在 qB 全量重拉上（实测每任务 ~3.5s、一天 1300+ 条「统计任务慢」告警）；
          ② 缓存过期瞬间 9 个线程同时重算（重复劳动 9 份）。
          现在：改用 stale-while-revalidate 的展示快照 + **单飞锁**（同一时刻只算一次）。
        """
        now = time.time()
        cache = getattr(self, "_hr_owed_cache", None)
        if isinstance(cache, dict) and (now - float(cache.get("ts", 0) or 0)) < 300:
            return cache.get("data") or {}
        lock = getattr(self, "_hr_owed_lock", None)
        if lock is None:
            lock = self._hr_owed_lock = threading.Lock()
        with lock:                                   # 单飞：并发统计线程只算一次
            now = time.time()
            cache = getattr(self, "_hr_owed_cache", None)
            if isinstance(cache, dict) and (now - float(cache.get("ts", 0) or 0)) < 300:
                return cache.get("data") or {}
            _t0 = time.time()
            out: Dict[str, Dict[str, float]] = {}
            try:
                snap = self._tag_snapshot_view() or {}      # ★ 展示用快照：stale 先返回
                ledger = dict(self._tag_state().items() or {})
            except Exception:
                snap, ledger = {}, {}
            try:
                cssrc = dict(self._crossseed_sources().items() or {})
            except Exception:
                cssrc = {}
            # 只算「魔流相关」的种（账本 / 跨站来源份），与 H&R 巡检同口径（不再读标签）
            scope = {str(x).strip().lower() for x in set(ledger) | set(cssrc)}
            for h, t in snap.items():
                try:
                    if float(getattr(t, "progress", 0) or 0) < 0.999:
                        continue
                    if str(h).lower() not in scope:
                        continue
                    rec = ledger.get(str(h).lower()) or {}
                    tags = [str(x) for x in (getattr(t, "tags", None) or [])]
                    site = str(rec.get("site") or "").strip() or self._torrent_site_name(tags, "")
                    if not site:
                        continue
                    obl, need, seeded, _src = self._hr_obligation(site, t)
                    if not obl:
                        continue
                    slot = out.setdefault(site, {"n": 0, "h": 0.0})
                    slot["n"] = int(slot["n"]) + 1
                    slot["h"] = float(slot["h"]) + max(0.0, float(need or 0.0) - float(seeded or 0.0))
                except Exception:
                    continue
            data = {k: {"n": int(v["n"]), "h": round(float(v["h"]), 1)} for k, v in out.items()}
            self._hr_owed_cache = {"ts": time.time(), "data": data}
            _ms = (time.time() - _t0) * 1000.0
            if _ms > 300:
                self._dbg(f"H&R 欠账扫描 {_ms:.0f}ms（站点 {len(data)}）")
            return data

    def _hr_guard_tick(self, apply: bool = True, limit: int = 0, snap: Any = None) -> Dict[str, Any]:
        """★ H&R **统一管理**（Master 2026-09-28 01:37）：

        ① 欠 H&R 的种 → 统一**强挂保种**（``force_start``，绕过队列）拉起继续挂；
        ② 非义务却仍强制挂种（3.15.0 残留 / 结清后没松绑）→ 松绑降回普通做种；
        ③ H&R 状态已**账本化**（7.0.0）：``魔流-H&R`` 标签不再写/摘（真值源在账本 + 站点规则），
           标签仅作展示投影 / 历史可读。

        只处理**已完成**的种：没下完的没有 H&R 义务（未完成删除不计 H&R），
        未下完的跨站来源份归「跨站池」/辅种归校验流程管。
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "checked": 0, "completed": 0,
                               "obligated": 0, "tagged": 0, "resumed": 0,
                               "cleared": 0, "released": 0, "failed": 0,
                               "items": [], "release": []}
        from ..common import HR_HOST_TASK_ID  # 惰性导入（离线测试不碰 common）
        # ★ P0：本轮只拉一次 qB 快照（同一轮内复用）；不传则自拉并计数（向后兼容）
        _beg = getattr(self, "_decision_round_begin", None)
        if callable(_beg):
            _beg("hr_guard")
        if snap is None:
            snap = self._tag_all_torrents() or {}
            _note = getattr(self, "_decision_round_note_pull", None)
            if callable(_note):
                _note()
        if not snap:
            rep["reason"] = "无快照"
            _end = getattr(self, "_decision_round_end", None)
            if callable(_end):
                _end()
            return rep
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        # ★ 「家人已有身份」→ 不贴（Master 2026-09-30 01:34）：
        #   同**资源**在本池已经有拿到身份的（资源/普通）→ 新来的跟家人走，不隔离。
        fam_gids: set = set()
        try:
            _files = self._tag_groups()
            for _h2, _r2 in ledger.items():
                if str(_r2.get("sub") or "") not in (SUB_RESOURCE, SUB_PLAIN):
                    continue
                try:
                    _g2 = str(_files.group_of(_h2) or "")
                except Exception:  # noqa: BLE001
                    _g2 = ""
                if _g2:
                    fam_gids.add(_g2)
        except Exception:  # noqa: BLE001
            pass
        # ★ 11.11.0：只处理 __hr_host__（职务 保种）的种；跨站来源份由 _crossseed_sources_tick 管，
        #   静默池全 paused（无 H&R 例外），不再扫 ledger 全量。
        scope = [h for h, _r in ledger.items()
                 if str((_r or {}).get("taken_by") or "") == HR_HOST_TASK_ID]
        cap = int(limit or 0)
        to_tag: List[str] = []
        to_start: List[str] = []
        to_clear: List[str] = []
        to_release: List[str] = []
        for hh in sorted(scope):
            if cap and rep["checked"] >= cap:
                break
            hh = str(hh or "").strip().lower()
            t = snap.get(hh)
            if t is None:
                continue
            rep["checked"] = int(rep["checked"]) + 1
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            has_tag = MARK_HR in tags
            try:
                done = float(getattr(t, "progress", 0) or 0) >= 0.999
            except (TypeError, ValueError):
                done = False
            if not done:
                continue  # 未完成：无 H&R 义务（另由跨站池/校验流程管）
            rep["completed"] = int(rep["completed"]) + 1
            rec = ledger.get(hh) or {}
            site = str(rec.get("site") or "").strip() or self._torrent_site_name(tags, "")
            obl, need, seeded, src = self._hr_obligation(site, t, snap=snap)
            if not obl:
                if has_tag:
                    to_clear.append(hh)
                # ★ 非义务却还「强制挂种」（3.15.0 残留 / 结清后没松绑）→ 松绑，降回普通做种
                st_now = str(getattr(t, "state", "") or "").strip().lower()
                if st_now == "forcedup" and any(str(x).startswith("魔流-") for x in tags):
                    to_release.append(hh)
                    rep["release"].append({
                        "hash": hh[:12], "site": site, "state": st_now,
                        "tagged": bool(has_tag),
                        "name": str(getattr(t, "title", "") or "")[:50],
                    })
                continue
            rep["obligated"] = int(rep["obligated"]) + 1
            # ★ 检查站语义（Master 2026-09-30 01:34「h&r 是过检查站给贴的」）：
            #   ① 家人已有身份（同资源在本池已是 资源/普通）→ 不贴；已贴的摘掉。
            #   ② 在岗（带职务标签）不贴 —— 等回池（进池/回池当场 + 每小时兜底）再过检查站。
            try:
                _g = str(self._tag_groups().group_of(hh) or "")
            except Exception:  # noqa: BLE001
                _g = ""
            if _g and _g in fam_gids:
                rep["family"] = int(rep.get("family") or 0) + 1
                if has_tag:
                    to_clear.append(hh)
                continue
            # ★ 账本判在岗（职务=刷流/魔力）；标签只作展示投影
            #   ★ 11.11.0：保种( STATE_HR )是 __hr_host__ 的职务，欠债要强挂，**不能**当「在岗」跳过
            _duty = str(rec.get("state") or "")
            if _duty in DUTY_STATES and _duty != STATE_HR and not has_tag:
                rep["on_duty"] = int(rep.get("on_duty") or 0) + 1
                continue
            rep["items"].append({
                "hash": hh[:12], "site": site, "need_h": round(need, 1),
                "seeded_h": round(seeded, 1), "src": src,
                "state": str(getattr(t, "state", "") or ""), "tagged": has_tag,
            })
            if not has_tag:
                to_tag.append(hh)
            st = str(getattr(t, "state", "") or "").strip().lower()
            # 「没到时间」但被暂停/排队/停止 → 强行拉起来（checking* 是校验中，别动）
            if st in ("paused", "pausedup", "pauseddl", "stopped", "stoppedup", "stoppeddl",
                      "queued", "queuedup", "queueddl") or st.startswith("paused") \
                    or st.startswith("queued") or st.startswith("stopped"):
                if not (MARK_REUSE in tags and not done):
                    to_start.append(hh)
        if apply and to_tag:
            # ★ 7.0.0 标签退役：不写 MARK_HR 标签（H&R 状态账本化、账本是真值源）。
            #   保留``to_tag``统计/``has_tag``展示投影；老种身上的旧标签无害，仅历史可读。
            rep["tagged"] = len(to_tag)
            if to_tag:
                self._log(f"H&R:打标已退役（账本化）{len(to_tag)} 个", "info")
        if apply and to_start:
            try:
                dl = self._get_downloader("qbittorrent")
                fn = getattr(dl, "force_start_torrents", None) if dl is not None else None
                if callable(fn):
                    cnt, err = fn(to_start)
                elif dl is not None:
                    cnt, err = dl.resume_torrents(to_start)
                else:
                    cnt, err = 0, "无下载器"
                rep["resumed"] = int(cnt or 0)
                if err:
                    self._log(f"H&R:强拉失败 {err}", "warning")
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"H&R:强拉异常:{err}", "warning")
        if apply and to_clear:
            # ★ 7.0.0 标签退役：不再主动摘 MARK_HR 标签（不再写新标，老标仅历史可读）。
            rep["cleared"] = len(to_clear)
            if to_clear:
                self._log(f"H&R:摘标已退役（账本化）{len(to_clear)} 个", "info")
        if apply and to_release:
            # ★ 取消强挂（enable=False）：降回普通做种（不暂停、不删，只是不再强制绕过队列）
            _by_dl: Dict[str, List[str]] = {}
            for hh in to_release:
                _dn = str((ledger.get(hh) or {}).get("downloader") or "qbittorrent")
                _by_dl.setdefault(_dn, []).append(hh)
            _tot = 0
            for _dn, _hs in _by_dl.items():
                try:
                    dl = self._get_downloader(_dn)
                    fn = getattr(dl, "release_force_start_torrents", None) if dl is not None else None
                    if callable(fn):
                        cnt, err = fn(_hs)
                        _tot += int(cnt or 0)
                        if err:
                            self._log(f"H&R:松绑失败({_dn}) {err}", "warning")
                except Exception as err:  # noqa: BLE001
                    rep["failed"] = int(rep["failed"]) + 1
                    self._log(f"H&R:松绑异常({_dn}):{err}", "warning")
            rep["released"] = _tot
        if apply and (rep["tagged"] or rep["resumed"] or rep["cleared"] or rep["released"]):
            _skip = ""
            if rep.get("family") or rep.get("on_duty"):
                _skip = f"（家人已有身份跳过 {rep.get('family', 0)} · 在岗跳过 {rep.get('on_duty', 0)}）"
            self._log(
                f"魔流:H&R 统一管理:欠 H&R {rep['obligated']} 个 → 打标 {rep['tagged']} · "
                f"强拉起 {rep['resumed']} · 结清摘标 {rep['cleared']} · 松绑 {rep['released']}{_skip}"
            )
        _end = getattr(self, "_decision_round_end", None)
        if callable(_end):
            _end()
        return rep

    # ------------------------------------------------------- 11.11.0 H&R 保种宿主 __hr_host__

    def _hr_host_assign(self, hashes: Any, *, reason: str = "") -> int:
        """把欠 H&R 的种挂到 __hr_host__（职务 保种）：贴职务标签 + 写账本（taken_by=__hr_host__）。

        幂等：已 taken_by=__hr_host__ 的种不重复写。不 force_start（保挂由 hr_host()/ _hr_guard_tick 负责）。
        """
        from ..common import HR_HOST_TASK_ID, SILENT_HR_SPLIT_ENABLED  # 惰性导入（离线测试不碰 common）
        if not SILENT_HR_SPLIT_ENABLED:
            return 0
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
            if str(_rec0.get("taken_by") or "") == HR_HOST_TASK_ID:
                continue  # 已在保种宿主
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            _sub = str(_rec0.get("sub") or "") or _i_sub \
                or (SUB_RESOURCE if is_library_asset(_rec0) else SUB_NEW)
            _sub = _sub or SUB_NEW
            _site = str(_rec0.get("site") or "") or _i_site or self._torrent_site_name(cur, "")
            new_tags = retag(cur, site=_site, state=STATE_HR, sub=_sub) \
                if cur else [tag_for(_site, STATE_HR, _sub)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {
                    "site": _site, "state": STATE_HR, "sub": _sub,
                    "taken_by": HR_HOST_TASK_ID, "task": "H&R保种",
                    "taken_at": _now, "lease_until": 0,
                    "title": str(getattr(live, "title", "") or "") if live is not None else "",
                })
            except Exception:  # noqa: BLE001
                pass
            n += 1
        # ★ 挂上即做种（保挂 H&R）：入池即暂停的种被迁进保种宿主，立即 force_start 继续挂
        if n:
            try:
                _fn2 = getattr(downloader, "force_start_torrents", None)
                if callable(_fn2):
                    _fn2(hs)
                else:
                    downloader.resume_torrents(hs)
            except Exception as err:  # noqa: BLE001
                self._log(f"H&R保种:强挂失败:{err}", "warning")
        return n

    def _hr_host_release(self, hashes: Any, *, reason: str = "") -> int:
        """结清/作废/规则不欠后，把种从 __hr_host__ 释放回静默（退保种职务 + pause）。"""
        from ..common import HR_HOST_TASK_ID  # 惰性导入（离线测试不碰 common）
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
            if str(_rec.get("taken_by") or "") not in ("", HR_HOST_TASK_ID):
                continue
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _sub = str(_rec.get("sub") or "") or SUB_PLAIN
            _site = str(_rec.get("site") or "") or self._torrent_site_name(cur, "")
            new_tags = retag(cur, site=_site, state=STATE_SILENT, sub=_sub) \
                if cur else [tag_for(_site, STATE_SILENT, _sub)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {"site": _site, "state": STATE_SILENT, "sub": _sub,
                               "taken_by": "", "lease_until": 0,
                               "hr_released_at": _now, "hr_released_reason": str(reason or "")})
            except Exception:  # noqa: BLE001
                pass
            n += 1
        if n:
            try:
                self._silent_pause_gate(hs)
            except Exception:  # noqa: BLE001
                pass
        return n

    def hr_host(self) -> Dict[str, Any]:
        """★ 11.11.0：__hr_host__ 常驻 worker —— 保挂 H&R + 结清释放。

        只处理 taken_by=__hr_host__（职务 保种）的种：
        ① 欠 H&R → force_start（保挂）；② 已结清（seed 时长达标）/ 账单 settled/void → 释放回静默（pause）。
        种消失的违约由 ``_hrbills_tick`` 转 breached，这里不重复处理。
        """
        from ..common import SILENT_HR_SPLIT_ENABLED, HR_HOST_TASK_ID  # 惰性导入（离线测试不碰 common）
        if not SILENT_HR_SPLIT_ENABLED:
            return {"enabled": False}
        rep: Dict[str, Any] = {"assigned": 0, "migrated": 0, "resumed": 0, "released": 0}
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            return rep
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        store = None
        try:
            store = self._hrbills_store()
        except Exception:  # noqa: BLE001
            store = None
        # ① 统一迁移（堵洞）：账本里欠 H&R、不在岗（非刷流/魔力）、未 taken_by=__hr_host__ → 保种。
        #    覆盖 reseed/ondemand/crossseed 等入池口只补了 pause 的欠债种，保证「静默全 paused」∧「欠债照挂」。
        to_migrate: List[str] = []
        for hh, rec in ledger.items():
            _st = str((rec or {}).get("state") or "")
            if _st in DUTY_STATES and _st != STATE_HR:
                continue  # 在岗（刷流/魔力）→ 任务在挂，不迁移
            if str((rec or {}).get("taken_by") or "") == HR_HOST_TASK_ID:
                continue  # 已在保种宿主
            t = snap.get(hh)
            if t is None:
                continue
            site = str((rec or {}).get("site") or "") or self._torrent_site_name(getattr(t, "tags", None), "")
            try:
                if bool(self._hr_obligation(site, t, snap=snap)[0]):
                    to_migrate.append(hh)
            except Exception:  # noqa: BLE001
                continue
        if to_migrate:
            rep["migrated"] = int(self._hr_host_assign(to_migrate, reason="欠 H&R 迁移") or 0)
        to_resume: List[str] = []
        to_release: List[str] = []
        for hh, rec in ledger.items():
            if str(rec.get("state") or "") != STATE_HR:
                continue
            rep["assigned"] = int(rep["assigned"]) + 1
            t = snap.get(hh)
            if t is None:
                continue  # 消失 → 由 _hrbills_tick 违约；账本稍后对账
            site = str(rec.get("site") or "") or self._torrent_site_name(getattr(t, "tags", None), "")
            try:
                obl = bool(self._hr_obligation(site, t, snap=snap)[0])
            except Exception:  # noqa: BLE001
                obl = False
            bstate = ""
            if store is not None:
                try:
                    bstate = str((store.get(hh) or {}).get("state") or "")
                except Exception:  # noqa: BLE001
                    bstate = ""
            if not obl or bstate in (BILL_STATE_SETTLED, BILL_STATE_VOID):
                to_release.append(hh)
                continue
            st = str(getattr(t, "state", "") or "").strip().lower()
            if st.startswith("paused") or st.startswith("stopped") or st.startswith("queued"):
                to_resume.append(hh)
        if to_release:
            rep["released"] = int(self._hr_host_release(to_release, reason="结清/作废/规则不欠") or 0)
        if to_resume:
            try:
                dl = self._get_downloader("qbittorrent")
                fn = getattr(dl, "force_start_torrents", None) if dl is not None else None
                if callable(fn):
                    cnt, err = fn(to_resume)
                elif dl is not None:
                    cnt, err = dl.resume_torrents(to_resume)
                else:
                    cnt, err = 0, "无下载器"
                rep["resumed"] = int(cnt or 0)
                if err:
                    self._log(f"H&R保种:强挂失败 {err}", "warning")
            except Exception as err:  # noqa: BLE001
                self._log(f"H&R保种:强挂异常:{err}", "warning")
        return rep

    def _hr_host_card(self) -> Dict[str, Any]:
        """★ 11.11.0：__hr_host__（H&R 保种）常驻任务在任务列表里的只读条目。

        与 ``__silent_host__`` 的 ``_silent_host_card`` 同构：只读展示，不接受候选/清理/换种。
        """
        from ..common import HR_HOST_TASK_ID, HR_HOST_INTERVAL_MINUTES  # 惰性导入
        n_hr = 0
        by_site: Dict[str, int] = {}
        try:
            for _h, _rec in (self._tag_state().items() or {}).items():
                if str((_rec or {}).get("state") or "") == STATE_HR:
                    n_hr += 1
                    _s = str((_rec or {}).get("site") or "未知")
                    by_site[_s] = int(by_site.get(_s) or 0) + 1
        except Exception:  # noqa: BLE001
            pass
        try:
            _min = float(getattr(self, "_tags_cfg", {}).get("hr_host_interval") or HR_HOST_INTERVAL_MINUTES)
        except Exception:  # noqa: BLE001
            _min = float(HR_HOST_INTERVAL_MINUTES)
        return {
            "id": HR_HOST_TASK_ID, "name": "H&R保种", "builtin": True, "enabled": True,
            "run_mode": "running", "task_type": "host", "state": "running",
            "site_id": 0, "site_domain": "", "site_name": "全部站点（H&R 保种）",
            "downloader": "所有下载器", "brush_tag": "魔流-<站点>-保种", "save_path": "",
            "seeding_count": n_hr, "hr_count": n_hr, "nonhr_count": 0,
            "active_seeding_count": n_hr, "downloading_count": 0, "paused_count": 0,
            "classify": {"by_site": by_site},
            "host_interval_minutes": round(_min, 1),
            "host_last_run": "—",
        }
