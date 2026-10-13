# -*- coding: utf-8 -*-
"""魔流 · trend —— 趋势观测（可观测②）：插件内建的轻量时间序列。

Master 口径（2026-10-02 11:10）：**不装 Prometheus、不暴露 /metrics 接口**
→ 观测全部做成「插件内建」，端点只给自家前端用。

设计：
  * **采样**：每小时一个点（bucket = 整点）。同一个小时内重复采样只更新不追加。
  * **保留**：环形，每序列最近 ``TREND_KEEP`` 个点（默认 168 = 7 天）。
  * **存储**：热层（``dtier.TierCache`` → 内存 + FileCache/Redis，region=``cache-trend``）
    —— 一次采样 flush 一次，写入极稀（每任务每小时 1 次）。★ 12.6.0 从 kv 搬入热层：
    趋势是**可重取值**（丢了最多少一段历史），不该占 kv。
  * **序列名**：``task:<task_id>``（任务口径） / ``site:<site_id>``（站点口径，多任务同站只记一份）。
  * **单点字段**：``t``(整点时间戳) / ``bonus``(站点口径时魔) / ``seeds``(托管做种数) /
    ``gb``(自身体积，不含辅种) / ``reuse_gb``(辅种体积) / ``bonus_now``(站点当前魔力存量)。
  * **只读端点**：``GET /trend``（scope=task|site|all，id，hours）。

为什么要「站点口径」和「任务口径」两条：任务是我的动作单元，站点才是魔力账本单元
（同站多任务会互相抢名额），趋势图两把尺子都要有。
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from app.schemas import Response

from ..common import CACHE_TTL_HISTORY
from ..kvstore import cache_get, cache_set

TREND_KEY = "trend_v1"          # 热层里的逻辑键（★ 12.6.0 起不再落 kv）
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
                raw = cache_get(self, "trend", TREND_KEY, CACHE_TTL_HISTORY)
                if isinstance(raw, dict):
                    cache = raw
            except Exception:  # noqa: BLE001
                cache = {}
            self._trend_cache = cache
        return cache

    def _trend_flush(self) -> bool:
        """把内存趋势写进热层（可丢缓存）。写失败不抛，返回是否成功。"""
        if not getattr(self, "_trend_dirty", False):
            return True
        try:
            cache_set(self, "trend", TREND_KEY, self._trend_data(), CACHE_TTL_HISTORY)
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
                # ★ 15.12.0：任务口径日报（站点口径由站点监控采样，别互相覆盖）
                record_day(self, "task", str(getattr(task, "id", "") or ""), vals)
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
            daily = daily_load(self)
            out["daily_series"] = {k: len(v) for k, v in daily.items() if isinstance(v, list)}
            out["daily_points"] = sum(len(v) for v in daily.values() if isinstance(v, list))
            out["daily_path"] = _daily_path(self)
            return Response(success=True, data=out)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"趋势诊断失败：{err}")


    # ------------------------------------------------------------
    # ★ 15.12.0：日报（长期趋势，持久化）—— 归因要有「昨天/上周」可比
    # ------------------------------------------------------------

    def get_trend_daily(self, scope: Any = "site", id: Any = "", days: Any = 30) -> Response:
        """功能端点：日报序列（持久化到插件数据目录，默认站点口径 30 天）。

        scope=site|task|all；id 给定时只返该序列。点字段同小时序列，另含 ``free``（限免数）。
        """
        try:
            sc = str(scope or "site").strip().lower()
            ident = str(id or "").strip()
            win = max(1, min(int(days or 30), TREND_DAILY_KEEP))
            data: Dict[str, Any] = {"days": win, "keep": TREND_DAILY_KEEP, "series": {}}
            all_series = daily_load(self)
            if sc in ("task", "site") and ident:
                data["series"][f"{sc}:{ident}"] = daily_series(self, sc, ident, win)
            else:
                for k in all_series:
                    if ":" not in k:
                        continue
                    s2, i2 = k.split(":", 1)
                    if s2 in ("task", "site") and (sc == "all" or s2 == sc):
                        data["series"][k] = daily_series(self, s2, i2, win)
            data["names"] = _series_names(self)
            return Response(success=True, data=data)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取日报失败：{err}")

    def explain_trend(self, scope: Any = "site", id: Any = "", hours: Any = 72) -> Response:
        """★ 归因：把「时魔变化」拆成 种子数 / 单种魔力 / 残差，并给结论 + 证据 + 建议。

        输入：scope=site|task，id=站点 id 或任务 id，hours=对比窗口（默认 72h，取前后等长两段）。
        输出：verdict（一句结论）/ level / delta / factors[] / recent / prior / advice[] / series。
        纯只读，只用本地采样点，不联网。
        """
        try:
            sc = str(scope or "site").strip().lower()
            if sc not in ("site", "task"):
                return Response(success=False, message="scope 只支持 site|task",
                                data={"bad_param": True, "field": "scope"})
            ident = str(id or "").strip()
            if not ident:
                return Response(success=False, message="id 必填（站点 id 或任务 id）",
                                data={"bad_param": True, "field": "id"})
            win = max(6, min(int(hours or 72), TREND_KEEP))
            series = self._trend_series(sc, ident, win)
            pts = [p for p in series if p.get("bonus") is not None]
            base = {"scope": sc, "id": ident, "hours": win, "points": len(series),
                    "series": series, "names": _series_names(self)}
            if len(pts) < 4:
                base.update({
                    "level": "unknown",
                    "verdict": f"样本不足（只有 {len(pts)} 个可比点）——等采样积累，或先让该序列跑一轮。",
                    "factors": [], "recent": {}, "prior": {}, "advice": [],
                    "evidence": "features/trend.py 小时序列（每小时 1 点，同小时覆盖）",
                })
                return Response(success=True, data=base)
            half = max(2, len(pts) // 2)
            prior, recent = pts[:-half], pts[-half:]

            def _avg(rows, key):
                vals = [float(r.get(key)) for r in rows if r.get(key) is not None]
                return (sum(vals) / len(vals)) if vals else 0.0

            def _pct(now, was):
                return ((now - was) / abs(was) * 100.0) if was else 0.0

            b_now, b_was = _avg(recent, "bonus"), _avg(prior, "bonus")
            s_now, s_was = _avg(recent, "seeds"), _avg(prior, "seeds")
            g_now, g_was = _avg(recent, "gb"), _avg(prior, "gb")
            p_now = (b_now / s_now) if s_now else 0.0
            p_was = (b_was / s_was) if s_was else 0.0
            db, ds, dp = b_now - b_was, s_now - s_was, p_now - p_was
            f_seeds, f_per = ds * p_was, s_now * dp
            f_cross = db - f_seeds - f_per
            total = abs(f_seeds) + abs(f_per) + abs(f_cross)

            def _share(v):
                return round(abs(v) / total * 100.0, 1) if total else 0.0

            factors = [
                {"key": "seeds", "label": "种子数", "delta": round(f_seeds, 2), "share": _share(f_seeds),
                 "detail": f"做种数 {s_was:.0f} → {s_now:.0f}（{_pct(s_now, s_was):+.1f}%）× 当时单种魔力 {p_was:.3f}"},
                {"key": "per_seed", "label": "单种魔力", "delta": round(f_per, 2), "share": _share(f_per),
                 "detail": f"单种平均 {p_was:.3f} → {p_now:.3f}（{_pct(p_now, p_was):+.1f}%）× 做种数 {s_now:.0f}"},
                {"key": "cross", "label": "交叉项（残差）", "delta": round(f_cross, 2), "share": _share(f_cross),
                 "detail": "两个因子同时变化的耦合部分"},
            ]
            factors.sort(key=lambda x: -abs(float(x["delta"])))

            pb, ps_pct, pper = _pct(b_now, b_was), _pct(s_now, s_was), _pct(p_now, p_was)
            advice: List[str] = []
            level = "flat"
            if abs(pb) < 3.0:
                verdict = f"基本平稳：时魔 {b_was:.2f} → {b_now:.2f} /h（{pb:+.1f}%）"
            else:
                up = pb > 0
                level = "up" if up else "down"
                top = factors[0]
                verdict = (f"{'上升' if up else '下降'} {abs(pb):.1f}%："
                           f"{b_was:.2f} → {b_now:.2f} /h")
                if top["share"] >= 60 and top["key"] == "seeds":
                    verdict += "，主因是种子数变化"
                    advice.append("查该站在跑任务是否被换出/停种；站点侧限免到期、种子被删、容量触发止损都会掉做种数。")
                    advice.append("用「站点报表」看单站做种数，或 /agent/decide?hashes= 看具体某个种为什么被删。")
                elif top["share"] >= 60 and top["key"] == "per_seed":
                    verdict += "，主因是单种魔力变化"
                    advice.append("单种魔力掉多半是「被抢种」——站点上同种的做种人数上升，魔力按人数因子衰减。")
                    advice.append("对策：优先保「人数少/无人下」的老种（人数因子 2.41 档最肥），或换出被抢晕的种。")
                else:
                    verdict += "，是种子数与单种魔力混合作用"
                    advice.append("看下面 factors 明细，按 share 大的那个因子先动手。")
                if not up and g_now and g_was and _pct(g_now, g_was) < -10 and abs(ps_pct) < 5:
                    advice.append("体积也掉了 >10% 而做种数没怎么变 → 多半是换出了大体积种，属正常置换，注意别把高价值种换没了。")
            if not advice:
                advice.append("继续观察；要在曲线拐点上收到告警，等本批的「趋势告警」接上通知渠道。")

            base.update({
                "level": level, "verdict": verdict, "factors": factors, "advice": advice,
                "delta": {"bonus": round(db, 3), "bonus_pct": round(pb, 1),
                          "seeds": round(ds, 1), "seeds_pct": round(ps_pct, 1),
                          "per_seed": round(dp, 4), "per_seed_pct": round(pper, 1)},
                "recent": {"bonus": round(b_now, 3), "seeds": round(s_now, 1), "gb": round(g_now, 1),
                           "per_seed": round(p_now, 4), "n": len(recent)},
                "prior": {"bonus": round(b_was, 3), "seeds": round(s_was, 1), "gb": round(g_was, 1),
                          "per_seed": round(p_was, 4), "n": len(prior)},
                "evidence": ("features/trend.py 小时序列（每小时 1 点，同小时覆盖，保留 7 天）；"
                             "对比 = 窗口前后等长的两段均值；站点口径由站点监控每轮采样"),
            })
            return Response(success=True, data=base)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"归因失败：{err}")

    # ------------------------------------------------------------
    # 日报存储（模块级函数，见文件底部；这里只做转发，避免跨文件私调）
    # ------------------------------------------------------------

    def trend_day(self, scope: str, ident: str, values: Dict[str, Any],
                  ts: Optional[float] = None) -> None:
        """记一个日报点（公开方法：允许其它 feature 文件直接调用，不再新增跨文件私调）。"""
        record_day(self, scope, ident, values, ts)


def _series_names(plugin: Any) -> Dict[str, str]:
    """序列名映射（任务名 / 站点名），前端少查一次。"""
    names: Dict[str, str] = {}
    try:
        for t in (getattr(plugin, "_task_configs", {}) or {}).values():
            names[f"task:{getattr(t, 'id', '')}"] = getattr(t, "name", "") or ""
            names[f"site:{getattr(t, 'site_id', '')}"] = getattr(t, "site_name", "") or ""
    except Exception:  # noqa: BLE001
        pass
    return names


# ===========================================================================
# 日报（daily）：持久化时间序列（180 天）—— 归因要跨天可比，缓存丢了不能丢历史
# ===========================================================================
TREND_DAILY_KEEP = 180           # 每序列保留天数
TREND_DAILY_KEY = "trend_daily_v1"
_DAY_TZ_OFFSET = 8 * 3600        # 本地日界（Asia/Shanghai 固定 +8，不依赖容器 tz）
_DAILY_LOCK = threading.RLock()


def _day_bucket(ts: Any) -> int:
    return int((float(ts) + _DAY_TZ_OFFSET) // 86400) * 86400 - _DAY_TZ_OFFSET


def _daily_path(plugin: Any) -> str:
    try:
        base = plugin.get_data_path()
    except Exception:  # noqa: BLE001
        return ""
    if not base:
        return ""
    return os.path.join(str(base), "trend_daily.json")


def daily_load(plugin: Any) -> Dict[str, Any]:
    """读全量日报（进程内缓存 + 磁盘真值；文件缺失/损坏 → 空）。"""
    cache = getattr(plugin, "_trend_daily_cache", None)
    if isinstance(cache, dict):
        return cache
    data: Dict[str, Any] = {}
    path = _daily_path(plugin)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, list):
                        data[str(k)] = [p for p in v if isinstance(p, dict)]
        except Exception:  # noqa: BLE001
            data = {}
    try:
        plugin._trend_daily_cache = data
        plugin._trend_daily_dirty = False
    except Exception:  # noqa: BLE001
        pass
    return data


def daily_save(plugin: Any) -> bool:
    """原子落盘（tmp + os.replace）；失败不抛。"""
    path = _daily_path(plugin)
    if not path:
        return False
    try:
        with _DAILY_LOCK:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(daily_load(plugin), fh, ensure_ascii=False)
            os.replace(tmp, path)
        return True
    except Exception:  # noqa: BLE001
        return False


def record_day(plugin: Any, scope: str, ident: str, values: Dict[str, Any],
               ts: Optional[float] = None) -> None:
    """记一个日报点（同一天覆盖，不追加；超过保留天数自动截断）。"""
    sc = str(scope or "").strip()
    i2 = str(ident or "").strip()
    if sc not in ("site", "task") or not i2 or not values:
        return
    try:
        day = _day_bucket(ts if ts is not None else time.time())
        point: Dict[str, Any] = {"t": day}
        for k, v in values.items():
            if v is None:
                continue
            try:
                point[str(k)] = round(float(v), 4)
            except (TypeError, ValueError):
                continue
        if len(point) <= 1:
            return
        with _DAILY_LOCK:
            data = daily_load(plugin)
            key = f"{sc}:{i2}"
            series = data.get(key)
            if not isinstance(series, list):
                series = []
                data[key] = series
            if series and int(series[-1].get("t") or 0) == day:
                if series[-1] == point:
                    return          # 同日同值 → 不重复落盘
                series[-1] = point
            else:
                series.append(point)
            if len(series) > TREND_DAILY_KEEP:
                del series[: len(series) - TREND_DAILY_KEEP]
        try:
            plugin._trend_daily_dirty = True
        except Exception:  # noqa: BLE001
            pass
        daily_save(plugin)
    except Exception:  # noqa: BLE001
        pass


def daily_series(plugin: Any, scope: str, ident: str, days: int = 30) -> List[Dict[str, Any]]:
    """取一条日报序列最近 ``days`` 天。"""
    series = daily_load(plugin).get(f"{scope}:{ident}")
    if not isinstance(series, list):
        return []
    n = max(1, min(int(days or 30), TREND_DAILY_KEEP))
    return [dict(p) for p in series[-n:]]
