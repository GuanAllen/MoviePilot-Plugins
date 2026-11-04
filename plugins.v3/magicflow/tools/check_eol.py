#!/usr/bin/env python3
"""仓库换行符护栏（护栏⑭，preflight 第 24 步）：.py / .sh 必须是纯 LF。

为什么需要这一步
----------------
`pathlib.Path.write_text(s, encoding="utf-8")` 在 Windows 上 `newline=None`
（默认值）会把 `\\n` 翻译成平台分隔符 `\\r\\n`。于是任何用脚本改过的文件，
换行符就从 LF 变成 CRLF，而 Python 解释器完全不在乎——功能正常、测试全绿，
代价全在别处：

  ① git diff 把整文件显示成重写，review 完全失效（几百行 vs 真实改 7 行）
  ② diff / patch 类校验失真：2026-10-28 用备份做改动比对时，因换行差异
     看不到真实改动，必须先归一化才看出「其实只改了 7–33 行」
  ③ 混合换行（同一文件里既有 CRLF 又有 LF）会让按行切割的逻辑出现幽灵 `\\r`

实测累积（2026-10-29）：27 个文件全 CRLF，横跨 tags.py / ledger.py /
features/silent.py / common.py 等十余个版本，不是单次事故。

修复方式
--------
`p.write_bytes(p.read_bytes().replace(b"\\r\\n", b"\\n"))` —— 字节级替换，
不经过 text 模式，天然无损（可逆验证：反向 `\\n → \\r\\n` 应得回原字节）。

以后所有脚本改文件统一用 `write_text(s, encoding="utf-8", newline="")`。
"""
from __future__ import annotations

import pathlib
import sys

DEFAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 只查源码；dist/ 是构建产物，vendor 的换行由上游决定
SUFFIXES = (".py", ".sh")
SKIP_DIRS = {"dist", ".build-fe", "node_modules", "__pycache__", ".git",
             ".venv", "venv", "_backup"}


def scan(root: pathlib.Path) -> list[tuple[str, int, int, bool]]:
    """返回 [(相对路径, CRLF 行数, LF 行数, 是否混合)]，只报有问题的文件。"""
    bad = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in SUFFIXES:
            continue
        if set(p.parts) & SKIP_DIRS:
            continue
        try:
            b = p.read_bytes()
        except OSError:
            continue
        if not b:
            continue
        n_crlf = b.count(b"\r\n")
        if not n_crlf:
            continue
        n_lf = b.count(b"\n")
        bad.append((p.relative_to(root).as_posix(), n_crlf, n_lf, n_crlf != n_lf))
    return bad


def main() -> int:
    args = sys.argv[1:]
    verbose = "--verbose" in args
    root = DEFAULT_ROOT
    if "--root" in args:
        root = pathlib.Path(args[args.index("--root") + 1]).resolve()

    bad = scan(root)
    total = sum(1 for p in root.rglob("*")
                if p.is_file() and p.suffix in SUFFIXES
                and not (set(p.parts) & SKIP_DIRS))

    if not bad:
        if verbose:
            print(f"  ✅ 扫描 {total} 个 .py/.sh，全部为纯 LF")
        return 0

    print(f"  ❌ {len(bad)}/{total} 个文件含 CRLF（必须是纯 LF）")
    for rel, n_crlf, n_lf, mixed in bad:
        tag = "混合换行" if mixed else "全 CRLF"
        print(f"     {rel}  {tag}：{n_crlf}/{n_lf} 行")
    print()
    print("  修复（字节级替换，无损）：")
    print('    p = pathlib.Path("X"); p.write_bytes(p.read_bytes().replace(b"\\r\\n", b"\\n"))')
    print('  以后脚本改文件：write_text(s, encoding="utf-8", newline="")')
    return 1


if __name__ == "__main__":
    sys.exit(main())
