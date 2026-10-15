#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4 回归测试：H&R 判定「拿不准一律保守」+ 完成度阈值走真值源 + 义务工时兜底单点化。

覆盖（对应 2026-10-15 审计结论与 P4 派工单）：
  A. **方向**：``_hr_obligation`` 抛异常时该 hash **不得被暂停**（旧实现 `except → _owed=False`
     → 反而暂停：暂停期间按墙钟计时的 H&R 不计做种时长 → 违约风险；且不产魔力），
     并且必须留下可观测痕迹（``pause_skipped_by_error`` + warning）。
  B. **不吞错**：``pause_torrents``/``resume_torrents`` 的错误进入返回值
     （旧实现 `n, _e = ...` 后 `_e` 直接被丢弃 → 暂停失败无声）。
  C. **兜底单点**：站点规则**缺失**（未知）与规则**明确为 0**必须得出不同结论，
     且未知一律走同一个保守默认（``features/hrbills.py::HR_NEED_HOURS_DEFAULT``），
     不再出现「crossseed 回 0.0 / hr 回 24.0」的分叉。
  D. **阈值真值源**：完成度阈值必须经 ``common.hr_incomplete`` + ``hr_complete_ratio_of``
     （站点覆盖 > 全局默认）判定，源码里两处硬编码 `0.999` 不得复活。

用法：``python3 tools/test_p4_hr_conservative.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_p4_conservative"


# ----------------------------------------------------------------- 桩加载器
def _stub_pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


class _Stub(types.ModuleType):
    """万能桩模块：任何属性/调用都是另一个 _Stub。"""

    def __init__(self, name: str = "_stub"):
        super().__init__(name)

    def __getattr__(self, name):
        return _Stub(name)

    def __call__(self, *a, **k):
        return _Stub("_call")


def _stub_sibling(modname: str) -> _Stub:
    m = _Stub(PKG + "." + modname)
    sys.modules[PKG + "." + modname] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------- 1. stub app.*
for n, attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": _Stub("EventType")}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": _Stub("eventmanager"), "Event": type("Event", (), {})}),
    ("app.sdk.logging", {"logger": types.SimpleNamespace(**{k: (lambda *a, **kw: None) for k in
        ("info", "warning", "error", "debug", "exception")})}),
    ("app.scheduler", {"Scheduler": type("Scheduler", (), {})}),
    ("app.api", {}),
    ("app.api.endpoints", {}),
    ("app.api.endpoints.plugin", {"register_plugin_api": lambda *a, **k: None}),
    ("app.db", {}),
    ("app.db.oper", {}),
    ("app.db.oper.site", {"SiteOper": type("SiteOper", (), {})}),
    ("app.sdk.network", {"SitesHelper": type("SitesHelper", (), {})}),
    ("app.sdk.services", {"DownloaderHelper": type("DownloaderHelper", (), {})}),
    # 宿主（本机）没有装 apscheduler；容器内才有。离线测试自带桩，保证本机可跑。
    ("apscheduler", {}),
    ("apscheduler.triggers", {}),
    ("apscheduler.triggers.cron", {"CronTrigger": type("CronTrigger", (), {})}),
):
    m = sys.modules.get(n)
    if m is None:
        m = types.ModuleType(n)
        sys.modules[n] = m
    for k, v in attrs.items():
        setattr(m, k, v)

# 2. 包骨架 + 兄弟模块桩（core.py 的 import 面很大）
_stub_pkg(PKG, ROOT)
_stub_pkg(PKG + ".features", ROOT / "features")
_stub_pkg(PKG + ".sites", ROOT / "sites")
for _modname in ("bonus", "fetcher", "recommend", "models", "fingerprint",
                 "persistence", "downloader_ops", "live_stats", "dtier",
                 "tags", "formulas", "hubs", "fallback", "collect", "cloud_archive",
                 "kvstore", "signin", "sitestore"):
    _stub_sibling(_modname)

# 3. common.py 先加载（它是所有 features 的依赖），随后 core.py（用上面的桩）
_common = _load(PKG + ".common", "common.py")
_core = _load(PKG + ".features.core", "features/core.py")

# 4. 再加载真实业务模块（覆盖第 2 步的桩，供 hr/hrbills 解析真实依赖）
_tags = _load(PKG + ".tags", "tags.py")
_fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
_persistence = _load(PKG + ".persistence", "persistence.py")
_downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
# ★ 注意：根目录下另有一个 crossseed.py（站点规则侧），功能集在 features/crossseed.py。
_crossseed = _load(PKG + ".features.crossseed", "features/crossseed.py")
_hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")
_hr = _load(PKG + ".features.hr", "features/hr.py")

HR_NEED_HOURS_DEFAULT = _hrbills.HR_NEED_HOURS_DEFAULT
HR_COMPLETE_RATIO_DEFAULT = _common.HR_COMPLETE_RATIO_DEFAULT

# core.py 在 import 时就把 `..downloader_ops` 的桩对象绑成了模块全局（那时真模块还没加载），
# 这里用真值覆盖回来，避免 `state in QB_PAUSED_STATES` 命中万能桩。
_core.QB_PAUSED_STATES = getattr(
    _downloader_ops, "QB_PAUSED_STATES",
    ("pauseddl", "pausedup", "paused", "stoppeddl", "stoppedup"),
)

FAILS: list = []


def _ok(cond: bool, msg: str) -> None:
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        FAILS.append(msg)


class _Dl:
    """假下载器：记录被暂停/恢复的 hash，可注入错误。"""

    is_available = True

    def __init__(self):
        self.paused: list = []
        self.resumed: list = []
        self.err = None

    def pause_torrents(self, hashes):
        self.paused.extend(list(hashes))
        return len(list(hashes)), self.err

    def resume_torrents(self, hashes):
        self.resumed.extend(list(hashes))
        return len(list(hashes)), self.err


class _Store:
    def get_manual_paused(self, task_id):
        return set()


class _Task:
    def __init__(self):
        self.id = "t1"
        self.name = "测试任务"
        self.downloader = "qbittorrent"
        self.site_name = "school.test"
        self.site_domain = "school.test"


class Harness(_hr.HrMixin, _hrbills.HrBillsMixin, _crossseed.CrossSeedMixin, _core.CoreMixin):
    """只实现「数据接口」的最小插件；判定逻辑全部走真实实现。"""

    def __init__(self):
        self._dir = Path(tempfile.mkdtemp(prefix="mf_p4_"))
        self.site_rules: dict = {}
        self.managed: list = []
        self.dl = _Dl()
        self._store = _Store()
        self.obligations: dict = {}
        self.raise_for: set = set()

    # --- 数据接口（桩） ---
    def get_data_path(self):
        return self._dir

    def _site_rules(self):
        return dict(self.site_rules)

    def _site_domain_by_name(self, name):
        return str(name or "")

    def _hr_complete_ratio(self, dom=""):
        # 真实现（hrbills.py:396）读设置；这里只桩化「设置来源」，判定链走真值函数
        rec = self.site_rules.get(str(dom or "").strip().lower()) or {}
        try:
            return float(rec.get("complete_ratio") or HR_COMPLETE_RATIO_DEFAULT)
        except (TypeError, ValueError):
            return HR_COMPLETE_RATIO_DEFAULT

    def _hr_margin_hours(self):
        return 0.0

    # --- core.py `_apply_run_mode` 需要 ---
    def _get_downloader(self, name="qbittorrent"):
        return self.dl

    def _task_managed_torrents(self, task, **kw):
        return list(self.managed)

    def _run_check(self, task_id):
        return None

    def _hr_obligation(self, site, torrent, **kw):
        h = str(getattr(torrent, "hash", "") or "").lower()
        if h in self.raise_for:
            raise RuntimeError(f"账单读取失败（模拟）:{h}")
        return self.obligations.get(h, (False, 0.0, 0.0, "未分类"))


def _torrent(hash_string, progress, state="uploading"):
    return types.SimpleNamespace(hash=str(hash_string).lower(), progress=progress,
                                 tags=[], state=state, title=hash_string)


def main() -> int:
    p = Harness()
    print(f"（HR_NEED_HOURS_DEFAULT={HR_NEED_HOURS_DEFAULT}, "
          f"HR_COMPLETE_RATIO_DEFAULT={HR_COMPLETE_RATIO_DEFAULT}）")

    # ================= A. 方向：判不出来 → 不暂停 + 留痕 =================
    print("\n[A] 判定异常时不得暂停（方向必须保守）")
    p.managed = [_torrent("boom", 0.5), _torrent("fine", 0.5)]
    p.raise_for = {"boom"}
    p.obligations = {"fine": (False, 0.0, 0.0, "不欠")}   # fine 确实不欠 → 应暂停
    p.dl = _Dl()
    out = p._apply_run_mode(_Task(), "seeding")
    _ok("boom" not in p.dl.paused, "判定抛异常的种**没有被暂停**（旧实现会暂停它）")
    _ok("fine" in p.dl.paused, "判定成功且不欠的种仍然被暂停（暂停通路没被改坏）")
    _ok(out.get("paused") == 1, f"paused 计数只算真暂停的（实得 {out.get('paused')}）")
    _ok(out.get("pause_skipped_by_error") == ["boom"],
        "跳过的 hash 进入返回值（可观测，不再是无声行为）")

    # ================= B. 不吞错：下载器错误进返回值 =================
    print("\n[B] 暂停/恢复失败不再无声")
    p.managed = [_torrent("fine", 0.5)]
    p.raise_for = set()
    p.dl = _Dl()
    p.dl.err = "下载器 500"
    out = p._apply_run_mode(_Task(), "seeding")
    _ok(out.get("pause_error") == "下载器 500", "pause_torrents 的错误进入 out['pause_error']")
    p.managed = [_torrent("pausedone", 1.0, state="pausedUP")]
    p.dl = _Dl()
    p.dl.err = "下载器 502"
    out = p._apply_run_mode(_Task(), "seeding")
    _ok(out.get("resume_error") == "下载器 502", "resume_torrents 的错误进入 out['resume_error']")

    # ================= C. 兜底单点：未知 vs 真实 0 =================
    print("\n[C] 义务工时兜底：未知一律保守，真实 0 不臆造")
    p.site_rules = {}
    _ok(p._hr_need_hours_known("norule.test") is None,
        "无站点规则 → `_hr_need_hours_known` 返回 None（未知，而非 0）")
    _ok(p._hr_need_hours_or_default("norule.test") == float(HR_NEED_HOURS_DEFAULT),
        f"无站点规则 → 保守默认 {HR_NEED_HOURS_DEFAULT}h（旧 crossseed 路径给 0.0 ⇒ 已收敛）")
    _ex_val, _ex_known = p._crossseed_seed_need_hours_ex("norule.test")
    _ok((_ex_val, _ex_known) == (0.0, False),
        "`_ex` 对未知回 (0.0, known=False)，由调用方走上面的保守默认（语义可分辨）")

    p.site_rules = {"zero.test": {"seed_need_hours": 0}}
    _ok(p._hr_need_hours_known("zero.test") == 0.0,
        "规则明确写 0 → known 且值 0.0（站点已定论「不要求做种时长」）")
    _ok(p._hr_need_hours_or_default("zero.test") == 0.0,
        "真实 0 **不**被当成未知 → 仍回 0.0（不凭空多挂 24h）")
    _ok(p._crossseed_seed_need_hours_ex("zero.test") == (0.0, True),
        "`_ex` 对真实 0 回 (0.0, known=True)（与「缺失」可区分）")
    _ok(p._hr_need_hours_known("norule.test") is None
        and p._hr_need_hours_or_default("norule.test") != p._hr_need_hours_or_default("zero.test"),
        "两种情形结论不同（缺失→24h 保守；明确 0→0h）")

    p.site_rules = {"twenty.test": {"seed_need_hours": 20}}
    _ok(p._hr_need_hours_or_default("twenty.test") == 20.0, "规则 20 → 20.0（照抄站点真值）")
    _ok(HR_NEED_HOURS_DEFAULT == p._hr_need_hours_or_default("norule.test"),
        "唯一保守默认 = hrbills.HR_NEED_HOURS_DEFAULT（单点，无第二处硬编码 24.0 兜底）")

    # ================= D. 阈值走真值源 =================
    print("\n[D] 完成度阈值走 common.hr_incomplete + hr_complete_ratio_of")
    p.site_rules = {"permissive.test": {"complete_ratio": 0.95}}
    p.obligations = {}
    _ok(p._hr_incomplete_of("permissive.test", _torrent("a", 0.97)) is False,
        "站点阈值 0.95 + progress 0.97 → 视为已完成（旧硬编码 0.999 会判未完成）")
    p.site_rules = {"strict.test": {}}
    _ok(p._hr_incomplete_of("strict.test", _torrent("b", 0.97)) is True,
        "无站点覆盖 → 用全局默认 0.999 判未完成")
    _ok(_common.hr_incomplete(_torrent("c", None), 0.5) is False,
        "progress 读不到 → fail-safe 当作已完成（不豁免），语义未变")

    print("\n[E] 源码级护栏：硬编码 0.999 不得复活")
    for rel in ("features/hr.py", "features/core.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        hits = [m.start() for m in re.finditer(r"0\.999", src)]
        # 允许出现在注释里，不允许出现在代码里（`# ` 开头行）
        code_hits = []
        for pos in hits:
            line_start = src.rfind("\n", 0, pos) + 1
            line = src[line_start:src.find("\n", pos)]
            if not line.strip().startswith("#"):
                code_hits.append(line.strip())
        _ok(not code_hits, f"{rel} 代码里无硬编码 0.999（发现 {code_hits}）")

    print("\n" + "=" * 60)
    if FAILS:
        print(f"❌ P4 回归测试失败 {len(FAILS)} 项：")
        for f in FAILS:
            print("   - " + f)
        return 1
    print("✅ P4 回归测试全通过（方向保守 / 不吞错 / 兜底单点 / 阈值真值源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
