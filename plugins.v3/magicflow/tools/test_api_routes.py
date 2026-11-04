#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · API 路由表检查器的**反向**回归 —— 钉住「它真的会红」。

`tools/check_api_routes.py` 是 preflight 第 25 步。一个永远绿的检查器等于没有，
所以这里用临时目录造四类坏表，逐条验证检查器确实报错，再验证干净表确实通过：

  [1] 干净表通过（146 条真实表 → 零错误）；
  [2] 同一 (path, method) 注册两次 → R3 报「重复路由」；
  [3] 同一 path 不同 method → 合法（GET/POST 并存是常态），不报；
  [4] handler 名字不存在 → R4 报「改名或搬走后没跟上」；
  [5] 通配路由写在字面量前面 → R5 报「被更早注册的 ... 遮蔽」；
  [6] 字面量写在通配前面 → 合法，不报（顺序正确就是对的）；
  [7] 未知 method（如 Get/FOO）→ R1 报；
  [8] path 规范（末尾斜杠 / 空段）→ R2 报；
  [9] 与 /agent 路由撞 (path, method) → R6 报；
  [10] 4 元组写错（3 元组 / 非字符串）→ 结构性报错，不静默跳过。

用法：``python3 tools/test_api_routes.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_api_routes_test"

_fails: list[str] = []
_n = 0


def ok(cond, msg: str) -> None:
    global _n
    _n += 1
    if not cond:
        _fails.append(msg)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


chk = _load(PKG + ".chk", "tools/check_api_routes.py")

API_TPL = '''# -*- coding: utf-8 -*-
from typing import Any, Dict, List


_ROUTES = (
{rows}
)


class ApiMixin:
    def get_api(self) -> List[Dict[str, Any]]:
        return []
'''

AGENT_TPL = '''# -*- coding: utf-8 -*-
from typing import Any, Dict, List


def _agent_endpoints() -> List[Dict[str, Any]]:
    return [
{rows}
    ]
'''


def _tree(rows: list, agent_rows: list | None = None) -> Path:
    """造一棵只含 features/api.py（+ agentapi.py）的假树，返回 root。"""
    tmp = Path(tempfile.mkdtemp(prefix="mf_routes_"))
    (tmp / "features").mkdir(parents=True, exist_ok=True)
    body = "\n".join("    " + r for r in rows)
    (tmp / "features" / "api.py").write_text(API_TPL.format(rows=body), encoding="utf-8")
    abody = "\n".join("    " + r for r in (
        agent_rows if agent_rows is not None
        else ['{"path": "/agent", "method": "GET", "handler": "agent_manifest"},']))
    (tmp / "features" / "agentapi.py").write_text(AGENT_TPL.format(rows=abody), encoding="utf-8")
    return tmp


def _run(rows: list, agent_rows: list | None = None) -> list:
    """跑一遍检查，返回错误列表（空=通过）。"""
    tmp = _tree(rows, agent_rows)
    saved_root, saved_feat = chk.ROOT, chk.FEATURES_DIR
    chk.ROOT = tmp
    chk.FEATURES_DIR = ROOT / "features"      # 用真实 Mixin 集，handler 名字才有意义
    chk._ERRORS.clear()
    try:
        routes = chk._read_routes()
        if routes:
            chk._check_route_specs(routes)
            chk._check_duplicates(routes)
            chk._check_handlers(routes, chk._collect_mixin_methods())
            chk._check_first_match(routes)
            chk._check_agent_conflict(routes)
        return list(chk._ERRORS)
    finally:
        chk.ROOT, chk.FEATURES_DIR = saved_root, saved_feat
        chk._ERRORS.clear()


def _has(errs: list, *needles: str) -> bool:
    return any(all(n in e for n in needles) for e in errs)


def main() -> int:
    print("== API 路由表检查器 · 反向回归 ==")

    # [1] 真实表必须过
    chk._ERRORS.clear()
    real = chk._read_routes()
    chk._check_route_specs(real)
    chk._check_duplicates(real)
    chk._check_handlers(real, chk._collect_mixin_methods())
    chk._check_first_match(real)
    chk._check_agent_conflict(real)
    ok(not chk._ERRORS, f"[1] 真实表零错误，实际 {chk._ERRORS[:2]}")
    # 条数快照：**加/删路由要一起改这里**（它是「表被人动过」的锚，不是业务断言）。
    # 143 → 145：19.11.0 加 /ondemand/batch（多选一并点播），另有一条同批新增。
    ok(len(real) == 146, f"[1] 真实表 146 条（实际 {len(real)}）")
    chk._ERRORS.clear()

    GOOD = '("/pool", "pool_info", "GET", "池盘空间"),'

    # [2] 重复 (path, method)
    errs = _run([GOOD, GOOD])
    ok(_has(errs, "重复路由", "/pool"), f"[2] 重复路由被抓，实际 {errs}")

    # [3] 同 path 不同 method 合法
    errs = _run([GOOD, '("/pool", "get_status", "POST", "另一方法"),'])
    ok(not errs, f"[3] GET/POST 并存不报错，实际 {errs}")

    # [4] handler 不存在
    errs = _run(['("/pool", "no_such_handler_xyz", "GET", "池盘空间"),'])
    ok(_has(errs, "no_such_handler_xyz", "不存在"), f"[4] 幽灵 handler 被抓，实际 {errs}")

    # [5] 通配排在字面量前面 → 遮蔽
    errs = _run(['("/tasks/{task_id}", "get_task_detail", "GET", "详情"),',
                 '("/tasks/batch", "get_task_bonus", "GET", "批量"),'])
    ok(_has(errs, "遮蔽"), f"[5] 通配遮蔽被抓，实际 {errs}")

    # [6] 字面量排在通配前面 → 合法
    errs = _run(['("/tasks/batch", "get_task_bonus", "GET", "批量"),',
                 '("/tasks/{task_id}", "get_task_detail", "GET", "详情"),'])
    ok(not errs, f"[6] 正确顺序不报错，实际 {errs}")

    # [7] 未知 method
    errs = _run(['("/pool", "pool_info", "get", "池盘空间"),'])
    ok(_has(errs, "未知 method"), f"[7] 小写 method 被抓，实际 {errs}")

    # [8] path 规范
    errs = _run(['("/pool/", "pool_info", "GET", "池盘空间"),'])
    ok(_has(errs, "以 / 结尾"), f"[8a] 末尾斜杠被抓，实际 {errs}")
    errs = _run(['("/pool//x", "pool_info", "GET", "池盘空间"),'])
    ok(_has(errs, "空段"), f"[8b] 空段被抓，实际 {errs}")

    # [9] 与 agent 路由撞车
    errs = _run([GOOD], ['{"path": "/pool", "method": "GET", "handler": "agent_manifest"},'])
    ok(_has(errs, "撞车"), f"[9] agent 撞车被抓，实际 {errs}")

    # [10] 结构错误不被静默跳过
    errs = _run(['("/pool", "pool_info", "GET"),'])
    ok(_has(errs, "不是 4 元组"), f"[10a] 3 元组被抓，实际 {errs}")
    errs = _run(['("/pool", "pool_info", "GET", 42),'])
    ok(_has(errs, "字符串字面量"), f"[10b] 非字符串被抓，实际 {errs}")

    # [11] 空 summary
    errs = _run(['("/pool", "pool_info", "GET", "  "),'])
    ok(_has(errs, "summary 为空"), f"[11] 空 summary 被抓，实际 {errs}")

    print()
    if _fails:
        print(f"❌ FAIL {len(_fails)}/{_n}")
        for m in _fails:
            print(f"   - {m}")
        return 1
    print(f"✅ PASS {_n}/{_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
