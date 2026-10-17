#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 凭据脱敏离线回归（★ 19.2.4，真跑 common.redact_secrets / mask_*）

背景（Master 2026-10-17 指令「不管理、不自存、不回显站点 cookie/API 凭据」）
--------------------------------------------------------------------------
站点 cookie/apikey 侧本来就合规（现取 MoviePilot 的 Site 对象，插件不落盘）；
真正的外泄面是**出口回显**：`/status`、`/settings`、`get_iyuu_sites`、插件原生
设置表单 `get_form` 会把已存的第三方密钥（IYUU token / OpenList token / 站点
密钥表 passkey）明文送回浏览器，前端 `useTasks` / `SettingsDialog` 再原样存回 ——
只脱敏出口而不改保存路径，就会把真密钥写成 `***`（真丢数据）。

本测试覆盖「脱敏纯函数」+「保存路径不写坏真值」+「前端不再预填明文」三组不变量。

用法：``python3 tools/test_redact_secrets.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_redact_test"

CHECKS = 0
FAILS: list[str] = []


def _ensure_app() -> None:
    """容器里有真 ``app``；本机（无 MoviePilot）时给最小桩，让 common.py 能加载。"""
    try:
        import app.schemas.types  # noqa: F401
        import app.sdk.events  # noqa: F401
        return
    except Exception:
        pass
    for name in ("app", "app.schemas", "app.sdk"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    t = types.ModuleType("app.schemas.types")
    t.EventType = type("EventType", (), {})
    sys.modules["app.schemas.types"] = t
    e = types.ModuleType("app.sdk.events")
    e.eventmanager = types.SimpleNamespace()
    sys.modules["app.sdk.events"] = e


def _pkg(name: str, path: Path) -> None:
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def ok(cond: bool, msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        FAILS.append(msg)


def log(title: str) -> None:
    print(f"\n── {title} ──")


_pkg(PKG, ROOT)
_ensure_app()
common = _load(PKG + ".common", "common.py")

SECRET_MASK = common.SECRET_MASK
redact_secrets = common.redact_secrets
mask_secret_fields = common.mask_secret_fields
mask_url_secrets = common.mask_url_secrets
mask_long_tokens = common.mask_long_tokens
is_secret_key = common.is_secret_key
is_secret_blank = common.is_secret_blank


# ---------------------------------------------------------------------------
log("① redact_secrets：凭据键遮蔽 + 保留「是否已配置」")
# ---------------------------------------------------------------------------
got = redact_secrets({
    "iyuu_token": "abc123", "cloud_openlist_token": "xyz", "cookie": "c=1",
    "apikey": "k", "passkey": "p", "note": "正常字段", "count": 3,
    "enabled": True, "empty_token": "", "no_token": None, "cloud": {"token": "deep"},
})
ok(got["iyuu_token"] == SECRET_MASK and got["iyuu_token_set"] is True, "iyuu_token → `***` 且 iyuu_token_set=True")
ok(got["cloud_openlist_token"] == SECRET_MASK, "cloud_openlist_token → `***`")
ok(got["cookie"] == SECRET_MASK and got["apikey"] == SECRET_MASK and got["passkey"] == SECRET_MASK,
   "cookie / apikey / passkey 均已遮")
ok(got["note"] == "正常字段" and got["count"] == 3 and got["enabled"] is True, "非凭据键原样保留")
ok(got["empty_token"] == "" and "empty_token_set" not in got, "空值不遮、不补 _set")
ok(got["no_token"] is None and "no_token_set" not in got, "None 值不遮、不补 _set")
ok(isinstance(got["cloud"], dict) and got["cloud"]["token"] == SECRET_MASK, "嵌套 dict 递归遮蔽")

# 大小写不敏感 + 保留原键名
got2 = redact_secrets({"Token": "t", "API_KEY": "k"})
ok(got2["Token"] == SECRET_MASK and got2["API_KEY"] == SECRET_MASK, "键名大小写不敏感（Token / API_KEY）")
ok(got2["token_set"] is True and got2["api_key_set"] is True, "补的 _set 用小写键名")
# 幂等
ok(redact_secrets({"token": SECRET_MASK})["token"] == SECRET_MASK, "掩码再次脱敏仍为 `***`（幂等）")
# list 递归
got3 = redact_secrets([{"token": "a"}, {"plain": "b"}])
ok(got3[0]["token"] == SECRET_MASK and got3[1]["plain"] == "b", "list 内 dict 同样遮蔽")


# ---------------------------------------------------------------------------
log("② is_secret_key / is_secret_blank：保存路径的「不修改」判据")
# ---------------------------------------------------------------------------
ok(is_secret_key("Token") and is_secret_key(" API_KEY ") and is_secret_key("passkey"), "凭据键名识别（大小写/空白容错）")
ok(not is_secret_key("uid") and not is_secret_key("sites"), "`uid`/普通键**不**进全局凭据表（避免误伤同名显示字段）")
ok(not is_secret_key(None), "非字符串 → False（不抛异常）")
for v in ("", None, "   ", SECRET_MASK):
    ok(is_secret_blank(v), f"「空/掩码」判为不修改：{v!r}")
ok(not is_secret_blank("realvalue"), "真值不算「不修改」")


# ---------------------------------------------------------------------------
log("③ mask_secret_fields：IYUU 站点密钥表（含 uid，仅此一处）")
# ---------------------------------------------------------------------------
row = mask_secret_fields({"passkey": "pk-value", "uid": "12345", "downhash": "", "junk": "j", "token": "t"})
ok(row["passkey"] == SECRET_MASK and row["passkey_set"] is True, "passkey → `***` + passkey_set")
ok(row["uid"] == SECRET_MASK and row["uid_set"] is True, "uid → `***` + uid_set（只在密钥表这一处遮）")
ok(row["downhash"] == "" and "downhash_set" not in row, "空字段保持空、不补 _set")
ok(row["junk"] == "j", "非密钥字段原样保留")
ok(row["token"] == SECRET_MASK, "密钥表里嵌的 token 走 redact_secrets 一并遮")


# ---------------------------------------------------------------------------
log("④ mask_url_secrets：诊断回显里的下载链口令")
# ---------------------------------------------------------------------------
u = mask_url_secrets("https://pt.example/download.php?id=1&passkey=deadbeefcafe&uid=42")
ok("passkey=***" in u and "deadbeefcafe" not in u, "query 里 passkey 值 → `***`")
ok("id=1" in u and "uid=***" in u, "非口令参数保留、uid 也遮")
ok(mask_url_secrets("https://pt.example/torrents.php") == "https://pt.example/torrents.php", "无 query 的 URL 原样返回")
u2 = mask_url_secrets("https://pt.example/dl.php?authkey=AAA#frag")
ok(u2.endswith("#frag") and "AAA" not in u2, "保留 fragment、遮 authkey")
ok(mask_url_secrets("") == "", "空值不抛异常")


# ---------------------------------------------------------------------------
log("⑤ mask_long_tokens：诊断片段里的长口令串")
# ---------------------------------------------------------------------------
frag = '密钥：<b>a1b2c3d4e5f60718293a4b5c6d7e8f90</b>（passkey）'
masked = mask_long_tokens(frag)
ok("a1b2c3d4e5f60718293a4b5c6d7e8f90" not in masked and SECRET_MASK in masked, "≥16 位长串 → `***`")
ok("密钥" in masked and "passkey" in masked, "短词/标签保留（诊断仍可读）")


# ---------------------------------------------------------------------------
log("⑥ 源码不变量：单一真值源 / 出口脱敏 / 持久化路径不被脱敏 / 前端不预填")
# ---------------------------------------------------------------------------
SRC = {n: (ROOT / n).read_text(encoding="utf-8") for n in (
    "features/agentapi.py", "features/settings.py", "features/status.py", "features/core.py",
    "src/views/magicflow/composables/useTasks.js",
    "src/views/magicflow/components/dialogs/SettingsDialog.vue",
)}
ok("def _agent_scrub" not in SRC["features/agentapi.py"], "agentapi 不再自带第二份脱敏实现")
ok("SECRET_KEYS as _AGENT_SECRET_KEYS" in SRC["features/agentapi.py"], "agentapi 复用 common.SECRET_KEYS")
ok("redact_secrets(data)" in SRC["features/status.py"], "get_status 出口过脱敏闸")
ok("redact_secrets(self._current_config())" in SRC["features/settings.py"]
   and "redact_secrets(self._current_config())" in SRC["features/core.py"],
   "settings 保存响应 / core.get_form 出口都过脱敏闸")
core = SRC["features/core.py"]
body = core.split("def _current_config(", 1)[1].split("\n    def ", 1)[0]
ok("redact_secrets" not in body, "`_current_config()` 本体**不**脱敏（它还被 update_config 用于落盘）")
ok("mask_secret_fields" in SRC["features/settings.py"], "站点密钥表出口用 mask_secret_fields")
ok("iyuu_token: ''" in SRC["src/views/magicflow/composables/useTasks.js"],
   "前端不再把 status.iyuu_token 预填进 draft")
ok("status.value.iyuu_token" not in SRC["src/views/magicflow/composables/useTasks.js"], "前端草稿不读明文 token")
ok(SRC["src/views/magicflow/components/dialogs/SettingsDialog.vue"].count("已保存（留空则不修改）") >= 4,
   "密钥输入框占位符 =「已保存（留空则不修改）」（token + passkey/uid/downhash）")


# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{CHECKS} 项未过")
    for f in FAILS:
        print(f"  · {f}")
    sys.exit(1)
print(f"✅ PASS：{CHECKS}/{CHECKS} 项全过")
sys.exit(0)
