# -*- coding: utf-8 -*-
"""魔流 · trend —— 趋势观测（可观测②）：插件内建的轻量时间序列。

Master 口径（2026-10-02 11:10）：**不装 Prometheus、不暴露 /metrics 接口**
→ 观测全部做成「插件内建」，端点只给自家前端用。

设计：
  * **采样**：每小时一个点（bucket = 整点）。同一个小时内重复采样只更新不追加。
  * **保留**：环形，每序列最近 ``TREND_KEEP`` 个点（默认 168 = 7 天）。
  * **存储**：插件 KV（``plugindata``，key=``trend_v1``）——一次采样 flush 一次，
    写入极稀（每任务每小时 1 次），不碰 Redis 热层、不引入新依赖。
  * **序列名**：``task:<task_id>``（任务口径） / ``site:<site_id>``（站点口径，多任务同站只记一份）。
  * **单点字段**：``t``(整点时间戳) / ``bonus``(站点口径时魔) / ``seeds``(托管做种数) /
    ``gb``(自身体积，不含辅种) / ``reuse_gb``(辅种体积) / ``bonus_now``(站点当前魔力存量)。
  * **只读端点**：``GET /trend``（scope=task|site|all，id，hours）。

为什么要「站点口径」和「任务口径」两条：任务是我的动作单元，站点才是魔力账本单元
（同站多任务会互相抢名额），趋势图两把尺子都要有。
"""

import time
from typing import Any, Dict, List, Optional

from app.schemas import Response

TREND_KEY = "trend_v1"          # 插件 KV 里的键（plugindata）
TREND_KEEP = 168                # 每序列保留的点数（7 天 × 24）
DEFAULT_HOURS = 72              # 前端默认拉取窗口


class TrendMixin:
    """趋势采样 + 只读查询。"""

    # ------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------

    def _trend_data(self) -> Dict[str, Any]:
        """读全量趋势（进程内缓存，热重载后重建）。"""
        cache = getattr(self, "_trend_cache", None)
        if cache is None:
            cache = {}
            try:
                raw = self.get_data(TREND_KEY)
                if isinstance(raw, dict):
                    cache = raw
            except Exception:  # noqa: BLE001
                cache = {}
            self._trend_cache = cache
        return cache

    def _trend_flush(self) -> bool:
        """把内存趋势落盘（插件 KV）。写失败不抛，返回是否成功。"""
        if not getattr(self, "_trend_dirty", False):
            return True
        try:
            self.save_data(key=TREND_KEY, value=self._trend_data())
            self._trend_dirty = False
            return True
        except Exception:  # noqa: BLE001
            return False

    def _trend_record(self, series_key: str, values: Dict[str, Any], ts: Optional[float] = None) -> None:
        """记一个采样点（同一小时覆盖，不追加）。"""
        if not series_key or not values:
            return
        try:
            now = float(ts if ts is not None else time.time())
            bucket = int(now // 3600) * 3600
            point: Dict[str, Any] = {"t": bucket}
            for k, v in values.items():
                if v is None:
                    continue
                try:
                    point[k] = round(float(v), 4)
                except (TypeError, ValueError):
                    continue
            if len(point) <= 1:
                return
            data = self._trend_data()
            series = data.get(series_key)
            if not isinstance(series, list):
                series = []
                data[series_key] = series
            if series and int(series[-1].get("t") or 0) == bucket:
                series[-1] = point
            else:
                series.append(point)
            if len(series) > TREND_KEEP:
                del series[: len(series) - TREND_KEEP]
            self._trend_dirty = True
            self._trend_flush()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------
    # 采样入口（被 check / brush 轮次调用）
    # ------------------------------------------------------------

    def _trend_sample_task(self, task: Any, out: Optional[Dict[str, Any]] = None) -> None:
        """从一轮清理/检查结果里采一个点（任务口径 + 站点口径）。"""
        try:
            out = out or {}
            dec = dict(out.get("decision") or {})
            bonus = out.get("total_after")
            if bonus is None:
                bonus = out.get("total_before")
            vals = {
                "bonus": bonus,
                "seeds": dec.get("cur_n"),
                "gb": dec.get("cur_gb"),
                "reuse_gb": dec.get("reuse_gb"),
            }
            # 站点当前魔力存量（有则记，别为它额外发请求）
            rep = None
            try:
                rep = self._site_reported(task) or {}
            except Exception:  # noqa: BLE001
                rep = {}
            if isinstance(rep, dict) and rep.get("ok"):
                vals["bonus_now"] = rep.get("current_bonus")
            vals = {k: v for k, v in vals.items() if v is not None}
            if vals:
                self._trend_record(f"task:{task.id}", vals)
                self._trend_record(f"site:{getattr(task, 'site_id', '') or '?'}", vals)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------

    def _trend_series(self, scope: str, ident: str, hours: int) -> List[Dict[str, Any]]:
        """取一条序列的最近 ``hours`` 小时。"""
        key = f"{scope}:{ident}"
        series = self._trend_data().get(key)
        if not isinstance(series, list):
            return []
        hours = max(1, min(int(hours or DEFAULT_HOURS), TREND_KEEP))
        point_count = hours  # 每小时一点
        return [dict(p) for p in series[-point_count:]]

    def get_trend(self, scope: Any = "all", id: Any = "", hours: Any = DEFAULT_HOURS) -> Response:
        """功能端点：趋势序列（默认任务+站点全量，最近 72 小时）。"""
        try:
            scope = str(scope or "all").strip().lower()
            ident = str(id or "").strip()
            hours = int(hours or DEFAULT_HOURS)
            data: Dict[str, Any] = {"hours": hours, "keep": TREND_KEEP, "series": {}}
            all_series = self._trend_data()
            if scope in ("task", "site") and ident:
                data["series"][f"{scope}:{ident}"] = self._trend_series(scope, ident, hours)
            elif scope == "task":
                for k in all_series:
                    if k.startswith("task:"):
                        data["series"][k] = self._trend_series("task", k.split(":", 1)[1], hours)
            elif scope == "site":
                for k in all_series:
                    if k.startswith("site:"):
                        data["series"][k] = self._trend_series("site", k.split(":", 1)[1], hours)
            else:
                for k in all_series:
                    if ":" in k:
                        s, i = k.split(":", 1)
                        if s in ("task", "site"):
                            data["series"][k] = self._trend_series(s, i, hours)
            # 任务名/站点名映射，前端少查一次
            names: Dict[str, str] = {}
            try:
                for t in (getattr(self, "_task_configs", {}) or {}).values():
                    names[f"task:{getattr(t, 'id', '')}"] = getattr(t, "name", "") or ""
                    names[f"site:{getattr(t, 'site_id', '')}"] = getattr(t, "site_name", "") or ""
            except Exception:  # noqa: BLE001
                names = {}
            data["names"] = names
            return Response(success=True, data=data)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取趋势失败：{err}")

    def debug_trend(self) -> Response:
        """只读诊断：点数 / 序列数 / 最后采样时间。"""
        try:
            all_series = self._trend_data()
            out: Dict[str, Any] = {"series_count": len(all_series), "points": 0, "last": 0.0}
            for k, v in all_series.items():
                if isinstance(v, list):
                    out["points"] += len(v)
                    if v:
                        out["last"] = max(out["last"], float(v[-1].get("t") or 0))
            out["series"] = {k: len(v) for k, v in all_series.items() if isinstance(v, list)}
            return Response(success=True, data=out)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"趋势诊断失败：{err}")
