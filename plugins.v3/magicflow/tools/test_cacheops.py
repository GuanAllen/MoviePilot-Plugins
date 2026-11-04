#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · cacheops（进程内缓存惯用法）离线回归 —— 钉住信封 / 有界容器 / 冷却的契约。

背景（2026-10-29，见 ``docs/ADR-0001-cacheops.md``）：仓库里 30 个 mixin 手写缓存 +
5 个模块级缓存，语义只有三种，惯用法却有五种，过期判定被手写 23 处。``cacheops`` 只做
「收敛惯用法」这一件事 —— **不**把值搬到冷层（``_tag_snapshot_cache`` 装的是
``Dict[str, List[TorrentInfo]]``，搬进 TierCache 会被 ``default=str`` 静默降级）。

本文件钉住最容易悄悄变掉的十二件事：

  [1] 离线可加载（纯标准库，顶层无 ``app.*``）；
  [2] 信封：过期判定 + 「入参变了就该重算」的校验键；
  [3] TTLCache 命中 / 过期 / 未命中都不回源不抛异常；
  [4] TTLCache 有界：超 ``max_entries`` 丢最旧（防长跑无界增长）；
  [5] stale 宽限：陈旧但落在 ``stale_max`` 内仍返回值（stale-while-revalidate）；
  [6] Cooldown：冷却中 / 过期自动清 / 按条 ttl / 解除；
  [7] SingleFlight：新鲜直返 / 过期同键单飞只回源一次 / 不同键不串行 / 回源失败不固化；
  [8] KeyLocks：同键同锁 / 不裁正在用的锁 / 不裁刚建出来的锁 / drop；
  [9] Solo：阻塞 with 严格串行 / try_enter 非阻塞 / 重复 leave 不抛；
  [10] Inflight：同 key 重复占位失败 / 满员只拒绝不淘汰在飞的 / leave 可盲调；
  [11] SingleFlight.peek：新鲜 / stale 宽限 / 超宽限三态的返回值与 fresh 标志；
  [12] 缓存容器自动登记（锁表 / Solo / Inflight 不登记，它们不是缓存位）。

用法：``python3 tools/test_cacheops.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_cacheops_test"

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
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- [1] 离线加载
assert "app" not in sys.modules, "测试环境已污染：加载 cacheops 前不应存在 app 模块"
cacheops = _load(PKG + ".cacheops", "cacheops.py")
ok("app" not in sys.modules, "[1] 纯标准库，加载后仍未引入 app.*")

# ---------------------------------------------------------------- [2] 信封
print("\n[2] entry / fresh / value")
env = cacheops.entry({"a": 1})
ok(cacheops.fresh(env, 60.0) is True, "[2] 刚写入 → 新鲜")
ok(cacheops.value(env, 60.0) == {"a": 1}, "[2] 新鲜时取到值")

old = cacheops.entry({"a": 1}, ts=time.time() - 100.0)
ok(cacheops.fresh(old, 60.0) is False, "[2] 超过 TTL → 不新鲜")
ok(cacheops.value(old, 60.0, default="兜底") == "兜底", "[2] 过期回 default（不回源）")

keyed = cacheops.entry({"a": 1}, key="hash1|hash2")
ok(cacheops.fresh(keyed, 60.0, key="hash1|hash2") is True, "[2] 校验键一致 → 新鲜")
ok(cacheops.fresh(keyed, 60.0, key="hash9") is False, "[2] 校验键变了 → 视同过期（入参变了要重算）")
ok(cacheops.fresh(None, 60.0) is False, "[2] 非信封（None）→ 不新鲜，不抛异常")

# ---------------------------------------------------------------- [3] TTLCache 读
print("\n[3] TTLCache 命中 / 过期 / 未命中")
box = cacheops.TTLCache("test-hit", ttl=0.5, max_entries=4)
box.set("k", "v")
ok(box.get("k") == "v", "[3] 命中返回值")
time.sleep(0.6)
ok(box.get("k") is None, "[3] 过期返回 None（不回源、不抛）")
ok(box.get("nope") is None, "[3] 未命中返回 None")
ok(box.get("k", ttl=60.0) == "v", "[3] 单次调用可覆盖 ttl（陈旧值仍可取回）")

# ---------------------------------------------------------------- [4] 有界
print("\n[4] TTLCache 容量上限（LRU 丢最旧）")
box2 = cacheops.TTLCache("test-max", ttl=60.0, max_entries=3)
for i in range(5):
    box2.set(f"k{i}", i)
st = box2.stats()
ok(st["n"] == 3, f"[4] 写 5 条只留 3 条 → {st}")
ok(box2.get("k0") is None and box2.get("k1") is None, "[4] 最旧的两条被淘汰")
ok(box2.get("k4") == 4, "[4] 最新的还在")
box2.set("k4", 4)
box2.set("k4b", 44)
ok(box2.get("k2") is None and box2.get("k4") == 4, "[4] 命中的键被 move_to_end（LRU 不误删热键）")
box2.invalidate("k4")
ok(box2.get("k4") is None, "[4] invalidate 单键")
box2.invalidate()
ok(box2.stats()["n"] == 0, "[4] invalidate 不传键 = 全清")

# ---------------------------------------------------------------- [5] stale 宽限
print("\n[5] stale-while-revalidate 宽限")
box3 = cacheops.TTLCache("test-stale", ttl=0.3, max_entries=8, stale_max=5.0)
box3.set("k", "旧值")
time.sleep(0.4)
val, is_fresh = box3.peek("k")
ok(val == "旧值" and is_fresh is False, f"[5] 过期但在宽限内 → 返回 (旧值, False) → {(val, is_fresh)}")
box3b = cacheops.TTLCache("test-nostale", ttl=0.3, max_entries=8)
box3b.set("k", "旧值")
time.sleep(0.4)
val2, is_fresh2 = box3b.peek("k")
ok(val2 is None and is_fresh2 is False, f"[5] 未配 stale_max 时过期即未命中（不给旧值）→ {(val2, is_fresh2)}")
box3.set("k2", "v2")
time.sleep(0.4)
ok(box3.get("k2") is None, "[5] get() 不吃 stale（只有 peek 才给旧值）")

# ---------------------------------------------------------------- [6] Cooldown
print("\n[6] Cooldown 冷却")
cd = cacheops.Cooldown("test-cd", ttl=0.5, max_entries=4)
ok(cd.hot("site1") is False, "[6] 未标记 → 不冷却")
cd.mark("site1")
ok(cd.hot("site1") is True, "[6] 标记后 → 冷却中")
time.sleep(0.6)
ok(cd.hot("site1") is False, "[6] 过冷却 → 自动解除并清掉条目")
cd.mark("site2", ttl=0.2)
ok(cd.hot("site2") is True, "[6] 按条 ttl 生效")
time.sleep(0.3)
ok(cd.hot("site2") is False, "[6] 按条 ttl 到期")
cd.mark("site3")
cd.clear("site3")
ok(cd.hot("site3") is False, "[6] clear 单键解除")
cd.mark("a")
cd.mark("b")
cd.clear()
ok(cd.stats()["n"] == 0, "[6] clear 不传键 = 全部解除")

# ---------------------------------------------------------------- [7] SingleFlight
print("\n[7] SingleFlight 单飞")
fl = cacheops.SingleFlight("test-flight", ttl=5.0)
_calls = {"n": 0}
_clk = threading.Lock()


def _compute():
    """慢回源：睡 0.25s 再计数，用来观察「到底算了几次」。"""
    time.sleep(0.25)
    with _clk:
        _calls["n"] += 1
    return "v"


_N = 8
_bar = threading.Barrier(_N)
_errs: list = []


def _worker():
    """8 个线程同时进门：只有第一个该真回源，其余等它的结果。"""
    try:
        _bar.wait()
        fl.run("all", _compute)
    except Exception as _e:  # noqa: BLE001
        _errs.append(_e)


_ths = [threading.Thread(target=_worker) for _ in range(_N)]
for _t in _ths:
    _t.start()
for _t in _ths:
    _t.join()
ok(not _errs, f"[7] 并发无异常 → {_errs}")
ok(_calls["n"] == 1, f"[7] {_N} 线程同键单飞：回源只 1 次（实际 {_calls['n']}）")

fl2 = cacheops.SingleFlight("test-flight2", ttl=5.0)


def _slow(val):
    """每键各睡 0.3s：若被串行化，两个键加起来必然 > 0.55s。"""
    def _c():
        time.sleep(0.3)
        return val
    return _c


_t0 = time.time()
_ths = [threading.Thread(target=fl2.run, args=(v, _slow(v))) for v in ("a", "b")]
for _t in _ths:
    _t.start()
for _t in _ths:
    _t.join()
_el = time.time() - _t0
ok(_el < 0.55, f"[7] 不同键并发回源不串行（耗时 {_el:.2f}s < 0.55）")

fl3 = cacheops.SingleFlight("test-flight3", ttl=5.0)
_seq = {"n": 0}


def _boom():
    """第一次必炸、第二次成功：验证失败不会被固化进缓存。"""
    _seq["n"] += 1
    if _seq["n"] == 1:
        raise RuntimeError("boom")
    return "ok"


try:
    fl3.run("k", _boom)
    ok(False, "[7] 首次回源应当抛异常")
except RuntimeError:
    ok(True, "[7] 回源异常照常向外抛")
ok(fl3.stats()["n"] == 0, "[7] 回源失败不写缓存（不会把失败固化）")
ok(fl3.run("k", _boom) == "ok", "[7] 失败后仍可重试并写入")

fl4 = cacheops.SingleFlight("test-flight4", ttl=60.0, max_entries=2)
for _k in ("k1", "k2", "k3"):
    fl4.run(_k, lambda _k=_k: _k)
_st = fl4.stats()
ok(_st["n"] == 2, f"[7] 超 max_entries 丢最旧（n={_st['n']}）")
ok(_st["locks"] <= 2, f"[7] 淘汰的键顺手回收锁（locks={_st['locks']}）")

fl5 = cacheops.SingleFlight("test-flight5", ttl=60.0)
fl5.run("a", lambda: 1)
fl5.invalidate("a")
ok(fl5.get("a") is None, "[7] invalidate 单键失效")
fl5.run("b", lambda: 2)
fl5.invalidate()
ok(fl5.stats()["n"] == 0, "[7] invalidate 不传键 = 整容器清空")

fl6 = cacheops.SingleFlight("test-flight6", ttl=0.3)
ok(fl6.get("x") is None, "[7] get() 未命中返回 None（不回源）")
fl6.run("x", lambda: 9)
ok(fl6.get("x") == 9, "[7] get() 命中取值")
time.sleep(0.4)
ok(fl6.get("x") is None, "[7] get() 过期也不回源（只有 run 才回源）")

# ---------------------------------------------------------------- [8] KeyLocks
print("\n[8] KeyLocks 按 key 发锁（有界）")
kl = cacheops.KeyLocks("test-locks", max_entries=2)
ok(kl.get("a") is kl.get("a"), "[8] 同键返回同一把锁（单飞前提）")
ok(kl.get("a") is not kl.get("b"), "[8] 不同键不同锁（不互相串行）")

kl2 = cacheops.KeyLocks("test-locks2", max_entries=1)
_busy = kl2.get("busy")
_busy.acquire()
_other = kl2.get("other")
ok(kl2.stats()["n"] == 2,
   f"[8] 被持有的锁不被裁掉 → 暂时超上限 n={kl2.stats()['n']}（>max=1）")
ok(_other is kl2.get("other"),
   "[8] 刚建出来那把不被自己裁掉（否则本次返回的锁不在表里，同键会造第二把）")
_busy.release()
kl2.get("third")
ok(kl2.stats()["n"] <= 1, f"[8] 有锁释放后下次 get 再裁到上限内 → n={kl2.stats()['n']}")

kl3 = cacheops.KeyLocks("test-locks3", max_entries=8)
_dropped = kl3.get("x")
kl3.drop("x")
ok(kl3.get("x") is not _dropped, "[8] drop 丢掉空闲锁（下次取到新的一把）")
_held = kl3.get("y")
_held.acquire()
kl3.drop("y")
ok(kl3.get("y") is _held, "[8] 正被持有的锁 drop 不生效（删了会破单飞）")
_held.release()
ok(kl3.stats()["kind"] == "locks", "[8] stats 标明是锁表而非缓存")

# ---------------------------------------------------------------- [9] Solo
print("\n[9] Solo 全局单锁")
solo = cacheops.Solo("test-solo")
ok(solo.busy is False, "[9] 初始空闲")
ok(solo.try_enter() is True, "[9] 非阻塞抢到 → True")
ok(solo.busy is True, "[9] 持有时 busy 为真")
ok(solo.try_enter() is False, "[9] 已被占 → try_enter 立刻 False（不阻塞）")
solo.leave()
ok(solo.busy is False, "[9] leave 后释放")
solo.leave()
ok(True, "[9] 重复 leave 不抛（finally 里可以无脑调）")

with solo:
    ok(solo.busy is True, "[9] with 期间持有")
ok(solo.busy is False, "[9] with 退出自动释放")

# 阻塞语义：两个线程串行，最大值不会超过 1
_conc = {"now": 0, "max": 0}
_conc_lock = threading.Lock()


def _solo_worker() -> None:
    with solo:
        with _conc_lock:
            _conc["now"] += 1
            _conc["max"] = max(_conc["max"], _conc["now"])
        time.sleep(0.05)
        with _conc_lock:
            _conc["now"] -= 1


_st = [threading.Thread(target=_solo_worker) for _ in range(5)]
for t in _st:
    t.start()
for t in _st:
    t.join()
ok(_conc["max"] == 1, f"[9] 5 线程 with solo 严格串行（同时最多 {_conc['max']} 个）")

# ---------------------------------------------------------------- [10] Inflight
print("\n[10] Inflight 在飞名额")
fly = cacheops.Inflight("test-inflight", max_entries=2)
ok(fly.try_enter("a") is True, "[10] 首次占位成功")
ok(fly.try_enter("a") is False, "[10] 同 key 重复占位失败（这就是要防的重复起线程）")
ok(fly.try_enter("b") is True, "[10] 不同 key 互不影响")
ok(fly.has("a") is True and fly.has("b") is True, "[10] has 反映在飞状态")
ok(fly.try_enter("c") is False, "[10] 名额满 → 拒绝新进入（不淘汰在飞的）")
ok(fly.has("a") is True, "[10] 满员时在飞的 key 仍在（没被挤掉）")
fly.leave("a")
ok(fly.try_enter("c") is True, "[10] 让出一个再进就成功（此时 b+c 仍满）")
ok(fly.try_enter("a") is False, "[10] 名额仍满时再进被拒（不是只看这个 key 在不在）")
fly.leave("b")
ok(fly.try_enter("a") is True, "[10] 已让出过的 key 在有名额时可重新占位")
fly.leave("不存在的")
ok(True, "[10] leave 未占过的 key 不抛（后台线程 finally 里可盲调）")
fly.leave("a")
fly.leave("b")
fly.leave("c")
ok(fly.stats()["n"] == 0, "[10] 全部让出后归零")
ok(fly.stats()["kind"] == "inflight", "[10] stats 标明是在飞名额而非锁")

# ---------------------------------------------------------------- [11] peek
print("\n[11] SingleFlight.peek（SWR 用）")
pk = cacheops.SingleFlight("test-peek", ttl=0.3, max_entries=4, stale_max=10.0)
pk.run("k", lambda: {"v": 1})
ok(pk.peek("k") == ({"v": 1}, True), "[11] 新鲜 → (值, True)")
ok(pk.peek("none") == (None, False), "[11] 未命中 → (None, False)")
time.sleep(0.4)
val, is_fresh = pk.peek("k")
ok(val == {"v": 1} and is_fresh is False, "[11] 过期但在 stale 宽限内 → 给旧值 + False")
ok(pk.get("k") is None, "[11] 同一时刻 get() 视为未命中（两者语义不同，别混用）")
time.sleep(0.2)
pk2 = cacheops.SingleFlight("test-peek2", ttl=0.1, max_entries=4, stale_max=0.2)
pk2.run("k", lambda: "旧")
time.sleep(0.35)
ok(pk2.peek("k") == (None, False), "[11] 超过 stale_max → (None, False)，调用方该阻塞重算")

# ---------------------------------------------------------------- 收尾：注册表
print("\n[12] 登记与诊断")
snap = cacheops.snapshot()
names = [x["name"] for x in snap]
ok("test-hit" in names and "test-cd" in names and "test-flight" in names,
   f"[12] 缓存容器自动登记 → {names}")
ok(all(("n" in x and "max" in x) for x in snap), "[12] 每条都有规模与上限（供 cache_status 枚举）")
ok("test-locks" not in names and "test-solo" not in names and "test-inflight" not in names,
   "[12] 锁表 / Solo / Inflight **不登记**（它们不是缓存位，混进清单只会干扰诊断）")

print()
if _fails:
    print(f"❌ FAIL {len(_fails)}/{_n}")
    for m in _fails:
        print(f"   - {m}")
    sys.exit(1)
print(f"✅ PASS {_n}/{_n}")
sys.exit(0)
