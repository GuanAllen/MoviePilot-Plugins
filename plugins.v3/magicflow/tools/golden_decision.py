#!/usr/bin/env python3
"""行为基线（golden decision）—— 把「保护/删除判定」钉死，重构前后 diff 报警。

删除不可逆，这是唯一可证明「重构没改变判定行为」的手段。

原理：对一组**冻结**的种子 hash，调用两个只读端点，记录每颗种子的判定结果：
  * ``GET /debug/delete-gate?hashes=h1,h2,...``  → 每个 hash 的硬保护拦截理由串
  * ``GET /tags?action=state&hash=<h>``          → 台账 {site,state} + group_id

判定理由里的数字（挂种时长、体积…）会被**归一化**成 ``#``，否则基线天天抖。
结果按 hash 字典序排序后落盘，``--check`` 重算同一基线并逐字段 diff：
任何差异（增删 hash / 理由变化 / 状态迁移）都打印明细并以退出码 1 报警。

仅依赖 Python 标准库。认证：读 ``~/.openclaw/magicflow.json``（``{"url","user","password"}``，
host 是 :3001）登录换 JWT；也可用环境变量 ``MOVIEPILOT_TOKEN`` 跳过登录。
（登录逻辑与魔流 skill CLI 一致，此处为独立实现，不 import。）

用法：
  python3 tools/golden_decision.py --init-hashes 40   # 冻结前 N 个 hash 到基线清单
  python3 tools/golden_decision.py --record           # 记录当前判定 → golden_decisions.json
  python3 tools/golden_decision.py --check            # 重算并 diff 基线（有差异 → exit 1）
  python3 tools/golden_decision.py --why <hash>       # 打印单个 hash 的判定+状态（排查用）
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ------------------------------------------------------------------ 路径 / 常量
_HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(_HERE, "fixtures")
HASHES_FILE = os.path.join(FIXTURES_DIR, "golden_hashes.json")
DECISIONS_FILE = os.path.join(FIXTURES_DIR, "golden_decisions.json")

CONFIG_FILE = os.path.expanduser("~/.openclaw/magicflow.json")
DEFAULTS = {"url": "http://127.0.0.1:3001", "user": "guan", "password": ""}
PLUGIN = "/api/v1/plugin/MagicFlow"
SCHEMA_VERSION = 1

# 数字（含小数）→ '#'。判定理由里的时长/体积等会随时间漂移，必须抹掉。
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def normalize_reason(text):
    """判定理由串归一化：所有数字 → '#'，并收敛空白。"""
    s = _NUM_RE.sub("#", str(text or ""))
    return " ".join(s.split())


# ------------------------------------------------------------------ 客户端
def _load_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as fh:
                cfg.update({k: v for k, v in json.load(fh).items() if v})
        except Exception as err:  # noqa: BLE001
            sys.stderr.write(f"[warn] 读取 {CONFIG_FILE} 失败: {err}\n")
    for env, key in (("MOVIEPILOT_URL", "url"), ("MOVIEPILOT_USER", "user"), ("MOVIEPILOT_PASSWORD", "password")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


class Client:
    def __init__(self):
        cfg = _load_cfg()
        self.base = cfg["url"].rstrip("/")
        self.token = os.environ.get("MOVIEPILOT_TOKEN") or self._login(cfg["user"], cfg["password"])

    def _login(self, user, password):
        body = urllib.parse.urlencode({"username": user, "password": password}).encode()
        req = urllib.request.Request(
            self.base + "/api/v1/login/access-token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            tok = json.load(resp).get("access_token")
        if not tok:
            raise SystemExit("登录失败：未取到 access_token（检查 ~/.openclaw/magicflow.json）")
        return tok

    def get(self, path, query=None):
        url = self.base + PLUGIN + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode(errors="replace"))
        except urllib.error.HTTPError as err:
            raise SystemExit(f"HTTP {err.code}: {err.read().decode(errors='replace')[:500]}")
        except Exception as err:  # noqa: BLE001
            raise SystemExit(f"请求失败 {path}: {err}")


def _data(resp):
    return (resp or {}).get("data") if isinstance(resp, dict) else resp


# ------------------------------------------------------------------ 数据采集
def fetch_gate(cli, hashes):
    """批量取删除闸门判定 → {hash: 归一化理由串}（未拦截的不出现）。"""
    out = {}
    hs = [str(h).strip().lower() for h in hashes if str(h).strip()]
    if not hs:
        return out
    resp = cli.get("/debug/delete-gate", {"hashes": ",".join(hs)})
    if not (isinstance(resp, dict) and resp.get("success", True)):
        raise SystemExit(f"delete-gate 返回失败: {resp}")
    why = (_data(resp) or {}).get("why") or {}
    for h, reason in why.items():
        out[str(h).strip().lower()] = normalize_reason(reason)
    return out


def fetch_state(cli, h):
    """单个 hash 的台账状态 → {site, state, group_id}（只保留稳定字段）。"""
    resp = cli.get("/tags", {"action": "state", "hash": h})
    d = _data(resp) or {}
    ledger = d.get("ledger") or {}
    return {
        "site": str(ledger.get("site") or ""),
        "state": str(ledger.get("state") or ""),
        "group_id": str(d.get("group_id") or ""),
    }


def compute_decisions(cli, hashes):
    """对冻结清单重算全部判定 → {hash: {reason, blocked, site, state, group_id}}。"""
    gate = fetch_gate(cli, hashes)
    decisions = {}
    for h in hashes:
        st = fetch_state(cli, h)
        reason = gate.get(h, "")
        decisions[h] = {
            "reason": reason,
            "blocked": bool(reason),
            "site": st["site"],
            "state": st["state"],
            "group_id": st["group_id"],
        }
    return decisions


# ------------------------------------------------------------------ 落盘 / 读取
def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text + "\n")
    os.replace(tmp, path)


def load_hashes():
    if not os.path.exists(HASHES_FILE):
        raise SystemExit(f"缺少 {HASHES_FILE}，先跑 `--init-hashes N`")
    with open(HASHES_FILE) as fh:
        obj = json.load(fh)
    hs = obj.get("hashes") if isinstance(obj, dict) else obj
    return [str(h).strip().lower() for h in (hs or []) if str(h).strip()]


# ------------------------------------------------------------------ 命令
def cmd_init(cli, n):
    try:
        resp = cli.get("/debug/torrents", {"limit": 0})
    except SystemExit:
        resp = None
    if not (isinstance(resp, dict) and resp.get("success", True) and (_data(resp) or {}).get("by_tag")):
        # 退化：limit 参数不被认 / 返回异常 → 用 limit=200
        resp = cli.get("/debug/torrents", {"limit": 200})
    if not (isinstance(resp, dict) and resp.get("success", True)):
        raise SystemExit(f"debug/torrents 返回失败: {resp}")
    d = _data(resp) or {}
    seen, ordered = set(), []
    for _tag, lst in (d.get("by_tag") or {}).items():
        for t in lst or []:
            h = str((t or {}).get("hash", "")).strip().lower()
            if h and h not in seen:
                seen.add(h)
                ordered.append(h)
    if not ordered:
        raise SystemExit("未取到任何 hash（下载器为空？）")
    picked = sorted(ordered[:max(1, int(n))])
    obj = {"version": SCHEMA_VERSION, "count": len(picked), "hashes": picked}
    _dump(HASHES_FILE, obj)
    print(f"✅ 冻结 {len(picked)} 个 hash → {os.path.relpath(HASHES_FILE, _HERE)}")
    for h in picked[:5]:
        print(f"   {h}")
    if len(picked) > 5:
        print(f"   …（共 {len(picked)}）")


def cmd_record(cli):
    hashes = load_hashes()
    if not hashes:
        raise SystemExit("基线 hash 清单为空，先跑 `--init-hashes N`")
    decisions = compute_decisions(cli, hashes)
    obj = {"version": SCHEMA_VERSION, "count": len(decisions), "decisions": decisions}
    _dump(DECISIONS_FILE, obj)
    print(f"✅ 记录 {len(decisions)} 个 hash 的判定 → {os.path.relpath(DECISIONS_FILE, _HERE)}")


def _diff(baseline, current):
    diffs = []
    b = baseline.get("decisions") or {}
    for h in sorted(set(b) | set(current)):
        if h not in b:
            diffs.append(("+", h, "新增 hash（基线不存在）", None, None))
            continue
        if h not in current:
            diffs.append(("-", h, "缺失 hash（本次未取到）", None, None))
            continue
        bd, cd = b[h], current[h]
        for k in ("reason", "blocked", "site", "state", "group_id"):
            if bd.get(k) != cd.get(k):
                diffs.append(("~", h, k, bd.get(k), cd.get(k)))
    return diffs


def cmd_check(cli):
    if not os.path.exists(DECISIONS_FILE):
        raise SystemExit(f"缺少基线 {DECISIONS_FILE}，先跑 `--record`")
    with open(DECISIONS_FILE) as fh:
        baseline = json.load(fh)
    hashes = load_hashes()
    current = compute_decisions(cli, hashes)
    diffs = _diff(baseline, current)
    if not diffs:
        print(f"✅ 基线一致（{len(current)} 个 hash，判定无变化）")
        return 0
    print(f"❌ 判定行为发生变化：{len(diffs)} 处差异（基线 {os.path.relpath(DECISIONS_FILE, _HERE)}）")
    for kind, h, field, old, new in diffs:
        if kind == "+":
            print(f"  + {h[:12]}…  {field}")
        elif kind == "-":
            print(f"  - {h[:12]}…  {field}")
        else:
            print(f"  ~ {h[:12]}…  {field}: {old!r} -> {new!r}")
    return 1


def cmd_why(cli, h):
    h = str(h).strip().lower()
    gate = fetch_gate(cli, [h])
    st = fetch_state(cli, h)
    reason = gate.get(h, "")
    print(json.dumps({
        "hash": h,
        "blocked": bool(reason),
        "reason": reason,
        "raw_reason_hint": "数字已归一化为 #；原始理由请直接看 /debug/delete-gate",
        **st,
    }, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description="魔流行为基线（golden decision）")
    ap.add_argument("--init-hashes", metavar="N", type=int, help="冻结前 N 个 hash 到基线清单")
    ap.add_argument("--record", action="store_true", help="记录当前判定为基线")
    ap.add_argument("--check", action="store_true", help="重算并与基线 diff（有差异 exit 1）")
    ap.add_argument("--why", metavar="HASH", help="打印单个 hash 的判定+状态")
    args = ap.parse_args(argv)

    chosen = [bool(args.record), bool(args.check), args.init_hashes is not None, bool(args.why)]
    if sum(chosen) != 1:
        ap.error("请且仅请指定一个操作：--init-hashes N / --record / --check / --why HASH")

    cli = Client()
    if args.init_hashes is not None:
        cmd_init(cli, args.init_hashes)
        return 0
    if args.record:
        cmd_record(cli)
        return 0
    if args.check:
        return cmd_check(cli)
    if args.why:
        return cmd_why(cli, args.why)
    return 0


if __name__ == "__main__":
    sys.exit(main())
