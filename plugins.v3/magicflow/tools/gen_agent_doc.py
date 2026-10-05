#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 从能力清单**自动生成** ``docs/AGENT-API.md`` 的端点表附录。

契约 §5.2 / §1.8：「文档从清单自动生成」—— 手写部分只保留原则，端点表由
``_agent_endpoints()``（唯一真值源）生成，禁止手改表格。

用法：``python3 tools/gen_agent_doc.py``
  - 找到 ``docs/AGENT-API.md`` 里的 ``<!-- AGENT_ENDPOINTS_TABLE_START -->`` /
    ``<!-- AGENT_ENDPOINTS_TABLE_END -->`` 标记块并原地重写；无标记则文末追加。
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from check_agent_manifest import _load_agentapi  # noqa: E402

START = "<!-- AGENT_ENDPOINTS_TABLE_START -->"
END = "<!-- AGENT_ENDPOINTS_TABLE_END -->"


def build_table() -> str:
    agentapi = _load_agentapi()
    data = agentapi.AgentApiMixin()._agent_manifest_data()
    lines = [
        "| 端点 | 方法 | 写 | 参数 | 返回 | 版本 |",
        "|---|---|---|---|---|---|",
    ]
    for e in data["endpoints"]:
        params = ", ".join(f"`{k}`: {v}" for k, v in (e.get("params") or {}).items()) or "—"
        write = "✓" if e.get("write") else ""
        lines.append(
            f"| `{e['path']}` | {e['method']} | {write} | {params} | "
            f"`{e['returns']}` | {e['version']} |"
        )
    return "\n".join(lines)


def main() -> int:
    doc = ROOT / "docs" / "AGENT-API.md"
    text = doc.read_text(encoding="utf-8")
    table = build_table()
    block = f"{START}\n{table}\n{END}"
    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text,
                     flags=re.S)
    else:
        new = text.rstrip() + "\n\n" + block + "\n"
    doc.write_text(new, encoding="utf-8")
    print(f"✅ 已生成端点表 → {doc.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
