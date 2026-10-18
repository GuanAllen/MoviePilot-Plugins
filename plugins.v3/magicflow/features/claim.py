# -*- coding: utf-8 -*-
"""魔流 · claim —— 站点认领（把「我们在做种」的种在站点侧认领掉，换站点给的权益）。

它是**保种增值**动作，和「刷流拿到种」「刷魔力养种」解耦 —— 认领负责**把种变现**。
CARPT：达标种子魔力奖励 = 正常值 ×2；代价是「不达标 −100 / 主动放弃 −500」，
所以：**默认关 + 默认干跑 + 写动作必须显式 confirm**（docs/认领.md §9）。

分层（docs/认领.md §7.5）：
  · 能力层（本模块）：能力探测（profile）+ 写动作适配器（``claim_sites/``）+ 账本 + 统计。
  · 任务层（v2）：``task_type="claim"`` 的全局性认领任务（优先级/属地权/不可接管）。

★ 保护联动：认领 = **保种承诺** → 已认领的种进硬保护、清种永不删（见
  ``ProtectionMixin._protection_sets`` 与 ``_claim_protected_hashes``）；
  否则「认领了又被自己删掉 → 站点判不达标 → 扣魔力」。
"""

import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.schemas import Response
from app.sdk.logging import logger

from ..common import (
    CLAIM_BATCH,
    CLAIM_CFG_KEY,
    CLAIM_DAILY_PER_SITE,
    CLAIM_FAIL_TTL,
    CLAIM_INTERVAL_SEC,
    CLAIM_LEDGER_KEY,
    CLAIM_PROFILE_KEY,
    CLAIM_PROFILE_TTL,
    CLAIM_SOFT_CAP,
    CLAIM_TASK_ID,
)
from ..persistence import OperationItem
from ..sites.claim_presets import preset_for
from ..sitestore import slot_callbacks

_ID_RE = None
try:
    import re as _re

    _ID_RE = _re.compile(r"(?:torrent_id|id)=(\d+)", _re.I)
except Exception:  # noqa: BLE001
    _ID_RE = None


def _torrent_id_of(url: Any) -> str:
    """从详情页链接里抠站点种子 id（``…/details.php?id=12345&hit=1``）。"""
    if not url or _ID_RE is None:
        return ""
    m = _ID_RE.search(str(url))
    return m.group(1) if m else ""


def _est_month_bonus(hourly: Any, settle: Dict[str, Any]) -> float:
    """满月预计魔力收益：``时魔 × 满月小时数(720) × 站点倍率``。

    站点宣告的公式是「达标种子时魔 ×（达标种子总做种小时数 / 达标种子数）× 倍数」，
    满月等价于每颗都做满 720h；这里是**上界口径**，实际按当月小时数比例成文。
    单结算日口径见 :func:`_est_settle_payout`。
    """
    try:
        h = float(hourly or 0.0)
        hours = float(settle.get("payout_hours") or 720)
        mult = float(settle.get("payout_multiplier") or 1.0)
        return round(h * hours * mult, 1)
    except (TypeError, ValueError):
        return 0.0


def _est_settle_payout(hourly: Any, settle: Dict[str, Any]) -> float:
    """本结算日预计魔力：``时魔 × min(周期小时数, 到结算日剩余小时) × 站点倍率``。

    与满月上界不同，这里按「现在到结算日还能做种多少小时」折算，
    给 UI 展示真正落在下一个结算日的收益（未结算前认领的口径）。
    """
    try:
        h = float(hourly or 0.0)
        left = max(0.0, float(settle.get("days_left") or 0.0) * 24.0)
        hours = min(float(settle.get("payout_hours") or 720), left)
        mult = float(settle.get("payout_multiplier") or 1.0)
        return round(h * hours * mult, 1)
    except (TypeError, ValueError):
        return 0.0


def _claim_domain_of(value: Any) -> str:
    """把站点域名/URL 归一成**裸域名**（小写、去 scheme/路径/端口）。

    ``SitesHelper`` 部分站点把 ``domain`` 直接给成 ``https://xxx/``；认领白名单
    与预设表都按裸域名比，故此处统一口径（与 ``_same_site_torrents`` 的 host 口径一致）。
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        host = str(urlparse(text).hostname or "")
    except Exception:  # noqa: BLE001
        host = ""
    for prefix in ("tracker.", "www."):
        if host.startswith(prefix) and len(host) > len(prefix) + 3:
            host = host[len(prefix):]
    return host


class _ClaimSiteRef:
    """轻量站点引用：只带 ``_claim_profile`` 需要的最小字段（id/domain/url）。

    认领扫描按「站点全集」建行时用；避免为每个站点跨文件 ``_get_site``（棘轮计数）。
    """

    def __init__(self, site_id: Any, name: Any = "", domain: Any = ""):
        self.id = site_id
        self.name = str(name or "")
        self.domain = str(domain or "")
        self.url = f"https://{self.domain}/" if self.domain else ""


class ClaimMixin:
    """认领功能集（全局功能页「认领」的后端）。"""

    # ------------------------------------------------------------------ 配置
    def _claim_cfg(self) -> Dict[str, Any]:
        """当前配置：插件配置（models）打底，plugin data 覆盖（便于接口临时开关/干跑）。"""
        cfg: Dict[str, Any] = {
            "enabled": bool(getattr(self, "_claim_enabled", False)),
            "dry": bool(getattr(self, "_claim_dry", True)),
            "sites": list(getattr(self, "_claim_sites", None) or []),
            "daily": int(getattr(self, "_claim_daily", CLAIM_DAILY_PER_SITE) or 0),
            "batch": int(getattr(self, "_claim_batch", CLAIM_BATCH) or CLAIM_BATCH),
            "interval_sec": float(getattr(self, "_claim_interval_sec", CLAIM_INTERVAL_SEC) or 0),
            "min_age_days": float(getattr(self, "_claim_min_age_days", 0) or 0),
            "require_seeders": int(getattr(self, "_claim_require_seeders", 0) or 0),
            "min_size_gb": float(getattr(self, "_claim_min_size_gb", 0) or 0),
            "exclude_zero_bonus": bool(getattr(self, "_claim_exclude_zero_bonus", True)),
        }
        raw = self.get_data(CLAIM_CFG_KEY)
        if isinstance(raw, dict):
            for k in list(cfg.keys()):
                if k in raw:
                    cfg[k] = raw[k]
        return cfg

    def set_claim_cfg(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """写 plugin data 覆盖项（接口用；传空字典 = 回到插件配置）。"""
        raw = self.get_data(CLAIM_CFG_KEY)
        cur: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
        for k, v in (patch or {}).items():
            if k in ("enabled", "dry", "exclude_zero_bonus"):
                cur[k] = bool(v)
            elif k == "sites":
                cur[k] = [str(x).strip().lower() for x in (v or []) if str(x).strip()]
            elif k in ("daily", "batch", "require_seeders"):
                cur[k] = max(0, int(v or 0))
            elif k in ("interval_sec", "min_age_days", "min_size_gb"):
                cur[k] = max(0.0, float(v or 0.0))
        self.save_data(key=CLAIM_CFG_KEY, value=(cur if patch else {}))
        return self._claim_cfg()

    def _claim_cfg_view(self) -> Dict[str, Any]:
        return self._claim_cfg()

    def _claim_feature_enabled(self) -> bool:
        """功能注册表用：认领是否开启（默认关）。"""
        return bool(self._claim_cfg().get("enabled"))

    # ------------------------------------------------------------------ 能力
    def _claim_profile(self, site: Any, refresh: bool = False) -> Dict[str, Any]:
        """站点认领能力（``ClaimProfile``），插件数据缓存 TTL 24h。"""
        if site is None:
            return {"supported": False, "source": "none", "reason": "站点不存在"}
        sid = str(getattr(site, "id", "") or "")
        cache = slot_callbacks(self, CLAIM_PROFILE_KEY)[0]()
        cache = dict(cache) if isinstance(cache, dict) else {}
        hit = cache.get(sid)
        if hit and not refresh and (time.time() - float(hit.get("at") or 0)) < CLAIM_PROFILE_TTL:
            prof = dict(hit.get("profile") or {})
            # ★ 预设表是本地真值：以最新预设覆盖缓存（改站点规则不用等 24h TTL 过期）。
            try:
                fresh = preset_for(str(getattr(site, "domain", "") or getattr(site, "url", "") or ""))
            except Exception:  # noqa: BLE001
                fresh = None
            if isinstance(fresh, dict) and fresh:
                prof.update(fresh)
            return prof
        prof = self._probe_claim_profile(site)
        cache[sid] = {"profile": prof, "at": time.time()}
        try:
            slot_callbacks(self, CLAIM_PROFILE_KEY)[1](value=cache)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领能力缓存写入失败：{err}")
        return prof

    def _probe_claim_profile(self, site: Any) -> Dict[str, Any]:
        """探测顺序（docs/认领.md §1）：预设表命中即用；否则 v1 标记不支持（不浪费请求）。

        v2 计划：① 规则页「种子认领规则」段落解析 ② 详情页 ``#add-claim`` selector 探测。
        """
        domain = str(getattr(site, "domain", "") or getattr(site, "url", "") or "").strip()
        preset = preset_for(domain)
        if preset:
            preset["source"] = "preset"
            preset["verified_at"] = int(time.time())
            return preset
        return {
            "supported": False,
            "source": "none",
            "reason": "未收录该站的认领能力（规则/接口未核对；可在 sites/claim_presets.py 添加 preset，见 docs/认领.md）",
            "verified_at": int(time.time()),
        }

    def _claim_site_universe(self) -> List[Dict[str, Any]]:
        """认领扫描的站点全集：**全部已配置站点**（MP 站点表优先，任务引用兜底）。

        ★ 19.5.0「认领全站纳入」：以前只枚举「有参与任务（running/seeding）的站」，
          站点一旦没有参与任务就从认领页整块消失（哪怕还在做种、还在产生魔力）。
          现在以 MP 站点表为全集；未收录认领能力的站也会出现在列表里
          （``supported=False`` → UI 计数并跳过，不再静默消失）。
        """
        out: Dict[int, Dict[str, Any]] = {}
        try:
            for item in self._list_sites() or []:
                if not isinstance(item, dict):
                    continue
                try:
                    sid = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    sid = 0
                if not sid:
                    continue
                domain = _claim_domain_of(item.get("domain"))
                out[sid] = {
                    "site_id": sid,
                    "site_name": str(item.get("name") or domain or sid),
                    "domain": domain,
                }
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领：枚举站点失败 {err}")
        # 兜底：站点从 MP 删了但任务还挂着 → 仍要出现在全集里（否则任务名下的种漏扫）。
        try:
            for task in (getattr(self, "_task_configs", {}) or {}).values():
                try:
                    sid = int(getattr(task, "site_id", 0) or 0)
                except (TypeError, ValueError):
                    sid = 0
                if not sid or sid in out:
                    continue
                domain = _claim_domain_of(getattr(task, "site_domain", ""))
                out[sid] = {
                    "site_id": sid,
                    "site_name": str(getattr(task, "site_name", "") or domain or sid),
                    "domain": domain,
                }
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领：枚举任务站点失败 {err}")
        return sorted(out.values(), key=lambda x: int(x.get("site_id") or 0))

    def _claim_sites_supported(self) -> List[Dict[str, Any]]:
        """**全部已配置站点**的认领能力清单（功能页顶部能力卡 / 设置页站点下拉）。

        未收录认领能力的站也返回（``supported=False`` + ``profile.reason``）——
        UI 据此计数并跳过，而不是让站点从列表里消失。
        """
        out: List[Dict[str, Any]] = []
        for item in self._claim_site_universe():
            sid = int(item.get("site_id") or 0)
            if not sid:
                continue
            site = _ClaimSiteRef(sid, item.get("site_name"), item.get("domain"))
            prof = self._claim_profile(site)
            out.append(
                {
                    "site_id": sid,
                    "site_name": str(item.get("site_name") or item.get("domain") or sid),
                    "domain": str(item.get("domain") or ""),
                    "supported": bool(prof.get("supported")),
                    "profile": dict(prof),
                }
            )
        return out

    # ------------------------------------------------------------------ 账本
    def _claim_ledger(self) -> Dict[str, Any]:
        """认领账本：``"<site_id>:<hash>" → {tid, ts, st, benefit, note, task, title}``。

        过期只丢「失败/名额满」类；``ok/already`` 是**承诺**，永久保留（还进硬保护）。
        """
        raw = slot_callbacks(self, CLAIM_LEDGER_KEY)[0]()
        if not isinstance(raw, dict):
            return {}
        now = time.time()
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if not isinstance(v, dict):
                continue
            st = str(v.get("st") or "")
            if st in ("ok", "already"):
                out[k] = v
                continue
            age = now - float(v.get("ts") or 0)
            if st in ("full", "unmet") and age > CLAIM_FAIL_TTL:
                continue
            if st == "fail" and age > CLAIM_FAIL_TTL:
                continue
            out[k] = v
        return out

    def _claim_ledger_put(
        self,
        site_id: Any,
        hash_string: str,
        torrent_id: Any = "",
        st: str = "ok",
        benefit: str = "",
        note: str = "",
        task_id: str = "",
        title: str = "",
    ) -> None:
        key = f"{site_id}:{str(hash_string or '').lower()}"
        if not str(hash_string or "").strip():
            return
        led = self._claim_ledger()
        old = led.get(key) if isinstance(led.get(key), dict) else {}
        # ok/already 一旦写下不被失败覆盖（承诺优先）
        if old.get("st") in ("ok", "already") and st not in ("ok", "already"):
            return
        led[key] = {
            "tid": str(torrent_id or old.get("tid") or ""),
            "ts": time.time(),
            "st": st,
            "benefit": benefit or old.get("benefit") or "",
            "note": str(note or "")[:160],
            "task": task_id or old.get("task") or "",
            "title": str(title or old.get("title") or "")[:200],
        }
        if len(led) > 20000:  # 防无限膨胀（先丢失败类）
            for k in sorted(led, key=lambda x: float(led[x].get("ts") or 0)):
                if len(led) <= 20000:
                    break
                if str(led[k].get("st")) in ("ok", "already"):
                    continue
                led.pop(k, None)
        try:
            slot_callbacks(self, CLAIM_LEDGER_KEY)[1](value=led)
        except Exception as err:  # noqa: BLE001
            self._log(f"认领账本写入失败：{err}", "warning")

    def _claim_protected_hashes(self, site_id: Any = None) -> set:
        """已认领（承诺中）的 hash 集合 → 保护联动用（硬保护，永不删）。"""
        out = set()
        for key, val in (self._claim_ledger() or {}).items():
            if not isinstance(val, dict):
                continue
            if str(val.get("st")) not in ("ok", "already"):
                continue
            sid, _, h = str(key).partition(":")
            if site_id is not None and str(site_id) != sid:
                continue
            if h:
                out.add(h)
        return out

    def _claim_today_count(self, site_id: Any) -> int:
        """该站今日已发起的认领次数（限速用）。"""
        day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        n = 0
        for key, val in (self._claim_ledger() or {}).items():
            if not isinstance(val, dict):
                continue
            sid, _, _ = str(key).partition(":")
            if str(sid) != str(site_id):
                continue
            if float(val.get("ts") or 0) >= day0:
                n += 1
        return n

    # ------------------------------------------------------------------ 扫描
    @staticmethod
    def _claim_settlement(prof: Dict[str, Any]) -> Dict[str, Any]:
        """站点结算口径 + 本周期剩余天数（站点预设没声明时给保守默认值）。

        ``cycle=natural_month``：按自然月结算，下一结算点 = 下月 1 日 00:00（本机时区）。
        """
        st = prof.get("settlement") if isinstance(prof.get("settlement"), dict) else {}
        now = time.time()
        lt = time.localtime(now)
        year, month = lt.tm_year, lt.tm_mon + 1
        if month > 12:
            year, month = year + 1, 1
        nxt = int(time.mktime((year, month, 1, 0, 0, 0, 0, 0, -1)))
        return {
            "cycle": str(st.get("cycle") or ""),
            "cycle_text": str(st.get("cycle_text") or ""),
            "target_seed_hours": st.get("target_seed_hours"),
            "target_upload_ratio": st.get("target_upload_ratio"),
            "payout_hours": float(st.get("payout_hours") or 720),
            "payout_multiplier": float(st.get("payout_multiplier") or 1.0),
            "next_settle_at": nxt,
            "days_left": round(max(0.0, (nxt - now) / 86400.0), 1),
        }

    @staticmethod
    def _claim_limit(value: Any) -> int:
        """``limit`` 入参归一（0 / 非法 = 不限）。"""
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _claim_tasks(self) -> List[Any]:
        """认领扫描的任务来源：**有站点的全部任务**（不再按参与调度过滤）。

        ★ 19.5.0「全站纳入」：以前走 ``task_is_participating``（running/seeding），
        站点一旦没有参与任务，它名下还在做种的种就从认领页整块消失（却仍在产生
        魔力）。停止任务名下的种仍可能在做种 → 一并纳入。

        种子来源本身是**下载器当前快照**（``_task_managed_torrents``），所以已删的
        种不会因为任务还挂着被算回来；站点全集另见 ``_claim_site_universe``。
        """
        out: List[Any] = []
        try:
            for task in (getattr(self, "_task_configs", {}) or {}).values():
                if not int(getattr(task, "site_id", 0) or 0):
                    continue
                out.append(task)
        except Exception as err:  # noqa: BLE001
            self._log(f"认领：枚举任务失败 {err}", "warning")
        return out

    def _claim_scan(self, site_id: Any = None, upcoming: int = 20, limit: int = 0) -> Dict[str, Any]:
        """扫一遍「可认领 / 已认领 / 快到期」——**只读本地账本 + 下载器**，零站点请求。

        站点范围 = **全部已配置站点**（``_claim_site_universe``）；未收录认领能力的站
        也出现在 ``sites`` 里（``supported=False``），并由 ``sites_skipped`` 计数。
        ``limit>0`` 时只回前 N 条可认领（按**满月预计收益降序**，多站大量种子时给大模型
        省 token；``claimable_total`` 仍是全量计数）。每条带 ``hourly_bonus``（时魔）与
        ``est_month_bonus``（满月预计收益 = 时魔 × 720h × 站点倍率）；已认领带
        ``seed_hours``（认领后已做种小时数）与 ``est_payout_now``（按已做种小时折算的预计结算）。

        ★ 本方法**永不发写请求**；真写只在 ``run_claim(write=1, confirm=1)`` 且设置里
        关闭「干跑」时才发生（干跑/真跑两个动作彻底分开，19.5.0）。
        """
        cfg = self._claim_cfg()
        now = time.time()
        ledger = self._claim_ledger()
        want = str(site_id).strip() if site_id not in (None, "", "0") else ""
        sites_filter = {str(x).strip().lower() for x in (cfg.get("sites") or [])}
        claimed: List[Dict[str, Any]] = []
        claimable: List[Dict[str, Any]] = []
        soon: List[Dict[str, Any]] = []
        per_site: Dict[str, Dict[str, Any]] = {}

        # ① 站点全集先建行：**全部已配置站点**（含未收录认领能力的站）。
        #    ★ 19.5.0「全站纳入」：站点表是全集，未收录的站也进列表
        #    （supported=False → UI 计数并跳过），不再「没有参与任务就整站消失」。
        for item in self._claim_site_universe():
            sid = int(item.get("site_id") or 0)
            if not sid or (want and str(sid) != want):
                continue
            domain = str(item.get("domain") or "").strip().lower()
            if sites_filter and domain not in sites_filter:
                continue
            prof = self._claim_profile(_ClaimSiteRef(sid, item.get("site_name"), domain))
            per_site[str(sid)] = {
                "site_id": sid,
                "site_name": str(item.get("site_name") or domain or sid),
                "domain": domain,
                "supported": bool(prof.get("supported")),
                "profile": dict(prof),
                "settlement": self._claim_settlement(prof),
                "claimed": 0, "claimable": 0, "today": self._claim_today_count(sid),
                "hourly_bonus_total": 0.0, "est_month_bonus_total": 0.0,
                "est_payout_now_total": 0.0, "est_claimable_payout_total": 0.0,
                "claimed_hours_total": 0.0,
            }

        # ② 任务循环只负责「往行里记种」：站点集合已由上一步定好；同一颗种跨任务
        #    只记一次（``seen`` 防重复计数）。
        seen: set = set()
        for task in self._claim_tasks():
            sid = int(getattr(task, "site_id", 0) or 0)
            row = per_site.get(str(sid))
            if row is None or not row.get("supported"):
                continue
            prof = dict(row.get("profile") or {})
            settle = dict(row.get("settlement") or {})
            sname = str(row.get("site_name") or sid)
            min_age = float(cfg.get("min_age_days") or prof.get("min_age_days") or 0)
            try:
                managed = self._task_managed_torrents(task) or []
            except Exception:  # noqa: BLE001
                managed = []
            if not managed:
                continue
            pages = {}
            try:
                pages = dict(self._store.get_torrent_pages(task.id) or {})
            except Exception:  # noqa: BLE001
                pages = {}
            try:
                pub = dict(self._task_pub_dates(task) or {})
            except Exception:  # noqa: BLE001
                pub = {}
            try:
                ni = dict(self._site_ni_map(sid, managed) or {})
            except Exception:  # noqa: BLE001
                ni = {}
            try:
                bonus = self._claim_bonus_map(task, managed, pub, ni)
            except Exception:  # noqa: BLE001
                bonus = {}
            for tr in managed:
                h = str(getattr(tr, "hash", "") or "").strip().lower()
                if not h:
                    continue
                key = f"{sid}:{h}"
                if key in seen:
                    continue
                seen.add(key)
                rec = ledger.get(key) if isinstance(ledger.get(key), dict) else None
                hb = round(float(bonus.get(h, 0.0) or 0.0), 4)
                est_m = _est_month_bonus(hb, settle)
                base = {
                    "site_id": sid,
                    "site_name": sname,
                    "hash": h,
                    "task": str(getattr(task, "id", "") or ""),
                    "title": str(getattr(tr, "title", "") or "")[:200],
                    "size_gb": round(float(getattr(tr, "size_gb", 0) or 0), 3),
                    "seeders": int(ni.get(h, -1) if h in ni else -1),
                    "torrent_id": _torrent_id_of(pages.get(h)) or (rec or {}).get("tid", ""),
                    "hourly_bonus": hb,
                    "est_month_bonus": est_m,
                }
                if rec and str(rec.get("st")) in ("ok", "already"):
                    row["claimed"] += 1
                    hours = max(0.0, (now - float(rec.get("ts") or 0)) / 3600.0)
                    payout_now = round(
                        hb * min(float(settle["payout_hours"]), hours)
                        * float(settle["payout_multiplier"]), 1)
                    row["hourly_bonus_total"] += hb
                    row["est_month_bonus_total"] += est_m
                    row["est_payout_now_total"] += payout_now
                    row["claimed_hours_total"] += hours
                    claimed.append({**base, "ts": float(rec.get("ts") or 0),
                                    "state": str(rec.get("st")), "benefit": str(rec.get("benefit") or ""),
                                    "seed_hours": round(hours, 1),
                                    "est_payout_now": payout_now,
                                    "note": str(rec.get("note") or "")})
                    continue
                ts = float(pub.get(h) or 0)
                age_days = round((now - ts) / 86400.0, 2) if ts else None
                reasons: List[str] = []
                if not base["torrent_id"]:
                    reasons.append("未回填详情页（先跑一次「回填详情页」）")
                if age_days is None:
                    reasons.append("无发布时间")
                elif min_age and age_days < min_age:
                    reasons.append(f"未满 {min_age:g} 天（还差 {max(0.0, min_age - age_days):.1f} 天）")
                req_seed = int(cfg.get("require_seeders") or 0)
                if req_seed and 0 <= base["seeders"] < req_seed:
                    reasons.append(f"做种人数 {base['seeders']} < {req_seed}")
                min_sz = float(cfg.get("min_size_gb") or 0)
                if min_sz and 0 < base["size_gb"] < min_sz:
                    reasons.append(f"体积 {base['size_gb']}G < {min_sz:g}G")
                if cfg.get("exclude_zero_bonus") and bonus and h in bonus and bonus[h] <= 0:
                    reasons.append("零魔（认领无收益）")
                if any("未满" in r or "无发布时间" in r for r in reasons):
                    soon.append({**base, "age_days": age_days, "block": reasons})
                    continue
                if reasons:
                    continue
                row["claimable"] += 1
                row["hourly_bonus_total"] += hb
                row["est_month_bonus_total"] += est_m
                payout_pot = _est_settle_payout(hb, settle)
                row["est_claimable_payout_total"] += payout_pot
                claimable.append({**base, "age_days": age_days, "profile_min_age": prof.get("min_age_days"),
                                  "est_settle_payout": payout_pot})
        claimable.sort(key=lambda x: (-float(x.get("est_month_bonus") or 0.0),
                                      -float(x.get("age_days") or 0.0)))
        soon.sort(key=lambda x: float(x.get("age_days") or 0), reverse=True)
        claimable_total = len(claimable)
        if limit and int(limit) > 0:
            claimable = claimable[: int(limit)]
        for r in per_site.values():
            r["profile"] = dict(r.get("profile") or {})
            r["soft_cap"] = CLAIM_SOFT_CAP
            r["hourly_bonus_total"] = round(float(r.get("hourly_bonus_total") or 0.0), 3)
            r["est_month_bonus_total"] = round(float(r.get("est_month_bonus_total") or 0.0), 1)
            r["est_payout_now_total"] = round(float(r.get("est_payout_now_total") or 0.0), 1)
            r["est_claimable_payout_total"] = round(float(r.get("est_claimable_payout_total") or 0.0), 1)
            r["est_settle_payout_total"] = round(
                float(r["est_payout_now_total"]) + float(r["est_claimable_payout_total"]), 1)
            r["claimed_hours_total"] = round(float(r.get("claimed_hours_total") or 0.0), 1)
        settle_first = next((r.get("settlement") for r in per_site.values() if r.get("supported")), {})
        return {
            "cfg": cfg,
            "enabled": bool(cfg.get("enabled")),
            "dry": bool(cfg.get("dry")),
            "sites": sorted(per_site.values(), key=lambda x: x["site_id"]),
            "claimed": sorted(claimed, key=lambda x: -float(x.get("ts") or 0)),
            "claimable": claimable,
            "soon": soon[: max(0, int(upcoming))] if upcoming else soon,
            "settlement": settle_first,
            "est_month_bonus_total": round(
                sum(float(r.get("est_month_bonus_total") or 0.0) for r in per_site.values()), 1),
            "claimed_total": len(claimed),
            "claimable_total": claimable_total,
            # ★ 19.5.0「全站纳入」计数：全站 N / 支持认领 M / 未收录被跳过（名字，前 50）。
            "sites_total": len(per_site),
            "sites_supported_total": sum(1 for r in per_site.values() if r.get("supported")),
            "sites_skipped": [
                str(r.get("site_name") or r.get("domain") or r.get("site_id") or "")
                for r in per_site.values() if not r.get("supported")
            ][:50],
            # ★ 19.6.0：站点规则未核对的计数（预设值来自同族插件默认值，UI 标「规则未核对」）
            "sites_unverified_total": sum(
                1 for r in per_site.values()
                if r.get("supported") and bool((r.get("profile") or {}).get("rules_unverified"))
            ),
            "sites_unverified": [
                str(r.get("site_name") or r.get("domain") or r.get("site_id") or "")
                for r in per_site.values()
                if r.get("supported") and bool((r.get("profile") or {}).get("rules_unverified"))
            ][:50],
        }

    def _claim_bonus_map(self, task: Any, managed: List[Any], pub: Dict[str, float], ni: Dict[str, int]) -> Dict[str, float]:
        """算一遍本任务的「当前时魔」（用于排除零魔种）；失败返回空表（不阻塞扫描）。"""
        try:
            params = self._build_formula_params(task)
            items = self._convert_to_bonus_list(
                managed,
                params,
                pub,
                getattr(task, "ti_source", "publish"),
                ni,
                self._site_official_titles(int(getattr(task, "site_id", 0) or 0)),
            )
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领：魔力表计算失败 {err}")
            return {}
        out: Dict[str, float] = {}
        for it in items or []:
            h = str(getattr(it, "hash", "") or "").lower()
            if h:
                out[h] = float(getattr(it, "bonus_per_hour", 0) or 0)
        return out

    # ------------------------------------------------------------------ 只读端点
    def get_claim_state(self, site_id: Any = None, limit: Any = 0) -> Response:
        """功能页数据：概览 / 能力卡 / 可认领 / 已认领 / 账本 / 记录。"""
        try:
            data = self._claim_scan(site_id=site_id, limit=self._claim_limit(limit))
            data["supported_sites"] = self._claim_sites_supported()
            data["cap_total"] = sum(int((s.get("profile") or {}).get("per_user_cap") or 0) for s in data["sites"])
            data["benefit_desc"] = next(
                (str((s.get("profile") or {}).get("benefit_desc") or "") for s in data["sites"]
                 if (s.get("profile") or {}).get("supported")),
                "",
            )
            last = 0.0
            for v in (self._claim_ledger() or {}).values():
                if isinstance(v, dict) and str(v.get("st")) in ("ok", "already"):
                    last = max(last, float(v.get("ts") or 0))
            data["last_claim_at"] = last
            data["records"] = self._claim_records()
            return Response(success=True, data=data)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取认领状态失败：{err}")

    def _claim_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """操作记录（kind=claim）。"""
        try:
            rows = self._store.journal.list_recent(limit=limit, kind="claim") or []
            return [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            return []

    def debug_claim(self, site: Any = "") -> Response:
        """只读诊断：profile + 可认领列表 + 账本。"""
        try:
            out = self._claim_scan(site_id=site)
            led = self._claim_ledger()
            out["ledger"] = {k: v for k, v in list(led.items())[:200]}
            out["ledger_count"] = len(led)
            out["adapters"] = self._claim_adapter_domains()
            return Response(success=True, data=out)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"认领诊断失败：{err}")

    @staticmethod
    def _claim_adapter_domains() -> List[str]:
        try:
            from .. import claim_sites as _cs  # noqa: WPS433

            return list(_cs.domains())
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------ 写动作
    def _claim_one(self, site: Any, profile: Dict[str, Any], torrent_id: Any, uid: Any = None) -> Dict[str, Any]:
        """发一次认领（单条）：匹配适配器 → 发请求 → 解析。不重试。"""
        domain = str(getattr(site, "domain", "") or getattr(site, "url", "") or "")
        try:
            from .. import claim_sites as _cs  # noqa: WPS433

            handler = _cs.find(domain)
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "status": "fail", "message": f"适配器加载失败：{err}"}
        if handler is None:
            return {"ok": False, "status": "unsupported", "message": f"未收录站点 {domain} 的认领适配器"}
        ctx = self._claim_site_ctx(site)
        ctx["uid"] = uid
        try:
            ok, st, msg = handler().claim(ctx, torrent_id, profile)
        except Exception as err:  # noqa: BLE001
            ok, st, msg = False, "fail", f"认领异常：{err}"
        # 幂等：站点侧已认领 → 当成功处理
        if ok and st == "already":
            ok = True
        return {"ok": bool(ok), "status": str(st), "message": str(msg or "")[:300]}

    def _claim_site_ctx(self, site: Any) -> Dict[str, Any]:
        """构造适配器要的站点信息（与签到 site_info 同口径）。"""
        def _s(key: str) -> str:
            return str(getattr(site, key, "") or "").strip()

        timeout = int(getattr(site, "timeout", 0) or 0)
        return {
            "id": getattr(site, "id", None),
            "name": _s("name"),
            "url": _s("url"),
            "domain": _s("domain"),
            "cookie": _s("cookie"),
            "ua": _s("ua"),
            "proxy": bool(getattr(site, "proxy", 0)),
            "timeout": timeout or None,
        }

    def run_claim(self, write: Any = None, confirm: Any = None, dry: Any = None,
                  site_id: Any = None, limit: Any = None) -> Response:
        """扫一轮并（可选）认领：默认**干跑**；真写需 ``write=1&confirm=1``。

        ★ 19.5.0：干跑 / 真跑是两个**互斥动作**——``dry=1``（或默认）永远只读、
        零写请求；``write=1`` 且 ``confirm=1`` 才是真写，且设置里「干跑」开着时
        依旧拒绝（返回 ``dry_blocked`` 供 UI 区分「被设置拦住」与「没确认」）。
        """
        rec = self._claim_scan(site_id=site_id)
        cfg = rec["cfg"]
        want_write = bool(self._as_bool_arg(write))
        dry_arg = self._as_bool_arg(dry)
        dry_ = (not want_write) if dry_arg is None else dry_arg
        preview = {"dry": bool(dry_), "mode": "scan" if dry_ else "write",
                   "claimable": rec["claimable"], "sites": rec["sites"],
                   "claimable_total": rec["claimable_total"]}
        if dry_:
            return Response(
                success=True,
                message=f"干跑：可认领 {rec['claimable_total']} 个（只读，未发任何写请求）",
                data=preview,
            )
        if not bool(self._as_bool_arg(confirm)):
            return Response(
                success=False,
                message="写动作需 confirm=1（认领不可逆：不达标 −魔力 / 放弃 −更多）",
                data={**preview, "need_confirm": True},
            )
        if not cfg.get("enabled"):
            return Response(success=False, message="认领功能未启用（插件设置 → 认领）", data=preview)
        if cfg.get("dry"):
            return Response(
                success=False,
                message="干跑中，未发写请求（设置 → 认领 → 关闭「干跑」后才可认领）",
                data={**preview, "dry_blocked": True},
            )
        rows = list(rec["claimable"])
        cap = int(limit or cfg.get("batch") or 0) or len(rows)
        done: List[Dict[str, Any]] = []
        for row in rows[: max(1, cap)]:
            sid = row["site_id"]
            daily = int(cfg.get("daily") or 0)
            if daily and self._claim_today_count(sid) >= daily:
                done.append({**row, "result": "skip", "message": f"今日已达站点上限 {daily}"})
                continue
            site = self._get_site(sid)
            if not site:
                done.append({**row, "result": "skip", "message": "站点不存在"})
                continue
            prof = self._claim_profile(site)
            res = self._claim_one(site, prof, row.get("torrent_id"), uid=self._site_user_id(site))
            done.append({**row, "result": res.get("status"), "message": res.get("message")})
            if res.get("ok"):
                self._claim_ledger_put(sid, row["hash"], row.get("torrent_id"), st="ok",
                                       benefit=str(prof.get("benefit") or ""),
                                       note=res.get("message", ""), task_id=row.get("task") or "",
                                       title=row.get("title", ""))
            else:
                st = str(res.get("status") or "fail")
                if st in ("fail", "unmet", "full"):
                    self._claim_ledger_put(sid, row["hash"], row.get("torrent_id"), st=st,
                                           note=res.get("message", ""), title=row.get("title", ""))
            self._claim_journal(row, res)
            iv = float(cfg.get("interval_sec") or 0)
            if iv > 0:
                time.sleep(min(iv, 30.0))
        okn = sum(1 for d in done if d.get("result") in ("ok", "already"))
        unverified = [str(r.get("site_name") or r.get("domain") or "") for r in rec.get("sites") or []
                      if r.get("supported") and bool((r.get("profile") or {}).get("rules_unverified"))]
        warn = ""
        if unverified:
            warn = (f"；⚠ {len(unverified)} 个站规则未核对（{'、'.join(unverified[:6])}"
                    f"{'…' if len(unverified) > 6 else ''}）：本表数值为同族默认值，请先在站点核对认领规则")
        return Response(
            success=True,
            message=f"认领完成：成功 {okn} / 共尝试 {len(done)}{warn}",
            data={"done": done, "ok": okn, "sites_unverified": unverified},
        )

    def claim_do(self, site_id: Any = None, hash: str = "", torrent_id: Any = None,
                 confirm: Any = None) -> Response:
        """手动认领单条（``site_id`` + ``hash``），需 ``confirm=1``。"""
        if not bool(self._as_bool_arg(confirm)):
            return Response(success=False, message="需 confirm=1 才执行认领（不可逆）")
        if not self._claim_cfg().get("enabled"):
            return Response(success=False, message="认领功能未启用（插件设置 → 认领）")
        if self._claim_cfg().get("dry"):
            return Response(success=False, message="干跑中，未发写请求（先在设置里关闭「干跑」）")
        try:
            sid = int(site_id or 0)
        except (TypeError, ValueError):
            sid = 0
        hash_string = str(hash or "").strip().lower()
        tid = str(torrent_id or "").strip()
        if not sid or not hash_string:
            return Response(success=False, message="缺少 site_id / hash")
        rec = self._claim_scan(site_id=sid)
        row = next((r for r in rec["claimable"] if r["hash"] == hash_string), None)
        if row is None:
            return Response(success=False, message="该种当前不可认领（未满期 / 已在账本 / 被安全阀挡）")
        if not tid:
            tid = str(row.get("torrent_id") or "")
        site = self._get_site(sid)
        if not site or not tid:
            return Response(success=False, message="站点或种子 id 缺失")
        prof = self._claim_profile(site)
        res = self._claim_one(site, prof, tid, uid=self._site_user_id(site))
        if res.get("ok"):
            self._claim_ledger_put(sid, hash_string, tid, st="ok",
                                   benefit=str(prof.get("benefit") or ""),
                                   note=res.get("message", ""), title=row.get("title", ""))
        else:
            self._claim_ledger_put(sid, hash_string, tid, st=str(res.get("status") or "fail"),
                                   note=res.get("message", ""), title=row.get("title", ""))
        self._claim_journal(row, res)
        return Response(success=bool(res.get("ok")),
                        message=f"{'认领成功' if res.get('ok') else '认领失败'}：{res.get('message')}",
                        data={"result": res})

    def claim_abandon(self, site_id: Any = None, hash: str = "", torrent_id: Any = None,
                      confirm: Any = None) -> Response:
        """放弃认领：**默认不执行**（无接口模板 → unsupported；有 → 需 confirm=1）。"""
        try:
            sid = int(site_id or 0)
        except (TypeError, ValueError):
            sid = 0
        hash_string = str(hash or "").strip().lower()
        if not sid or not hash_string:
            return Response(success=False, message="缺少 site_id / hash")
        if not bool(self._as_bool_arg(confirm)):
            return Response(success=False, message="放弃认领会丢权益并可能扣魔力，需 confirm=1")
        if not self._claim_cfg().get("enabled"):
            return Response(success=False, message="认领功能未启用（插件设置 → 认领）")
        site = self._get_site(sid)
        if not site:
            return Response(success=False, message="站点不存在")
        prof = self._claim_profile(site)
        led = self._claim_ledger()
        rec = led.get(f"{sid}:{hash_string}") or {}
        tid = str(rec.get("tid") or torrent_id or "")
        domain = str(getattr(site, "domain", "") or "")
        try:
            from .. import claim_sites as _cs  # noqa: WPS433

            handler = _cs.find(domain)
        except Exception:  # noqa: BLE001
            handler = None
        if handler is None:
            return Response(success=False, message=f"未收录 {domain} 的认领适配器")
        ctx = self._claim_site_ctx(site)
        try:
            ok, st, msg = handler().abandon(ctx, tid, prof)
        except Exception as err:  # noqa: BLE001
            ok, st, msg = False, "fail", f"放弃异常：{err}"
        if ok:
            self._claim_ledger_put(sid, hash_string, tid, st="abandoned",
                                   note=str(msg), title=str(rec.get("title") or ""))
            self._claim_journal({"site_id": sid, "hash": hash_string, "title": str(rec.get("title") or "")},
                                {"ok": False, "status": "abandoned", "message": str(msg)})
            return Response(success=True, message=f"已放弃认领：{msg}")
        return Response(success=False, message=f"放弃未执行（{st}）：{msg}")

    # ------------------------------------------------------------------ 审计
    def _claim_journal(self, row: Dict[str, Any], res: Dict[str, Any]) -> None:
        """写操作记录（kind=claim）。"""
        try:
            st = str(res.get("status") or "")
            item = OperationItem(
                hash=str(row.get("hash") or ""),
                title=str(row.get("title") or ""),
                reason=str(res.get("message") or ""),
                size_gb=float(row.get("size_gb") or 0),
                seeders=int(row.get("seeders") or 0),
                source="claim" if st in ("ok", "already") else "claim-fail",
            )
            self._store.journal.record(
                task_id=str(row.get("task") or CLAIM_TASK_ID),
                kind="claim",
                items=[item],
                state="completed" if st in ("ok", "already") else "failed",
            )
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领记录写入失败：{err}")
