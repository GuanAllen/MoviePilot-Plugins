#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 回归测试：落盘「可见 + 原子 + 不清空 + 只补缺键」（离线，不需要 MoviePilot）

为什么单开一个（2026-10-15 的审计结论）：
  * `KvBridge.flush_if_dirty()` 原来**无条件** `self.dirty = False; return True`，
    而继承它的 6 个 Store 的 `_write_file` 全是 `except Exception: pass` —— 于是
    「磁盘满 / 权限错 / 序列化失败」时**丢了却报告已落盘**（`hot_stats()` 还报 dirty:false）。
  * `TaskStateStore._write_file` 是**全项目唯一直接覆盖原文件**的写（`open(..., "w")`），
    写一半被杀 → 半截 JSON → 下次载入 `self._states = {}` → 丢掉 `protected_torrents`
    （删除闸门第 1 类硬保护「手动保留」）、`manual_paused`、纳管标记。
  * 热层「有 ≥1 条就完全不读文件」→ Redis(allkeys-lru) 淘汰单键后，该键在冷备里
    被覆盖成永久消失。

本测试只看行为，不碰真实数据目录（全部 tempfile）。
退出码：0 = 全过；1 = 有失败（与 tools/test_gate_failclosed.py 同风格）。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import persistence as P  # noqa: E402

FAILS: list = []


def _ok(cond: bool, msg: str) -> None:
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        FAILS.append(msg)


class _WriteFail(P.KvBridge):
    """写盘恒失败（模拟磁盘满 / 权限错）。"""
    kv_region = "t_fail"

    def _write_file(self) -> bool:  # noqa: D102
        return False


class _WriteOk(P.KvBridge):
    kv_region = "t_ok"

    def _write_file(self) -> bool:  # noqa: D102
        return True


class _WriteRaise(P.KvBridge):
    """子类实现本不该抛；这里验证 KvBridge 的防御性兜底也不丢脏标记。"""
    kv_region = "t_raise"

    def _write_file(self) -> bool:  # noqa: D102
        raise OSError("disk full")


def main() -> int:
    print("== P2 落盘可见 / 原子写 / 不清空 / 只补缺键 ==")
    tmp = Path(tempfile.mkdtemp(prefix="mf_p2_"))
    try:
        # ---------- 1) flush_if_dirty：只有真写成功才清 dirty ----------
        print("\n[1] flush_if_dirty 的成败语义")
        s1 = _WriteFail()
        s1.dirty = True
        _ok(s1.flush_if_dirty() is False and s1.dirty is True,
            "写失败 → 返回 False 且 dirty 保持 True（下次重试）")

        s2 = _WriteOk()
        s2.dirty = True
        _ok(s2.flush_if_dirty() is True and s2.dirty is False,
            "写成功 → 返回 True 且 dirty 清空")

        s3 = _WriteRaise()
        s3.dirty = True
        _ok(s3.flush_if_dirty() is False and s3.dirty is True,
            "写抛异常 → 兜底返回 False 且 dirty 保持 True（不静默）")

        s4 = _WriteFail()
        s4.dirty = False
        _ok(s4.flush_if_dirty() is False, "未标脏 → 不写、返回 False（原语义不变）")

        # ---------- 2) 原子写：中途失败 → 原文件完好、不留 .tmp ----------
        print("\n[2] 原子写（tmp + os.replace）")
        d = tmp / "atomic.json"
        d.write_text('{"ok": 1}', encoding="utf-8")
        before = d.read_text(encoding="utf-8")
        raised = False
        try:
            # set 不可 JSON 序列化 → json.dump 中途抛 TypeError
            P.KvBridge._atomic_write_json(d, {"bad": {1, 2, 3}})
        except Exception:  # noqa: BLE001
            raised = True
        _ok(raised, "不可序列化数据 → 抛异常（不静默吞掉）")
        _ok(d.read_text(encoding="utf-8") == before, "原文件内容保持完好（没有半截 JSON）")
        _ok(not (tmp / "atomic.json.tmp").exists(), "失败后不留 .tmp 垃圾")

        P.KvBridge._atomic_write_json(d, {"ok": 2})
        _ok(json.loads(d.read_text(encoding="utf-8")) == {"ok": 2}, "成功路径写入正确内容")

        # ---------- 3) 只补缺键，绝不覆盖（热层权威）----------
        print("\n[3] 热层 + 冷备份并集：只补缺、不覆盖")
        tgt = {"a": 1, "b": 2}
        added = P.KvBridge._merge_missing(tgt, {"a": 99, "b": 99, "c": 3})
        _ok(added == 1 and tgt == {"a": 1, "b": 2, "c": 3},
            "只补热层没有的键；已有键（哪怕文件里更新）一律不覆盖")

        # ---------- 4) TaskStateStore：坏 JSON 不清空内存状态 + 留证 ----------
        print("\n[4] TaskStateStore 载入：坏 JSON 不再清空")
        st_dir = tmp / "states"
        st_dir.mkdir()
        st = P.TaskStateStore(st_dir, kv=None)
        st._states["t1"] = P.TaskState(task_id="t1")   # 模拟「热层已载入」的内存状态
        st.state_file.write_text("{ 这不是合法 JSON", encoding="utf-8")
        st._load()
        _ok("t1" in st._states, "文件解析失败 → 已有内存状态**保留**（旧实现在此清空）")
        _ok(any(p.name.startswith("task_states.json.corrupt.") for p in st_dir.iterdir()),
            "坏文件被改名留证（.corrupt.<ts>），不静默丢弃证据")
        _ok(not st.state_file.exists(), "坏文件已挪走（下次启动不会重复报错）")

        # ---------- 5) TaskStateStore：正常写盘 + 失败可检出 ----------
        print("\n[5] TaskStateStore 写盘成败")
        st2_dir = tmp / "states2"
        st2_dir.mkdir()
        st2 = P.TaskStateStore(st2_dir, kv=None)
        st2._states["t2"] = P.TaskState(task_id="t2")
        _ok(st2._write_file() is True and st2.state_file.exists(), "正常写盘 → True 且文件存在")
        _ok(json.loads(st2.state_file.read_text(encoding="utf-8")).get("t2") is not None,
            "写出的 JSON 可读回（格式未变）")

        bad_dir = tmp / "not_a_dir"
        bad_dir.write_text("x", encoding="utf-8")   # 路径被文件占住 → mkdir 必失败
        st3 = P.TaskStateStore(bad_dir, kv=None)
        _ok(st3._write_file() is False, "写目录不可用 → 返回 False（不再静默 pass）")
        st3.dirty = True
        _ok(st3.flush_if_dirty() is False and st3.dirty is True,
            "写目录不可用 → flush_if_dirty 不误报「已落盘」")

        # ---------- 6) 非 TaskState 的 Store 也走原子写 ----------
        print("\n[6] SeenStore 走统一原子写路径")
        seen_dir = tmp / "seen"
        seen_dir.mkdir()
        ss = P.SeenStore(seen_dir, kv=None)
        ss.mark("task-x", ["k1"])
        _ok(ss.file.exists() and json.loads(ss.file.read_text(encoding="utf-8")).get("task-x"),
            "SeenStore 正常落盘且内容可读回")

        print("\n" + "=" * 60)
        if FAILS:
            print(f"❌ P2 回归测试失败 {len(FAILS)} 项：")
            for f in FAILS:
                print("   - " + f)
            return 1
        print("✅ P2 回归测试全通过（落盘可见 / 原子写 / 不清空 / 只补缺键）")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as err:  # pragma: no cover
        print(f"❌ 断言失败: {err}")
        sys.exit(1)
