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

import threading
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
)
from ..kvstore import cache_get, cache_set
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

    def _claim_host_status(self, resume: bool = False) -> Dict[str, Any]:
        """★ 19.7.0：已认领种的保挂状态（``resume=False`` 纯只读）。

        账本 ``st=ok/already`` = 站点侧承诺。这里只做保活：
          · qB 里没了 → missing（不自动重下，避免误吞流量）
          · paused/stopped → resume（仅 worker 调用时）
          · 其余 → 视为在种
        绝不删除、不改账本承诺；删除闸门另有硬保护。
        """
        claims = {
            str(k): v for k, v in (self._claim_ledger() or {}).items()
            if isinstance(v, dict) and str(v.get("st")) in ("ok", "already")
        }
        snap = self._claim_qb_snapshot()
        missing: List[str] = []
        to_resume: List[str] = []
        seeding = 0
        for key in claims:
            _, _, h = str(key).partition(":")
            h = h.strip().lower()
            if not h:
                continue
            t = snap.get(h)
            if t is None:
                missing.append(h)
                continue
            st = str(getattr(t, "state", "") or "").lower()
            if st in ("paused", "stopped", "queued", "pausedup", "stoppedup"):
                to_resume.append(h)
            else:
                seeding += 1
        resumed = 0
        if resume and to_resume:
            try:
                dl = self._get_downloader()
                n, err = dl.resume_torrents(to_resume)
                resumed = int(n or 0)
                if err:
                    self._log(f"认领保挂:恢复失败 {err}", "warning")
            except Exception as err:  # noqa: BLE001
                self._log(f"认领保挂:恢复异常 {err}", "warning")
        rep = {
            "at": time.time(),
            "total": len(claims),
            "seeding": seeding,
            "paused": len(to_resume),
            "resumed": resumed,
            "missing": len(missing),
            "missing_hashes": missing[:20],
        }
        if resume and claims:
            self._log(
                f"认领保挂: {rep['total']} 个已认领 / 在种 {seeding} / 恢复 {resumed} / 丢失 {len(missing)}"
            )
        return rep

    def claim_host(self) -> Dict[str, Any]:
        """★ 19.7.0：``__claim__`` 常驻保挂 worker（会 resume 暂停的已认领种）。"""
        return self._claim_host_status(resume=True)

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
    @staticmethod
    def _claim_parse_table(html: str) -> Dict[str, Any]:
        """解析 NexusPHP 认领页（表头驱动，兼容 11/12/13 列与学校 viewclaims）。"""
        import re as _re

        out: Dict[str, Any] = {"summary": {}, "by_tid": {}}
        text = str(html or "")
        m = _re.search(r"本月认领总数：\s*(\d+).*?已达标：\s*(\d+).*?未达标：\s*(\d+)", text, _re.S)
        if m:
            out["summary"] = {"total": int(m.group(1)), "qualified": int(m.group(2)), "unqualified": int(m.group(3))}
        m = _re.search(r"下次结算时间：\s*([0-9:\- ]+)", text)
        if m:
            out["summary"]["next_settle"] = m.group(1).strip()

        def clean(x: str) -> str:
            return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", x or "")).strip()

        def hours_of(v: str) -> float:
            tm = _re.match(r"(?:(\d+)天)?\s*(\d+):(\d+):(\d+)", v or "")
            if not tm:
                return 0.0
            return int(tm.group(1) or 0) * 24 + int(tm.group(2)) + int(tm.group(3)) / 60.0 + int(tm.group(4)) / 3600.0

        rows = _re.findall(r"<tr[^>]*>(.*?)</tr>", text, _re.S)
        header = None
        for tr in rows:
            cells = _re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, _re.S)
            vals = [clean(c) for c in cells]
            if any("种子名称" in v for v in vals) and any(("认领时间" in v or "添加时间" in v) for v in vals):
                header = vals
                break
        if not header:
            return out
        idx: Dict[str, int] = {}
        for i, name in enumerate(header):
            n = name.strip()
            if n == "ID":
                idx["id"] = i
            elif n == "用户":
                idx["user"] = i
            elif "种子名称" in n:
                idx["title"] = i
            elif "种子大小" in n or n == "大小":
                idx["size"] = i
            elif "种子存活" in n:
                idx["alive"] = i
            elif "认领时间" in n or "添加时间" in n:
                idx["claimed_at"] = i
            elif "上次结算" in n:
                idx["last_settle"] = i
            elif "本月做种" in n or n == "做种时间":
                idx["seed_time"] = i
            elif "本月上传" in n or n == "上传":
                idx["upload"] = i
            elif "是否达标" in n:
                idx["qualified"] = i
            elif "预计奖励" in n or "获得魔力" in n:
                idx["reward"] = i
            elif "下次结账" in n:
                idx["next_settle"] = i

        def at(vals, key, default=""):
            i = idx.get(key)
            return vals[i] if i is not None and i < len(vals) else default

        for tr in rows:
            cells = _re.findall(r"<td[^>]*>(.*?)</td>", tr, _re.S)
            if len(cells) < len(header):
                continue
            title_cell = at(cells, "title", "")
            tid_m = _re.search(r"detail\w*\s*\.php\?id=(\d+)", title_cell) or _re.search(r"detail\w*\s*\.php\?id=(\d+)", tr)
            if not tid_m:
                continue
            vals = [clean(c) for c in cells]
            seed_time = at(vals, "seed_time")
            reward = at(vals, "reward")
            reward_num = None
            rm = _re.search(r"([\d,]+)", reward)
            if rm:
                reward_num = float(rm.group(1).replace(",", ""))
            qv = at(vals, "qualified")
            qualified = (qv.lower() in ("yes", "是", "达标")) if qv else bool(reward_num and reward_num > 0)
            out["by_tid"][tid_m.group(1)] = {
                "claim_id": at(vals, "id"),
                "title": clean(title_cell),
                "size": at(vals, "size"),
                "alive": at(vals, "alive"),
                "claimed_at": at(vals, "claimed_at"),
                "last_settle": at(vals, "last_settle"),
                "next_settle": at(vals, "next_settle"),
                "seed_time": seed_time,
                "seed_hours": round(hours_of(seed_time), 2),
                "upload": at(vals, "upload"),
                "qualified": qualified,
                "reward": reward,
                "reward_num": reward_num,
            }
        if not out["summary"]:
            out["summary"] = {"total": len(out["by_tid"])}
            first = next(iter(out["by_tid"].values()), None)
            if first and first.get("next_settle"):
                out["summary"]["next_settle"] = first["next_settle"]
        return out

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
            data = self._claim_parse_table(res.text or "")
            data["at"] = time.time()
            data["url"] = url
            cache[sid] = data
            return data
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领站点口径读取失败 {sid}: {err}")
            return {}

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

    def _claim_scan(self, site_id: Any = None, upcoming: int = 20, limit: int = 0, refresh_site: bool = False) -> Dict[str, Any]:
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
            if not row_s0.get("claimed") and "viewclaims" not in str((row_s0.get("profile") or {}).get("claim_list") or ""):
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
            # 19.7.18: default cache-only; 19.7.27: cold viewclaims sites fetch once
            cache0 = getattr(self, "_claim_site_cache", {}) or {}
            cold = []
            for sid_s1, site_obj1 in targets:
                cached = cache0.get(sid_s1)
                if cached:
                    prefetched[sid_s1] = cached
                    continue
                prof1 = self._claim_profile(site_obj1)
                if "viewclaims" in str(prof1.get("claim_list") or ""):
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
            if not row_s.get("claimed") and "viewclaims" not in str((row_s.get("profile") or {}).get("claim_list") or ""):
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
                r["site_qualified"] = bool(srow.get("qualified"))
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
                    "site_qualified": bool(srow.get("qualified")),
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

    def _claim_state_key(self, site_id: str, limit: int) -> str:
        from ..common import __version__ as _ver  # noqa: WPS433
        return f"state:{_ver}:{self._claim_state_gen()}:{site_id or 'all'}:{int(limit or 0)}"

    def _claim_state_build(self, site_id: Any, limit: int, cache_key: str, refresh_site: bool = False) -> Dict[str, Any]:
        """真正算一遍并写缓存（计算很重：账本 + qB 快照 + 站点页）。"""
        data = self._claim_scan(site_id=site_id, limit=limit, refresh_site=refresh_site)
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

    def _claim_state_refresh(self, site_id: str, limit: int) -> None:
        """后台刷新（同一 key 单飞，避免并发打站点）。"""
        key = self._claim_state_key(site_id, limit)
        locks = getattr(self, "_claim_state_locks", None)
        if not isinstance(locks, dict):
            locks = self._claim_state_locks = {}
        guard = locks.get(key)
        if guard is None:
            guard = locks[key] = threading.Lock()
        if not guard.acquire(blocking=False):
            return
        try:
            self._claim_state_build(site_id or None, limit, key, refresh_site=True)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"认领缓存后台刷新失败：{err}")
        finally:
            guard.release()

    # ------------------------------------------------------------------ 只读端点
    def get_claim_state(self, site_id: Any = None, limit: Any = 0, refresh: Any = None) -> Response:
        """功能页数据：概览 / 能力卡 / 可认领 / 已认领 / 账本 / 记录。

        ★ 19.7.22：整份结果进 Redis 缓存（CLAIM_STATE_TTL 新鲜期，CLAIM_STATE_STALE
        内陈旧也直接返回并后台刷新）。refresh=1 强制重算。
        """
        try:
            sid = str(site_id).strip() if site_id not in (None, "", "0") else ""
            lim = self._claim_limit(limit)
            force = bool(self._as_bool_arg(refresh))
            key = self._claim_state_key(sid, lim)
            if not force:
                hit = cache_get(self, "claim", key, CLAIM_STATE_STALE)
                if isinstance(hit, dict) and isinstance(hit.get("data"), dict):
                    age = max(0.0, time.time() - float(hit.get("at") or 0))
                    data = dict(hit["data"])
                    data["cached"] = True
                    data["cache_age"] = round(age, 1)
                    if age > CLAIM_STATE_TTL:
                        try:
                            threading.Thread(
                                target=self._claim_state_refresh, args=(sid, lim), daemon=True
                            ).start()
                        except Exception:  # noqa: BLE001
                            pass
                    return Response(success=True, data=data)
            data = self._claim_state_build(sid or None, lim, key, refresh_site=force)
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
