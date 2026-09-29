# -*- coding: utf-8 -*-
"""魔流 · swap —— 自动换种（边际魔力收益换入换出，只暂停不删）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from ..bonus import (
    marginal_bonus_per_hour,
    score_candidate,
)
from ..downloader_ops import (
    DownloaderAdapter,
    TorrentInfo,
    QB_PAUSED_STATES,
)
from ..persistence import OperationItem
from ..sites.formula_fetch import (
    _norm_title as normalize_title,
)


from ..common import (
    BROWSE_PAGES,
    MagicFlowTaskConfig,
    SWAP_DAY_DL_GB,
    SWAP_DAY_DL_GB_TOTAL,
    SWAP_INTERVAL,
    SWAP_MAX_ADD_GB,
    SWAP_MAX_IN_GB,
    SWAP_MAX_PER_ROUND,
    SWAP_MIN_GAIN_PER_GB,
    SWAP_SOFT_MARGIN_MULT,
)


class SwapMixin:
    """swap 功能集（原 MagicFlow 方法原样搬入）。"""

    def _swap_plan(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, Any]:
        """算出「该换哪些种」——纯决策，不落盘。

        站点魔力是「对**合计 A** 只取一次 arctan」，所以换种能算真实边际：
            gain = B(A − a_v + a_c) − B(A − a_v)
            loss = B(A) − B(A − a_v)
            net  = gain − loss      （> 0 才说明「换掉 v、换进 c」净赚）
        只有 ``net ≥ loss × swap_min_gain_pct`` 才列入计划。

        换出侧一律排除**硬保护**：欠 H&R / 手动保留 / 跨站来源份 / 尚未下载完成。
        库内资产 / 同站纳管自有种属**软保护**——可换出（只是暂停做种、不删种），但要求净收益
        达基础的 ``SWAP_SOFT_MARGIN_MULT`` 倍。
        触发条件（任一）：名额满 / 磁盘满 / 站点占用 ≥ swap_ceiling_pct。
        还有空间时**不换**（直接补种更划算，由 brush 负责）。
        """
        out: Dict[str, Any] = {"ok": False, "reason": "", "pairs": [], "net": 0.0, "trigger": "", "triggered": False, "a_total": 0.0, "active": 0}
        if not downloader or not downloader.is_available:
            out["reason"] = "下载器不可用"
            return out
        if not bool(getattr(task, "auto_swap", True)):
            out["reason"] = "未开启自动换种"
            return out
        if str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() != "bonus":
            out["reason"] = "刷流任务不参与魔力换种（自有「产出换种」）"
            return out
        if not str(getattr(task, "save_path", "") or "").strip():
            out["reason"] = "未配置保存目录"
            return out

        # 1) 本任务托管种
        try:
            _groups, _ = downloader.get_torrents_by_tag() if hasattr(downloader, "get_torrents_by_tag") else ({}, "n/a")
        except Exception as e:  # noqa: BLE001
            out["reason"] = f"取托管种失败:{e}"
            return out
        all_tagged = _groups.get(task.brush_tag, []) if isinstance(_groups, dict) else []
        managed = self._task_owned_torrents(task, all_tagged)
        if len(managed) < 2:
            out["reason"] = "托管种不足，无需换种"
            return out

        params = self._build_formula_params(task)
        official = self._site_official_titles(task.site_id)
        self._backfill_pub_dates(task, managed)
        managed_bonus = self._convert_to_bonus_list(
            managed, params, self._task_pub_dates(task),
            getattr(task, "ti_source", "publish"),
            self._site_ni_map(task.site_id, managed), official,
        )
        # ★ 「在做种」才算数：被换下线的（paused）既不计 A，也不占名额
        by_hash = {(getattr(t, "hash", "") or "").lower(): t for t in managed}

        def _paused(h: str) -> bool:
            t = by_hash.get((h or "").lower())
            if not t:
                return False
            return str(getattr(t, "state", "") or "").lower() in QB_PAUSED_STATES

        def _active(h: str) -> bool:
            t = by_hash.get((h or "").lower())
            if not t or _paused(h):
                return False
            try:
                return float(getattr(t, "progress", 1.0) or 0.0) >= 0.999
            except Exception:  # noqa: BLE001
                return True

        active_bonus = [b for b in managed_bonus if _active(b.hash)]
        a_total = 0.0
        for b in active_bonus:
            try:
                a_total += float(getattr(b, "bonus_score", 0.0) or 0.0)
            except Exception:  # noqa: BLE001
                pass
        out["a_total"] = round(a_total, 4)
        out["active"] = len(active_bonus)

        # 2) 触发条件
        policy = self._build_magic_policy(task, managed_bonus)
        max_keep = policy.max_keep_torrents
        disk_gb = task.disk_size_gb
        try:
            size_gb = sum(float(getattr(t, "size_gb", 0) or 0) for t in managed)
        except Exception:  # noqa: BLE001
            size_gb = 0.0
        occ = self._site_ceiling_pct(task)
        ceiling_pct = float(getattr(task, "swap_ceiling_pct", 70.0) or 70.0)
        triggers = []
        if max_keep and len(active_bonus) >= int(max_keep):
            triggers.append(f"名额满 {len(active_bonus)}/{int(max_keep)}")
        if disk_gb and size_gb >= float(disk_gb):
            triggers.append(f"磁盘满 {size_gb:.0f}/{float(disk_gb):.0f}GB")
        if occ >= ceiling_pct:
            triggers.append(f"站点占用 {occ:.0f}%≥{ceiling_pct:.0f}%")
        if not triggers:
            out["reason"] = f"还有空间（占用 {occ:.0f}%），直接补种更划算"
            return out
        out["triggered"] = True
        out["trigger"] = " / ".join(triggers)

        # 冷却：换种要抓候选 + 下载，不宜每分钟都跑
        _now = time.time()
        _bag = getattr(self, "_swap_last", None)
        if _bag is None:
            _bag = self._swap_last = {}
        _last = float(_bag.get(task.id, 0.0) or 0.0)
        if _last and (_now - _last) < SWAP_INTERVAL:
            out["reason"] = f"换种冷却中（剩 {int(SWAP_INTERVAL - (_now - _last))}s）"
            return out
        _bag[task.id] = _now

        # 3) 保护分层
        #   硬保护（永不换出）：手动保留 / 跨站来源份 / 欠 H&R / 未下完
        #   软保护（**可换出**，但要求更高净收益）：库内资产（已整理/下载历史）/ 同站纳管的自有资源
        #   —— 因为换出只是「暂停做种、不被拉去做种」，不删种、不删文件，可随时换回，不是破坏性操作。
        # ★ 保护裁决统一走 _protection_sets（唯一真值源，见 docs/MODULES.md）
        _prot = self._protection_sets(task, managed_bonus, list(managed))
        hard, soft = _prot["hard"], _prot["soft"]
        _act = {b.hash for b in active_bonus}
        out["hard_n"] = len(hard & _act)
        out["soft_n"] = len(soft & _act)

        # 4) 换出候选（a 最小、非硬保护、正在做种）
        victims = [
            b for b in active_bonus
            if b.hash and b.hash not in hard
            and float(getattr(b, "bonus_score", 0.0) or 0.0) > 0
        ]
        victims.sort(key=lambda b: float(getattr(b, "bonus_score", 0.0) or 0.0))
        if not victims:
            out["reason"] = "无可换出的种（全为硬保护）"
            return out

        # 5) 候选（站点级共享抓取）
        try:
            cands = self._fetch_site_candidates(task, pages=max(int(task.browse_pages or BROWSE_PAGES), 1))
        except Exception as e:  # noqa: BLE001
            out["reason"] = f"抓取候选失败:{e}"
            return out
        if not cands:
            out["reason"] = "未获取到候选"
            return out
        min_seeders = max(int(getattr(policy, "min_seeders", 0) or 0), 1)
        flat = float(getattr(params, "per_torrent_flat", 0.0) or 0.0)
        cap_n = int(getattr(params, "seeding_count_cap", 0) or 0)
        flat_gain = flat if (not cap_n or len(managed) < cap_n) else 0.0
        have_titles = {(normalize_title(getattr(t, "title", "") or "")) for t in managed}
        scored: List[Tuple[Any, Any]] = []
        _in_cap_raw = getattr(task, "swap_max_in_gb", None)
        _in_cap = float(SWAP_MAX_IN_GB if _in_cap_raw is None else _in_cap_raw)
        skipped_big = 0
        for c in cands:
            try:
                if float(getattr(c, "size_gb", 0) or 0) <= 0:
                    continue
            except Exception:  # noqa: BLE001
                continue
            # ★ 体积闸门:换种不该拿全盘去换几个魔力。换入种超过任务上限直接跳过
            #   （大体积种魔力看着很香，但下载/磁盘成本远超收益）。
            if _in_cap > 0 and float(getattr(c, "size_gb", 0) or 0) > _in_cap:
                skipped_big += 1
                continue
            if have_titles and normalize_title(getattr(c, "title", "") or "") in have_titles:
                continue
            _is_off = bool(official) and (normalize_title(getattr(c, "title", "") or "") in official)
            sc = score_candidate(
                size_gb=float(getattr(c, "size_gb", 0) or 0),
                seeders=int(getattr(c, "seeders", 0) or 0),
                age_weeks=float(getattr(c, "age_weeks", 0) or 0),
                a_current=a_total,
                is_zero_bonus=bool(getattr(c, "is_zero_bonus", False)),
                is_official=_is_off,
                params=params,
                min_seeders=min_seeders,
                flat_gain=flat_gain,
            )
            if not sc.viable:
                continue
            scored.append((c, sc))
        scored.sort(key=lambda kv: (float(kv[1].a_contrib or 0.0), float(kv[1].value or 0.0)), reverse=True)
        if not scored:
            out["reason"] = (
                f"无可用候选（{skipped_big} 个超过体积上限 {_in_cap:.0f}GB）"
                if skipped_big else "无可用候选（无源/高于门槛）"
            )
            return out
        out["skipped_big"] = skipped_big

        # 6) 贪心配对：候选 a 必须超过被撤种 a，且净收益达门槛
        margin = max(float(getattr(task, "swap_min_gain_pct", 25.0) or 25.0) / 100.0, 0.05)
        A = a_total
        pairs: List[Dict[str, Any]] = []
        added_gb = 0.0
        for (c, sc), v in zip(scored, victims):
            a_v = float(getattr(v, "bonus_score", 0.0) or 0.0)
            a_c = float(sc.a_contrib or 0.0)
            if a_c <= a_v:
                break
            in_gb = float(getattr(c, "size_gb", 0) or 0)
            out_gb = float(getattr(v, "size_gb", 0) or 0)
            grow = max(in_gb - out_gb, 0.0)
            # 单轮累计「多占磁盘」不超过阈值
            if added_gb + grow > SWAP_MAX_ADD_GB:
                continue
            # 不越任务磁盘预算
            if disk_gb and (size_gb - out_gb + in_gb) > float(disk_gb):
                continue
            a_after = max(A - a_v, 0.0)
            gain = marginal_bonus_per_hour(a_after, a_c, params)
            loss = marginal_bonus_per_hour(a_after, a_v, params)
            net = gain - loss
            _mult = SWAP_SOFT_MARGIN_MULT if (v.hash in soft) else 1.0
            if net < loss * margin * _mult:
                continue
            pairs.append({"cand": c, "score": sc, "victim": v, "net": net, "gain": gain, "loss": loss, "soft": bool(v.hash in soft)})
            added_gb += grow
            A = a_after + a_c
        if not pairs:
            out["reason"] = "无可换（现有种都比候选优）"
            return out
        pairs = pairs[:SWAP_MAX_PER_ROUND]
        out["ok"] = True
        out["pairs"] = pairs
        out["net"] = round(sum(float(p["net"]) for p in pairs), 3)
        return out

    def _swap_crossseed_in(
        self, task: MagicFlowTaskConfig, cand: Any, downloader: DownloaderAdapter
    ) -> Optional[str]:
        """换种「取种换入」：本站不免费的候选 → 去兄弟站找免费同 Release 的副本取种。

        复用现有跨站链路（`:meth:`_crossseed_start`），因此来源份照旧进 `crossseed_sources`
        H&R 保种账本；本站侧零下载（兄弟站免费），后续由「跨站回辅」worker 指向同一批文件回辅。

        Returns: 成功发起返回兄弟站种子 hash；找不到免费副本 / 取种失败 / PV 不足 → None
        （调用方据此**跳过这一对**，绝不退回付费下载）。
        """
        try:
            if not getattr(cand, "raw", None):
                # ★ 3.44.0 API 站（馒头）候选：现场取签名直链
                if not getattr(cand, "enclosure", ""):
                    try:
                        self._cand_enclosure(cand)
                    except Exception:  # noqa: BLE001
                        pass
                url = str(getattr(cand, "enclosure", "") or "")
                if not url:
                    return None
                sid = int(getattr(task, "site_id", 0) or 0)
                if sid and (
                    self._pv_block_reason(sid) or not self._pv_allow(sid, "crossseed", want=1)
                ):
                    self._log(
                        f"魔流 [{task.name}] 换种:跨站取种 PV 预算不足/已封，改为跳过 {str(getattr(cand, 'title', ''))[:40]}",
                        "warning",
                    )
                    return None
                raw = downloader.fetch_torrent_bytes(
                    url,
                    cookie=getattr(cand, "site_cookie", None),
                    user_agent=getattr(cand, "site_ua", None),
                    referer=str(getattr(cand, "page_url", "") or "") or None,
                )
                if not raw:
                    return None
                try:
                    cand.raw = raw
                except Exception:  # noqa: BLE001
                    return None
            # 契约②：走取种统一入口（第 ④ 跳）；拿不到免费副本就返回 None → 调用方跳过该对
            _acq = self._acquire_source(task, cand, downloader, allow_cross_site=True)
            return _acq.get("sib_hash") or None
        except Exception as e:  # noqa: BLE001
            self._log(
                f"魔流 [{task.name}] 换种:跨站取种失败 {str(getattr(cand, 'title', ''))[:40]} ({e})",
                "warning",
            )
            return None

    def _swap_round(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter, apply: bool = True) -> Dict[str, Any]:
        """★ 自动换种：把低价值种「换下线」（暂停做种，**不删种**），换入更优候选。

        换出 = 不再拉它做种（种子与文件全部保留，可随时换回）；
        换入 = 优先复用本机已有同资源（零下载辅种），没命中才下载。
        不在换种触发状态且站点占用明显回落时，把之前换下线的种「换回」做种（滞回，防抖）。
        """
        plan = self._swap_plan(task, downloader)
        if not apply:
            return plan
        _eligible = (
            str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "bonus"
            and bool(getattr(task, "auto_swap", True))
        )
        if not plan.get("triggered"):
            if _eligible:
                plan["resumed"] = self._swap_resume(task, downloader)
            return plan
        pairs = plan.get("pairs") or []
        if not plan.get("ok") or not pairs:
            return plan
        # ★ 每日换种下载预算：换种是「拿磁盘/**流量**换魔力」，必须按**真实下载量**限速。
        #   （3.35.x 教训：旧口径按「磁盘增量」计——下载 30GB 只记几 GB，一夜烧穿 100GB+ 流量。）
        _allow_dl = bool(getattr(task, "swap_allow_download", False))
        _dl_cap = float(getattr(task, "swap_daily_dl_gb", None) or SWAP_DAY_DL_GB)
        _min_gain_per_gb = float(getattr(task, "swap_min_gain_per_gb", None) or SWAP_MIN_GAIN_PER_GB)
        _min_in_seeders = int(getattr(task, "swap_min_in_seeders", 3) or 1)
        _today = datetime.now().strftime("%Y-%m-%d")
        _daybag = getattr(self, "_swap_day", None)
        if _daybag is None:
            _daybag = self._swap_day = {}
        _st = _daybag.get(task.id) or {}
        if _st.get("d") != _today:
            _st = {"d": _today, "gb": 0.0}
            _daybag[task.id] = _st
        _gbag = getattr(self, "_swap_day_total", None)
        if _gbag is None:
            _gbag = self._swap_day_total = {}
        if _gbag.get("d") != _today:
            _gbag = {"d": _today, "gb": 0.0}
            self._swap_day_total = _gbag
        _used = float(_st.get("gb", 0.0) or 0.0)
        _used_g = float(_gbag.get("gb", 0.0) or 0.0)
        plan["day_gb"] = round(_used, 1)
        plan["day_gb_total"] = round(_used_g, 1)
        if _allow_dl and (_used >= _dl_cap or _used_g >= SWAP_DAY_DL_GB_TOTAL):
            plan["applied"] = 0
            plan["reason"] = (
                f"今日换种下载已用满（本任务 {_used:.0f}/{_dl_cap:.0f}GB · "
                f"全局 {_used_g:.0f}/{SWAP_DAY_DL_GB_TOTAL:.0f}GB）"
            )
            return plan
        # 换入优先零下载：本机已有同资源 → 直接辅种（统一走 _acquire_existing）
        local_by_size = None
        local_index: Dict[str, TorrentInfo] = {}
        fp_cache: Dict[str, Optional[str]] = {}
        try:
            local_index, local_by_size = self._local_reuse_index(downloader)
        except Exception:  # noqa: BLE001
            local_by_size = None
        swapped = 0
        swap_items: List[OperationItem] = []
        for p in pairs:
            c = p["cand"]
            v = p["victim"]
            _sz = float(getattr(c, "size_gb", 0) or 0)
            _is_free = bool(getattr(c, "is_free", False) or getattr(c, "is_double_free", False))
            new_hash = ""
            reused = False
            try:
                _amode, _ainfo = self._acquire_existing(
                    task, c, downloader,
                    local_index=local_index, local_by_size=local_by_size,
                    fp_cache=fp_cache, raw=getattr(c, "raw", None),
                    respect_task_flag=False,
                )
                reused = bool(_amode and _ainfo is not None)
                if not reused and local_by_size is not None:
                    # 统一入口未命中 → 退回「单候选辅种」（会实际下载 .torrent 并校验特征码）
                    reused, _info = self._try_reuse_candidate(downloader, c, local_by_size, fp_cache, task)
            except Exception as _re:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 换种:辅种尝试失败 {_re}", "warning")
                reused = False
            # ★ 换入闸门（3.36.0；3.37.1 收紧「不付费」）：没命中本地复用 = 要真下载。
            #   默认**不许**（只做零下载辅种）；开了「取种换入」也只走**免费渠道**：
            #     ① 本站免费候选 → 直接下；
            #     ② 本站不免费 → 去兄弟站找「免费且同一 Release」的副本取种（跨站免费取种）；
            #     ③ 两条都不通 → **跳过这一对，不换**（绝不付费下载：吃下载量/分享率，得不偿失）。
            #   ① ② 统一还要过：每日预算（本任务+全局） ②性价比（net ≥ 下载GB × 门槛）。
            _kind = "reuse" if reused else ""
            if not reused:
                if not _allow_dl:
                    plan["skipped_download"] = int(plan.get("skipped_download") or 0) + 1
                    continue
                if (_used + _sz > _dl_cap) or (_used_g + _sz > SWAP_DAY_DL_GB_TOTAL):
                    plan["reason"] = (
                        f"今日换种下载预算不足（本任务 {_used:.0f}/{_dl_cap:.0f}GB · "
                        f"全局 {_used_g:.0f}/{SWAP_DAY_DL_GB_TOTAL:.0f}GB，候选 {_sz:.1f}GB）"
                    )
                    continue
                if _min_gain_per_gb > 0 and float(p["net"]) < _sz * _min_gain_per_gb:
                    plan["reason"] = (
                        f"换种性价比不足（净 +{float(p['net']):.2f}/h < {_sz:.1f}GB × {_min_gain_per_gb:.2f}）"
                    )
                    continue
                if not _is_free:
                    # ② 跨站免费取种：去兄弟站找免费副本。找不到 → 放弃这一对（不花钱）。
                    _sib = self._swap_crossseed_in(task, c, downloader)
                    if not _sib:
                        plan["skipped_nofree"] = int(plan.get("skipped_nofree") or 0) + 1
                        continue
                    new_hash = _sib
                    _kind = "cross"
                else:
                    # ① 本站免费：能不能下得完（老种候选常常没人做种，Ni 小≠有源）
                    if int(getattr(c, "seeders", 0) or 0) < _min_in_seeders:
                        plan["skipped_noseed"] = int(plan.get("skipped_noseed") or 0) + 1
                        continue
                    raw = None
                    try:
                        if not getattr(c, "enclosure", None):
                            self._cand_enclosure(c)
                        if getattr(c, "enclosure", None):
                            raw = downloader.fetch_torrent_bytes(
                                c.enclosure,
                                cookie=getattr(c, "site_cookie", None),
                                user_agent=getattr(c, "site_ua", None),
                                referer=getattr(c, "page_url", "") or None,
                            )
                    except Exception as e:  # noqa: BLE001
                        self._log(f"魔流 [{task.name}] 换种:取种失败 {str(getattr(c, 'title', ''))[:40]} ({e})", "warning")
                        continue
                    if not raw:
                        continue
                    new_hash, err = downloader.add_torrent(
                        content=raw,
                        download_dir=task.save_path or "",
                        tag=self._task_tag(task),
                        cookie=getattr(c, "site_cookie", None),
                        user_agent=getattr(c, "site_ua", None),
                        upload_limit=task.up_speed,
                        download_limit=task.dl_speed,
                    )
                    if not new_hash:
                        self._log(f"魔流 [{task.name}] 换种:换入失败 {str(getattr(c, 'title', ''))[:40]} ({err})", "warning")
                        continue
                    _kind = "dl"
            # 换出：暂停做种（不删种、不删文件）
            try:
                pcnt, perr = downloader.pause_torrents([v.hash])
            except Exception as e:  # noqa: BLE001
                pcnt, perr = 0, str(e)
            if not pcnt:
                self._log(
                    f"魔流 [{task.name}] 换种:换下线失败（新种已入）{str(getattr(v, 'title', ''))[:40]} ({perr})",
                    "warning",
                )
                continue
            swapped += 1
            if not reused:
                _used += _sz
                _used_g += _sz
                _st["gb"] = _used
                _gbag["gb"] = _used_g
                _k = "cross_gb" if _kind == "cross" else "free_gb"
                plan[_k] = round(float(plan.get(_k) or 0.0) + _sz, 1)
            if self._store:
                try:
                    self._store.mark_swap_paused(task.id, [v.hash])
                    if new_hash:
                        self._store.seen.mark(task.id, [f"hash:{new_hash.lower()}"])
                except Exception:  # noqa: BLE001
                    pass
            swap_items.append(OperationItem(
                hash=(new_hash or "").lower(), title=str(getattr(c, "title", "")),
                reason=(
                    "换入·辅种（零下载，净 +%.2f/h）" % float(p["net"]) if _kind == "reuse" else
                    ("换入·跨站免费（净 +%.2f/h）" % float(p["net"]) if _kind == "cross" else
                     "换入·本站免费下载（净 +%.2f/h）" % float(p["net"]))
                ),
                size_gb=float(getattr(c, "size_gb", 0) or 0), source="swap",
            ))
            swap_items.append(OperationItem(
                hash=v.hash, title=str(getattr(v, "title", "")),
                reason=f"换出·暂停做种（边际 {p['loss']:.2f} → {p['gain']:.2f}/h，不删种）",
                size_gb=float(getattr(v, "size_gb", 0) or 0), source="swap",
            ))
        if swap_items and self._store:
            try:
                self._store.journal.record(task_id=task.id, kind="swap", items=swap_items)
            except Exception:  # noqa: BLE001
                pass
        plan["applied"] = swapped
        plan["day_gb"] = round(_used, 1)
        plan["day_gb_total"] = round(_used_g, 1)
        if swapped:
            self._log(
                f"魔流 [{task.name}] 换种 {swapped} 对（净 +{plan['net']:.2f}/h）"
                f"| 换出=暂停做种不删种 | 今日取种 {_used:.0f}/{_dl_cap:.0f}GB"
                f"（本站免费 {float(plan.get('free_gb') or 0):.0f} / 跨站免费 {float(plan.get('cross_gb') or 0):.0f}）"
                f"（全局 {_used_g:.0f}/{SWAP_DAY_DL_GB_TOTAL:.0f}GB）| 触发 {plan.get('trigger')}"
            )
        if plan.get("skipped_download") or plan.get("skipped_nofree") or plan.get("skipped_noseed"):
            self._dbg(
                f"魔流 [{task.name}] 换种:跳过取种换入 —— 未开启 {plan.get('skipped_download', 0)} 对"
                f" / 找不到免费副本 {plan.get('skipped_nofree', 0)} 个 / 没源 {plan.get('skipped_noseed', 0)} 个"
            )
        return plan

    def _swap_resume(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> int:
        """换回：站点占用已明显回落（滞回 30pt）时，把换下线的种恢复做种。"""
        if not self._store:
            return 0
        try:
            paused = self._store.get_swap_paused(task.id)
        except Exception:  # noqa: BLE001
            return 0
        if not paused:
            return 0
        ceiling_pct = float(getattr(task, "swap_ceiling_pct", 70.0) or 70.0)
        occ = self._site_ceiling_pct(task)
        if occ > max(ceiling_pct - 30.0, 0.0):
            return 0
        _now = time.time()
        _bag = getattr(self, "_swap_last", None)
        if _bag is None:
            _bag = self._swap_last = {}
        _last = float(_bag.get(task.id, 0.0) or 0.0)
        if _last and (_now - _last) < SWAP_INTERVAL:
            return 0
        hashes = list(paused)[:SWAP_MAX_PER_ROUND]
        try:
            cnt, err = downloader.resume_torrents(hashes)
        except Exception as e:  # noqa: BLE001
            self._log(f"魔流 [{task.name}] 换回异常: {e}", "warning")
            return 0
        if not cnt:
            return 0
        _bag[task.id] = _now
        try:
            self._store.clear_swap_paused(task.id, hashes)
            self._store.journal.record(task_id=task.id, kind="swap", items=[
                OperationItem(hash=h, title="", reason="换回·恢复做种（占用已回落）", source="swap")
                for h in hashes
            ])
        except Exception:  # noqa: BLE001
            pass
        self._log(f"魔流 [{task.name}] 换回做种 {cnt} 个（占用 {occ:.0f}% 已明显回落）")
        return int(cnt or 0)
