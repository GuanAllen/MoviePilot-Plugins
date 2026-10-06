# -*- coding: utf-8 -*-
"""魔流 · reseed —— 全站辅种（本机驱动：本机已有的资源 → 去各站落户，**零下载**）。

方向与「跨站取种(crossseed)」**正好相反**：
  · 跨站取种：本机**没有**这颗资源，本站又收费 → 去他站免费下同一 Release → 回辅本站（**要下载**）。
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
import time
from typing import Any, Dict, List, Optional


from app.sdk.logging import logger
from app.schemas import Response

from ..downloader_ops import TorrentFetchFlowControl
from ..fingerprint import fingerprint, info_hash
from ..iyuu_cloud import (
    build_download_url,
    harvest_passkey,
    resolve_link_vars,
)
from ..tags import STATE_SILENT, SUB_NEW, SUB_PLAIN, SUB_RESOURCE, tag_for
from ..sitestore import slot_callbacks


from ..common import (
    RESEED_BATCH,
    RESEED_CLOUD_KEY,
    RESEED_CLOUD_TTL,
    RESEED_CFG_KEY,
    RESEED_DAILY_PER_SITE,
    RESEED_DAY_KEY,
    RESEED_FAIL_TTL,
    RESEED_LEDGER_KEY,
    RESEED_MIN_SIZE_GB,
    RESEED_MISS_TTL,
    RESEED_PASSKEY_KEY,
    SILENT_HR_SPLIT_ENABLED,
)


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
            age = now - float(v.get("ts") or 0)
            if st == "miss" and age > RESEED_MISS_TTL:
                continue
            if st == "fail" and age > RESEED_FAIL_TTL:
                continue
            out[k] = v
        return out

    def _reseed_ledger_put(self, key: str, st: str, note: str = "") -> None:
        if not key:
            return
        led = self._reseed_ledger()
        led[key] = {"st": st, "ts": time.time(), "note": note[:160]}
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
        raw = self.get_data(RESEED_DAY_KEY)
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
            self.save_data(key=RESEED_DAY_KEY, value=day)
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
        """IYUU 站点表里该 sid 的条目（download_page 模板 / base_url / is_https）。"""
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

    def _reseed_download_url(self, sid: int, tid: Any) -> Optional[str]:
        """目标站种子下载链：API 鉴权站走站点 API 签名直链；普通站走云端模板 + passkey。"""
        conn = self._reseed_site_conn(sid)
        if not conn:
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
                    self._dbg(f"全站辅种:API 站 {sid} 取直链失败 {(r or {}).get('error')}")
                    return None
            except Exception as err:  # noqa: BLE001
                self._dbg(f"全站辅种:API 站 {sid} 取直链异常 {err}")
                return None
        # ② 普通站：云端模板 + passkey
        entry = self._reseed_iyuu_entry(sid)
        template = str(entry.get("download_page") or "").strip()
        base_url = str(entry.get("base_url") or "").strip()
        is_https = int(entry.get("is_https") or 0)
        if not template or not base_url:
            return None
        dom = str(conn.get("domain") or base_url or "").strip().lower()
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
        return build_download_url(template, base_url, is_https, tid, variables)

    # --------------------------------------------------------------- 云端反查
    def _reseed_cloud_map(self, local_hashes: List[str]) -> Dict[str, Any]:
        """本机全量种 → IYUU 反查「他站也有同资源」（带 TTL 缓存；只声明我们的 sid）。"""
        raw = self.get_data(RESEED_CLOUD_KEY)
        data = raw if isinstance(raw, dict) else {}
        now = time.time()
        want = sorted({str(h).strip().lower() for h in local_hashes if h})
        have = {str(x).lower() for x in (data.get("hashes") or [])}
        fresh = (now - float(data.get("ts") or 0)) < RESEED_CLOUD_TTL
        if fresh and data.get("by_hash") and set(want) <= have:
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
        data = {"ts": now, "hashes": want, "by_hash": by_hash, "sids": sids}
        try:
            self.save_data(key=RESEED_CLOUD_KEY, value=data)
        except Exception:  # noqa: BLE001
            pass
        self._log(f"全站辅种:云端反查完成 —— {len(by_hash)}/{len(want)} 颗本机种在他站有同资源"
                  f"（只声明我们 {len(sids)} 个站）")
        return data

    # ------------------------------------------------------------------ 计划
    def _reseed_pairs(self, cloud: Dict[str, Any], local_index: Dict[str, Any],
                      site_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """算出本轮可执行的「本机种 × 目标站」对（去重 + 过期过滤 + 站间轮转）。"""
        cfg = self._reseed_cfg()
        min_bytes = float(cfg.get("min_size_gb") or 0.0) * (1024 ** 3)
        ledger = self._reseed_ledger()
        day = self._reseed_day()
        daily = int(cfg.get("daily") or 0)
        limit = max(1, int(cfg.get("batch") or 1))
        groups: Dict[int, List[Dict[str, Any]]] = {}
        for src_hash, rows in (cloud.get("by_hash") or {}).items():
            src = local_index.get(src_hash)
            if src is None:
                continue  # 本机已经没这颗了
            try:
                size = float(getattr(src, "size", 0) or 0)
            except (TypeError, ValueError):
                size = 0.0
            if size < min_bytes:
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
                key = f"{sid}:{ih}"
                if ledger.get(key):
                    continue
                if daily and int(day["sites"].get(str(sid)) or 0) >= daily:
                    continue
                groups.setdefault(sid, []).append({
                    "key": key, "src": src_hash, "src_size": size, "ih": ih, "tid": tid, "sid": sid,
                })
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
    def _reseed_one(self, downloader: Any, local_index: Dict[str, Any],
                    pair: Dict[str, Any], dry: bool = False) -> str:
        sid = int(pair["sid"])
        site_name = str((self._reseed_site_map().get(sid) or {}).get("name") or sid)
        key = pair["key"]
        if self._pv_block_reason(sid) or not self._pv_allow(sid, "reseed", want=1):
            self._log(f"全站辅种:{site_name} PV 预算不足/已封，本轮跳过", "warning")
            return "pv"
        url = self._reseed_download_url(sid, pair["tid"])
        if not url:
            self._reseed_ledger_put(key, "miss", "无下载链模板/缺口令")
            return "nourl"
        conn = self._reseed_site_conn(sid)
        raw = None
        try:
            raw = downloader.fetch_torrent_bytes(
                url, cookie=conn.get("cookie"), user_agent=conn.get("ua"),
                referer=(conn.get("url") or None),
            )
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
            self._reseed_ledger_put(key, "fail", "空内容")
            return "fail"
        try:
            ih2 = str(info_hash(raw) or "").lower()
        except Exception:  # noqa: BLE001
            ih2 = ""
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
            self._reseed_ledger_put(key, "miss", "源种无保存目录")
            return "nosave"
        # ★ 先按资源身份定标签：资源表的身份就是这颗种的「身份」（继承）；
        #   资源表说「资源」→ 直接「静默-资源」（不观察，Master 13:37）；没记过身份 → 辅种即资源
        tag = tag_for(site_name, STATE_SILENT, SUB_RESOURCE)
        gid = ""
        try:
            groups = self._tag_groups()
            gid = groups.group_with_fp(fp) or ""
            if gid:
                ident = groups.identity(gid)
                if ident in (SUB_NEW, SUB_PLAIN):
                    tag = tag_for(site_name, STATE_SILENT, ident)  # 资源表明写了他身份 → 跟随
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
            self._log(f"全站辅种:{site_name} 挂种失败 {err}", "warning")
            return "fail"
        self._reseed_ledger_put(key, "ok", "已挂")
        self._reseed_day_bump(sid)
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

    def reseed_round(self, dry: Optional[bool] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """跑一轮（可干跑）。返回统计：{plan, ok, have, mismatch, fail, nourl, pv, would}。"""
        started = time.time()
        cfg = self._reseed_cfg()
        if dry is None:
            dry = bool(cfg.get("dry"))
        report: Dict[str, Any] = {
            "dry": bool(dry), "plan": 0, "ok": 0, "have": 0, "mismatch": 0,
            "fail": 0, "nourl": 0, "pv": 0, "would": 0, "errors": [],
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
        pairs = self._reseed_pairs(cloud, local_index, site_map)
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
                "/ 缺PV %s / 干跑 %s（%ss）"
                % (rep.get("plan"), rep.get("ok"), rep.get("have"), rep.get("mismatch"),
                   rep.get("fail"), rep.get("nourl"), rep.get("pv"), rep.get("would"),
                   rep.get("duration"))
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
        cloud = self.get_data(RESEED_CLOUD_KEY)
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
                    url = self._reseed_download_url(sid, 1)
                    row.update({"passkey_len": len(pk or ""), "url_ok": bool(url),
                                "url_sample": (url or "")[:70]})
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
                    out["tries"].append({"url": url, "ok": bool(getattr(res, "ok", False)),
                                         "status": getattr(res, "status", None),
                                         "len": len(txt), "pk": (m.group(1)[:6] + "…") if m else ""})
                    if not out.get("ctx"):
                        ctx = []
                        low = txt.lower()
                        for needle in ("passkey", "密钥", "downhash", "authkey"):
                            pos = low.find(needle.lower())
                            if pos >= 0:
                                ctx.append(txt[max(0, pos - 60):pos + 80])
                        out["ctx"] = ctx[:3]
                        try:
                            from ..collect import parse_passkey as _pp, _passkey_from_label as _pl  # noqa: WPS433
                            out["label"] = (_pl(txt) or "")[:10]
                            out["parsed_pk"] = str((_pp(txt) or {}).get("passkey") or "")[:10]
                        except Exception as err:  # noqa: BLE001
                            out["label"] = f"ERR {err}"
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

    def run_reseed(self, dry: Any = None, limit: Any = None) -> Response:
        """立刻跑一轮全站辅种（dry=1 = **取种校验但不挂**，会花站点 PV；首轮会做云端反查，可能要几十秒）。"""
        try:
            d = self._as_bool_arg(dry)
            lim = None
            try:
                lim = int(limit) if str(limit or "").strip() != "" else None
            except Exception:  # noqa: BLE001
                lim = None
            return Response(success=True, data=self.reseed_round(dry=d, limit=lim))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"全站辅种执行失败:{err}")
