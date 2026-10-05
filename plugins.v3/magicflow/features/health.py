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

import time
from typing import Any, Dict, List, Optional

from app.schemas import Response

from ..common import task_is_running

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
