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
            return dict(hit.get("profile") or {})
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
            "reason": "未收录该站的认领能力（v1 仅支持内置预设站）",
            "verified_at": int(time.time()),
        }

    def _claim_sites_supported(self) -> List[Dict[str, Any]]:
        """所有已配置站点的认领能力清单（功能页顶部能力卡）。"""
        out: List[Dict[str, Any]] = []
        seen = set()
        for task in self._claim_tasks():
            sid = int(getattr(task, "site_id", 0) or 0)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            site = self._get_site(sid)
            if not site:
                continue
            prof = self._claim_profile(site)
            out.append(
                {
                    "site_id": sid,
                    "site_name": str(getattr(task, "site_name", "") or getattr(site, "name", "") or sid),
                    "domain": str(getattr(site, "domain", "") or getattr(site, "url", "") or ""),
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
    def _claim_tasks(self) -> List[Any]:
        """参与认领的任务（启用中、有站点）。"""
        out: List[Any] = []
        try:
            for task in (getattr(self, "_task_configs", {}) or {}).values():
                if not bool(getattr(task, "enabled", False)):
                    continue
                if not int(getattr(task, "site_id", 0) or 0):
                    continue
                out.append(task)
        except Exception as err:  # noqa: BLE001
            self._log(f"认领：枚举任务失败 {err}", "warning")
        return out

    def _claim_scan(self, site_id: Any = None, upcoming: int = 20) -> Dict[str, Any]:
        """扫一遍「可认领 / 已认领 / 快到期」——**只读本地账本 + 下载器**，零站点请求。"""
        cfg = self._claim_cfg()
        now = time.time()
        ledger = self._claim_ledger()
        want = str(site_id).strip() if site_id not in (None, "", "0") else ""
        sites_filter = {str(x).strip().lower() for x in (cfg.get("sites") or [])}
        claimed: List[Dict[str, Any]] = []
        claimable: List[Dict[str, Any]] = []
        soon: List[Dict[str, Any]] = []
        per_site: Dict[str, Dict[str, Any]] = {}
        for task in self._claim_tasks():
            sid = int(getattr(task, "site_id", 0) or 0)
            if want and str(sid) != want:
                continue
            site = self._get_site(sid)
            if not site:
                continue
            domain = str(getattr(site, "domain", "") or "").strip().lower()
            if sites_filter and domain not in sites_filter:
                continue
            prof = self._claim_profile(site)
            sname = str(getattr(task, "site_name", "") or getattr(site, "name", "") or sid)
            row = per_site.setdefault(
                str(sid),
                {"site_id": sid, "site_name": sname, "domain": domain,
                 "supported": bool(prof.get("supported")), "profile": dict(prof),
                 "claimed": 0, "claimable": 0, "today": self._claim_today_count(sid)},
            )
            if not prof.get("supported"):
                continue
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
            bonus = {}
            if cfg.get("exclude_zero_bonus"):
                bonus = self._claim_bonus_map(task, managed, pub, ni)
            for tr in managed:
                h = str(getattr(tr, "hash", "") or "").strip().lower()
                if not h:
                    continue
                key = f"{sid}:{h}"
                rec = ledger.get(key) if isinstance(ledger.get(key), dict) else None
                base = {
                    "site_id": sid,
                    "site_name": sname,
                    "hash": h,
                    "task": str(getattr(task, "id", "") or ""),
                    "title": str(getattr(tr, "title", "") or "")[:200],
                    "size_gb": round(float(getattr(tr, "size_gb", 0) or 0), 3),
                    "seeders": int(ni.get(h, -1) if h in ni else -1),
                    "torrent_id": _torrent_id_of(pages.get(h)) or (rec or {}).get("tid", ""),
                }
                if rec and str(rec.get("st")) in ("ok", "already"):
                    row["claimed"] += 1
                    claimed.append({**base, "ts": float(rec.get("ts") or 0),
                                    "state": str(rec.get("st")), "benefit": str(rec.get("benefit") or ""),
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
                claimable.append({**base, "age_days": age_days, "profile_min_age": prof.get("min_age_days")})
        claimable.sort(key=lambda x: float(x.get("age_days") or 0), reverse=True)
        soon.sort(key=lambda x: float(x.get("age_days") or 0), reverse=True)
        for r in per_site.values():
            r["profile"] = dict(r.get("profile") or {})
            r["soft_cap"] = CLAIM_SOFT_CAP
        return {
            "cfg": cfg,
            "enabled": bool(cfg.get("enabled")),
            "dry": bool(cfg.get("dry")),
            "sites": sorted(per_site.values(), key=lambda x: x["site_id"]),
            "claimed": sorted(claimed, key=lambda x: -float(x.get("ts") or 0)),
            "claimable": claimable,
            "soon": soon[: max(0, int(upcoming))] if upcoming else soon,
            "claimed_total": len(claimed),
            "claimable_total": len(claimable),
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
    def get_claim_state(self, site_id: Any = None) -> Response:
        """功能页数据：概览 / 能力卡 / 可认领 / 已认领 / 账本 / 记录。"""
        try:
            data = self._claim_scan(site_id=site_id)
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
        """扫一轮并（可选）认领：默认**干跑**；真写需 ``write=1&confirm=1``。"""
        rec = self._claim_scan(site_id=site_id)
        cfg = rec["cfg"]
        want_write = bool(self._as_bool_arg(write))
        dry_arg = self._as_bool_arg(dry)
        dry_ = (not want_write) if dry_arg is None else dry_arg
        preview = {"dry": True, "claimable": rec["claimable"], "sites": rec["sites"],
                   "claimable_total": rec["claimable_total"]}
        if dry_:
            return Response(
                success=True,
                message=f"干跑：可认领 {rec['claimable_total']} 个（未发任何写请求）",
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
                data=preview,
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
        return Response(
            success=True,
            message=f"认领完成：成功 {okn} / 共尝试 {len(done)}",
            data={"done": done, "ok": okn},
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
