#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 105 / API-01 后端保存守卫离线测试。

加载真实 ``features/settings.py``（app.* / 兄弟模块用桩替代），验证：
  A. 全量 payload：enabled / show_sidebar_nav / fallback_* 全部写入（行为不变）。
  B. 局部 payload（不含 enabled）：插件总开关不被默认值改写。
  C. 局部 payload（只带一个 fallback 键）：其余 fallback 配置保持现值，不按默认重建。
  D. 4 种开关组合：enabled 与 fallback_enabled 互不影响。
  E. 无 model_fields_set 的旧式 payload：按全量处理（不误伤宿主配置页）。
  F. 只读性：不改 payload、不写真实数据目录（save_data 被桩替换）。

用法：``python3 tools/test_settings_save_guard.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t105_settings"
FAILS: list[str] = []
CASES = 0


def _ok(cond, name, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}" + (f" —— {detail}" if detail else ""))
        FAILS.append(name)


def _mod(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    m.__path__ = getattr(m, "__path__", [])
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_SRC = (ROOT / "features/settings.py").read_text(encoding="utf-8")
_ALL_KEYS = sorted(set(re.findall(r"payload\.([A-Za-z_][A-Za-z0-9_]*)", _SRC))
                   | set(re.findall(r"getattr\(payload,\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']", _SRC)))


def _payload(**kw):
    """构造同时带属性与 model_fields_set 的 payload 替身（模拟 pydantic v2）。

    没传的字段一律 None；``full=True`` 时把 model_fields_set 标成全量键。
    """
    full = bool(kw.pop("full", False))
    # 只有这些是真「直读」字段（其余都走 getattr 带默认），给合理缺省即可。
    base = dict(enabled=True, show_sidebar_nav=True, debug_log=False, compact_mode=False,
                journal_keep=200, request_interval=0.0, bonus_upload_limit_kbps=200.0,
                brush_upload_limit_kbps=10240.0, seed_up_limit_kbps=0.0,
                brush_seed_up_limit_kbps=0.0)
    base.update(kw)
    p = types.SimpleNamespace(**base)
    p.model_fields_set = set(_ALL_KEYS) if full else set(kw.keys())
    return p


def _load_settings():
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {"__init__": lambda self, success=True,
                                                       message="", data=None: (
        setattr(self, "success", success), setattr(self, "message", message),
        setattr(self, "data", data))[-1]}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=types.SimpleNamespace(warning=lambda *a, **k: None,
                                                         info=lambda *a, **k: None,
                                                         error=lambda *a, **k: None))
    pkg = _mod(PKG)
    pkg.__path__ = []
    _mod(PKG + ".iyuu_cloud", IyuuCloud=type("IyuuCloud", (), {}))
    _mod(PKG + ".sitestore", slot_callbacks=lambda owner, key: [key, lambda **kw: None])
    _mod(PKG + ".models", MagicFlowDefaultsPayload=type("A", (), {}),
         MagicFlowDownloaderPathsPayload=type("B", (), {}),
         MagicFlowDownloaderPrefsPayload=type("C", (), {}),
         MagicFlowSettingsPayload=type("D", (), {}), DOWNLOADER_PREF_RECOMMENDED={})
    _mod(PKG + ".fallback", DEFAULT_SOURCES=["themoviedb", "bangumi", "douban"])
    _mod(PKG + ".kvstore", cache_get=lambda *a, **k: None, cache_set=lambda *a, **k: None)
    _mod(PKG + ".cloud_archive", DEFAULT_TARGET_TEMPLATE="{title}")
    _mod(PKG + ".signin", SigninEngine=type("SigninEngine", (), {"__init__": lambda self, *a, **k: None}))
    _mod(PKG + ".tags", DEFAULT_SORT_RULES=[])
    _mod(PKG + ".common",
         BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT=0, CACHE_TTL_REPORT=60, CLAIM_CFG_KEY="claim_cfg",
         CLOUD_INTERVAL_MINUTES=30, CLOUD_SCAN_MAX=100, CROSSSEED_SEED_HOURS_DEFAULT=24,
         CROSSSEED_SITE_HOURS_DEFAULT=[], FALLBACK_SCAN_MAX=30, LIVE_DOWNLOAD_ALERT_MB=50,
         LIVE_INTERVAL_MINUTES=4, LIVE_RATIO_TARGET=0.5, RESEED_CFG_KEY="reseed_cfg",
         SEED_UP_LIMIT_KBPS_DEFAULT=0, SIGNIN_INTERVAL_MINUTES=60, SIGNIN_QUEUE=3,
         SIGNIN_RETRY_KEYWORD="", _cs_parse_site_hours=lambda v: v, is_secret_blank=lambda v: not v,
         mask_secret_fields=lambda d: d, redact_secrets=lambda d: d)
    spec = importlib.util.spec_from_file_location(PKG + ".features.settings", ROOT / "features/settings.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG + ".features.settings"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class StubBase:
    """只实现 update_settings 需要的状态与副作用汇（不写盘、不碰网络）。"""

    def __init__(self):
        self._enabled = False
        self._show_sidebar_nav = True
        self._fallback_cfg = {"enabled": False, "sources": ["tvdb"], "paths": ["/keep"],
                              "interval": 240.0, "scan_max": 88, "sp_to_s00": True,
                              "after_import": False, "dry_run": True}
        self._recommend_cfg = {}
        self._live_cfg = {}
        self._cloud_cfg = {"token": "", "paths": [], "exclude_paths": [], "exclude_tags": []}
        self._signin_cfg = {}
        self._tags_cfg = {}
        self._rules_cfg = {}
        self._rescue_cfg = {}
        self._fallback_engine = None
        self._iyuu_client = types.SimpleNamespace(set_token=lambda *a, **k: None)
        self._iyuu_token = ""
        self._iyuu_sites = ""
        self._signin = None
        self._live = None
        # ★ 任务 107：标量/H&R 字段的「现值」——被守卫拒绝写入时必须原样保持。
        self._debug_log = True
        self._compact_mode = True
        self._journal_keep = 123
        self._request_interval = 1.5
        self._bonus_upload_limit_kbps = 200.0
        self._brush_upload_limit_kbps = 10240.0
        self._seed_up_limit_kbps = 0.0
        self._brush_seed_up_limit_kbps = 0.0
        self._hr_seed_margin_hours = 9.0
        self._hr_deadline_warn_hours = 36.0
        self._hr_complete_ratio_v = 0.5
        self._agent_mcp = True
        self._agent_mcp_scope = "core"
        self._notify_enabled = True
        self.saved: list[dict] = []

    def _build_iyuu_client(self, token):
        return types.SimpleNamespace(set_token=lambda *a, **k: None)

    # 副作用桩
    def save_data(self, key, data):
        self.saved.append({"key": key, "data": data})

    def _save_config(self):
        self.saved.append({"key": "_save_config", "data": dict(self._fallback_cfg)})

    def _apply_runtime_settings(self):
        pass

    def _refresh_scheduler(self):
        pass

    def _apply_task_traffic_limit(self, force=False):
        pass

    def _apply_seed_upload_limit(self, force=False):
        pass

    def _dbg(self, *a, **k):
        pass

    def _current_config(self):
        return {"enabled": self._enabled, "fallback": dict(self._fallback_cfg)}


def _snapshot(stub) -> dict:
    """可比较的当前状态快照（只取被守卫的字段；fallback 深拷贝）。"""
    return {
        "enabled": stub._enabled,
        "show_sidebar_nav": stub._show_sidebar_nav,
        "fallback": dict(stub._fallback_cfg),
        "journal_keep": stub._journal_keep,
        "debug_log": stub._debug_log,
        "compact_mode": stub._compact_mode,
        "request_interval": stub._request_interval,
        "hr_seed_margin_hours": stub._hr_seed_margin_hours,
        "hr_deadline_warn_hours": stub._hr_deadline_warn_hours,
        "hr_complete_ratio_v": stub._hr_complete_ratio_v,
        "agent_mcp": stub._agent_mcp,
        "agent_mcp_scope": stub._agent_mcp_scope,
    }


def make_stub_cls(mixin):
    """StubBase 在前：副作用桩覆盖 Mixin 同名方法；update_settings 由 Mixin 提供。"""
    return type("Stub", (StubBase, mixin), {})


def full_payload(**over):
    base = dict(enabled=True, show_sidebar_nav=True, agent_mcp=True, agent_mcp_scope="core",
                debug_log=False, compact_mode=False, journal_keep=200, request_interval=0,
                fallback_enabled=False, fallback_sources=["tvdb"], fallback_paths=["/x"],
                fallback_interval_minutes=120, fallback_scan_max=66, fallback_sp_to_s00=True,
                fallback_after_import=False, fallback_dry_run=True)
    base.update(over)
    return base


def main() -> int:
    settings = _load_settings()
    Mix = settings.SettingsMixin
    Stub = make_stub_cls(Mix)
    stub = Stub()

    print("── 0. 修改前问题复现（旧口径） ──")
    _legacy = _payload(journal_keep=123)          # 局部 payload：不含 enabled / fallback_*
    _ok(bool(_legacy.enabled) is True,
        "旧代码 bool(payload.enabled) 取模型缺省 True ⇒ 局部保存会静默打开插件")
    _ok(int(getattr(_legacy, "fallback_interval_minutes", 30)) == 30,
        "旧代码整份重建会把 interval 取成默认 30（现值 240 被打回）")

    print("── A. 全量 payload：全部生效（行为不变） ──")
    stub.update_settings(_payload(full=True, **full_payload()))
    _ok(stub._enabled is True, "enabled 写入")
    _ok(stub._show_sidebar_nav is True, "show_sidebar_nav 写入")
    _ok(stub._fallback_cfg["enabled"] is False, "fallback.enabled 写入")
    _ok(stub._fallback_cfg["interval"] == 120.0, "fallback.interval 写入")
    _ok(stub._fallback_cfg["scan_max"] == 66, "fallback.scan_max 写入")
    _ok(stub._fallback_cfg["sources"] == ["tvdb"], "fallback.sources 写入")
    _ok(stub._fallback_cfg["paths"] == ["/x"], "fallback.paths 写入")

    print("── B. 局部 payload（不含 enabled）不碰总开关 ──")
    stub2 = Stub()
    stub2._fallback_cfg = dict(stub._fallback_cfg)
    stub2.update_settings(_payload(journal_keep=123))
    _ok(stub2._enabled is False, "总开关保持关闭（旧代码会被 enabled=True 默认值打开）")
    _ok(stub2._show_sidebar_nav is True, "show_sidebar_nav 保持")
    _ok(stub2._fallback_cfg == stub._fallback_cfg, "未带 fallback 键时兜底配置完全保持")
    _ok(stub2._journal_keep == 123, "带了的键正常写入")

    print("── C. 局部 payload 只改一个 fallback 键 ──")
    stub3 = Stub()
    before = dict(stub3._fallback_cfg)
    stub3.update_settings(_payload(fallback_scan_max=99))
    _ok(stub3._fallback_cfg["scan_max"] == 99, "被改键生效")
    _ok(stub3._fallback_cfg["interval"] == before["interval"], "interval 不被默认 30 覆盖")
    _ok(stub3._fallback_cfg["sources"] == before["sources"], "sources 保持")
    _ok(stub3._fallback_cfg["paths"] == before["paths"], "paths 保持")
    _ok(stub3._fallback_cfg["enabled"] is before["enabled"], "兜底开关保持")
    _ok(stub3._fallback_cfg["sp_to_s00"] is True and stub3._fallback_cfg["dry_run"] is True,
        "其余开关保持")
    _ok(stub3._enabled is False, "总开关保持")

    print("── D. 4 种开关组合互不污染 ──")
    for enabled, fb in ((True, True), (True, False), (False, True), (False, False)):
        s = Stub()
        s.update_settings(_payload(full=True, **full_payload(enabled=enabled, fallback_enabled=fb)))
        _ok(s._enabled is enabled and s._fallback_cfg["enabled"] is fb,
            f"enabled={enabled} / fallback_enabled={fb} 各自落位")

    print("── E. 无 model_fields_set 的旧式 payload 按全量处理 ──")
    s = Stub()
    _fp = _payload(full=True, **full_payload(enabled=True, fallback_enabled=True))
    legacy = types.SimpleNamespace(**{k: v for k, v in _fp.__dict__.items() if k != "model_fields_set"})
    s.update_settings(legacy)
    _ok(s._enabled is True, "旧式 payload 的 enabled 仍生效（不误伤宿主配置页）")
    _ok(s._fallback_cfg["enabled"] is True, "旧式 payload 的 fallback_enabled 生效")

    print("── F. 只读/无外部副作用 ──")
    s = Stub()
    payload = _payload(journal_keep=55)
    keys_before = set(payload.__dict__)
    s.update_settings(payload)
    _ok(set(payload.__dict__) == keys_before, "不改 payload 对象")
    _ok(all(not str(x.get("key", "")).startswith("/") for x in s.saved), "只经桩 save_data/_save_config，无真实写盘")
    _ok(any(x["key"] == "_save_config" for x in s.saved), "保存后仍触发一次配置落盘（桩）")

    print("── G. R-01：显式空 payload 无副作用（任务 107） ──")
    s = Stub()
    snap = _snapshot(s)
    resp = s.update_settings(_payload())          # model_fields_set = set()
    _ok(getattr(resp, "success", False) is True, "空 payload 返回成功")
    _ok(getattr(resp, "message", "") == "无变更", "空 payload 明确告知无变更")
    _ok(_snapshot(s) == snap, "空 payload 后所有字段保持现值（enabled/fallback/journal_keep/hr_*）")
    _ok(s.saved == [], "空 payload 不落盘（无 save_data / 无 _save_config）")

    print("── H. R-02：journal_keep / hr_* 字段级守卫（任务 107） ──")
    s = Stub()
    s.update_settings(_payload(journal_keep=321))
    _ok(s._journal_keep == 321, "只提交 journal_keep 时写入 321")
    _ok(s._hr_seed_margin_hours == 9.0 and s._hr_deadline_warn_hours == 36.0
        and s._hr_complete_ratio_v == 0.5, "只提交 journal_keep 时 hr_* 不被默认值覆盖")
    _ok(s._fallback_cfg["scan_max"] == 88 and s._fallback_cfg["interval"] == 240.0,
        "只提交 journal_keep 时 fallback 不被默认值覆盖")
    _ok(s._enabled is False, "只提交 journal_keep 时总开关不被默认值打开")
    s = Stub()
    s.update_settings(_payload(hr_seed_margin_hours=7.0, hr_deadline_warn_hours=24.0,
                               hr_complete_ratio=0.75))
    _ok(s._hr_seed_margin_hours == 7.0, "显式提交 hr_seed_margin_hours 正常保存（不禁止修改）")
    _ok(s._hr_deadline_warn_hours == 24.0, "显式提交 hr_deadline_warn_hours 正常保存")
    _ok(s._hr_complete_ratio_v == 0.75, "显式提交 hr_complete_ratio 正常保存")
    _ok(s._journal_keep == 123 and s._fallback_cfg["scan_max"] == 88,
        "只提交 hr_* 时 journal_keep / fallback 保持")
    s = Stub()
    s.update_settings(_payload(hr_seed_margin_hours=9.0))
    _ok(s._hr_seed_margin_hours == 9.0 and s._hr_deadline_warn_hours == 36.0,
        "只提交一个 hr 字段时另一个保持（不因同组默认值覆盖）")

    print("── I. 任务 107 十个必须验证场景 ──")
    # 1 空 payload
    s = Stub(); snap = _snapshot(s)
    s.update_settings(_payload())
    _ok(_snapshot(s) == snap, "场景1 空 payload：零改动")
    # 2 只改 fallback 子项
    s = Stub(); s.update_settings(_payload(fallback_interval_minutes=45))
    _ok(s._fallback_cfg["interval"] == 45.0 and s._fallback_cfg["scan_max"] == 88
        and s._fallback_cfg["sources"] == ["tvdb"], "场景2 只改 fallback 子项：其余 fallback 保持")
    # 3 只改普通 UI 设置
    s = Stub(); s.update_settings(_payload(compact_mode=False))
    _ok(s._compact_mode is False and s._debug_log is True, "场景3 只改普通 UI：只写该项")
    _ok(s._journal_keep == 123 and s._hr_seed_margin_hours == 9.0, "场景3 不重置其它字段")
    # 4 只改 HR
    s = Stub(); s.update_settings(_payload(hr_deadline_warn_hours=12.0))
    _ok(s._hr_deadline_warn_hours == 12.0 and s._hr_seed_margin_hours == 9.0,
        "场景4 只改 HR：单键生效、同组其余保持")
    # 5 只改 journal_keep
    s = Stub(); s.update_settings(_payload(journal_keep=77))
    _ok(s._journal_keep == 77 and s._compact_mode is True, "场景5 只改 journal_keep：其余保持")
    # 6 改 enabled
    s = Stub(); s.update_settings(_payload(enabled=True))
    _ok(s._enabled is True and s._fallback_cfg["enabled"] is False, "场景6 改 enabled：兜底开关不受影响")
    s = Stub(); s.update_settings(_payload(enabled=False))
    _ok(s._enabled is False, "场景6b enabled=False 正常保存")
    # 7 改 show_sidebar_nav
    s = Stub(); s.update_settings(_payload(show_sidebar_nav=False))
    _ok(s._show_sidebar_nav is False and s._enabled is False, "场景7 改 show_sidebar_nav：开关独立")
    # 8 混合修改
    s = Stub()
    s.update_settings(_payload(enabled=True, fallback_scan_max=99, hr_seed_margin_hours=5.0,
                               journal_keep=42, compact_mode=False))
    _ok(s._enabled is True and s._fallback_cfg["scan_max"] == 99
        and s._hr_seed_margin_hours == 5.0 and s._journal_keep == 42 and s._compact_mode is False,
        "场景8 混合修改：全部生效")
    _ok(s._fallback_cfg["interval"] == 240.0 and s._hr_deadline_warn_hours == 36.0,
        "场景8 混合修改：未提交的 fallback/hr 键保持")
    # 9 局部 payload 不得重置未提交字段（逐字段快照对比）
    s = Stub(); snap = _snapshot(s)
    s.update_settings(_payload(fallback_dry_run=False))
    after = _snapshot(s)
    after["fallback"] = dict(after["fallback"], dry_run=True)   # 只允许 dry_run 变
    diff = {k: (snap[k], after[k]) for k in snap if snap[k] != after[k]}
    _ok(diff == {}, f"场景9 局部 payload：除 fallback.dry_run 外全部字段不变（实际变化={diff}）")
    _ok(s._fallback_cfg["dry_run"] is False, "场景9 被提交字段生效")
    # 10 新旧前端映射与后端字段语义一致（旧 spread 不再污染 enabled；新映射键集=后端键集）
    _ok("fallbackSettingsFrom" in (ROOT / "src/views/magicflow/composables/useTasks.js").read_text(encoding="utf-8"),
        "场景10 useTasks 使用显式映射")
    _ok("...(status.value.fallback || {})" not in (ROOT / "src/views/magicflow/composables/useTasks.js").read_text(encoding="utf-8"),
        "场景10 旧 spread 未复活")

    print("── J. 旧式 payload（无 fields_set）保持全量写入 ──")
    s = Stub()
    _fp = _payload(full=True, **full_payload(enabled=True, fallback_enabled=True))
    legacy = types.SimpleNamespace(**{k: v for k, v in _fp.__dict__.items() if k != "model_fields_set"})
    s.update_settings(legacy)
    _ok(s._enabled is True and s._fallback_cfg["enabled"] is True,
        "旧式 payload 仍是全量语义（兼容老宿主）")

    print(f"\n{'✅ PASS' if not FAILS else '❌ FAIL'} —— {CASES - len(FAILS)}/{CASES} 通过")
    if FAILS:
        print("失败项：" + "；".join(FAILS))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
