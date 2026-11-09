#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_crossseed_src_tick.py —— 恢复的 _crossseed_sources_tick 行为（14.0.0 删了调用点残留）。

覆盖：① 做种时长达标 → 标 done（解除保护）② 未达标 → 标签确权 ③ 已消失 → prune ④ done 后不再动。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.plugins.magicflow.features.crossseed import CrossSeedMixin  # noqa: E402
from app.plugins.magicflow.crossseed import CROSSSEED_TAG  # noqa: E402

N = [0, 0]


def ok(c, m):
    N[0] += 1
    if c:
        print(f"  \u2705 {m}")
    else:
        N[1] += 1
        print(f"  \u274c {m}")
        raise AssertionError(m)


class FakeInfo:
    def __init__(self, progress=1.0, seed_time=0.0, completion_on=0.0, tags=None):
        self.progress = progress
        self.seed_time = seed_time
        self.completion_on = completion_on
        self.tags = list(tags or [])


class FakeDL:
    is_available = True

    def __init__(self, infos):
        self.infos = infos
        self.retagged = []

    def get_torrent_info(self, h):
        return self.infos.get(h)

    def set_torrent_tags(self, h, tags):
        self.retagged.append((h, tuple(tags)))
        return True


class FakeStore:
    def __init__(self, data):
        self.data = data

    def items(self):
        return {k: dict(v) for k, v in self.data.items()}

    def put(self, h, patch):
        self.data.setdefault(h, {}).update(patch)
        return self.data[h]

    def drop(self, h):
        self.data.pop(str(h).strip().lower(), None)

    def prune(self, live):
        dead = [h for h in list(self.data) if h not in live]
        for h in dead:
            self.data.pop(h, None)
        return dead


class Host(CrossSeedMixin):
    def __init__(self, store, dl):
        self._store = store
        self._dl = dl
        self.logs = []

    def _hrbills_store(self):
        """跨站来源份的 H&R 账单判据：19.12.x 起只认 PG 三态（离线用内存字典）。"""
        bills = getattr(self, "bills", {}) or {}

        class _S:
            @staticmethod
            def get_result(h):
                v = bills.get(str(h).strip().lower())
                return {"status": "found" if v else "absent", "value": v}

            @staticmethod
            def all_result():
                return {"status": "found", "value": dict(bills)}

            @staticmethod
            def all():
                return dict(bills)
        return _S()

    def _log(self, msg, level="info"):
        self.logs.append(str(msg))

    def _crossseed_sources(self):
        return self._store

    def _get_downloader(self, name="qbittorrent"):
        return self._dl


NOW = time.time()


def main():
    print("1. 做种时长达标 → 标 done（解除 H&R 保护）")
    infos = {"h1": FakeInfo(seed_time=10 * 3600, completion_on=NOW - 10 ** 7, tags=[CROSSSEED_TAG])}
    store = FakeStore({"h1": {"hours": 10.0, "downloader": "qbittorrent", "site_b": "红豆饭"}})
    h = Host(store, FakeDL(infos))
    # 19.10.11：达标 = H&R 账单已结清 → 直接摘记录（不再写历史 done 标记）
    h.bills = {"h1": {"site": "hongdou", "rule": "site_hr", "state": "settled",
                      "need_h": 24.0, "seeded_h": 30.0}}
    r = h._crossseed_sources_tick()
    ok("h1" not in store.data, "账单已结清 → 摘来源份记录（释放保护）")
    ok(r["completed"] == 1, "res.completed=1")
    ok(any("义务完成" in x for x in h.logs), "日志有「义务完成」")

    print("2. 未达标 → 不置 done；标签确权到「魔流-跨站」")
    infos = {"h2": FakeInfo(seed_time=1 * 3600, completion_on=NOW - 10 ** 7, tags=["别的标"])}
    store = FakeStore({"h2": {"hours": 10.0, "downloader": "qbittorrent"}})
    dl = FakeDL(infos)
    h = Host(store, dl)
    h.bills = {"h2": {"site": "hongdou", "rule": "site_hr", "state": "active",
                      "need_h": 24.0, "seeded_h": 1.0}}
    r = h._crossseed_sources_tick()
    ok(not store.data["h2"].get("done"), "未达标 → 不置 done")
    ok(r["retagged"] == 1 and dl.retagged and dl.retagged[0][1] == (CROSSSEED_TAG,), "标签确权到 魔流-跨站")

    print("3. 已不在下载器 → prune 清掉")
    infos = {}
    store = FakeStore({"h3": {"hours": 10.0, "downloader": "qbittorrent"}})
    h = Host(store, FakeDL(infos))
    # 账单仍开放 → 不走「结清摘除」，交给 prune 清理（19.10.11 口径）
    h.bills = {"h3": {"site": "hongdou", "rule": "site_hr", "state": "active",
                      "need_h": 24.0, "seeded_h": 1.0}}
    r = h._crossseed_sources_tick()
    ok(r["pruned"] == 1 and "h3" not in store.data, "消失条目被 prune")

    print("4. 已 done → 不再保护、不强制标签")
    infos = {"h4": FakeInfo(seed_time=1 * 3600, completion_on=NOW, tags=["别的标"])}
    store = FakeStore({"h4": {"hours": 10.0, "done": True, "downloader": "qbittorrent"}})
    dl = FakeDL(infos)
    r = h._crossseed_sources_tick()
    ok(r["retagged"] == 0 and not dl.retagged, "done 条目不再被改标签")

    print(f"\n\u2705 PASS \u2014\u2014 \u5171 {N[0]} \u9879\u65ad\u8a00\uff0c{N[1]} \u5931\u8d25")
    return 0 if N[1] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
