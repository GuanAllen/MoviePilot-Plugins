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
    DUTY_STATES,
)


class HrMixin:
    """hr 功能集（原 MagicFlow 方法原样搬入）。"""

    def _hr_obligation(self, site: str, torrent: Any) -> Tuple[bool, float, float, str]:
        """该种是否**欠 H&R**：``(欠?, 要求小时, 已挂小时, 来源)``。

        站点名先解析成域名再查规则库（manual > probe > builtin > 默认）；义务按**实测做种时长**判。
        """
        dom = self._site_domain_by_name(site) or str(site or "")
        try:
            thr = True if bool(getattr(torrent, "hit_and_run", False)) else None
        except Exception:  # noqa: BLE001
            thr = None
        try:
            protect, hours, src = self._crossseed_hr_decision(dom, thr)
        except Exception:  # noqa: BLE001
            protect, hours, src = False, 0.0, "err"
        if not protect:
            return False, 0.0, 0.0, src
        need = 0.0
        try:
            need = float(self._crossseed_seed_need_hours(dom) or 0.0)
        except Exception:  # noqa: BLE001
            need = 0.0
        if need <= 0:
            need = float(hours or 0.0)
        try:
            seeded = float(getattr(torrent, "seed_time", 0) or 0.0) / 3600.0
        except (TypeError, ValueError):
            seeded = 0.0
        if need <= 0:
            return False, 0.0, seeded, f"无时长要求({src})"
        return (seeded + 1e-6 < need), float(need), seeded, src

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

    def _hr_guard_tick(self, apply: bool = True, limit: int = 0) -> Dict[str, Any]:
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
        snap = self._tag_all_torrents() or {}
        if not snap:
            rep["reason"] = "无快照"
            return rep
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        try:
            cssrc = dict(self._crossseed_sources().items() or {})
        except Exception:  # noqa: BLE001
            cssrc = {}
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
        scope = set(ledger) | set(cssrc)
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
            obl, need, seeded, src = self._hr_obligation(site, t)
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
            if str(rec.get("state") or "") in DUTY_STATES and not has_tag:
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
        return rep
