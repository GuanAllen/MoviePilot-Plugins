# -*- coding: utf-8 -*-
"""魔流 · 认领预设表回归（离线，无需 MoviePilot）。

覆盖：
  (a) 预设表 11 站齐全（CARPT + 咖啡/Depth Studio + 8 个同族站）
  (b) 每个 supported 预设字段完整、endpoint 模板合法（只有 {id}/{uid} 占位）
  (c) 已核对站数值断言（carpt / ptcafe / dstudio）
  (d) 未公布规则的 8 站必须带 rules_unverified=True（不许伪装成已核对）
  (e) preset_for() 域名归一（协议/大小写/www/尾斜杠）

用法：``python3 tools/test_claim_presets.py``（退出码 0=PASS / 1=FAIL）。
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("mf_claim_presets", ROOT / "sites/claim_presets.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CLAIM_PRESETS = mod.CLAIM_PRESETS
preset_for = mod.preset_for

fails = []


def _ok(cond, msg):
    if not cond:
        fails.append(msg)


EXPECTED = {
    "carpt.net", "ptcafe.club", "dstudio.me",
    "cyanbug.net", "hdtime.org", "pt.soulvoice.club", "duckboobee.org",
    "novahd.top", "crabpt.vip", "cspt.top", "pt.btschool.club",
}
_ok(set(CLAIM_PRESETS) == EXPECTED, f"预设站点集合不符：{sorted(set(CLAIM_PRESETS) ^ EXPECTED)}")

UNVERIFIED = {
    "cyanbug.net", "hdtime.org", "pt.soulvoice.club", "duckboobee.org",
    "novahd.top", "crabpt.vip", "cspt.top",
}
for key, prof in CLAIM_PRESETS.items():
    _ok(prof.get("supported") is True, f"{key}: supported 必须为 True")
    for field in ("min_age_days", "max_claimers", "per_user_cap", "benefit", "benefit_desc",
                  "claim_page", "claim_list", "claim_entry", "detail_selector"):
        _ok(field in prof, f"{key}: 缺字段 {field}")
    pen = prof.get("penalty") or {}
    for field in ("unsatisfied", "abandon", "exempt_days"):
        _ok(field in pen, f"{key}: penalty 缺 {field}")
    st = prof.get("settlement") or {}
    for field in ("cycle", "cycle_text", "target_seed_hours", "target_upload_ratio",
                  "payout_hours", "payout_multiplier"):
        _ok(field in st, f"{key}: settlement 缺 {field}")
    ep = prof.get("endpoint") or {}
    method = str(ep.get("method") or "POST").upper()
    _ok(str(ep.get("path") or "").startswith("/"), f"{key}: endpoint.path 非法")
    if method == "POST":
        _ok((ep.get("body") or {}).get("action") == "addClaim", f"{key}: POST endpoint 不是 addClaim")
    else:
        _ok("{id}" in str(ep.get("path") or ""), f"{key}: GET endpoint 缺 {{id}} 占位符")
    placeholders = set()
    stack = [ep]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str):
            placeholders |= set(re.findall(r"\{[^}]*\}", cur))
    _ok(placeholders <= {"{id}", "{uid}"}, f"{key}: endpoint 出现非法占位符 {sorted(placeholders)}")
    unverified = bool(prof.get("rules_unverified"))
    _ok(unverified == (key in UNVERIFIED), f"{key}: rules_unverified 标记错误（应为 {key in UNVERIFIED}）")
    _ok(bool(str(prof.get("rules_note") or "").strip()), f"{key}: 缺 rules_note")

# 已核对站数值
_ok(CLAIM_PRESETS["carpt.net"]["max_claimers"] == 20, "carpt: 每颗 20 人")
_ok(CLAIM_PRESETS["carpt.net"]["settlement"]["target_seed_hours"] == 300, "carpt: 达标 300h")
_ok(CLAIM_PRESETS["carpt.net"]["penalty"]["abandon"] == 500, "carpt: 放弃扣 500")
_ok(CLAIM_PRESETS["ptcafe.club"]["per_user_cap"] == 3000, "咖啡: 上限 3000")
_ok(CLAIM_PRESETS["ptcafe.club"]["max_claimers"] == 10, "咖啡: 每颗 10 人")
_ok(CLAIM_PRESETS["ptcafe.club"]["settlement"]["target_upload_ratio"] == 10, "咖啡: 上传 ×10")
_ok(CLAIM_PRESETS["ptcafe.club"]["penalty"]["unsatisfied"] == 3000, "咖啡: 不达标扣 3000")
_ok(CLAIM_PRESETS["dstudio.me"]["max_claimers"] == 30, "Depth: 每颗 30 人")
_ok(CLAIM_PRESETS["dstudio.me"]["per_user_cap"] == 500, "Depth: 单用户 500")
_ok(CLAIM_PRESETS["dstudio.me"]["penalty"]["unsatisfied"] == 1000, "Depth: 不达标扣 1000")

# 学校：入口/动作都在种子详情页 → GET viewclaims.php?add_torrent_id={id}
_school = CLAIM_PRESETS["pt.btschool.club"]
_ok(_school["claim_page"] == "/details.php?id={id}", "学校: 认领详情页应是种子详情页")
_ok(_school["endpoint"]["method"] == "GET", "学校: 认领动作应为 GET")
_ok("viewclaims.php?add_torrent_id={id}" in _school["endpoint"]["path"], "学校: GET 模板应是 viewclaims.php?add_torrent_id=")
_ok("viewclaims" in _school["claim_entry"], "学校: 入口应是 viewclaims.php")
_ok(_school["min_age_days"] == 0,
    "学校: 认领无发布天数门槛（19.10.60 纠错：30 天是「发奖」条件）")
_ok(_school["reward_min_age_days"] == 30.0, "学校: 发奖满30天")
_ok(_school["max_claimers"] == 20, "学校: 每颗20人")
_ok(_school["per_user_cap"] == 100, "学校: 每人100")
_ok(_school["settlement"]["target_seed_hours"] == 300, "学校: 月做种300h")
_ok(_school["settlement"]["target_upload_ratio"] == 10, "学校: 月上传×10")
_ok(_school["penalty"]["abandon"] == 300, "学校: 放弃扣300")

# 同族插件站：入口在个人详情页（userdetails.php 的认领配额）
for _k in ("ptcafe.club", "cyanbug.net", "cspt.top", "carpt.net"):
    _ok("userdetails.php" in CLAIM_PRESETS[_k]["claim_entry"], f"{_k}: 入口应是 userdetails.php 配额")

# 域名归一
for raw in ("https://ptcafe.club/", "WWW.PTCAFE.CLUB", "ptcafe.club/rules.php"):
    _ok(bool(preset_for(raw)), f"preset_for 未命中：{raw}")
_ok(preset_for("example.org") is None, "未知域名不应命中")
_ok(preset_for("www.novahd.top") is not None, "www 前缀应命中")

if fails:
    print("FAIL")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print(f"PASS · 预设 {len(CLAIM_PRESETS)} 站（未核对 {len(UNVERIFIED)}），字段/模板/域名归一全部通过")
