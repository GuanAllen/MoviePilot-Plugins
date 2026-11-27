# -*- coding: utf-8 -*-
"""魔力兑换解析器离线测试：用 13 站真实 mybonus.php 样本验证。"""
import glob
import importlib.util
import io
import json
import os
import sys

# collect_parse.py 是 L0（只 import .norm），用包上下文加载以满足相对导入
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)   # _dev_live
PARENT = os.path.dirname(ROOT)
sys.path.insert(0, PARENT)
# 把 _dev_live 作为一个包挂进去
if "magicflow_dev" not in sys.modules:
    pkg = type(sys)("magicflow_dev")
    pkg.__path__ = [ROOT]
    sys.modules["magicflow_dev"] = pkg
import importlib
cp = importlib.import_module("magicflow_dev.collect_parse")

samples = sorted(glob.glob(os.path.join(ROOT, "..", "_mybonus_samples", "*.html")))
if not samples:
    print("!! 无样本")
    sys.exit(1)

fail = 0
KIND_CN = {"upload": "上传量", "invite": "邀请名额", "temp_invite": "临时邀请"}
for fn in samples:
    html = io.open(fn, encoding="utf-8", errors="replace").read()
    r = cp.parse_bonus_exchange_page(html)
    its = r["items"]
    name = os.path.basename(fn)
    k = r.get("kinds") or {}
    print("%-26s ok=%s balance=%-10s cur=%-6s forms=%-3d 上传%d/邀请%d/临时%d"
          % (name, r["ok"], r["balance"], r["currency"], r["form_count"],
             k.get("upload", 0), k.get("invite", 0), k.get("temp_invite", 0)))
    if not (r["ok"] and len(its) > 0):
        fail += 1
        print("   FAIL why=", r["why"])
        continue
    # ★ 余额必须能读到（19.16.29 补 PT时间「魔力值：N」形态；取不到就说明又漏了一种文案）
    if r["balance"] is None or not r["currency"]:
        fail += 1
        print("   FAIL 余额/币名缺失 balance=%r currency=%r" % (r["balance"], r["currency"]))
    # kinds 汇总必须与逐项分类一致
    cnt = {}
    for u in its:
        cnt[u["kind"]] = cnt.get(u["kind"], 0) + 1
    for kk in ("upload", "invite", "temp_invite"):
        if cnt.get(kk, 0) != k.get(kk, 0):
            fail += 1
            print("   FAIL kinds 不一致", kk, cnt.get(kk, 0), k.get(kk, 0))
    for u in its:
        bad = u["option"] < 0 or u["price"] is None
        if u["kind"] == "upload":
            bad = bad or u["size_gb"] is None
        elif u["kind"] in ("invite", "temp_invite"):
            bad = bad or u["size_gb"] is not None or int(u.get("count") or 0) < 1
        elif u["kind"] not in KIND_CN:
            bad = True  # 不该出现未知类型
        if bad:
            fail += 1
            print("   FAIL item", u)
        else:
            qty = ("%sGB" % u["size_gb"]) if u["kind"] == "upload" else ("×%s" % u["count"])
            print("     [%-4s] opt=%-3s %-26s %8s %-8s %s"
                  % (KIND_CN.get(u["kind"], u["kind"]), u["option"], u["title"][:26],
                     u["price"], qty,
                     "禁用:" + str(u["disabled_reason"]) if u["disabled"] else "可换"))

# 边界：空页 / 登录页 / 无表单
for txt, label in [("", "空页"), ("<html><body>login</body></html>", "登录页"),
                   ("<html>just text</html>", "无表单")]:
    r = cp.parse_bonus_exchange_page(txt)
    if r["ok"] or r["items"]:
        fail += 1
        print("FAIL 边界", label, r)
    else:
        print("PASS 边界 %-8s why=%s" % (label, r["why"]))

print("\n结果：%s（fail=%d）" % ("PASS" if fail == 0 else "FAIL", fail))
sys.exit(1 if fail else 0)
