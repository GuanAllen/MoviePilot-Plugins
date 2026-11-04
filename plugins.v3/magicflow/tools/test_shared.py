#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · shared（进程级共享槽）离线回归 —— 钉住「热重载后仍是同一份」的契约。

背景（2026-10-29）：取 ``__magicflow_shared__`` 槽 + 幂等补齐属性的逻辑原先抄了 7 遍
（cacheops / common / siteops×2 / tags×2 / kvstore / persistence），每处都在注释里
记一遍「踩过」。收敛成一个 L0 模块后，本文件钉住最容易悄悄退化的事：

  [1] 离线可加载（纯标准库，顶层无 ``app.*``）；
  [2] ``module()`` 幂等补齐 —— 任一入口先建、缺属性，后面补回来（否则 AttributeError
      会让**整个插件加载失败**）；
  [3] ``module()`` 反复调用是同一对象（不是每次新建）；
  [4] ``lock()`` 同名同一把，且**跨热重载仍是同一把**（这是它存在的唯一理由）；
  [5] ``singleton()`` 只建一次，``factory`` 不重复执行；
  [6] ``singleton()`` 撞上「旧类的实例」→ 重建（热重载后新方法缺失的那个坑）；
  [7] ``singleton()`` 并发只建一次（否则双单例互相覆盖账本）；
  [8] ``singleton()`` 的 ``factory`` 抛异常 → 注册表不被污染，下次还能重试；
  [9] ``bump()`` 原子累加；``counters()`` 返回原 dict（kvstore 直接往里写的兼容要求）。

用法：``python3 tools/test_shared.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_shared_test"

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


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    # 先给一个「假父包」：``importlib.reload`` 要求父包在 sys.modules 里才肯干活
    # （目录名带连字符，不能按普通包导入，只能手工拼）
    if "." in name:
        parent = name.rsplit(".", 1)[0]
        if parent not in sys.modules:
            pkg = types.ModuleType(parent)
            pkg.__path__ = [str(ROOT)]
            sys.modules[parent] = pkg
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- [1] 离线加载
assert "app" not in sys.modules, "测试环境已污染：加载 shared 前不应存在 app 模块"
shared = _load(PKG + ".shared", "shared.py")
ok("app" not in sys.modules, "[1] 纯标准库，加载后仍未引入 app.*")
ok(shared.KEY == "__magicflow_shared__", "[1] 槽名与 kvstore / persistence 约定一致")

# ---------------------------------------------------------------- [2] 幂等补齐
print("\n[2] module() 幂等补齐（防插件加载失败）")
slot = shared.module()
for attr in ("instances", "counters", "singletons", "lock"):
    assert hasattr(slot, attr), attr
ok(True, "[2] 首次取槽就补齐四个属性")

# 模拟历史事故：某入口只建了 instances / counters，没有 lock
del slot.lock
again = shared.module()
ok(hasattr(again, "lock"), "[2] 缺 lock 的槽被补回来（否则另一入口读 mod.lock 直接 AttributeError）")

# ---------------------------------------------------------------- [3] 同一对象
print("\n[3] module() 反复调用是同一对象")
ok(shared.module() is shared.module() is slot, "[3] 同一槽对象（不是每次新建模块）")

# ---------------------------------------------------------------- [4] 锁跨重载
print("\n[4] lock() 同名同一把 + 跨热重载存活")
lk1 = shared.lock("rules_probe")
lk2 = shared.lock("other")
ok(lk1 is shared.lock("rules_probe"), "[4] 同名取回同一把锁")

reloaded = importlib.reload(shared)
lk3 = reloaded.lock("rules_probe")
ok(lk3 is lk1, "[4] 模块 reload 后仍是同一把锁（热重载换实例，旧线程照样互斥）")
ok(reloaded.lock("other") is lk2, "[4] 另一个名字也保持稳定")
ok(reloaded.lock("rules_probe") is not reloaded.lock("other"), "[4] 不同名字是不同锁（不是全局一把）")

with reloaded.lock("demo"):
    ok(reloaded.lock("demo").locked() is True, "[4] with 期间 locked() 为真")
ok(reloaded.lock("demo").locked() is False, "[4] 退出 with 后释放")

# 一次性迁移：把散装实现的那个槽名搬过来。不做这一步的话，迁移那一刻
# 新旧实例各拿一把不同的锁 —— 正是这把锁要防的事。
reloaded.module().instances["legacy_probe_lock"] = threading.Lock()
old_lk = reloaded.module().instances["legacy_probe_lock"]
migrated = reloaded.lock("probe", legacy="legacy_probe_lock")
ok(migrated is old_lk, "[4] legacy 槽里的锁被搬过来（不是新建一把）")
ok(reloaded.lock("probe") is old_lk, "[4] 迁移后再取还是同一把（第二次走新槽名）")
ok(reloaded.lock("probe2", legacy="nope-not-there") is not old_lk, "[4] legacy 指向不存在 → 正常新建")

# ---------------------------------------------------------------- [5] 单例只建一次
print("\n[5] singleton() 只建一次")
calls = {"n": 0}


class Ledger:
    def __init__(self) -> None:
        calls["n"] += 1


a = shared.singleton("test-ledger", Ledger, Ledger)
b = shared.singleton("test-ledger", Ledger, Ledger)
ok(a is b, "[5] 两次取到同一实例")
ok(calls["n"] == 1, f"[5] factory 只执行一次（实际 {calls['n']}）")
ok(isinstance(a, Ledger), "[5] 返回的就是 factory 建出来的类型")

# ---------------------------------------------------------------- [6] 旧类重建
print("\n[6] 撞上旧类实例 → 重建")


class OldLedger:
    """模拟热重载前那一代的类（没有新方法）。"""


shared.module().instances["stale-ledger"] = OldLedger()
fresh_obj = shared.singleton("stale-ledger", Ledger, Ledger)
ok(isinstance(fresh_obj, Ledger), "[6] 旧类实例被判定不匹配并重建")
ok(not isinstance(fresh_obj, OldLedger), "[6] 拿到的不是旧实例")
ok(shared.module().instances["stale-ledger"] is fresh_obj, "[6] 注册表已换成新实例")

# 不给 cls 时不做校验（persistence 那种要自己管换类的对象走这里之外）
shared.module().instances["noclS-ledger"] = OldLedger()
kept = shared.singleton("noclS-ledger", Ledger)
ok(isinstance(kept, OldLedger), "[6] 不传 cls → 不做类型校验，原样返回（留给特殊对象自己管）")

# ---------------------------------------------------------------- [7] 并发只建一次
print("\n[7] singleton() 并发只建一次")
build = {"n": 0}
barrier = threading.Barrier(8)
results: list = []
res_lock = threading.Lock()


class Contended:
    def __init__(self) -> None:
        build["n"] += 1


def _race() -> None:
    barrier.wait()
    obj = shared.singleton("race-ledger", Contended, Contended)
    with res_lock:
        results.append(obj)


threads = [threading.Thread(target=_race) for _ in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
ok(build["n"] == 1, f"[7] 8 线程并发 → factory 只执行 1 次（实际 {build['n']}）")
ok(len({id(x) for x in results}) == 1, "[7] 8 个线程拿到的是同一个实例")

# ---------------------------------------------------------------- [8] 失败不污染
print("\n[8] factory 抛异常 → 注册表干净")


def _boom():
    raise RuntimeError("建不出来")


try:
    shared.singleton("broken-ledger", _boom, Ledger)
    ok(False, "[8] 异常应当向外抛")
except RuntimeError:
    ok(True, "[8] 异常照常抛给调用方（不吞）")
ok(shared.peek("broken-ledger") is None, "[8] 失败没有留在注册表里")

retried = shared.singleton("broken-ledger", Ledger, Ledger)
ok(isinstance(retried, Ledger), "[8] 下次还能成功重试（失败不被固化）")

# ---------------------------------------------------------------- [9] 计数器
print("\n[9] bump 原子累加 / counters 返回原 dict")
for _ in range(5):
    shared.bump("hot_writes")
ok(int(shared.counters().get("hot_writes") or 0) >= 5, "[9] 连续自增生效")
ok(shared.counters() is shared.module().counters, "[9] counters() 返回原 dict（kvstore 直接往里写要兼容）")

shared.counters()["hot_writes"] = 100          # kvstore 现在的写法
ok(shared.bump("hot_writes", 2) == 102, "[9] bump 在外部写入的基数上继续累加")

cnt = {"n": 0}
cnt_lock = threading.Lock()


def _bump_many() -> None:
    for _ in range(200):
        shared.bump("race_counter")


bthreads = [threading.Thread(target=_bump_many) for _ in range(6)]
for t in bthreads:
    t.start()
for t in bthreads:
    t.join()
ok(int(shared.counters().get("race_counter") or 0) == 1200,
   f"[9] 6×200 并发自增无丢失（实际 {shared.counters().get('race_counter')}）")

print()
if _fails:
    print(f"❌ FAIL {len(_fails)}/{_n}")
    for m in _fails:
        print(f"   - {m}")
    sys.exit(1)
print(f"✅ PASS {_n}/{_n}")
sys.exit(0)
