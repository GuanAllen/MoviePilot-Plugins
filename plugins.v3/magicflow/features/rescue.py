# -*- coding: utf-8 -*-
"""魔流 · rescue —— 死种补源（停滞欠 H&R 的种 → 从他站「无 H&R」站补下同 Release）。

背景（Master 2026-10-05）：仓库里有若干「已下载但长期 0 速、下不完」的种子
（尤其欠 H&R 债的）。它们在 CARPT 等站会累积 H&R 罚款。补源 = 从**无 H&R**的他站
找到**同一 Release**（标题规范化后**完全一致**）且有源的副本，下回来把文件喂给本机
那个停滞的种，让它校验续传下完，从而消除 H&R 债务。

★ 判定（UI /rescue 与 AI 入口 /agent/rescue **同源**，人机同源）：
  - 目标 = 进度 ``progress < 0.999`` 且 0 速停滞 ≥ ``stall_hours``（默认 6h），
    且（``_hr_obligation`` 判欠 H&R **或** 在手动保护集合里）。
  - 候选①（**首选，11.6.0**）= **IYUU 云端内容指纹索引**（``iyuu_cloud.query``）：
    按内容指纹反查「他站也有同一颗」，**不看种名** → 对「名实不符」的种依然有效；
    来源站一律先过 ``rescue_source_blocked``（``hr != False`` 全禁）。
  - 候选②（回退）= MP 站名搜索，标题规范化后**完全一致**（大小写/全半角/多余空格归一，
    但**不许**把 10bit 与非 10bit 当同一个——词元多/少一个即判不一致）。
  - ★ **候选必过落地校验**：拉候选 ``.torrent`` 算**文件清单特征码**，与目标种一致才算数
    （IYUU 分组偶尔近邻非同封装；实测 O11CE / C.U.Soon 同组候总体积分别差 83 万 / 350 万字节）。

★ 未下完的种**不进辅种(reuse)路径**：``progress < 0.999`` 的种若去全站辅种会
反复 ADD-REUSE → recheck → 校验不过 → 撤销（空转，实测日志
`全站辅种:咖啡 挂种失败 文件不匹配（校验 36.3%），已撤销`），因此只能走本模块补源。
每个 target 记录带 ``reason_not_reuse`` 说明这一点。
TODO（主 agent 排后续版本）：全站辅种 ``features/reuse.py`` 应对 ``progress < 1`` 的种
短路，避免无效 ADD-REUSE 空转（本模块不改 reuse.py，只在此登记待办）。

铁律：
  - 只读现有真值源（qB 快照 / ``_hr_obligation`` / 手动保护集 ``_agent_manual_hashes`` /
    站点规则库 ``_site_hr_flag``），**绝不新增第二份决策真值**（停滞起算这类**观测状态**
    走 kv ``rescue_stall``，见 ``_rescue_stall_*``）。
  - 写动作（``add_torrent``）必须 ``confirm=1``；默认干跑（dry_run）。
  - 不 bump 版本、不改决策路径（golden 基线必须不变）。
"""

import re
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas import Response

# 跨站取种标签（= crossseed.CROSSSEED_TAG；此处内联字符串避免模块级 import 拉进
# crossseed 依赖——离线加载 / 依赖方向都要更干净）。
_CROSSSEED_TAG = "魔流-跨站"
# 补源专用标签（下回来的副本打这个标，与「魔流-跨站」区分）。
# ★ 11.11.1：与 tags.py 的 `RESCUE_TAG` 同值（tags.py 是特殊标签体系的登记处，这里
#   内联字符串只为避免拉进 tags 依赖、保持离线测试纯净）；两边必须保持一致。
RESCUE_TAG = "魔流-补源"


def rescue_source_blocked(hr_flag: Any, per_torrent_hr: bool = False) -> bool:
    """★ 补源来源站**唯一判定**：``hr != False`` 或**逐种 H&R 站**一律禁用。

    ``True`` = 有 H&R；``None`` = 未知（保守排除）。
    ``per_torrent_hr=True``（11.7.0，如野马PT）：H&R 由**发布者逐种开关**，站点级无法评估
    具体种子的 ``hrPunishEnable`` ⇒ 站点级预筛只能**保守排除**（否则可能凭空引入逐种 H&R 债）。
    **11.5.0 起这条不再只写在候选过滤里**——它是补源的硬护栏，
    手动补种（含走 MP 下载接口等旁路）同样适用（见 ``GET /agent/blindspot``
    的 ``source_guard``），由 ``tools/check_rescue_guard.py`` 做静态棘轮。
    """
    if per_torrent_hr:
        return True
    return hr_flag is not False

# 停滞时长阈值（小时，默认；可被 ``_rescue_cfg`` 覆盖）。
RESCUE_STALL_HOURS_DEFAULT = 6.0
# 每个目标最多返回几个候选（按 seeders 降序 + 体积邻近排序取前 N）。
RESCUE_MAX_CANDIDATES = 3
# ★ 候选「落地校验」缓存 TTL（秒）：抓到候选 .torrent 的原始字节在此 TTL 内复用，
#   让「扫描 → 执行」不重复抓取（一次抓取 = 1 PV）。
RESCUE_VERIFY_CACHE_TTL = 900.0


def _fullwidth_to_halfwidth(s: str) -> str:
    """全角 → 半角（含全角空格 U+3000 → 半角空格）。"""
    out: List[str] = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _rescue_norm_title(title: Any) -> Tuple[str, ...]:
    """标题归一化：小写 + 全角转半角 + 去 [组名]/年代 + 非字母数字汉字当分隔符。

    ★ 返回**有序词元组**，用于「规范化后完全一致」的**精确比较**（绝不模糊匹配），
    因此「10bit」与「非 10bit」天然不同（词元多/少一个即判不一致）。
    """
    s = _fullwidth_to_halfwidth(str(title or "").lower())
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\b(19[0-9]{2}|20[0-9]{2})\b", " ", s)
    return tuple(t for t in s.split() if len(t) > 1)


class RescueMixin:
    """rescue 功能集（死种补源）。"""

    # --------------------------------------------------------------- 配置 / 观测状态
    def _rescue_settings(self) -> Dict[str, Any]:
        """补源配置视图（真值源 = ``self._rescue_cfg``，未配置用默认）。"""
        cfg = getattr(self, "_rescue_cfg", None)
        if not isinstance(cfg, dict):
            cfg = {}
        try:
            stall = float(cfg.get("stall_hours") or RESCUE_STALL_HOURS_DEFAULT)
        except (TypeError, ValueError):
            stall = RESCUE_STALL_HOURS_DEFAULT
        try:
            maxn = int(cfg.get("max_candidates") or RESCUE_MAX_CANDIDATES)
        except (TypeError, ValueError):
            maxn = RESCUE_MAX_CANDIDATES
        return {
            "stall_hours": stall,
            "tag": RESCUE_TAG,
            "max_candidates": maxn,
            "sources": ["iyuu", "mp"],
            "verify": True,
            "verify_note": "候选必拉 .torrent 比对「文件清单特征码」才算数（IYUU 分组偶有近邻非同封装）",
            "reason_not_reuse": "progress<1 的种不进辅种(reuse)路径，只能走补源(rescue)",
        }

    def _rescue_stall_kv(self) -> Dict[str, float]:
        """停滞起算时间观测状态（kv；非决策真值，只用于估算停滞时长）。"""
        obj = getattr(self, "_rescue_stall_obj", None)
        if isinstance(obj, dict):
            return obj
        raw: Dict[str, Any] = {}
        try:
            from ..sitestore import slot_callbacks  # noqa: WPS433

            raw = slot_callbacks(self, "rescue_stall")[0]() or {}
        except Exception:  # noqa: BLE001
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        obj = self._rescue_stall_obj = {
            str(k): float(v) for k, v in raw.items()
            if str(k).strip() and _float_ok(v)
        }
        return obj

    def _rescue_stall_save(self) -> None:
        try:
            from ..sitestore import slot_callbacks  # noqa: WPS433

            slot_callbacks(self, "rescue_stall")[1](value=self._rescue_stall_kv())
        except Exception:  # noqa: BLE001
            pass

    def _rescue_stall_seconds(self, h: str, t: Any, now: float) -> float:
        """估算「停滞至今的秒数」：qB ``added_on``（若从未下载任何数据）> kv 起算。

        返回 0 表示本轮才第一次观察到停滞（累计观察时间）。
        """
        kv = self._rescue_stall_kv()
        first = kv.get(h)
        if first is None:
            first = now
            kv[h] = now
            self._rescue_stall_save()
        est = first
        try:
            added = float(getattr(t, "added_on", 0) or 0)
            downloaded = float(getattr(t, "downloaded", 0) or 0)
            if added > 0 and downloaded <= 0 and added < first:
                est = added
        except Exception:  # noqa: BLE001
            pass
        # ★ 11.2.1 兜底：当前 0 速时，qB ``last_activity`` 是「至少多久没有任何动静」的下界
        #   （取更早的起点 = 更长停滞；对长期无 peer/announce 的死种立刻可见，冷启动期也能用）
        try:
            last = float(getattr(t, "last_activity", 0) or 0)
            if last > 0:
                est = min(est, last)
        except Exception:  # noqa: BLE001
            pass
        return max(0.0, now - est)

    def _rescue_manual_hashes(self) -> Set[str]:
        """手动保留集合（与 ``_delete_gate_detail`` 同源，复用 agent 门面）。"""
        try:
            return {str(x).strip().lower() for x in (self._agent_manual_hashes() or set())}
        except Exception:  # noqa: BLE001
            return set()

    @staticmethod
    def _rescue_now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _rescue_bool(v: Any) -> Optional[bool]:
        if v is None:
            return None
        s = str(v).strip().lower()
        if s == "":
            return None
        return s not in ("0", "false", "no", "off", "none")

    # --------------------------------------------------------------- 目标 / 候选
    def _rescue_site_of(self, t: Any) -> str:
        tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
        try:
            return str(self._torrent_site_name(tags, "") or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _rescue_targets(self, snap: Any = None) -> List[Dict[str, Any]]:
        """扫描「停滞欠 H&R / 手动保留」的未下完种（只读，不写、不联网）。"""
        now = time.time()
        cfg = self._rescue_settings()
        stall_sec = float(cfg["stall_hours"]) * 3600.0
        if snap is None:
            try:
                snap = self._tag_all_torrents() or {}
            except Exception:  # noqa: BLE001
                snap = {}
        manual = self._rescue_manual_hashes()
        targets: List[Dict[str, Any]] = []
        for h, t in (snap or {}).items():
            h = str(h or "").strip().lower()
            if not h:
                continue
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if _CROSSSEED_TAG in tags or RESCUE_TAG in tags:
                continue  # 已跨站 / 已补源 → 不再重复补
            try:
                progress = float(getattr(t, "progress", 1.0) or 1.0)
            except Exception:  # noqa: BLE001
                progress = 1.0
            if progress >= 0.999:
                continue
            try:
                dlspeed = float(getattr(t, "download_speed", 0) or 0)
            except Exception:  # noqa: BLE001
                dlspeed = 0.0
            if dlspeed > 0:
                continue  # 未停滞（仍在下载）
            stalled = self._rescue_stall_seconds(h, t, now)
            if stalled < stall_sec:
                continue
            try:
                owed, need, seeded, src = self._hr_obligation("", t, snap=snap)
            except Exception:  # noqa: BLE001
                owed, need, seeded, src = False, 0.0, 0.0, ""
            is_manual = h in manual
            if not owed and not is_manual:
                continue
            title = str(getattr(t, "title", "") or "")
            save_path = str(getattr(t, "save_path", "") or "")
            size = float(getattr(t, "size", 0) or 0)
            chain: List[Dict[str, Any]] = [
                {"rule": "rescue/stalled", "verdict": "candidate",
                 "inputs": {"progress": round(progress, 4), "download_speed": dlspeed,
                            "stalled_h": round(stalled / 3600.0, 2),
                            "threshold_h": cfg["stall_hours"]},
                 "source_of_truth": "qB snapshot", "at": self._rescue_now()},
            ]
            if owed:
                chain.append({"rule": "rescue/hr_owed", "verdict": "candidate",
                              "inputs": {"need_h": round(float(need), 1),
                                         "seeded_h": round(float(seeded), 1), "src": src},
                              "source_of_truth": "hr ledger / bills", "at": self._rescue_now()})
            if is_manual:
                chain.append({"rule": "rescue/manual_protect", "verdict": "candidate",
                              "inputs": {"manual": True},
                              "source_of_truth": "task_states.json:protected_torrents",
                              "at": self._rescue_now()})
            targets.append({
                "hash": h,
                "title": title,
                "site": self._rescue_site_of(t),
                "progress": round(progress, 4),
                "stalled_hours": round(stalled / 3600.0, 2),
                "download_speed": dlspeed,
                "hr_owed": bool(owed),
                "hr_need_h": round(float(need), 1),
                "hr_seeded_h": round(float(seeded), 1),
                "hr_src": str(src or ""),
                "manual": bool(is_manual),
                "save_path": save_path,
                "size_gb": round(size / (1024 ** 3), 2) if size else 0.0,
                "reason_not_reuse": f"本机文件未完成 {progress * 100:.1f}% → 不可辅种（只能补源）",
                "reason_chain": chain,
            })
        return targets

    def _rescue_domain_of_site_id(self, sid: int) -> str:
        for s in self._list_sites() or []:
            try:
                if int(s.get("id") or 0) == int(sid or 0):
                    return str(s.get("domain") or "").strip().lower()
            except Exception:  # noqa: BLE001
                continue
        return ""

    def _rescue_site_ids_except(self, target_dom: str) -> List[int]:
        """全部站点 id（排除目标站自己）。"""
        target_dom = str(target_dom or "").strip().lower()
        target_id = 0
        if target_dom:
            try:
                target_id = int(self._site_id_by_domain(target_dom) or 0)
            except Exception:  # noqa: BLE001
                target_id = 0
        ids: List[int] = []
        for s in self._list_sites() or []:
            try:
                sid = int(s.get("id") or 0)
            except Exception:  # noqa: BLE001
                continue
            if not sid:
                continue
            if target_id and sid == target_id:
                continue
            if sid not in ids:
                ids.append(sid)
        return ids

    def _rescue_candidates_mp(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """[MP 名称搜索 · 回退路径] 按标题规范化「完全一致」找他站候选（保留排除证据）。

        结构性缺陷（2026-10-05 实测）：CARPT 存在「名实不符」的种（名字写 ``S01`` /
        ``S01.Complete``，实际只装某几集）→ 标题精确匹配永远对不上，看起来像「全网没有」。
        IYUU 指纹索引（``_rescue_iyuu_candidates``）因此成为**首选**，本函数只当回退。
        """
        title = str(target.get("title") or "")
        norm = _rescue_norm_title(title)
        if not title or not norm:
            return {"candidates": [], "skipped": [{"site": "", "reason": "标题为空，无法检索"}]}
        target_dom = ""
        try:
            target_dom = self._site_domain_by_name(str(target.get("site") or ""))
        except Exception:  # noqa: BLE001
            target_dom = ""
        site_ids = self._rescue_site_ids_except(target_dom)
        if not site_ids:
            return {"candidates": [], "skipped": [
                {"site": target_dom or "?", "reason": "无其它站点可搜"}]}
        try:
            hits = self._mp_search_title(title, site_ids) or []
        except Exception as e:  # noqa: BLE001
            return {"candidates": [], "skipped": [{"site": "", "reason": f"MP 搜索失败:{e}"}]}
        cands: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        for ti in hits:
            ht = str(getattr(ti, "title", "") or "")
            if _rescue_norm_title(ht) != norm:
                continue
            sid = int(getattr(ti, "site", 0) or 0)
            sname = str(getattr(ti, "site_name", "") or "")
            dom = ""
            try:
                dom = self._site_domain_by_name(sname) or self._rescue_domain_of_site_id(sid)
            except Exception:  # noqa: BLE001
                dom = ""
            flag = None
            try:
                flag = self._site_hr_flag(dom) if dom else None
            except Exception:  # noqa: BLE001
                flag = None
            pthr = False
            try:
                pthr = self._site_per_torrent_hr(dom) if dom else False
            except Exception:  # noqa: BLE001
                pthr = False
            if rescue_source_blocked(flag, pthr):
                reason = ("来源站逐种H&R(保守排除)" if pthr
                          else ("来源站有H&R" if flag is True else "来源站H&R未知(保守排除)"))
                skipped.append({"site": dom or sname, "reason": reason})
                continue
            try:
                seeders = int(getattr(ti, "seeders", 0) or 0)
            except Exception:  # noqa: BLE001
                seeders = 0
            if seeders <= 0:
                skipped.append({"site": dom or sname, "reason": "无源(seeders=0)"})
                continue
            size = float(getattr(ti, "size", 0) or 0)
            cands.append({
                "title": ht,
                "size": size,
                "size_gb": round(size / (1024 ** 3), 2) if size else 0.0,
                "seeders": seeders,
                "site": sid,
                "site_name": sname,
                "domain": dom,
                "enclosure": str(getattr(ti, "enclosure", "") or ""),
                "page_url": str(getattr(ti, "page_url", "") or ""),
            })
        tsize = float(target.get("size_gb") or 0) * (1024 ** 3)

        def _key(c: Dict[str, Any]) -> Tuple[int, float]:
            delta = abs(float(c.get("size") or 0) - tsize) if tsize else 0.0
            return (-int(c.get("seeders") or 0), delta)
        cands.sort(key=_key)
        maxn = int(self._rescue_settings()["max_candidates"])
        return {"candidates": cands[:maxn], "skipped": skipped}

    # ------------------------------------------------- IYUU 指纹索引（11.6.0 首选路径）
    def _rescue_raw_cache(self) -> Dict[str, Any]:
        """候选 .torrent 字节短 TTL 缓存（内存热层；热重载后为空 → 重新抓一次，无副作用）。"""
        cache = getattr(self, "_rescue_raw_obj", None)
        if not isinstance(cache, dict):
            cache = {}
            try:
                self._rescue_raw_obj = cache
            except Exception:  # noqa: BLE001
                pass
        return cache

    def _rescue_verify_cache_get(self, key: str) -> Optional[bytes]:
        item = self._rescue_raw_cache().get(key)
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            return None
        ts, raw = item
        try:
            if (time.time() - float(ts or 0)) > RESCUE_VERIFY_CACHE_TTL:
                return None
        except (TypeError, ValueError):
            return None
        return raw if isinstance(raw, (bytes, bytearray)) else None

    def _rescue_verify_cache_put(self, key: str, raw: bytes) -> None:
        try:
            self._rescue_raw_cache()[key] = (time.time(), bytes(raw))
        except Exception:  # noqa: BLE001
            pass

    def _rescue_target_fp(self, h: str) -> str:
        """目标种（本机，可能未下完）的文件清单特征码 —— qB 有元数据即可算。"""
        try:
            dl = self._get_downloader("qbittorrent")
            fp = dl.get_torrent_fingerprint(str(h)) if dl is not None else None
            return str(fp or "")
        except Exception:  # noqa: BLE001
            return ""

    def _rescue_verify_torrent(self, raw: bytes, target_fp: str) -> Tuple[bool, str, str, str]:
        """校验候选 .torrent 是否与目标种**同内容**。

        返回 ``(ok, 候选特征码, 候选 infohash, 不通过原因)``。判据 = 文件清单特征码一致
        （含根目录名 / 文件名 / 大小），这是唯一可铺的必要条件。
        """
        try:
            from ..fingerprint import fingerprint, info_hash  # noqa: WPS433
        except Exception as e:  # noqa: BLE001
            return False, "", "", f"指纹模块不可用:{e}"
        try:
            cih = str(info_hash(raw) or "").strip().lower()
        except Exception:  # noqa: BLE001
            cih = ""
        try:
            fp = str(fingerprint(raw) or "")
        except Exception:  # noqa: BLE001
            fp = ""
        if not fp:
            return False, "", cih, "候选 .torrent 无法解析（文件清单为空）"
        if not target_fp:
            return False, fp, cih, "目标种特征码不可用（qB 取不到文件清单）"
        if fp != target_fp:
            return False, fp, cih, "文件清单特征码不一致（非同一 Release）"
        return True, fp, cih, ""

    @staticmethod
    def _rescue_torrent_size(raw: bytes) -> int:
        try:
            from ..fingerprint import load_torrent_entries, total_size  # noqa: WPS433
            return int(total_size(load_torrent_entries(raw) or []))
        except Exception:  # noqa: BLE001
            return 0

    def _rescue_iyuu_siblings(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """IYUU 指纹索引反查：「本机这颗」在他站有哪些同资源（先过来源站护栏）。

        ★ 按**内容指纹**索引（不看种名），因此对「名实不符」的种依然有效；
        来源站一律先过 ``rescue_source_blocked``（hr != False 全禁），排除证据照留。
        """
        h = str(target.get("hash") or "").strip().lower()
        out: Dict[str, Any] = {"siblings": [], "skipped": [], "sids": []}
        cli = getattr(self, "_iyuu_client", None)
        if cli is None or not h:
            out["skipped"].append({"site": "iyuu", "reason": "IYUU 未启用（无客户端）"})
            return out
        try:
            site_map = self._reseed_site_map() or {}
        except Exception as e:  # noqa: BLE001
            out["skipped"].append({"site": "iyuu", "reason": f"IYUU 站点映射失败:{e}"})
            return out
        if not site_map:
            out["skipped"].append({"site": "iyuu", "reason": "IYUU 站点映射为空（我们无可用 sid）"})
            return out
        target_dom = ""
        try:
            target_dom = str(self._site_domain_by_name(str(target.get("site") or "")) or "")
        except Exception:  # noqa: BLE001
            target_dom = ""
        target_sid = 0
        if target_dom:
            try:
                target_sid = int(cli.sid_by_domain(target_dom) or 0)
            except Exception:  # noqa: BLE001
                target_sid = 0
        sids = sorted(int(x) for x in site_map)
        out["sids"] = sids
        try:
            res = cli.query([h], sids=sids) or {}
        except Exception as e:  # noqa: BLE001
            out["skipped"].append({"site": "iyuu", "reason": f"IYUU 云端查询失败:{e}"})
            return out
        rows = res.get(h) or []
        if not rows:
            out["skipped"].append({"site": "iyuu", "reason": "IYUU 云端未见他站同资源"})
            return out
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                sid = int(r.get("sid") or 0)
            except (TypeError, ValueError):
                continue
            tid = r.get("torrent_id")
            ih = str(r.get("info_hash") or "").strip().lower()
            if not sid or not tid:
                continue
            info = site_map.get(sid) or {}
            dom = str(info.get("domain") or "").strip().lower()
            name = str(info.get("name") or dom or sid)
            if sid not in site_map:
                out["skipped"].append({"site": dom or str(sid), "reason": "IYUU 候选：不在我们启用的站点"})
                continue
            if target_sid and sid == target_sid:
                out["skipped"].append({"site": dom or name, "reason": "IYUU 候选：目标站自身"})
                continue
            if ih and ih == h:
                out["skipped"].append({"site": dom or name, "reason": "IYUU 候选：与目标种同一 infohash"})
                continue
            flag = None
            try:
                flag = self._site_hr_flag(dom) if dom else None
            except Exception:  # noqa: BLE001
                flag = None
            pthr = False
            try:
                pthr = self._site_per_torrent_hr(dom) if dom else False
            except Exception:  # noqa: BLE001
                pthr = False
            if rescue_source_blocked(flag, pthr):
                reason = ("来源站逐种H&R(保守排除)" if pthr
                          else ("来源站有H&R" if flag is True else "来源站H&R未知(保守排除)"))
                out["skipped"].append({"site": dom or name, "reason": f"IYUU 候选：{reason}"})
                continue
            out["siblings"].append({"sid": sid, "tid": tid, "ih": ih,
                                    "domain": dom, "site_name": name,
                                    "site_id": info.get("site_id") or 0})
        return out

    def _rescue_iyuu_candidates(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """IYUU 候选 + **落地校验**：拉候选 .torrent → 与目标种特征码逐条比对。

        ★ 只有校验通过（文件清单特征码一致）的候选才算数 —— IYUU 分组偶尔会把
        不同封装归到一组（实测 O11CE / C.U.Soon 的同组候总体积分别差 83 万 / 350 万字节），
        不校验就直接铺会白下。每次抓取 = 1 PV（受站点预算约束），抓到的字节进短 TTL 缓存，
        ``/rescue?action=apply`` 直接复用，不重复抓。
        """
        h = str(target.get("hash") or "").strip().lower()
        sib = self._rescue_iyuu_siblings(target)
        cands: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = list(sib["skipped"])
        siblings = sib["siblings"]
        if not siblings:
            return {"candidates": cands, "skipped": skipped,
                    "source": "iyuu", "siblings": 0}
        tfp = self._rescue_target_fp(h)
        if not tfp:
            skipped.append({"site": "iyuu", "reason": "目标种特征码不可用（qB 取不到文件清单）"})
            return {"candidates": cands, "skipped": skipped,
                    "source": "iyuu", "siblings": len(siblings)}
        dl = None
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception:  # noqa: BLE001
            dl = None
        maxn = int(self._rescue_settings()["max_candidates"])
        attempts = 0
        for s in siblings:
            if len(cands) >= maxn or attempts >= maxn * 2:
                break
            sid = int(s["sid"])
            tid = s["tid"]
            dom = str(s["domain"] or "")
            name = str(s["site_name"] or dom or sid)
            key = f"{sid}:{h}"
            raw = self._rescue_verify_cache_get(key)
            if raw is None:
                if not self._pv_allow(sid, "rescue", want=1):
                    skipped.append({"site": dom or name, "reason": "站点 PV 预算不足，本轮跳过"})
                    continue
                attempts += 1
                url = None
                try:
                    url = self._reseed_download_url(sid, tid)
                except Exception:  # noqa: BLE001
                    url = None
                if not url:
                    skipped.append({"site": dom or name,
                                    "reason": "IYUU 候选：无法构造下载链（模板/口令缺失）"})
                    continue
                conn: Dict[str, Any] = {}
                try:
                    conn = self._reseed_site_conn(sid) or {}
                except Exception:  # noqa: BLE001
                    conn = {}
                try:
                    raw = dl.fetch_torrent_bytes(
                        url, cookie=conn.get("cookie"), user_agent=conn.get("ua"),
                        referer=(conn.get("url") or None),
                    ) if dl is not None else None
                except Exception:  # noqa: BLE001
                    raw = None
                finally:
                    try:
                        self._pv_spend(sid, "rescue", 1)
                    except Exception:  # noqa: BLE001
                        pass
                if not raw:
                    skipped.append({"site": dom or name,
                                    "reason": "IYUU 候选：取 .torrent 失败（流控/权限/空内容）"})
                    continue
                self._rescue_verify_cache_put(key, raw)
            ok, fp, cih, why = self._rescue_verify_torrent(raw, tfp)
            if not ok:
                skipped.append({"site": dom or name, "reason": f"IYUU 候选：{why}"})
                continue
            size = self._rescue_torrent_size(raw)
            cands.append({
                "title": str(target.get("title") or ""),
                "size": float(size),
                "size_gb": round(size / (1024 ** 3), 2) if size else 0.0,
                "seeders": 0,
                "site": int(s.get("site_id") or 0),
                "site_name": name,
                "domain": dom,
                "enclosure": "",
                "page_url": "",
                "source": "iyuu",
                "verified": True,
                "iyuu_sid": sid,
                "torrent_id": tid,
                "info_hash": cih,
                "fingerprint": fp,
                "reason_chain": [
                    {"rule": "rescue/candidate_source", "verdict": "iyuu_fingerprint_index",
                     "inputs": {"iyuu_sid": sid, "torrent_id": tid, "siblings": len(siblings),
                                "declared_sids": len(sib.get("sids") or [])},
                     "source_of_truth": "IYUU 云端内容指纹索引（iyuu_cloud.query）",
                     "at": self._rescue_now()},
                    {"rule": "rescue/source_guard", "verdict": "allowed",
                     "inputs": {"site": dom, "hr": False},
                     "source_of_truth": "features/siteops.py::_site_hr_flag(domain) 经 rescue_source_blocked()",
                     "at": self._rescue_now()},
                    {"rule": "rescue/fingerprint_check", "verdict": "match",
                     "inputs": {"target_fp": tfp, "candidate_fp": fp, "candidate_infohash": cih},
                     "source_of_truth": "fingerprint.py（文件清单：路径+大小）",
                     "at": self._rescue_now()},
                ],
            })
        return {"candidates": cands, "skipped": skipped,
                "source": "iyuu", "siblings": len(siblings)}

    def _rescue_candidates(self, target: Dict[str, Any],
                           verify: bool = True) -> Dict[str, Any]:
        """候选编排：**IYUU 指纹索引优先**（带落地校验）→ 无果才回退 MP 名称搜索。

        ``verify=False`` 只查处（不抓 .torrent、不联网校验）—— 给「只想看看有哪些站」
        的便宜调用用；UI/AI 默认 verify=True（因为只有校验过的候选才敢铺）。
        """
        res: Dict[str, Any] = {"candidates": [], "skipped": [], "source": "none"}
        if verify:
            try:
                res = self._rescue_iyuu_candidates(target)
            except Exception as e:  # noqa: BLE001
                res = {"candidates": [], "source": "iyuu",
                       "skipped": [{"site": "iyuu", "reason": f"IYUU 候选检索失败:{e}"}]}
        cands = list(res.get("candidates") or [])
        skipped = list(res.get("skipped") or [])
        if cands:
            return {"candidates": cands, "skipped": skipped, "source": "iyuu"}
        mp = self._rescue_candidates_mp(target)
        for c in mp.get("candidates") or []:
            c["source"] = "mp"
            c["verified"] = False
        mp_cands = mp.get("candidates") or []
        cands += mp_cands
        skipped += mp.get("skipped") or []
        return {"candidates": cands, "skipped": skipped,
                "source": "mp" if mp_cands else "none"}

    def _rescue_skipped_sites(self) -> List[Dict[str, Any]]:
        """站点级排除清单：``hr != False`` 的站都不能当补源（静态、廉价）。"""
        out: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for s in self._list_sites() or []:
            name = str(s.get("name") or s.get("domain") or "")
            try:
                dom = self._site_domain_by_name(name)
            except Exception:  # noqa: BLE001
                dom = str(s.get("domain") or "").strip().lower()
            if not dom or dom in seen:
                continue
            seen.add(dom)
            flag = None
            try:
                flag = self._site_hr_flag(dom)
            except Exception:  # noqa: BLE001
                flag = None
            pthr = False
            try:
                pthr = self._site_per_torrent_hr(dom)
            except Exception:  # noqa: BLE001
                pthr = False
            if rescue_source_blocked(flag, pthr):
                out.append({"domain": dom, "name": name, "hr": flag,
                            "per_torrent_hr": pthr,
                            "reason": ("逐种H&R(保守排除)" if pthr
                                       else ("有H&R" if flag is True else "H&R未知(保守排除)"))})
        return out

    def _rescue_scan(self, hashes: Optional[List[str]] = None,
                     verify: bool = True) -> Dict[str, Any]:
        """补源扫描（只读预览）：targets（含候选 + 依据链） + 排除站点 + 配置。

        ``verify=True``（默认）会走 IYUU 指纹索引并**拉候选 .torrent 做落地校验**
        （联网 + 站点 PV）；``verify=False`` 只出目标清单（不联网）。
        """
        targets = self._rescue_targets()
        if hashes:
            hs = {str(h).strip().lower() for h in hashes if str(h).strip()}
            targets = [t for t in targets if t["hash"] in hs]
        enriched: List[Dict[str, Any]] = []
        sources: List[str] = []
        for t in targets:
            c = self._rescue_candidates(t, verify=verify)
            if c.get("source"):
                sources.append(str(c["source"]))
            item = dict(t)
            item["candidates"] = c["candidates"]
            item["skipped"] = c["skipped"]
            item["candidate_source"] = str(c.get("source") or "none")
            item["best"] = c["candidates"][0] if c["candidates"] else None
            item["action"] = "add" if c["candidates"] else "skip"
            enriched.append(item)
        return {"targets": enriched, "skipped_sites": self._rescue_skipped_sites(),
                "settings": self._rescue_settings(),
                "verify": bool(verify),
                "sources_used": sorted(set(sources))}

    # --------------------------------------------------------------- 写动作（补下副本）
    def _rescue_add_one(self, target: Dict[str, Any], candidate: Dict[str, Any],
                        save_path: str = "") -> Dict[str, Any]:
        """为一个目标种补下一个候选副本（取字节 → add_torrent → 记账）。

        候选来源两条：``iyuu``（IYUU 指纹索引，用 sid+tid 现构下载链）与
        ``mp``（MP 站名搜索，用 enclosure）。两条都走同一个 add 口与同一个标签。
        """
        h = target["hash"]
        src = str(candidate.get("source") or "mp")
        data = None
        if src == "iyuu":
            sid = int(candidate.get("iyuu_sid") or 0)
            tid = candidate.get("torrent_id")
            if not sid or not tid:
                return {"hash": h, "ok": False, "err": "IYUU 候选缺少 sid/torrent_id"}
            key = f"{sid}:{h}"
            data = self._rescue_verify_cache_get(key)
            if data is None:
                url = None
                try:
                    url = self._reseed_download_url(sid, tid)
                except Exception:  # noqa: BLE001
                    url = None
                if not url:
                    return {"hash": h, "ok": False, "err": "无法构造候选下载链（模板/口令缺失）"}
                conn: Dict[str, Any] = {}
                try:
                    conn = self._reseed_site_conn(sid) or {}
                except Exception:  # noqa: BLE001
                    conn = {}
                try:
                    dl0 = self._get_downloader("qbittorrent")
                    data = dl0.fetch_torrent_bytes(
                        url, cookie=conn.get("cookie"), user_agent=conn.get("ua"),
                        referer=(conn.get("url") or None),
                    ) if dl0 is not None else None
                except Exception:  # noqa: BLE001
                    data = None
                finally:
                    try:
                        self._pv_spend(sid, "rescue", 1)
                    except Exception:  # noqa: BLE001
                        pass
                if data:
                    self._rescue_verify_cache_put(key, data)
        else:
            row = SimpleNamespace(
                site=int(candidate.get("site") or 0),
                title=candidate.get("title") or "",
                enclosure=candidate.get("enclosure") or "",
                page_url=candidate.get("page_url") or "",
                site_cookie=None,
                site_ua=None,
                site_proxy=False,
                size=float(candidate.get("size") or 0),
                seeders=int(candidate.get("seeders") or 0),
            )
            try:
                data = self._crossseed_torrent_bytes(row)
            except Exception as e:  # noqa: BLE001
                return {"hash": h, "ok": False, "err": f"取种子字节失败:{e}"}
        if not data:
            return {"hash": h, "ok": False, "err": "取种子字节为空（PV 不足 / 站点拒绝）"}
        # ★ 写前再过一次落地校验（缓存命中时也复核；MUST NOT 铺非同一 Release）
        tfp = self._rescue_target_fp(str(h))
        ok, fp, cih, why = self._rescue_verify_torrent(data, tfp)
        if not ok:
            return {"hash": h, "ok": False, "err": f"写前校验未通过:{why}",
                    "candidate_fingerprint": fp, "candidate_infohash": cih}
        dest = str(save_path or target.get("save_path") or "").strip()
        if not dest:
            return {"hash": h, "ok": False, "err": "未配置保存目录（避免落到下载器默认目录）"}
        try:
            dl = self._get_downloader("qbittorrent")
            if dl is None:
                return {"hash": h, "ok": False, "err": "下载器不可用"}
            nh, err = dl.add_torrent(content=data, download_dir=dest, tag=RESCUE_TAG,
                                     site_domain=str(candidate.get("domain") or ""),
                                     hit_and_run=bool(candidate.get("hit_and_run")))
            if not nh:
                return {"hash": h, "ok": False, "err": str(err or "添加失败")}
        except Exception as e:  # noqa: BLE001
            return {"hash": h, "ok": False, "err": str(e)}
        try:
            self._rescue_record(h, target, candidate, str(nh))
        except Exception:  # noqa: BLE001
            pass
        self._log(f"补源:{target.get('title', '')} 已从 {candidate.get('domain', '?')} "
                  f"（{src}）下回副本({str(nh)[:12]}…) ｜校验 {str(fp)[:8]}…")
        return {"hash": h, "ok": True, "new_hash": str(nh), "source": src,
                "candidate_fingerprint": fp}

    def _rescue_record(self, h: str, target: Dict[str, Any], candidate: Dict[str, Any],
                       new_hash: str) -> None:
        """补源操作台账（journal kind=rescue；写失败静默，不影响补源本身）。"""
        try:
            journal = getattr(getattr(self, "_store", None), "journal", None)
            fn = getattr(journal, "record", None) if journal is not None else None
            if not callable(fn):
                return
            from ..persistence import OperationItem  # noqa: WPS433
            item = OperationItem(
                hash=h,
                title=str(target.get("title") or ""),
                reason=(f"补源：从 {candidate.get('domain') or candidate.get('site_name') or '?'} "
                        f"补下同 Release（{str(new_hash)[:12]}…）"),
                size_gb=float(target.get("size_gb") or 0.0),
                source="rescue",
            )
            fn(task_id="", kind="rescue", items=[item])
        except Exception:  # noqa: BLE001
            pass

    def _rescue_apply(self, hashes: List[str], save_path: str = "",
                      dry: Optional[bool] = None, confirm: Optional[bool] = None) -> Dict[str, Any]:
        """执行补源：dry 默认干跑；真写必须 confirm=1。"""
        scan = self._rescue_scan(hashes=hashes)
        targets = scan["targets"]
        if dry is None:
            dry = not bool(confirm)
        plan: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        for t in targets:
            cands = t.get("candidates") or []
            if not cands:
                plan.append({"hash": t["hash"], "action": "skip", "reason": "无可用候选",
                             "skipped": t.get("skipped") or []})
                continue
            best = cands[0]
            if dry:
                plan.append({"hash": t["hash"], "action": "add", "dry": True,
                             "candidate": best["title"], "site": best["domain"],
                             "save_path": save_path or t["save_path"]})
                continue
            if not confirm:
                plan.append({"hash": t["hash"], "action": "skip", "reason": "需 confirm=1"})
                continue
            res = self._rescue_add_one(t, best, save_path)
            results.append(res)
            plan.append({"hash": t["hash"], "action": "add", "ok": bool(res.get("ok")),
                         "new_hash": res.get("new_hash") or "",
                         "err": res.get("err") or ""})
        if dry:
            return {"dry_run": True, "targets": len(targets), "plan": plan,
                    "would_add": sum(1 for p in plan if p.get("action") == "add")}
        return {"dry_run": False, "targets": len(targets), "plan": plan, "results": results,
                "added": sum(1 for r in results if r.get("ok"))}

    # --------------------------------------------------------------- 路由 / AI 入口
    @staticmethod
    def _rescue_parse_hashes(hashes: Any) -> List[str]:
        if hashes is None:
            return []
        if isinstance(hashes, (list, tuple, set)):
            return [str(h).strip().lower() for h in hashes if str(h).strip()]
        if isinstance(hashes, str):
            return [h.strip().lower() for h in hashes.split(",") if h.strip()]
        return [str(hashes).strip().lower()]

    def rescue(self, action: str = "", hashes: Any = None, save_path: str = "",
               dry_run: Any = None, confirm: Any = None) -> Response:
        """死种补源（UI 同源端点）：``action=scan`` 只读预览 / ``action=apply`` 执行（需 confirm=1）。"""
        try:
            act = str(action or "").strip().lower() or "scan"
            if act == "scan":
                return Response(success=True, message="OK", data=self._rescue_scan())
            if act == "apply":
                hs = self._rescue_parse_hashes(hashes)
                return Response(
                    success=True,
                    message="OK",
                    data=self._rescue_apply(hs, save_path=save_path,
                                            dry=self._rescue_bool(dry_run),
                                            confirm=self._rescue_bool(confirm)),
                )
            return Response(success=False, message=f"未知 action:{action}（scan|apply）", data={})
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"补源执行失败:{e}", data={})

    def agent_rescue(self) -> Dict[str, Any]:
        """``GET /agent/rescue`` —— 死种补源观测（只读，不联网、不写）。

        返回 ``{targets, skipped_sites, settings}``：targets 是停滞欠 H&R / 手动保留的
        未下完种（带 reason_chain / reason_not_reuse），skipped_sites 是 ``hr != False``
        不能当补源的站点，settings 是当前补源配置。
        """
        t0 = time.time()
        try:
            targets = self._rescue_targets()
            skipped = self._rescue_skipped_sites()
            settings = self._rescue_settings()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"补源观测失败:{e}", t0, trace_id=str(e))
        return self._agent_ok({"targets": targets, "skipped_sites": skipped,
                               "settings": settings}, t0)

    def agent_rescue_candidates(self, hashes: Any = None, verify: Any = None) -> Dict[str, Any]:
        """``GET /agent/rescue/candidates`` —— **真正可用的补源候选**（带落地校验）。

        ★ 与 UI 的 ``/rescue?action=scan`` **同源**（同一个 ``_rescue_scan``）。
        ★ 会联网：IYUU 指纹索引反查 + 拉候选 ``.torrent`` 比对文件清单特征码
          （每次抓取 = 1 PV，进站点预算账本）；**不写下载器**（纯读观测）。
        回答「这批烂种能从哪里补源、为什么这几个行/那几个不行」。
        """
        t0 = time.time()
        verify_b = True if verify is None else bool(self._rescue_bool(verify))
        hs = self._rescue_parse_hashes(hashes)
        try:
            scan = self._rescue_scan(hs or None, verify=verify_b)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"补源候选查询失败:{e}", t0, trace_id=str(e))
        targets: List[Dict[str, Any]] = []
        for t in scan["targets"]:
            targets.append({
                "hash": t["hash"], "title": t.get("title"), "site": t.get("site"),
                "progress": t.get("progress"), "stalled_hours": t.get("stalled_hours"),
                "hr_owed": t.get("hr_owed"), "save_path": t.get("save_path"),
                "size_gb": t.get("size_gb"),
                "candidate_source": t.get("candidate_source"),
                "action": t.get("action"),
                "candidates": t.get("candidates") or [],
                "skipped": t.get("skipped") or [],
            })
        return self._agent_ok({
            "targets": targets,
            "skipped_sites": scan["skipped_sites"],
            "settings": scan["settings"],
            "verify": scan["verify"],
            "sources_used": scan["sources_used"],
        }, t0)


def _float_ok(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
