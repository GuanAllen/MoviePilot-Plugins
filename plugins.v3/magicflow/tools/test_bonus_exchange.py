# -*- coding: utf-8 -*-
"""魔力兑换 mixin 离线测试：看板只读（三类项）+ 确认闸门 + option 核对（不发真写请求）。

19.16.29：样本换 04_cyanbug（含可换的邀请名额 / 临时邀请），覆盖三类项与邀请专属文案。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if "magicflow_dev" not in sys.modules:
    pkg = type(sys)("magicflow_dev")
    pkg.__path__ = [ROOT]
    sys.modules["magicflow_dev"] = pkg

# 假的 Response（避免造 app 模块）
class Response:
    def __init__(self, success=True, message="", data=None):
        self.success, self.message, self.data = success, message, data or {}

# 给 app.schemas 造假
if "app" not in sys.modules:
    app = type(sys)("app"); app.__path__ = []; sys.modules["app"] = app
schemas = type(sys)("app.schemas"); schemas.__path__ = []; schemas.Response = Response
sys.modules["app.schemas"] = schemas
types_mod = type(sys)("app.schemas.types")
for n in ("EventType", "MediaType"):
    setattr(types_mod, n, type(n, (), {}))
sys.modules["app.schemas.types"] = types_mod

# stub common（真 common 依赖 app.sdk 事件系统，离线不必加载）
common_stub = type(sys)("magicflow_dev.common")
def as_bool_arg(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")
common_stub.as_bool_arg = as_bool_arg
common_stub.task_is_participating = lambda *a, **k: False
common_stub.CROSSSEED_TASK_ID = -1
sys.modules["magicflow_dev.common"] = common_stub

from magicflow_dev.features.bonus_exchange import BonusExchangeMixin

SAMPLE = io.open(os.path.join(ROOT, "..", "_mybonus_samples", "04_cyanbug_net.html"),
                 encoding="utf-8", errors="replace").read()

class FakeRes:
    ok = True
    text = SAMPLE
    error = ""

class FakeHttp:
    def text(self, sid, url, kind=None, ttl=None):
        return FakeRes()

class FakeCollect:
    http = FakeHttp()

class T(BonusExchangeMixin):
    def _collect_ref(self): return FakeCollect()
    def _pv_allow(self, sid, kind, want=1): return True
    def _pv_spend(self, sid, kind, n=1): return n
    def _list_sites(self):
        return [{"id": 4, "name": "大青虫", "domain": "https://cyanbug.net/", "url": "https://cyanbug.net",
                 "cookie": "x=1", "ua": "Mozilla/5.0", "timeout": 15}]
    def _get_site(self, sid):
        return self._list_sites()[0]

t = T()
fail = 0

# 1) 看板：三类都解析出来（upload 5 / invite 3 / temp_invite 1）→ 总 9 项，可换 6
r = t.get_bonus_exchange_state()
d = r.data
s0 = d["sites"][0]
k = s0["kinds"]
tot = d["totals"]
print("看板: ok=%s balance=%s kinds=u%s/i%s/t%s items=%s 可换=%s"
      % (s0["ok"], s0["balance"], k.get("upload"), k.get("invite"), k.get("temp_invite"),
         tot["items"], tot["exchangeable"]))
if not (r.success and s0["ok"] and k.get("upload") == 5 and k.get("invite") == 3
        and k.get("temp_invite") == 1 and tot["items"] == 9 and tot["exchangeable"] == 6):
    print("FAIL 看板三类"); fail += 1
# 对账：各类可换之和 == 总可换
eb = tot.get("exchangeable_by_kind") or {}
if sum(eb.values()) != tot["exchangeable"]:
    print("FAIL 可换数对账", eb, tot["exchangeable"]); fail += 1

# 2) 干跑（上传量 opt=0）：需 confirm，kind=upload
r2 = t.bonus_exchange_act(site_id=4, option=0)
dd = r2.data or {}
print("干跑上传: need_confirm=%s kind=%s msg=%s"
      % (dd.get("need_confirm"), dd.get("kind"), r2.message[:40]))
if r2.success or not dd.get("need_confirm") or dd.get("kind") != "upload":
    print("FAIL 上传干跑闸门"); fail += 1

# 3) 干跑（可换邀请 opt=8）：需 confirm，kind=invite，文案提示名额不退
r3 = t.bonus_exchange_act(site_id=4, option=8)
d3 = r3.data or {}
print("干跑邀请: need_confirm=%s kind=%s cn=%s msg=%s"
      % (d3.get("need_confirm"), d3.get("kind"), d3.get("kind_cn"), r3.message[:46]))
if (r3.success or not d3.get("need_confirm") or d3.get("kind") != "invite"
        or d3.get("kind_cn") != "邀请名额" or "名额换回不退" not in r3.message):
    print("FAIL 邀请干跑闸门"); fail += 1

# 4) 越界 option → 拒绝
r4 = t.bonus_exchange_act(site_id=4, option=999, confirm=1)
print("越界 option: success=%s msg=%s" % (r4.success, r4.message[:44]))
if r4.success:
    print("FAIL option 核对"); fail += 1

# 5) disabled 项（opt=9 = 10个邀请名额，需要更多魔力值）→ 拒绝
r5 = t.bonus_exchange_act(site_id=4, option=9, confirm=1)
print("disabled 项: success=%s msg=%s" % (r5.success, r5.message[:44]))
if r5.success:
    print("FAIL disabled 闸门"); fail += 1

print("\n结果：%s fail=%d" % ("PASS" if fail == 0 else "FAIL", fail))
sys.exit(1 if fail else 0)
