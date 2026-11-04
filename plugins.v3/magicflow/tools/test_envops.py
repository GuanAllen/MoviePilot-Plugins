#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · envops（外部环境能力）离线回归 —— 钉住「日志 / 站点 / 下载器」的契约。

背景（2026-10-29）：``_log`` / ``_dbg`` / ``_get_site`` / ``_list_sites`` /
``_list_downloaders`` 五个方法原本长在 ``features/core.py``（生命周期 + 调度层），
却被全库 673 处跨文件 ``self._`` 调用 —— 基础设施寄居服务层。19.10.21 下沉到
``envops.py``，core 只留一行委托（调用点零改动，同 ``downloader_ops.acquire``）。

本文件钉住下沉过程中**最容易悄悄变掉**的五件事：

  [1] 离线可加载：本模块不得在顶层 import ``app.*``（否则十几套离线测试集体崩）；
  [2] 日志前缀「魔流:」与非法级别回落 info（历史上拼错等级会把主流程打断）；
  [3] ``_dbg`` 受 ``_debug_log`` 开关控制，且与 ``_log`` 只加一次前缀；
  [4] ``_get_site`` 取不到要记 error 并返回 None（不抛给调用方）；
  [5] ``_list_sites`` 认证失败回落站点登记表，且回落告警按状态变化去重（不刷日志）；
  [6] ``_list_downloaders`` 全空时给出两个常见项兜底（任务编辑器下拉不能是空的）。

用法：``python3 tools/test_envops.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_envops_test"

_fails: list[str] = []
_n = 0


def ok(cond, msg: str) -> None:
    global _n
    _n += 1
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        _fails.append(msg)


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

# ---------------------------------------------------------------- [1] 离线加载
# 安装任何 app.* 桩之前先加载：顶部若有 app 依赖，这一步就崩。
assert "app" not in sys.modules, "测试环境已污染：加载 envops 前不应存在 app 模块"
envops = _load(PKG + ".envops", "envops.py")
ok("app" not in sys.modules, "[1] envops 加载后仍未引入 app.*（app 一律函数内延迟导入）")


# ---------------------------------------------------------------- 桩
class _Rec:
    """代替 MP logger，把每条日志记成 (级别, 文本)。"""

    def __init__(self) -> None:
        self.lines: list = []

    def info(self, text: str) -> None:
        self.lines.append(("info", text))

    def warning(self, text: str) -> None:
        self.lines.append(("warning", text))

    def error(self, text: str) -> None:
        self.lines.append(("error", text))


class _Host:
    """最小插件实例桩：只带 envops 会读写的两个状态位。"""

    def __init__(self, debug: bool = False) -> None:
        self._debug_log = debug


def _install(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_app_sdk(helper_raise=False, helper_items=None,
                     oper_raise=False, oper_items=None, dl_raise=False, dl_names=None):
    """把 app.db.oper.site / app.sdk.network / app.sdk.services 换成可控桩。"""
    for parent in ("app", "app.db", "app.db.oper", "app.sdk"):
        if parent not in sys.modules:
            _install(parent)

    class _SiteOper:
        def __init__(self):
            if oper_raise:
                raise RuntimeError("登记表不可用")

        def get(self, site_id):
            return ("site", site_id)

        def list(self):
            return list(oper_items or [])

    class _SitesHelper:
        def __init__(self):
            if helper_raise:
                raise RuntimeError("认证失效")

        def get_indexers(self):
            return list(helper_items or [])

    class _DownloaderHelper:
        def __init__(self):
            if dl_raise:
                raise RuntimeError("下载器服务不可用")

        def get_configs(self):
            return {n: object() for n in (dl_names or [])}

    _install("app.db.oper.site", SiteOper=_SiteOper)
    _install("app.sdk.network", SitesHelper=_SitesHelper)
    _install("app.sdk.services", DownloaderHelper=_DownloaderHelper)


def _rec():
    r = _Rec()
    envops._MP_LOGGER = r
    return r


# ---------------------------------------------------------------- [2] 日志
print("\n[2] log：前缀 + 非法级别回落")
r = _rec()
envops.log("上线完成")
ok(r.lines == [("info", "魔流:上线完成")], f"[2] 默认 info 且带前缀 → {r.lines}")

r = _rec()
envops.log("删种失败", "error")
ok(r.lines == [("error", "魔流:删种失败")], f"[2] error 级别生效 → {r.lines}")

r = _rec()
envops.log("拼错等级", "err")
ok(r.lines and r.lines[0][0] == "info", f"[2] 非法级别回落 info（不抛异常）→ {r.lines}")

# ---------------------------------------------------------------- [3] _dbg
print("\n[3] debug：开关 + 只加一次前缀")
r = _rec()
envops.debug(_Host(debug=False), "不该出现")
ok(r.lines == [], f"[3] 关闭时不输出 → {r.lines}")

r = _rec()
envops.debug(_Host(debug=True), "抓到了")
ok(r.lines == [("info", "魔流:[调试] 抓到了")], f"[3] 打开时输出且只一次前缀 → {r.lines}")

# ---------------------------------------------------------------- [4] _get_site
print("\n[4] get_site：成功 / 异常")
_install_app_sdk(oper_raise=False)
r = _rec()
ok(envops.get_site(_Host(), 7) == ("site", 7), "[4] 成功路径返回站点对象")

_install_app_sdk(oper_raise=True)
r = _rec()
ok(envops.get_site(_Host(), 7) is None, "[4] 异常返回 None（不抛给调用方）")
ok(len(r.lines) == 1 and r.lines[0][0] == "error", f"[4] 异常记一条 error → {r.lines}")

# ---------------------------------------------------------------- [5] _list_sites
print("\n[5] list_sites：主路径 / 回落 / 告警去重")
_install_app_sdk(helper_items=[
    {"id": 3, "name": "馒头", "domain": "M-Team.cc"},
    "不是字典",
    {"id": None, "domain": ""},
])
r = _rec()
host = _Host()
out = envops.list_sites(host)
ok(len(out) == 1 and out[0]["domain"] == "m-team.cc", f"[5] 只收字典项且域名小写 → {out}")
ok(host._site_fallback_note is False, "[5] 主路径有数据 → 回落标记复位为 False")


class _MpSite:
    def __init__(self, sid, name, dom):
        self.id = sid
        self.name = name
        self.domain = dom


_install_app_sdk(helper_raise=True, oper_items=[_MpSite(9, "聆听", "Listen.Audio")])
r = _rec()
host = _Host()
out = envops.list_sites(host)
ok(len(out) == 1 and out[0]["id"] == 9, f"[5] 认证失效 → 回落站点登记表 → {out}")
ok(host._site_fallback_note is True, "[5] 回落后置标记 True（下次不再重复告警）")
warn = [x for x in r.lines if x[0] == "warning"]
ok(len(warn) == 1 and "10" not in warn[0][1], f"[5] 回落告警一条 → {warn}")

r = _rec()
envops.list_sites(host)
warn2 = [x for x in r.lines if x[0] == "warning"]
ok(warn2 == [], f"[5] 第二次回落不再告警（去重生效）→ {r.lines}")

# ---------------------------------------------------------------- [6] _list_downloaders
print("\n[6] list_downloaders：正常 / 兜底")
_install_app_sdk(dl_names=["qbittorrent", "transmission"])
r = _rec()
out = envops.list_downloaders(_Host())
ok(out == [{"title": "qbittorrent", "value": "qbittorrent"},
           {"title": "transmission", "value": "transmission"}], f"[6] 正常路径 → {out}")

_install_app_sdk(dl_raise=True)
r = _rec()
out = envops.list_downloaders(_Host())
ok(len(out) == 2 and out[0]["value"] == "qbittorrent", f"[6] 全空兜底两项 → {out}")
ok(any(x[0] == "error" for x in r.lines), f"[6] 失败记 error → {r.lines}")

# ---------------------------------------------------------------- 收尾
print()
if _fails:
    print(f"❌ FAIL {len(_fails)}/{_n}")
    for m in _fails:
        print(f"   - {m}")
    sys.exit(1)
print(f"✅ PASS {_n}/{_n}")
sys.exit(0)
