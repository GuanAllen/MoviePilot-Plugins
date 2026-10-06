# -*- coding: utf-8 -*-
"""魔流 · registry —— 功能模块（Feature）注册表 + 协议（契约③）。

**一个职责 = 一个模块 = 一个入口**：工作台上每个「功能页」在这里登记一次，
后端据此产出状态（是否开启 / 数据端点），前端 `MF_PAGES` 只负责展示与分发。

铁律（`docs/CONTRACTS.md` 契约③）：
  * 每个 Feature 必须声明 `key / name / scope`；`key` **必须与前端 `MF_PAGES` 的 key 一字不差**
    （`tools/check_pages.py` 会对齐，防漂移）。
  * 功能页一律**全局单例**（`scope="global"`）或**只读视图**（`scope="view"`）；
    任务级字段**不允许**出现在这里。
  * Feature **不得**直接删种/改任务状态 —— 删除只归「清理」「静默池」，
    任务状态只归「任务」入口。
  * 加功能 = 改 `FEATURES` + 前端 `MF_PAGES`（两处，别的地方不用动）。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.schemas import Response

from ..common import task_is_participating, CROSSSEED_TASK_ID

SCOPE_GLOBAL = "global"   # 全局单例能力（有自己的开关）
SCOPE_VIEW = "view"       # 只读视图（无开关，随时可看）


@dataclass(frozen=True)
class FeatureSpec:
    """一个功能页的登记项。"""

    key: str                              # ★ 与前端 MF_PAGES.key 一致
    name: str                             # 显示名
    scope: str                            # global | view
    api: str = ""                         # 只读端点（前端拉数据用）
    cfg_attr: str = ""                    # 配置对象属性名（读开关键）
    enabled_key: str = "enabled"          # 配置里的开关键
    default_enabled: Optional[bool] = None
    enabled_probe: str = ""               # 需要现算时：self 上的方法名（返回 bool/None）
    tick: str = ""                        # 调度入口方法名（若有）
    note: str = ""                        # 边界/说明


# ★ 顺序 = 工作台展示顺序；key 必须与 `src/components/MagicFlowWorkbench.vue` 的 MF_PAGES 一致
FEATURES: tuple = (
    FeatureSpec("recommend", "推荐", SCOPE_GLOBAL, api="/recommend",
                cfg_attr="_recommend_cfg", default_enabled=True,
                tick="recommend_scan", note="找值得入库的片 + 通知（全局）"),
    FeatureSpec("exam", "新手考核", SCOPE_GLOBAL, api="/exam",
                cfg_attr="_live_cfg", enabled_key="exam_enabled", default_enabled=False,
                note="站点考核进度与下载模式（全局）"),
    FeatureSpec("signin", "签到", SCOPE_GLOBAL, api="/signin",
                cfg_attr="_signin_cfg", default_enabled=False,
                tick="signin_watch", note="自动签到（全局）"),
    FeatureSpec("cloud", "云盘归档", SCOPE_GLOBAL, api="/cloud",
                cfg_attr="_cloud_cfg", default_enabled=False,
                tick="run_cloud", note="上传云盘 + 生成 STRM（全局）"),
    FeatureSpec("douban", "豆瓣评分", SCOPE_GLOBAL, api="/douban_service",
                note="外部服务 magicflow-douban 的库/爬虫状态（无可开关）"),
    FeatureSpec("crossseed", "跨站取种", SCOPE_GLOBAL, api="/crossseed",
                enabled_probe="_crossseed_feature_enabled",
                note="按任务开（任务·高级·跨站），此处只看是否有任务在用"),
    FeatureSpec("claim", "认领", SCOPE_GLOBAL, api="/claim",
                enabled_probe="_claim_feature_enabled",
                note="把在做的种在站点侧认领换权益（默认关；写动作需确认）"),
    FeatureSpec("silent", "静默池", SCOPE_GLOBAL, api="/silent/pool",
                note="无主种池：静默-新/资源/普通 + H&R 保挂 + 记录（由常驻「静默托管」worker 承担）"),
    FeatureSpec("sitereport", "站点报表", SCOPE_VIEW, api="/site/seeds",
                note="站点级种子报表：逐条种子状态（分类/保护/账单/qB）+ H&R 摘要（只读视图）"),
    FeatureSpec("hrbills", "H&R账单", SCOPE_VIEW, api="/hr/bills",
                note="H&R 账单按站分组：欠债/状态分布/need_left/in_qb/missing/per_torrent_hr/规则来源（只读）"),
    FeatureSpec("seedhealth", "挂种健康", SCOPE_VIEW, api="/health/scan",
                note="挂种健康度自检：逐文件核盘找空转/缺文件的种 + 其中欠 H&R 的风险（只读）"),
    FeatureSpec("ceiling", "站点容量", SCOPE_VIEW, api="/status",
                note="各站魔力上限占用（只读视图）"),
    FeatureSpec("ops", "操作记录", SCOPE_VIEW, api="/operations",
                note="跨任务操作流水（只读视图；单任务流水只在任务详情）"),
    FeatureSpec("settings", "插件设置", SCOPE_GLOBAL, api="",
                note="全局设置（唯一配置入口）"),
)


class RegistryMixin:
    """功能注册表（契约③）：登记 + 状态查询。"""

    def feature_keys(self) -> List[str]:
        """登记在案的功能 key（供前端/检查工具对齐）。"""
        return [sp.key for sp in FEATURES]

    def _feature_enabled(self, sp: FeatureSpec) -> Optional[bool]:
        """读某个功能的开启状态；读不到 → None（只读视图 / 无可开关）。"""
        if sp.enabled_probe:
            fn = getattr(self, sp.enabled_probe, None)
            if callable(fn):
                try:
                    return bool(fn())
                except Exception:  # noqa: BLE001
                    return None
            return None
        if sp.cfg_attr:
            cfg = getattr(self, sp.cfg_attr, None)
            if isinstance(cfg, dict):
                default = sp.default_enabled if sp.default_enabled is not None else True
                return bool(cfg.get(sp.enabled_key, default))
        return None

    def feature_specs(self) -> List[Dict[str, Any]]:
        """全部功能页的运行时状态（前端/诊断共用）。"""
        out: List[Dict[str, Any]] = []
        for sp in FEATURES:
            out.append(
                {
                    "key": sp.key,
                    "name": sp.name,
                    "scope": sp.scope,
                    "api": sp.api,
                    "enabled": self._feature_enabled(sp),
                    "has_tick": bool(sp.tick),
                    "note": sp.note,
                }
            )
        return out

    def features_overview(self) -> Response:
        """`GET /features`：功能页登记表 + 开启状态（只读）。"""
        specs = self.feature_specs()
        return Response(
            success=True,
            data={
                "features": specs,
                "count": len(specs),
                "keys": self.feature_keys(),
            },
        )

    def _crossseed_feature_enabled(self) -> bool:
        """「跨站取种」是否在用（14.0.0）。

        两个来源（任一为真）：
          · **全局真任务**「跨站取种」（``__crossseed__``）在岗 —— 它是承接方，常驻；
          · 任一任务开了 ``crossseed_enabled`` 且在岗 —— 它们是发起方（刷流任务）。
        """
        try:
            cs = (self._task_configs or {}).get(CROSSSEED_TASK_ID)
            if cs is not None and task_is_participating(cs):
                return True
            for task in (self._task_configs or {}).values():
                if getattr(task, "crossseed_enabled", False) and task_is_participating(task):
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False
