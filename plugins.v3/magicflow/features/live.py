# -*- coding: utf-8 -*-
"""魔流 · live —— 站点监控（可达性、流量兜底、下载中干预）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional


from app.schemas import Response

from ..live_stats import title_match
from ..persistence import OperationItem
from ..sitecap import (
    SiteCap,
    SiteCapRegistry,
    norm_domain,
)
from ..sitestore import get_site_store


from ..common import (
    SILENT_HOST_TASK_ID,
    LIVE_ALERT_COOLDOWN_MIN,
    LIVE_DOWNLOAD_ALERT_MB,
    LIVE_INTERVAL_MINUTES,
    LIVE_RATIO_TARGET,
    enabled_of_run_mode,
    RUN_MODE_SEEDING,
    task_is_running,
    run_mode_of,
)


class LiveMixin:
    """live 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------
    # 站点实时数据 + 站点流量监控
    #   MoviePilot 的站点账号数据靠它自己的「站点数据刷新」(默认 6h)写库 → 魔流拿它做
    #   决策(任务目标达标 / 救号分享率 / 兑换提醒 / 下载量异常)太滞后。这里直连站点用户栏
    #   拿实时值(站点级缓存 + single-flight,抓不到回退 MP 数据),并监控「下载量在涨」。
    # ---------------------------------------------------------
    def _live_site_name(self, site_id: int) -> str:
        try:
            site = self._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            site = None
        if not site:
            return f"站点 {site_id}"
        return str(
            getattr(site, "name", "") or getattr(site, "domain", "") or f"站点 {site_id}"
        ).strip() or f"站点 {site_id}"

    def _live_sites(self, enabled_only: bool = False, only_site_id: int = 0) -> Dict[int, Dict[str, Any]]:
        """收集任务涉及的站点(含各任务本地托管数)。

        - `enabled_only=True`:只取「在跑」的任务（运行中 + 做种中；只有 stopped 跳过），供监控 worker 用，避免打闲置站点。
        - `only_site_id`:只要指定站点(供前端只看当前任务站点)。
        """
        out: Dict[int, Dict[str, Any]] = {}
        try:
            stats_by_id = self._runtime_stats_bulk(list(self._task_configs.values()))
        except Exception:  # noqa: BLE001
            stats_by_id = {}
        for task in self._task_configs.values():
            # ★ X11：不再用派生字段 enabled，一律走契约①的访问器。
            _mode = run_mode_of(task)
            if enabled_only and _mode == "stopped":
                continue
            try:
                sid = int(getattr(task, "site_id", 0) or 0)
            except (TypeError, ValueError):
                sid = 0
            if not sid or (only_site_id and sid != int(only_site_id)):
                continue
            item = out.setdefault(
                sid,
                {
                    "site_id": sid,
                    "site_name": self._live_site_name(sid),
                    "local_managed": 0,
                    "has_running": False,
                    "tasks": [],
                },
            )
            managed = int((stats_by_id.get(task.id) or {}).get("seeding_count", 0) or 0)
            item["local_managed"] += managed
            item["tasks"].append(
                {
                    "id": task.id,
                    "name": task.name,
                    "managed": managed,
                    "running": _mode == "running",
                }
            )
            if _mode == "running":
                item["has_running"] = True
        return out

    def _live_snapshot(
        self, site_id: int, local_managed: Optional[int] = None, force: bool = False
    ) -> Dict[str, Any]:
        """实时数据 + 速率 + 告警 的组合快照(绝不抛出)。"""
        try:
            return self._live.snapshot(
                int(site_id), cfg=dict(self._live_cfg or {}), local_managed=local_managed, force=force
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"站点实时数据获取失败(站点 {site_id}):{err}", "warning")
            return {"live": {"ok": False}, "rates": {}, "alerts": [], "level": "ok"}

    def get_live_state(self, force: bool = False, site_id: int = 0) -> Response:
        """站点实时数据 + 流量监控快照(只读,不做任何写操作)。

        `site_id` 给出时只返回该站点(前端只看当前任务的站点,少打站点)。
        """
        sites = self._live_sites(only_site_id=int(site_id or 0))
        rows: List[Dict[str, Any]] = []
        for sid, meta in sites.items():
            snap = self._live_snapshot(sid, local_managed=meta.get("local_managed"), force=bool(force))
            rows.append(
                {
                    "site_id": sid,
                    "site_name": meta.get("site_name"),
                    "local_managed": meta.get("local_managed"),
                    "tasks": meta.get("tasks") or [],
                    "live": snap.get("live") or {},
                    "rates": snap.get("rates") or {},
                    "alerts": snap.get("alerts") or [],
                    "level": snap.get("level") or "ok",
                }
            )
        return Response(
            success=True,
            data={
                "cfg": {
                    "enabled": bool(self._live_cfg.get("enabled", True)),
                    "interval_minutes": float(self._live_cfg.get("interval") or LIVE_INTERVAL_MINUTES),
                    "download_alert_mb": float(self._live_cfg.get("download_alert_mb") or LIVE_DOWNLOAD_ALERT_MB),
                    "ratio_target": float(self._live_cfg.get("ratio_target") or LIVE_RATIO_TARGET),
                    "auto_stop": bool(self._live_cfg.get("auto_stop", False)),
                    "kill_unfree": bool(self._live_cfg.get("kill_unfree", True)),
                    "kill_delete_files": bool(self._live_cfg.get("kill_delete_files", True)),
                    "notify": bool(self._live_cfg.get("notify", True)),
                    "exam_enabled": bool(self._live_cfg.get("exam_enabled", False)),
                },
                "sites": rows,
                "ts": time.time(),
            },
        )

    def _live_kill_unfree(self, site_id: int, site_name: str) -> Dict[str, Any]:
        """★ 下载量异常增长时:去站点「正在下载」列表,把**非免费**的种子从下载器干掉。

        安全阀(三重):1 只动**下载中**的种(state ∈ QB_DOWNLOADING_STATES);
        2 名称必须完全匹配;3 体积必须对得上(±2%)--避免误删同名资源。
        """
        out: Dict[str, Any] = {"checked": 0, "killed": [], "errors": []}
        # 豁免:该站存在「考核下载模式」任务 → 下非免费种是**有意为之**,绝不清理
        try:
            for _t in self._task_configs.values():
                if int(getattr(_t, "site_id", 0) or 0) == int(site_id) and self._exam_download_active(_t):
                    out["skipped"] = f"考核下载任务「{_t.name}」进行中,豁免"
                    self._log(
                        f"魔流:[站点监控] {site_name} 有考核下载任务进行中 → 跳过「清非免费下载种」", "info"
                    )
                    return out
        except Exception:  # noqa: BLE001
            pass
        try:
            leech = self._live.leeching(int(site_id), force=True)
        except Exception as err:  # noqa: BLE001
            out["errors"].append(f"取正在下载列表失败:{err}")
            return out
        if not leech.get("ok"):
            out["errors"].append(f"取正在下载列表失败:{leech.get('error')}")
            return out
        rows = [r for r in (leech.get("rows") or []) if not r.get("free")]
        out["checked"] = len(rows)
        if not rows:
            return out
        try:
            downloader = self._get_downloader()
            dl_torrents, err = downloader.get_torrents(status="downloading")
        except Exception as err:  # noqa: BLE001
            out["errors"].append(f"读下载器失败:{err}")
            return out
        if err:
            out["errors"].append(f"读下载器失败:{err}")
            return out
        # ★ 豁免「跨站取种的种」：它们是**故意**下载的（免费，有专门兜底在管），
        #   别让通用「清非免费下载种」按名字误伤（站点那条促销标记偶尔读不到）。
        try:
            _cs_skip = set(self._crossseed_pending().items().keys()) | self._crossseed_source_hashes()
        except Exception:  # noqa: BLE001
            _cs_skip = set()
        # 名称匹配(站上标题常见「点 vs 空格」「带年代」差异 → 走归一化模糊匹配)+ 体积校对
        victims: List[str] = []
        name_by_hash: Dict[str, Any] = {}
        for row in rows:
            row_name = str(row.get("name") or "")
            row_size = float(row.get("size") or 0)
            if not row_name:
                continue
            for t in dl_torrents or []:
                t_title = str(getattr(t, "title", "") or "")
                if not t_title or not title_match(row_name, t_title):
                    continue
                try:
                    t_size = float(getattr(t, "size", 0) or 0)
                except (TypeError, ValueError):
                    t_size = 0.0
                if row_size > 0 and t_size > 0 and abs(t_size - row_size) / max(row_size, 1.0) > 0.02:
                    continue
                h = str(getattr(t, "hash", "") or "").strip().lower()
                if h and h in _cs_skip:
                    continue
                if h and h not in victims:
                    victims.append(h)
                    name_by_hash[h] = {"hash": h, "name": t_title, "size": t_size}
        if not victims:
            return out
        try:
            ok, err2 = downloader.delete_torrents(
                hashes=victims, delete_file=bool(self._live_cfg.get("kill_delete_files", True))
            )
            if err2:
                out["errors"].append(str(err2))
        except Exception as err:  # noqa: BLE001
            out["errors"].append(f"删除失败:{err}")
            return out
        for h in victims:
            info2 = name_by_hash.get(h) or {}
            out["killed"].append({"hash": h, "name": info2.get("name", ""), "size": info2.get("size", 0.0)})
        if out["killed"]:
            self._log(
                f"站点监控 [{site_name}] 下载量异常 → 清除非免费下载种 {len(out['killed'])} 个:"
                + ";".join(f"{k['name'][:60]}" for k in out["killed"][:5]),
                "warning",
            )
        return out

    def live_watch(self) -> None:
        """站点流量监控(worker):采样 → 告警(可配自动止损)。

        ⚠ 自动止损仅把该站「运行中」的任务切到「做种中」(停调度、只保做种),
        **不删种、不搬种**,与主人「先尽量刷流」的纪律一致。
        """
        if not bool(self._live_cfg.get("enabled", True)):
            return
        try:
            self._live_watch_impl()
        except Exception as err:  # noqa: BLE001
            self._log(f"站点流量监控异常:{err}", "warning")

    def _live_watch_impl(self) -> None:
        sites = self._live_sites(enabled_only=True)
        if not sites:
            return
        try:
            seen = self.get_data("live_alerts") or {}
        except Exception:  # noqa: BLE001
            seen = {}
        if not isinstance(seen, dict):
            seen = {}
        now = time.time()
        cooldown = float(LIVE_ALERT_COOLDOWN_MIN) * 60.0
        changed = False
        for sid, meta in sites.items():
            snap = self._live_snapshot(sid, local_managed=meta.get("local_managed"))
            live = snap.get("live") or {}
            if not live.get("ok"):
                continue
            fresh: List[Dict[str, Any]] = []
            for alert in snap.get("alerts") or []:
                key = f"{sid}:{alert.get('kind')}"
                if now - float(seen.get(key, 0) or 0) < cooldown:
                    continue
                seen[key] = now
                changed = True
                fresh.append(alert)
            if not fresh:
                continue
            name = str(meta.get("site_name") or f"站点 {sid}")
            # ★ 下载量异常增长 → 去站点「正在下载」列表,把非免费的种从下载器干掉
            #   ★ X11(3.37.7):动手只限「运行中」任务所在的站(运行中有刷流下载=可能白烧);
            #     「做种中」的站只采样/告警、不动手(做种模式本就不该有插件发起的下载)。
            kill_info = ""
            killed_rows: List[Dict[str, Any]] = []
            if (
                bool(meta.get("has_running"))
                and self._promo_guard_on()
                and bool(self._live_cfg.get("kill_unfree", True))
                and any(a.get("kind") == "download_rising" for a in fresh)
            ):
                kres = self._live_kill_unfree(sid, name)
                killed = kres.get("killed") or []
                killed_rows = [k for k in killed if isinstance(k, dict)]
                if killed:
                    gb = sum(float(k.get("size") or 0) for k in killed) / (1024 ** 3)
                    kill_info = (
                        f"已清除非免费下载种 {len(killed)} 个({gb:.2f}GB):"
                        + "、".join(str(k.get("name") or "")[:50] for k in killed[:3])
                    )
                elif kres.get("errors"):
                    kill_info = "清除非免费下载种失败:" + ";".join(kres["errors"][:2])
            for alert in fresh:
                self._log(
                    f"站点监控 [{name}] {alert.get('text')}",
                    "warning" if alert.get("level") == "warn" else "info",
                )
            if self._store:
                try:
                    self._store.journal.record(
                        task_id=str((meta.get("tasks") or [{}])[0].get("id") or ""),
                        kind="live",
                        items=[
                            OperationItem(
                                hash="",
                                title=f"站点流量监控 · {name}",
                                reason=";".join(
                                    [str(a.get("text") or "") for a in fresh]
                                    + ([kill_info] if kill_info else [])
                                ),
                            )
                        ],
                    )
                except Exception as err:  # noqa: BLE001
                    self._log(f"记录站点监控事件失败:{err}", "warning")
            # ★ 止损删掉的种：逐条落「操作记录」（Master：清理逻辑必须有操作记录 + 详情）
            if killed_rows and self._store:
                _tid = str((meta.get("tasks") or [{}])[0].get("id") or SILENT_HOST_TASK_ID)
                self._journal_deletions({_tid: [
                    OperationItem(
                        hash=str(k.get("hash") or ""),
                        title=str(k.get("name") or ""),
                        reason=f"站点监控[{name}]：站内下载量异常增长，该种非免费（白烧流量）→ 删除",
                        size_gb=round(float(k.get("size") or 0.0) / (1024 ** 3), 3),
                        source="live",
                    )
                    for k in killed_rows
                ]}, log_prefix="站点监控止损")
            if bool(self._live_cfg.get("notify", True)):
                try:
                    gb = 1024 ** 3
                    self.post_message(
                        title=f"魔流·站点监控({name})",
                        text="\n".join(
                            [f"· {a.get('text')}" for a in fresh]
                            + ([f"· {kill_info}"] if kill_info else [])
                        )
                        + (
                            "\n\n实时:"
                            f"上传 {float(live.get('upload') or 0) / gb:.2f}GB / "
                            f"下载 {float(live.get('download') or 0) / gb:.2f}GB / "
                            f"分享率 {live.get('ratio')}"
                        ),
                    )
                except Exception as err:  # noqa: BLE001
                    self._log(f"站点监控通知失败:{err}", "warning")
            # 自动止损:下载量在涨 → 该站任务切「做种中」(停调度、不删种)
            if bool(self._live_cfg.get("auto_stop", False)) and any(
                a.get("kind") == "download_rising" for a in fresh
            ):
                stopped: List[str] = []
                for tinfo in meta.get("tasks") or []:
                    task = self._task_configs.get(str(tinfo.get("id") or ""))
                    if task is None or not task_is_running(task):
                        continue
                    task.run_mode = RUN_MODE_SEEDING
                    task.enabled = enabled_of_run_mode(RUN_MODE_SEEDING)
                    stopped.append(task.name)
                    self._spawn_run_mode_apply(task, "seeding")
                if stopped:
                    self._log(
                        f"站点监控 [{name}] 下载量异常增长 → 自动切「做种中」:{'、'.join(stopped)}",
                        "warning",
                    )
                    try:
                        self._save_config()
                        self._refresh_scheduler()
                        self._invalidate_summary()
                    except Exception as err:  # noqa: BLE001
                        self._log(f"自动止损应用失败:{err}", "warning")
        if changed:
            try:
                self.save_data("live_alerts", seen)
            except Exception:  # noqa: BLE001
                pass

    def sitecaps(self) -> SiteCapRegistry:
        """站点类型/能力注册表(懒加载;识别结果持久化在 ``mf_site.caps``)。"""
        reg = getattr(self, "_site_cap_reg", None)
        if reg is None:
            _st = get_site_store(self)
            _get, _save = _st.callbacks("site_caps")
            over: Dict[str, Any] = {}
            try:
                raw = _st.get("sitecap_override")
                if isinstance(raw, dict):
                    over = raw
            except Exception:  # noqa: BLE001
                over = {}
            reg = self._site_cap_reg = SiteCapRegistry(
                get_data=_get,
                save_data=_save,
                override=over,
                fetch_provider=self,
            )
        return reg

    def _site_cap(self, site_id: int, probe: bool = False) -> SiteCap:
        """取某站的类型/能力(无站点对象时返回未知)。"""
        try:
            site = self._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            site = None
        if site is None:
            return SiteCap(domain="")

        def _gate() -> bool:
            # 探针也要走 PV 闸门:被封/超预算就不打站点(否则又是一条绕过配额的路)
            sid = int(site_id)
            if self._pv_block_reason(sid):
                return False
            if not self._pv_allow(sid, "sitecap", want=1):
                self._log(
                    f"魔流 站点 {getattr(site, 'domain', sid)} 识别探针跳讨"
                    f"(PV 预算将尽 {self._pv_ledger().today_total(sid)}/{self._pv_budget(sid)})",
                    "warning",
                )
                return False
            self._pv_spend(sid, "sitecap", 1)
            return True

        return self.sitecaps().ensure(site, probe=bool(probe), gate=_gate)

    def debug_site_caps(self, probe: bool = False) -> Response:
        """站点类型/能力识别结果;``probe=true`` 时对未识别/过期的站联网探测一次。"""
        try:
            caps = self.sitecaps()
            rows: List[Dict[str, Any]] = []
            for item in self._list_sites():
                sid = item.get("id")
                if sid is None:
                    continue
                try:
                    site = self._get_site(int(sid))
                except Exception:  # noqa: BLE001
                    site = None
                if site is None:
                    continue
                # 与探测路径保持同一套 key（都用 Site.domain 规范化），避免同一站存成两条
                dom = norm_domain(getattr(site, "domain", "") or item.get("domain") or "")
                cap = self._site_cap(int(sid), probe=bool(probe)) if probe else caps.get(dom)
                row = cap.to_dict()
                row["site_id"] = sid
                row["site_name"] = item.get("name") or ""
                rows.append(row)
            return Response(success=True, data={"items": rows})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"站点识别失败:{err}")
