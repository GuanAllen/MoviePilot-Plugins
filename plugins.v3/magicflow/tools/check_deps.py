#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流（MagicFlow）依赖方向检查器 —— 硬护栏 #1。

规则（契约）：
  层级 L0  leaf/基础设施：kvstore.py, fingerprint.py, models.py, persistence.py, utils 等
  层级 L1  领域模块：bonus.py, collect.py, fetcher.py, sites/*, rulepack.py, live_stats.py ...
  层级 L2  features/*（mixin）
  层级 L3  __init__.py（组装）

  允许：L(n) → L(m)，m <= n（同层允许，但不能成环）。
  禁止：
    - 任何模块 import `magicflow` 包本身（= `__init__.py`），会成环；
    - L0/L1 模块 import features/*；
    - 模块级（顶层）import 成环。
      ★ 19.10.12：函数/方法体内的**延迟 import** 不算环（本仓库官方拆环手法：
      `tags.duty_assign` 惰性导入 `dutyreg`、`hr._hr_host_assign` 惰性导入 `common`），
      但它**仍计入依赖方向**（L0/L1 倒挂照抓）。

用法：python3 tools/check_deps.py [--verbose] [--json]
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "magicflow"

# 层级定义：文件（相对 ROOT 的 POSIX 路径）→ 层号
L0 = {
    "kvstore.py", "fingerprint.py", "models.py", "persistence.py",
    "douban.py", "rulepack.py", "sitecap.py", "dtier.py",
    "db.py", "tables.py",   # 插件自有表（SQLAlchemy 模型）—— 纯基础设施
    "codedict.py",          # 代码字典：纯 ast 解析自身源码（11.12.0）
    "qbsync.py",            # qB 增量同步快照（/sync/maindata?rid=，纯内存，15.3.0）
    "norm.py",              # 数据清洗纯函数（文本归一/数值/时间），L0 唯一出口（19.10.16）
    "envops.py",            # 外部环境能力唯一出口（插件日志 / MP 站点·下载器清单），19.10.21
    #   只 import 标准库；app.* 一律函数内延迟导入，故不依赖任何其他插件模块。
    "cacheops.py",          # 进程内缓存的惯用法（信封/过期判定/有界容器/冷却/单飞），19.10.22
    #   ★ 不是缓存底座：要跨热重载存活且可 JSON 的值走 dtier.TierCache，见 ADR-0001。
    "shared.py",            # 跨热重载的进程级共享槽（单例 / 锁 / 计数器），19.10.25
    #   只 import 标准库；原先这段「取槽 + 幂等补齐属性」在 7 个模块各抄一份，
    #   每处都得重新踩「缺 lock → AttributeError → 插件加载失败」和
    #   「热重载后类是新的、单例是旧实例 → 新方法 AttributeError」。见模块 docstring。
    "tagspec.py",           # 标签编解码纯函数 + 全部常量（原 tags.py 前半，19.10.27 下沉）
    #   只 import 标准库；无 host、不碰 app.*、可 `python3 tagspec.py` 离线自测。
    #   ``tags.py`` 反过来 import 它（媒体编排留 L1），故本条边是 L1 → L0 的正当方向；
    #   models.py / ledger.py 也能直接取常量，不再为了一个词表往上穿到 L1。
    "collect_parse.py",     # 页面/XML/JSON → 规整事实（22 个 parse_*，原 collect.py 解析段，19.10.31 下沉）
    #   只 import 标准库 + norm；**不** import common（common 顶层 from app.schemas.types）
    #   → 离线测试可直接 spec_from_file_location 加载，不必造 app 桩。
    #   ``collect.py`` 反过来全量 re-export 它，业务模块的 import 面保持不变。
    #   ★ 新增解析写这里；HTTP/配额/事实库仍归 collect.py（L1）。
    "level_req.py",         # 站点等级表 + 升级要求计算（抄 PT-depiler 站点模型，19.11.18）
    #   只 import 标准库；纯数据 + 纯函数，离线测试直接加载（tools/test_level_req.py）。
    "storekit.py",          # 存储数据层：4 个数据模型 + KvBridge（冷热双写桥）+ 冷层惯用法（19.10.33 下沉）
    #   只 import json/os/threading/time/pathlib + 标准库 dataclasses；app.log 仅 try 兜底。
    #   ``persistence.py`` 反过来显式 re-export 它的全部名字（40+ 处 import 零改动）。
    #   ★ 只放「自己处理数据」的：模型编解码 / 容错读 / 原子写 / 差分写热层。
    #     带业务口径的 Store（操作日志 / 任务状态 / 闸门 / 推荐 / 云归档）与后台 flusher
    #     仍归 persistence.py（L1 编排），别往上塞。
    "collect_rows.py",      # 站点列表页 / API 行 → 候选种子（SiteCandidateTorrent，19.10.35 下沉）
    #   只 import re/time/dataclasses/datetime/typing/urllib.parse —— 零 host 依赖。
    #   ``fetcher.py`` 反过来显式 re-export 它的全部名字（26 个），调用点零改动。
    #   ★ 判据不是行数，是「改的理由不同源」：解析因**站点换皮肤**而改，抓取因**网络/配额
    #     策略**而改。原来挤在 fetcher.py 里，调一次皮肤都要绕开 SiteFetcher 与 _ensure_sdk()。
    #   ★ SiteCandidateTorrent 定义在文件**前部**：它被 parse_yema_rows 的返回注解引用，
    #     而 PEP 649（惰性求值）要 Python 3.14 —— 更早的版本会在导入期立即求值 → NameError。
    #   ⚠ 新增「页面 → 候选」的解析写这里；翻页 / 限流 / 初筛仍归 fetcher.py（L1）。
}
L1 = {
    "bonus.py", "collect.py", "fetcher.py", "live_stats.py", "fallback.py",
    "downloader_ops.py", "cloud_archive.py", "crossseed.py", "iyuu_cloud.py",
    "recommend.py", "signin.py", "tags.py",
    "dutyreg.py",  # ★ 19.10.11 岗位注册表：纯数据+纯函数，只依赖 tags（可离线加载）。
    #   职务派生/岗位反查/抢占优先级/可设白名单的唯一真值；加岗位只改这张表。
    "dutyops.py",  # ★ 19.10.12 岗位操作（占岗/退岗/让位）：只依赖 dutyreg + tags。
    #   assign/release/free_for/claim_hashes 是「纳管」流程的唯一实现，
    #   H&R / 认领 / 手动保种 / 音乐 / 点播都走它，不再各写一份。
    "dlops.py",    # ★ 19.10.13 下载器写操作唯一出口：只依赖 dutyreg + tags。
    #   pause/resume/recheck 的归因（by）+ 账本守卫 + 防抖（90s 反向操作拒绝），
    #   解决「930 停 / 911 起 精确对消却查不到是谁」的结构性问题。
    "ledger.py",   # 种子/资源台账（SQLAlchemy 后端，依赖 tags/common）
    "sitestore.py",  # 站点/能力/跨站来源 三套 kv 账本 → 表（12.1.0 WS2 桥接层）
}
L2_PREFIX = "features/"
L1_PREFIXES = ("sites/", "signin_sites/", "claim_sites/")   # L1 域的包（站点解析 / 站点签到适配器 / 站点认领写动作）
L3 = {"__init__.py", "common.py", "dupgate.py"}


def layer_of(rel: str) -> int | None:
    """层级查询；未登记 → None（登记制硬护栏）。"""
    if rel in L3:
        return 3
    if rel in L0:
        return 0
    if rel in L1:
        return 1
    if rel.startswith(L2_PREFIX):
        return 2
    if rel.startswith(L1_PREFIXES):
        return 1
    return None


def mod_name(rel: str) -> str:
    """文件 → 逻辑模块名（用于依赖图）：features/x.py → features.x；x.py → x"""
    rel = rel.removesuffix(".py")
    rel = rel.replace("/__init__", "")
    return rel.replace("/", ".")


def resolve(cur_mod: str, target: str, level: int, is_pkg: bool = False) -> str | None:
    """把相对 import 解析成绝对模块名（以 magicflow 为根）。

    Python 语义：`from .x import y` 的 level=1 表示「当前包」；
    对 `pkg/__init__.py` 来说「当前包」= pkg 自身（is_pkg=True 时层级要少减 1）。
    """
    if level == 0:
        return target if target else None
    cur = cur_mod.split(".")
    eff = level - (1 if is_pkg else 0)
    if eff > len(cur):
        return None
    base = cur[: len(cur) - eff] if eff else cur
    parts = base + ([target] if target else [])
    return ".".join(parts)


def collect() -> dict:
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*.py")
        if "node_modules" not in p.parts
        and "_backup" not in p.parts
        and "__pycache__" not in p.parts
        and not p.relative_to(ROOT).as_posix().startswith("tools/")
    )
    known = {
        SELF + "." + (m if m != "__init__" else "")
        for m in (mod_name(f) for f in files)
    }
    known = {k.rstrip(".") for k in known}
    known |= {SELF}
    graph: dict[str, set[str]] = {mod_name(f): set() for f in files}
    raw: list[tuple[str, str, int, int, bool]] = []
    for f in files:
        try:
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        except SyntaxError as e:  # noqa: PERF203
            print(f"❌ 语法错误 {f}: {e}")
            continue
        cur = SELF + "." + f.removesuffix(".py").replace("/", ".")
        is_pkg = f.endswith("/__init__.py") or f == "__init__.py"
        if is_pkg:
            cur = cur[: -len(".__init__")]
        # ★ 19.10.12：区分「顶层 import」与「函数内延迟 import」。
        #   环检测只认顶层（契约原文就是「模块级 import 成环」）；函数内 import 是
        #   本仓库**官方拆环手法**（见 `features/hr.py::_hr_host_assign` 惰性导入 common、
        #   `tags.py::duty_assign` 惰性导入 dutyreg），在导入期不执行，不构成加载环。
        #   层级倒挂（L0/L1 → features）仍然两种都算 —— 那是方向问题，与执行时机无关。
        _nested: set[int] = set()
        for _n in ast.walk(tree):
            if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for _sub in ast.walk(_n):
                    if isinstance(_sub, (ast.Import, ast.ImportFrom)):
                        _nested.add(id(_sub))
        for node in ast.walk(tree):
            _top = id(node) not in _nested
            if isinstance(node, ast.ImportFrom):
                base = resolve(cur, node.module or "", node.level, is_pkg)
                if not base:
                    continue
                if node.module:
                    cands = [base]
                else:
                    # `from . import A, B`：逐个名字判断是不是本插件模块
                    cands = [base + "." + a.name for a in node.names]
                for c in cands:
                    c = c.rstrip(".")
                    if c in known:
                        raw.append((f, c.replace(SELF + ".", "") if c != SELF else "__init__", 0, node.lineno, _top))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == SELF or a.name.startswith(SELF + "."):
                        raw.append((f, a.name[len(SELF) + 1:] or "__init__", 0, node.lineno, _top))
    graph_top: dict[str, set[str]] = {mod_name(f): set() for f in files}
    for f, dep, _lvl, _ln, _top in raw:
        graph.setdefault(mod_name(f), set()).add(dep)
        if _top:
            graph_top.setdefault(mod_name(f), set()).add(dep)
    return {"files": files, "graph": graph, "graph_top": graph_top, "raw": raw}


def main() -> int:
    verbose = "--verbose" in sys.argv
    data = collect()
    files, graph = data["files"], data["graph"]
    rel_of = {mod_name(f): f for f in files}
    violations: list[str] = []

    # 1) 禁止 import 包本身（__init__）
    for mod, deps in graph.items():
        if "__init__" in deps:
            violations.append(f"[包自引用] {rel_of.get(mod, mod)} import 了 magicflow 包本身（→ __init__），会成环")

    # 1b) 登记制：每个模块必须在层级表里登记
    for f in files:
        if layer_of(f) is None:
            violations.append(
                f"[未登记] {f} 不在 L0/L1/L2/L3 层级表 —— 新模块必须先登记（tools/check_deps.py）"
            )

    # 2) L0/L1 不得 import features/*
    for mod, deps in graph.items():
        lay = layer_of(rel_of.get(mod, mod + ".py"))
        if lay is not None and lay <= 1:
            for d in deps:
                if d == "features" or d.startswith("features."):
                    violations.append(f"[层级倒挂] L{lay} 模块 {rel_of.get(mod, mod)} import 了 {d}")

    # 3) 环检测（**模块级/顶层** import；函数内延迟 import 不算 —— 见 collect() 注释）
    graph_top = data["graph_top"]
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in sorted(graph_top.get(u, ())):
            if v not in graph_top and "." in v:
                # 直接指向子模块名（如 sites.rules 存在时 ok；不存在则跳过）
                continue
            if v not in graph_top:
                continue
            if color.get(v, 0) == 1:
                cyc = stack[stack.index(v):] + [v]
                violations.append("[循环依赖] " + " → ".join(cyc))
            elif color.get(v, 0) == 0:
                dfs(v)
        stack.pop()
        color[u] = 2

    for m in sorted(graph):
        if color.get(m, 0) == 0:
            dfs(m)

    print(f"检查模块 {len(files)} 个；依赖边 {sum(len(v) for v in graph.values())} 条")
    if verbose:
        for m in sorted(graph):
            print(f"  {m:28s} → {', '.join(sorted(graph[m])) or '-'}")
    if violations:
        print(f"\n❌ 发现 {len(violations)} 处违规：")
        for v in violations:
            print("  " + v)
        return 1
    print("\n✅ 依赖方向检查通过")
    return 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps({k: sorted(v) for k, v in collect()["graph"].items()}, ensure_ascii=False, indent=1, sort_keys=True))
        raise SystemExit(0)
    raise SystemExit(main())
