#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_source_site.py —— 来源站判据（DESIGN-RESOURCE-SEED §2 / §5.2）

判据：来源站 = 成员中「真下载(downloaded>0，非复用) 且完成最早(completion_on 最小)」那份的站；
write-once（定了不漂）；全是辅种/复用 → 空（不挂 H&R）；老口径（调用方未给真下载信息）退化为首个 downloaded。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.plugins.magicflow.ledger import ResourceLedgerStore  # noqa: E402

N = [0, 0]


def ok(cond, msg):
    N[0] += 1
    if cond:
        print(f"  \u2705 {msg}")
    else:
        N[1] += 1
        print(f"  \u274c {msg}")
        raise AssertionError(msg)


class FakeBackend:
    def __init__(self):
        self.g = {}

    def load_groups(self):
        return {k: dict(v) for k, v in self.g.items()}

    def save_groups(self, data):
        self.g = data


def store():
    return ResourceLedgerStore(FakeBackend())


GID = "fp:" + "a" * 40
GB = 1024 ** 3


def main():
    print("1. 辅种（dl_bytes=0，完成时刻更早）不能占源；真下载者胜")
    s = store()
    s.add_member(GID, "rep1", site="B站", downloaded=True, dl_bytes=0.0,
                 completed_at=1000.0, added_at=900.0)          # 复用份（辅种）
    s.add_member(GID, "src1", site="A站", downloaded=True, dl_bytes=5 * GB,
                 completed_at=2000.0, added_at=500.0)          # 真下载
    rec = s.items()[GID]
    ok(rec["source_site"] == "A站", "辅种不占源 → 来源站=A站(真下载)")
    ok(rec["source_hash"] == "src1", "source_hash 指向真下载那份")
    ok(rec["members"]["rep1"]["reused"] is True, "辅种标 reused=True")
    ok(rec["members"]["src1"]["reused"] is False, "真下载标 reused=False")

    print("2. 真下载定源后 write-once：后续真下载/辅种都不顶替（冻结不漂）")
    s = store()
    s.add_member(GID, "srca", site="A站", downloaded=True, dl_bytes=5 * GB,
                 completed_at=1000.0, added_at=100.0)          # 先完成 → 定为源
    s.add_member(GID, "srcc", site="C站", downloaded=True, dl_bytes=5 * GB,
                 completed_at=900.0, added_at=200.0)           # 后到（完成更早）→ 不顶替
    s.add_member(GID, "repB", site="B站", downloaded=True, dl_bytes=0.0,
                 completed_at=50.0, added_at=90.0)             # 辅种 → 不参评
    rec = s.items()[GID]
    ok(rec["source_site"] == "A站" and rec["source_hash"] == "srca",
       "源冻结在 A站，后到者(含完成更早的 C站)不顶替")

    print("3. 全辅种/复用（无真下载份）→ 来源站 空（不挂 H&R，宁漏不错）")
    s = store()
    s.add_member(GID, "r1", site="A站", downloaded=True, dl_bytes=0.0, completed_at=100.0)
    s.add_member(GID, "r2", site="B站", downloaded=True, dl_bytes=0.0, completed_at=200.0)
    rec = s.items()[GID]
    ok(not rec.get("source_site"), "全复用 → 来源站为空")
    ok(rec.get("source_hash") in (None, ""), "source_hash 亦为空")

    print("4. 真下载但无完成时刻 → 退用加入最早者（不误判为空）")
    s = store()
    s.add_member(GID, "n1", site="A站", downloaded=True, dl_bytes=9 * GB, added_at=800.0)
    s.add_member(GID, "n2", site="B站", downloaded=True, dl_bytes=9 * GB, added_at=300.0)
    rec = s.items()[GID]
    ok(rec["source_site"] == "A站" and rec["source_hash"] == "n1",
       "无完成时刻 → 该 pass 首个真下载(A站)兜底")

    print("5. 老口径兜底：调用方未给真下载信息（dl_bytes=None）→ 首个 downloaded 成员")
    s = store()
    s.add_member(GID, "old1", site="A站", downloaded=True)   # 不给 dl_bytes
    rec = s.items()[GID]
    ok(rec["source_site"] == "A站" and rec["source_hash"] == "old1",
       "dl_bytes=None 老口径：source=A站")

    print(f"\n\u2705 PASS \u2014\u2014 \u5171 {N[0]} \u9879\u65ad\u8a00\uff0c{N[1]} \u5931\u8d25")
    return 0 if N[1] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
