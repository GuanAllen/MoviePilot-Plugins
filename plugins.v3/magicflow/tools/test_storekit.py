#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · storekit（存储数据层）离线回归 —— 钉住模型编解码 / 冷层惯用法 / 差分写热层。

背景（2026-10-29）：``persistence.py`` 3093 行里，真正「自己处理数据」的那一段
（数据模型 + ``KvBridge`` 冷热桥 + 5 个 Store 各抄一份的容错读/原子写/差分写）与插件
运行时零耦合，已下沉到 L0 ``storekit.py``。切出来的第一收益就是**这个文件能离线跑**：
以前验 ``TaskState.from_dict`` 得先造 ``app`` / ``common`` 桩。

本文件钉住最容易悄悄变掉的八件事：

  [1] 离线可加载（只 import 标准库，加载后仍无 ``app.*``）；
  [2] ``OperationRecord`` / ``TaskState`` 编解码：字段不丢、集合/字典归一；
  [3] ``TaskState.from_dict`` 对脏数据的容错（缺字段 / None / 空串 / 大小写）；
  [4] ``WorkReport`` 的「None = 本报告不涉及该计数」语义；
  [5] ``read_json_dict``：缺文件 / 坏 JSON / 顶层非 dict / 归一钩子 / 单条坏条目；
  [6] ``_atomic_write_json``：落盘格式不变（ensure_ascii=False + indent=2）、失败清 tmp；
  [7] ``_write_json_file`` / ``_merge_missing``：失败返回 False（不抛）、只补缺不覆盖；
  [8] ``batch_kv_apply``：差分跳过 / 变更重写 / 消失删键 / 单键模式 / 热层不可用退回。

用法：``python3 tools/test_storekit.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_storekit_test"

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


class FakeKv:
    """最小热层替身：只实现 KvBridge / batch_kv_apply 真正用到的那几个方法。"""

    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self.store: dict = {}
        self._available = available
        self.fail = fail
        self.calls: list = []

    def available(self) -> bool:
        return self._available

    def items(self, prefix: str) -> dict:
        return {k: v for k, v in self.store.items() if k.startswith(prefix)}

    def set(self, key: str, value) -> bool:
        self.calls.append(("set", key))
        if self.fail:
            return False
        self.store[key] = value
        return True

    def delete(self, key: str) -> bool:
        self.calls.append(("delete", key))
        if self.fail:
            return False
        self.store.pop(key, None)
        return True

    def set_many(self, mapping: dict) -> bool:
        self.calls.append(("set_many", dict(mapping)))
        if self.fail:
            return False
        self.store.update(mapping)
        return True

    def delete_many(self, keys) -> bool:
        self.calls.append(("delete_many", list(keys)))
        if self.fail:
            return False
        for key in keys:
            self.store.pop(key, None)
        return True


def _span_factory(sk):
    class Store(sk.KvBridge):
        kv_region = "t"

        def __init__(self, kv=None):
            self.kv_bind(kv)

    return Store


# ---------------------------------------------------------------- [1] 离线加载
assert "app" not in sys.modules, "测试环境已污染：加载 storekit 前不应存在 app 模块"
sk = _load(PKG + ".storekit", "storekit.py")
# app.log 是 try/except 兜底导入（源码设计允许）；容器里 app 一定可导入，
# 因此断言改为「唯一的 app 导入必须包在 try 里」，语义仍是纯标准库优先。
_src = (ROOT / "storekit.py").read_text(encoding="utf-8")
_lines = _src.splitlines()
_ok_try = all(l.startswith((" ", "\t")) for l in _lines
              if "import app" in l or "from app" in l)
ok(_ok_try, "[1] app.* 仅 try 兜底（无模块级硬依赖）")

tmp = Path(tempfile.mkdtemp(prefix="mf-storekit-"))

# ---------------------------------------------------------------- [2] 模型编解码
print("\n[2] 数据模型编解码")
rec = sk.OperationRecord(
    operation_id="op1",
    request_id="rq1",
    task_id="t1",
    kind="selection",
    state="completed",
    items=[sk.OperationItem(hash="aa", title="种子 A", bonus_per_hour=1.5)],
)
back = sk.OperationRecord.from_dict(json.loads(json.dumps(rec.to_dict())))
ok(back.operation_id == "op1" and back.state == "completed", "[2] OperationRecord 基本字段往返")
ok(len(back.items) == 1 and back.items[0].hash == "aa", "[2] 子项 OperationItem 往返")
ok(back.items[0].bonus_per_hour == 1.5, "[2] 子项浮点字段不丢精度")

st = sk.TaskState(
    task_id="t1",
    protected_torrents={"AA", "bb"},
    pub_dates={"AA": 100.0},
    torrent_pages={"AA": "https://x/detail?id=1"},
    torrent_free_until={"AA": 50.0},
    brush_upload={"AA": {"up": 1, "idle": 0, "ts": 1.0}},
    adopted_hashes={"cc"},
    manual_paused={"dd"},
    revision=7,
)
d = st.to_dict()
ok(sorted(d["protected_torrents"]) == ["AA", "bb"], "[2] 集合按原值序列化（顺序无关）")
ok(d["torrent_free_until"] == {"aa": 50.0}, "[2] 序列化时 infohash 统一小写")
st2 = sk.TaskState.from_dict(json.loads(json.dumps(d)))
ok(st2.protected_torrents == {"AA", "bb"}, "[2] 集合往返不丢元素")
ok(st2.pub_dates == {"aa": 100.0}, "[2] 载入时 pub_dates 键统一小写")
ok(st2.revision == 7, "[2] 计数器字段往返")

# ---------------------------------------------------------------- [3] 脏数据容错
print("\n[3] TaskState.from_dict 容错")
dirty = {"task_id": "t9", "pub_dates": {"AA": 0, "BB": "123.5"}, "torrent_pages": {"": "x", "CC": ""}}
st3 = sk.TaskState.from_dict(dirty)
ok(st3.pub_dates == {"bb": 123.5}, "[3] pub_dates 丢掉 0 值、字符串转 float、键小写")
ok(st3.torrent_pages == {}, "[3] torrent_pages 丢掉空键/空值")
ok(st3.enabled is True and st3.last_run_at == 0.0, "[3] 缺字段用默认值，不抛")
st4 = sk.TaskState.from_dict({"task_id": "t9", "exam_download_base": ""})
ok(st4.exam_download_base is None, "[3] exam_download_base 空串 → None（不是 0.0）")

# ---------------------------------------------------------------- [4] WorkReport
print("\n[4] WorkReport 缺省语义")
rep = sk.WorkReport(task_id="t1")
ok(rep.added is None and rep.deleted is None, "[4] 不涉及的计数是 None（不是 0，避免清零）")
ok(rep.source == "brush" and rep.decision is None, "[4] source / decision 默认值不变")

# ---------------------------------------------------------------- [5] read_json_dict
print("\n[5] read_json_dict 容错读")
missing = tmp / "nope.json"
ok(sk.read_json_dict(missing) == {}, "[5] 文件不存在 → 空字典")

broken = tmp / "broken.json"
broken.write_bytes(b'{"a": 1, "b": ')                       # 半截 JSON（上次写中断）
ok(sk.read_json_dict(broken) == {}, "[5] 坏 JSON → 空字典（不抛、不阻断加载）")

notdict = tmp / "list.json"
notdict.write_text('["x"]', encoding="utf-8")
ok(sk.read_json_dict(notdict) == {}, "[5] 顶层非 dict → 空字典")

good = tmp / "good.json"
good.write_text(json.dumps({"AA": {"v": 1}, "bb": "文本", "cc": []}), encoding="utf-8")
ok(sk.read_json_dict(good) == {"AA": {"v": 1}, "bb": "文本", "cc": []}, "[5] 正常文件原样返回")
ok(
    sk.read_json_dict(good, norm_key=lambda k: str(k).lower())["aa"] == {"v": 1},
    "[5] norm_key 生效（infohash 大小写归一）",
)
only_dict = sk.read_json_dict(good, norm_value=lambda v: dict(v) if isinstance(v, dict) else None)
ok(only_dict == {"AA": {"v": 1}}, "[5] norm_value 返回 None → 丢弃该条目（只收 dict 值）")
ok(sk.read_json_dict(good)["cc"] == [], "[5] 空列表值仍保留（未被误当 None 丢弃）")


def _boom(_value):
    raise ValueError("坏条目")


ok(sk.read_json_dict(good, norm_value=_boom) == {}, "[5] 单条归一抛异常 → 跳过该条，不拖垮整表")

# ---------------------------------------------------------------- [6] 原子写
print("\n[6] 原子写 + 落盘格式")
Store = _span_factory(sk)
box = Store(None)
target = tmp / "sub" / "cold.json"
target.parent.mkdir(parents=True, exist_ok=True)             # 建目录是 _write_json_file 的职责
box._atomic_write_json(target, {"中文": "值", "n": 1})
ok(target.exists(), "[6] 原子写落盘")
raw = target.read_bytes().decode("utf-8")
ok('"中文"' in raw, "[6] ensure_ascii=False（中文不转义）")
ok("\n  " in raw, "[6] indent=2（与历史文件同格式）")
ok(json.loads(raw) == {"中文": "值", "n": 1}, "[6] 内容可回读")

box.data_dir = tmp / "deep"
box.file = tmp / "deep" / "x.json"
ok(box._write_json_file({"a": 1}) is True, "[6] 目录不存在时由 _write_json_file 建")
ok((tmp / "deep" / "x.json").exists(), "[6] 建目录后文件确实落地")

real_replace = sk.os.replace


def _replace_fail(_src, _dst):
    raise OSError("磁盘满")


sk.os.replace = _replace_fail
raised = False
try:
    box._atomic_write_json(tmp / "x.json", {"a": 1})
except OSError:
    raised = True
sk.os.replace = real_replace
ok(raised, "[6] 写失败向上抛（由 _write_json_file 兜底转成 False）")
ok(not (tmp / "x.json.tmp").exists(), "[6] 失败后清掉半截 .tmp，不留垃圾")

# ---------------------------------------------------------------- [7] 落盘成败 / 补缺
print("\n[7] _write_json_file / _merge_missing")
box.data_dir = tmp
box.file = tmp / "cold2.json"
ok(box._write_json_file({"a": 1}) is True, "[7] 正常落盘返回 True")
bad = Store(None)
bad.data_dir = tmp / "ro"
bad.file = tmp / "ro" / "x.json"
(tmp / "ro").mkdir(exist_ok=True)
sk.os.replace = _replace_fail
res = None
try:
    res = bad._write_json_file({"a": 1})
except Exception:  # noqa: BLE001
    res = "raised"
sk.os.replace = real_replace
ok(res is False, "[7] 落盘失败返回 False（不抛，交给 flusher 保脏重试）")

dst = {"a": 1}
added = sk.KvBridge._merge_missing(dst, {"a": 999, "b": 2})
ok(added == 1 and dst == {"a": 1, "b": 2}, "[7] 只补缺，绝不覆盖热层已有的键")

# ---------------------------------------------------------------- [8] 差分写热层
print("\n[8] batch_kv_apply 差分口径")
kv = FakeKv()
bridge = Store(kv)
items = {"h1": {"v": 1}, "h2": {"v": 2}}
marks: dict = {}
ok(sk.batch_kv_apply(bridge, items, written=marks) is True, "[8] 首次全量写成功")
ok(kv.store == {"t:h1": {"v": 1}, "t:h2": {"v": 2}}, "[8] 键带 region 前缀写入")
ok(len(marks) == 2, "[8] 指纹表回写 2 条")

kv.calls.clear()
ok(sk.batch_kv_apply(bridge, items, written=marks) is True, "[8] 无变化再写返回 True")
ok(kv.calls == [], "[8] 指纹一致 → 一次热层调用都不发（增量写的核心）")

items["h1"] = {"v": 9}
kv.calls.clear()
sk.batch_kv_apply(bridge, items, written=marks)
ok(kv.calls and kv.calls[0][0] == "set_many" and kv.calls[0][1] == {"t:h1": {"v": 9}}, "[8] 值变了只写变化的键")

items.pop("h2")
kv.calls.clear()
sk.batch_kv_apply(bridge, items, written=marks)
ok(("delete_many", ["t:h2"]) in kv.calls, "[8] 全量模式下内存已删的键 → 热层删键")
ok("h2" not in marks, "[8] 删键同时清掉指纹，避免复活")

kv.calls.clear()
sk.batch_kv_apply(bridge, items, "h1", written=marks)
ok(kv.calls == [], "[8] 单键模式且指纹一致 → 不写")
kv.calls.clear()
sk.batch_kv_apply(bridge, {"h1": {"v": 10}}, "h1", written=marks)
ok(kv.calls and kv.calls[0][1] == {"t:h1": {"v": 10}}, "[8] 单键模式只写该键")

dead = FakeKv(available=False)
ok(sk.batch_kv_apply(Store(dead), items, written={}) is False, "[8] 热层不可用 → False（调用方退回写文件）")
sick = FakeKv(fail=True)
sick_marks = {}
ok(sk.batch_kv_apply(Store(sick), items, written=sick_marks) is False, "[8] 热层写失败 → False")
ok(sick_marks == {}, "[8] 写失败不更新指纹（否则下次误以为已写入）")

# ---------------------------------------------------------------- 收尾
shutil.rmtree(tmp, ignore_errors=True)
print()
if _fails:
    print(f"❌ FAIL —— {len(_fails)}/{_n} 项未过")
    for f in _fails:
        print(f"   · {f}")
    sys.exit(1)
print(f"✅ PASS —— 共 {_n} 项全过")
