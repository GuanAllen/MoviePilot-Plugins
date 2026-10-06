# -*- coding: utf-8 -*-
"""魔流 · health —— 健康自检与告警（可观测③）：插件内建，不依赖外部系统。

Master 口径（2026-10-02 11:10）：**不装 Prometheus、不暴露 /metrics** → 自检在插件里做，
只给自家面板用：`GET /health` 返回「按严重度排序的问题清单」，前端顶栏一个指示灯 + 弹窗。

设计原则：
  * **零外部请求**：只看本地已落库的运行时数据（任务状态）+ 趋势序列（`features/trend.py`）。
    绝不为自检去抓站点/下载器（那会把观测变成负担、还会被风控）。
  * **可操作**：每条问题都给 `title`（发生了什么）+ `detail`（数字/原因）+ 可选 `task_id`（点进去诊断）。
  * **不刷屏**：只在「状态没变化」时不重复报警；状态变化才写日志（见 `_health_log_delta`）。

检查项（v1）：
  H1 任务上次运行失败（`last_error` / `last_run_status=failed`）
  H2 任务卡死：超过 `max(5×检查间隔, 30min)` 没跑过（或从未成功跑过）
  H3 站点口径时魔下滑：最近采样 vs 24h 前，跌幅 ≥25% 且绝对值 ≥5/h
  H4 磁盘贴上限：任务占用 ≥ 站点 `disk_size_gb` 的 95%
  H5 没有启用的任务（全局）
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from app.schemas import Response

from ..common import task_is_running
from .hrbills import (
    BILL_STATE_ACTIVE,
    BILL_STATE_BREACHED,
    RULE_HIT_AND_RUN,
    RULE_SITE_HR,
)

# H4 阈值：占用达到存储上限的多少比例算「贴上限」
DISK_NEAR_PCT = 95.0
# H3 阈值：时魔跌幅（相对 + 绝对都要超）
BONUS_DROP_PCT = 25.0
BONUS_DROP_ABS = 5.0
# H2：卡死判定 = max(5×检查间隔, 30 分钟)
STALE_MIN_SECONDS = 1800.0
STALE_INTERVAL_FACTOR = 5

LEVEL_ORDER = {"error": 0, "warning": 1, "info": 2}


class HealthMixin:
    """健康自检：聚合「需要你管」的信号。"""

    # ------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------

    def _health_issues(self) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        now = time.time()
        try:
            tasks = list((getattr(self, "_task_configs", {}) or {}).values())
        except Exception:  # noqa: BLE001
            tasks = []
        running = [t for t in tasks if task_is_running(t)]

        # H1 / H2：任务维度
        for t in running:
            stats: Dict[str, Any] = {}
            if self._store:
                try:
                    stats = self._store.get_task_stats(getattr(t, "id", "")) or {}
                except Exception:  # noqa: BLE001
                    stats = {}
            name = getattr(t, "name", "") or getattr(t, "id", "")
            err = str(stats.get("last_error") or "").strip()
            status = str(stats.get("last_run_status") or "").strip().lower()
            last = float(stats.get("last_run_at") or 0.0)
            if err:
                issues.append({
                    "key": f"H1:{getattr(t, 'id', '')}",
                    "level": "error",
                    "title": f"「{name}」上次运行出错",
                    "detail": err[:200],
                    "task_id": getattr(t, "id", ""),
                })
            elif status == "failed":
                issues.append({
                    "key": f"H1:{getattr(t, 'id', '')}",
                    "level": "error",
                    "title": f"「{name}」上次运行失败",
                    "detail": "运行以失败告终，请到「运行诊断」看最后一轮",
                    "task_id": getattr(t, "id", ""),
                })
            interval = max(int(getattr(t, "check_interval", 1) or 1), 1) * 60
            stale_after = max(interval * STALE_INTERVAL_FACTOR, STALE_MIN_SECONDS)
            if last <= 0:
                issues.append({
                    "key": f"H2:{getattr(t, 'id', '')}",
                    "level": "warning",
                    "title": f"「{name}」还没跑过",
                    "detail": "已启用但没有任何运行记录（等首轮，或调度没起来）",
                    "task_id": getattr(t, "id", ""),
                })
            elif now - last > stale_after:
                issues.append({
                    "key": f"H2:{getattr(t, 'id', '')}",
                    "level": "warning",
                    "title": f"「{name}」已 {int((now - last) / 60)} 分钟没跑",
                    "detail": f"检查间隔 {interval // 60} 分钟，超过 {int(stale_after // 60)} 分钟视为卡死",
                    "task_id": getattr(t, "id", ""),
                })

        # H3 / H4：趋势维度（零外部请求）
        try:
            trend = self._trend_data()
        except Exception:  # noqa: BLE001
            trend = {}
        for key, series in (trend or {}).items():
            if not isinstance(series, list) or len(series) < 2:
                continue
            last_point = series[-1]
            if not isinstance(last_point, dict):
                continue
            # H3 站点口径时魔下滑（任务/站点序列都看，站点优先）
            try:
                prev = None
                target_ts = float(last_point.get("t") or 0) - 24 * 3600
                for p in series:
                    if isinstance(p, dict) and float(p.get("t") or 0) <= target_ts:
                        prev = p
                if prev and last_point.get("bonus") is not None and prev.get("bonus"):
                    last_v = float(last_point.get("bonus") or 0.0)
                    prev_v = float(prev.get("bonus") or 0.0)
                    drop = prev_v - last_v
                    pct = (drop / prev_v * 100.0) if prev_v else 0.0
                    if drop >= BONUS_DROP_ABS and pct >= BONUS_DROP_PCT:
                        scope, ident = (key.split(":", 1) + [""])[:2]
                        label = self._trend_label(scope, ident)
                        issues.append({
                            "key": f"H3:{key}",
                            "level": "warning",
                            "title": f"{label}时魔下滑 {pct:.0f}%",
                            "detail": f"24 小时前 {prev_v:.1f}/h → 现在 {last_v:.1f}/h（少 {drop:.1f}/h）",
                            "task_id": ident if scope == "task" else "",
                        })
            except Exception:  # noqa: BLE001
                pass

        # H4 磁盘贴上限（任务口径）
        for t in running:
            try:
                disk = float(getattr(t, "disk_size_gb", 0) or 0)
                if disk <= 0:
                    continue
                series = trend.get(f"task:{getattr(t, 'id', '')}")
                if not isinstance(series, list) or not series:
                    continue
                gb = float((series[-1] or {}).get("gb") or 0.0)
                if gb >= disk * DISK_NEAR_PCT / 100.0:
                    issues.append({
                        "key": f"H4:{getattr(t, 'id', '')}",
                        "level": "info",
                        "title": f"「{getattr(t, 'name', '')}」体积贴上限",
                        "detail": f"占用 {gb:.0f} / {disk:.0f}GB（≥{DISK_NEAR_PCT:.0f}%），已达上限后将只做换种",
                        "task_id": getattr(t, "id", ""),
                    })
            except Exception:  # noqa: BLE001
                pass

        # H6 账号保活：站点「多久不登入删号」临近（只读快照，**零外部请求**）
        try:
            _snap = getattr(getattr(self, "_signin", None), "keepalive_snapshot", lambda: {})() or {}
        except Exception:  # noqa: BLE001
            _snap = {}
        for row in _snap.get("sites") or []:
            if not isinstance(row, dict) or not row.get("warn"):
                continue
            issues.append({
                "key": f"H6:{row.get('site_id')}",
                "level": "warning",
                "title": f"「{row.get('site_name')}」距不登入删号还有 {row.get('days_left')} 天",
                "detail": (
                    f"站点记录的最后登入：{row.get('last_login') or '未知'}。"
                    f"{row.get('rule_note') or ''}→ 请用浏览器 / 官方 App 亲自登一次"
                ),
                "task_id": "",
            })

        # H5 全局：一个启用的任务都没有
        if tasks and not running:
            issues.append({
                "key": "H5:global",
                "level": "info",
                "title": "没有启用中的任务",
                "detail": f"共 {len(tasks)} 个任务，全部处于「已停止」",
                "task_id": "",
            })

        issues.sort(key=lambda i: (LEVEL_ORDER.get(str(i.get("level")), 9), str(i.get("title", ""))))
        return issues

    def _trend_label(self, scope: str, ident: str) -> str:
        """把 ``task:<id>`` / ``site:<id>`` 变成可读名字。"""
        try:
            for t in (getattr(self, "_task_configs", {}) or {}).values():
                if scope == "task" and str(getattr(t, "id", "")) == str(ident):
                    return f"「{getattr(t, 'name', '') or ident}」"
                if scope == "site" and str(getattr(t, "site_id", "")) == str(ident):
                    name = getattr(t, "site_name", "") or ident
                    return f"「{name}」站"
        except Exception:  # noqa: BLE001
            pass
        return f"{scope}:{ident}"

    # ------------------------------------------------------------
    # 端点
    # ------------------------------------------------------------

    def get_health(self) -> Response:
        """功能端点：健康自检（问题清单按严重度排序）。"""
        try:
            issues = self._health_issues()
            counts = {"error": 0, "warning": 0, "info": 0}
            for i in issues:
                lv = str(i.get("level") or "info")
                counts[lv] = counts.get(lv, 0) + 1
            level = "ok"
            if counts.get("error"):
                level = "error"
            elif counts.get("warning"):
                level = "warning"
            elif counts.get("info"):
                level = "info"
            data = {
                "level": level,
                "ok": level in ("ok", "info"),
                "counts": counts,
                "issues": issues,
                "checked_at": time.time(),
            }
            self._health_log_delta(data)
            return Response(success=True, data=data)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"健康自检失败：{err}")

    def _health_log_delta(self, data: Dict[str, Any]) -> None:
        """只在问题集合发生变化时写一条日志（避免每轮刷屏）。"""
        try:
            sig = "|".join(sorted(str(i.get("key", "")) for i in (data.get("issues") or [])))
            if sig == getattr(self, "_health_last_sig", None):
                return
            self._health_last_sig = sig
            issues = data.get("issues") or []
            if not issues:
                self._log("健康自检:全部正常")
                self._emit_event("health", action="健康恢复正常", level="info", reason="全部检查项通过")
                return
            top = ", ".join(str(i.get("title", "")) for i in issues[:3])
            self._log(f"健康自检:{data.get('level')} · {len(issues)} 项 → {top}"
                      + ("…" if len(issues) > 3 else ""),
                      "warning" if data.get("level") in ("error", "warning") else "info")
            first = issues[0] if isinstance(issues[0], dict) else {}
            self._emit_event(
                "health",
                action="健康告警",
                level=str(data.get("level") or "warning"),
                task_id=str(first.get("task_id") or ""),
                reason=top + ("…" if len(issues) > 3 else ""),
                metrics={"count": len(issues), "error": int((data.get("counts") or {}).get("error") or 0),
                         "warning": int((data.get("counts") or {}).get("warning") or 0)},
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------
    # ★ 挂种健康度自检（12.5.0，只读）
    # ------------------------------------------------------------
    #
    # 回答一类问题：「哪些挂种在空转 / 缺文件、占多少体积、其中哪些还欠 H&R（风险）」
    # 两段式（性能关键，见 docs/TASK-1250-HEALTH.md）：
    #   第 1 段粗筛：顶层 listing（按目录缓存，只列一次）比 `content_path` 的候选名；
    #   第 2 段精确：只对候选调 `torrents/files` 逐文件 `os.path.exists`（含临时路径）。
    # 桶位：normal / partial（不全）/ incomplete（只在临时目录且未完成 `.!qB`）/ ghost（一点都没有）。
    # 零写入：不 recheck / 不改 qB / 不写账本 / 不动文件。真值源：qB 快照 + 文件系统 +
    #   hr_bills.json（只读）。

    # 逐文件核盘的候选上限（防爆盘；超限截断并在输出标 probe_truncated）
    MAX_PROBE_DEFAULT = 300

    def _health_manual_hashes(self) -> Set[str]:
        """手动保留 hash 并集（跨所有任务 + 历史空 task_id），与 ``_delete_gate_detail`` 同源。"""
        out: Set[str] = set()
        try:
            store = getattr(self, "_store", None)
            if store is None:
                return out
            tids = list((getattr(self, "_task_configs", None) or {}).keys())
            tids.append("")
            for tid in tids:
                try:
                    out |= set(store.get_protected_torrents(tid) or set())
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return {str(h).strip().lower() for h in out}

    @staticmethod
    def _health_norm_domain(raw: Any) -> str:
        """tracker/URL → 裸域名（小写）。"""
        s = str(raw or "").strip().lower()
        s = s.split("://")[-1]
        s = s.split("/")[0]
        s = s.split(":")[0]
        return s.strip()

    def _health_torrent_domain(self, t: Any) -> str:
        """单种 → 站点域名（短名 → 域名；回退 tracker 域名；再回退短名原样）。"""
        short = ""
        try:
            short = str(self._torrent_site_name(getattr(t, "tags", None)) or "").strip()
        except Exception:  # noqa: BLE001
            short = ""
        if short:
            try:
                dom = self._site_domain_by_name(short)
            except Exception:  # noqa: BLE001
                dom = ""
            if dom:
                return self._health_norm_domain(dom)
        tr = self._health_norm_domain(getattr(t, "tracker", ""))
        if tr:
            return tr
        return short

    @staticmethod
    def _health_coarse_names(cp: str) -> Set[str]:
        """候选名集合 = {basename(content_path), basename(dirname(content_path))}（rstrip '/' 后）。"""
        c = str(cp or "").strip().rstrip("/")
        if not c or c == "/":
            return set()
        names = {os.path.basename(c)}
        d = os.path.dirname(c)
        if d and d not in ("/", "."):
            b = os.path.basename(d)
            if b:
                names.add(b)
        names.discard("")
        names.discard("/")
        return names

    def _health_scan(self, site: str = "", only: str = "", limit: int = 200,
                     max_probe: int = 0) -> Dict[str, Any]:
        """挂种健康度自检核心（只读，人机同源）。UI ``GET /health/scan`` 与
        AI ``GET /agent/seeds/health`` 都走这里。

        - ``site``：域名 / 短名 / id（可空=全站）；
        - ``only``：``ghost``（只回无数据）/ ``partial``（只回缺文件）/ ``all``（默认）；
        - ``limit``：``items`` 条数上限（默认 200，0=不限）；
        - ``max_probe``：逐文件核盘的候选上限（默认 300，超限截断标 ``probe_truncated``）。
        """
        at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}

        only = str(only or "").strip().lower()
        if only not in ("ghost", "partial", "incomplete", "all"):
            only = "all"
        try:
            limit = int(limit or 200)
        except (TypeError, ValueError):
            limit = 200
        if limit < 0:
            limit = 0
        try:
            max_probe = int(max_probe or self.MAX_PROBE_DEFAULT)
        except (TypeError, ValueError):
            max_probe = self.MAX_PROBE_DEFAULT
        if max_probe <= 0:
            max_probe = self.MAX_PROBE_DEFAULT

        dl = None
        try:
            dl = self._get_downloader()
        except Exception:  # noqa: BLE001
            dl = None
        def _local(p: str) -> str:
            """下载器（宿主）路径 → 插件（容器）可访问路径。

            ★ 必须做这层映射：qB 给的是宿主机路径（如 ``/vol6/1000/movie/刷流``），
            插件进程在容器里只能看到挂载后的 ``/movie/刷流``；直接用原始路径
            ``os.listdir/os.path.exists`` 会**全部判不存在**（假 ghost 满屏）。
            """
            raw = str(p or "").strip()
            if not raw:
                return ""
            try:
                if dl is not None:
                    norm = dl.normalize_path(raw)
                    if norm:
                        return str(norm).rstrip("/") or "/"
            except Exception:  # noqa: BLE001
                pass
            return raw

        temp_path = ""
        try:
            prefs, _err = (dl.get_app_preferences() if dl is not None else (None, "no-dl"))
            if bool((prefs or {}).get("temp_path_enabled")):
                temp_path = _local(str((prefs or {}).get("temp_path") or ""))
        except Exception:  # noqa: BLE001
            temp_path = ""

        filter_dom = ""
        if str(site or "").strip():
            raw = str(site).strip()
            try:
                filter_dom = self._site_domain_by_name(raw) or raw.lower()
            except Exception:  # noqa: BLE001
                filter_dom = raw.lower()
            filter_dom = self._health_norm_domain(filter_dom)

        bill_store = None
        try:
            bill_store = self._hrbills_store()
        except Exception:  # noqa: BLE001
            bill_store = None

        listing_cache: Dict[str, Set[str]] = {}

        def _listing(path: str) -> Set[str]:
            p = str(path or "").strip()
            if not p:
                return set()
            if p not in listing_cache:
                try:
                    listing_cache[p] = {n for n in os.listdir(p)}
                except Exception:  # noqa: BLE001
                    listing_cache[p] = set()
            return listing_cache[p]

        manual = self._health_manual_hashes()

        # ---- 第 1 段：粗筛（廉价，只列目录） ----
        suspicious: List[str] = []
        rows: Dict[str, Dict[str, Any]] = {}
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            dom = self._health_torrent_domain(t)
            if filter_dom and dom != filter_dom:
                continue
            save_path = str(getattr(t, "save_path", "") or "").strip()
            cp = str(getattr(t, "content_path", "") or "").strip().rstrip("/")
            title = str(getattr(t, "title", "") or "")[:160]
            state = str(getattr(t, "state", "") or "")
            try:
                progress = round(float(getattr(t, "progress", 0) or 0), 4)
            except (TypeError, ValueError):
                progress = 0.0
            size_gb = round(float(getattr(t, "size_gb", 0) or 0), 3)
            rows[hh] = {
                "hash": hh, "title": title, "site": dom, "qb_state": state,
                "progress": progress, "save_path": save_path,
                "size_gb": size_gb, "files_total": None, "files_exist": None,
                "files_incomplete": None,
                "bucket": "normal", "hr": None, "protected": [],
                "bill": None,
            }
            if not save_path:
                # 无保存路径元数据 → 无法粗筛/核盘，按正常跳过（不误报 ghost）
                continue
            names = self._health_coarse_names(cp)
            # 粗筛只看**保存目录**：临时目录里同名目录不一定属于这个种（可能只是别人的
            # 未完成副本）→ 交给第 2 段逐文件核，宁多核不漏。
            present = bool(names & _listing(_local(save_path)))
            if not names or not present:
                suspicious.append(hh)

        # ---- 第 2 段：精确（只对候选，逐文件核） ----
        probe_truncated = 0
        probed = 0
        for hh in suspicious:
            if probed >= max_probe:
                probe_truncated = len(suspicious) - probed
                break
            t = snap.get(hh)
            if t is None:
                continue
            probed += 1
            save_path = _local(str(getattr(t, "save_path", "") or "").strip())
            entries = []
            try:
                entries = list(dl.get_file_entries(hh) or []) if dl is not None else []
            except Exception:  # noqa: BLE001
                entries = []
            exist = 0
            incom = 0
            for rel, _sz in entries:
                rel = str(rel or "").strip()
                if not rel:
                    continue
                done = False
                part = False
                for base in (save_path, temp_path):
                    if not base:
                        continue
                    try:
                        if os.path.exists(os.path.join(base, rel)):
                            done = True
                            break
                        # qB 未完成文件会带 `.!qB` 后缀（数据在临时目录、还没搬完）
                        if os.path.exists(os.path.join(base, rel + ".!qB")):
                            part = True
                    except Exception:  # noqa: BLE001
                        continue
                if done:
                    exist += 1
                elif part:
                    incom += 1
            total = len(entries)
            r = rows.get(hh)
            if r is None:
                continue
            r["files_total"] = total
            r["files_exist"] = exist
            r["files_incomplete"] = incom
            if total <= 0:
                r["bucket"] = "normal"
            elif exist >= total:
                r["bucket"] = "normal"
            elif exist > 0:
                r["bucket"] = "partial"
            elif incom > 0:
                r["bucket"] = "incomplete"
            else:
                r["bucket"] = "ghost"

        # ---- 汇总 + H&R 关联 + 保护 -------
        counts = {"normal": 0, "ghost": 0, "partial": 0, "incomplete": 0, "not_in_qb": 0}
        bytes_agg = {"ghost_gb": 0.0, "partial_gb": 0.0, "incomplete_gb": 0.0}
        by_site: Dict[str, Dict[str, Any]] = {}
        items: List[Dict[str, Any]] = []
        hr_at_risk: List[Dict[str, Any]] = []

        def _site_bucket(dom: str) -> Dict[str, Any]:
            if dom not in by_site:
                by_site[dom] = {"ghost": 0, "partial": 0, "incomplete": 0, "gb": 0.0}
            return by_site[dom]

        for hh, r in rows.items():
            bill = None
            if bill_store is not None:
                try:
                    bill = bill_store.get(hh)
                except Exception:  # noqa: BLE001
                    bill = None
            bill_state = str((bill or {}).get("state") or "")
            bill_rule = str((bill or {}).get("rule") or "")
            scopes: List[str] = []
            if bill_state in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED) \
                    and bill_rule in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                scopes.append("hr_bill")
            if hh in manual:
                scopes.append("manual")
            r["protected"] = scopes
            if bill:
                need_h = float(bill.get("need_h") or 0.0)
                seeded_h = float(bill.get("seeded_h") or 0.0)
                r["hr"] = {
                    "state": bill_state, "rule": bill_rule,
                    "need_h": round(need_h, 1),
                    "seeded_h": round(seeded_h, 2),
                    "need_left": round(max(0.0, need_h - seeded_h), 2),
                }
            bucket = r["bucket"]
            counts[bucket] = counts.get(bucket, 0) + 1
            dom = r["site"] or "?"
            sb = _site_bucket(dom)
            if bucket in ("ghost", "incomplete"):
                bytes_agg[bucket + "_gb"] += r["size_gb"]
                sb[bucket] += 1
                sb["gb"] = round(sb["gb"] + r["size_gb"], 3)
                if bucket in ("ghost", "incomplete") and r["hr"] and r["hr"]["state"] in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED):
                    hr_at_risk.append({
                        "hash": hh, "title": r["title"], "site": dom, "bucket": bucket,
                        "state": r["hr"]["state"], "rule": r["hr"]["rule"],
                        "need_h": r["hr"]["need_h"], "need_left": r["hr"]["need_left"],
                        "save_path": r["save_path"], "size_gb": r["size_gb"],
                    })
            elif bucket == "partial":
                bytes_agg["partial_gb"] += r["size_gb"]
                sb["partial"] += 1
                sb["gb"] = round(sb["gb"] + r["size_gb"], 3)
            r.pop("bill", None)
            items.append(r)

        # H&R 账单在册但 qB 里没有的种（active/breached，已从下载器消失）
        try:
            all_bills = bill_store.all() if bill_store is not None else {}
        except Exception:  # noqa: BLE001
            all_bills = {}
        for hh, b in all_bills.items():
            if not isinstance(b, dict):
                continue
            st = str(b.get("state") or "")
            if st not in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED):
                continue
            if hh in snap:
                continue
            dom = self._health_norm_domain(b.get("site"))
            if filter_dom and dom != filter_dom:
                continue
            counts["not_in_qb"] = int(counts.get("not_in_qb") or 0) + 1

        # only 过滤（只作用于 items；counts/by_site/bytes 始终全量）
        if only in ("ghost", "partial", "incomplete"):
            items = [x for x in items if x["bucket"] == only]

        # 排序：ghost（先欠 H&R）> incomplete > partial > normal，同桶按体积降序
        _rank = {"ghost": 0, "incomplete": 1, "partial": 2, "normal": 3}
        items.sort(key=lambda x: (
            _rank.get(x["bucket"], 9),
            0 if x["hr"] else 1,
            -float(x["size_gb"] or 0),
        ))
        if limit > 0:
            items = items[:limit]

        return {
            "at": at,
            "scanned": len(snap),
            "candidates": len(suspicious),
            "probed": probed,
            "probe_truncated": probe_truncated,
            "site_filter": filter_dom,
            "counts": counts,
            "bytes": {"ghost_gb": round(bytes_agg["ghost_gb"], 2),
                       "partial_gb": round(bytes_agg["partial_gb"], 2),
                       "incomplete_gb": round(bytes_agg["incomplete_gb"], 2)},
            "by_site": {k: {"ghost": v["ghost"], "partial": v["partial"],
                            "incomplete": v["incomplete"], "gb": round(v["gb"], 2)}
                        for k, v in sorted(by_site.items(),
                                           key=lambda kv: -kv[1]["gb"])},
            "hr_at_risk": hr_at_risk,
            "items": items,
            "write": False,
            "source_of_truth": [
                "qB torrents/info + files（逐文件存在性）",
                "文件系统 os.listdir / os.path.exists",
                "hr_bills.json（只读）",
            ],
        }

    def health_scan(self, site: str = "", only: str = "", limit: int = 200) -> Response:
        """``GET /health/scan``：挂种健康度自检（只读）。"""
        try:
            data = self._health_scan(site, only, limit)
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"挂种健康度自检失败: {e}", "error")
            return Response(success=False, message=str(e))
