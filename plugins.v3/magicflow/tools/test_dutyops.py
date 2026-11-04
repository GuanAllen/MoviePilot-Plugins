#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 岗位操作（dutyops）离线回归 —— 用桩对象跑「占岗 / 退岗 / 让位」，不需 qB。

背景（2026-10-28）：同一段「纳管」流程原来在四处各写一遍 ——
``tags.duty_assign``（音乐/点播）、``hr._hr_host_assign``（欠债保种）、
``tags._manual_hold``（人工点名）、``claim._claim_host_status``（认领名单）。
差异只有职务名 / 租约 / 要不要记 prev_state / 退出回落到哪 / 谁拉起，
其余逐字相同。收进 ``dutyops.py`` 后，本文件钉住这套动作的**契约**：

  [1] 占位判据只由注册表决定（默认只招「没岗位」的种；特殊岗位才能跨岗挑人）；
  [2] 贴标签成功才写账本；职务轴替换、身份轴保留；
  [3] 幂等：账本+标签都在位 → holding，不重写；
  [4] 干跑零写入（``apply=False`` 只出 ``would``）；
  [5] 退岗：``prev_state`` 在 ``restore_prev`` 里才还原，否则回静默；
  [6] 只放自己占的种（别人的种一律跳过）。

用法：``python3 tools/test_dutyops.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_dutyops_test"

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
tags = _load(PKG + ".tags", "tags.py")
dutyreg = _load(PKG + ".dutyreg", "dutyreg.py")
dutyops = _load(PKG + ".dutyops", "dutyops.py")

STATE_SILENT = tags.STATE_SILENT
STATE_HR = tags.STATE_HR
STATE_CLAIM = tags.STATE_CLAIM
STATE_MUSIC = tags.STATE_MUSIC
STATE_BRUSH = tags.STATE_BRUSH
STATE_BONUS = tags.STATE_BONUS


# ---------------------------------------------------------------- 桩

class _T:
    """qB 种子快照项。"""

    def __init__(self, h: str, tags_: list, title: str = "种子"):
        self.hash = h
        self.tags = list(tags_)
        self.title = title
        self.state = "stalledUP"
        self.size_gb = 1.0


class _DL:
    def __init__(self, snap: dict):
        self.is_available = True
        self.snap = snap
        self.calls: list = []

    def replace_torrent_tags(self, h: str, new_tags: list) -> bool:
        self.calls.append((h, list(new_tags)))
        if h in self.snap:
            self.snap[h].tags = list(new_tags)   # 模拟 qB 真的改标签
        return True


class _Store:
    def __init__(self, data: dict):
        self.data = data

    def get(self, h: str) -> dict:
        return self.data.get(h) or {}

    def items(self) -> dict:
        return self.data

    def put(self, h: str, patch: dict) -> dict:
        self.data.setdefault(h, {}).update(patch)
        return self.data[h]

    def release(self, h: str, task_id: str = "") -> str | None:
        rec = self.data.get(h) or {}
        if task_id and rec.get("taken_by") and rec["taken_by"] != task_id:
            return None
        rec.update({"state": STATE_SILENT})
        rec.pop("taken_by", None)
        self.data[h] = rec
        return "魔流-馒头-静默"


class _Host:
    def __init__(self, snap: dict, store: _Store):
        self._snap = snap
        self._store = store
        self._dl = _DL(snap)
        self.logs: list = []
        self.claims = {"claimed" + "x" * 33}

    # dutyops 只认这几个协作方法
    def _get_downloader(self, name=None):
        return self._dl

    def _tag_state(self):
        return self._store

    def _tag_all_torrents(self):
        return self._snap

    def _torrent_site_name(self, tags_, default=""):
        return "馒头"

    def _claim_protected_hashes(self, site_id=None):
        return set(self.claims)

    def _log(self, msg, level=""):
        self.logs.append((level, msg))


def _host():
    snap = {
        "a": _T("a", ["魔流-馒头-静默-资源"]),      # 没岗位
        "b": _T("b", ["魔流-馒头-认领"]),            # 认领在岗(90)
        "c": _T("c", ["魔流-馒头-保种"]),            # 手动保种在岗(95)
        "d": _T("d", ["魔流-馒头-魔力"]),            # 真任务占位(动态 id)
    }
    store = _Store({
        "b": {"taken_by": dutyreg.ID_CLAIM, "state": STATE_CLAIM, "lease_until": 9e12},
        "c": {"taken_by": dutyreg.ID_KEEP, "state": STATE_HR},
        "d": {"taken_by": "__brush_task_x", "state": STATE_BRUSH, "lease_until": 9e12},
    })
    return _Host(snap, store)


print("[1] 占位判据：绩效岗只能招「没岗位」的")
h = _host()
r = dutyops.assign(h, ["a", "b", "c", "d"], taker=dutyreg.ID_MUSIC, state=STATE_MUSIC)
ok((r["adopted"], r["blocked"]) == (1, 3), "音乐只纳管了空缺的 a，其余 3 个让位")
ok(h._store.get("a").get("taken_by") == dutyreg.ID_MUSIC, "账本记为音乐占位")
ok("魔流-馒头-音乐" in h._snap["a"].tags, "职务轴已贴上")
ok("魔流-馒头-静默-资源" in h._snap["a"].tags, "身份轴原样保留")
ok(h._snap["c"].tags == ["魔流-馒头-保种"], "手动保种的标签没被动过")

print("[2] 特殊岗位：认领可从刷流/魔力挑人，但不抢手动保种")
r = dutyops.assign(h, ["d"], taker=dutyreg.ID_CLAIM, state=STATE_CLAIM,
                   lease_until=1e13, prev_from=(STATE_BRUSH, STATE_BONUS),
                   resume_when="new")
ok(r["adopted"] == 1, "认领(90) 从刷流(60) 收人成功")
ok(h._store.get("d").get("prev_state") == STATE_BRUSH, "记下 prev_state=刷流（退出时还原）")
ok("魔流-馒头-认领" in h._snap["d"].tags and "魔流-馒头-魔力" not in h._snap["d"].tags,
   "职务轴被替换，不是叠加")
ok(r["resume"] == ["d"], "resume_when=new → 新纳管的进拉起名单")

r = dutyops.assign(h, ["c"], taker=dutyreg.ID_CLAIM, state=STATE_CLAIM)
ok((r["adopted"], r["blocked"]) == (0, 1), "认领(90) 不抢手动保种(95)")

print("[3] 幂等：账本 + 标签都在位 → holding")
r = dutyops.assign(h, ["d"], taker=dutyreg.ID_CLAIM, state=STATE_CLAIM)
ok((r["holding"], r["adopted"]) == (1, 0), "第二轮不再重写")
ok(len(h._dl.calls) == 2, "标签只写过两次（a、d），幂等轮没有多余写入")

# 账本职务漂移（标签对、state 错）→ 只补账本，不重贴标签
h._store.data["d"]["state"] = STATE_MUSIC
_before = len(h._dl.calls)
r = dutyops.assign(h, ["d"], taker=dutyreg.ID_CLAIM, state=STATE_CLAIM)
ok(h._store.get("d").get("state") == STATE_CLAIM, "账本职务被纠正回认领")
ok(len(h._dl.calls) == _before, "没有多余的贴标签动作")

print("[4] 干跑：零写入")
h._snap["e"] = _T("e", ["魔流-馒头-静默-资源"])
r = dutyops.assign(h, ["e"], taker=dutyreg.ID_CLAIM, state=STATE_CLAIM, apply=False)
ok(r["would"] == ["e"] and r["adopted"] == 0, "apply=False 只出 would")
ok("e" not in h._store.data and "魔流-馒头-认领" not in h._snap["e"].tags, "账本与标签都没动")

print("[5] 退岗：prev_state 在 restore_prev 里才还原")
r = dutyops.release(h, ["d"], taker=dutyreg.ID_CLAIM,
                    restore_prev=(STATE_BRUSH, STATE_BONUS), pause=True)
ok(r["released"] == 1, "d 已退出")
ok(h._store.get("d").get("state") == STATE_BRUSH, "prev_state=刷流 → 还原成刷流")
ok(h._store.get("d").get("taken_by") == "", "占位已清空")
ok("魔流-馒头-刷流" in h._snap["d"].tags, "标签也回到刷流")

r = dutyops.release(h, ["a"], taker=dutyreg.ID_MUSIC, pause=True)
ok(r["released"] == 1 and h._store.get("a").get("state") == STATE_SILENT, "无 prev_state → 回静默")
ok("魔流-馒头-静默-资源" in h._snap["a"].tags, "回静默保住了身份轴")

print("[6] 只放自己占的种")
r = dutyops.release(h, ["b"], taker=dutyreg.ID_MUSIC)
ok((r["released"], r["skipped"]) == (0, 1), "音乐的退出不会动认领的种")
ok(h._store.get("b").get("taken_by") == dutyreg.ID_CLAIM, "认领占位仍在")

print("[7] 小工具")
ok(dutyops.normalize_hashes(["A", " a ", "", None]) == ["a"], "hash 归一：小写 + 去重 + 去空")
ok(dutyops.holder({"taken_by": dutyreg.ID_CLAIM}) == dutyreg.ID_CLAIM, "holder 取现任")
ok(dutyops.lease_of({"lease_until": "x"}) == 0.0, "坏租约按 0（不留异常）")
ok(dutyops.free_for({"taken_by": dutyreg.ID_CLAIM}, dutyreg.ID_MUSIC)[0] is False,
   "free_for：认领在岗 → 音乐不能接")
ok(dutyops.has_duty_tag(["魔流-馒头-魔力", "魔流-馒头-认领"], STATE_CLAIM),
   "has_duty_tag 不看标签顺序（残留职务标签是常态）")
ok(dutyops.claim_hashes(h) == {"claimed" + "x" * 33}, "claim_hashes 归一化（小写）")

print()
print("=" * 60)
if _fails:
    print(f"❌ 失败 {len(_fails)} 项 / 共 {_n} 项：")
    for f in _fails:
        print("   -", f)
    raise SystemExit(1)
print(f"✅ 全部通过：{_n} 项断言")
