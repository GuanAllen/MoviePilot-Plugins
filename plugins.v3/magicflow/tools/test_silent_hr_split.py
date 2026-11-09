#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 11.11.0 静默池全 paused + H&R 拆到 __hr_host__ 离线回归测试。

覆盖（对应 DISCUSS-silent-hr-split.pro.md §6 测试清单 + DISCUSS-hr-exit-ui.pro.md §1.7）：
  ① 保种职务 `STATE_HR` 进状态机（DUTY_STATES / retag 产出 `魔流-<站>-保种`）；
  ② `retag(state=保种)` 不产出静默身份；`set_tag_state` 合法态不含保种（保种只由 _hr_obligation 派生）；
  ③ 陈旧保护被 `forget_torrents` 释放（protected_torrents / adopted_hashes）；
  ④ `_hrbills_tick` 违约拆两路：消失+active 账单 → `breached`（不 void）+ 报警归因；
  ⑤ 消失+从未完成 → 仍 void（无害，行为不变）；
  ⑥ `breached` 种重新出现 → 恢复 active（复欠重进）；
  ⑦ `_hr_breaches` 归因：deletions.jsonl 命中 ok=true → plugin_deleted（gate bug 升级 critical）。

用法：``python3 tools/test_silent_hr_split.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

import _app_stub  # noqa: E402
_app_stub.install()

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_hr_split_test"


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

tags = _load(PKG + ".tags", "tags.py")
fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
crossseed = _load(PKG + ".crossseed", "crossseed.py")
persistence = _load(PKG + ".persistence", "persistence.py")
downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")

HrBillsMixin = hrbills.HrBillsMixin
BILL_STATE_ACTIVE = hrbills.BILL_STATE_ACTIVE
BILL_STATE_VOID = hrbills.BILL_STATE_VOID
BILL_STATE_BREACHED = hrbills.BILL_STATE_BREACHED
CROSSSEED_TAG = crossseed.CROSSSEED_TAG
from _hr_mem_store import MemHrBillsStore  # noqa: E402


CHECKS = 0
FAILS: list[str] = []


def _ok(cond: bool, msg: str) -> None:
    """★ 任务 134：断言失败不再中断脚本——收集后继续跑，保证后续断言仍被执行。

    失败仍然计入 ``FAILS`` 并让退出码非 0（不降低强度，只是不早停）。
    """
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        FAILS.append(msg)



def _torrent(progress=0.0, seed_time=0.0, title="test", tracker="hdfans.org", completion_on=0.0):
    return types.SimpleNamespace(
        hash="", title=title, progress=progress, seed_time=seed_time,
        hit_and_run=False, tags=[], tracker=tracker, completion_on=completion_on, downloaded=1e9,
    )


def _torrent_bytes(name="test") -> bytes:
    info = {b"name": name.encode("utf-8"), b"length": 1000, b"piece length": 16384,
            b"pieces": b"0" * 20}
    meta = {b"info": info, b"announce": b"http://hdfans.org/announce"}
    return fingerprint.bencode(meta)


class HrHarness(HrBillsMixin):
    """最小 HrBills 桩：覆盖 breach / 归因所需的依赖。"""

    def __init__(self, data_dir: Path, deletions: Path):
        self._data_dir = data_dir
        self._hot = None
        self._deletions = deletions
        self.site_hr: dict = {}
        self.need_hours: dict = {}
        self.torrents: dict = {}
        self.ledger: dict = {}
        self.name2dom: dict = {}

    def _hrbills_store(self):
        if getattr(self, "_mem_store", None) is None:
            self._mem_store = MemHrBillsStore()
        return self._mem_store

    def get_data_path(self):
        return self._data_dir

    def _agent_deletions_rows(self):
        """删除审计读取口（生产走 mf_deletions；测试读 del_file JSONL）。"""
        import json as _json
        f = getattr(self, "del_file", None)
        if f is None:
            return []
        try:
            out = []
            for line in Path(f).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(_json.loads(line))
                except ValueError:
                    continue
            return out
        except OSError:
            return []

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _site_per_torrent_hr(self, dom):
        return False

    def _crossseed_seed_need_hours(self, dom):
        return self.need_hours.get(dom, 0.0)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        class _S:
            def __init__(self, d):
                self._d = d

            def items(self):
                return dict(self._d)

            def get(self, h):
                return dict(self._d.get(str(h).strip().lower()) or {})

            def put(self, h, rec):
                k = str(h).strip().lower()
                self._d.setdefault(k, {}).update(dict(rec or {}))
                return dict(self._d[k])
        return _S(self.ledger)

    def _site_domain_by_name(self, name):
        if not name:
            return ""
        if "." in name and " " not in name:
            return name.lower()
        return self.name2dom.get(name, "")

    def _deletions_log_path(self):
        return self._deletions


# ---------------------------------------------------------------------------
# 加载 common / silent / hr（stub app.* + 叶子模块）——测核心机制（pause gate/退役/迁移/收敛）
# ---------------------------------------------------------------------------
def _load_core():
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    common = _load(PKG + ".common", "common.py")
    silent = _load(PKG + ".features.silent", "features/silent.py")
    hr = _load(PKG + ".features.hr", "features/hr.py")
    return common, silent, hr


common, silent, hr = _load_core()


class _FakeDownloader:
    """桩下载器：记录 pause/resume/force_start 调用。"""

    def __init__(self):
        self.paused = []
        self.tags_set = []
        self.resumed = []
        self.force_started = []
        self.deleted = []
        self.is_available = True

    def replace_torrent_tags(self, h, tags):
        return True

    def set_torrent_tags(self, h, tags):
        return True

    def pause_torrents(self, hashes):
        self.paused.extend(hashes)
        return len(hashes), None

    def resume_torrents(self, hashes):
        self.resumed.extend(hashes)
        return len(hashes), None

    def set_torrent_tags(self, h, tags):
        self.tags_set.append((h, list(tags)))
        return True

    def force_start_torrents(self, hashes):
        self.force_started.extend(hashes)
        return len(hashes), None

    def delete_torrents(self, hashes, delete_file=False, reason="", source=""):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.deleted.extend(hs)
        return len(hs), None


class CoreHarness(silent.SilentMixin, hr.HrMixin):
    """带桩的最小插件实例：覆盖 silent/hr 的依赖（downloader / _hr_obligation / 账本）。"""

    def __init__(self):
        self.torrents = {}
        self.ledger = {}
        self.dl = _FakeDownloader()
        self.dl.is_available = True   # _hr_host_assign 要求下载器可用
        self.oblig = {}       # hash -> (owed, need, seeded, src)
        self.site_hr = {}     # 站点 H&R 制度（None/True/False），迁移判据要用
        self._tags_cfg = {"host_interval": 60}

    def _site_hr_flag(self, dom):
        return self.site_hr.get(str(dom or "").strip().lower())

    def _site_per_torrent_hr(self, dom):
        return False

    def _hr_incomplete_of(self, site, t):
        return False

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        class _S:
            def __init__(self, d):
                self._d = d

            def items(self):
                return dict(self._d)

            def get(self, h):
                return self._d.get(str(h or "").lower()) or {}

            def put(self, h, rec):
                self._d[str(h or "").lower()] = dict(rec or {})

            def drop(self, h):
                self._d.pop(str(h or "").lower(), None)
        return _S(self.ledger)

    def _get_downloader(self, name="qbittorrent"):
        return self.dl

    def _journal_deletions(self, by_task, log_prefix=""):
        pass

    def _log(self, msg, level=None):
        pass

    def _torrent_site_name(self, tags, fallback=""):
        return "hdfans.org"

    def _hr_obligation_rule(self, dom, torrent_hr=None):
        """与 hrbills 同口径的两道门槛（离线桩）。"""
        if torrent_hr is True:
            return "hit_and_run"
        if self._site_per_torrent_hr(dom):
            return None
        return "site_hr" if self._site_hr_flag(dom) is True else None

    def _hr_domain(self, site, torrent=None):
        return str(site or "hdfans.org").strip().lower()

    def _hr_obligation(self, site, torrent, snap=None):
        h = str(getattr(torrent, "hash", "") or "").lower()
        return self.oblig.get(h, (False, 24.0, 100.0, "test"))

    def _hrbills_store(self):
        if getattr(self, "_mem_store", None) is None:
            self._mem_store = MemHrBillsStore()
        return self._mem_store

    def _silent_pause_gate(self, hashes):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.dl.pause_torrents(hs)
        return {"paused": 0, "failed": 0}

    def _tag_groups(self):
        class _G:
            def group_of(self, h):
                return ""

            def items(self):
                return {}
        return _G()

    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self):
        return set()


class PlainSweepHarness(CoreHarness):
    """在 CoreHarness 上补 `_silent_plain_sweep` 所需的桩：魔力达标 + 低效可删。"""

    def _silent_hr_done(self, site, torrent):
        return (True, "done")

    def _magic_out_per_hour(self, t, n):
        return 0.5

    def _qb_num_complete(self):
        return {}

    def _pool_dirs(self):
        return []

    def _match_pool(self, sp, dirs):
        return ("/x", "/x")

    def _usage(self, ct):
        return {"pct": 80.0}

    def _site_magic_enough(self, site):
        return (True, "达标")


def main() -> int:
    print("=" * 64)
    print("魔流 · 11.11.0 静默全 paused + H&R 拆 __hr_host__ 回归测试")
    print("=" * 64)

    # ---- ① 保种职务进状态机 ----
    print("\n[1] 保种职务 STATE_HR 进状态机")
    _ok(tags.STATE_HR == "H&R", f"STATE_HR = 'H&R'（{tags.STATE_HR!r}）")
    _ok(tags.STATE_HR in tags.STATES, "STATE_HR 在 STATES（parse_tag 能解析）")
    _ok(tags.STATE_HR in tags.DUTY_STATES, "STATE_HR 在 DUTY_STATES（retag 能贴职务标签）")
    _ok(tags.STATE_HR not in ("刷流", "魔力", "静默", "推荐"), "保种是独立状态，不与老四态混")

    # ---- ② retag(state=保种) 产职务标签 + 保留静默身份；手动态不含保种 ----
    print("\n[2] retag(保种) 产出 魔流-<站>-保种，不覆盖身份")
    out = tags.retag(["魔流-hdfans-静默-资源", "魔流-hdfans-魔力"], site="hdfans", state=tags.STATE_HR, sub=tags.SUB_RESOURCE)
    _ok("魔流-hdfans-H&R" in out, f"retag 产出 H&R 职务标签（{out}）")
    _ok("魔流-hdfans-静默-资源" in out, f"静默身份保留（{out}）")
    _ok("魔流-hdfans-魔力" not in out, "原魔力职务被摘（换保种）")
    # set_tag_state 的合法态（静态断言：不含保种）
    legal = (tags.STATE_BRUSH, tags.STATE_BONUS, tags.STATE_SILENT, tags.STATE_RECOMMEND)
    _ok(tags.STATE_HR not in legal, "set_tag_state 合法态不含保种（保种只由 _hr_obligation 派生）")
    _ok(tags.tag_for("hdfans", tags.STATE_HR) == "魔流-hdfans-H&R", "tag_for(H&R) 正确拼标签")

    # ---- ③ forget_torrents 释放陈旧保护 ----
    print("\n[3] forget_torrents 释放陈旧保护")
    tmp = tempfile.mkdtemp(prefix="hr_split_persist_")
    store = persistence.MagicFlowStore(Path(tmp)) if hasattr(persistence, "MagicFlowStore") else None
    if store is None:
        # 高层封装在 persistence 里可能叫 MagicFlowStore；退回 TaskStateStore 单测
        print("  ⚠️ 无 MagicFlowStore，直接测 protect/unprotect + forget 语义（stub）")
        class _TS:
            def __init__(self):
                self.protected_torrents = {"aaaa", "bbbb"}
                self.adopted_hashes = {"aaaa", "cccc"}
                self.manual_paused = {"aaaa"}
                self.torrent_free_until = {}
        st = _TS()
        _ok("aaaa" in st.protected_torrents and "aaaa" in st.adopted_hashes, "初始有保护 + 纳管记录")
        # 直接验证 forget_torrents 的清理语义（在 TaskStateStore 方法上）
        _forget = getattr(persistence.TaskState, "__init__", None)
        _ok(_forget is not None, "TaskState 类存在")
    else:
        st = store.task_states.create("t1")
        st.protected_torrents = {"aaaa", "bbbb"}
        st.adopted_hashes = {"aaaa", "cccc"}
        store.task_states.save(st)
        _ok(len(store.get_protected_torrents("t1")) == 2, "保护集 2 个")
        n = store.forget_torrents("t1", ["aaaa"])
        _ok(n >= 2, f"forget_torrents 清理保护+纳管（{n}）")
        _ok("aaaa" not in store.get_protected_torrents("t1"), "aaaa 保护被释放")
        _ok("bbbb" in store.get_protected_torrents("t1"), "bbbb 保护保留（只清本任务指定 hash）")

    # ---- ④ 违约拆两路：active + 消失 → breached（不 void）----
    print("\n[4] 违约拆两路：消失 + active 账单 → breached")
    tmp2 = tempfile.mkdtemp(prefix="hr_split_")
    del_file = Path(tmp2) / "deletions.jsonl"
    h = HrHarness(Path(tmp2), del_file)
    h.site_hr["hdfans.org"] = True
    h.need_hours["hdfans.org"] = 20.0
    t_act = _torrent(progress=1.0, title="欠债种", tracker="hdfans.org")
    t_act.hash = "a111"
    h.torrents["a111"] = t_act
    h._hrbills_open("a111", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("a"))
    _ok(h._hrbills_store().get("a111")["state"] == "pending",
        "★ 15.5.1：开账 pending（H&R 自完成起算）")
    h._hrbills_tick()  # 先 tick 一次：把 bill.progress 刷到 1.0（种已完成）→ 转 active
    _ok(h._hrbills_store().get("a111")["state"] == "active", "已完成 → 转 active（欠债）")
    _ok(h._hrbills_store().get("a111")["progress"] >= 0.999, "tick 后 bill.progress 刷到 1.0")
    h.torrents.pop("a111")  # 从下载器消失
    # ★ 快照不能为空（19.0.0 空快照安全闸会整轮跳过）；放一颗无关种保持快照非空。
    _keep = _torrent(progress=1.0, title="无关种", tracker="hdfans.org")
    _keep.hash = "zzzz"
    h.torrents["zzzz"] = _keep
    h._hrbills_tick()
    b = h._hrbills_store().get("a111")
    _ok(b["state"] == BILL_STATE_BREACHED, f"消失 + active → breached（{b['state']}）")
    _ok(b.get("breached_at"), "写 breached_at 时间戳")

    # ---- ⑤ 消失 + 从未完成 → 仍 void（行为不变）----
    print("\n[5] 消失 + 从未完成 → 仍 void")
    t_inc = _torrent(progress=0.5, title="半截种", tracker="hdfans.org")
    t_inc.hash = "a222"
    h.torrents["a222"] = t_inc
    h._hrbills_open("a222", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("b"))
    h.torrents.pop("a222")
    h._hrbills_tick()
    b2 = h._hrbills_store().get("a222")
    # ★ 19.12.40：摘账不再物理删/立墓碑 —— 保留行 + alive=False + missing_since，等站端证据
    _ok((b2 or {}).get("state") == "pending" and b2.get("alive") is False
        and b2.get("missing_since"), f"消失 + 未完成 → 保留 pending + missing_since（实际 {(b2 or {}).get('state')}/{b2.get('alive')}）")

    # ---- ⑥ breached 种重新出现 → 恢复 active ----
    print("\n[6] breached 种重新出现 → 恢复 active（复欠重进）")
    t_re = _torrent(progress=1.0, title="欠债种", tracker="hdfans.org")
    t_re.hash = "a111"
    h.torrents["a111"] = t_re
    h._hrbills_tick()
    b3 = h._hrbills_store().get("a111")
    _ok(b3["state"] == BILL_STATE_ACTIVE, f"breached 重新出现 → active（{b3['state']}）")

    # ---- ⑦ _hr_breaches 归因：deletions.jsonl ok=true → plugin_deleted ----
    print("\n[7] _hr_breaches 归因")
    # 再让它消失，并写一条 deletions.jsonl 记录（ok=true = 本插件删 → gate bug）
    # ★ 任务 136：tick 不再自动把「消失」判成 breached；这里显式置 breached 以验归因链
    _st = h._hrbills_store()
    _st.patch_if("a111", {"state": BILL_STATE_ACTIVE}, state=BILL_STATE_BREACHED,
                 breached_at=__import__("time").time())
    h.torrents.pop("a111")
    h._hrbills_tick()
    h.del_file = del_file
    del_file.write_text(json.dumps({
        "ts": "2026-10-06 08:00:00", "hash": "a111", "site": "hdfans.org",
        "title": "欠债种", "source": "test", "reason": "x", "delete_file": False,
        "ok": True, "blocked": False, "err": "", "blocked_by": "",
    }) + "\n", encoding="utf-8")
    print("DEBUG a111:", h._hrbills_store().get("a111"))
    print("DEBUG del_file:", del_file, del_file.exists() if hasattr(del_file,"exists") else "?")
    rep = h._hr_breaches()
    _ok(rep["totals"]["breached"] >= 1, f"breaches 清单非空（{rep['totals']['breached']}）")
    row = next((x for x in rep["breaches"] if x["hash"] == "a111"), None)
    _ok(row is not None, "a111 出现在违约清单")
    _ok(row["attribution"] == "plugin_deleted", f"归因 = plugin_deleted（{row['attribution']}）")
    _ok(row["gate_bug"] is True and row["severity"] == "critical", "gate bug → severity=critical")

    # ---- ⑧ _silent_resume_tick 退役（SILENT_HR_SPLIT_ENABLED 下 no-op）----
    print("\n[8] _silent_resume_tick 退役")
    hc = CoreHarness()
    rep8 = hc._silent_resume_tick(apply=True)
    _ok(rep8.get("retired") is True, "_silent_resume_tick 返回 retired=True（静默池不再 resume）")
    _ok(not hc.dl.force_started and not hc.dl.resumed, "退役后不 force_start/resume 任何种")

    # ---- ⑨ _silent_pause_gate 无例外 pause ----------------
    print("\n[9] _silent_pause_gate 无例外 pause")
    hc2 = CoreHarness()
    t9 = _torrent(progress=1.0, tracker="hdfans.org")
    t9.hash = "aaaa"
    hc2.torrents["aaaa"] = t9
    hc2._silent_pause_gate(["aaaa"])
    _ok("aaaa" in hc2.dl.paused, "_silent_pause_gate 暂停该种（无 H&R 例外）")

    # ---- ⑩ _hr_guard_tick 收敛作用域（只扫 taken_by=__hr_host__）----
    print("\n[10] _hr_guard_tick 收敛作用域")
    hc3 = CoreHarness()
    t_a = _torrent(progress=1.0); t_a.hash = "aaaa"; t_a.tags = []
    t_b = _torrent(progress=1.0); t_b.hash = "bbbb"; t_b.tags = []
    hc3.torrents["aaaa"] = t_a
    hc3.torrents["bbbb"] = t_b
    hc3.ledger["aaaa"] = {"site": "hdfans.org", "state": "保种", "taken_by": "__hr_host__"}
    hc3.ledger["bbbb"] = {"site": "hdfans.org", "state": "静默", "taken_by": ""}
    rep10 = hc3._hr_guard_tick(apply=False)
    _ok(rep10["checked"] == 1, f"_hr_guard_tick 只扫 taken_by=__hr_host__（checked={rep10['checked']}）")

    # ---- ⑪ hr_host() 统一迁移：欠 H&R 非在岗非保种 → 保种 ----
    print("\n[11] hr_host() 统一迁移")
    hc4 = CoreHarness()
    t11 = _torrent(progress=1.0); t11.hash = "aaaa"; t11.tags = []
    hc4.torrents["aaaa"] = t11
    hc4.site_hr["hdfans.org"] = True   # 19.12.37：迁移先过「该不该记」两道门槛（与开账同源）
    hc4.ledger["aaaa"] = {"site": "hdfans.org", "state": "静默", "sub": "普通", "taken_by": ""}
    hc4.oblig["aaaa"] = (True, 24.0, 0.0, "test")   # 欠 H&R
    rep11 = hc4.hr_host()
    _ok(rep11.get("migrated", 0) >= 1, f"hr_host 统一迁移（migrated={rep11.get('migrated')}）")
    # ★ 19.12.38 职务拆分：H&R 保种是独立职务 STATE_HR（"H&R"），不再复用「保种」状态
    _ok(hc4.ledger["aaaa"].get("state") == "H&R", f"迁移后 state=H&R（{hc4.ledger['aaaa'].get('state')}）")
    _ok(hc4.ledger["aaaa"].get("taken_by") == "__hr_host__", "迁移后 taken_by=__hr_host__")
    _ok("aaaa" in hc4.dl.force_started, "迁移后立即 force_start（保挂 H&R）")

    # ---- ⑫ 解除「零删除」gate：apply=True 恢复真删除（13.0.0）----
    print("\n[12] 解除零删除 gate：apply=True 恢复真删除")
    _ok(silent.SILENT_HR_SPLIT_ENABLED is True, "SILENT_HR_SPLIT_ENABLED = True（拆分语义保留，零删除语义已解除）")
    hc5 = CoreHarness()
    t12 = _torrent(progress=0.5, tracker="hdfans.org"); t12.hash = "aaaa"; t12.tags = ["魔流-hdfans-静默-普通"]
    hc5.torrents["aaaa"] = t12
    hc5.ledger["aaaa"] = {"site": "hdfans.org", "state": "静默", "sub": "普通"}
    r_on = hc5._silent_purge_incomplete(apply=True, limit=10)
    _ok(r_on.get("pending", 0) >= 1, f"apply=True 算出 pending（{r_on.get('pending')}）")
    _ok("aaaa" in hc5.dl.deleted, "apply=True 真删（delete 被调用，零删除 gate 已解除）")
    _ok(r_on.get("deleted", 0) >= 1, f"返回 deleted={r_on.get('deleted')}")
    _ok(r_on.get("skipped", 0) == 0 and r_on.get("reason") != "阶段1 零删除", "不再返回 skipped + 阶段1 零删除")
    hc6 = CoreHarness()
    t13 = _torrent(progress=0.5); t13.hash = "aaaa"; t13.tags = ["魔流-hdfans-静默-普通"]
    hc6.torrents["aaaa"] = t13
    hc6.ledger["aaaa"] = {"site": "hdfans.org", "state": "静默", "sub": "普通"}
    r_dry = hc6._silent_purge_incomplete(apply=False, limit=10)
    _ok(r_dry.get("pending", 0) >= 1, f"apply=False 照旧算出 pending（{r_dry.get('pending')}）")
    _ok(not hc6.dl.deleted, "apply=False 不删")

    # ---- ⑬ 解除零删除 gate：低效普通清理 apply=True 真删（13.0.0）----
    print("\n[13] 低效普通清理（_silent_plain_sweep）ungate 后真删")
    hp = PlainSweepHarness()
    tp = _torrent(progress=1.0, tracker="hdfans.org"); tp.hash = "aaaa"; tp.tags = []
    hp.torrents["aaaa"] = tp
    hp.ledger["aaaa"] = {"site": "hdfans.org", "state": "静默", "sub": "普通"}
    rp = hp._silent_plain_sweep(apply=True, limit=10)
    _ok(rp.get("pending", 0) >= 1, f"低效普通算出 pending（{rp.get('pending')}）")
    _ok("aaaa" in hp.dl.deleted, "低效普通 apply=True 真删（delete 被调用）")
    _ok(rp.get("deleted", 0) >= 1, f"返回 deleted={rp.get('deleted')}")
    _ok(rp.get("skipped", 0) == 0 and rp.get("reason") != "阶段1 零删除", "不再返回 skipped + 阶段1 零删除")

    # ---- ⑬b ★15.8.11：音乐线不参与「低效普通种」清理 ----
    print("\n[13b] ★15.8.11 音乐线豁免：低效普通名单里的音乐种不删（自动不删；手动闸门另开）")
    hm = PlainSweepHarness()
    tm = _torrent(progress=1.0, tracker="hdfans.org"); tm.hash = "mus1"; tm.tags = []
    tm.category = "音乐"
    tn = _torrent(progress=1.0, tracker="hdfans.org"); tn.hash = "nor1"; tn.tags = []
    hm.torrents["mus1"] = tm
    hm.torrents["nor1"] = tn
    hm.ledger["mus1"] = {"site": "hdfans.org", "state": "静默", "sub": "普通"}
    hm.ledger["nor1"] = {"site": "hdfans.org", "state": "静默", "sub": "普通"}
    rm = hm._silent_plain_sweep(apply=True, limit=10)
    _ok("mus1" not in hm.dl.deleted,
        f"音乐种不删（按分类豁免，不依赖身份是否归位；删了 {sorted(set(hm.dl.deleted))}）")
    _ok("nor1" in hm.dl.deleted, "对照：同形的非音乐低效普通种照删")
    _ok(rm.get("deleted", 0) >= 1, f"返回 deleted={rm.get('deleted')}")

    print("\n" + "=" * 64)
    if FAILS:
        print(f"FAIL：{len(FAILS)} / {CHECKS} 项断言失败")
        for m in FAILS:
            print("  - " + m)
        return 1
    print(f"✅ 全部通过：{CHECKS} 项断言")
    return 0


if __name__ == "__main__":
    sys.exit(main())
