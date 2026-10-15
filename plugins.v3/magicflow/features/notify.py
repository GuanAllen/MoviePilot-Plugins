# -*- coding: utf-8 -*-
"""魔流 · 事件通知（★ 15.13.0）。

Master 22:42「全部」→ 批次②：**H&R 临期 / 容量触红线 / 产出骤降 / 任务失败** 直接推给
MoviePilot 通知渠道（微信 / Telegram / Bark…），外带可选**每日日报**。

设计
----
- **不自己造通知通道**：复用 MP 插件基类 ``post_message(title=, text=)`` —— 用户在 MP
  「通知」里配好的渠道自动生效（与 ``live.py`` 站点监控告警同一套）。
- **去重**：同一事件（``kind + dedup``）在 TTL（默认 6h）内只发一次；走热层缓存
  ``cache_get/cache_set``（缓存丢了最多多发一条，不影响正确性）。
- **落历史**：``notify_history.json``（插件数据目录，原子写 ``tmp+os.replace``，保留 200 条）
  → 前端「事件通知」面板可回看。**不是真值表**（派生观测，丢了不影响任何账）。
- **扫描来源全部只读**：
  * 容量 —— ``pool_info()``（池盘 ``pct`` ≥ 阈值）
  * H&R 临期 —— ``get_hr_bills()``（``at_risk`` 条目，或 ``hours_left`` ≤ 阈值）
  * 产出骤降 —— ``features/trend.daily_load()``（最近一日站点时魔 vs 前 3 日均值）
  * 任务失败 —— 任务跑完 ``status == failed`` 时由 ``brush`` 实时调用
- **红线**：通知**只读、只发消息**，绝不触发任何外部动作（删种 / 订阅一律要人确认）。
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from app.schemas import Response
from app.sdk.logging import logger

from ..kvstore import cache_get, cache_set
from ..models import MagicFlowNotifyActPayload
from .trend import daily_load

#: 事件类型 → 中文名
NOTIFY_KIND_TEXT: Dict[str, str] = {
    "hr_deadline": "H&R 临期",
    "capacity": "容量红线",
    "trend_drop": "产出骤降",
    "site_deleted": "站点已删除",
    "task_fail": "任务失败",
    "daily": "每日日报",
    "test": "测试通知",
}

NOTIFY_DEDUP_TTL = 6 * 3600          # 同事件去重窗口（秒）
NOTIFY_SWEEP_INTERVAL = 600          # 周期扫描最短间隔（秒）= 10 分钟
NOTIFY_HISTORY_KEEP = 200            # 历史保留条数
NOTIFY_LEVEL_TEXT = {"info": "信息", "warn": "注意", "error": "严重"}

_HISTORY_LOCK = threading.RLock()


class NotifyMixin:
    """事件通知：配置 / 去重发送 / 周期扫描 / 历史。"""

    # ------------------------------------------------------------ 配置
    def notify_cfg(self) -> Dict[str, Any]:
        """通知配置（前端 / agent 读同一份）。"""
        def _f(name: str, dflt: float) -> float:
            try:
                return float(getattr(self, name, dflt) or 0)
            except (TypeError, ValueError):
                return dflt

        return {
            "enabled": bool(getattr(self, "_notify_enabled", True)),
            "hr_hours": _f("_notify_hr_hours", 24.0),
            "capacity_pct": _f("_notify_capacity_pct", 80.0),
            "drop_pct": _f("_notify_drop_pct", 20.0),
            "task_fail": bool(getattr(self, "_notify_task_fail", True)),
            "daily": bool(getattr(self, "_notify_daily", False)),
            "daily_hour": int(getattr(self, "_notify_daily_hour", 9) or 0),
            "quiet": str(getattr(self, "_notify_quiet", "") or ""),
        }

    def notify_in_quiet(self, cfg: Optional[Dict[str, Any]] = None) -> bool:
        """是否处于免打扰时段（``quiet`` 形如 ``23:00-08:00``；空 = 不静音）。"""
        raw = str((cfg or self.notify_cfg()).get("quiet") or "").strip()
        if "-" not in raw:
            return False
        try:
            a, b = [x.strip() for x in raw.split("-", 1)]
            ah, am = [int(x) for x in a.split(":")]
            bh, bm = [int(x) for x in b.split(":")]
        except (ValueError, TypeError):
            return False
        lt = time.localtime()
        now = lt.tm_hour * 60 + lt.tm_min
        start, end = ah * 60 + am, bh * 60 + bm
        return (start <= now or now < end) if start > end else (start <= now < end)

    # ------------------------------------------------------------ 历史
    def notify_path(self) -> str:
        try:
            base = self.get_data_path()
        except Exception:  # noqa: BLE001
            return ""
        return os.path.join(str(base), "notify_history.json") if base else ""

    def notify_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """最近事件（新 → 旧）。"""
        path = self.notify_path()
        rows: List[Dict[str, Any]] = []
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, list):
                    rows = [r for r in raw if isinstance(r, dict)]
            except Exception:  # noqa: BLE001
                rows = []
        rows.sort(key=lambda r: float(r.get("t") or 0), reverse=True)
        n = max(1, min(int(limit or 50), NOTIFY_HISTORY_KEEP))
        return rows[:n]

    def notify_history_add(self, row: Dict[str, Any]) -> None:
        path = self.notify_path()
        if not path:
            return
        try:
            with _HISTORY_LOCK:
                rows = self.notify_history(NOTIFY_HISTORY_KEEP)
                rows.insert(0, row)
                rows = rows[:NOTIFY_HISTORY_KEEP]
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(rows, fh, ensure_ascii=False)
                os.replace(tmp, path)
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流通知历史写入失败（忽略）：{err}")

    def notify_clear(self) -> int:
        """清空事件历史，返回清掉的条数。"""
        n = len(self.notify_history(NOTIFY_HISTORY_KEEP))
        path = self.notify_path()
        if path:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as err:  # noqa: BLE001
                logger.warning(f"魔流通知历史清理失败（忽略）：{err}")
        return n

    # ------------------------------------------------------------ 发送
    def notify_event(self, kind: str, title: str, text: str, *, dedup: str = "",
                     level: str = "warn", ttl: float = NOTIFY_DEDUP_TTL,
                     force: bool = False) -> bool:
        """发一条事件通知（去重 + 落历史）；返回是否真的发出去了。

        ``force=True``（测试通知）跳过「总开关 / 免打扰 / 去重」三道闸。
        """
        cfg = self.notify_cfg()
        k = str(kind or "event").strip() or "event"
        if not force and not cfg["enabled"]:
            return False
        key = f"{k}:{dedup}" if dedup else ""
        if key and not force:
            if cache_get(self, "notify", key, float(ttl or NOTIFY_DEDUP_TTL)) is not None:
                return False
            cache_set(self, "notify", key, int(time.time()), float(ttl or NOTIFY_DEDUP_TTL))
        quiet = (not force) and self.notify_in_quiet(cfg)
        sent = False
        if not quiet:
            try:
                self.post_message(
                    title=str(title or f"魔流·{NOTIFY_KIND_TEXT.get(k, '通知')}"),
                    text=str(text or ""),
                )
                sent = True
            except Exception as err:  # noqa: BLE001
                logger.warning(f"魔流通知发送失败（忽略）：{err}")
        self.notify_history_add({
            "t": time.time(), "kind": k, "kind_text": NOTIFY_KIND_TEXT.get(k, k),
            "level": str(level or "warn"), "level_text": NOTIFY_LEVEL_TEXT.get(str(level), "注意"),
            "title": str(title or ""), "text": str(text or ""), "dedup": str(dedup or ""),
            "sent": bool(sent), "quiet": bool(quiet),
        })
        return sent

    def notify_task_fail(self, task: Any, reason: Any = "", duration: float = 0.0) -> None:
        """任务失败 → 实时通知（由 ``brush`` 在收尾时调用）。"""
        try:
            name = str(getattr(task, "name", "") or getattr(task, "id", "") or "任务")
            tid = str(getattr(task, "id", "") or "")
            body = [f"任务「{name}」本轮执行失败。"]
            if reason:
                body.append(f"原因：{str(reason)[:300]}")
            if duration:
                body.append(f"耗时：{float(duration) / 60.0:.1f} 分钟。")
            body.append("详情见插件「操作记录」。")
            self.notify_event("task_fail", f"魔流·任务失败（{name}）", "\n".join(body),
                              dedup=tid or name, level="error", ttl=3600)
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流任务失败通知异常（忽略）：{err}")

    # ------------------------------------------------------------ 扫描
    def notify_check_capacity(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """池盘占用 ≥ 阈值 → 一条事件。"""
        out: List[Dict[str, Any]] = []
        try:
            resp = self.pool_info(path="")
            data = getattr(resp, "data", None) or {}
            for p in (data.get("pools") or []):
                pct = float(p.get("pct") or 0)
                if pct >= float(cfg.get("capacity_pct") or 80):
                    out.append({"name": str(p.get("name") or ""), "path": str(p.get("path") or ""),
                                "pct": round(pct, 1), "free_gb": round(float(p.get("free") or 0) / (1024 ** 3), 1)})
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流容量通知检查失败（忽略）：{err}")
        return out

    def notify_check_hr(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """H&R 临期（``at_risk`` 或 ``hours_left`` ≤ 阈值）。"""
        out: List[Dict[str, Any]] = []
        try:
            resp = self.get_hr_bills(site="", live=0)
            data = getattr(resp, "data", None) or {}
            lim = float(cfg.get("hr_hours") or 24)
            for s in (data.get("sites") or []):
                site_name = str(s.get("name") or s.get("domain") or "")
                for it in (s.get("items") or []):
                    hl = it.get("hours_left")
                    risk = bool(it.get("at_risk"))
                    if not risk and hl is None:
                        continue
                    if not risk and float(hl) > lim:
                        continue
                    out.append({
                        "site": site_name, "title": str(it.get("title") or "")[:80],
                        "hours_left": (round(float(hl), 1) if hl is not None else None),
                        "need_h": it.get("need_h"), "seeded_h": it.get("seeded_h"),
                        "state": str(it.get("state") or ""),
                    })
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 H&R 通知检查失败（忽略）：{err}")
        out.sort(key=lambda x: (x.get("hours_left") if x.get("hours_left") is not None else -1e9))
        return out[:20]

    def notify_check_drop(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """产出骤降：最近一日站点时魔 vs 前 3 日均值（日报口径）。"""
        out: List[Dict[str, Any]] = []
        try:
            daily = daily_load(self) or {}
            thr = abs(float(cfg.get("drop_pct") or 20))
            for key, series in daily.items():
                if not str(key).startswith("site:") or not isinstance(series, list) or len(series) < 3:
                    continue
                vals = [float(p.get("bonus")) for p in series
                        if isinstance(p, dict) and p.get("bonus") is not None]
                if len(vals) < 3:
                    continue
                cur = vals[-1]
                prev = vals[-4:-1] if len(vals) >= 4 else vals[:-1]
                base = sum(prev) / len(prev) if prev else 0.0
                if base <= 0:
                    continue
                pct = (cur - base) / base * 100.0
                if pct <= -thr:
                    out.append({"key": str(key), "cur": round(cur, 2), "base": round(base, 2),
                                "pct": round(pct, 1), "days": len(vals)})
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流产出骤降检查失败（忽略）：{err}")
        out.sort(key=lambda x: x["pct"])
        return out[:10]

    def notify_check_site_deleted(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """★ 17.4.0：站点已被 MoviePilot 删除（只报告、不处置）。

        判据与 ``GET /agent/sites/deleted`` **同源**（``siteops.deleted_sites_rows``：魔流台账
        ``mf_site`` 里还在、MP 站点表里已无；按 ``mp_site_id`` / 域名 / 站名三级回落），零额外外部
        请求——``SiteGuard.mp_sites()`` 自带 60s 记忆化，牵连面统计读的是本地标签快照。

        ★ 为什么只告警不自动摘种：真删不可逆，而判据依赖 MP 站点表可读（未认证 / 索引器临时为空
        时 ``deleted_sites_rows`` 自己就返回空——宁可漏报一轮）。故**发现**自动化，**处置**必须显式
        下令（``POST /agent/sites/deleted/act``，默认干跑）。
        """
        out: List[Dict[str, Any]] = []
        try:
            from .siteops import deleted_sites_rows   # 延迟导入：feature 间勿在模块级互相拉
            out = [r for r in (deleted_sites_rows(self) or []) if isinstance(r, dict)]
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流已删站点检查失败（忽略）：{err}")
        return out

    def notify_daily_report(self, cfg: Dict[str, Any]) -> bool:
        """每日日报（可选；按 ``daily_hour`` 之后第一次扫描发一次）。"""
        if not cfg.get("daily"):
            return False
        try:
            lt = time.localtime()
            if lt.tm_hour < int(cfg.get("daily_hour") or 9):
                return False
            day = time.strftime("%Y-%m-%d", lt)
            daily = daily_load(self) or {}
            lines: List[str] = []
            total = 0.0
            for key in sorted(daily.keys()):
                if not key.startswith("site:"):
                    continue
                series = daily.get(key) or []
                last = series[-1] if series else {}
                b = float(last.get("bonus") or 0)
                total += b
                lines.append(f"· {key.split(':', 1)[1]}：{b:.2f} /h · 做种 {int(float(last.get('seeds') or 0))} 个")
            if not lines:
                return False
            body = "\n".join(lines[:20])
            return self.notify_event(
                "daily", f"魔流·每日日报（{day}）",
                f"站点时魔合计 {total:.2f} /h\n{body}",
                dedup=day, level="info", ttl=20 * 3600)
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流每日日报失败（忽略）：{err}")
            return False

    def notify_sweep(self, force: bool = False) -> Dict[str, Any]:
        """周期扫描（站点监控每轮调用，自带最短间隔）；返回本轮触发的事件。"""
        cfg = self.notify_cfg()
        if not force and not cfg["enabled"]:
            return {"skipped": "disabled"}
        if not force:
            if cache_get(self, "notify", "sweep-ts", NOTIFY_SWEEP_INTERVAL) is not None:
                return {"skipped": "throttled"}
            cache_set(self, "notify", "sweep-ts", int(time.time()), NOTIFY_SWEEP_INTERVAL)
        fired: List[Dict[str, Any]] = []

        caps = self.notify_check_capacity(cfg)
        if caps:
            lines = [f"· {c['name']}（{c['path']}）：已用 {c['pct']}%，剩 {c['free_gb']}GB" for c in caps[:6]]
            if self.notify_event("capacity", "魔流·池盘触红线",
                                 f"池盘占用已达阈值（{cfg['capacity_pct']:.0f}%）：\n" + "\n".join(lines)
                                 + "\n\n处理：调低任务容量上限 / 清静默池 / 删低效种子（库内资源管理 → 删除，默认干跑）。",
                                 dedup="pool", level="warn"):
                fired.append({"kind": "capacity", "n": len(caps)})

        hrs = self.notify_check_hr(cfg)
        if hrs:
            lines = []
            for r in hrs[:10]:
                hl = r.get("hours_left")
                left = f"剩 {hl}h" if hl is not None else "已逾期/未达标"
                lines.append(f"· [{r['site']}] {r['title'][:40]}：{left}（做种 {r.get('seeded_h')}h / 需 {r.get('need_h')}h）")
            if self.notify_event("hr_deadline", "魔流·H&R 临期预警",
                                 f"{len(hrs)} 个 H&R 种子临近考核窗口：\n" + "\n".join(lines)
                                 + "\n\n处理：H&R 账单面板一键补种；别停这些种。",
                                 dedup="hr", level="error"):
                fired.append({"kind": "hr_deadline", "n": len(hrs)})

        drops = self.notify_check_drop(cfg)
        if drops:
            lines = [f"· {d['key'].split(':', 1)[1]}：{d['base']:.2f} → {d['cur']:.2f} /h（{d['pct']:+.1f}%）"
                     for d in drops]
            if self.notify_event("trend_drop", "魔流·产出骤降",
                                 f"{len(drops)} 个站点时魔较前几日明显下滑：\n" + "\n".join(lines)
                                 + "\n\n处理：「魔力趋势」看归因（被抢种？换种？限免到期？）。",
                                 dedup="drop", level="warn"):
                fired.append({"kind": "trend_drop", "n": len(drops)})

        dels = self.notify_check_site_deleted(cfg)
        for r in dels[:5]:   # 一次最多告警 5 个站，避免「整排站被删」时刷屏
            sd = r.get("seeds") if isinstance(r.get("seeds"), dict) else {}
            nm = str(r.get("name") or r.get("domain") or r.get("site_id") or "")
            if self.notify_event(
                    "site_deleted", f"魔流·站点已被 MP 删除：{nm}",
                    (f"站点「{nm}」（{r.get('domain') or '—'}）已不在 MP 站点表里"
                     f"（判据 {r.get('reason') or '—'}）。\n"
                     f"魔流这边还挂着：种 {int(sd.get('count') or 0)} 个 · {sd.get('size_gb') or 0}GB"
                     f"（运行 {int(sd.get('running') or 0)} / 暂停 {int(sd.get('paused') or 0)}）"
                     f"· 复用副本 {int(sd.get('reuse') or 0)} 个"
                     f"· 站内任务 {len(r.get('tasks') or [])} 个。\n\n"
                     "处理：`GET /agent/sites/deleted` 看全量牵连面；处置用 "
                     "`POST /agent/sites/deleted/act`（**默认干跑**）——remove 只摘掉复用副本与本体"
                     "（都不删文件）、仅把「自有非本体」连文件删；也可先用 pause 止血。"),
                    dedup=f"sitedel:{r.get('site_id')}", level="warn"):
                fired.append({"kind": "site_deleted", "n": 1})
        if len(dels) > 5:
            logger.warning(f"魔流已删站点共 {len(dels)} 个，本轮只告警前 5 个："
                           f"{[r.get('name') for r in dels[5:]]}")

        try:
            if self.notify_daily_report(cfg):
                fired.append({"kind": "daily", "n": 1})
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流日报发送异常（忽略）：{err}")

        return {"fired": fired, "checked": {"capacity": len(caps), "hr": len(hrs), "drop": len(drops),
                                            "site_deleted": len(dels)},
                "at": time.time()}

    # ------------------------------------------------------------ 端点
    def notify_status(self, limit: int = 50) -> Response:
        """``GET /notify`` —— 配置 + 最近事件 + 分类计数（只读）。"""
        try:
            rows = self.notify_history(limit)
            counts: Dict[str, int] = {}
            for r in self.notify_history(NOTIFY_HISTORY_KEEP):
                k = str(r.get("kind") or "")
                counts[k] = counts.get(k, 0) + 1
            return Response(success=True, data={
                "cfg": self.notify_cfg(),
                "history": rows,
                "counts": counts,
                "kinds": NOTIFY_KIND_TEXT,
                "sweep_interval": NOTIFY_SWEEP_INTERVAL,
                "dedup_ttl": NOTIFY_DEDUP_TTL,
                "path": self.notify_path(),
                "quiet_now": self.notify_in_quiet(),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取通知状态失败：{err}")

    def notify_act(self, payload: MagicFlowNotifyActPayload) -> Response:
        """``POST /notify/act`` —— ``test``（发测试）/ ``scan``（立即扫描）/ ``clear``（清历史）。

        ⚠ 参数必须用 pydantic 模型（不能用 ``Any``）：MP 插件框架靠类型注解判 body 模型，
        ``Any`` 会被当成必填 query 参数 → 报「payload Field required」。
        """
        try:
            act = str(getattr(payload, "action", "") or "").strip().lower()
            if act == "test":
                sent = self.notify_event(
                    "test", "魔流·测试通知",
                    str(getattr(payload, "text", "") or "这是一条来自魔流的测试通知 🐂\n收到即说明 MP 通知渠道可用。"),
                    force=True, level="info")
                return Response(success=bool(sent), message="测试通知已发送" if sent else "发送失败，请看插件日志",
                                data={"sent": bool(sent)})
            if act == "scan":
                rep = self.notify_sweep(force=True)
                n = len(rep.get("fired") or [])
                return Response(success=True, message=f"已扫描，触发 {n} 类事件", data=rep)
            if act == "clear":
                n = self.notify_clear()
                return Response(success=True, message=f"已清空 {n} 条历史", data={"cleared": n})
            return Response(success=False, message="action 需为 test / scan / clear")
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"通知动作失败：{err}")
