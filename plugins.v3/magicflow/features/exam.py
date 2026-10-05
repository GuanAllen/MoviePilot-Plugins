# -*- coding: utf-8 -*-
"""魔流 · exam —— 站点考核（进度、下载模式、自动转做种）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
import time
from dataclasses import fields
from datetime import datetime
from typing import Any, Dict, List, Optional


from app.schemas import Response

from ..models import (
    MagicFlowTaskPayload,
)


from ..common import (
    MagicFlowTaskConfig,
    SIGNIN_INTERVAL_MINUTES,
    enabled_of_run_mode,
    RUN_MODE_RUNNING,
    RUN_MODE_STOPPED,
    RUN_MODE_SEEDING,
)


class ExamMixin:
    """exam 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------------- 新手考核
    def _exam_download_state(self, task: MagicFlowTaskConfig) -> Dict[str, Any]:
        """考核下载模式状态:{on, base, cur, delta_gb, target_gb, remain_gb, done}。

        首次进入该模式(baseline 为空)时,用站点当前下载量作为基线并落盘。
        """
        out: Dict[str, Any] = {
            "on": False, "base": None, "cur": None,
            "delta_gb": 0.0, "target_gb": 0.0, "remain_gb": 0.0, "done": False,
        }
        try:
            target = float(getattr(task, "download_target_gb", None) or 0.0)
        except (TypeError, ValueError):
            target = 0.0
        if target <= 0 or not bool(getattr(task, "allow_unfree_download", False)):
            return out
        out["on"] = True
        out["target_gb"] = target
        sid = int(getattr(task, "site_id", 0) or 0)
        cur: Optional[float] = None
        try:
            if getattr(self, "_live", None) is not None and sid:
                live = self._live.get(sid)
                if isinstance(live, dict) and live.get("ok") and live.get("download") is not None:
                    cur = float(live.get("download") or 0.0)
        except Exception:  # noqa: BLE001
            cur = None
        base: Optional[float] = None
        if self._store is not None:
            try:
                saved = self._store.get_exam_download(task.id).get("base")
            except Exception:  # noqa: BLE001
                saved = None
            if saved is None and cur is not None:
                saved = cur
                try:
                    self._store.set_exam_download(task.id, cur, f"基线取自 {time.strftime('%Y-%m-%d %H:%M')}")
                except Exception:  # noqa: BLE001
                    pass
            base = saved
        out["base"], out["cur"] = base, cur
        if base is not None and cur is not None:
            delta = max(0.0, (cur - base) / (1024 ** 3))
            out["delta_gb"] = round(delta, 3)
            out["remain_gb"] = round(max(0.0, target - delta), 3)
            out["done"] = delta >= target - 1e-9
        else:
            out["remain_gb"] = target
        return out

    def _exam_download_active(self, task: MagicFlowTaskConfig) -> bool:
        st = self._exam_download_state(task)
        return bool(st.get("on")) and not bool(st.get("done"))

    def _exam_action_plan(
        self, site_id: int, live: Dict[str, Any], tasks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """把考核未通过项翻译成可执行动作(**只读**,不创建任何东西)。"""
        exam = (live or {}).get("exam") or {}
        items = exam.get("items") or []
        if not items:
            return []
        site_name = self._live_site_name(int(site_id or 0))
        up = float((live or {}).get("upload") or 0.0)
        dn = float((live or {}).get("download") or 0.0)
        bonus = float((live or {}).get("bonus") or 0.0)
        free = exam.get("site_free") or {}
        free_on = bool(free and free.get("on"))
        left = exam.get("days_left")
        plan: List[Dict[str, Any]] = []
        for it in items:
            if it.get("pass"):
                continue
            label = str(it.get("label") or "")
            short_gb = it.get("short_gb")
            short_num = it.get("short_num")
            notes: List[str] = []
            entry: Dict[str, Any] = {"label": label, "kind": "hold", "notes": [], "blocked": False}
            if "下载" in label and short_gb is not None:
                # ★ 我们不做下载业务 / 不建下载任务（Master 2026-09-30）：只如实提示，不给可执行动作
                short = float(short_gb)
                entry.update({"kind": "info", "label": f"{label}（不建任务）", "short_gb": short})
                notes.append("下载类考核：本插件不建下载任务，需自行安排；不建任务不影响已有做种")
                if up and dn + short * (1024 ** 3) > 0:
                    ra = up / (dn + short * (1024 ** 3))
                    notes.append(f"参考：若补下载 {short:.1f}GB，分享率约 {ra:.2f}" + ("（会低于 1）" if ra < 1 else ""))
            elif "上传" in label and short_gb is not None:
                short = float(short_gb)
                target = round(up / (1024 ** 3) + short, 2)
                entry.update({
                    "kind": "upload",
                    "short_gb": short,
                    "task_name": f"{site_name}-考核刷流",
                    "params": {
                        "task_type": "brush",
                        "goal_value": target,
                        "brush_interval": 5,
                        "check_interval": 1,
                    },
                })
                notes.append(f"目标:本站上传 {target:.2f}GB(当前 {up / (1024 ** 3):.2f}GB,还差 {short:.2f}GB)达到后自动停")
            elif ("魔力" in label or "积分" in label) and short_num is not None:
                short = float(short_num)
                target = round(bonus + short, 1)
                entry.update({
                    "kind": "bonus",
                    "short_num": short,
                    "task_name": f"{site_name}-考核魔力",
                    "params": {"task_type": "bonus", "goal_value": target, "brush_interval": 5, "check_interval": 1},
                })
                notes.append(f"目标:本站魔力 {target:.0f}(当前 {bonus:.0f},还差 {short:.0f})达到后自动停;魔力靠多挂种 / 挂老种")
            else:
                # 简版考核（没给具体数值）：只放行「上传/下载/魔力/积分」类，不硬套「保持做种」
                if any(k in label for k in ("上传", "下载", "魔力", "积分", "分享率")):
                    entry["kind"] = "info"
                    entry["label"] = f"{label}（未通过）"
                    notes.append("该站考核区块没给具体数值，去「做种明细」看站点实时数据")
                else:
                    entry["kind"] = "hold"
                    notes.append("靠「保持做种 + 增加做种数(多辅种)」改善,不需要新任务;别停该站任务、别删种")
            if left is not None and float(left) <= 3:
                notes.append(f"⏰ 考核只剩 {float(left):.1f} 天,尽快处理")
            entry["notes"] = notes
            plan.append(entry)
        return plan

    # ------------------------------------------------------------- 站点签到 / 登录
    def _signin_cfg_view(self) -> Dict[str, Any]:
        """签到配置视图(/status 用;不含逐站状态,轻)。"""
        cfg = dict(getattr(self, "_signin_cfg", {}) or {})
        today: Dict[str, Any] = {}
        try:
            today = (self._signin.records().get(datetime.now().strftime("%Y-%m-%d")) or {}) if getattr(self, "_signin", None) else {}
        except Exception:  # noqa: BLE001
            today = {}
        cfg["today"] = today
        return cfg

    def get_signin_state(self, days: int = 7) -> Response:
        """站点签到/登录状态(今日 + 近 N 天记录)。"""
        try:
            engine = getattr(self, "_signin", None)
            if engine is None:
                return Response(success=True, data={"enabled": False, "sites": [], "records": []})
            return Response(success=True, data=engine.state(days=int(days or 7)))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"签到状态读取失败:{err}")

    def run_signin(self, kind: str = "sign", site_ids: str = "", force: bool = False) -> Response:
        """立即签到/登录一次。site_ids 逗号分隔;force=true 忽略「今日已成功」跳过。"""
        cfg = getattr(self, "_signin_cfg", {}) or {}
        if not cfg.get("enabled") and not bool(force):
            return Response(success=False, message="「站点签到」未开启(设置 → 签到)")
        engine = getattr(self, "_signin", None)
        if engine is None:
            return Response(success=False, message="签到组件未初始化")
        lock = getattr(self, "_signin_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._signin_lock = lock
        if not lock.acquire(blocking=False):
            return Response(success=False, message="已有签到任务在跑,稍后再试")
        try:
            ids = [x.strip() for x in str(site_ids or "").split(",") if x.strip()]
            out = engine.run(kind=str(kind or "sign"), site_ids=ids or None, force=bool(force))
            return Response(success=bool(out.get("ok")), message=str(out.get("message") or "已执行"), data=out)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"签到执行失败:{err}")
        finally:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass

    def signin_watch(self) -> None:
        """签到 worker：① 先补到期的失败重试（按 PV 节奏，间隔+抖动）；② 再按「签到间隔」跑全量。

        注：调度器按 min(签到间隔, 15min) 唤醒本函数——空闲 tick 几乎零成本（不发请求），
        只有真的到点才发请求（重试请求同样被 collect 配额闸门管着）。
        """
        cfg = getattr(self, "_signin_cfg", {}) or {}
        engine = getattr(self, "_signin", None)
        if not cfg.get("enabled") or engine is None:
            return
        try:
            if not engine.should_run_now():
                return
            lock = getattr(self, "_signin_lock", None)
            if lock is None:
                lock = threading.Lock()
                self._signin_lock = lock
            if not lock.acquire(blocking=False):
                return
            try:
                # ① 到期的失败重试（只补签到；已经成功的会被 already_done 跳过）
                try:
                    due = engine.retry_due() if cfg.get("sites") else []
                except Exception:  # noqa: BLE001
                    due = []
                if due:
                    self._log(f"签到重试：{len(due)} 个站点到期补一次", "info")
                    engine.run(kind="sign", site_ids=due)
                # ② 全量：距上次全量跑够「签到间隔」才跑
                now = time.time()
                try:
                    last_full = float(self.get_data("signin_last_full") or 0)
                except Exception:  # noqa: BLE001
                    last_full = 0.0
                gap = float(cfg.get("interval") or SIGNIN_INTERVAL_MINUTES) * 60.0
                if now - last_full >= gap:
                    if cfg.get("sites"):
                        engine.run(kind="sign")
                    if cfg.get("login_sites"):
                        engine.run(kind="login")
                    self.save_data(key="signin_last_full", value=now)
                    # ★ 7.17.0 账号保活：站点「多久不登入删号」临近 → 当日提醒一次（快照 6h 内零请求）
                    try:
                        self._alert_keepalive(engine)
                    except Exception as err:  # noqa: BLE001
                        self._log(f"账号保活检查失败:{err}", "debug")
            finally:
                lock.release()
        except Exception as err:  # noqa: BLE001
            self._log(f"签到 worker 失败:{err}", "warning")

    def _alert_keepalive(self, engine: Any) -> None:
        """账号保活提醒：剩 ≤ 临界天数 → 当日提醒一次。

        ★ 只提醒，不替主人做任何事：站点口径「第三方工具间接存取不算登入」，
          保活只能主人用浏览器 / 官方 App 亲自登。
        """
        snap = engine.keepalive_check()
        warns: List[Dict[str, Any]] = list(snap.get("warnings") or [])
        if not warns:
            return
        day = datetime.now().strftime("%Y-%m-%d")
        try:
            if str(self.get_data("keepalive_alert_day") or "") == day:
                return
            self.save_data(key="keepalive_alert_day", value=day)
        except Exception:  # noqa: BLE001
            return
        lines = [
            f"⚠️ {w.get('site_name')}：最后登入 {w.get('last_login') or '未知'}，"
            f"距不登入删号还有 {w.get('days_left')} 天"
            for w in warns
        ]
        self._log("账号保活提醒：" + "；".join(lines), "warning")
        hint = str((warns[0] or {}).get("agent") or "")
        try:
            self.post_message(
                title="魔流·账号保活提醒",
                text="\n".join(lines) + (("\n\n" + hint) if hint else ""),
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"保活提醒发送失败:{err}", "debug")

    def _exam_sites(self, only_site_id: int = 0) -> Dict[int, Dict[str, Any]]:
        """考核要看的站点集合:**所有已配置 cookie 的站点**(不只任务站点)+ 任务站点兜底。

        若设置里选了「考核站点」(`exam_sites`)→ 只看这些站(**选多少有多少**)。
        """
        only = int(only_site_id or 0)
        picked: List[str] = [str(x) for x in (self._live_cfg.get("exam_sites") or [])]
        if only:
            if picked and str(only) not in picked:
                return {}
            meta = (self._live_sites(only_site_id=only) or {}).get(only)
            if meta:
                return {only: meta}
            return {only: {"site_id": only, "site_name": self._live_site_name(only), "local_managed": 0, "tasks": []}}
        sites: Dict[int, Dict[str, Any]] = {}
        for item in self._list_sites() or []:
            try:
                sid = int(item.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if not sid or not self._site_has_cookie(sid):
                continue
            if picked and str(sid) not in picked:
                continue
            sites[sid] = {
                "site_id": sid,
                "site_name": item.get("name") or self._live_site_name(sid),
                "local_managed": 0,
                "tasks": [],
            }
        for sid, meta in (self._live_sites() or {}).items():
            if picked and str(sid) not in picked:
                continue
            sites.setdefault(sid, meta)
        return sites

    def get_exam_state(
        self, force: bool = False, site_id: int = 0, include_pass: bool = False
    ) -> Response:
        """新手考核汇总(只读)。**已全部通过的考核默认不返回**(include_pass=true 才带)。

        ★ 总开关 `exam_enabled` 关闭时**不解析也不返回**(跟云盘归档一个路子)。
        """
        if not bool(getattr(self, "_live_cfg", {}).get("exam_enabled", False)):
            return Response(
                success=True,
                message="「新手考核」未开启(设置 → 考核)",
                data={"sites": [], "count": 0, "enabled": False, "ts": time.time()},
            )
        if not bool(include_pass):
            include_pass = bool(self._live_cfg.get("exam_include_pass", False))
        sites = self._exam_sites(only_site_id=int(site_id or 0))
        rows: List[Dict[str, Any]] = []
        for sid, meta in sites.items():
            snap = self._live_snapshot(sid, local_managed=meta.get("local_managed"), force=bool(force))
            live = snap.get("live") or {}
            exam = live.get("exam") or None
            if not exam:
                continue
            failed = exam.get("failed") or []
            if not failed and not bool(include_pass):
                continue
            rows.append(
                {
                    "site_id": sid,
                    "site_name": meta.get("site_name"),
                    "exam": exam,
                    "plan": self._exam_action_plan(sid, live, meta.get("tasks") or []),
                    "tasks": meta.get("tasks") or [],
                    "live_ok": bool(live.get("ok")),
                    "upload": live.get("upload"),
                    "download": live.get("download"),
                    "bonus": live.get("bonus"),
                    "ratio": live.get("ratio"),
                    "seeding": live.get("seeding"),
                }
            )
        rows.sort(key=lambda r: (float((r.get("exam") or {}).get("days_left") or 9999.0)))
        return Response(success=True, data={"sites": rows, "count": len(rows), "ts": time.time(), "enabled": True})

    def _exam_payload_kwargs(
        self, name: str, site_id: int, site_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """用「默认任务模板」做底、叠考核参数 → MagicFlowTaskPayload 构造参数。"""
        try:
            fields = set(MagicFlowTaskPayload.model_fields.keys())
        except Exception:  # noqa: BLE001
            fields = set()
        kw: Dict[str, Any] = {}
        for k, v in (getattr(self, "_defaults", {}) or {}).items():
            if k in fields and v not in (None, ""):
                kw[k] = v
        kw.pop("id", None)
        kw.update({
            "name": name,
            "site_id": int(site_id),
            "site_name": site_name,
            "brush_tag": "",  # ★ 5.11.5：留空 → 由 create_task 按「站点+任务类型」派生（魔流-<站点>-<刷流|魔力>）
            "task_type": str(params.get("task_type") or "bonus"),
            "brush_interval": int(params.get("brush_interval") or 5),
            "check_interval": int(params.get("check_interval") or 1),
            "goal_value": params.get("goal_value"),
            "download_target_gb": params.get("download_target_gb"),
            "allow_unfree_download": bool(params.get("allow_unfree_download", False)),
            "run_mode": "running",
            "enabled": True,
        })
        for extra in ("purge_unfree_incomplete",):
            if extra in params:
                kw[extra] = bool(params.get(extra))
        # 下载器兜底：默认模板 downloader 为空时会被上面的 v not in (None, "") 过滤掉，
        # 而 MagicFlowTaskPayload.downloader 是必填 → 一键考核建任务曾报
        # 「downloader Field required」。这里按「可用下载器首个 → qbittorrent」兜底。
        if not str(kw.get("downloader") or "").strip():
            try:
                opts = self._list_downloaders() or []
                kw["downloader"] = str((opts[0] or {}).get("value") or "qbittorrent")
            except Exception:  # noqa: BLE001
                kw["downloader"] = "qbittorrent"
        return kw

    def exam_act(self, site_id: int = 0, kind: str = "", confirm: bool = False) -> Response:
        """一键起任务(**必须 confirm=true**):按考核未通过项创建/启用一个任务。"""
        if not bool(confirm):
            return Response(success=False, message="未确认:不会创建任务(需 confirm=true)")
        if not bool(getattr(self, "_live_cfg", {}).get("exam_enabled", False)):
            return Response(success=False, message="「新手考核」未开启(设置 → 考核)")
        sid = int(site_id or 0)
        if not sid:
            return Response(success=False, message="缺少 site_id")
        kind = str(kind or "").strip().lower()
        if kind == "download":
            return Response(success=False, message="本插件不做下载任务（下载类考核请自行安排）")
        if kind not in ("upload", "download", "bonus", "hold"):
            return Response(success=False, message="kind 只能是 upload/download/bonus/hold")
        live = (self._live_snapshot(sid) or {}).get("live") or {}
        plan = self._exam_action_plan(sid, live, [])
        item = next((p for p in plan if p.get("kind") == kind), None)
        if item is None:
            return Response(success=False, message="该考核项当前无需处理(已通过 / 未识别)")
        if kind == "hold":
            return Response(
                success=True,
                message="该项不需要创建任务:保持做种 + 多辅种即可",
                data={"noop": True, "notes": item.get("notes") or []},
            )
        name = str(item.get("task_name") or "")
        params = dict(item.get("params") or {})
        if not name:
            return Response(success=False, message="未生成任务名,已中止")
        dl = str((getattr(self, "_defaults", {}) or {}).get("downloader") or "").strip()
        if not dl:
            try:
                dl = "qbittorrent"
            except Exception:  # noqa: BLE001
                dl = "qbittorrent"
        sp = str((getattr(self, "_defaults", {}) or {}).get("save_path") or "").strip()
        site_name = self._live_site_name(sid)
        existing = next(
            (
                t
                for t in self._task_configs.values()
                if int(getattr(t, "site_id", 0) or 0) == sid and str(getattr(t, "name", "")) == name
            ),
            None,
        )
        try:
            if existing is not None:
                for key, val in params.items():
                    setattr(existing, key, val)
                existing.run_mode = RUN_MODE_RUNNING
                existing.enabled = enabled_of_run_mode(RUN_MODE_RUNNING)
                self._save_config()
                self._refresh_scheduler()
                self._invalidate_summary()
                if kind == "download":
                    try:
                        self._store.set_exam_download(existing.id, None, "重置基线(重新开始考核下载)")
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    self._apply_task_traffic_limit()
                    self._apply_seed_upload_limit()
                except Exception:  # noqa: BLE001
                    pass
                return Response(
                    success=True,
                    message=f"已更新并启用任务「{name}」",
                    data={"task_id": existing.id, "name": name, "updated": True, "notes": item.get("notes") or []},
                )
            payload = MagicFlowTaskPayload(**self._exam_payload_kwargs(name, sid, site_name, params))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"参数构建失败:{err}")
        res = self.create_task(payload)
        data = getattr(res, "data", None) or {}
        tid = ""
        if isinstance(data, dict):
            tid = str((data.get("task") or {}).get("id") or data.get("id") or "")
        if not tid:
            tid = next(
                (
                    t.id
                    for t in self._task_configs.values()
                    if int(getattr(t, "site_id", 0) or 0) == sid and str(getattr(t, "name", "")) == name
                ),
                "",
            )
        if tid:
            try:
                self._store.set_exam_download(tid, None, "新建(基线下轮自动记录)")
            except Exception:  # noqa: BLE001
                pass
            if not sp:
                self._task_configs[tid].run_mode = RUN_MODE_SEEDING
                self._task_configs[tid].enabled = enabled_of_run_mode(RUN_MODE_SEEDING)
                self._save_config()
                self._refresh_scheduler()
                self._invalidate_summary()
                return Response(
                    success=False,
                    message=(
                        f"已创建任务「{name}」(暂设「做种中」):**未配置默认保存目录**,"
                        "请先到「设置 → 下载目录」填任务保存目录,再启用任务"
                    ),
                    data={"task_id": tid, "name": name, "need_save_path": True, "notes": item.get("notes") or []},
                )
        return Response(
            success=bool(getattr(res, "success", False)),
            message=str(getattr(res, "message", "") or f"已创建任务「{name}」"),
            data={"task_id": tid, "name": name, "notes": item.get("notes") or []},
        )
