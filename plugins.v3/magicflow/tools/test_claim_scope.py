# -*- coding: utf-8 -*-
"""魔流 · 认领「全站纳入 + 干跑/真跑分离」离线回归（真跑，无需 MoviePilot）。

覆盖：
  (a) 站点全集 = 全部已配置站点（未收录认领能力的站也在列表里，supported=False）
  (b) sites_total / sites_supported_total / sites_skipped 计数
  (c) 同一颗种跨任务只记一次（seen 去重）
  (d) run_claim() 默认干跑：只读、mode=scan、零写
  (e) write=1 未确认 → need_confirm；确认但设置干跑 → dry_blocked
  (f) 关掉设置干跑后 write=1&confirm=1 才真写
  (g) site_id 筛选只回该站

用法：``python3 tools/test_claim_scope.py``（退出码 0=PASS / 1=FAIL）。
"""
import importlib.util, sys, types
from pathlib import Path

ROOT = Path('/vol1/@apphome/trim.openclaw/data/workspace/magicflow')
PKG = 'mf_claim_test'

def _pkg(name, path):
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name); m.__path__ = [str(path)]; sys.modules[name] = m
    return m

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT/rel)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

for n in ('app', 'app.plugins', 'app.schemas', 'app.schemas.types', 'app.sdk', 'app.sdk.logging', 'app.sdk.events'):
    m = types.ModuleType(n); sys.modules[n] = m
sys.modules['app.schemas.types'].EventType = type('EventType', (), {})
sys.modules['app.sdk.events'].eventmanager = types.SimpleNamespace()
class _Resp:
    def __init__(self, success=True, message='', data=None):
        self.success, self.message, self.data = success, message, data
sys.modules['app.schemas'].Response = _Resp
class _Logger:
    def __getattr__(self, k):
        return lambda *a, **kw: None
sys.modules['app.sdk.logging'].logger = _Logger()

_pkg(PKG, ROOT); _pkg(PKG + '.sites', ROOT/'sites')
# stubs
persist = types.ModuleType(PKG + '.persistence')
class OperationItem:
    def __init__(self, **kw): self.__dict__.update(kw)
persist.OperationItem = OperationItem; sys.modules[PKG + '.persistence'] = persist
pres = types.ModuleType(PKG + '.sites.claim_presets')
pres.preset_for = lambda d: ({'supported': True, 'min_age_days': 7, 'max_claimers': 20,
                              'per_user_cap': 1000, 'benefit': 'bonus_x2',
                              'settlement': {'cycle': 'natural_month', 'cycle_text': '每月结算',
                                             'payout_hours': 720, 'payout_multiplier': 2}}
                             if str(d).strip().lower() == 'carpt.net' else None)
sys.modules[PKG + '.sites.claim_presets'] = pres
ss = types.ModuleType(PKG + '.sitestore'); ss.slot_callbacks = lambda *a, **k: (lambda: {}, lambda **k: None)
sys.modules[PKG + '.sitestore'] = ss
common = _load(PKG + '.common', 'common.py')
for k in dir(common):
    if k.startswith('CLAIM_'):
        setattr(pres, k, getattr(common, k))
claim = _load(PKG + '.features.claim', 'features/claim.py')
ClaimMixin = claim.ClaimMixin


class Site:
    def __init__(self, sid, name, domain):
        self.id, self.name, self.domain = sid, name, domain
        self.url = 'https://' + domain + '/'

class Task:
    def __init__(self, tid, sid, sname):
        self.id, self.site_id, self.site_name = tid, sid, sname
        self.task_type, self.ti_source = 'bonus', 'publish'

class Tr:
    def __init__(self, h, title, size=1.0):
        self.hash, self.title, self.size_gb = h, title, size

class Store:
    def __init__(self, pages): self.pages = pages
    def get_torrent_pages(self, tid): return self.pages.get(tid, {})

class Fake(ClaimMixin):
    def __init__(self, sites, tasks, managed, pages, pub, ni, ledger=None, cfg=None):
        self.sites, self.tasks, self.managed = sites, tasks, managed
        self._task_configs = {t.id: t for t in tasks}
        self._store = Store(pages)
        self.pub, self.ni = pub, ni
        self._ledger = ledger or {}
        self.cfg = cfg or {'enabled': True, 'dry': True, 'sites': [], 'daily': 20, 'batch': 5,
                           'interval_sec': 0, 'min_age_days': 0, 'require_seeders': 0,
                           'min_size_gb': 0, 'exclude_zero_bonus': True}
    def _log(self, *a, **k): pass
    def _list_sites(self): return [{'id': s.id, 'name': s.name, 'domain': s.domain} for s in self.sites]
    def _get_site(self, sid): return next((s for s in self.sites if int(s.id) == int(sid)), None)
    def _claim_cfg(self): return dict(self.cfg)
    def _claim_ledger(self): return dict(self._ledger)
    def _claim_today_count(self, sid): return 0
    def _task_managed_torrents(self, task): return self.managed.get(task.id, [])
    def _task_pub_dates(self, task): return dict(self.pub)
    def _site_ni_map(self, sid, managed): return dict(self.ni)
    def _claim_bonus_map(self, task, managed, pub, ni): return {t.hash: 10.0 for t in managed}
    @staticmethod
    def _as_bool_arg(v):
        if v is None: return None
        s = str(v).strip().lower()
        if s == '': return None
        return s not in ('0', 'false', 'no', 'off', 'none')
    def _claim_journal(self, *a, **k): pass
    def _site_user_id(self, site): return 'u1'
    def _claim_one(self, *a, **k): return {'ok': True, 'status': 'ok', 'message': 'ok'}

h1 = 'a' * 40
sites = [Site(1, 'CARPT', 'carpt.net'), Site(2, '野马PT', 'https://yemapt.org/'), Site(3, '车站', 'carpt2.net')]
tasks = [Task('t-run', 1, 'CARPT'), Task('t-stop', 1, 'CARPT'), Task('t-other', 2, '野马PT')]
managed = {'t-run': [Tr(h1, 'A')], 't-stop': [Tr(h1, 'A')], 't-other': [Tr(h1, 'A')]}
pages = {'t-run': {h1: 'https://carpt.net/details.php?id=111'}}
pub = {h1: 1_600_000_000.0}  # 很久以前 → 满期
f = Fake(sites, tasks, managed, pages, pub, {h1: 5})
rec = f._claim_scan()
print('sites rows:', [(r['site_id'], r['supported'], r['claimable']) for r in rec['sites']])
assert [r['site_id'] for r in rec['sites']] == [1, 2, 3], '全站纳入：3 个站点都应在列表'
assert rec['sites_total'] == 3 and rec['sites_supported_total'] == 1, (rec['sites_total'], rec['sites_supported_total'])
assert rec['sites_skipped'] == ['野马PT', '车站'], rec['sites_skipped']
assert rec['claimable_total'] == 1, '同站两任务同一颗种只记一次'
assert len(rec['claimable']) == 1 and rec['claimable'][0]['task'] in ('t-run', 't-stop')
print('✅ 全站纳入 + 去重 OK')

# 干跑：只读，零写
r = f.run_claim()
assert r.success and r.data['mode'] == 'scan' and '只读' in r.message, r.message
# 真写未确认
r = f.run_claim(write=1)
assert not r.success and r.data.get('need_confirm'), r.message
# 真写确认但设置干跑
r = f.run_claim(write=1, confirm=1)
assert not r.success and r.data.get('dry_blocked'), r.message
# 关干跑 → 真写执行
f.cfg['dry'] = False
r = f.run_claim(write=1, confirm=1)
assert r.success and '成功 1' in r.message, r.message
print('✅ 干跑/真跑分离 OK')

# 站点筛选：单站扫描只回该站
rec2 = f._claim_scan(site_id=2)
assert rec2['sites_total'] == 1 and rec2['sites'][0]['supported'] is False
print('✅ site_id 筛选 OK')

# 域名归一：SitesHelper 有时把 domain 给成 URL，白名单按裸域名比
assert claim._claim_domain_of('https://pt.btschool.club/') == 'pt.btschool.club'
assert claim._claim_domain_of('HTTP://Tracker.Example.com:8080/x') == 'example.com'
f3 = Fake(sites, tasks, managed, pages, pub, {h1: 5}, cfg={**f.cfg, 'sites': ['yemapt.org']})
rec3 = f3._claim_scan()
assert [r['site_id'] for r in rec3['sites']] == [2], rec3['sites']
print('✅ 域名归一 + 白名单 OK')
print('ALL PASS')
