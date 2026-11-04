#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播「整理入库」失败重试（★ 19.10.70）离线回归 —— 真跑 features/ondemand.py，不需 MoviePilot / qB。

背景（Master 2026-11-01 15:00）：
  点播下完 → ``_ondemand_settle`` 转「资源」后**顺手**调 ``_ondemand_import`` 入 MP 媒体库。
  这一步要联网识别（TMDB），而**入库是一次性动作**：那次失败（实测 = MP 无外网，
  TMDB ConnectTimeout）就再没人管 —— 种永远停在「已转资源·未入库」，不告警不重试。
  实锤：小猪佩奇 S01（52 集 / 5.38GB，hash 82ef219a）就这样漏在下载目录一整天。

  19.10.70 = 把「未入库」变成**可重试状态**，不新建累加器，真值源仍是
  ``ondemand_history`` 落盘记录（``stage=resource`` + ``in_library=False``），
  每轮 Check 按退避表补整理。

断言：
  [1] 退避表合法：单调不减、末项为稳态、总跨度覆盖断网（> 1 天）；
  [2] 未到 ``retry_at`` → 跳过，不碰 MP（不硬刷）；
  [3] 失败 → ``retry_n+1``、``retry_at`` 后移、``import_msg`` 记真原因（可排障）；
  [4] 成功 → ``in_library=True`` + ``imported_at``，清 ``retry_n/retry_at``、解除 ``retry_stop``；
  [5] 种已不在下载器 → 标 ``retry_stop`` 且**不消耗**重试次数（重试必然失败）；
  [6] 下载器整体不可用（快照空）→ 整轮跳过，**不消耗**次数（否则 qB 重启一次烧光上限）；
  [7] 次数用完 → 标 ``retry_stop`` 停止重试（防无限刷 MP）；
  [8] ``force=True`` → 忽略节流/退避/次数上限并清零计数（人工「全部重跑」入口）；
  [9] 10 分钟节流：连续两轮只跑一次；
  [10] 上线接线：brush.py Check 周期调 ``_ondemand_import_retry``；api.py 注册 ``/ondemand/repair``；
       ``_ondemand_settle`` 改用带 msg 的 ``_ondemand_import_ex`` 并落 ``retry_at``；
  [11] 清单可见：``_ondemand_hist_row`` 的 stage_text 区分「待补整理/待重试/已放弃」。

用法：``python3 tools/test_ondemand_import_retry.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_import_retry_test"

FAILS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")
_pkg(PKG + ".sites", ROOT / "sites")

# 桩：app.schemas.Response / app.sdk.logging
_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

# 桩：..tags（本用例不测标签，只要 import 期能解析名字）
_tags = types.ModuleType(PKG + ".tags")
for _n in ("MEDIA_CAND_TTL", "SUB_NEW", "SUB_RESOURCE", "STATE_ONDEMAND", "STATE_SILENT"):
    setattr(_tags, _n, _n)
for _n in ("duty_assign", "duty_of", "identity_of", "is_freeleech", "media_act",
           "media_cand_get", "media_cand_hydrate", "media_cand_put", "media_fetch_torrent",
           "media_grab", "media_row_from_ti", "media_totals", "retag",
           "strip_media_prefix", "tag_for"):
    setattr(_tags, _n, lambda *a, **k: None)
_tags.fmt_iso_ts = lambda ts: ("" if not float(ts or 0) else "T%s" % int(float(ts)))
# ★ 19.11.14：点播排序要用的计费口径（本用例不测成本，给了能跑就行）
_tags.promo_factor = lambda v=None, d=1.0: d
_tags.promo_label = lambda *a, **k: ""
sys.modules[PKG + ".tags"] = _tags

_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec

_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site

_fp = types.ModuleType(PKG + ".fingerprint")
_fp.info_hash = lambda *a, **k: ""
_fp.load_torrent_entries = lambda *a, **k: []
_fp.total_size = lambda *a, **k: 0
sys.modules[PKG + ".fingerprint"] = _fp

_ff = types.ModuleType(PKG + ".sites.formula_fetch")
_ff.fetch_torrent_promotion = lambda *a, **k: None
sys.modules[PKG + ".sites.formula_fetch"] = _ff

_persist = types.ModuleType(PKG + ".persistence")
_persist.OperationItem = type("OperationItem", (), {})
sys.modules[PKG + ".persistence"] = _persist

# 桩：``shared``（真实模块，只用 lock()；19.10.72 起历史表读改写要持锁）
_shared = _load(PKG + ".shared", "shared.py")
sys.modules[PKG + ".shared"] = _shared
setattr(sys.modules[PKG], "shared", _shared)

ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
OnDemandMixin = ondemand.OnDemandMixin

H1 = "a" * 40
H2 = "b" * 40
H3 = "c" * 40
H4 = "d" * 40


class Host(OnDemandMixin):
    """最小宿主：只提供 ``_ondemand_import_retry`` 依赖的五个入口（其余方法不触达）。"""

    def __init__(self, rows, snap=None, import_ok=False, msg="连接TMDB出错:无法连接TheMovieDb"):
        self.rows = [dict(r) for r in rows]
        self.snap = {h: object() for h in (snap if snap is not None else [r["hash"] for r in rows])}
        self.import_ok = import_ok
        self.msg = msg
        self.calls = []
        self.logs = []

    def _ondemand_history_read(self, limit=None):
        return [dict(r) for r in self.rows]

    def _ondemand_history_save(self, rows):
        self.rows = [dict(r) for r in rows]

    def _ondemand_snapshot(self):
        return dict(self.snap)

    def _ondemand_import_ex(self, h, gid="", title="", media_hint=None):
        # ★ 19.11.2 起真实签名多了 ``media_hint``（下载期身份贯穿）→ 桩要跟上，
        #   否则这条测试自己先 TypeError 挂掉，等于 19.11.2 之后一直是红的。
        self.calls.append((h, title))
        return self.import_ok, ("" if self.import_ok else self.msg)

    def _log(self, msg, level="info"):
        self.logs.append((level, msg))

    # 测试辅助
    def row(self, h):
        for r in self.rows:
            if str(r.get("hash")) == h:
                return r
        return {}

    def reset_round(self):
        self._od_import_round_ts = 0.0


def _pending(h, **kw):
    r = {"hash": h, "title": "某部片", "stage": "resource", "in_library": False,
         "added_at": time.time() - 3600, "retry_n": 0, "retry_at": 0}
    r.update(kw)
    return r


print("\n[1] 退避表")
B = ondemand._OD_IMPORT_BACKOFF
ok(all(B[i] <= B[i + 1] for i in range(len(B) - 1)), "退避间隔单调不减")
ok(sum(B) + (ondemand._OD_IMPORT_MAX_TRY - len(B)) * B[-1] > 86400, "总重试跨度 > 1 天（覆盖断网）")
ok(ondemand._OD_IMPORT_MAX_TRY > len(B), "重试上限 > 退避表长度（末项为稳态循环）")

print("\n[2] 未到 retry_at → 不碰 MP")
h = Host([_pending(H1, retry_at=time.time() + 3600)])
r = h._ondemand_import_retry(force=True)   # 先用 force 过掉节流门，再看退避门
h.reset_round()
h.calls.clear()
r = h._ondemand_import_retry()
ok(r["retried"] == 0 and not h.calls, "retry_at 未到 → 零调用（不硬刷 MP）")
ok(r["skipped"] == 1, "统计口径：记为 skipped")

print("\n[3] 失败 → 计数 + 退避 + 原因落盘")
h = Host([_pending(H1)])
r = h._ondemand_import_retry()
row = h.row(H1)
ok(r["retried"] == 1 and r["fail"] == 1, "真试过 → retried/fail 各 1")
ok(row.get("retry_n") == 1, "retry_n 递增")
ok(float(row.get("retry_at") or 0) > time.time() + 100, "retry_at 后移至未来")
ok("TMDB" in str(row.get("import_msg") or ""), "import_msg 记下真原因（TMDB）")
ok(row.get("in_library") is False, "失败不改 in_library")

print("\n[4] 成功 → 入库 + 清重试状态")
h = Host([_pending(H1, retry_n=3, retry_at=0, retry_stop=True)], import_ok=True)
r = h._ondemand_import_retry(force=True)
row = h.row(H1)
ok(r["ok"] == 1, "force 忽略 retry_stop 并成功")
ok(row.get("in_library") is True, "in_library=True")
ok(float(row.get("imported_at") or 0) > 0, "落 imported_at")
ok(int(row.get("retry_n") or 0) == 0 and float(row.get("retry_at") or 0) == 0, "清 retry_n/retry_at")
ok(row.get("retry_stop") is False, "解除 retry_stop")

print("\n[5] 种已不在下载器 → 标停 & 不计次数")
h = Host([_pending(H1)], snap=[])
h.snap = {}   # 快照为空 → 走 [6] 分支；这里要模拟「快照有别的种、缺这颗」
h.snap = {H2: object()}
r = h._ondemand_import_retry()
row = h.row(H1)
ok(r["retried"] == 0, "不尝试整理")
ok(row.get("retry_stop") is True and int(row.get("retry_n") or 0) == 0, "retry_stop=True 且不烧次数")
ok("不在下载器" in str(row.get("import_msg") or ""), "原因说明「种已不在下载器」")

print("\n[6] 下载器不可用 → 整轮跳过、不计次数")
h = Host([_pending(H1)], snap=[])
h.snap = {}
r = h._ondemand_import_retry()
row = h.row(H1)
ok(r["retried"] == 0 and r["skipped"] == 1, "整轮跳过")
ok(int(row.get("retry_n") or 0) == 0 and not row.get("retry_stop"), "不烧次数、不标停")
ok("下载器不可用" in str(r.get("note") or ""), "note 说明原因")

print("\n[7] 次数用完 → 停止重试")
h = Host([_pending(H1, retry_n=ondemand._OD_IMPORT_MAX_TRY, retry_at=0)])
r = h._ondemand_import_retry()
row = h.row(H1)
ok(r["retried"] == 0 and row.get("retry_stop") is True, "达上限 → retry_stop")

print("\n[8] force 清计数并重试")
h = Host([_pending(H1, retry_n=ondemand._OD_IMPORT_MAX_TRY, retry_at=time.time() + 99999)])
h._od_import_round_ts = time.time()
r = h._ondemand_import_retry(force=True)
ok(r["retried"] == 1 and len(h.calls) == 1, "force 穿透节流 + 退避 + 上限")
ok(int(h.row(H1).get("retry_n") or 0) == 1, "force 从 0 起算（不沿用旧计数）")

print("\n[9] 10 分钟节流")
h = Host([_pending(H1)])
h._ondemand_import_retry()
h.calls.clear()
r2 = h._ondemand_import_retry()
ok(r2["retried"] == 0 and not h.calls, "第二轮被节流，零调用")
ok(float(getattr(h, "_od_import_round_ts", 0)) > 0, "节流时间戳已记")

print("\n[10] 上线接线（源码锚点）")
_src_brush = (ROOT / "features" / "brush.py").read_text(encoding="utf-8")
_src_api = (ROOT / "features" / "api.py").read_text(encoding="utf-8")
_src_od = (ROOT / "features" / "ondemand.py").read_text(encoding="utf-8")
ok("self._ondemand_settle(task)" in _src_brush, "brush.py Check 周期调 _ondemand_settle（补整理挂在它里面）")
ok("self._ondemand_import_retry()" in _src_od, "settle 内调补整理（同文件自调用，不新增跨界边）")
ok("_retry: Dict[str, Any] = self._ondemand_import_retry()" in _src_od, "补整理结果并入 settle 返回")
ok("_retry = self._ondemand_import_retry()" not in _src_brush, "brush.py 无新增跨界调用（棘轮）")
ok('("/ondemand/repair"' in _src_api, "api.py 注册 /ondemand/repair")
ok("def ondemand_repair" in _src_od, "ondemand.py 有 ondemand_repair 入口")
ok("self._ondemand_import_ex(" in _src_od and "media_hint=" in _src_od,
   "_ondemand_settle 用带 msg 的版本（19.11.2 起还带 media_hint 身份）")
ok("retry_at=time.time() + _OD_IMPORT_BACKOFF[0]" in _src_od, "settle 首次失败即排重试")
ok("def _ondemand_import_retry" in _src_od, "补整理方法存在")

print("\n[10b] 无资源组时的收尾（★ 19.10.71：佩奇型死锁）")
ok('if gid:\n                    files.set_identity' in _src_od, "set_identity 改为有组才设身份")
ok('if _ident != SUB_RESOURCE:' in _src_od, "无组时按账本身份决定是否继续等")
ok("self._tag_state().get(h)" in _src_od, "无组分支读账本 sub 判身份")
ok("continue      # 有码、组还没成形 → 再等一轮" in _src_od and "无特征码也收尾" in _src_od,
   "19.11.4 口径：只有「有码没组」继续等，无码收尾不死等")

print("\n[11] 清单可见性")
row = ondemand.OnDemandMixin._ondemand_hist_row(h, {"hash": H1, "stage": "resource", "in_library": False})
ok("待补整理" in row["stage_text"], "未入库首轮文案「待补整理」")
row = ondemand.OnDemandMixin._ondemand_hist_row(
    h, {"hash": H1, "stage": "resource", "in_library": False, "retry_n": 2, "retry_at": time.time() + 60})
ok("待重试 2" in row["stage_text"], "有次数时显示「待重试 N」")
ok(row["retry_n"] == 2 and row["retry_at"], "行带 retry_n / retry_at")
row = ondemand.OnDemandMixin._ondemand_hist_row(
    h, {"hash": H1, "stage": "resource", "in_library": False, "retry_stop": True})
ok("已放弃" in row["stage_text"], "放弃后文案「已放弃」")
row = ondemand.OnDemandMixin._ondemand_hist_row(h, {"hash": H1, "stage": "resource", "in_library": True})
ok("已入库" in row["stage_text"], "入库后文案不变")

print("\n" + ("=" * 60))
if FAILS:
    print(f"FAIL：{len(FAILS)}/{N} 条不通过")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print(f"PASS：{N}/{N} 条断言全过")
