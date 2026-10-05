#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""棘轮：禁止新增「跨文件 self._xxx() 互调」。

背景
----
`features/*.py` 里 38 个 mixin 通过 `self._method()` 跨文件互调，是隐式耦合的根因。
本工具**不要求现在消除**这批调用，只要求**禁止新增**：

  1. 先用 `--record` 把当前所有 `{调用方文件::被调方法}` 的计数写进基线
     `tools/.self_calls_baseline.json`；
  2. 之后默认模式下，任何键的当前计数 **> 基线计数** → 打印明细并 **exit 1**；
     键消失（跨界调用被消除）是好事，不报错。

判定「跨界」：被调 `self._name` 的 `_name` **不在本文件定义的任何方法名里**，
但**出现在其它 features 文件的方法名集合里**。若同一方法名被多个文件定义，
忽略歧义，一律按「本文件没有就算跨界」处理。

用法
----
  python3 tools/check_self_calls.py            # 校验（棘轮），超基线则 exit 1
  python3 tools/check_self_calls.py --record   # 生成/更新基线
  python3 tools/check_self_calls.py --selftest # 合成源码自检判定逻辑

纯标准库（ast），无第三方依赖。
"""

import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FEATURES_DIR = os.path.join(ROOT, "features")
BASELINE_PATH = os.path.join(HERE, ".self_calls_baseline.json")


# --------------------------------------------------------------------------
# 核心分析（可对内存中的源码运行，便于 selftest）
# --------------------------------------------------------------------------
def collect_class_methods(tree):
    """收集一个模块里所有 class 定义的方法名（含 _ 开头）。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(item.name)
    return names


def collect_self_private_calls(tree):
    """收集所有形如 `self._name(...)` 的调用，返回被调方法名列表（含重复）。"""
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "self"
                and func.attr.startswith("_")
            ):
                calls.append(func.attr)
    return calls


def analyze(sources):
    """sources: {文件名: 源码字符串} -> 排序后的 {『文件::方法』: 计数}。

    只统计「本文件未定义、但其它文件定义了」的私有调用（跨界）。
    """
    trees = {}
    defined = {}
    for fname, src in sources.items():
        tree = ast.parse(src, filename=fname)
        trees[fname] = tree
        defined[fname] = collect_class_methods(tree)

    all_defined = set()
    for names in defined.values():
        all_defined |= names

    counts = {}
    for fname, tree in trees.items():
        own = defined[fname]
        for method in collect_self_private_calls(tree):
            if method in own:
                continue  # 本文件内部调用，不算跨界
            if method not in all_defined:
                continue  # 不在任何 features 文件定义，跳过
            key = "%s::%s" % (fname, method)
            counts[key] = counts.get(key, 0) + 1

    return {k: counts[k] for k in sorted(counts)}


def load_sources():
    sources = {}
    if not os.path.isdir(FEATURES_DIR):
        return sources
    for name in sorted(os.listdir(FEATURES_DIR)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(FEATURES_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            sources[name] = fh.read()
    return sources


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------
def cmd_record():
    sources = load_sources()
    counts = analyze(sources)
    payload = json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
        fh.write(payload)

    total = sum(counts.values())
    print("已记录基线：%d 条键，总调用 %d 次" % (len(counts), total))
    print("基线文件：%s" % BASELINE_PATH)
    if not counts:
        print("（无跨界 self._ 调用）")
    else:
        for key in sorted(counts, key=lambda k: (-counts[k], k)):
            print("  %-48s %d" % (key, counts[key]))
    return 0


def cmd_check():
    if not os.path.exists(BASELINE_PATH):
        print("❌ 基线不存在：%s" % BASELINE_PATH)
        print("   请先运行：python3 tools/check_self_calls.py --record")
        return 1

    with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    if not isinstance(baseline, dict):
        print("❌ 基线格式非法（应为 dict）")
        return 1

    current = analyze(load_sources())

    increased = []
    for key, cur in current.items():
        base = int(baseline.get(key, 0))
        if cur > base:
            increased.append((key, base, cur))

    if increased:
        print("❌ 检测到新增跨界 self._ 调用（棘轮生效）：")
        for key, base, cur in sorted(increased):
            print("   %-48s 基线 %d → 当前 %d (+%d)" % (key, base, cur, cur - base))
        print()
        print("   请改回「本文件内定义」或改用非隐式方式；")
        print("   确属必要：先评审，再运行 --record 重建基线（并说明理由）。")
        return 1

    total = sum(current.values())
    print("✅ 棘轮通过：%d 条键，总调用 %d 次（无新增）" % (len(current), total))
    return 0


def cmd_selftest():
    """用合成源码验证判定逻辑（真跑）。"""
    sources = {
        "file_a.py": (
            "class AMixin:\n"
            "    def _internal(self):\n"
            "        self._internal_ok()\n"
            "    def _internal_ok(self):\n"
            "        return 1\n"
            "    def run(self):\n"
            "        self._cross_file()   # 跨界：本文件未定义，file_b 有\n"
            "        self._internal_ok()  # 本文件内部：不算\n"
            "        self._nowhere()      # 谁都没定义：跳过\n"
        ),
        "file_b.py": (
            "class BMixin:\n"
            "    def _cross_file(self):\n"
            "        return 2\n"
        ),
    }
    counts = analyze(sources)

    ok = True
    cross_key = "file_a.py::_cross_file"
    if counts.get(cross_key) != 1:
        print("❌ selftest 失败：跨界调用未按预期识别（期望 %s=1，实际 %r）"
              % (cross_key, counts.get(cross_key)))
        ok = False
    else:
        print("✅ 识别跨界：%s = 1" % cross_key)

    # 本文件内部调用不得出现
    internal_key = "file_a.py::_internal_ok"
    if internal_key in counts:
        print("❌ selftest 失败：本文件内部调用被误判为跨界（%s）" % internal_key)
        ok = False
    else:
        print("✅ 未误报本文件内部调用：%s" % internal_key)

    # 未定义调用不得出现
    nowhere_key = "file_a.py::_nowhere"
    if nowhere_key in counts:
        print("❌ selftest 失败：未定义方法被误判（%s）" % nowhere_key)
        ok = False
    else:
        print("✅ 未误报未定义方法：%s" % nowhere_key)

    # 反向：file_b 里 self._internal_ok 应被识别为跨界（file_a 定义）
    sources2 = dict(sources)
    sources2["file_b.py"] = (
        "class BMixin:\n"
        "    def _cross_file(self):\n"
        "        self._internal_ok()\n"
    )
    counts2 = analyze(sources2)
    rev_key = "file_b.py::_internal_ok"
    if counts2.get(rev_key) != 1:
        print("❌ selftest 失败：反向跨界未识别（%s 期望 1，实际 %r）"
              % (rev_key, counts2.get(rev_key)))
        ok = False
    else:
        print("✅ 反向识别跨界：%s = 1" % rev_key)

    if ok:
        print("PASS")
        return 0
    return 1


def main(argv):
    args = argv[1:]
    if "--selftest" in args:
        return cmd_selftest()
    if "--record" in args:
        return cmd_record()
    if args:
        print("用法：check_self_calls.py [--record|--selftest]")
        return 2
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
