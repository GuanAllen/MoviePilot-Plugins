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

import json as _json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.schemas import Response
from app.sdk.logging import logger

from ..collect_parse import as_bool_arg

from ..common import (
    CLAIM_BATCH,
    CLAIM_CFG_KEY,
    CLAIM_DAILY_PER_SITE,
    CLAIM_FAIL_TTL,
    CLAIM_HOST_INTERVAL_MINUTES,
    CLAIM_INTERVAL_SEC,
    CLAIM_LEDGER_KEY,
    CLAIM_PROFILE_KEY,
    CLAIM_PROFILE_TTL,
    CLAIM_SITE_TTL,
    CLAIM_STATE_STALE,
    CLAIM_STATE_TTL,
    CLAIM_SOFT_CAP,
    CLAIM_TASK_ID,
    CLAIM_HOST_LEASE_DAYS,
    CLAIM_HOST_TASK_NAME,
)
from .. import cacheops
from ..collect import parse_claim_page
from ..tags import (
    STATE_BONUS,
    STATE_BRUSH,
    STATE_CLAIM,
    STATE_SILENT,
    SUB_RESOURCE,
)
from ..kvstore import cache_get, cache_set
# ★ 19.10.12：纳管 / 退出流程走 ``dutyops``（与 H&R 保种 / 手动保种 / 媒体线共用一套），
#   认领只负责「名单是什么」和「账本标记」，交接动作不再自己写。
from ..dutyops import assign, release
from ..persistence import OperationItem
from ..sites.claim_presets import preset_for
from ..sites.formula_fetch import (
    _norm_title as normalize_title,
    _norm_title_loose as normalize_title_loose,
    fetch_user_torrent_rows,
    title_digest,
)
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


def _claim_min_age(cfg_min: Any, prof_min: Any) -> float:
    """认领资格门槛 = 站点门槛与用户门槛里**更严**的那个（0 = 不限）。

    ★ 19.10.60：旧写法 ``cfg or prof`` 是「用户设了值就把站点门槛整个替掉」——
      用户填 7 天会把聆音的 30 天门槛放宽成 7 天，于是插件说「能领」而站点
      详情页根本没有按钮。站点门槛来自站点规则（硬约束），用户门槛只代表
      「我想不想领」，取严者是唯一不会把话说满的口径。
    """
    try:
        a = float(cfg_min or 0.0)
    except (TypeError, ValueError):
        a = 0.0
    try:
        b = float(prof_min or 0.0)
    except (TypeError, ValueError):
        b = 0.0
    return max(0.0, a, b)


def _reward_gate(prof: Dict[str, Any], age_days: Any, size_gb: Any) -> str:
    """★ 19.10.60：站点**发奖门槛**——「能领」但「这个月领了有没有魔力」。

    与 :func:`_claim_min_age`（能不能领）是两件事，必须分开：学校
    pt.btschool.club 的规则页把两者写在不同段落，混成一个 ``min_age_days``
    的代价是——所有新种在插件里看着都像"还不能领"，而站点详情页早有按钮。

    学校原文（rules.php「认领种子规则」第 5 条 + 奖励标准）：
      「做种时间或者上传到达要求，种子的大小超过1G，并且种子的发布时间超过
        一个月（30天），按照奖励标准发放魔力值」
      「发布时间少于一个月的种子，即使达到认领要求依然没有魔力值奖励」

    返回**原因串**（空串 = 没有门槛或已满足），判定只在这里做一次，前端只摆结论。
    """
    p = prof or {}
    out: List[str] = []
    try:
        min_age = float(p.get("reward_min_age_days") or 0.0)
    except (TypeError, ValueError):
        min_age = 0.0
    try:
        min_size = float(p.get("reward_min_size_gb") or 0.0)
    except (TypeError, ValueError):
        min_size = 0.0
    if min_age > 0:
        if age_days is None:
            # 算不出来就说算不出来（铁律 8），不能默默当成「已达标」
            out.append(f"发布时间未知，满 {min_age:g} 天才计魔力")
        else:
            try:
                days = float(age_days)
            except (TypeError, ValueError):
                days = 0.0
            if days < min_age:
                out.append(f"发布 {days:.1f} 天，满 {min_age:g} 天才计魔力")
    if min_size > 0:
        try:
            sz = float(size_gb or 0.0)
        except (TypeError, ValueError):
            sz = 0.0
        if 0 < sz < min_size:
            out.append(f"{sz:g}G 低于 {min_size:g}G 不计魔力")
    return "；".join(out)


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
                # ★ 2026-10-18：预设表是本地真值 → 整份以 preset 为准。
                #   旧缓存里的 source/reason（早期 "未收录" 探测）不能被 update 残留，
                #   否则会出现 supported=True 但 reason=未收录 的自相矛盾数据。
                prof = dict(fresh)
                prof["source"] = "preset"
                prof["verified_at"] = int(time.time())
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
        """写一条认领账本记录（承诺优先：``ok``/``already`` 不被失败覆盖，但可被放弃终止）。"""
        key = f"{site_id}:{str(hash_string or '').lower()}"
        if not str(hash_string or "").strip():
            return
        led = self._claim_ledger()
        old = led.get(key) if isinstance(led.get(key), dict) else {}
        # ok/already 一旦写下不被失败覆盖（承诺优先）
        # ★ 19.10.58：``abandoned`` 是**承诺的终止**（站点侧已取消认领），必须能落下去 ——
        #   旧口径一律「非 ok/already 不覆盖」，导致放弃后账本仍是 ok，前端继续列「已认领」。
        if old.get("st") in ("ok", "already") and st not in ("ok", "already", "abandoned"):
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
            self._claim_state_bump()
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

    # ------------------------------------------------------- 19.7.0 保挂
    def _claim_qb_snapshot(self) -> Dict[str, Any]:
        """qB 当前快照（hash → TorrentInfo）；失败返回空表，不影响只读展示。"""
        try:
            return dict(self._tag_all_torrents() or {})
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领保挂: qB 快照失败 {err}")
            return {}

    def _claim_duty_targets(self) -> Dict[str, Dict[str, Any]]:
        """★ 19.10.11：**认领的纳管名单** —— 账本 ``st∈{ok,already}`` 的 hash → 记录。

        与刷流/魔力的「任务分派清单」同构：名单在 → 上班（贴 ``魔流-<站>-认领``）；
        名单不在 → 下班（还原原职务，缺省回静默）。
        """
        out: Dict[str, Dict[str, Any]] = {}
        for key, val in (self._claim_ledger() or {}).items():
            if not isinstance(val, dict):
                continue
            if str(val.get("st")) not in ("ok", "already"):
                continue
            # ★ 19.10.11 **退出机制**：带 ``duty_excluded`` 的记录不进名单 → 自动下班。
            #   标记落在**认领账本**（KV），不依赖 mf_seed 的退役列（manual 等不落库，靠不住）。
            if val.get("duty_excluded"):
                continue
            _, _, h = str(key).partition(":")
            h = h.strip().lower()
            if h:
                out[h] = val
        return out

    def _claim_duty_mark(self, hashes: Any, *, excluded: bool = True) -> int:
        """★ 19.10.11：给认领账本打 / 摘「职务排除」标记（**只动标记，不动 st**）。

        st 是站点侧承诺（删除硬保护、账单口径都看它），退出职务不等于放弃认领，
        所以这里只加 ``duty_excluded``，恢复时摘掉即可重新纳管。
        """
        hs = {
            str(h or "").strip().lower()
            for h in ([hashes] if isinstance(hashes, str) else list(hashes or []))
            if str(h or "").strip()
        }
        if not hs:
            return 0
        led = self._claim_ledger()
        n = 0
        for key, val in list(led.items()):
            if not isinstance(val, dict):
                continue
            _, _, h = str(key).partition(":")
            if h.strip().lower() not in hs:
                continue
            rec = dict(val)
            if excluded:
                rec["duty_excluded"] = True
                rec["duty_excluded_at"] = time.time()
            else:
                rec.pop("duty_excluded", None)
                rec.pop("duty_excluded_at", None)
            led[key] = rec
            n += 1
        if n:
            try:
                slot_callbacks(self, CLAIM_LEDGER_KEY)[1](value=led)
                self._claim_state_bump()
            except Exception as err:  # noqa: BLE001
                logger.warning(f"认领职务:排除标记写入失败:{err}")
                return 0
        return n

    def _claim_host_status(self, resume: bool = False) -> Dict[str, Any]:
        """★ 19.7.0 / ★ 19.10.11：``__claim__`` 宿主 —— **认领职务的纳管 + 退出 + 保挂**。

        ``resume=False`` 纯只读（``/claim`` 页面用；只算 would_adopt/would_release，不写标签、不写账本）；
        ``resume=True``（worker）执行三件事（都幂等）：

        ① **纳管**：名单内、职务不是「认领」→ 贴职务轴 ``魔流-<站>-认领``（身份轴原样保留）
           + 账本占位（``taken_by=__claim__`` + 长期租约，任务分派因此抢不走）+ 记 ``prev_state``
        ② **在岗**：已是认领职务 → 只确保在种
        ③ **退出**：账本还是「认领」但已不在名单 → 还原 ``prev_state``（只有刷流/魔力还原，
           其余回静默）；回静默的**当场 pause**（静默池语义就是不上传），不等下一轮收敛

        与 H&R 的关系：认领 = 保种承诺，做种中照样累积 H&R 时长；``_hr_host_assign`` 已跳过
        ``taken_by=__claim__`` 的种，避免两边抢同一个职务。
        绝不删除、不改账本承诺；删除闸门另有硬保护。
        """
        claims = self._claim_duty_targets()
        snap = self._claim_qb_snapshot()
        rep: Dict[str, Any] = {
            "at": time.time(), "apply": bool(resume), "total": len(claims),
            "seeding": 0, "paused": 0, "resumed": 0,
            "missing": 0, "missing_hashes": [],
            "adopted": 0, "holding": 0, "released": 0, "excluded": 0,
            "skipped": 0, "failed": 0,
            "blocked": 0, "blocked_hashes": [],
            "would_adopt": [], "would_release": [],
        }
        missing: List[str] = []
        to_resume: List[str] = []
        try:
            rep["excluded"] = sum(
                1 for _v in (self._claim_ledger() or {}).values()
                if isinstance(_v, dict) and _v.get("duty_excluded")
                and str(_v.get("st")) in ("ok", "already")
            )
        except Exception:  # noqa: BLE001
            rep["excluded"] = 0
        try:
            store = self._tag_state()
        except Exception as err:  # noqa: BLE001
            rep["error"] = f"账本不可用:{err}"
            return rep
        try:
            downloader = self._get_downloader()
        except Exception:  # noqa: BLE001
            downloader = None
        recs = dict(store.items() or {})
        _now = time.time()
        _lease = _now + float(CLAIM_HOST_LEASE_DAYS) * 86400.0

        # ---------------------------------------------------------- ① 名单内 → 上班
        # ★ 19.10.12：纳管流程走 ``dutyops.assign``（与 H&R 保种 / 手动保种 / 媒体线共用一套）。
        #   认领是 ``poach=True`` 的特殊岗位：能从刷流/魔力(60)、点播/音乐(70)、H&R(80)
        #   名下收人 —— 「名单在我这，就该我管」；但手动保种(95) 不抢（人工点名更强，
        #   且它照样在做种，承诺与时长都不受影响，抢只会每轮互贴标签）。
        #   在岗判定 = 账本归本岗 **且** 标签在位（任一路径清过 ``taken_by`` 都会自愈）。
        present: List[str] = []
        for hh in claims:
            if (snap or {}).get(hh) is None:
                missing.append(hh)  # qB 里没了：不重下（认领不吞流量）
            else:
                present.append(hh)
        _adopt = assign(
            self, present, taker=CLAIM_TASK_ID, state=STATE_CLAIM,
            name=CLAIM_HOST_TASK_NAME, lease_until=_lease,
            prev_from=(STATE_BRUSH, STATE_BONUS),  # 退出时只还原这两个真任务职务
            apply=resume, require_site=True, resume_when="all",
            default_sub=SUB_RESOURCE,
        )
        rep["adopted"] = int(_adopt.get("adopted") or 0)
        rep["holding"] = int(_adopt.get("holding") or 0)
        rep["blocked"] = int(_adopt.get("blocked") or 0)
        rep["blocked_hashes"] = list(_adopt.get("blocked_hashes") or [])
        rep["skipped"] = int(rep["skipped"]) + int(_adopt.get("skipped") or 0)
        rep["failed"] = int(rep["failed"]) + int(_adopt.get("failed") or 0)
        rep["would_adopt"] = list(_adopt.get("would") or [])
        to_resume.extend(_adopt.get("resume") or [])

        # ---------------------------------------------------------- ② 名单外 → 下班
        _stale = [hh for hh, rec in recs.items()
                  if hh not in claims and str(rec.get("state") or "") == STATE_CLAIM]
        if not resume:
            rep["would_release"] = list(_stale)
        elif _stale:
            _rel = release(
                self, _stale, taker=CLAIM_TASK_ID, state=STATE_SILENT,
                restore_prev=(STATE_BRUSH, STATE_BONUS),  # 原职务是刷流/魔力就还原，否则回静默
                pause=True, allow_untaken=True, default_sub=SUB_RESOURCE,
            )
            rep["released"] = int(_rel.get("released") or 0)
            rep["failed"] = int(rep["failed"]) + int(_rel.get("failed") or 0)

        # ---------------------------------------------------------- ③ 保挂（resume）
        # ★ 19.10.13：``paused`` 原来 = ``len(to_resume)``，而 ``resume_when="all"`` 让它恒等于
        #   名单数（19）—— 页面于是永远显示「暂停 19 个」，与 qB 实况无关，误导读数
        #   （2026-10-28 实测 qB 里 19 个全 ``stalledUP``，页面却报 paused=19）。
        #   现在 ``paused`` = qB 里**确实不在做种**的个数；「本轮要拉起的」另给 ``need_resume``。
        _paused_now = sum(
            1 for h in claims
            if h in (snap or {})
            and str(getattr((snap or {}).get(h), "state", "") or "").lower().startswith(
                ("paused", "stopped", "queued"))
        )
        rep["paused"] = int(_paused_now)
        rep["need_resume"] = len(to_resume)
        rep["missing"] = len(missing)
        rep["missing_hashes"] = missing[:20]
        if resume and to_resume:
            try:
                n, err = downloader.resume_torrents(to_resume)
                rep["resumed"] = int(n or 0)
                if err:
                    self._log(f"认领保挂:恢复失败 {err}", "warning")
            except Exception as err:  # noqa: BLE001
                self._log(f"认领保挂:恢复异常 {err}", "warning")
        rep["seeding"] = sum(
            1 for h in claims
            if h in (snap or {})
            and not str(getattr((snap or {}).get(h), "state", "") or "").lower().startswith(
                ("paused", "stopped", "queued"))
        )
        if resume and claims:
            self._log(
                f"认领职务: 名单 {rep['total']} / 在岗 {rep['holding']} / 新纳管 {rep['adopted']} "
                f"/ 退出 {rep['released']} / 在种 {rep['seeding']} / 恢复 {rep['resumed']} "
                f"/ 丢失 {rep['missing']} / 让位 {rep['blocked']}"
            )
        return rep

    def claim_host(self) -> Dict[str, Any]:
        """★ 19.7.0 / ★ 19.10.11：``__claim__`` 常驻 worker（纳管 + 退出 + 保挂）。"""
        return self._claim_host_status(resume=True)

    def claim_host_enforce(self, confirm: Any = None, exclude: Any = None,
                           include: Any = None) -> Response:
        """★ 19.10.11：``GET|POST /claim/host`` —— **手动收敛一轮**认领职务（默认干跑）。

        - 不带参：只算 ``would_adopt`` / ``would_release``（零写入）；``confirm=1`` 才真写。
        - ``exclude=h1,h2``：把这几个种**退出**认领职务（名单里打 ``duty_excluded``，
          立刻还原静默并暂停；站点侧承诺不放弃 → 删除保护照旧）。需 ``confirm=1``。
        - ``include=h1,h2``：摘掉排除标记，下一轮重新纳管。需 ``confirm=1``。

        与 ``/silent/enforce`` 同风格：运维要能「现在就对齐」，不必等 15 分钟的 worker。
        """
        _v = str(confirm if confirm is not None else "").strip().lower()
        apply = _v in ("1", "true", "yes", "on", "y")

        def _hs(x: Any) -> List[str]:
            return [p.strip().lower() for p in str(x or "").split(",") if p.strip()]

        _ex, _in = _hs(exclude), _hs(include)
        if (_ex or _in) and not apply:
            return Response(success=False, message="退出/恢复需 confirm=1", data={
                "exclude": len(_ex), "include": len(_in), "need_confirm": True})
        marks = 0
        if apply and _ex:
            marks += self._claim_duty_mark(_ex, excluded=True)
        if apply and _in:
            marks += self._claim_duty_mark(_in, excluded=False)
        rep = self._claim_host_status(resume=apply)
        rep["marked"] = marks
        if not apply:
            rep["note"] = "干跑（confirm=0）：零写入；确认后加 confirm=1"
        else:
            rep["note"] = (f"已收敛：纳管 {rep.get('adopted')} / 退出 {rep.get('released')} "
                           f"/ 在岗 {rep.get('holding')} / 恢复 {rep.get('resumed')}"
                           + (f" / 标记 {marks}" if marks else ""))
        return Response(success=True, message=str(rep.get("note") or ""), data=rep)

    def _claim_host_card(self) -> Dict[str, Any]:
        """★ 19.7.0：``__claim__`` 保挂在任务列表里的只读卡片（不触发 resume）。"""
        rep = self._claim_host_status(resume=False)
        return {
            "id": CLAIM_TASK_ID,
            "name": "认领保挂",
            "builtin": True,
            "enabled": True,
            "run_mode": "running",
            "task_type": "host",
            "state": "running",
            "site_id": 0,
            "site_domain": "",
            "site_name": "全部站点（认领保挂）",
            "downloader": "所有下载器",
            "brush_tag": "魔流-<站点>-认领",
            "save_path": "",
            "seeding_count": int(rep.get("seeding") or 0),
            "active_seeding_count": int(rep.get("seeding") or 0),
            "paused_count": int(rep.get("paused") or 0),
            "missing_count": int(rep.get("missing") or 0),
            "claim_count": int(rep.get("total") or 0),
            "host_interval_minutes": float(CLAIM_HOST_INTERVAL_MINUTES),
            "host_last_run": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(rep.get("at") or time.time()))),
        }

    # --------------------------------------------------- 19.7.1 站点口径

    # 19.10.30：认领页解析已下沉 ``collect.parse_claim_page``（铁律 1「解析归采集」）。
    #   原 87 行静态方法整体搬走，本类只剩「抓取 + 落账」；调用点见 ``_claim_parse_live``。

    def _claim_discover_uid(self, site: Any, ctx: Dict[str, Any], base: str) -> str:
        """没有 c_secure_uid 时，从 userdetails.php 的 claim.php？uid= 链接反查 UID。"""
        sid = str(getattr(site, "id", "") or "")
        cache = getattr(self, "_claim_uid_cache", None)
        if cache is None:
            cache = {}
            try:
                self._claim_uid_cache = cache
            except Exception:  # noqa: BLE001
                pass
        if sid in cache:
            return str(cache.get(sid) or "")
        uid = ""
        try:
            from app.utils.http import RequestUtils  # noqa: WPS433

            proxies = None
            if ctx.get("proxy"):
                try:
                    from app.core.config import settings as _settings  # noqa: WPS433

                    proxies = _settings.PROXY
                except Exception:  # noqa: BLE001
                    proxies = None
            req = RequestUtils(
                cookies=ctx.get("cookie"), ua=ctx.get("ua"), proxies=proxies,
                timeout=ctx.get("timeout") or 20, referer=base + "/",
            )
            res = req.get_res(url=base + "/userdetails.php")
            text = (res.text or "") if res is not None else ""
            import re as _re

            m = _re.search(r"claim\.php\?uid=(\d+)", text) or _re.search(r"userdetails\.php\?id=(\d+)", text)
            uid = m.group(1) if m else ""
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领 UID 反查失败 {sid}: {err}")
        cache[sid] = uid
        return uid

    def _claim_site_claims(self, site: Any, refresh: bool = False) -> Dict[str, Any]:
        """★ 19.7.1：抓站点认领页（按站缓存 10 分钟），返回站点口径。"""
        sid = str(getattr(site, "id", "") or "")
        cache = getattr(self, "_claim_site_cache", None)
        if cache is None:
            cache = {}
            try:
                self._claim_site_cache = cache
            except Exception:  # noqa: BLE001
                pass
        hit = cache.get(sid)
        if not refresh and hit and (time.time() - float(hit.get("at") or 0)) < CLAIM_SITE_TTL:
            return hit
        prof = self._claim_profile(site)
        path = str(prof.get("claim_list") or "").strip()
        ctx = self._claim_site_ctx(site)
        base = str(ctx.get("url") or "").strip().rstrip("/")
        if not path or not base:
            return {}
        uid = self._site_user_id(site) or self._claim_discover_uid(site, ctx, base)
        if "{uid}" in path and not uid:
            return {}
        path = path.replace("{uid}", str(uid or ""))
        url = base + (path if path.startswith("/") else "/" + path)
        try:
            from app.utils.http import RequestUtils  # noqa: WPS433

            proxies = None
            if ctx.get("proxy"):
                try:
                    from app.core.config import settings as _settings  # noqa: WPS433

                    proxies = _settings.PROXY
                except Exception:  # noqa: BLE001
                    proxies = None
            req = RequestUtils(
                cookies=ctx.get("cookie"), ua=ctx.get("ua"), proxies=proxies,
                timeout=ctx.get("timeout") or 20, referer=base + "/",
            )
            res = req.get_res(url=url)
            if res is None:
                return {}
            data = parse_claim_page(res.text or "")
            data["at"] = time.time()
            data["url"] = url
            cache[sid] = data
            return data
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领站点口径读取失败 {sid}: {err}")
            return {}

    def _claim_site_claims_invalidate(self, site_id: Any = None) -> None:
        """★ 19.10.58：作废「站点认领页」缓存（放弃认领后必须做）。

        认领页缓存 ``CLAIM_SITE_TTL``=600s，而放弃是**秒级生效**的写动作：
        不作废的话站点侧那颗已经取消了，前端重建仍从旧页面把它读回「已认领」，
        用户会以为「点了放弃没反应」。这里只丢缓存，下一次读自然重抓一页。
        """
        cache = getattr(self, "_claim_site_cache", None)
        if not isinstance(cache, dict):
            return
        sid = str(site_id or "").strip()
        if sid:
            cache.pop(sid, None)
        else:
            cache.clear()

    @staticmethod
    def _claim_days_since(text: Any) -> Any:
        """站点时间串（``2026-10-18 11:07`` / ``2026-10-18 11:07:33``）→ 天数（算不出返回 None）。"""
        raw = str(text or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return max(0.0, (time.time() - datetime.strptime(raw, fmt).timestamp()) / 86400.0)
            except (TypeError, ValueError):
                continue
        return None

    def _claim_abandon_verdict(self, prof: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
        """**能不能安全放弃**这一颗 —— 判断只做一次，UI 只负责如实摆出来。

        认领是带罚则的承诺：「放弃」在**未达标**时会按站点罚则扣魔力，所以这里先替用户
        把「会不会被扣」算清楚，只有算得出「不会扣」的状态才允许点（19.10.58 Master 定）。

        返回 ``{"state","reason","penalty","claim_id"}``，``state`` 取值：

          ``safe``        站点判本月**已达标** → 放弃只失去 ×2 奖励，不触发未达标罚
          ``grace``       未达标，但仍在站点「首 N 天豁免」期内 → 站点不按未达标处罚
          ``blocked``     未达标且已过豁免期 → 放弃会按该站罚则扣魔力（按钮锁死）
          ``unknown``     站点没给达标状态 / 没给认领记录 id → **算不出来**，不让用户拿命试
          ``unsupported`` 该站没有放弃接口（学校 viewclaims；聆音未核对）
        """
        p = (prof or {}).get("penalty") or {}
        penalty = int(p.get("abandon") or 0)
        exempt = int(p.get("exempt_days") or 0)
        claim_id = str((row or {}).get("site_claim_id") or "").strip()
        qualified = (row or {}).get("site_qualified")
        days = ClaimMixin._claim_days_since((row or {}).get("site_claimed_at"))

        def out(state: str, reason: str) -> Dict[str, Any]:
            return {"state": state, "reason": reason, "penalty": penalty, "claim_id": claim_id}

        fee = f"；站点按规则收 {penalty} 放弃费" if penalty else ""
        if not ((prof or {}).get("abandon_endpoint") or {}).get("path"):
            return out("unsupported", "该站未提供「放弃认领」接口，需到站点操作")
        if not claim_id:
            return out("unknown", "站点未回发认领记录 id，判断不出放弃是否安全")
        if qualified is True:
            return out("safe", f"本月已达标：放弃不触发未达标罚{fee}")
        if qualified is None:
            return out("unknown", "站点未回发本颗达标状态，判断不出放弃是否安全")
        # qualified is False：未达标 → 看豁免期
        unq = int(p.get("unsatisfied") or 0)
        if exempt and days is not None and days < exempt:
            # 站点口径（咖啡 rules.php 认领规则原文）：首月未达标只是「本月不计奖励、认领记录保持」，
            # 未达标罚（扣 3000）明确标注「非认领首月」；放弃费则任何时点都收。
            tail = f"（本月不计奖励、记录保持，不触发{unq}未达标罚）" if unq else ""
            return out("grace", f"未达标，但认领 {days:.1f} 天仍在首 {exempt} 天豁免期{tail}{fee}")
        left = "" if days is None else f"（已认领 {days:.1f} 天，过 {exempt} 天豁免）" if exempt else ""
        keep = f"；继续持有会被删种并扣 {unq}" if unq else ""
        return out("blocked", f"未达标{left}{keep}，放弃{fee or '按站点未达标处理'}")

    # ------------------------------------------------------------------ 扫描
    def _claim_site_rows(self, site: Any, refresh: bool = False) -> Dict[str, Any]:
        """★ 19.10.49：抓站点「我的种子」列表行 —— 认领判定的**事实源**（按站缓存）。

        站点在这一页里把答案写全了：``data-torrent_id``（细节页号）、``data-claim_id``
        （``0``=可认领未认领 / 非 ``0``=已认领）、发布时间、做种时长。

        在这之前 ``claimable`` 全靠本地 qB + 本地「发布时间」+ ``min_age`` 推算，任一环
        断了就**静默丢弃**（既不进可认领、也只在个别分支进「快到期」），界面表现为
        「没有能认领的新种子」。实测 11 个支持站站点侧共 633 个可领未领，插件报 0。

        返回 ``{'at','uid','rows','pages','declared_total','error'}``；
        缓存按站点 id，TTL 复用 ``CLAIM_SITE_TTL``（10 分钟）。
        """
        sid = str(getattr(site, "id", "") or "")
        cache = getattr(self, "_claim_rows_cache", None)
        if cache is None:
            cache = {}
            try:
                self._claim_rows_cache = cache
            except Exception:  # noqa: BLE001
                pass
        hit = cache.get(sid)
        if not refresh and hit and (time.time() - float(hit.get("at") or 0)) < CLAIM_SITE_TTL:
            return hit
        uid = ""
        try:
            uid = str(self._site_user_id(site) or "")
        except Exception:  # noqa: BLE001
            uid = ""
        if not uid:
            try:
                ctx = self._claim_site_ctx(site)
                uid = self._claim_discover_uid(site, ctx, str(ctx.get("url") or "").rstrip("/"))
            except Exception:  # noqa: BLE001
                uid = ""
        if not uid:
            return {}
        try:
            data = fetch_user_torrent_rows(site, uid, ttype="seeding")
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领做种行读取失败 {sid}: {err}")
            return {}
        if not data or not data.get("rows"):
            return {}
        out = {
            "at": time.time(),
            "uid": uid,
            "rows": data.get("rows") or [],
            "pages": int(data.get("pages") or 0),
            "declared_total": data.get("declared_total"),
            "error": data.get("error") or "",
        }
        cache[sid] = out
        return out

    def _claim_site_rows_invalidate(self, site_id: Any = None) -> None:
        """★ 19.10.55：作废站点行缓存（不重抓，只丢，下次用到时自然重取）。

        站点行缓存 ``CLAIM_SITE_TTL``=600s，而认领是**秒级生效**的写动作。不作废
        的话，认领成功后重建整页仍会读到「这一颗还是 open」的旧行 —— 用户看到
        「认领完了还在可认领里」，等 10 分钟才自己好，且期间再点一次会重复提交。

        ``site_id`` 为空时清全部（代价是下次扫描重抓整轮站点行）。
        """
        cache = getattr(self, "_claim_rows_cache", None)
        if not isinstance(cache, dict):
            return
        sid = str(site_id or "").strip()
        if sid:
            cache.pop(sid, None)
        else:
            cache.clear()

    def _claim_site_rows_mark(self, site_id: Any, tid: Any, claimed: bool = True) -> bool:
        """★ 19.10.55：写动作成功后**就地**改站点行缓存里那一颗的状态。

        比「清站重抓」精确得多：认领完前端重新拉列表时，这颗已经是 claimed，
        不用为了一颗种重抓整站（实测整页重抓 27s，前端像卡死）。
        缓存里没这一行（还没抓过 / 行被换掉）就返回 False，由调用方退回清站。
        """
        cache = getattr(self, "_claim_rows_cache", None)
        if not isinstance(cache, dict):
            return False
        d = cache.get(str(site_id or "").strip())
        if not isinstance(d, dict):
            return False
        tid_s = str(tid or "").strip()
        if not tid_s:
            return False
        for r in d.get("rows") or []:
            if str(r.get("tid") or "") != tid_s:
                continue
            if claimed:
                r["claim_state"] = "claimed"
                # claim_id 非 0 是「已认领」的判据；真值站点下次刷新会覆盖成真号
                if not r.get("claim_id"):
                    r["claim_id"] = -1
            else:
                r["claim_state"] = "open"
                r["claim_id"] = 0
            return True
        return False

    def _claim_fill_by_details(self, site: Any, data: Dict[str, Any], limit: int = 30) -> bool:
        """★ 19.10.49：viewclaims 型站的兜底判定 —— 逐个开种子详情页看认领按钮。

        学校（pt.btschool.club）这类老式认领站，做种列表整页**没有** ``data-claim_id``
        （实测连 ``claim`` 字样都搜不到），``parse_user_torrent_rows`` 对它只能给出
        ``claim_state='none'``。它的认领入口只在种子详情页：未认领有
        ``add_torrent_id`` 链接，已认领整行消失。

        只在「本站在做种的种子」这个有限集合上跑（一颗一次请求）。**绝不扫全站** ——
        学校 2274 页 ≈ 25 万颗，且实测新种也带按钮（可认领率 ~100%），扫全站既
        没有筛选价值，也会把站点打爆。

        原地把 ``rows[i]['claim_state']`` 补成 ``open`` / ``claimed``；补到了返回 True。
        """
        sid = str(getattr(site, "id", "") or "")
        try:
            prof = self._claim_profile(site)
        except Exception:  # noqa: BLE001
            return False
        page_tpl = str(prof.get("claim_page") or "")
        sel = str(prof.get("detail_selector") or "")
        if "{id}" not in page_tpl or not sel:
            return False
        rows = data.get("rows") or []
        tids = [str(r.get("tid") or "") for r in rows if str(r.get("tid") or "").isdigit()]
        if not tids:
            return False
        if len(tids) > limit:
            tids = tids[:limit]
        try:
            from ..sites.formula_fetch import fetch_claim_open_by_details  # noqa: WPS433

            got = fetch_claim_open_by_details(site, tids, page_tpl, sel, limit=limit)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领详情页判定失败 {sid}: {err}")
            return False
        if not got:
            return False
        for r in rows:
            tid = str(r.get("tid") or "")
            if tid in got:
                r["claim_state"] = "open" if got[tid] else "claimed"
        data["claim_source"] = "details"
        return True

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

    def _claim_scan(self, site_id: Any = None, upcoming: int = 20, limit: int = 0, refresh_site: bool = False,
                    local_only: bool = True) -> Dict[str, Any]:
        """扫一遍「可认领 / 已认领 / 快到期」。

        ★ 19.10.51 **默认只列我本地有的**（``local_only=True``）。站点说能领但我本地
        没这颗种的，领了还得重新下载，属于「要不要补种」的另一类决策，不该混进
        「该领哪些」的清单。传 ``local_only=0`` 可看全量（含 ``in_local=false``）。
        被过滤掉的数量照报在 ``site_not_local`` / ``not_local_total``，**绝不静默丢弃**。

        ★ 19.10.49 **事实源换人**：可认领不再由本地推算，改读站点「我的种子」列表
        行里的 ``data-claim_id``（``0``=可领 / 非 ``0``=已领 / 无按钮=站点未开放）。
        本地 qB 只负责标 ``in_local``（这颗种我本地有没有）和提供时魔。
        认亲四路（``match_by``）：tid → 严格标题 → **松标题（抹平集数写法）** → 体积唯一。

        为什么换：旧版 ``claimable = 本地托管 ∧ 有 tid ∧ 有发布时间 ∧ 满 min_age``，
        而 tid 与发布时间都靠「标题逐字匹配」回填 —— 站点会把
        ``S01.Complete`` 改写成 ``S01E11``、``H.265``→``H265``、``Blu-ray``→``BLURAY``，
        实测咖啡 160 个只命中 59 个（37%），其余**静默消失**：既不在可认领，也不在
        快到期。站点侧那 633 个可领就是被这么吃掉的。

        站点范围 = **全部已配置站点**（``_claim_site_universe``）；未收录认领能力的站
        也出现在 ``sites`` 里（``supported=False``），并由 ``sites_skipped`` 计数。
        ``limit>0`` 时只回前 N 条可认领（按满月预计收益降序）。

        ★ 本方法**永不发写请求**；真写只在 ``run_claim(write=1, confirm=1)`` 且设置里
        关闭「干跑」时才发生（干跑/真跑两个动作彻底分开，19.5.0）。
        """
        cfg = self._claim_cfg()
        now = time.time()
        ledger = self._claim_ledger()
        try:
            snap = dict(self._tag_all_torrents() or {})
        except Exception:  # noqa: BLE001
            snap = {}
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

        # ①' ★ 19.10.49：先把「站点我的种子列表」并行抓回来 —— 认领判定的真值源。
        #     站点每行自带 data-claim_id（0=可领 / 非0=已领）与发布时间，比本地用
        #     「标题匹配 + 满 N 天」推算可靠得多（后者在咖啡只命中 37%）。
        truth: Dict[str, Dict[str, Any]] = {}
        truth_targets = []
        for sid_s0, row_s0 in per_site.items():
            if not row_s0.get("supported"):
                continue
            try:
                site_obj0 = self._get_site(int(sid_s0))
            except Exception:  # noqa: BLE001
                site_obj0 = None
            if site_obj0:
                truth_targets.append((sid_s0, site_obj0))
        if truth_targets:
            from concurrent.futures import ThreadPoolExecutor  # noqa: WPS433

            def _fetch_rows(item):
                sid_s1, site_obj1 = item
                return sid_s1, site_obj1, self._claim_site_rows(site_obj1)

            try:
                with ThreadPoolExecutor(max_workers=min(5, len(truth_targets))) as ex:
                    for sid_s1, site_obj1, d1 in ex.map(_fetch_rows, truth_targets):
                        if not d1 or not d1.get("rows"):
                            continue
                        # 只有「这一页确实表达认领状态」的站才算真值源。
                        if any(str(r.get("claim_state") or "") != "none" for r in d1["rows"]):
                            truth[sid_s1] = d1
                            continue
                        # 整页无认领字段 = 学校这类 viewclaims 型站：改用详情页判定
                        # （认领入口只在种子详情页，做种列表里压根没有）。
                        # 只在「本站在做种的种子」上跑，不扫全站。
                        try:
                            if self._claim_fill_by_details(site_obj1, d1):
                                truth[sid_s1] = d1
                        except Exception as err2:  # noqa: BLE001
                            logger.debug(f"认领详情页兜底失败 {sid_s1}: {err2}")
            except Exception as err:  # noqa: BLE001
                logger.debug(f"认领做种行并行抓取失败: {err}")

        # ② 任务循环只负责「往行里记种」：站点集合已由上一步定好；同一颗种跨任务
        #    只记一次（``seen`` 防重复计数）。
        seen: set = set()
        # 本地资源索引（按站点）：给站点行标「本地有没有这颗种」，没标到就只展示不可领
        local_tid: Dict[str, Dict[str, str]] = {}
        local_norm: Dict[str, Dict[str, str]] = {}
        # ★ 19.10.51：松索引（抹平集数写法）。只在严格索引落空后**等值**兜底，
        #   且仅当该松 key 全站唯一时才敢认 —— 松 key 丢了集数，多义就会认错种。
        local_loose: Dict[str, Dict[str, List[str]]] = {}
        local_size: Dict[str, Dict[float, List[str]]] = {}
        hb_map: Dict[str, float] = {}
        for task in self._claim_tasks():
            sid = int(getattr(task, "site_id", 0) or 0)
            row = per_site.get(str(sid))
            if row is None or not row.get("supported"):
                continue
            prof = dict(row.get("profile") or {})
            settle = dict(row.get("settlement") or {})
            sname = str(row.get("site_name") or sid)
            # ★ 19.10.60：站点门槛与用户门槛取**更严者**（旧写法 cfg 覆盖会放宽站点门槛）
            min_age = _claim_min_age(cfg.get("min_age_days"), prof.get("min_age_days"))
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
            _in_truth = str(sid) in truth
            if _in_truth:
                for _k, _v in (bonus or {}).items():
                    try:
                        hb_map[str(_k).lower()] = float(_v or 0.0)
                    except (TypeError, ValueError):
                        continue
            for tr in managed:
                h = str(getattr(tr, "hash", "") or "").strip().lower()
                if not h:
                    continue
                key = f"{sid}:{h}"
                if key in seen:
                    continue
                seen.add(key)
                if _in_truth:
                    _tid0 = _torrent_id_of(pages.get(h))
                    if _tid0:
                        local_tid.setdefault(str(sid), {}).setdefault(str(_tid0), h)
                    _nt = normalize_title(str(getattr(tr, "title", "") or ""))
                    if _nt:
                        local_norm.setdefault(str(sid), {}).setdefault(_nt, h)
                        _lt = normalize_title_loose(str(getattr(tr, "title", "") or ""))
                        if _lt:
                            local_loose.setdefault(str(sid), {}).setdefault(_lt, []).append(h)
                    _z = round(float(getattr(tr, "size_gb", 0) or 0), 2)
                    if _z > 0:
                        local_size.setdefault(str(sid), {}).setdefault(_z, []).append(h)
                rec = ledger.get(key) if isinstance(ledger.get(key), dict) else None
                hb = round(float(bonus.get(h, 0.0) or 0.0), 4)
                est_m = _est_month_bonus(hb, settle)
                base = {
                    "site_id": sid,
                    "site_name": sname,
                    "site_domain": str((per_site.get(str(sid)) or {}).get("domain") or ""),
                    "hash": h,
                    "task": str(getattr(task, "id", "") or ""),
                    "title": str(getattr(tr, "title", "") or "")[:200],
                    "size_gb": round(float(getattr(tr, "size_gb", 0) or 0), 3),
                    "seeders": int(ni.get(h, -1) if h in ni else -1),
                    "torrent_id": _torrent_id_of(pages.get(h)) or (rec or {}).get("tid", ""),
                    "hourly_bonus": hb,
                    "est_month_bonus": est_m,
                    # ★ 19.10.53：与站点真值行同口径，界面不用区分两条通道
                    "digest": title_digest(str(getattr(tr, "title", "") or "")),
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
                                    # ★ 19.10.55：账本存的是**站点标题**（认领时从那行拿的），
                                    #   而 base.title 是 qB 本地标题。站点回来说「这颗我记着
                                    #   已认领」时要靠它把两条认成同一颗（本地名与站点名
                                    #   常不一样，比如 Friends S10 …HHWEB 尾巴）。
                                    "site_title": str(rec.get("title") or ""),
                                    "state": str(rec.get("st")), "benefit": str(rec.get("benefit") or ""),
                                    "seed_hours": round(hours, 1),
                                    "est_payout_now": payout_now,
                                    "note": str(rec.get("note") or ""),
                                    "qb_state": str(getattr(snap.get(h), "state", "") or ""),
                                    "in_qb": h in snap,
                                    "progress": float(getattr(snap.get(h), "progress", 0) or 0)})
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
                if _in_truth:
                    # 站点已给真值 → 本地推算不再冒充「可认领 / 快到期」（19.10.49）
                    continue
                if any("未满" in r or "无发布时间" in r for r in reasons):
                    _w = None
                    if min_age and age_days is not None and age_days < min_age:
                        _w = round(min_age - float(age_days), 1)
                    soon.append({**base, "age_days": age_days, "block": reasons, "wait_days": _w})
                    continue
                if reasons:
                    continue
                row["claimable"] += 1
                row["hourly_bonus_total"] += hb
                row["est_month_bonus_total"] += est_m
                payout_pot = _est_settle_payout(hb, settle)
                row["est_claimable_payout_total"] += payout_pot
                claimable.append({**base, "age_days": age_days, "profile_min_age": prof.get("min_age_days"),
                                  # ★ 19.10.60：能领 ≠ 有魔力。站点发奖门槛单独给出（空串=无门槛）
                                  "reward_block": _reward_gate(prof, age_days, base.get("size_gb")),
                                  "est_settle_payout": payout_pot})
        # ②' ★ 19.10.49：站点真值 → 「可认领」按 data-claim_id 判定，不再本地推算。
        #     同一颗种三路认亲：tid（详情页回填过才准）→ 规范化标题 → **体积唯一**。
        #     认不到本地资源的照样列出（in_local=False）：让你看得见「站点说能领、
        #     但我本地没这颗种」，那属于「要不要重下」的决策，不该被隐藏。
        for sid_s, d_row in truth.items():
            row_s = per_site.get(sid_s)
            if row_s is None:
                continue
            settle_s = dict(row_s.get("settlement") or {})
            idx_t = local_tid.get(sid_s) or {}
            idx_n = local_norm.get(sid_s) or {}
            idx_l = local_loose.get(sid_s) or {}
            idx_z = local_size.get(sid_s) or {}
            open_cnt = none_cnt = claimed_cnt = 0
            not_local_cnt = 0
            for r in d_row.get("rows") or []:
                state = str(r.get("claim_state") or "")
                tid_r = str(r.get("tid") or "")
                # ★ 19.10.55：``claimed`` 不再提前 continue —— 站点说已认领的行也要
                #   认亲、也要进「已认领」列表（见下方 basis 之后的分支）。
                #   旧写法只 ``claimed_cnt += 1`` 就丢，后果是用户在站点网页上自己
                #   认领的种**两栏都看不到**：不在可认领（对，已领），也不在已认领
                #   （错，账本没记录），看起来像凭空消失。
                # ★ 19.10.51 四路认亲（顺序即可信度）：
                #   ① tid（详情页回填过才准） ② 严格标题 ③ **松标题**（抹平集数写法）
                #   ④ 体积唯一。③④ 只在全站唯一命中时才敢认，多义一律算认不出。
                h_local = idx_t.get(tid_r) or idx_n.get(str(r.get("title_norm") or "")) or ""
                match_by = "tid" if (h_local and tid_r and idx_t.get(tid_r)) else (
                    "title" if h_local else "")
                if not h_local:
                    _lk = normalize_title_loose(str(r.get("title") or ""))
                    cand = idx_l.get(_lk) if _lk else None
                    if isinstance(cand, list) and len(cand) == 1:
                        h_local, match_by = cand[0], "loose"
                if not h_local:
                    _z = round(float(r.get("size_bytes") or 0) / float(1024 ** 3), 2)
                    cand = idx_z.get(_z) if _z > 0 else None
                    if isinstance(cand, list) and len(cand) == 1:
                        h_local, match_by = cand[0], "size"
                in_local = bool(h_local)
                hb = round(float(hb_map.get(h_local, 0.0) or 0.0), 4)
                age_days = None
                pub = str(r.get("pubdate") or "")
                if pub:
                    try:
                        age_days = round(
                            (now - time.mktime(time.strptime(pub, "%Y-%m-%d %H:%M:%S"))) / 86400.0, 2)
                    except Exception:  # noqa: BLE001
                        age_days = None
                basis = {
                    "site_id": int(sid_s),
                    "site_name": str(row_s.get("site_name") or sid_s),
                    # ★ 19.10.53：站点域名给界面拼「详情页」链接。站点把中文片名转成拼音
                    #   （唐朝诡事录之长安 → Tang Chao Gui Shi Lu Zhi Chang An），列表里
                    #   认不出是哪部片；翻译这条路在本机不可用（识别链 32s/次且返空），
                    #   最省事且最准的办法是让人一键跳到站点详情页看原名与简介。
                    "site_domain": str(row_s.get("domain") or ""),
                    "hash": h_local,
                    "task": "",
                    "title": str(r.get("title") or "")[:200],
                    "size_gb": round(float(r.get("size_bytes") or 0) / float(1024 ** 3), 2),
                    "seeders": -1,
                    "torrent_id": tid_r,
                    "hourly_bonus": hb,
                    "est_month_bonus": _est_month_bonus(hb, settle_s),
                    "age_days": age_days,
                    "site_pubdate": pub,
                    "site_seed_seconds": r.get("seed_seconds"),
                    "in_local": in_local,
                    "match_by": match_by,
                    "source": "site",
                    # ★ 19.10.53：站点标题是英文发布名（「Battle of Britain 1969 AUS
                    #   UHD BluRay 2160p REMUX …」），用户在列表里认不出是哪部片，
                    #   也判断不了值不值得承诺保种。附一份**零成本**的结构化规格，
                    #   界面至少能排出「1969 · 2160p · REMUX · 电影」。
                    "digest": title_digest(r.get("title")),
                }
                # ★ 19.10.55：站点说已认领 → 进「已认领」列表。
                #   账本里已有同一条就**不重复**加。判重不能只看 hash：站点行常常
                #   认亲失败（hash=''），而账本按 ``sid:hash`` 存 —— 光比 hash 会让
                #   同一颗种在「已认领」里出现两次（一条账本 ok、一条站点侧，
                #   实测 咖啡 tid=122005 就是这个现象）。故 hash 落空时按 tid 查重。
                if state == "claimed":
                    claimed_cnt += 1
                    rec_c = ledger.get(f"{sid_s}:{h_local}") if h_local else None
                    if not (isinstance(rec_c, dict) and str(rec_c.get("st")) in ("ok", "already")) \
                            and tid_r:
                        for _k_c, _v_c in ledger.items():
                            if (isinstance(_v_c, dict) and str(_v_c.get("tid") or "") == tid_r
                                    and str(_k_c).partition(":")[0] == str(sid_s)):
                                rec_c = _v_c
                                break
                    if isinstance(rec_c, dict) and str(rec_c.get("st")) in ("ok", "already"):
                        continue
                    # 再按「已列表里是否已有这颗」兜底合并。账本老记录可能**没有 tid**
                    # （claimed 行的 tid 是从 torrent_pages 反查来的），认亲又拿不到
                    # hash —— 唯一还能对上的就是「同站 + 标题完全一致」。这里只用于
                    # **合并展示**（顺手把缺的 tid 补上），不用于认领动作，风险可控。
                    _dup_row = None
                    if tid_r:
                        _dup_row = next(
                            (x for x in claimed
                             if str(x.get("site_id")) == str(sid_s)
                             and str(x.get("torrent_id") or "") == tid_r), None)
                    if _dup_row is None:
                        _tt = str(r.get("title") or "")
                        if _tt:
                            _dup_row = next(
                                (x for x in claimed
                                 if str(x.get("site_id")) == str(sid_s)
                                 and _tt in (str(x.get("site_title") or ""),
                                             str(x.get("title") or ""))), None)
                    if _dup_row is not None:
                        if tid_r and not str(_dup_row.get("torrent_id") or ""):
                            _dup_row["torrent_id"] = tid_r
                            _dup_row["site_domain"] = basis.get("site_domain") or ""
                            _dup_row["digest"] = _dup_row.get("digest") or basis.get("digest")
                        _dup_row["site_claim_id"] = r.get("claim_id")
                        continue
                    _t_c = snap.get(h_local) if h_local else None
                    claimed.append({
                        **basis,
                        "ts": 0.0,
                        "state": "site",
                        "benefit": "",
                        "seed_hours": 0.0,
                        "est_payout_now": 0.0,
                        "note": "站点侧已认领（本地账本无记录）",
                        "qb_state": str(getattr(_t_c, "state", "") or ""),
                        "in_qb": bool(h_local and h_local in snap),
                        "progress": float(getattr(_t_c, "progress", 0) or 0),
                        "site_only": True,
                    })
                    row_s["claimed"] = int(row_s.get("claimed") or 0) + 1
                    continue
                if state == "open":
                    # ★ 19.10.55：**账本优先于站点行**。站点行可能是认领前抓的旧快照
                    #   （站点行缓存 600s / 站点列表本身有延迟），而账本是我们刚写成功
                    #   的事实。只在认亲拿到 hash 时才敢据账本排除 —— 认不出就不猜，
                    #   照旧列出来让人自己核对（宁多列，不错列）。
                    _rec_o = ledger.get(f"{sid_s}:{h_local}") if h_local else None
                    if isinstance(_rec_o, dict) and str(_rec_o.get("st")) in ("ok", "already"):
                        claimed_cnt += 1
                        continue
                    open_cnt += 1
                    if not in_local:
                        # 只数「站点说可领、但本地认不出」的 —— 语义必须等于
                        # 全量口径与默认口径的**差值**，用户才能一眼对上账。
                        not_local_cnt += 1
                    # ★ 19.10.51 用户口径：**只列我本地有的**。
                    #   站点说能领但本地没这颗的，领了也得重新下载，属于「要不要补种」
                    #   的另一类决策，不该混进「该领哪些」的清单。数量照报（不静默丢）。
                    if local_only and not in_local:
                        pass
                    else:
                        row_s["claimable"] = int(row_s.get("claimable") or 0) + 1
                        payout_pot = _est_settle_payout(hb, settle_s)
                        row_s["hourly_bonus_total"] += hb
                        row_s["est_month_bonus_total"] += float(basis["est_month_bonus"])
                        row_s["est_claimable_payout_total"] += payout_pot
                        claimable.append({**basis, "est_settle_payout": payout_pot,
                                          # ★ 19.10.60：站点说能领，但「这个月有没有魔力」是另一条门槛
                                          "reward_block": _reward_gate(row_s.get("profile") or {},
                                                                        age_days, basis.get("size_gb")),
                                          "profile_min_age": (row_s.get("profile") or {}).get("min_age_days")})
                elif state == "none":
                    none_cnt += 1
                    if in_local:
                        # ★ 19.10.53：新下的种子为什么不出现在「可认领」——站点对这颗
                        #   压根没给认领按钮，因为它**还没到资格日**（多数站发布满 7 天，
                        #   CARPT/Depth 满 30 天）。旧版这里统一写成「站点未开放认领」，
                        #   等于把「你还得等 5 天」误报成「这个站不支持」——新种用户会
                        #   以为自己被漏扫。现在按发布时间算真实倒计时，说清楚还差几天。
                        _min_age = float((row_s.get("profile") or {}).get("min_age_days") or 0)
                        wait_days = None
                        block = ["站点未开放认领（该行没有认领入口）"]
                        if _min_age > 0 and age_days is not None and float(age_days) < _min_age:
                            wait_days = round(_min_age - float(age_days), 1)
                            block = [f"未满 {_min_age:g} 天，还差 {wait_days:g} 天可领"]
                        soon.append({**basis, "block": block, "wait_days": wait_days})
            row_s["site_open"] = open_cnt
            row_s["site_none"] = none_cnt
            row_s["site_claimed"] = claimed_cnt
            row_s["site_rows"] = len(d_row.get("rows") or [])
            row_s["site_pages"] = int(d_row.get("pages") or 0)
            row_s["site_declared"] = d_row.get("declared_total")
            # 站点说能领、但本地认不出资源的条数（含「真没有」与「认亲失败」两种可能）。
            # ★ 铁律 8/11：绝不能静默丢弃 —— 认不出来的必须让它在数字上可见。
            row_s["site_not_local"] = not_local_cnt
        # ★ 19.7.0：账本里有、但不在任务管辖内的已认领种也要出现在「已认领」列表。
        for key, rec2 in ledger.items():
            if not isinstance(rec2, dict) or str(rec2.get("st")) not in ("ok", "already"):
                continue
            if key in seen:
                continue
            sid_s, _, h2 = str(key).partition(":")
            try:
                sid2 = int(sid_s)
            except (TypeError, ValueError):
                continue
            h2 = h2.strip().lower()
            if not h2:
                continue
            t2 = snap.get(h2)
            hours2 = max(0.0, (now - float(rec2.get("ts") or 0)) / 3600.0)
            row2 = per_site.get(str(sid2))
            if want and row2 is None:
                continue
            claimed.append({
                "site_id": sid2,
                "site_name": str((row2 or {}).get("site_name") or sid2),
                "hash": h2,
                "task": str(rec2.get("task") or ""),
                "title": str(rec2.get("title") or "")[:200],
                "size_gb": round(float(getattr(t2, "size_gb", 0) or 0), 3) if t2 else 0,
                "seeders": -1,
                "torrent_id": str(rec2.get("tid") or ""),
                "hourly_bonus": 0.0,
                "est_month_bonus": 0.0,
                "ts": float(rec2.get("ts") or 0),
                "state": str(rec2.get("st") or ""),
                "benefit": str(rec2.get("benefit") or ""),
                "seed_hours": round(hours2, 1),
                "est_payout_now": 0.0,
                "note": str(rec2.get("note") or ""),
                "qb_state": str(getattr(t2, "state", "") or "") if t2 else "",
                "in_qb": t2 is not None,
                "progress": float(getattr(t2, "progress", 0) or 0) if t2 else 0.0,
            })
            seen.add(key)
            if row2 is not None:
                row2["claimed"] += 1
                row2["claimed_hours_total"] += hours2
        # ★ 19.7.1：站点口径覆盖（本月做种 / 上传 / 达标 / 预计奖励）。
        # ★ 19.7.5：先并行抓取，避免 6 个站串行把 /claim 拖到 60s+。
        site_calc: Dict[str, Any] = {}
        prefetched: Dict[str, Any] = {}
        targets = []
        for sid_s0, row_s0 in per_site.items():
            # ★ 19.10.11：站点侧认领页（claim_list 非空）一律纳入抓取——本地账本
            # 为空时也要拉。站点口径是真值，可据此恢复账本（此前只放行 viewclaims，
            # 财神/CARPT 等 claim.php?uid= 站点在账本丢失后认领页根本不被拉取，
            # 表现为「认领数据没了」，实际是扫描不看、不是站点没数据）。
            if not str((row_s0.get("profile") or {}).get("claim_list") or "").strip():
                continue
            try:
                site_obj0 = self._get_site(int(sid_s0))
            except Exception:  # noqa: BLE001
                site_obj0 = None
            if site_obj0:
                targets.append((sid_s0, site_obj0))
        if targets and refresh_site:
            from concurrent.futures import ThreadPoolExecutor  # noqa: WPS433

            def _fetch_one(item):
                sid_s1, site_obj1 = item
                return sid_s1, self._claim_site_claims(site_obj1, refresh=True)

            try:
                with ThreadPoolExecutor(max_workers=min(6, len(targets))) as ex:
                    for sid_s1, data1 in ex.map(_fetch_one, targets):
                        prefetched[sid_s1] = data1
            except Exception as err:  # noqa: BLE001
                logger.debug(f"认领站点口径并行抓取失败: {err}")
        elif targets:
            # 19.7.18: default cache-only; 19.7.27: cold viewclaims sites fetch once;
            # 19.10.11: 有认领页的站都冷抓一次（站点侧认领可显示/可恢复；之后按缓存）
            cache0 = getattr(self, "_claim_site_cache", {}) or {}
            cold = []
            for sid_s1, site_obj1 in targets:
                cached = cache0.get(sid_s1)
                if cached:
                    prefetched[sid_s1] = cached
                    continue
                cold.append((sid_s1, site_obj1))
            if cold:
                from concurrent.futures import ThreadPoolExecutor  # noqa: WPS433
                def _fetch_cold(item):
                    sid_s1, site_obj1 = item
                    return sid_s1, self._claim_site_claims(site_obj1, refresh=True)
                try:
                    with ThreadPoolExecutor(max_workers=min(4, len(cold))) as ex:
                        for sid_s1, data1 in ex.map(_fetch_cold, cold):
                            prefetched[sid_s1] = data1
                except Exception as err:  # noqa: BLE001
                    logger.debug(f"claim site cold fetch failed: {err}")

        for sid_s, row_s in per_site.items():
            # ★ 19.10.11：与 targets 同口径——有认领页就合并站点侧数据（站点侧
            # 认领行以 site_only 显示/供恢复），不再要求本地已有认领才看站点页。
            if not str((row_s.get("profile") or {}).get("claim_list") or "").strip():
                continue
            data_s = prefetched.get(sid_s) or {}
            if not data_s:
                continue
            by_tid = data_s.get("by_tid") or {}
            site_calc[sid_s] = data_s.get("summary") or {}
            for r in claimed:
                if str(r.get("site_id")) != sid_s:
                    continue
                srow = by_tid.get(str(r.get("torrent_id") or ""))
                if not srow:
                    continue
                r["site_seed_time"] = srow.get("seed_time")
                r["site_seed_hours"] = srow.get("seed_hours")
                r["site_upload"] = srow.get("upload")
                # ★ 19.10.58：保持三态（True/False/None），不 bool() 压平 ——
                #   「站点没说」与「站点说没达标」在「能不能安全放弃」里是完全不同的答案。
                r["site_qualified"] = srow.get("qualified")
                r["site_reward"] = srow.get("reward")
                r["site_reward_num"] = srow.get("reward_num")
                r["site_claimed_at"] = srow.get("claimed_at")
                r["site_last_settle"] = srow.get("last_settle")
                r["site_alive"] = srow.get("alive")
                r["site_claim_id"] = srow.get("claim_id")
                r["calc_source"] = "site"
                if srow.get("seed_hours") is not None:
                    r["seed_hours"] = srow["seed_hours"]
                if srow.get("reward_num") is not None:
                    r["est_payout_now"] = float(srow["reward_num"]) if srow.get("qualified") else 0.0
            known_tids = {str(x.get("torrent_id")) for x in claimed if str(x.get("site_id")) == sid_s}
            for tid_s, srow in by_tid.items():
                if tid_s in known_tids:
                    continue
                if not _re.match(r"\d{4}-\d{2}-\d{2}", str(srow.get("claimed_at") or "")):
                    continue
                title_s = str(srow.get("title") or "")
                if "本月做种时间" in title_s or "种子名称" in title_s:
                    continue
                hours_s = float(srow.get("seed_hours") or 0)
                payout_s = float(srow.get("reward_num") or 0) if srow.get("qualified") else 0.0
                claimed.append({
                    "site_id": int(sid_s),
                    "site_name": str(row_s.get("site_name") or sid_s),
                    "hash": "",
                    "task": "",
                    "title": str(srow.get("title") or "")[:200],
                    "size_gb": 0,
                    "seeders": -1,
                    "torrent_id": tid_s,
                    "hourly_bonus": 0.0,
                    "est_month_bonus": 0.0,
                    "ts": 0,
                    "state": "site",
                    "benefit": "",
                    "seed_hours": round(hours_s, 1),
                    "est_payout_now": float(srow.get("reward_num") or 0) if srow.get("qualified") else 0.0,
                    "note": "站点侧认领",
                    "qb_state": "",
                    "in_qb": False,
                    "site_only": True,
                    "site_seed_time": srow.get("seed_time"),
                    "site_seed_hours": srow.get("seed_hours"),
                    "site_upload": srow.get("upload"),
                    "site_qualified": srow.get("qualified"),
                    "site_reward": srow.get("reward"),
                    "site_reward_num": srow.get("reward_num"),
                    "site_claimed_at": srow.get("claimed_at"),
                    "site_last_settle": srow.get("last_settle"),
                    "site_next_settle": srow.get("next_settle"),
                    "site_claim_id": srow.get("claim_id"),
                    "calc_source": "site",
                })
                if row_s is not None:
                    row_s["claimed"] = int(row_s.get("claimed") or 0) + 1
                    row_s["claimed_hours_total"] += hours_s
                    row_s["est_payout_now_total"] += payout_s
        # ★ 19.10.49：站点口径补「可领 / 未开放 / 已领」三档（来自做种行的 claim 状态）
        for sid_s, row_s in per_site.items():
            if sid_s not in truth:
                continue
            sc = site_calc.get(sid_s)
            if not isinstance(sc, dict):
                sc = site_calc[sid_s] = {}
            sc["open"] = int(row_s.get("site_open") or 0)
            sc["none"] = int(row_s.get("site_none") or 0)
            sc["rows"] = int(row_s.get("site_rows") or 0)
            sc["claim_rows_claimed"] = int(row_s.get("site_claimed") or 0)
            if row_s.get("site_declared") is not None:
                sc["declared"] = row_s.get("site_declared")
        # ★ 19.10.58：每条「已认领」都算一次「能不能**安全**放弃」——
        #   放弃是用户行为、带罚则（未达标时按站点罚则扣魔力），判断只在后端算一次，
        #   前端只负责摆出结论与依据（不在浏览器里重算，避免两套口径）。
        for r in claimed:
            prof_r = (per_site.get(str(r.get("site_id") or "")) or {}).get("profile") or {}
            verdict = self._claim_abandon_verdict(prof_r, r)
            r["abandon_state"] = verdict["state"]
            r["abandon_reason"] = verdict["reason"]
            r["abandon_penalty"] = verdict["penalty"]
            r["abandon_claim_id"] = verdict["claim_id"]
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
            # ★ 19.10.53：``soon`` 被 ``upcoming`` 截断过，单看长度会谎报。
            #   「还差几天可领」是用户判断「新种什么时候轮到」的唯一依据，必须给全量计数。
            "soon_total": len(soon),
            "settlement": settle_first,
            "est_month_bonus_total": round(
                sum(float(r.get("est_month_bonus_total") or 0.0) for r in per_site.values()), 1),
            "claimed_total": len(claimed),
            "claimable_total": claimable_total,
            # ★ 19.10.51：站点说能领、本地认不出资源的条数（不静默丢弃，UI 单独标注）。
            "not_local_total": sum(int(r.get("site_not_local") or 0) for r in per_site.values()),
            "local_only": bool(local_only),
            "host": self._claim_host_status(resume=False),
            "site_calc": site_calc,
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

    # ------------------------------------------------- 19.7.22 结果缓存（Redis）
    def _claim_state_gen(self) -> int:
        """缓存代际：账本一变就 +1，旧键自然失效（不用枚举删除）。"""
        try:
            return int(cache_get(self, "claim", "state_gen", 86400 * 30) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _claim_state_bump(self) -> None:
        try:
            cache_set(self, "claim", "state_gen", self._claim_state_gen() + 1, 86400 * 30)
        except Exception:  # noqa: BLE001
            pass
        # ★ 19.10.55：站点行缓存**不在**这里清 —— 这里只知道「账本变了」，不知道
        #   是哪颗种，清站就得重新抓整站（9 站并行实测 27s，前端会像卡死）。
        #   写动作自己在 ``claim_do`` / ``claim_abandon`` 里精确就地更新那一行。

    def _claim_state_key(self, site_id: str, limit: int, local_only: bool = True) -> str:
        """认领列表的缓存键：带版本号、代际号与 ``local_only`` 口径，任一变更即失效。"""
        from ..common import __version__ as _ver  # noqa: WPS433
        # ★ 19.10.51：``local_only`` 进 key —— 否则切开关会读到另一口径的旧缓存。
        return (f"state:{_ver}:{self._claim_state_gen()}:{site_id or 'all'}:"
                f"{int(limit or 0)}:lo{1 if local_only else 0}")

    def _claim_state_build(self, site_id: Any, limit: int, cache_key: str, refresh_site: bool = False,
                            local_only: bool = True) -> Dict[str, Any]:
        """真正算一遍并写缓存（计算很重：账本 + qB 快照 + 站点页）。"""
        data = self._claim_scan(site_id=site_id, limit=limit, refresh_site=refresh_site,
                                local_only=local_only)
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
        data["built_at"] = time.time()
        cache_set(self, "claim", cache_key, {"at": time.time(), "data": data}, CLAIM_STATE_STALE)
        return data

    def _claim_state_refresh(self, site_id: str, limit: int, local_only: bool = True) -> None:
        """后台刷新（同一 key 单飞，避免并发打站点）。"""
        key = self._claim_state_key(site_id, limit, local_only)
        # ★ 19.10.24：锁表改用 cacheops.KeyLocks，**非阻塞语义不变**（抢不到就跳过）。
        #   判定必须按类型：原来的 ``isinstance(locks, dict)`` 在换成 KeyLocks 后会
        #   **每次调用都重建**（KeyLocks 不是 dict）→ 后台刷新的「同 key 单飞」彻底失效；
        #   而只判 ``is None`` 又会让热重载残留的旧裸 dict 混进来（``dict.get()`` → None
        #   → ``acquire`` 抛 AttributeError）。故直接判 KeyLocks。
        locks = getattr(self, "_claim_state_locks", None)
        if not isinstance(locks, cacheops.KeyLocks):
            locks = self._claim_state_locks = cacheops.KeyLocks("claim.statelock", max_entries=64)
        guard = locks.get(key)
        if not guard.acquire(blocking=False):
            return
        try:
            self._claim_state_build(site_id or None, limit, key, refresh_site=True, local_only=local_only)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领缓存后台刷新失败：{err}")
        finally:
            guard.release()

    # ------------------------------------------------------------------ 只读端点
    def get_claim_state(self, site_id: Any = None, limit: Any = 0, refresh: Any = None,
                        local_only: Any = None) -> Response:
        """功能页数据：概览 / 能力卡 / 可认领 / 已认领 / 账本 / 记录。

        ``local_only``（默认 1）：可认领只列**我本地有资源**的；传 ``0`` 看站点全量。
        ★ 19.7.22：整份结果进 Redis 缓存（CLAIM_STATE_TTL 新鲜期，CLAIM_STATE_STALE
        内陈旧也直接返回并后台刷新）。refresh=1 强制重算。
        """
        try:
            sid = str(site_id).strip() if site_id not in (None, "", "0") else ""
            lim = self._claim_limit(limit)
            force = bool(as_bool_arg(refresh))
            # 不传 = 1（只列本地有的）；显式 0/false/no 才切全量
            lo = True if local_only in (None, "") else bool(as_bool_arg(local_only))
            key = self._claim_state_key(sid, lim, lo)
            if not force:
                hit = cache_get(self, "claim", key, CLAIM_STATE_STALE)
                if isinstance(hit, dict) and isinstance(hit.get("data"), dict):
                    age = max(0.0, time.time() - float(hit.get("at") or 0))
                    data = dict(hit["data"])
                    data["cached"] = True
                    data["cache_age"] = round(age, 1)
                    # ★ 19.10.13：``host`` 是**可变状态**（在种/暂停/丢失），不能跟着整页缓存陈旧
                    #   最多 1 小时 —— 运维看着旧读数会误判「又被暂停了」（实测：qB 里 19 个认领种
                    #   全 ``stalledUP``，页面却显示 ``paused=19`` 达半小时，据此排查了一整轮）。
                    #   站点侧数据（可认领/已认领/账本）照旧吃缓存：那才是打站点换来的重数据。
                    try:
                        _host = self._claim_host_status(resume=False)
                        _host["cache_age"] = 0.0
                        data["host"] = _host
                    except Exception as err:  # noqa: BLE001
                        logger.debug(f"认领宿主实时刷新失败（沿用缓存）：{err}")
                    if age > CLAIM_STATE_TTL:
                        try:
                            threading.Thread(
                                target=self._claim_state_refresh, args=(sid, lim, lo), daemon=True
                            ).start()
                        except Exception:  # noqa: BLE001
                            pass
                    return Response(success=True, data=data)
            data = self._claim_state_build(sid or None, lim, key, refresh_site=force, local_only=lo)
            data["cached"] = False
            data["cache_age"] = 0.0
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
        want_write = bool(as_bool_arg(write))
        dry_arg = as_bool_arg(dry)
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
        if not bool(as_bool_arg(confirm)):
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
                # ★ 19.10.55：站点行缓存就地改 claimed，否则前端重拉仍读旧行
                if not self._claim_site_rows_mark(sid, row.get("torrent_id"), True):
                    self._claim_site_rows_invalidate(sid)
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
        # ★ 19.10.52：批量跑完同样要让整页缓存失效（否则前端看不到刚领的这批）。
        if done:
            self._claim_state_bump()
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
        if not bool(as_bool_arg(confirm)):
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
        # ★ 19.10.52：写动作会改变「可认领 / 已认领」两个清单的归属，必须让整页
        #   缓存失效——否则前端 loadClaim() 拿回的还是认领前的快照，用户看到
        #   「点了没反应」（实测：claim_do 成功后列表仍列该种为可认领，直到 TTL 过期）。
        # ★ 19.10.55：整页 key 换了还不够 —— 重建时 `_claim_site_rows` 仍命中
        #   **认领前**抓的站点行（缓存 600s），那颗种照旧被判 open 又回到可认领。
        #   所以这里就地把它标成 claimed；标不到（缓存里没这行）才退回清该站重抓。
        #   实测：咖啡 唐朝诡事录 tid=122005 站点侧已 claim_id=147033，插件仍列可领。
        if res.get("ok"):
            if not self._claim_site_rows_mark(sid, tid, True):
                self._claim_site_rows_invalidate(sid)
        self._claim_state_bump()
        return Response(success=bool(res.get("ok")),
                        message=f"{'认领成功' if res.get('ok') else '认领失败'}：{res.get('message')}",
                        data={"result": res})

    def claim_abandon(self, site_id: Any = None, hash: str = "", torrent_id: Any = None,
                      confirm: Any = None) -> Response:
        """放弃认领：**先判「能不能安全放弃」，再发一次站点写请求**。

        ★ 19.10.58（Master 定调）：认领是带罚则的承诺，「放弃」在**未达标**时会被站点扣魔力
          （咖啡 −1000 / CARPT −500 / Depth −200 …）。所以放弃不是「想点就点」：

            · 站点判**本月已达标** → 安全：只失去 ×2 奖励，不触发未达标罚；
            · 未达标但在**首 N 天豁免期**内 → 安全：站点不按未达标处罚；
            · 未达标且已过豁免期 → **拒绝**（并告诉用户会扣多少），要放弃请到站点操作；
            · 站点没回发达标状态 / 没回发认领记录 id → **拒绝**（算不出来就别拿用户的魔力赌）；
            · 该站没有放弃接口（学校 viewclaims / 聆音未核对） → **拒绝**。

          这里**不读整页扫描缓存**：放弃是秒级生效的破坏性动作，判定必须现抓站点认领页
          （一页 GET），拿到最新的 `是否达标 / 认领记录 id`，而不是 10 分钟前的快照。
        """
        try:
            sid = int(site_id or 0)
        except (TypeError, ValueError):
            sid = 0
        hash_string = str(hash or "").strip().lower()
        tid_arg = str(torrent_id or "").strip()
        if not sid or not (hash_string or tid_arg):
            return Response(success=False, message="缺少 site_id / hash（或 torrent_id）")
        if not bool(as_bool_arg(confirm)):
            return Response(success=False, message="放弃认领会丢权益并可能扣魔力，需 confirm=1")
        cfg = self._claim_cfg()
        if not cfg.get("enabled"):
            return Response(success=False, message="认领功能未启用（插件设置 → 认领）")
        if cfg.get("dry"):
            return Response(success=False, message="干跑中，未发写请求（先在设置里关闭「干跑」）")
        site = self._get_site(sid)
        if not site:
            return Response(success=False, message="站点不存在")
        prof = self._claim_profile(site)
        led = self._claim_ledger()
        rec = led.get(f"{sid}:{hash_string}") or {}
        tid = str(rec.get("tid") or tid_arg or "")
        if not tid:
            return Response(success=False, message="账本里没有这颗的站点种子 id（请在站点操作）")

        # ① 现抓站点认领页（站点口径真值）：拿这一颗的达标状态 + 认领记录 id
        data = self._claim_site_claims(site, refresh=True)
        if not data:
            return Response(success=False, message="读取站点认领页失败，未执行（拿不到真实状态不敢放弃）")
        srow = (data.get("by_tid") or {}).get(tid) or {}
        if not srow:
            return Response(
                success=False,
                message="站点认领页里没有这颗（可能已放弃 / 已结算），未发请求",
            )
        row = {
            "site_id": sid,
            "hash": hash_string,
            "torrent_id": tid,
            "title": str(srow.get("title") or rec.get("title") or ""),
            "site_qualified": srow.get("qualified"),
            "site_claimed_at": srow.get("claimed_at"),
            "site_claim_id": srow.get("claim_id"),
        }
        # ② 安全判定（与 UI 同一套口径，后端是最后一道闸）
        verdict = self._claim_abandon_verdict(prof, row)
        state = verdict["state"]
        if state in ("unsupported", "unknown", "blocked"):
            penalty = verdict.get("penalty") or 0
            head = "未达标放弃" if state == "blocked" else "无法安全放弃"
            tail = f"（该站放弃扣 {penalty} 魔力）" if state == "blocked" and penalty else ""
            return Response(
                success=False,
                message=f"{head}：{verdict['reason']}{tail}。未发请求 —— 确需放弃请到站点操作",
                data={"abandon": verdict, "result": {"ok": False, "status": state,
                                                     "message": verdict["reason"]}},
            )

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
            ok, st, msg = handler().abandon(ctx, tid, prof, claim_id=verdict["claim_id"])
        except Exception as err:  # noqa: BLE001
            ok, st, msg = False, "fail", f"放弃异常：{err}"
        if ok:
            self._claim_ledger_put(sid, hash_string, tid, st="abandoned",
                                   note=str(msg), title=str(row.get("title") or ""))
            self._claim_journal(row, {"ok": False, "status": "abandoned", "message": str(msg)})
            # ★ 19.10.52/55：整页缓存 + 站点行缓存都要跟着动，否则前端看不到「已放弃」；
            # ★ 19.10.58：**认领页缓存**（`_claim_site_cache`）也必须作废 —— 那是「已认领」
            #   列表的数据源，不作废的话站点侧已取消、插件仍显示「已认领」。
            if not self._claim_site_rows_mark(sid, tid, False):
                self._claim_site_rows_invalidate(sid)
            self._claim_site_claims_invalidate(sid)
            self._claim_state_bump()
            why = "已达标，只失去 ×2 奖励" if state == "safe" else "豁免期内，不按未达标处罚"
            return Response(success=True, message=f"已放弃认领（{why}）：{msg}",
                            data={"abandon": verdict, "result": {"ok": True, "status": st,
                                                                 "message": str(msg)}})
        # ★ 站点可能已自行取消（幂等）：把本地账本也标成 abandoned，避免列表一直挂着
        if st == "already":
            self._claim_ledger_put(sid, hash_string, tid, st="abandoned",
                                   note=str(msg), title=str(row.get("title") or ""))
            self._claim_site_claims_invalidate(sid)
            self._claim_state_bump()
            return Response(success=True, message=f"站点侧已无此认领，本地已同步：{msg}")
        return Response(success=False, message=f"放弃未执行（{st}）：{msg}",
                        data={"abandon": verdict, "result": {"ok": False, "status": st, "message": str(msg)}})

    def claim_restore(self, site_id: Any = None, confirm: Any = None, pairs: Any = None) -> Response:
        """从站点认领页重建本地账本（★ 19.10.11 · 数据丢失恢复）。

        站点认领页是**站点口径真值**。本地账本（``mf_claim``）丢失后由两层数据重建：
        站点认领行（``by_tid``）+ ``torrent_pages``（hash → 详情页 URL → tid）反查
        hash，以 ``st=already`` 补账本（幂等；ok/already 永不被失败覆盖），恢复
        ``_claim_protected_hashes`` 硬保护（已认领种不再被清种误删）。

        · **只写本地账本**，不发任何站点写请求（认领/放弃都不碰）；
        · tid 反查不到 hash 的行只报缺（``missing``），不入账（行仍以 site_only 显示）；
        · ``pairs``（可选）：显式 ``[{site_id, tid, hash}]`` 补 hash——种子在别的下载器 /
          详情页从未入库、``torrent_pages`` 反查不到时用；只认扫描里真实存在的认领行，
          多给的键进 ``pairs_unused`` 只报不用；
        · 未 ``confirm=1`` 只回预览（``dry_run=true`` + would_restore），不写账本。
        """
        ok_conf = str(confirm or "").strip().lower() in ("1", "true", "yes", "on", "y")
        rec = self._claim_scan(site_id=site_id, refresh_site=True)
        # (site_id, tid) → hash：扫**全部** TaskState 的 torrent_pages——认领的种常在
        # 已删任务的孤儿状态里（当前任务的 pages 可能是空的）；site_id 按详情页 URL
        # 域名归位（TaskState 不带 site_id）。
        sid_by_domain: Dict[str, int] = {}
        for item_u in self._claim_site_universe():
            d_u = _claim_domain_of(item_u.get("domain") or "")
            if d_u:
                sid_by_domain[d_u] = int(item_u.get("site_id") or 0)
        maps: Dict[Any, str] = {}
        try:
            states_m = list(self._store.task_states.list_all() or [])
        except Exception:  # noqa: BLE001
            states_m = []
        for st_m in states_m:
            for h_m, url_m in (getattr(st_m, "torrent_pages", None) or {}).items():
                tid_m = _torrent_id_of(url_m)
                if not tid_m or not h_m:
                    continue
                sid_m = sid_by_domain.get(_claim_domain_of(url_m), 0)
                if not sid_m:
                    continue
                maps[(sid_m, tid_m)] = str(h_m).strip().lower()
        # ★ 19.10.11：显式补 hash（站点行在 torrent_pages 里反查不到时用）
        extra = self._claim_pair_map(pairs)
        led = self._claim_ledger()
        would: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        seen_keys = set()
        for row_r in rec.get("claimed") or []:
            if not row_r.get("site_only"):
                continue
            sid_r = int(row_r.get("site_id") or 0)
            tid_r = str(row_r.get("torrent_id") or "")
            seen_keys.add((sid_r, tid_r))
            h_pages = maps.get((sid_r, tid_r)) or ""
            h_r = h_pages or extra.get((sid_r, tid_r)) or ""
            item_r: Dict[str, Any] = {
                "site_id": sid_r,
                "site_name": str(row_r.get("site_name") or ""),
                "torrent_id": tid_r,
                "hash": h_r,
                "hash_source": "pages" if h_pages else ("pair" if h_r else ""),
                "title": str(row_r.get("title") or "")[:200],
                "claimed_at": str(row_r.get("site_claimed_at") or ""),
                "seed_hours": row_r.get("seed_hours"),
            }
            if not h_r:
                missing.append(item_r)
                continue
            old_r = led.get(f"{sid_r}:{h_r}")
            if isinstance(old_r, dict) and str(old_r.get("st") or "") in ("ok", "already"):
                continue  # 账本已有承诺，不动
            would.append(item_r)
        pairs_unused = [
            {"site_id": s_u, "tid": t_u} for (s_u, t_u) in extra if (s_u, t_u) not in seen_keys
        ]
        if not ok_conf:
            return Response(
                success=True,
                message=(f"预览：将从站点重建 {len(would)} 条认领账本"
                         f"（另 {len(missing)} 条反查不到 hash，只报缺不入账"
                         + (f"；{len(pairs_unused)} 个 pairs 键无对应认领行" if pairs_unused else "")
                         + "）；未写入，需 confirm=1"),
                data={"dry_run": True, "would_restore": would, "would_restore_total": len(would),
                      "missing": missing[:50], "missing_total": len(missing),
                      "pairs_unused": pairs_unused[:20], "pairs_unused_total": len(pairs_unused)},
            )
        restored: List[Dict[str, Any]] = []
        for item_w in would:
            tag_w = "(手工hash) " if item_w.get("hash_source") == "pair" else ""
            self._claim_ledger_put(
                item_w["site_id"], item_w["hash"], item_w["torrent_id"], st="already",
                note=f"站点恢复 {tag_w}{item_w['claimed_at']}".strip(), title=item_w["title"],
            )
            restored.append(item_w)
        return Response(
            success=True,
            message=(f"已从站点重建认领账本 {len(restored)} 条"
                     f"（{len(missing)} 条反查不到 hash，未入账）"),
            data={"restored": restored, "restored_total": len(restored),
                  "missing": missing[:50], "missing_total": len(missing),
                  "pairs_unused": pairs_unused[:20], "pairs_unused_total": len(pairs_unused),
                  "protected_claim": len(self._claim_protected_hashes())},
        )

    def _claim_pair_map(self, pairs: Any) -> Dict[Any, str]:
        """``pairs`` 参数 → ``{(site_id, tid): hash}``（容忍 JSON 串 / 单条 dict / 脏值）。"""
        raw = pairs
        if isinstance(raw, str):
            if not raw.strip():
                return {}
            try:
                raw = _json.loads(raw)
            except Exception:  # noqa: BLE001
                return {}
        if isinstance(raw, dict):
            raw = [raw]
        out: Dict[Any, str] = {}
        for p in raw if isinstance(raw, list) else []:
            if not isinstance(p, dict):
                continue
            try:
                sid_p = int(p.get("site_id") or 0)
            except (TypeError, ValueError):
                sid_p = 0
            tid_p = str(p.get("tid") or p.get("torrent_id") or "").strip()
            h_p = str(p.get("hash") or "").strip().lower()
            if sid_p and tid_p and h_p:
                out[(sid_p, tid_p)] = h_p
        return out

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
