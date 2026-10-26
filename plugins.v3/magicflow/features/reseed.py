# -*- coding: utf-8 -*-
"""魔流 · reseed —— 全站辅种（本机驱动：本机已有的资源 → 去各站落户，**零下载**）。

方向与「跨站取种(crossseed)」**正好相反**：
  · 跨站取种：本机**没有**这颗资源，本站又收费 → 去他站免费下同一 Release → 下完交「全站辅种」挂回本站（**要下载**）。
  · 全站辅种（本模块）：本机**已经有文件** → 去每个目标站挂同一 Release（**零下载**：
    把目标站的 .torrent 指向源种所在目录，recheck 通过即做种）。

Master 2026-09-30 定稿口径：
  · 挂上去**只给身份**（`魔流-<站点>-静默-<身份>`），**不**另造「辅种」职务；
    之后由该站点的任务照常让它上班（魔力/刷流）。
  · **身份继承资源**：按文件特征码并进资源组，组的身份是「资源」→ 直接贴「静默-资源」，
    **不经过「新」的观察期**（本地已有且认证过的东西没什么可观察的）。
  · 零下载 ⇒ 不产生下载记录 ⇒ **没有 H&R**（不欠工时、不进隔离区）。
  · 校验只是**动作**：暂停加入 → recheck → 通过才做种，不通过自动撤销（`add_torrent_reuse`）。
  · IYUU 云端只当「发现」：必须拉目标站 .torrent 比对**文件列表特征码**才算数。

限速/风控：共用站点 PV 账本（`_pv_allow`/`_pv_spend`），每站每天有挂种上限，
每轮小批量、站间轮转；取种由下载器 `fetch_torrent_bytes` 发出（撞站点流控即整站让路）。
"""

import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote


from sqlalchemy import select

from app.sdk.logging import logger
from app.schemas import Response

from ..downloader_ops import TorrentFetchFlowControl, TorrentFetchGone
from ..fingerprint import fingerprint, info_hash
from ..iyuu_cloud import (
    build_download_url,
    harvest_passkey,
    resolve_link_vars,
)
from ..tags import STATE_SILENT, SUB_NEW, SUB_PLAIN, SUB_RESOURCE, tag_for
from ..sitestore import slot_callbacks
from ..kvstore import cache_get, cache_set
from .reuse import _reuse_local_complete


from ..common import (
    CACHE_TTL_COUNTER,
    CACHE_TTL_REPORT,
    RESEED_BATCH,
    RESEED_CLOUD_BACKOFF_S,
    RESEED_CLOUD_KEY,
    RESEED_CLOUD_TTL,
    RESEED_CFG_KEY,
    RESEED_DAILY_PER_SITE,
    RESEED_DAY_KEY,
    RESEED_DOWNSHIFT_MIN_SIZE_GB,
    RESEED_FAIL_TTL,
    RESEED_LEDGER_KEY,
    RESEED_MIN_SIZE_GB,
    RESEED_MISS_TTL,
    RESEED_OK_TTL,
    RESEED_PASSKEY_KEY,
    SILENT_HR_SPLIT_ENABLED,
    mask_long_tokens,
    mask_url_secrets,
)


def _rlog(msg: str, level: str = "info") -> None:
    """本文件自有的「魔流:」日志出口（与 `self._log` 输出格式一致）。

    ★ 19.7.92：本文件新增的诊断日志**不走 `self._log`** —— 那个方法定义在 features/core.py，
    跨文件 `self._` 互调会被棘轮护栏（tools/check_self_calls.py）判为「新增隐式耦合」。
    `logger` 本文件已直接 import，输出格式与 `self._log` 完全相同（`魔流:` 前缀）。
    """
    getattr(logger, level if hasattr(logger, level) else "info")(f"魔流:{msg}")


# ---------------------------------------------------------------------------
# 特殊站（详情页抓链）—— 与隔壁 IYUU 插件 `__is_special_site` / `_torrent_xpaths` 同口径
#   模板里出现 `hash=`/`authkey=`（HDDolby 的 `download_page` 就是
#   `download.php?id={}&uid={uid}&hash={hash}`）说明链上带**每颗种一次性令牌**：
#   那个 `{hash}` 不是账号级配置，而是站点 RSS/详情页里的 per-tid 令牌，
#   拼不出来 ⇒ 只能带 cookie 去详情页把它抠出来。
# ---------------------------------------------------------------------------
_SPECIAL_DL_MARKERS = ("hash=", "authkey=")
_SPECIAL_DL_DOMAINS = ("hdchina.org", "hdsky.me", "hdcity.in", "totheglory.im")
# 详情页里下载链的抠法（顺序即优先级；与隔壁 IYUU 插件 `_torrent_xpaths` 逐条一致）
_DETAIL_LINK_XPATHS = (
    "//form[contains(@action, 'download.php?id=')]/@action",
    "//a[contains(@href, 'download.php?hash=')]/@href",
    "//a[contains(@href, 'download.php?id=')]/@href",
    "//a[@class='index'][contains(@href, '/dl/')]/@href",
)


def _is_special_dl(template: str, domain: str) -> bool:
    """是否「特殊站」（链带一次性令牌 → 必须抓详情页，不能拼模板）。"""
    t = str(template or "")
    if any(_m in t for _m in _SPECIAL_DL_MARKERS):
        return True
    d = str(domain or "").strip().lower()
    return any(_d in d for _d in _SPECIAL_DL_DOMAINS)


# ★ 2026-10-20：缺链（nourl）在旧版本里一律记 `miss` = 冻结 30 天，现场实测把
#   `无下载链模板/缺口令` 14 条（含 HDDolby 4 条）冻到 2026-11-19 —— 而这批原因
#   全是**配置/站点侧可修复**的缺口（补 cookie、站点换模板、CF 盾放行），且这条路径
#   **不花 PV**（只花一次模板拼链/详情页请求）。现在 nourl 一律写 `fail`（1 天），
#   读账本时把旧记录的这类 miss 按 fail 口径重算 TTL（超 1 天直接放行，无需清缓存）。
_LEGACY_NOURL_NOTE_HEADS = (
    "无下载链模板", "详情页未取到下载链", "特殊站需 cookie", "特殊站无 cookie",
    "详情页被拒", "详情页没有下载链",
)


def _is_legacy_nourl(note: str) -> bool:
    """旧账本里由「缺链」写入的 miss 备注（按新口径应视为 fail）。"""
    n = str(note or "")
    return any(n.startswith(h) for h in _LEGACY_NOURL_NOTE_HEADS)


def _chain_usable(entry: Dict[str, Any], conn: Dict[str, Any]) -> bool:
    """该站现在能不能取到链：特殊站（模板带一次性令牌）**需要 cookie**。

    ★ 2026-10-20 Master 口径「不让用就不辅种他了，保证大部分站好了」：
    特殊站没 cookie 时走详情页是**必然失败**（无 cookie 连详情页都不发请求），排进本轮只会白占
    一个 batch 名额（不吃 PV，但挤掉别的站）→ 在**选对阶段**就把它排除，不进 `plan`。
    补上 cookie 后下一轮即刻恢复（无需改配置/改代码）。

    ★ 2026-10-20（方案 3）：返回 False 只代表「**cookie 这条腿**不通」——特殊站没有 cookie 时
    仍可走目录缓存里的 `downhash`（见 `_reseed_cache_link`），所以 `_reseed_pairs` 对这个
    False 还要再查一次「该 tid 有没有缓存凭据」，有就照排。
    """
    tpl = str((entry or {}).get("download_page") or "")
    dom = str((entry or {}).get("base_url") or "") or str((conn or {}).get("domain") or "")
    if not _is_special_dl(tpl, dom):
        return True
    return bool(str((conn or {}).get("cookie") or ""))


class HdQuotaExhausted(Exception):
    """HDDolby API 小时限额耗尽（HTTP 403 / status 30005「Limit of api call per hour」）。

    实测该限额远低于错误码字面值：本机两轮目录爬取（72 + 150 次调用）叠加早前的
    维度探测后即被打满，站点回「please wait for four hour」。**必须显式识别并立即停手**，
    否则后续调用只会静默返回空页（`_hd_search_flat` 非 200 一律回 `[]`），
    既拿不到数据、又把限额继续耗在无意义请求上，还会挤掉辅种取种要用的配额。
    """


# 命中配额后静默 4 小时（站点原话「please wait for four hour」）再试。
HD_QUOTA_COOLDOWN_S = 4 * 3600
HD_QUOTA_BLOCK_KEY = "reseed_catalog_quota_block_until"

# ★ HDDolby 取种链（2026-10-20 真机定性）：
#   · 官方 API（`/api/v1/torrent/download`）回的 .torrent **不能做种**：announce 只给
#     `?passkey=<账号明文口令>`（**缺主机名**），站点 tracker 实测拒绝（`torrent error B`）；
#   · 模板 `download.php?id={}&uid={uid}&hash={hash}` 里的 `{hash}` 是**每颗种一次性令牌**，
#     拼不出来 ⇒ 按特殊站走「详情页抓链」；
#   · 详情页要登录态 + 过 Cloudflare 盾（本机匿名实测首页/详情页/RSS 全 403 `Just a moment`）
#     ⇒ **没有 cookie 就取不到链**（无 cookie 时不发请求，直接按缺链分类记账）；
#   · 老式 `download.php?id=&passkey=` 已被站点废弃（实测回 `Old Passkey no Support!`）。
#   ★ 2026-10-20（方案 3，Master 拍板）：**特殊站优先用目录缓存里的 `downhash` 免登录取链**
#   —— 搜索 API / RSS 每行自带 `downhash`（每 tid 唯一、实测不随时间的推移失效），
#   拼 `download.php?id=<tid>&downhash=<dh>` 即得**带正确主机名**的 .torrent
#   （announce = `https://t.hddolby.com/announce.php?passkey=<downhash>`）。
#   这就是 MP 自带 spider 的同款链（`hddolby.py::__get_download_url`），**不需要 cookie**。
#   因此取链口径按「有没有 cookie」分两条腿：
#     · 无 cookie：`mf_rss.downhash` → `download.php?id=&downhash=`（缓存没这颗就本轮不排）；
#     · 有 cookie：与隔壁 IYUU 插件同口径，带 cookie 抓 `details.php?id=<tid>&hit=1`
#       → `_DETAIL_LINK_XPATHS` 抠一次性链（见 `_reseed_details_link`）。
#   `downhash` 之外的目录字段仍只做「体积预筛」，不拿 `download_url` 当链（那是抓取时的快照）。
class ReSeedMixin:
    """全站辅种功能集。"""

    # ------------------------------------------------------------------ 配置
    def _reseed_cfg(self) -> Dict[str, Any]:
        """当前配置：插件配置(models)打底，plugin data 覆盖（便于接口临时开关/干跑）。"""
        cfg = {
            "enabled": bool(getattr(self, "_reseed_enabled", False)),
            "sites": list(getattr(self, "_reseed_sites", None) or []),
            "daily": int(getattr(self, "_reseed_daily", RESEED_DAILY_PER_SITE) or RESEED_DAILY_PER_SITE),
            "batch": int(getattr(self, "_reseed_batch", RESEED_BATCH) or RESEED_BATCH),
            "min_size_gb": float(getattr(self, "_reseed_min_size_gb", RESEED_MIN_SIZE_GB) or 0.0),
            "dry": bool(getattr(self, "_reseed_dry", False)),
        }
        raw = self.get_data(RESEED_CFG_KEY)
        if isinstance(raw, dict):
            for k in list(cfg.keys()):
                if k in raw:
                    cfg[k] = raw[k]
        return cfg

    def set_reseed_cfg(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """写 plugin data 覆盖项（接口用；传空字典=回到插件配置）。"""
        raw = self.get_data(RESEED_CFG_KEY)
        cur = dict(raw) if isinstance(raw, dict) else {}
        for k, v in (patch or {}).items():
            if k in ("enabled", "dry"):
                cur[k] = bool(v)
            elif k == "sites":
                cur[k] = [str(x).strip() for x in (v or []) if str(x).strip()]
            elif k == "daily":
                cur[k] = max(0, int(v or 0))
            elif k == "batch":
                cur[k] = max(1, int(v or 1))
            elif k == "min_size_gb":
                cur[k] = max(0.0, float(v or 0.0))
        self.save_data(key=RESEED_CFG_KEY, value=(cur if patch else {}))
        # ★ 开关可能翻转 → 立刻让宿主重建插件服务（enabled=true 才会注册 ReSeed worker）
        try:
            self._refresh_scheduler()
        except Exception:  # noqa: BLE001
            pass
        return self._reseed_cfg()

    # ------------------------------------------------------------------ 账本
    def _reseed_ledger(self) -> Dict[str, Any]:
        """已试过的「站点:目标hash」→ 状态（过期即丢；成功不靠它去重，靠本机实况）。"""
        _get, _save = slot_callbacks(self, RESEED_LEDGER_KEY)
        raw = _get()
        if not isinstance(raw, dict):
            return {}
        now = time.time()
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if not isinstance(v, dict):
                continue
            st = str(v.get("st") or "")
            if st == "miss" and _is_legacy_nourl(str(v.get("note") or "")):
                # ★ 2026-10-20：缺链类旧记录按新口径（fail=1 天）重算 TTL——
                #   本次不做数据手术，读侧兼容即可（超 1 天的直接放行重试）。
                st = "fail"
                v = dict(v, st=st)
            age = now - float(v.get("ts") or 0)
            if st == "miss" and age > RESEED_MISS_TTL:
                continue
            if st == "fail" and age > RESEED_FAIL_TTL:
                continue
            if st == "ok" and age > RESEED_OK_TTL:
                # ★ 19.0.0：ok 记录只是历史参考（去重靠本机实况）→ 90 天后过期
                continue
            out[k] = v
        return out

    def _reseed_ledger_put(self, key: str, st: str, note: str = "") -> None:
        if not key:
            return
        led = self._reseed_ledger()
        rec: Dict[str, Any] = {"st": st, "ts": time.time(), "note": note[:160]}
        if st == "ok":
            # ★ 19.0.0：生命周期三列（mf_reseed.alive/last_seen/seen_by）
            rec["alive"] = True
            rec["last_seen"] = rec["ts"]
            rec["seen_by"] = "reseed"
        led[key] = rec
        if len(led) > 4000:  # 防无限膨胀
            for k in sorted(led, key=lambda x: float(led[x].get("ts") or 0))[: len(led) - 4000]:
                led.pop(k, None)
        try:
            slot_callbacks(self, RESEED_LEDGER_KEY)[1](value=led)
        except Exception:  # noqa: BLE001
            pass

    # --------------------------------------------------------------- 每日计数
    def _reseed_day(self) -> Dict[str, Any]:
        today = time.strftime("%Y-%m-%d", time.localtime())
        raw = cache_get(self, "reseed", RESEED_DAY_KEY, CACHE_TTL_COUNTER)
        if not isinstance(raw, dict) or str(raw.get("day") or "") != today:
            raw = {"day": today, "sites": {}}
        if not isinstance(raw.get("sites"), dict):
            raw["sites"] = {}
        return raw

    def _reseed_day_bump(self, sid: int) -> None:
        day = self._reseed_day()
        key = str(int(sid))
        day["sites"][key] = int(day["sites"].get(key) or 0) + 1
        try:
            cache_set(self, "reseed", RESEED_DAY_KEY, day, CACHE_TTL_COUNTER)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 站点/口令表
    def _reseed_mp_sites(self) -> List[Dict[str, Any]]:
        """MoviePilot 已配置站点列表 [{id,name,domain}]（SiteOper 优先，回落 SitesHelper）。"""
        out: List[Dict[str, Any]] = []
        try:
            from app.db.oper.site import SiteOper
            for site in SiteOper().list() or []:
                dom = str(getattr(site, "domain", "") or "").strip().lower()
                out.append({"id": getattr(site, "id", None),
                            "name": getattr(site, "name", "") or dom, "domain": dom})
        except Exception:  # noqa: BLE001
            out = []
        if not out:
            try:
                out = list(self._list_sites() or [])
            except Exception:  # noqa: BLE001
                out = []
        return out

    def _reseed_site_map(self) -> Dict[int, Dict[str, Any]]:
        """IYUU sid → {sid, name, domain, site_id}（只含我们启用、且有 IYUU sid 的站）。"""
        out: Dict[int, Dict[str, Any]] = {}
        cli = getattr(self, "_iyuu_client", None)
        if cli is None:
            return out
        rows = self._reseed_mp_sites()
        cfg = self._reseed_cfg()
        allow = {str(x).strip().lower() for x in (cfg.get("sites") or []) if str(x).strip()}
        for row in rows:
            dom = str(row.get("domain") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            if allow and dom not in allow and name.lower() not in allow:
                continue
            try:
                sid = cli.sid_by_domain(dom)
            except Exception:  # noqa: BLE001
                sid = None
            if not sid:
                continue
            out[int(sid)] = {"sid": int(sid), "name": name or dom, "domain": dom,
                             "site_id": row.get("id")}
        if not out:
            self._log(f"全站辅种:站点映射为空（rows={len(rows)}, 白名单={sorted(allow)[:6]}）", "warning")
        return out

    def _reseed_site_conn(self, sid: int) -> Dict[str, Any]:
        """站点的连接信息（cookie/ua/url/apikey/token），从 MP 站点对象取。"""
        site = None
        cli = getattr(self, "_iyuu_client", None)
        rows = self._reseed_mp_sites()
        for row in rows:
            dom = str(row.get("domain") or "").strip().lower()
            try:
                if cli is not None and int(cli.sid_by_domain(dom) or 0) == int(sid):
                    site = row
                    break
            except Exception:  # noqa: BLE001
                continue
        obj = self._get_site(site.get("id")) if site else None
        if obj is None:
            return {}
        url = str(getattr(obj, "url", "") or f"https://{getattr(obj, 'domain', '')}").rstrip("/")
        return {
            "site_id": site.get("id"),
            "domain": str(getattr(obj, "domain", "") or site.get("domain") or "").strip().lower(),
            "cookie": getattr(obj, "cookie", None),
            "ua": str(getattr(obj, "ua", None) or "").strip() or None,
            "url": url,
            "apikey": str(getattr(obj, "apikey", "") or ""),
            "token": str(getattr(obj, "token", "") or ""),
        }

    def _reseed_iyuu_entry(self, sid: int) -> Dict[str, Any]:
        # 本地缓存优先（IYUU 限流时也能拼链）
        try:
            cache = self.get_data("iyuu_sites_cache")
            if isinstance(cache, dict):
                hit = cache.get(str(int(sid)))
                if isinstance(hit, dict) and hit.get("download_page"):
                    return hit
        except Exception:  # noqa: BLE001
            pass
        cli = getattr(self, "_iyuu_client", None)
        if cli is None:
            return {}
        try:
            for item in (cli.sites() or {}).values():
                if str(item.get("id") or "") == str(int(sid)):
                    return item
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _reseed_passkey(self, sid: int, base_url: str, is_https: int, site_id: int,
                        cookie: Any) -> str:
        """站点 passkey：抓浏览页抽「密钥」（两种形态）→ 落缓存，后续直接用模板拼链。"""
        cache = slot_callbacks(self, RESEED_PASSKEY_KEY)[0]()
        cache = dict(cache) if isinstance(cache, dict) else {}
        key = str(int(sid))
        if cache.get(key):
            return str(cache[key])
        # ★ 19.7.37：passkey 唯一来源 = 凭据中心（site_creds）。
        #   旧 IYUU 设置里的 passkey 做一次懒迁移，之后不再重复填写。
        try:
            _cred_pk = str(self._cred_get(int(site_id), "passkey") or "").strip()
        except Exception:  # noqa: BLE001
            _cred_pk = ""
        if not _cred_pk:
            # ★ 19.7.72：IYUU sid 与 MP site_id 不是一套编号
            #   （HDDolby：IYUU 105 / MP 17）——直查不到就按域名回查 MP 站点 id。
            try:
                _d = str(base_url or "").strip().lower()
                if _d.startswith("http"):
                    _d = _d.split("://", 1)[1]
                _d = _d.split("/", 1)[0]
                _d2 = _d[4:] if _d.startswith("www.") else _d
                _mp_sid = (self._site_id_by_domain(_d2) or self._site_id_by_domain(_d)) if _d else 0
                if _mp_sid and int(_mp_sid) != int(site_id):
                    _cred_pk = str(self._cred_get(int(_mp_sid), "passkey") or "").strip()
            except Exception:  # noqa: BLE001
                _cred_pk = ""
        if not _cred_pk:
            try:
                _dom = str(base_url or "").strip().lower()
                if _dom.startswith("http"):
                    _dom = _dom.split("://", 1)[1]
                _dom = _dom.split("/", 1)[0]
                _legacy = (getattr(self, "_iyuu_sites", {}) or {}).get(_dom) or {}
                _cred_pk = str(_legacy.get("passkey") or "").strip()
                if _cred_pk:
                    self.save_cred(site_id=int(site_id), field="passkey", value=_cred_pk)
            except Exception:  # noqa: BLE001
                _cred_pk = ""
        if _cred_pk:
            cache[key] = _cred_pk
            try:
                slot_callbacks(self, RESEED_PASSKEY_KEY)[1](value=cache)
            except Exception:  # noqa: BLE001
                pass
            return _cred_pk
        got = ""
        c = self._collect_ref()
        biz = str(base_url or "").strip().strip("/")
        if biz.startswith("http"):
            biz = biz.split("://", 1)[1]
        scheme = "https" if int(is_https or 0) in (1, 2) else "http"
        if c is not None and int(site_id or 0) and biz:
            try:
                from ..collect import parse_passkey  # noqa: WPS433
            except Exception:  # noqa: BLE001
                parse_passkey = None  # noqa: N806
            for path in ("torrents.php", "usercp.php"):
                if parse_passkey is None:
                    break
                try:
                    res = c.http.text(int(site_id), f"{scheme}://{biz}/{path}", kind="passkey")
                except Exception:  # noqa: BLE001
                    continue
                if not getattr(res, "ok", False):
                    continue
                got = str((parse_passkey(getattr(res, "text", "")) or {}).get("passkey") or "")
                if got:
                    break
        if not got and c is not None and int(site_id or 0):
            try:
                got = str((c.site(int(site_id)).passkey() or {}).get("passkey") or "")
            except Exception as err:  # noqa: BLE001
                self._dbg(f"全站辅种:站点 {sid} 取 passkey 失败 {err}")
        if got:
            cache[key] = got
            try:
                slot_callbacks(self, RESEED_PASSKEY_KEY)[1](value=cache)
            except Exception:  # noqa: BLE001
                pass
        else:
            self._dbg(f"全站辅种:站点 {sid} 没抽到 passkey（base={biz}）")
        return got

    def refresh_iyuu_sites_cache(self) -> Dict[str, Any]:
        """拉一次 IYUU 站点表并落本地（按 sid 建索引）。"""
        cli = getattr(self, "_iyuu_client", None)
        if cli is None:
            return {"ok": False, "error": "IYUU 未启用"}
        try:
            sites = cli.sites() or {}
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": str(err)}
        out = {}
        for item in (sites.values() if isinstance(sites, dict) else sites):
            try:
                out[str(int(item.get("id")))] = item
            except Exception:  # noqa: BLE001
                continue
        try:
            self.save_data(key="iyuu_sites_cache", value=out)
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": f"保存失败 {err}"}
        return {"ok": True, "count": len(out)}

    def _reseed_download_url(self, sid: int, tid: Any,
                             note: Optional[Dict[str, str]] = None) -> Optional[str]:
        """目标站种子下载链（与隔壁 IYUU 插件同口径，特殊站点多一条免登录腿）。

        ① API 鉴权站（馒头等）→ 站点 API 签名直链（`genDlToken`/`api_dl_token`）；
        ② **特殊站**（模板带 `hash=`/`authkey=`，如 HDDolby）：
           · **没有 cookie** → 目录缓存 `mf_rss.downhash` 拼 `download.php?id=&downhash=`
             （MP 自带 spider 同款链，免登录；见 `_reseed_cache_link`）；
           · **有 cookie** → 带 cookie 抓详情页，xpath 抠**每颗种一次性**的链
             （见 `_reseed_details_link`）；
        ③ 普通站 → 云端模板 + passkey 拼链。

        `note` 非空时写入失败原因（`note["why"]`）与实际走的腿（`note["chain"]`：
        特殊站 `cache`（缓存 downhash）/`details`（详情页抠链）），供台账分型记账与排查。
        """
        def _why(msg: str) -> None:
            if note is not None:
                note["why"] = msg

        conn = self._reseed_site_conn(sid)
        if not conn:
            _why("站点连接信息缺失")
            return None
        site_id = int(conn.get("site_id") or 0)
        c = self._collect_ref()
        # ① API 鉴权站（馒头/叶PT）：`genDlToken`，不用网页 cookie
        if c is not None and site_id:
            try:
                if c.is_api_site(site_id):
                    r = c.site(site_id).api_dl_token(tid)
                    url = str((r or {}).get("url") or "")
                    if url:
                        return url
                    _why(f"API 站取直链失败：{(r or {}).get('error') or '无返回'}")
                    self._dbg(f"全站辅种:API 站 {sid} 取直链失败 {(r or {}).get('error')}")
                    return None
            except Exception as err:  # noqa: BLE001
                _why(f"API 站取直链异常：{err}")
                self._dbg(f"全站辅种:API 站 {sid} 取直链异常 {err}")
                return None
        # ①.5 自有模板优先（存 creds.template，支持 {id}/{passkey}/{uid}/{downhash}）
        own_tpl = self._cred_get(site_id, "template")
        if own_tpl:
            _pk = self._cred_get(site_id, "passkey")
            _uid = self._cred_get(site_id, "uid")
            _dh = self._cred_get(site_id, "downhash")
            u = own_tpl
            for k, v in (("passkey", _pk), ("uid", _uid), ("downhash", _dh),
                         ("torrent_id", str(tid)), ("id", str(tid))):
                u = u.replace("{" + k + "}", str(v or ""))
            if u.startswith("http"):
                return u
        # ② 云端模板
        entry = self._reseed_iyuu_entry(sid)
        template = str(entry.get("download_page") or "").strip()
        base_url = str(entry.get("base_url") or "").strip()
        is_https = int(entry.get("is_https") or 0)
        dom = str(conn.get("domain") or base_url or "").strip().lower()
        # ②-特殊站：链带一次性令牌（`hash=`/`authkey=`）⇒ 拼不出来。
        #   ★ 方案 3（2026-10-20）：没有 cookie 时先试目录缓存里的 `downhash`
        #   （MP 自带 spider 同款链，免登录、零额外请求）；没有缓存凭据就本轮不排。
        if _is_special_dl(template, dom):
            if not str(conn.get("cookie") or "").strip():
                cached = self._reseed_cache_link(site_id, tid, conn)
                if cached:
                    if note is not None:
                        note["chain"] = "cache"
                    return cached
                # 没有 cookie、缓存也没有这颗 → 交给详情页分支给出统一口径的原因（不发请求）
                return self._reseed_details_link(sid, site_id, tid, conn, entry, note=note)
            if note is not None:
                note["chain"] = "details"
            return self._reseed_details_link(sid, site_id, tid, conn, entry, note=note)
        if not template or not base_url:
            # 直连兜底：站点自己的 download.php（有 cookie/passkey 就够）
            _pk0 = self._cred_get(site_id, "passkey")
            _base0 = str(conn.get("url") or "").rstrip("/")
            if _pk0 and _base0:
                return f"{_base0}/download.php?id={tid}&passkey={_pk0}"
            _why("无下载链模板/缺口令")
            return None
        user_fill: Dict[str, str] = {}
        try:
            uf = (getattr(self, "_iyuu_sites", {}) or {}).get(dom) or {}
            if isinstance(uf, dict):
                user_fill.update({k: str(v) for k, v in uf.items() if isinstance(v, str)})
        except Exception:  # noqa: BLE001
            pass
        pk = user_fill.get("passkey") or self._reseed_passkey(
            sid, base_url, is_https, site_id, conn.get("cookie"))
        if pk:
            user_fill["passkey"] = pk
        variables = resolve_link_vars(
            dom, user_fill,
            {"apikey": conn.get("apikey") or "", "token": conn.get("token") or ""},
            cookie="", base_url="", is_https=is_https,
        )
        url = build_download_url(template, base_url, is_https, tid, variables)
        if url:
            return url
        # 模板拼不出（缺 uid/downhash 等）→ 站点直连兜底
        _pk1 = user_fill.get("passkey") or self._cred_get(site_id, "passkey")
        _base1 = str(conn.get("url") or "").rstrip("/")
        if _pk1 and _base1:
            return f"{_base1}/download.php?id={tid}&passkey={_pk1}"
        missing = [n for n in re.findall(r"\{([a-zA-Z0-9_]+)\}", template) if not variables.get(n)]
        _why(f"模板缺变量 {','.join(missing)} 且无兜底口令" if missing else "模板拼链失败且无兜底口令")
        return None

    def _reseed_cache_link(self, site_id: int, tid: Any,
                           conn: Dict[str, Any]) -> Optional[str]:
        """特殊站的免登录取链：用目录缓存 `mf_rss` 里该 tid 的 `downhash` 拼链。

        与 MP 自带 spider 完全同款（`hddolby.py::__get_download_url` →
        ``download.php?id=<tid>&downhash=<downhash>``）：`downhash` 是站点列表/搜索/RSS
        随种下发的**每 tid 唯一**下载令牌（形如 ``rand x ts x uid x tid x md5``），
        实测**不随时间的推移失效**（最老 12.6h 仍 200），且回包里的 announce 带正确主机名
        （``https://t.hddolby.com/announce.php?passkey=<downhash>``）——这条链路**不需要 cookie**。

        命中返回绝对链；没有缓存凭据返回 `None`（调用方据此按缺链跳过，不发无谓请求）。
        """
        if not site_id:
            return None
        try:
            row = self._rss_lookup(site_id, tid) or {}
        except Exception:  # noqa: BLE001
            return None
        base = str((conn or {}).get("url") or "").strip().rstrip("/")
        dh = str(row.get("downhash") or "").strip()
        if dh and base:
            return (f"{base}/download.php?id={quote(str(tid), safe='')}"
                    f"&downhash={quote(dh, safe='')}")
        # 目录里存的是抓取时快照的直链（RSS enclosure）→ 只认绝对链，相对链补站点前缀
        raw = str(row.get("download_url") or "").strip()
        if raw:
            if raw.startswith("http"):
                return raw
            if base:
                return f"{base}/{raw.lstrip('/')}"
        return None

    def _reseed_details_link(self, sid: int, site_id: int, tid: Any,
                             conn: Dict[str, Any], entry: Dict[str, Any],
                             note: Optional[Dict[str, str]] = None) -> Optional[str]:
        """特殊站：带 cookie 抓详情页，用 xpath 抠一次性下载链（与隔壁 IYUU 插件同口径）。

        · 详情页地址取云端 `details_page`（缺省 `details.php?id={}`），补 `&hit=1`；
        · **没有 cookie 时不发请求**（站点要登录态 / 过 Cloudflare 盾，发了也是 403）；
        · 抠不到链时把原因写进 `note["why"]`（HTTP 状态 / xpath 未命中）。
        """
        def _why(msg: str) -> None:
            if note is not None:
                note["why"] = msg

        cookie = str(conn.get("cookie") or "").strip()
        base = str(conn.get("url") or "").strip().rstrip("/")
        if not base:
            _why("站点地址缺失，无法抓详情页")
            return None
        if not cookie:
            # ★ 方案 3：无 cookie 时，唯一还能走的免登录腿是目录缓存里的 downhash
            #   （调用方 `_reseed_download_url` 已先试过）——走到这里说明缓存也没有这颗。
            _why("特殊站无 cookie 且目录缓存无该种 downhash（取链不可用）")
            self._dbg(f"全站辅种:{sid} 特殊站 tid={tid} 无 cookie、无缓存 downhash，跳过")
            return None
        dp = str(entry.get("details_page") or "").strip() or "details.php?id={}"
        path = dp.replace("{}", str(tid)) if "{}" in dp else f"details.php?id={tid}"
        if not path.startswith("http"):
            path = f"{base}/{path.lstrip('/')}"
        if "hit=" not in path:
            path += ("&" if "?" in path else "?") + "hit=1"
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433
            res = RequestUtils(cookies=cookie, ua=conn.get("ua"),
                               referer=f"{base}/").get_res(url=path)
        except Exception as err:  # noqa: BLE001
            _why(f"详情页请求异常：{err}")
            return None
        status = getattr(res, "status_code", None) or 0
        text = str(getattr(res, "text", "") or "")
        if status not in (200, 500) or not text:
            if status in (401, 403):
                _why(f"详情页被拒（HTTP {status}，cookie 未过盾/已失效）")
            else:
                _why(f"详情页不可用（HTTP {status or '?'}）")
            self._dbg(f"全站辅种:{sid} 特殊站 tid={tid} 详情页 HTTP {status or '?'}，抠不到链")
            return None
        try:
            from lxml import etree  # noqa: WPS433
            html = etree.HTML(text)
        except Exception as err:  # noqa: BLE001
            _why(f"详情页解析失败：{err}")
            return None
        if html is None:
            _why("详情页解析失败（HTML 为空）")
            return None
        for xp in _DETAIL_LINK_XPATHS:
            try:
                got = html.xpath(xp)
            except Exception:  # noqa: BLE001
                continue
            if not got:
                continue
            link = str(got[0] or "").strip()
            if not link:
                continue
            if link.startswith("http"):
                return link
            return f"{base}/{link.lstrip('/')}"
        _why(f"详情页没有下载链（HTTP {status}，xpath 全未命中）")
        return None

    # ------------------------------------------------------------ 种子目录缓存
    # ★ 派生缓存 `mf_rss`：把每站浏览/搜索/RSS 拉到的最新种子目录沉淀成可命中的
    #    <<tid → download_url/downhash>> 表。治「RSS 只给最新 N 条 / API 下载每小时
    #   限额」这类站的辅种取种瓶颈：命中缓存的直接用（零 API 成本），不中才走现有
    #   API/模板链。增量填充（方案 A）：每轮在配额内翻几页，连续两页全重复即认为
    #   目录已齐，多轮累积成完整历史。
    def _rss_db(self) -> Optional["Any"]:
        """惰性取 DB 句柄（离线/未装配 → None，静默跳过缓存层）。"""
        try:
            from .. import db as _db  # noqa: WPS433

            return _db
        except Exception:  # noqa: BLE001
            return None

    def _rss_upsert(self, rows: List[Dict[str, Any]]) -> int:
        """幂等写入种子目录缓存（``(site_id, tid)`` 主键，merge upsert）。

        ``rows``：[{"site_id","tid","title","size","downhash","download_url","pub_at"}]。
        返回写入行数；失败静默（缓存层不允许阻断主链路）。
        """
        db = self._rss_db()
        if db is None:
            return 0
        try:
            now = time.time()
            n = 0
            with self.get_database().session() as sess:
                for r in rows or []:
                    sid = int(r.get("site_id") or 0)
                    tid = str(r.get("tid") or "").strip()
                    if not sid or not tid:
                        continue
                    sess.merge(db.RssRow(
                        site_id=sid,
                        tid=tid,
                        title=str(r.get("title") or "")[:500] or None,
                        size=float(r.get("size") or 0.0) if r.get("size") is not None else None,
                        downhash=str(r.get("downhash") or "")[:200] or None,
                        download_url=str(r.get("download_url") or "")[:800] or None,
                        pub_at=float(r.get("pub_at") or 0.0) or None,
                        created=float(r.get("pub_at") or now) or now,
                        updated=now,
                    ))
                    n += 1
                sess.commit()
            return n
        except Exception:  # noqa: BLE001
            self._dbg(f"全站辅种:种子目录缓存写入失败（{rows.__len__() if rows else 0} 行）")
            return 0

    def _rss_lookup(self, site_id: int, tid: Any) -> Dict[str, Any]:
        """查种子目录缓存里目标 tid 的下载凭据。

        命中返回 ``{downhash, download_url, title, pub_at, size}``（``size`` 单位 GB，
        ★ 19.7.92 增返：供目标体积预筛与排查，见 ``_rss_sizes``）。
        """
        db = self._rss_db()
        if db is None:
            return {}
        try:
            with self.get_database().session() as sess:
                r = sess.execute(
                    select(db.RssRow).where(
                        db.RssRow.site_id == int(site_id),
                        db.RssRow.tid == str(tid or "").strip(),
                    )
                ).scalars().first()
            if r is None:
                return {}
            return {
                "downhash": str(r.downhash or "") or None,
                "download_url": str(r.download_url or "") or None,
                "title": str(r.title or "") or None,
                "pub_at": float(r.pub_at or 0.0) or None,
                "size": float(r.size or 0.0) or None,
            }
        except Exception:  # noqa: BLE001
            return {}

    def _rss_tids(self, site_id: int) -> set:
        """该站目录缓存里**带取链凭据**的 tid 集合（`downhash` 或 `download_url`）。

        ★ 19.7.92（方案 3）新增：特殊站没有 cookie 时，选对阶段要判断「这颗有没有缓存
        downhash 能免登录取链」。逐对查库会打出上千次单行查询，所以按站一次取回 tid 集合，
        选对循环里只查内存 set（HDDolby 实测 ~14K 行，一次性 set 开销可忽略）。

        ``site_id`` 是 **MP 站点 id**（= `mf_rss.site_id` 的口径），不是 IYUU sid。
        """
        db = self._rss_db()
        if db is None or not site_id:
            return set()
        try:
            with self.get_database().session() as sess:
                rows = sess.execute(
                    select(db.RssRow.tid, db.RssRow.downhash, db.RssRow.download_url).where(
                        db.RssRow.site_id == int(site_id),
                    )
                ).all()
        except Exception:  # noqa: BLE001
            return set()
        out: set = set()
        for tid, dh, du in rows:
            if str(tid or "").strip() and (str(dh or "").strip() or str(du or "").strip()):
                out.add(str(tid).strip())
        return out

    def _rss_sizes(self, site_id: int, tids: List[Any]) -> Dict[str, float]:
        """批取目录缓存里一批 tid 的体积（GB）→ ``{tid: size}``。

        ★ 19.7.92 新增：目标体积预筛要在**取种之前**判体积，逐行 `_rss_lookup` 会打出
        上千次查询（实测候选 11083 行），所以按站一次 IN 查询（每站 ≤1 次，500/批）。
        返回空 dict 的语义是「本站没有体积数据」→ 调用方据此跳过滤（不筛）。

        ``site_id`` 是 **MP 站点 id**（= `mf_rss.site_id` 的口径）；调用方必须先把 IYUU sid
        换算成 `site_map[sid]["site_id"]` 再传进来 —— 直接传 IYUU sid 会恒查不到数据、
        预筛静默失效（2026-10-20 实测：HDDolby IYUU sid=105 / MP site_id=17）。
        """
        db = self._rss_db()
        if db is None or not tids:
            return {}
        out: Dict[str, float] = {}
        try:
            _ids = [str(t or "").strip() for t in tids if str(t or "").strip()]
            with self.get_database().session() as sess:
                for i in range(0, len(_ids), 500):
                    chunk = _ids[i:i + 500]
                    rows = sess.execute(
                        select(db.RssRow.tid, db.RssRow.size).where(
                            db.RssRow.site_id == int(site_id),
                            db.RssRow.tid.in_(chunk),
                        )
                    ).all()
                    for tid, size in rows:
                        try:
                            out[str(tid)] = float(size or 0.0)
                        except (TypeError, ValueError):
                            out[str(tid)] = 0.0
        except Exception:  # noqa: BLE001
            return {}
        return out

    def _rss_fetch(self, site: Any, rss_url: str) -> List[Dict[str, Any]]:
        """抓一个站点的 RSS 并解析成种子目录行（title/size/downhash/download_url/pub_at）。

        兼容两种 enclosure 形态：``download.php?id=X&downhash=...``（HDDolby 类）
        与带 passkey/token 的直链；解析后一律产出（site_id,tid,title,size,pub_at）。
        """
        from ..collect import sanitize_site_headers  # noqa: WPS433

        out: List[Dict[str, Any]] = []
        try:
            _ua, _cookie = sanitize_site_headers(site) if site else ("", "")
            resp = self._http_client_get(rss_url, cookies=_cookie or None, ua=_ua or None,
                                         referer=(getattr(site, "url", "") or "").rstrip("/") + "/")
            text = resp or ""
            if not text:
                return out
            for mt in re.finditer(
                r"<item>.*?</item>", text, flags=re.S
            ):
                item = mt.group(0)
                m_tid = re.search(r"torrents\.php\?id=(\d+)|details\.php\?id=(\d+)|download\.php\?id=(\d+)", item)
                tid = (m_tid.group(1) or m_tid.group(2) or m_tid.group(3)) if m_tid else None
                if not tid:
                    continue
                title = ""
                m_t = re.search(r"<title>(.*?)</title>", item, re.S)
                if m_t:
                    title = m_t.group(1).strip()
                size = None
                m_s = re.search(r"<size>([\d.]+) ?(GB|MB|KB|B)?</size>", item, re.I)
                if m_s:
                    try:
                        sz = float(m_s.group(1))
                        unit = (m_s.group(2) or "B").upper()
                        mult = {"B": 1, "KB": 1024 ** 2, "MB": 1024, "GB": 1}.get(unit, 1)
                        size = sz * mult / (1024 ** 3)
                    except ValueError:
                        size = None
                pub_at = None
                m_p = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
                if m_p:
                    from email.utils import parsedate_to_datetime
                    try:
                        pub_at = parsedate_to_datetime(m_p.group(1).strip()).timestamp()
                    except Exception:  # noqa: BLE001
                        pub_at = None
                downhash = ""
                m_dh = re.search(r"download\.php\?id=\d+&(?:amp;)?downhash=([0-9a-zA-Zx]+)", item)
                if m_dh:
                    downhash = m_dh.group(1)
                m_enc = re.search(r"<enclosure[^>]+url=['\"]([^'\"]+)['\"]", item, re.I)
                download_url = m_enc.group(1) if m_enc else ""
                if "&amp;" in download_url:
                    download_url = download_url.replace("&amp;", "&")  # XML 实体回退真参
                out.append({
                    "tid": tid, "title": title, "size": size,
                    "downhash": downhash, "download_url": download_url, "pub_at": pub_at,
                })
        except Exception:  # noqa: BLE001
            self._dbg(f"全站辅种:RSS 解析失败 {rss_url[:80]}")
        return out

    def _http_client_get(self, url: str, **kw: Any) -> str:
        """统一 HTTP GET 文本（RequestUtils 封装；失败返回空串）。"""
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433

            resp = RequestUtils(timeout=30, **kw).get_res(url=url)
            if resp and resp.ok:
                return resp.text or ""
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _reseed_rss_cache_refresh(self, site_map: Dict[int, Dict[str, Any]],
                                  quota_per_site: int = 0) -> Dict[str, Any]:
        """每轮刷新各辅种站的种子目录缓存（增量式，配额友好）。

        - 普通站：抓一次 RSS（免费），把最新 N 条 upsert 进 ``mf_rss``；
        - HDDolby 类（search 每时限额）：``quota_per_site`` = 本轮允许的 API 调用次数
          （默认 0 = 不调 API，仅靠 RSS + 之前累积），按「分类 × 页大小 × visible」
          分区枚举补齐历史目录。
        返回统计 {site, cached, pages, api_calls, errors}。
        """
        out: Dict[str, Any] = {"site": 0, "cached": 0, "pages": 0, "api_calls": 0,
                               "errors": []}
        db = self._rss_db()
        if db is None:
            return out
        for sid, s in sorted((site_map or {}).items()):
            site_id = int((s.get("site_id") or 0))
            try:
                site = self._get_site(site_id) if site_id else None
            except Exception:  # noqa: BLE001
                site = None
            # 1) RSS 免费通道（全站通用）
            rss_url = str(getattr(site, "rss", "") or "").strip()
            if not rss_url:
                try:
                    rss_url = str(self._cred_get(site_id, "rss_url") or "").strip()
                except Exception:  # noqa: BLE001
                    rss_url = ""
            if rss_url:
                rows = self._rss_fetch(site, rss_url)
                if rows:
                    for r in rows:
                        r["site_id"] = site_id
                    n = self._rss_upsert(rows)
                    out["cached"] += n
            # 2) HDDolby 类：配额内分区枚举补齐历史目录（增量）
            dom = str((s.get("domain") or "") or "").strip().lower()
            if "hddolby" in dom and int(quota_per_site or 0) > 0:
                try:
                    stat = self._hd_catalog_crawl(site_id, int(quota_per_site))
                    out["api_calls"] += int(stat.get("calls") or 0)
                    out["cached"] += int(stat.get("cached") or 0)
                    for e in (stat.get("errors") or []):
                        out["errors"].append(f"HDDolby 目录:{e}")
                except Exception as err:  # noqa: BLE001
                    out["errors"].append(f"HDDolby 目录爬取:{err}")
            out["site"] += 1
        return out

    def _hd_catalog_crawl(self, site_id: int, max_calls: int) -> Dict[str, Any]:
        """HDDolby 种子目录爬取（分类 × 页大小 × visible 分区枚举，配额内）。

        站点 ``/api/v1/torrent/search`` 的 ``page_number`` 实测**无效**：换页返回同一批
        （重叠 99%+，page 0/1/2 等价）。但 ``categories``（分类）、``page_size``（页大小）
        与 ``visible``（是否只露出可见种）都会真正改变返回窗口 —— 全量目录只能靠这三
        维分区枚举逼近：每个组合拉一批，幂等 upsert 进 ``mf_rss`` 去重累积，多轮叠加。

        ``max_calls``：本轮允许的 API 调用次数（站点每时限额 30005，留足余量）。
        返回统计 ``{calls, rows, cached, distinct, errors}``。
        """
        out: Dict[str, Any] = {"calls": 0, "rows": 0, "cached": 0, "distinct": 0,
                               "errors": []}
        if int(max_calls or 0) <= 0:
            return out
        if self._rss_db() is None:
            return out
        try:
            site = self._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            site = None
        if site is None:
            return out
        dom = str(getattr(site, "domain", "") or "").strip().lower()
        if "hddolby" not in dom:
            return out
        key = ""
        try:
            key = str(self._cred_get(int(site_id), "apikey") or "")
        except Exception:  # noqa: BLE001
            key = ""
        if not key:
            key = str(getattr(site, "apikey", "") or "").strip()
        if not key:
            return out
        # ★ 配额熔断冷却期：上一轮被站点打回「please wait for four hour」→ 冷却期内不再碰
        #   API。搜索与取种共用同一份小时配额，目录爬取必须给取种留出余量。
        try:
            _blk = cache_get(self, "reseed", HD_QUOTA_BLOCK_KEY, HD_QUOTA_COOLDOWN_S + 600) or {}
            _until = float(_blk.get("until") or 0) if isinstance(_blk, dict) else 0.0
        except Exception:  # noqa: BLE001
            _until = 0.0
        if _until > time.time():
            out["quota_cooldown"] = True
            out["errors"].append("配额冷却中（约 %d 分钟后重试）"
                                 % int((_until - time.time()) / 60))
            return out
        # 分区计划：分类 × 页大小 × visible（主力），再叠关键词扫（收益低，排后）。
        plan = self._hd_catalog_partitions()
        ckey = "reseed_catalog_cursor"
        try:
            _cur = cache_get(self, "reseed", ckey, 30 * 86400) or {}
            cur = int(_cur.get("i") or 0) if isinstance(_cur, dict) else 0
        except Exception:  # noqa: BLE001
            cur = 0
        if cur < 0 or cur >= len(plan):
            cur = 0  # 走完一轮 → 回卷（下一轮补齐新种）
        seen: set = set()
        idx = cur
        while idx < len(plan) and out["calls"] < int(max_calls):
            part = plan[idx]
            try:
                rows = self._hd_search_flat(site, dom, key, 0, cats=part.get("cats"),
                                            size=int(part.get("size") or 1000),
                                            visible=int(part.get("visible") or 1),
                                            keyword=str(part.get("kw") or ""))
            except HdQuotaExhausted as err:
                # 立刻停手 + 落 4 小时冷却标记，避免继续空转烧配额。
                out["quota_exhausted"] = True
                out["errors"].append(f"配额耗尽，立即停手:{err}")
                try:
                    cache_set(self, "reseed", HD_QUOTA_BLOCK_KEY,
                              {"until": time.time() + HD_QUOTA_COOLDOWN_S},
                              HD_QUOTA_COOLDOWN_S + 600)
                except Exception:  # noqa: BLE001
                    pass
                break
            except Exception as err:  # noqa: BLE001
                out["errors"].append(f"目录爬取 #{idx} {part}:{err}")
                idx += 1
                continue
            out["calls"] += 1
            idx += 1
            if not rows:
                continue
            out["rows"] += len(rows)
            for r in rows:
                r["site_id"] = int(site_id)
                tid = str(r.get("tid") or "")
                if tid:
                    seen.add(tid)
            out["cached"] += self._rss_upsert(rows)
            time.sleep(0.25)  # 轻微限速，避免触发站点流控
        try:
            cache_set(self, "reseed", ckey,
                      {"i": idx if idx < len(plan) else 0, "ts": time.time()}, 30 * 86400)
        except Exception:  # noqa: BLE001
            pass
        out["cursor"] = idx
        out["plan"] = len(plan)
        out["distinct"] = len(seen)
        self._dbg(
            "全站辅种:HDDolby 目录爬取 %s 次 / 抓 %s 行 / 不同 tid %s / 写入 %s / 游标 %s/%s"
            % (out["calls"], out["rows"], out["distinct"], out["cached"], idx, len(plan))
        )
        return out

    @staticmethod
    def _hd_catalog_partitions() -> List[Dict[str, Any]]:
        """HDDolby 目录分区计划：**分类 × 页大小 × visible 主力在前，关键词扫在尾**。

        2026-10-20 实测校准：
        - 主力 72 档（11 分类 + 不限 × size 1000/300/100 × visible 1/0）一轮就攒出
          **13664** 个不同 tid，是有效分区；
        - 关键词维度收益极低：187 个关键词（77 个裸年份 + 37 个介质词 + 36 个字母数字）
          整跑 150 次调用只净增 **1** 行（裸年份每个只命中约 5 条，早前探针里 kw=2019 的
          「990 新」是相对分类扫之前的空基线）。故**砍掉裸年份**，只留高价值介质/语言词；
        - 搜索与取种共用同一份小时配额，配额被打满后取种会一起失败 —— 关键词扫必须排在
          分类扫之后，且整体靠调用预算节制。
        游标走完一整轮后回卷，用于下一轮补齐新种。
        """
        plan: List[Dict[str, Any]] = []
        cats_seq: List[Any] = [None, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411]
        for visible in (1, 0):
            for size in (1000, 300, 100):
                for cats in cats_seq:
                    plan.append({"cats": cats, "size": size, "visible": visible, "kw": ""})
        toks = ["1080p", "2160p", "720p", "480p", "BluRay", "Blu-ray", "WEB-DL", "WEBRip",
                "REMUX", "HDTV", "DVDRip", "BDRip", "x264", "x265", "H264", "H265", "HEVC",
                "AAC", "DTS", "DTS-HD", "TrueHD", "Atmos", "FLAC", "MP3", "HDR", "HDR10",
                "Dolby", "10bit", "8bit", "国语", "粤语", "中字", "简繁", "原盘", "DIY",
                "合集", "演唱会"]
        for kw in toks:
            plan.append({"cats": None, "size": 1000, "visible": 1, "kw": kw})
        return plan

    def _rss_count(self) -> int:
        """``mf_rss`` 当前行数（缓存覆盖率观测；失败返回 0）。"""
        db = self._rss_db()
        if db is None:
            return 0
        try:
            from sqlalchemy import func  # noqa: WPS433

            with self.get_database().session() as sess:
                return int(sess.query(func.count()).select_from(db.RssRow).scalar() or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _hd_search_flat(self, site: Any, dom: str, key: str, page: int = 0,
                        cats: Optional[Any] = None, size: int = 100, visible: int = 1,
                        keyword: str = "") -> List[Dict[str, Any]]:
        """HDDolby search 一页 → 扁平种子目录行（复用 crossseed 的请求封装）。

        ``cats``：``None`` = 不限分类；可传分类号或分类号列表。实测站点
        ``page_number`` 无效（换页返回同一批），但 ``categories``/``page_size``/
        ``visible``/``keyword`` 都会真正改变返回窗口 —— 这几维是扩大目录覆盖的抓手。

        ★ 站点 API 的角色是**取资源信息**，不是下种子：每行都带 ``downhash``（每 tid 唯一的
        下载口令），取种靠它拼 ``download.php``（见 ``_reseed_download_url`` 缓存分支）。
        早前这里把 ``downhash`` 写死成空串、只留一个 API 下载直链，等于把唯一能用的凭据丢了。
        """
        from app.sdk.network import RequestUtils  # noqa: WPS433

        body = {"keyword": str(keyword or ""), "page_number": int(page or 0),
                "page_size": int(size or 100), "visible": int(visible)}
        if cats:
            body["categories"] = (list(cats) if isinstance(cats, (list, tuple, set))
                                  else [cats])
        res = RequestUtils(
            headers={"x-api-key": key, "Content-Type": "application/json",
                     "Accept": "application/json, text/plain, */*"}, timeout=20,
        ).post_res(url=f"https://api.{dom}/api/v1/torrent/search", json=body)
        if int(getattr(res, "status_code", 0) or 0) != 200:
            _body = str(getattr(res, "text", "") or "")
            if "30005" in _body or "api call per hour" in _body.lower():
                raise HdQuotaExhausted(_body[:200] or "HTTP %s" % getattr(res, "status_code", 0))
            return []
        import json as _json
        data = _json.loads(getattr(res, "text", "") or "{}")
        out: List[Dict[str, Any]] = []
        for it in (data.get("data") or []):
            tid = str(it.get("id") or "").strip()
            if not tid:
                continue
            out.append({
                "tid": tid,
                "title": str(it.get("name") or "")[:500],
                "size": (float(it.get("size") or 0.0) / (1024 ** 3))
                        if it.get("size") is not None else None,
                # ★ 保留站点给的 downhash（取种唯一凭据）；download_url 留空由缓存分支按
                #   站点 domain 拼 `download.php?id=&uid=&downhash=`（不猜主机名）。
                "downhash": str(it.get("downhash") or "").strip(),
                "download_url": "",
                "pub_at": None,
            })
        return out

    # --------------------------------------------------------------- 云端反查
    def _reseed_cloud_map(self, local_hashes: List[str]) -> Dict[str, Any]:
        """本机全量种 → IYUU 反查「他站也有同资源」（带 TTL 缓存；只声明我们的 sid）。

        ★ 19.7.93：反查 0 命中时**绝不覆盖旧结果**。现场（2026-10-20 14:32）IYUU 返回
        ``code=429 86400秒窗口内的次数500已耗尽``，旧代码把空 by_hash 当新结果写回缓存
        （ts 前进 3 天）⇒ 1773 颗本机种、6859 条候选被一次限流抹平，辅种停摆到 TTL 到期。
        现在：0 命中且旧结果非空 → 保留旧结果、不推进 ts，并记 ``blocked_until``
        冷静 ``RESEED_CLOUD_BACKOFF_S``，期内不再反查（IYUU 配额按 24h 窗口算）。
        """
        raw = cache_get(self, "reseed", RESEED_CLOUD_KEY, CACHE_TTL_REPORT)
        data = raw if isinstance(raw, dict) else {}
        now = time.time()
        want = sorted({str(h).strip().lower() for h in local_hashes if h})
        have = {str(x).lower() for x in (data.get("hashes") or [])}
        fresh = (now - float(data.get("ts") or 0)) < RESEED_CLOUD_TTL
        if fresh and data.get("by_hash") and set(want) <= have:
            return data
        # 冷静期：上次反查 0 命中（疑似 IYUU 限流/配额耗尽）→ 直接用旧结果，别再打 IYUU
        if now < float(data.get("blocked_until") or 0):
            return data
        cli = getattr(self, "_iyuu_client", None)
        site_map = self._reseed_site_map()
        if cli is None or not site_map or not want:
            if not site_map:
                self._log("全站辅种:没有可用站点（IYUU sid 未命中我们配置的站）→ 跳过", "warning")
            return data or {"by_hash": {}, "ts": 0.0, "hashes": []}
        sids = sorted(site_map.keys())
        by_hash: Dict[str, Any] = {}
        for i in range(0, len(want), 100):
            part = want[i:i + 100]
            try:
                res = cli.query(part, sids=sids)
            except Exception as err:  # noqa: BLE001
                self._log(f"全站辅种:云端反查失败（已查 {i}/{len(want)}）{err}", "warning")
                break
            if res:
                for h, rows in res.items():
                    if rows:
                        by_hash[str(h).lower()] = rows
            if i + 100 < len(want):
                time.sleep(3.2)  # IYUU 云端限流：批次间留间隔
        if not by_hash:
            # ★ 19.7.93：0 命中 = 反查不可用（限流/配额/网络）比「真的都没有」常见得多；
            #   **保留上次结果**，别让一次失败把 3 天的缓存抹掉。
            prev_by = data.get("by_hash") or {}
            kept: Dict[str, Any] = {
                "sids": sids,
                "blocked_until": now + RESEED_CLOUD_BACKOFF_S,
                "ts": float(data.get("ts") or now) if prev_by else now,
                "hashes": list(data.get("hashes") or []) if prev_by else want,
                "by_hash": prev_by,
            }
            try:
                cache_set(self, "reseed", RESEED_CLOUD_KEY, kept, CACHE_TTL_REPORT)
            except Exception:  # noqa: BLE001
                pass
            _rlog(f"全站辅种:云端反查 0 命中（疑似 IYUU 限流/配额耗尽）→ 保留上次 "
                  f"{len(prev_by)} 条候选，{int(RESEED_CLOUD_BACKOFF_S // 60)} 分钟内不再反查",
                  "warning")
            return kept
        data = {"ts": now, "hashes": want, "by_hash": by_hash, "sids": sids}
        try:
            cache_set(self, "reseed", RESEED_CLOUD_KEY, data, CACHE_TTL_REPORT)
        except Exception:  # noqa: BLE001
            pass
        self._log(f"全站辅种:云端反查完成 —— {len(by_hash)}/{len(want)} 颗本机种在他站有同资源"
                  f"（只声明我们 {len(sids)} 个站）")
        return data

    # ------------------------------------------------------------------ 计划
    def _reseed_pairs(self, cloud: Dict[str, Any], local_index: Dict[str, Any],
                      site_map: Dict[int, Dict[str, Any]],
                      min_gb: Optional[float] = None,
                      stats: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """算出本轮可执行的「本机种 × 目标站」对（去重 + 过期过滤 + 站间轮转）。

        ``min_gb``：体积线覆盖（None=用配置值）。供 `reseed_round` 在「本轮一对都排不出」
        时自动降档复算（见 ``RESEED_DOWNSHIFT_MIN_SIZE_GB``）。
        ``stats``：诊断出参（``src_small``/``src_max_gb``/``tgt_small``/``tgt_max_gb``/``dup``），
        调用方传空 dict；自动降档要用它判断「排不出到底是不是体积线卡的」。
        """
        cfg = self._reseed_cfg()
        min_gb_eff = float((cfg.get("min_size_gb") if min_gb is None else min_gb) or 0.0)
        min_bytes = min_gb_eff * (1024 ** 3)
        st: Dict[str, Any] = stats if isinstance(stats, dict) else {}
        ledger = self._reseed_ledger()
        day = self._reseed_day()
        daily = int(cfg.get("daily") or 0)
        limit = max(1, int(cfg.get("batch") or 1))
        groups: Dict[int, List[Dict[str, Any]]] = {}
        seen_ih: Dict[int, set] = {}   # sid → 本轮已取的目标 info_hash（★ 19.7.92 同轮去重）
        _usable: Dict[int, bool] = {}  # sid → 取链是否可用（特殊站无 cookie=False）
        # ★ 19.7.92（方案 3）：MP site_id → 目录缓存里「带 downhash/download_url」的 tid 集合，
        #   给「特殊站无 cookie」的站用（免登录取链的凭据从缓存来）。
        _cached_tids: Dict[int, set] = {}
        # IYUU sid → MP 站点 id（`mf_rss.site_id` 的口径）；两套 id 混用会让缓存查询静默落空。
        mp_sid = {int(_sid): int((_m or {}).get("site_id") or 0)
                  for _sid, _m in (site_map or {}).items() if (_m or {}).get("site_id")}
        for src_hash, rows in (cloud.get("by_hash") or {}).items():
            src = local_index.get(src_hash)
            if src is None:
                continue  # 本机已经没这颗了
            # ★ 未下完的本机种不能当辅种源：check → 必不过 → ADD-REUSE 纯属空转
            #   （口径复用 reuse.py::_reuse_local_complete，单一真值源）
            if not _reuse_local_complete(src):
                continue
            try:
                size = float(getattr(src, "size", 0) or 0)
            except (TypeError, ValueError):
                size = 0.0
            if size < min_bytes:
                # ★ 体积线拦下的候选用量 —— 自动降档的依据（本轮排不出时按它降一档）
                st["src_small"] = int(st.get("src_small", 0)) + 1
                st["src_max_gb"] = max(float(st.get("src_max_gb") or 0.0), size / (1024 ** 3))
                continue
            for r in (rows or []):
                if not isinstance(r, dict):
                    continue
                ih = str(r.get("info_hash") or "").strip().lower()
                if not ih or ih in local_index:
                    continue  # 目标站的这份本机已经有了
                try:
                    sid = int(r.get("sid"))
                except (TypeError, ValueError):
                    continue
                tid = r.get("torrent_id")
                if not tid or sid not in site_map:
                    continue
                # ★ 2026-10-20：取链**已知不可用**的站直接不排（特殊站无 cookie）——
                #   见 `_chain_usable`；逐站缓存，判定异常时放行（宁可失败也不静默漏站）。
                if sid not in _usable:
                    try:
                        _usable[sid] = _chain_usable(self._reseed_iyuu_entry(sid),
                                                     self._reseed_site_conn(sid))
                    except Exception:  # noqa: BLE001
                        _usable[sid] = True
                if not _usable[sid]:
                    # ★ 方案 3：特殊站没 cookie 时，只要目录缓存里存着这颗的 downhash
                    #   （HDDolby 搜索/RSS 随种下发的一次性令牌），取链照样走得通
                    #   （`download.php?id=&downhash=`，MP 自带 spider 同款）→ 照排。
                    _mp = mp_sid.get(int(sid), 0)
                    if _mp not in _cached_tids:
                        try:
                            _cached_tids[_mp] = self._rss_tids(_mp) if _mp else set()
                        except Exception:  # noqa: BLE001
                            _cached_tids[_mp] = set()
                    if str(tid) not in _cached_tids.get(_mp, set()):
                        st["nocookie"] = int(st.get("nocookie", 0)) + 1
                        continue
                # ★ 19.7.92 同轮同站同一目标只取一对。现场（2026-10-20）：IYUU 反查会给
                #   同一颗目标种多行（tid 不同、info_hash 相同），而台账查的是「已写下」的键
                #   —— 本轮尚未写入，所以几行全都排进同一批：qB 第二次起是**空操作**，
                #   却照记「挂上」+ 花一次 PV + 吃一格 daily（当天 115 行「挂上」只对应
                #   46 个唯一目标 hash；织梦/HDDolby 正好卡在 daily=30）。
                _seen = seen_ih.setdefault(sid, set())
                if ih in _seen:
                    st["dup"] = int(st.get("dup", 0)) + 1
                    continue
                key = f"{sid}:{ih}"
                if ledger.get(key):
                    continue
                if daily and int(day["sites"].get(str(sid)) or 0) >= daily:
                    continue
                _seen.add(ih)
                groups.setdefault(sid, []).append({
                    "key": key, "src": src_hash, "src_size": size, "ih": ih, "tid": tid, "sid": sid,
                })
        # ★ 19.7.92 目标体积预筛：用目录缓存 mf_rss.size（GB；目前只有 HDDolby 有全量 size，
        #   其余站 size 为空 → 命中 0 走「不筛」分支，行为与本改动前完全一致）。
        #   体积线以下的目标不取种：省一次取种 + 指纹 + 挂种（含一次 PV），也不占 daily。
        if min_bytes > 0 and groups:
            for sid in list(groups.keys()):
                # ★ 2026-10-20 修正：`mf_rss.site_id` 是 **MP 站点 id**（HDDolby=17），
                #   这里原来传的是 **IYUU sid**（HDDolby=105）⇒ 恒查空、预筛静默失效
                #   （`tgt_small` 恒 0，日志里只看得到 `too_small`）。必须换算。
                _mp = mp_sid.get(int(sid), 0)
                _sizes = (self._rss_sizes(_mp, [p.get("tid") for p in (groups.get(sid) or [])])
                          if _mp else {})
                if not _sizes:
                    continue
                kept: List[Dict[str, Any]] = []
                for p in (groups.get(sid) or []):
                    sz = float(_sizes.get(str(p.get("tid"))) or 0.0)
                    if sz > 0 and sz < min_gb_eff:
                        st["tgt_small"] = int(st.get("tgt_small", 0)) + 1
                        st["tgt_max_gb"] = max(float(st.get("tgt_max_gb") or 0.0), sz)
                        continue
                    kept.append(p)
                groups[sid] = kept
        for lst in groups.values():
            lst.sort(key=lambda p: -float(p.get("src_size") or 0))
        picked: List[Dict[str, Any]] = []
        while len(picked) < limit and any(groups.values()):
            for sid in sorted(groups.keys()):
                lst = groups.get(sid) or []
                if not lst:
                    continue
                picked.append(lst.pop(0))
                if len(picked) >= limit:
                    break
        return picked

    # ------------------------------------------------------------------ 执行
    def _reseed_nourl_note(self, sid: int, tid: Any) -> str:
        """取链为空时的分类口径（写进台账 note，供排查「为什么缺链」）。

        ★ 2026-10-20：缺链有两类真实原因（特殊站还要区分「cookie 腿」与「缓存 downhash 腿」）；
        逐次请求的实际原因由 `_reseed_download_url(note=…)` 直接给出（HTTP 状态/xpath 未命中），
        这里是**不发请求的兜底口径**（老调用点/异常路径用）。
        """
        conn: Dict[str, Any] = {}
        try:
            conn = self._reseed_site_conn(sid) or {}
        except Exception:  # noqa: BLE001
            conn = {}
        entry = self._reseed_iyuu_entry(sid)
        template = str(entry.get("download_page") or "").strip()
        dom = str(conn.get("domain") or entry.get("base_url") or "").strip().lower()
        if _is_special_dl(template, dom) and not str(conn.get("cookie") or "").strip():
            return "特殊站无 cookie 且目录缓存无该种 downhash（取链不可用）"
        if not template:
            return "无下载链模板/缺口令"
        return "详情页未取到下载链/模板拼链失败"

    def _reseed_one(self, downloader: Any, local_index: Dict[str, Any],
                    pair: Dict[str, Any], dry: bool = False) -> str:
        sid = int(pair["sid"])
        site_name = str((self._reseed_site_map().get(sid) or {}).get("name") or sid)
        key = pair["key"]
        if self._pv_block_reason(sid) or not self._pv_allow(sid, "reseed", want=1):
            self._log(f"全站辅种:{site_name} PV 预算不足/已封，本轮跳过", "warning")
            return "pv"
        _note: Dict[str, str] = {}
        url = self._reseed_download_url(sid, pair["tid"], note=_note)
        if not url:
            # ★ 2026-10-20：缺链按「原因」分型记账（特殊站缺 cookie ≠ 缺模板/口令）——
            #   原因由取链函数逐次给出（HTTP 状态/xpath 未命中），比静态兜底更准。
            #   且一律记 `fail`（1 天）而不是 `miss`（30 天）：这些原因都是**配置/站点侧
            #   可修复**的缺口（补 cookie、站点换模板、CF 盾放行），且本条路径**不花 PV**
            #   （只花一次模板拼链/详情页请求）——用 30 天冻结会让「补上 cookie 后还要再等
            #   一个月」才对这批种子生效。特征码不一致那种「确实不是同资源」才值得 30 天。
            self._reseed_ledger_put(
                key, "fail", _note.get("why") or self._reseed_nourl_note(sid, pair["tid"]))
            return "nourl"
        conn = self._reseed_site_conn(sid)
        raw = None
        try:
            # ★ 2026-10-20：取种链一律是站点网页下载链（特殊站 = 详情页抠出的
            #   `download.php?id=&uid=&hash=`）。原「官方 API 下载」分支已删 —— 那条端点
            #   （`/api/v1/torrent/download`）回的 .torrent 残缺（announce 缺主机名、
            #   明文口令不被 tracker 接受），见 `_reseed_download_url`。
            raw = downloader.fetch_torrent_bytes(
                url, cookie=conn.get("cookie"), user_agent=conn.get("ua"),
                referer=(conn.get("url") or None),
            )
        except TorrentFetchGone as err:
            # ★ 2026-10-20：站点用 JSON 明确回「种未找到」这类**确定性失效**（旧代码当流控）——
            #   单独分型：台账写原因、日志写清楚，不再冒充流控。
            self._reseed_ledger_put(key, "fail", f"目标种子不存在:{err}")
            _rlog(f"全站辅种:{site_name} 目标种子不存在（站点回：{err}）"
                  f" {pair['ih'][:8]}", "warning")
            return "gone"
        except TorrentFetchFlowControl as err:
            self._reseed_ledger_put(key, "fail", f"流控:{err}")
            self._log(f"全站辅种:{site_name} 取种被站点流控，本轮让路（{err}）", "warning")
            return "flow"
        except Exception as err:  # noqa: BLE001
            self._reseed_ledger_put(key, "fail", str(err))
            return "fail"
        finally:
            try:
                self._pv_spend(sid, "reseed", 1)
            except Exception:  # noqa: BLE001
                pass
        if not raw:
            # ★ 19.7.92：这条失败路径原先**完全静默**（只写台账、不写日志），现场只能看到
            #   「失败 25」而看不到「空内容 12」，排查全靠翻数据库。补日志。
            self._reseed_ledger_put(key, "fail", "空内容")
            _rlog(f"全站辅种:{site_name} 取种空内容（链失效/被站点拦，1 天后重试）"
                  f" {pair['ih'][:8]}", "warning")
            return "fail"
        try:
            ih2 = str(info_hash(raw) or "").lower()
        except Exception:  # noqa: BLE001
            ih2 = ""
        if not ih2:
            # ★ 19.7.92：取回 200 但不是种子（登录页/HTML 错误页/失效链）——旧代码会落到下面的
            #   「特征码不一致」分支、按 miss **锁 30 天**，等于把一次性坏链长期占坑
            #   （实测 2026-10-20：HDDolby 那 94 条 miss 大量属此类）。改按 fail（1 天）记。
            self._reseed_ledger_put(key, "fail", "返回内容非种子（疑似限流/登录页/失效链）")
            _rlog(f"全站辅种:{site_name} 取回内容不是种子（疑似限流/登录页/失效链）"
                  f" {pair['ih'][:8]}", "warning")
            return "fail"
        if ih2 and ih2 in local_index:
            self._reseed_ledger_put(key, "ok", "本机已有")
            return "have"
        try:
            fp = fingerprint(raw)
        except Exception:  # noqa: BLE001
            fp = None
        try:
            src_fp = downloader.get_torrent_fingerprint(pair["src"])
        except Exception:  # noqa: BLE001
            src_fp = None
        if not fp or not src_fp or fp != src_fp:
            self._reseed_ledger_put(key, "miss", "特征码不一致")
            self._log(f"全站辅种:{site_name} 特征码不一致，不挂 "
                      f"{pair['src'][:8]}→{pair['ih'][:8]}", "warning")
            return "mismatch"
        src = local_index.get(pair["src"])
        save_path = str(getattr(src, "save_path", "") or "").strip()
        if not save_path:
            # ★ 19.7.92：原先静默（只写台账）→ 现场只看到「失败 N」，看不到「源种无保存目录」。
            self._reseed_ledger_put(key, "miss", "源种无保存目录")
            _rlog(f"全站辅种:{site_name} 源种无保存目录（save_path 空），跳过 "
                  f"{pair['src'][:8]}", "warning")
            return "nosave"
        # ★ 先按资源身份定标签：资源表的身份就是这颗种的「身份」（继承）；
        #   资源表说「资源」→ 直接「静默-资源」（不观察，Master 13:37）；没记过身份 → 辅种即资源
        tag = tag_for(site_name, STATE_SILENT, SUB_RESOURCE)
        _ident = SUB_RESOURCE
        gid = ""
        try:
            groups = self._tag_groups()
            gid = groups.group_with_fp(fp) or ""
            if gid:
                ident = groups.identity(gid)
                if ident in (SUB_NEW, SUB_PLAIN):
                    tag = tag_for(site_name, STATE_SILENT, ident)  # 资源表明写了他身份 → 跟随
                    _ident = ident
                else:
                    groups.set_identity(gid, SUB_RESOURCE, by="reseed")
        except Exception:  # noqa: BLE001
            gid = ""
        if dry:
            self._log(f"全站辅种[干跑·已校验]:{site_name} 可挂 {pair['ih'][:8]}（源 {pair['src'][:8]} "
                      f"{float(pair.get('src_size') or 0) / 1024 ** 3:.2f}GB）")
            return "would"
        try:
            h, err = downloader.add_torrent_reuse(
                torrent_bytes=raw, save_path=save_path, tag=tag, verify=True,
                start=not SILENT_HR_SPLIT_ENABLED,
            )
        except Exception as ex:  # noqa: BLE001
            h, err = None, str(ex)
        if not h:
            self._reseed_ledger_put(key, "fail", str(err))
            # ★ 19.7.92：err 可能是 None（下载器未回原因）→ 至少把站点/目标/源打全，
            #   否则日志只剩「挂种失败 None」，学校那类「添加后未出现在下载器」没法追。
            self._log(f"全站辅种:{site_name} 挂种失败 {err or '（下载器未回原因）'}"
                      f"（目标 {pair['ih'][:8]} ← 源 {pair['src'][:8]}）", "warning")
            return "fail"
        self._reseed_ledger_put(key, "ok", "已挂")
        self._reseed_day_bump(sid)
        # ★ 19.0.1：挂上即登种子账本（mf_seed）。此前只写辅种台账（mf_reseed），
        #   种子账本无行 → drift qb_only 持续累积（实测 358 颗），账本侧逻辑
        #   （分拣/清理/H&R/报表）对辅种全盲。魔流化扫描只收「无魔流标签」的种，
        #   辅种挂上即带完整标签 → 永远没人登记。put 幂等（同 hash 只 patch）。
        try:
            _patch = {
                "site": site_name, "state": STATE_SILENT, "sub": _ident,
                "fp": fp or "",
                "reason": "全站辅种:挂种登记",
            }
            _sz = float(pair.get("src_size") or 0) / 1024 ** 3
            if _sz > 0:
                _patch["size_gb"] = _sz
            self._tag_state().put(h, _patch)
        except Exception as err:  # noqa: BLE001
            self._log(f"全站辅种:账本登记失败 {h[:12]}:{err}", "warning")
        # ★ 资源身份继承：组的身份是「资源」→ 挂上就转「静默-资源」，并写回账本
        if gid and tag.endswith(SUB_RESOURCE):
            try:
                self._silent_to_resource(h)
            except Exception:  # noqa: BLE001
                pass
        title = str(getattr(src, "title", "") or "")[:60]
        self._log(f"全站辅种:{site_name} 挂上「{title}」({pair['ih'][:8]}) ← 源 {pair['src'][:8]} "
                  f"@ {save_path}｜身份 {tag}")
        return "ok"

    def reseed_round(self, dry: Optional[bool] = None, limit: Optional[int] = None,
                     catalog: Optional[int] = None) -> Dict[str, Any]:
        """跑一轮（可干跑）。返回统计：{plan, ok, have, mismatch, fail, nourl, pv, would}
        ★ 19.7.92 增：{flow 流控, nosave 无保存目录, dup 同轮去重掉的重挂候选,
                        too_small 被体积线拦下的候选, downshift/min_size_used 自动降档}。"""
        started = time.time()
        cfg = self._reseed_cfg()
        if dry is None:
            dry = bool(cfg.get("dry"))
        report: Dict[str, Any] = {
            "dry": bool(dry), "plan": 0, "ok": 0, "have": 0, "mismatch": 0,
            "fail": 0, "nourl": 0, "pv": 0, "would": 0, "errors": [],
            # ★ 19.7.92：`flow`/`nosave` 原本靠 `report[st] += 1` 隐式产生、汇总行又不打印
            #   → 「流控 15 次」在日志里完全看不见（只看到「失败 25」里的差额）。
            "flow": 0, "nosave": 0, "gone": 0,
        }
        downloader = self._get_downloader("qbittorrent")
        if downloader is None or not getattr(downloader, "is_available", False):
            report["errors"].append("下载器不可用")
            return report
        try:
            local_index, _size_idx = self._local_reuse_index(downloader)
        except Exception as err:  # noqa: BLE001
            report["errors"].append(f"本机索引失败:{err}")
            return report
        report["local"] = len(local_index)
        if not local_index:
            return report
        try:
            cloud = self._reseed_cloud_map(list(local_index.keys()))
        except Exception as err:  # noqa: BLE001
            report["errors"].append(f"云端反查失败:{err}")
            return report
        site_map = self._reseed_site_map()
        # ★ 种子目录缓存刷新（派生缓存：免费 RSS + 配额内增量翻页）。
        #   先刷目录、后有候选命中缓存 → 本轮更多目标走零成本缓存链。
        try:
            self._reseed_rss_cache_refresh(site_map, quota_per_site=int(catalog or 0))
        except Exception as err:  # noqa: BLE001
            report["errors"].append(f"目录缓存刷新失败:{err}")
        _st: Dict[str, Any] = {}
        pairs = self._reseed_pairs(cloud, local_index, site_map, stats=_st)
        _base_gb = float(cfg.get("min_size_gb") or 0.0)
        report["too_small"] = int(_st.get("src_small", 0)) + int(_st.get("tgt_small", 0))
        report["dup"] = int(_st.get("dup", 0))
        # ★ 2026-10-20（方案 3 后口径）：特殊站没有 cookie、目录缓存里也没有这颗的
        #   downhash ⇒ 本轮不排 —— 记一次可见，免得看板只看到「候选很多、plan 很小」
        #   而不知道为什么（Master 口径：「不让用就不辅种他了，保证大部分站好了」）。
        report["nocookie"] = int(_st.get("nocookie", 0))
        if report["nocookie"]:
            _rlog(f"全站辅种:跳过 {report['nocookie']} 个候选 —— 站点取链不可用"
                  "（特殊站无 cookie 且目录缓存无该种 downhash；本轮不排、不花 PV）")
        if not pairs and _base_gb > 0 and report["too_small"] > 0:
            # ★ 19.7.92 体积线自动降档兜底。现场（2026-10-20）：云端反查出 233 个候选，
            #   全挂在本机 0.29~0.99GB 的小种上 → 1.0GB 体积线一卡，`plan` 恒 0（辅种停摆
            #   5 小时，日志 10 轮「计划 0」）。处置：**不改默认配置、不加设置键**，
            #   只在本轮一对都排不出、且候选中确被体积线拦下时，按「被拦下的最大候选体积」
            #   降一档复算一次（下限 RESEED_DOWNSHIFT_MIN_SIZE_GB）。
            _cand = max(float(_st.get("src_max_gb") or 0.0), float(_st.get("tgt_max_gb") or 0.0))
            # ★ 留 1MB 余量：被拦下的最大候选**正好等于**体积线时，bytes→GB→bytes 的浮点往返
            #   可能把 `size < min_bytes` 判成真 → 降档白降（历史上「只挂着一颗小种」的站
            #   就会出现这种情况）。减 1MB 后再取 3 位小数，日志也更好读。
            _down = min(_base_gb, max(RESEED_DOWNSHIFT_MIN_SIZE_GB, round(_cand - 0.001, 3)))
            if _down < _base_gb:
                _st2: Dict[str, Any] = {}
                pairs = self._reseed_pairs(cloud, local_index, site_map,
                                           min_gb=_down, stats=_st2)
                if pairs:
                    report["downshift"] = True
                    report["min_size_used"] = round(_down, 3)
                    # ★ 降档那一趟才是真正执行的口径：去重计数要取它的（首趟因源体积被拦，
                    #   候选行根本没进到去重判定 → 会把「本轮去重 6」误报成 0）。
                    report["dup"] = int(_st2.get("dup", 0))
                    _rlog(
                        f"全站辅种:体积线自动降档 {_base_gb:g}→{_down:g} GB"
                        f"（被拦候选 {report['too_small']} 个，本轮排出 {len(pairs)} 对）",
                        "warning")
                else:
                    _rlog(
                        f"全站辅种:体积线降档到 {_down:g} GB 仍排不出"
                        f"（下限 {RESEED_DOWNSHIFT_MIN_SIZE_GB:g} GB，被拦候选 "
                        f"{report['too_small']} 个）", "warning")
        if not limit:
            # ★ 打乱顺序：否则每轮都从同样前 N 个开始（干跑采样看不到全貌、实挂也总眷顾同一批）
            random.shuffle(pairs)
        if limit:
            pairs = pairs[: max(1, int(limit))]
        report["plan"] = len(pairs)
        report["candidates"] = sum(len(v or []) for v in (cloud.get("by_hash") or {}).values())
        report["sites"] = len(site_map)
        for pair in pairs:
            try:
                st = self._reseed_one(downloader, local_index, pair, dry=bool(dry))
            except Exception as err:  # noqa: BLE001
                st = "fail"
                report["errors"].append(str(err)[:160])
            report[st] = int(report.get(st, 0)) + 1
            time.sleep(1.2)  # 站间错峰（每挂一个歇一下）
        report["duration"] = round(time.time() - started, 2)
        self._reseed_last = dict(report)
        self._reseed_last["at"] = time.time()
        return report

    # ------------------------------------------------------------- worker 入口
    def reseed_scan(self) -> None:
        """全站辅种 worker（插件级单 worker；低频慢喂）。"""
        cfg = self._reseed_cfg()
        if not bool(cfg.get("enabled", False)):
            return
        if getattr(self, "_reseed_running", False):
            return
        if not self._acquire_worker_slot("全站辅种"):
            return
        self._reseed_running = True
        try:
            rep = self.reseed_round()
            logger.info(
                "全站辅种:计划 %s / 挂上 %s / 已有 %s / 不一致 %s / 失败 %s / 缺链 %s "
                "/ 缺PV %s / 流控 %s / 无目录 %s / 种不存在 %s / 干跑 %s / 去重 %s "
                "/ 体积线拦下 %s（%ss）%s"
                % (rep.get("plan"), rep.get("ok"), rep.get("have"), rep.get("mismatch"),
                   rep.get("fail"), rep.get("nourl"), rep.get("pv"), rep.get("flow"),
                   rep.get("nosave"), rep.get("gone"), rep.get("would"), rep.get("dup"),
                   rep.get("too_small"), rep.get("duration"),
                   ("｜体积线自动降档 %.3gGB" % rep["min_size_used"])
                   if rep.get("downshift") else "")
            )
        except Exception as err:  # noqa: BLE001
            logger.error(f"全站辅种:本轮异常 {err}")
        finally:
            self._reseed_running = False
            self._release_worker_slot()

    def reseed_status(self) -> Dict[str, Any]:
        """全站辅种状态（供接口/看板）。"""
        cfg = self._reseed_cfg()
        day = self._reseed_day()
        cloud = cache_get(self, "reseed", RESEED_CLOUD_KEY, CACHE_TTL_REPORT)
        cloud = cloud if isinstance(cloud, dict) else {}
        ledger = self._reseed_ledger()
        pk = slot_callbacks(self, RESEED_PASSKEY_KEY)[0]()
        pk = pk if isinstance(pk, dict) else {}
        site_map = self._reseed_site_map()
        rows = []
        for sid, s in sorted(site_map.items()):
            rows.append({
                "sid": sid,
                "name": s.get("name"),
                "domain": s.get("domain"),
                "done_today": int(day["sites"].get(str(sid)) or 0),
                "cap": int(cfg.get("daily") or 0),
                "passkey_ok": bool(pk.get(str(sid))),
            })
        stat: Dict[str, int] = {}
        for v in ledger.values():
            st = str(v.get("st") or "?")
            stat[st] = stat.get(st, 0) + 1
        return {
            "enabled": bool(cfg.get("enabled")),
            "dry": bool(cfg.get("dry")),
            "running": bool(getattr(self, "_reseed_running", False)),
            # ★ 7.10.0 接口/设置面用：完整有效配置（models 打底 + plugin data 覆盖后的结果）
            "config": {
                "enabled": bool(cfg.get("enabled")),
                "dry": bool(cfg.get("dry")),
                "sites": [str(x) for x in (cfg.get("sites") or [])],
                "daily": int(cfg.get("daily") or 0),
                "batch": int(cfg.get("batch") or 1),
                "min_size_gb": float(cfg.get("min_size_gb") or 0.0),
            },
            "debug": {
                "client": bool(getattr(self, "_iyuu_client", None)),
                "token": bool(getattr(self, "_iyuu_token", "")),
                "mp_sites": len(self._reseed_mp_sites()),
                "iyuu_sites": len((getattr(self, "_iyuu_client", None).sites() or {}) if getattr(self, "_iyuu_client", None) else {}),
                "mapped": len(site_map),
            },
            "sites": rows,
            "cloud": {
                "at": cloud.get("ts") or 0,
                "hashes": len(cloud.get("hashes") or []),
                "candidates": sum(len(v or []) for v in (cloud.get("by_hash") or {}).values()),
            },
            "ledger": stat,
            "last": getattr(self, "_reseed_last", {}),
        }

    # ------------------------------------------------------------------ 接口
    def reseed_probe(self, fetch: Any = None, api: Any = None) -> Response:
        """诊断：逐站看下载链能不能拼出来（模板/口令/cookie）。fetch=1 实抓；api=<sid> 试 API 取链。"""
        fetch = self._as_bool_arg(fetch)
        try:
            api = int(api) if str(api or "").strip() not in ("", "0") else 0
        except Exception:  # noqa: BLE001
            api = 0
        if api:
            out: Dict[str, Any] = {"ver": "p2", "sid": int(api)}
            try:
                conn = self._reseed_site_conn(int(api))
                site_id = int((conn or {}).get("site_id") or 0)
                c = self._collect_ref()
                out["site_id"] = site_id
                if c is not None and site_id:
                    from ..collect import api_channel  # noqa: WPS433
                    site = self._get_site(site_id)
                    out["channel"] = api_channel(site)[0]
                    out["api_site"] = bool(c.is_api_site(site_id))
                    out["api_dl"] = {k: str(v)[:120]
                                     for k, v in (c.site(site_id).api_dl_token(1) or {}).items()}
                    out["api_raw"] = {k: str(v)[:120]
                                      for k, v in (c.http.api(site_id, "dl", {"id": 1}, kind="api", force=True) or {}).items()}
            except Exception as err:  # noqa: BLE001
                out["error"] = str(err)
            return Response(success=True, data=out)
        rows: List[Dict[str, Any]] = []
        try:
            for sid, s in sorted(self._reseed_site_map().items()):
                entry = self._reseed_iyuu_entry(sid)
                conn = self._reseed_site_conn(sid)
                row: Dict[str, Any] = {
                    "sid": sid, "name": s.get("name"), "domain": s.get("domain"),
                    "template": str(entry.get("download_page") or ""),
                    "base_url": str(entry.get("base_url") or ""),
                    "is_https": int(entry.get("is_https") or 0),
                    "cookie_len": len(str((conn or {}).get("cookie") or "")),
                }
                if fetch:
                    row.update(self._reseed_fetch_probe(sid, entry, conn))
                else:
                    pk = self._reseed_passkey(sid, str(entry.get("base_url") or ""),
                                              int(entry.get("is_https") or 0),
                                              int((conn or {}).get("site_id") or 0),
                                              (conn or {}).get("cookie"))
                    # ★ 2026-10-20：把「取不到链」的原因也回显（特殊站缺 cookie / 详情页 403 /
                    #   xpath 未命中），排查时不必再翻日志。同样先遮口令再截断（只取链一次）。
                    _why: Dict[str, str] = {}
                    url = self._reseed_download_url(sid, 1, note=_why)
                    row.update({"passkey_len": len(pk or ""), "url_ok": bool(url),
                                "url_sample": mask_url_secrets(url or "")[:70],
                                "why": mask_url_secrets(str(_why.get("why") or ""))[:120]})
                rows.append(row)
            return Response(success=True, data={"ver": "p2", "sites": rows})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"诊断失败:{err}")

    def _reseed_fetch_probe(self, sid: int, entry: Dict[str, Any], conn: Any) -> Dict[str, Any]:
        """实抓浏览页，看采集模块到底拿到了什么。"""
        from ..iyuu_cloud import _PASSKEY_RE, harvest_passkey  # noqa: WPS433
        base_url = str(entry.get("base_url") or "")
        is_https = int(entry.get("is_https") or 0)
        scheme = "https" if is_https in (1, 2) else "http"
        biz = base_url.strip().strip("/")
        if biz.startswith("http"):
            biz = biz.split("://", 1)[1]
        out: Dict[str, Any] = {"tries": []}
        collect = self._collect_ref()
        out["collect"] = bool(collect)
        site_id = int((conn or {}).get("site_id") or 0)
        out["site_id"] = site_id
        if collect is not None and site_id:
            for path in ("torrents.php", "usercp.php"):
                url = f"{scheme}://{biz}/{path}"
                try:
                    res = collect.http.text(site_id, url, kind="passkey")
                    txt = str(getattr(res, "text", "") or "")
                    m = _PASSKEY_RE.search(txt)
                    out["tries"].append({"url": mask_url_secrets(url), "ok": bool(getattr(res, "ok", False)),
                                         "status": getattr(res, "status", None),
                                         "len": len(txt),
                                         # ★ 只回长度：旧版回 passkey 前 6 位 = 变相外泄口令。
                                         "pk_len": len(m.group(1)) if m else 0})
                    if not out.get("ctx"):
                        ctx = []
                        low = txt.lower()
                        for needle in ("passkey", "密钥", "downhash", "authkey"):
                            pos = low.find(needle.lower())
                            if pos >= 0:
                                # ★ 命中处前后 140 字符里正含着口令值：长串先遮再回显。
                                ctx.append(mask_long_tokens(txt[max(0, pos - 60):pos + 80]))
                        out["ctx"] = ctx[:3]
                        try:
                            from ..collect import parse_passkey as _pp, _passkey_from_label as _pl  # noqa: WPS433
                            # ★ 只回长度：旧版回前 10 位 = 变相外泄口令。
                            out["label_len"] = len(_pl(txt) or "")
                            out["parsed_pk_len"] = len(str((_pp(txt) or {}).get("passkey") or ""))
                        except Exception as err:  # noqa: BLE001
                            out["label_err"] = str(err)[:120]
                    if m:
                        break
                except Exception as err:  # noqa: BLE001
                    out["tries"].append({"url": url, "error": str(err)[:120]})
        out["fallback_pk_len"] = len(harvest_passkey((conn or {}).get("cookie"), base_url,
                                                     is_https=is_https,
                                                     collect=collect, site_id=site_id) or "")
        if collect is not None and site_id:
            try:
                facts = collect.site(site_id).passkey()
                out["facts"] = {k: (str(v)[:24] if k == "passkey" else v)
                                for k, v in (facts or {}).items()}
            except Exception as err:  # noqa: BLE001
                out["facts"] = f"ERR {err}"
            try:
                out["api_site"] = bool(collect.is_api_site(site_id))
            except Exception:  # noqa: BLE001
                out["api_site"] = None
            if out.get("api_site"):
                try:
                    r = collect.site(site_id).api_dl_token(1)
                    out["api_dl"] = {k: (str(v)[:90]) for k, v in (r or {}).items()}
                except Exception as err:  # noqa: BLE001
                    out["api_dl"] = f"ERR {err}"
        return out

    def get_reseed(self) -> Response:
        """全站辅种状态（站点/配额/云端缓存/账本/上轮结果）。"""
        try:
            return Response(success=True, data=self.reseed_status())
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取全站辅种状态失败:{err}")

    def update_reseed(self, payload: Dict[str, Any]) -> Response:
        """全站辅种配置：{enabled,dry,sites,daily,batch,min_size_gb}（写 plugin data 覆盖）。"""
        try:
            return Response(success=True, message="全站辅种配置已保存",
                            data=self.set_reseed_cfg(payload or {}))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"保存全站辅种配置失败:{err}")

    @staticmethod
    def _as_bool_arg(v: Any) -> Optional[bool]:
        """查询参数是字符串：''/None = 未传；'0'/'false'/'off' = False；其余非空 = True。"""
        if v is None:
            return None
        s = str(v).strip().lower()
        if s == "":
            return None
        return s not in ("0", "false", "no", "off", "none")

    def run_reseed(self, dry: Any = None, limit: Any = None, catalog: Any = None) -> Response:
        """立刻跑一轮全站辅种（dry=1 = **取种校验但不挂**，会花站点 PV；首轮会做云端反查，可能要几十秒）。

        ``catalog=N``：本轮顺带允许 N 次 HDDolby 目录分区枚举 API 调用（0/不传 = 不调）。
        """
        try:
            d = self._as_bool_arg(dry)
            lim = None
            try:
                lim = int(limit) if str(limit or "").strip() != "" else None
            except Exception:  # noqa: BLE001
                lim = None
            cat = None
            try:
                cat = int(catalog) if str(catalog or "").strip() != "" else None
            except Exception:  # noqa: BLE001
                cat = None
            return Response(success=True, data=self.reseed_round(dry=d, limit=lim, catalog=cat))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"全站辅种执行失败:{err}")

    def run_reseed_catalog(self, calls: Any = None, reset: Any = None) -> Response:
        """爬取辅种站种子目录缓存（HDDolby 分类×页大小×visible 分区枚举，**只刷缓存不挂种**）。

        - ``calls``：本轮 API 调用预算（默认 **24**，上限 300）。**搜索与取种共用同一份
          站点小时配额**，所以默认给得很小 —— 一轮轮靠游标推进即可，别一次打满。
        - ``reset``：传 1/true 时把分区游标归零（改了分区计划或想从头重扫时用）。

        返回前后 ``mf_rss`` 行数与 ``{calls,rows,cached,distinct,cursor,plan,errors}``。
        命中站点小时限额（status 30005）会立即停手并落 4 小时冷却标记
        （``quota_exhausted=True``），冷却期内本接口直接返回 ``quota_cooldown=True``。
        """
        try:
            n = 24
            try:
                if str(calls or "").strip() != "":
                    n = int(calls)
            except Exception:  # noqa: BLE001
                n = 24
            n = max(0, min(int(n), 300))
            if str(reset or "").strip().lower() not in ("", "0", "false", "none"):
                try:
                    cache_set(self, "reseed", "reseed_catalog_cursor",
                              {"i": 0, "ts": time.time()}, 30 * 86400)
                except Exception:  # noqa: BLE001
                    pass
            before = self._rss_count()
            site_map = self._reseed_site_map()
            rep = self._reseed_rss_cache_refresh(site_map, quota_per_site=n)
            after = self._rss_count()
            rep["cache_before"] = before
            rep["cache_after"] = after
            rep["cache_added"] = max(0, after - before)
            return Response(success=True,
                            message=f"种子目录缓存已爬取（{before} → {after}，+{after - before} 行）",
                            data=rep)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"目录缓存爬取失败:{err}")
