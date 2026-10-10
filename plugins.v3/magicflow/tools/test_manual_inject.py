#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 15.8.14「临时/手工投放通道」离线单测。

验什么（纯标准库 + 假下载器 / 假账本，不连真库真 qB）：
  1. 入参归一 ``_inject_content``：magnet（40hex / base32 两种 btih）、torrent(base64)、
     url、参数缺失/畸形各自的 ``error`` 与 ``dup_ready``；
  2. 身份口径 ``_inject_prepare``：缺省 ``site=手工`` / ``sub=资源`` → 标签
     ``魔流-手工-静默-资源``；``sub=普通`` / 自定义 ``site`` 也各就各位；保存目录兜底；
  3. 干跑 ``_inject_plan``：**不落种、不写账本、不占闸门**，只报 dup 冲突；
  4. 真投放 ``_inject_apply``：占闸门 → 加种（带身份标签 / 目录 / 分类）→ 写账本
     （site/state=静默/sub）→ finish；失败路径 release 且不动账本；冲突路径不落种；
  5. 退场 ``_inject_release``：干跑不动手；``pause`` 只暂停；非本通道拒收（``force`` 例外）；
     ``mode=delete`` 走唯一删种闸门、库内资产需 ``force=1``（先降级为普通再删）并销账。

为什么能离线跑：``manualinject.py`` 只依赖 ``tags.py`` / ``fingerprint.py``（纯标准库）
与 ``downloader_ops``（重）—— 本测试用一个**同名桩模块**顶掉后者，其余按真源码加载。

用法：``python3 tools/test_manual_inject.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import base64
import importlib
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_OK = 0
_FAIL = 0


def _ok(cond: bool, msg: str) -> None:
    global _OK, _FAIL
    if cond:
        _OK += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


# --------------------------------------------------------------------- 加载被测模块
PKG = "mf_inject_test"


def _load_modules():
    """按真源码加载 manualinject（downloader_ops 用桩顶掉，避免拖入 apscheduler/app）。"""
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

    stub = types.ModuleType(PKG + ".downloader_ops")

    def _magnet_infohash(magnet):
        """与 downloader_ops 同实现（40hex / base32）。"""
        try:
            m = re.search(r"xt=urn:btih:([A-Za-z0-9]+)", str(magnet or ""))
            if not m:
                return None
            raw = m.group(1)
            if len(raw) == 40:
                return raw.lower()
            if len(raw) == 32:
                return base64.b32decode(raw.upper()).hex()
        except Exception:  # noqa: BLE001
            return None
        return None

    stub._magnet_infohash = _magnet_infohash
    sys.modules[PKG + ".downloader_ops"] = stub

    mi = importlib.import_module(PKG + ".manualinject")
    fp = importlib.import_module(PKG + ".fingerprint")
    return mi, fp


MI, FP = _load_modules()
ManualInjectMixin = MI.ManualInjectMixin


# --------------------------------------------------------------------- 桩件
def _torrent_bytes(name: bytes = b"t.bin", length: int = 1024) -> bytes:
    """造一个最小合法 .torrent（bencode），用来验 infohash / 特征码。"""
    def bstr(s: bytes) -> bytes:
        return str(len(s)).encode() + b":" + s

    info = (b"d6:lengthi" + str(length).encode() + b"e4:name" + bstr(name)
            + b"12:piece lengthi16384e6:pieces20:" + b"\x00" * 20 + b"e")
    return b"d8:announce" + bstr(b"http://tracker.example/announce") + b"4:info" + info + b"e"


H_OK = "a" * 40


class FakeStore:
    """假种子账本（只实现本通道用到的 get/put/drop）。"""

    def __init__(self):
        self.rows = {}
        self.puts = []
        self.drops = []

    def get(self, h):
        return dict(self.rows.get(str(h).lower()) or {})

    def put(self, h, patch, **kw):
        h = str(h).lower()
        self.puts.append((h, dict(patch)))
        self.rows.setdefault(h, {})
        self.rows[h].update({k: v for k, v in patch.items() if v is not None})
        return dict(self.rows[h])

    def drop(self, h):
        self.drops.append(str(h).lower())
        return bool(self.rows.pop(str(h).lower(), None))


class FakeDL:
    """假下载器：只实现本通道用到的 add/pause/delete/索引。"""

    def __init__(self):
        self.is_available = True
        self.added = []
        self.paused = []
        self.deleted = []
        self.live = {}
        self.add_ok = True
        self.add_hash = H_OK

    def add_torrent(self, content=None, download_dir="", tag=None, category="", **kw):
        self.added.append({"content": content, "download_dir": download_dir,
                           "tag": tag, "category": category})
        if not self.add_ok:
            return None, "fake-fail"
        self.live[str(self.add_hash).lower()] = True
        return self.add_hash, None

    def pause_torrents(self, hashes):
        self.paused.append([str(h).lower() for h in hashes])
        return len(hashes), None

    def delete_torrents(self, hashes, delete_file=False, reason="", source=""):
        self.deleted.append({"hashes": [str(h).lower() for h in hashes],
                             "delete_file": delete_file, "reason": reason, "source": source})
        for h in list(hashes):
            self.live.pop(str(h).lower(), None)
        return len(hashes), None

    def get_all_torrents_index(self):
        return {h: object() for h in self.live}


class FakePlugin(ManualInjectMixin):
    """把宿主（qB / 账本 / dup 闸门 / 删除闸门）全部换成本文件里的桩。"""

    def __init__(self):
        self.store = FakeStore()
        self.dl = FakeDL()
        self.conflicts = set()
        self.claims = []
        self.finishes = []
        self.releases = []
        self.gate_blocks = set()

    # --- dup 闸门（根模块 dupgate.DupGateMixin 的等价桩）---
    def _dup_keys(self, info_hash=None, fingerprint=None):
        keys = []
        if info_hash:
            keys.append("ih:" + str(info_hash).lower())
        if fingerprint:
            keys.append("fp:" + str(fingerprint).lower())
        return keys

    def _dup_conflict_states(self, task_id, *, keys):
        return {k: "done" for k in keys if k in self.conflicts}

    def _dup_claim(self, task_id, *, keys):
        self.claims.append(list(keys))
        return [k for k in keys if k in self.conflicts]

    def _dup_finish(self, task_id, *, keys):
        self.finishes.append(list(keys))

    def _dup_release(self, task_id, *, keys):
        self.releases.append(list(keys))

    # --- 宿主 ---
    def _get_downloader(self, downloader_name="qbittorrent"):
        return self.dl

    def _tag_state(self):
        return self.store

    def _delete_gate_detail(self, hashes, snap=None):
        return {h: "库内资产（已入库，永不删）" for h in hashes if h in self.gate_blocks}

    def _ondemand_default_save_path(self):
        return "/tmp/dl"


MAGNET_HEX = "magnet:?xt=urn:btih:" + "b" * 40 + "&dn=x"
_B32 = base64.b32encode(bytes.fromhex("c" * 40)).decode()
MAGNET_B32 = "magnet:?xt=urn:btih:" + _B32
TORRENT_RAW = _torrent_bytes()
TORRENT_B64 = base64.b64encode(TORRENT_RAW).decode()
TORRENT_IH = FP.info_hash(TORRENT_RAW)


# --------------------------------------------------------------------- 1. 入参归一
def t_content():
    print("\n[1] _inject_content —— 入参归一")
    p = FakePlugin()
    c = p._inject_content(magnet=MAGNET_HEX)
    _ok(c["content"] == MAGNET_HEX and c["kind"] == "magnet", "magnet 原样透传")
    _ok(c["info_hash"] == "b" * 40 and c["dup_ready"] is True, "magnet: 40hex btih 解析出 infohash（可按 infohash 预检）")
    _ok(p._inject_content(magnet=MAGNET_B32)["info_hash"] == "c" * 40, "magnet: base32 btih 解码成 40hex")
    _ok(bool(p._inject_content(magnet="http://x")["error"]), "非 magnet:? 开头 → error")
    c = p._inject_content(torrent=TORRENT_B64)
    _ok(isinstance(c["content"], bytes) and c["kind"] == "torrent", "base64 torrent 解码成 bytes")
    _ok(c["info_hash"] == TORRENT_IH and bool(c["fingerprint"]) and c["dup_ready"] is True,
        "torrent: infohash + 特征码都算出来 → dup_ready")
    _ok("data:" in p._inject_content(torrent="data:application/x-bittorrent;base64," + TORRENT_B64)["kind"].__str__()
        or isinstance(p._inject_content(torrent="data:application/x-bittorrent;base64," + TORRENT_B64)["content"], bytes),
        "带 data: 前缀的 base64 也认")
    _ok(bool(p._inject_content(torrent="!!!not-base64!!!")["error"]) is False
        or p._inject_content(torrent="!!!")["content"] is None, "畸形 base64 → 不产生 content")
    c = p._inject_content(url="https://x.example/a.torrent")
    _ok(c["kind"] == "url" and c["dup_ready"] is False, "url: 无法预检重复（dup_ready=False）")
    _ok(bool(p._inject_content(url="ftp://x")["error"]), "非 http(s) 的 url → error")
    _ok("三者之一" in str(p._inject_content()["error"]), "三参数全空 → 明确报错")


# --------------------------------------------------------------------- 2. 身份口径
def t_prepare():
    print("\n[2] _inject_prepare —— 身份 / 目录口径")
    p = FakePlugin()
    d = p._inject_prepare(magnet=MAGNET_HEX)
    _ok(d["ok"] and d["site"] == MI.MANUAL_SITE == "手工", "缺省 site = 手工")
    _ok(d["sub"] == "资源" and d["tag"] == "魔流-手工-静默-资源", "缺省 sub = 资源 → 标签 魔流-手工-静默-资源")
    _ok(d["save_path"] == "/tmp/dl", "save_path 缺省走宿主默认目录兜底")
    _ok(d["dup_keys"] == ["ih:" + "b" * 40], "dup_keys 用 infohash")
    _ok(p._inject_prepare(magnet=MAGNET_HEX, sub="普通")["tag"] == "魔流-手工-静默-普通", "sub=普通 → 标签子类跟着变")
    _ok(p._inject_prepare(magnet=MAGNET_HEX, sub="乱写")["sub"] == "资源", "非法 sub 一律回落 资源")
    _ok(p._inject_prepare(magnet=MAGNET_HEX, site="CARPT")["tag"] == "魔流-CARPT-静默-资源", "自定义 site 进标签")
    _ok(p._inject_prepare(magnet=MAGNET_HEX, site="  ")["site"] == "手工", "空白 site 回落 手工")
    d2 = p._inject_prepare(magnet=MAGNET_HEX, save_path="/data/x")
    _ok(d2["save_path"] == "/data/x", "显式 save_path 优先")

    class NoDir(FakePlugin):
        def _ondemand_default_save_path(self):
            return ""

    nd = NoDir()._inject_prepare(magnet=MAGNET_HEX)
    _ok(nd["ok"] is False and "保存目录" in str(nd["error"]), "没有保存目录 → ok=False 且报错可读")


# --------------------------------------------------------------------- 3. 干跑
def t_plan():
    print("\n[3] _inject_plan —— 干跑无副作用")
    p = FakePlugin()
    out = p._inject_plan(magnet=MAGNET_HEX)
    _ok(out["ok"] and out["would_add"] is True and out["conflict"] == [], "无冲突 → would_add")
    _ok(not p.dl.added and not p.store.puts and not p.claims, "干跑不落种 / 不写账本 / 不占闸门")
    k = "ih:" + "b" * 40
    p.conflicts.add(k)
    out = p._inject_plan(magnet=MAGNET_HEX)
    _ok(out["conflict"] == [k] and out["would_add"] is False, "别人占用 → 干跑就报 conflict")
    _ok(out["conflict_states"].get(k) == "done", "conflict_states 带状态（done/inflight）")
    out = p._inject_plan(url="https://x.example/a.torrent")
    _ok(out["ok"] and "无法预检" in str(out["note"]), "url 投放 → 明确提示无法预检重复")
    p2 = FakePlugin()
    out = p2._inject_plan(magnet=MAGNET_HEX)
    _ok(out["dup_ready"] is True and out["note"] == "" and out["dup_keys"], "magnet 有 infohash → dup 预检可用（无需提示）")
    out = p2._inject_plan(magnet="magnet:?dn=no-btih")
    _ok(out["dup_keys"] == [] and "无法预检" in str(out["note"]), "magnet 无 btih → 退回「无法预检」提示")


# --------------------------------------------------------------------- 4. 真投放
def t_apply():
    print("\n[4] _inject_apply —— 占闸门 → 落种 → 写账本")
    p = FakePlugin()
    out = p._inject_apply(magnet=MAGNET_HEX)
    _ok(out["ok"] and out["hash"] == H_OK and out["added"] is True, "投放成功并回 infohash")
    _ok(p.claims == [["ih:" + "b" * 40]] and p.finishes == [["ih:" + "b" * 40]], "先 claim、成功后 finish")
    add = p.dl.added[0]
    _ok(add["tag"] == "魔流-手工-静默-资源" and add["download_dir"] == "/tmp/dl", "落种带身份标签 + 目录")
    _ok(add["category"] == "", "category 缺省为空（不硬塞分类）")
    row = p.store.get(H_OK)
    _ok(row.get("site") == "手工" and row.get("state") == "静默" and row.get("sub") == "资源",
        "账本行 = site=手工 / state=静默 / sub=资源（审计与报表都看得见）")
    _ok(p.store.puts and set(p.store.puts[0][1]) == {"site", "state", "sub"}, "只写这三个真列（不写幽灵列）")

    p2 = FakePlugin()
    out = p2._inject_apply(magnet=MAGNET_HEX, sub="普通", site="聆音", category="音乐")
    _ok(out["ok"] and p2.dl.added[0]["tag"] == "魔流-聆音-静默-普通", "site/sub/category 全量透传到 add_torrent")
    _ok(p2.store.get(H_OK).get("site") == "聆音", "账本记自定义 site")

    p3 = FakePlugin()
    p3.conflicts.add("ih:" + "b" * 40)
    out = p3._inject_apply(magnet=MAGNET_HEX)
    _ok(out["ok"] is False and "重复资源" in str(out["error"]), "闸门冲突 → 拒投")
    _ok(not p3.dl.added and not p3.store.puts, "冲突时不落种、不写账本")

    p4 = FakePlugin()
    p4.dl.add_ok = False
    out = p4._inject_apply(magnet=MAGNET_HEX)
    _ok(out["ok"] is False and "添加失败" in str(out["error"]), "加种失败 → ok=False")
    _ok(p4.releases == [["ih:" + "b" * 40]] and not p4.store.puts, "加种失败 → release 占用、账本不动")

    p5 = FakePlugin()
    out = p5._inject_apply(url="https://x.example/a.torrent")
    _ok(out["ok"] and p5.dl.added[0]["content"].startswith("https://"), "url 直接透传给下载器")
    _ok(p5.claims == [] and p5.finishes == [], "无法预检的入参 → 不产生假占用")


# --------------------------------------------------------------------- 5. 退场
def t_release():
    print("\n[5] _inject_release —— 退场（暂停 / 删除 / 拒收）")
    p = FakePlugin()
    p.store.put(H_OK, {"site": "手工", "state": "静默", "sub": "资源"})
    out = p._inject_release(hashes=H_OK, mode="pause")
    _ok(out["ok"] and out["apply"] is False and out["would"]["pause"] == [H_OK], "干跑：只报计划")
    _ok(not p.dl.paused, "干跑不暂停")
    out = p._inject_release(hashes=H_OK, mode="pause", apply="1")
    _ok(out["paused"] == 1 and p.dl.paused == [[H_OK]], "apply=1 → 真暂停")
    _ok(p.store.get(H_OK).get("sub") == "资源", "暂停不退账本（可再 resume）")

    other = "d" * 40
    p.store.put(other, {"site": "聆音", "state": "静默", "sub": "资源"})
    out = p._inject_release(hashes=f"{H_OK},{other}", mode="pause", apply="1")
    _ok(out["owned"] == 1 and len(out["refused"]) == 1 and out["refused"][0]["hash"] == other,
        "非本通道（site=聆音）的种拒收")
    out = p._inject_release(hashes=f"{H_OK},{other}", mode="pause", apply="0")
    _ok(out["owned"] == 1, "拒收判定同样在干跑生效")
    out = p._inject_release(hashes=other, mode="pause", site="聆音", apply="1")
    _ok(out["owned"] == 1 and not out["refused"], "site= 可指定别的来源桶")
    p4 = FakePlugin()
    p4.store.put(other, {"site": "聆音", "state": "静默", "sub": "资源"})
    p4.dl.live[other] = True
    out = p4._inject_release(hashes=other, mode="delete", force="1", apply="1")
    _ok(len(out["refused"]) == 1 and not p4.dl.deleted, "★ force 也不放宽归属：别人的种（site=聆音）一律拒收")
    _ok(p4.store.get(other).get("sub") == "资源", "★ 拒收时连身份都不动")

    # 删除：资源身份 = 库内资产 → 未 force 被唯一删种闸门硬拦；force=1 先降级为普通再删 → 销账
    p2 = FakePlugin()
    p2.store.put(H_OK, {"site": "手工", "state": "静默", "sub": "资源"})
    p2.dl.live[H_OK] = True
    p2.gate_blocks.add(H_OK)
    real_delete = p2.dl.delete_torrents
    p2.dl.delete_torrents = lambda hashes, delete_file=False, reason="", source="": (0, None)  # 闸门拦下
    out = p2._inject_release(hashes=H_OK, mode="delete", apply="1")
    _ok(out["deleted"] == 0 and out["still_live"] == [H_OK], "未 force：资源身份被闸门硬拦 → still_live 如实回传")
    _ok(out["downgraded"] == [] and p2.store.get(H_OK).get("sub") == "资源", "未 force：不动身份（库内资产仍受保护）")
    p2.dl.delete_torrents = real_delete
    out = p2._inject_release(hashes=H_OK, mode="delete", force="1", delete_files="1", apply="1")
    _ok(out["downgraded"] == [H_OK] and p2.store.get(H_OK) == {}, "force=1：先降级为普通再删，删掉后销账")
    _ok(p2.dl.deleted[-1]["delete_file"] is True, "delete_files=1 透传（连文件一起删）")

    # 硬拦时如实回传，不硬闯
    p3 = FakePlugin()
    h3 = "e" * 40
    p3.store.put(h3, {"site": "手工", "state": "静默", "sub": "资源"})
    p3.dl.live[h3] = True
    p3.gate_blocks.add(h3)
    p3.dl.delete_torrents = lambda hashes, delete_file=False, reason="", source="": (0, None)  # 闸门全拦
    out = p3._inject_release(hashes=h3, mode="delete", force="1", apply="1")
    _ok(out["still_live"] == [h3] and h3 in out["still_protected"], "被闸门硬拦 → still_live + 原因如实回传")
    _ok(p3.store.get(h3).get("sub") == "普通" and h3 not in p3.store.drops, "硬拦时保留账本行（还能再试）")

    _ok(p._inject_release(hashes="", mode="pause")["error"], "空 hashes → 报错")
    _ok(p._inject_release(hashes=H_OK, mode="remove")["error"], "非法 mode → 报错")
    _ok(MI._truthy("YES") and not MI._truthy("0"), "真值解析（1/true/yes/y/on）")


def main() -> int:
    print("魔流 15.8.14 临时/手工投放通道 —— 离线单测")
    t_content()
    t_prepare()
    t_plan()
    t_apply()
    t_release()
    print(f"\n结果：{_OK} 通过 / {_FAIL} 失败")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
