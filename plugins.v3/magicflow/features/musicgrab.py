# -*- coding: utf-8 -*-
"""魔流 · musicgrab —— 「歌单 → 选种计划」线（AI 端，只读）。

★ 15.7.0（Master 2026-10-07 20:44 拍板）：**歌曲也是资源** → 音乐走 PT 规则
（H&R / 账本），选种做成**可解释的判定链**。本模块只做**第一步：计划（干跑）**，
不下载、不写任何账本。

    歌单文本（每行一条）
      → 逐条搜候选（MP 搜索，``mtype=music``，只搜指定站、按站计 PV）
      → 硬过滤（视频 / MV / 现场录像）
      → 打分（无损格式 / 位深 / 分轨整轨 / 免费 / 做种 / 体积）
      → 选中 + **每条候选的依据链**（命中哪条规则 / 输入 / 真值源 / 时间）

只读铁律：不写 json、不写账本、不碰 qB；``grab``（真下载）另做（下一步）。
"""

import re
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from ..fingerprint import info_hash
from ..persistence import OperationItem
from ..tags import SUB_RESOURCE, STATE_SILENT, tag_for

# ---------------------------------------------------------------------------
# 常量（打分口径，集中在这里，便于以后做成可配权重）
# ---------------------------------------------------------------------------
MUSIC_PLAN_PER_ITEM_DEFAULT = 3      # 每首保留候选条数
MUSIC_PLAN_LIMIT_DEFAULT = 40        # 歌单条数上限
MUSIC_FREE_RATIO = 0.0               # downloadvolumefactor <= 0 → 免费
MUSIC_SAVE_PATH_DEFAULT = "/vol6/1000/music"   # 音乐落盘目录（qB 宿主路径）
MUSIC_CATEGORY = "音乐"                        # qB 分类
MUSIC_GRAB_SLEEP = 1.0               # 两次加种之间的小间隔（别猛打站点/下载器）

#: ★ 音乐线职务标签（不许出现在音乐种上）：音乐单独一条线，**不进魔力/刷流任务**
#: 匹配形如 ``魔流-<站点>-魔力`` / ``魔流-<站点>-刷流``（任务标签）。
_MUSIC_DUTY_STRIP_RE = re.compile(r"^魔流-.+-(魔力|刷流)$")

#: 视频 / 录像特征（命中即**硬排除**：我们要的是音频）
_MUSIC_VIDEO_TOKENS = (
    "2160p", "1080p", "1080i", "720p", "480p", "8k", "4k", "uhd",
    "x264", "x265", "h.264", "h264", "h.265", "h265", "hevc", "avc", "mpeg2", "vc-1",
    ".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".wmv", ".rmvb", ".flv",
    "演唱会", "music video", "官方mv",
)

#: 「MV」作为独立词出现才算（避免误伤包含 mv 的专辑/编码字样）
_MUSIC_VIDEO_RE = re.compile(r"\bmv\b")

#: 无损 / 高解析特征
_MUSIC_LOSSLESS_TOKENS = ("flac", "alac", "ape", "wav", "aiff", "dsd", "dff", "dsf", "shm-cd", "hires", "hi-res")
_MUSIC_LOSSY_TOKENS = ("mp3", "aac", "m4a", "ogg", "opus", "wma")
_MUSIC_HIRES_TOKENS = ("24bit", "24-bit", "24 bit", "96khz", "96 khz", "192khz", "192 khz", "dsd", "hi-res", "hires")
_MUSIC_SPLIT_TOKENS = ("分轨", "分軌", "tracks", "track", "cue", "整轨", "整軌")

#: 打分权重
_MUSIC_W_LOSSLESS = 40
_MUSIC_W_LOSSY = 8
_MUSIC_W_HIRES = 15
_MUSIC_W_SPLIT = 5
_MUSIC_W_FREE = 20
_MUSIC_W_2X = 5
_MUSIC_W_SEEDERS_MAX = 10          # 做种数封顶贡献
_MUSIC_W_SEEDERS_CAP = 50          # 做种数折算上限（>=50 拿满）
_MUSIC_W_SIZE_OK = 5


def _music_lower(s: Any) -> str:
    return str(s or "").strip().lower()


def _music_is_free(dv: Any) -> bool:
    """是否免费（downloadvolumefactor <= 0）。"""
    try:
        return float(dv if dv is not None else 1.0) <= MUSIC_FREE_RATIO
    except Exception:  # noqa: BLE001
        return False


class MusicGrabMixin:
    """「歌单 → 选种计划」（只读）。"""

    # ------------------------------------------------------------------ 入参解析
    @staticmethod
    def _music_parse_line(line: str) -> Optional[Dict[str, str]]:
        """一行 → ``{raw, artist, title, sites}``。

        支持：``艺人 - 歌名`` / ``歌名`` / ``歌名@站id,站id``。空行/注释(``#``) 跳过。
        """
        raw = str(line or "").strip()
        if not raw or raw.startswith("#"):
            return None
        sites = ""
        if "@" in raw:
            raw, _, sites = raw.rpartition("@")
            raw, sites = raw.strip(), sites.strip()
        artist, title = "", raw
        for sep in (" - ", " – ", "—", "-"):
            if sep in raw:
                a, _, t = raw.partition(sep)
                if a.strip() and t.strip():
                    artist, title = a.strip(), t.strip()
                    break
        return {"raw": raw, "artist": artist, "title": title, "sites": sites}

    def _music_parse(self, text: str, limit: int = MUSIC_PLAN_LIMIT_DEFAULT) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for line in str(text or "").replace("\r", "\n").split("\n"):
            ent = self._music_parse_line(line)
            if ent:
                out.append(ent)
            if limit and len(out) >= int(limit):
                break
        return out

    # ------------------------------------------------------------------ 搜索
    def _music_search(self, keyword: str, site_ids: List[int]) -> List[Dict[str, Any]]:
        """MP 搜索（``mtype=music``）→ 候选行。不过滤免费（要的是资源本身）。"""
        kw = str(keyword or "").strip()
        ids = [int(i) for i in (site_ids or []) if i]
        if not kw or not ids:
            return []
        allowed = [
            i for i in ids
            if not self._pv_block_reason(i) and self._pv_allow(i, "ondemand", want=1)
        ]
        if not allowed:
            self._log("音乐计划:候选站点 PV 预算不足/已封，跳过检索", "warning")
            return []
        try:
            hits = self._mp_search_title(kw, allowed, mtype="music")
        except TypeError:
            hits = self._mp_search_title(kw, allowed)
        except Exception as e:  # noqa: BLE001
            self._log(f"音乐计划:MP 搜索失败({kw}): {e}", "warning")
            hits = []
        finally:
            for i in allowed:
                self._pv_spend(i, "ondemand", 1)
        rows: List[Dict[str, Any]] = []
        for ti in hits or []:
            url = str(getattr(ti, "enclosure", "") or "")
            if not url:
                continue
            try:
                dv = float(getattr(ti, "downloadvolumefactor", 1.0) or 0.0)
            except Exception:  # noqa: BLE001
                dv = 1.0
            try:
                uv = float(getattr(ti, "uploadvolumefactor", 1.0) or 0.0)
            except Exception:  # noqa: BLE001
                uv = 1.0
            try:
                seeders = int(getattr(ti, "seeders", 0) or 0)
            except Exception:  # noqa: BLE001
                seeders = 0
            rows.append({
                "title": str(getattr(ti, "title", "") or ""),
                "size": float(getattr(ti, "size", 0.0) or 0.0),
                "seeders": seeders,
                "site": int(getattr(ti, "site", 0) or 0),
                "site_name": str(getattr(ti, "site_name", "") or ""),
                "downloadvolumefactor": dv,
                "uploadvolumefactor": uv,
                "hit_and_run": bool(getattr(ti, "hit_and_run", False)),
                # ↓ 加种（grab）要用；plan 输出会剔除
                "enclosure": url,
                "page_url": str(getattr(ti, "page_url", "") or ""),
                "site_cookie": getattr(ti, "site_cookie", None),
                "site_ua": getattr(ti, "site_ua", None),
                "site_proxy": bool(getattr(ti, "site_proxy", False)),
            })
        self._log(f"音乐计划:搜「{kw}」{len(allowed)} 站 → 候选 {len(rows)} 条")
        return rows

    # ------------------------------------------------------------------ 打分
    def _music_score(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """候选打分：返回 ``{score, excluded, exclude_reason, reasons[]}``。

        每条 ``reasons`` = ``{rule, verdict, inputs, source_of_truth, at}``（判定依据链）。
        """
        at = self._agent_now()
        title = _music_lower(row.get("title"))
        size = float(row.get("size") or 0.0)
        size_gb = size / 1024 ** 3
        seeders = int(row.get("seeders") or 0)
        dv = float(row.get("downloadvolumefactor", 1.0) or 0.0)
        uv = float(row.get("uploadvolumefactor", 1.0) or 0.0)
        reasons: List[Dict[str, Any]] = []

        def _r(rule: str, verdict: str, inputs: Dict[str, Any], sot: str = "候选行（MP 搜索 mtype=music）") -> None:
            reasons.append({"rule": rule, "verdict": verdict, "inputs": inputs, "source_of_truth": sot, "at": at})

        # R0 硬过滤：视频 / MV / 现场录像 → 排除
        hit_video = [t for t in _MUSIC_VIDEO_TOKENS if t in title]
        if str(title).lower().strip() and _MUSIC_VIDEO_RE.search(title):
            hit_video.append("mv")
        if hit_video:
            _r("music.video_filter", "exclude", {"hit": hit_video, "title": title})
            return {"score": 0, "excluded": True, "exclude_reason": f"视频/录像特征 {hit_video}",
                    "reasons": reasons, "size_gb": round(size_gb, 2), "seeders": seeders}

        score = 0

        # R1 无损 / 有损（★ 高解析但标题没写 FLAC 的，按无损算 —— 如 “24bit96khz”）
        lossless = [t for t in _MUSIC_LOSSLESS_TOKENS if t in title]
        lossy = [t for t in _MUSIC_LOSSY_TOKENS if t in title]
        hires = [t for t in _MUSIC_HIRES_TOKENS if t in title]
        if lossless and not lossy:
            score += _MUSIC_W_LOSSLESS
            _r("music.format", f"+{_MUSIC_W_LOSSLESS}", {"lossless": lossless})
        elif lossless and lossy:
            score += _MUSIC_W_LOSSLESS // 2
            _r("music.format", f"+{_MUSIC_W_LOSSLESS // 2}", {"lossless": lossless, "lossy": lossy,
                                                              "note": "标题同时含无损与有损字样，折半"})
        elif lossy:
            score += _MUSIC_W_LOSSY
            _r("music.format", f"+{_MUSIC_W_LOSSY}", {"lossy": lossy})
        elif hires:
            score += _MUSIC_W_LOSSLESS
            _r("music.format", f"+{_MUSIC_W_LOSSLESS}", {"hires": hires,
                                                         "note": "只有高解析字样没写格式 → 按无损"})
        else:
            _r("music.format", "+0", {"note": "未识别格式字样"})

        # R2 高解析（位深/采样率）
        if hires and not lossy:
            score += _MUSIC_W_HIRES
            _r("music.hires", f"+{_MUSIC_W_HIRES}", {"hit": hires})

        # R3 分轨 / 整轨
        split = [t for t in _MUSIC_SPLIT_TOKENS if t in title]
        if split:
            score += _MUSIC_W_SPLIT
            _r("music.structure", f"+{_MUSIC_W_SPLIT}", {"hit": split})

        # R4 免费 / 双倍
        if dv <= MUSIC_FREE_RATIO:
            score += _MUSIC_W_FREE
            _r("music.free", f"+{_MUSIC_W_FREE}", {"downloadvolumefactor": dv},
               "候选行 downloadvolumefactor（MP 搜索）")
        if uv >= 2.0:
            score += _MUSIC_W_2X
            _r("music.2x", f"+{_MUSIC_W_2X}", {"uploadvolumefactor": uv})

        # R5 做种数（越多越好，封顶）
        seed_score = int(round(_MUSIC_W_SEEDERS_MAX * min(seeders, _MUSIC_W_SEEDERS_CAP) / _MUSIC_W_SEEDERS_CAP))
        score += seed_score
        _r("music.seeders", f"+{seed_score}", {"seeders": seeders, "cap": _MUSIC_W_SEEDERS_CAP})

        # R6 体积合理性（单张 0.02~4G 加分；>8G 疑似大合集，不加也不减）
        if 0.02 <= size_gb <= 4.0:
            score += _MUSIC_W_SIZE_OK
            _r("music.size", f"+{_MUSIC_W_SIZE_OK}", {"size_gb": round(size_gb, 2)})
        else:
            _r("music.size", "+0", {"size_gb": round(size_gb, 2), "note": "超出常见单张体积区间"})

        return {"score": score, "excluded": False, "exclude_reason": "",
                "reasons": reasons, "size_gb": round(size_gb, 2), "seeders": seeders}

    # ------------------------------------------------------------------ 计划
    def _music_plan(self, text: str, sites: str = "", per_item: int = MUSIC_PLAN_PER_ITEM_DEFAULT,
                    limit: int = MUSIC_PLAN_LIMIT_DEFAULT) -> Dict[str, Any]:
        """歌单 → 计划（只读）。"""
        entries = self._music_parse(text, limit=limit)
        per_item = max(1, min(int(per_item or MUSIC_PLAN_PER_ITEM_DEFAULT), 10))
        base_sites = self._ondemand_sites(None, sites)
        items: List[Dict[str, Any]] = []
        n_chosen = n_excluded = n_empty = 0
        for ent in entries:
            kw = f"{ent['artist']} {ent['title']}".strip()
            ent_sites = base_sites
            if ent.get("sites"):
                try:
                    ent_sites = [int(x.strip()) for x in ent["sites"].split(",") if x.strip()] or base_sites
                except Exception:  # noqa: BLE001
                    ent_sites = base_sites
            rows = self._music_search(kw, ent_sites)
            scored: List[Dict[str, Any]] = []
            for r in rows:
                s = self._music_score(r)
                if s["excluded"]:
                    n_excluded += 1
                    continue
                scored.append({**r, "size_gb": s["size_gb"], "score": s["score"], "reasons": s["reasons"]})
            scored.sort(key=lambda x: (-x["score"], -int(x.get("seeders") or 0), -(x.get("size") or 0)))
            cands = scored[:per_item]
            chosen = cands[0] if cands else None
            if chosen:
                n_chosen += 1
            else:
                n_empty += 1
            excluded: List[Dict[str, Any]] = []
            if not cands:
                for r in rows[:per_item]:
                    s = self._music_score(r)
                    if s["excluded"]:
                        excluded.append({"title": r.get("title") or "",
                                         "site_name": r.get("site_name") or "",
                                         "reason": s["exclude_reason"]})
            items.append({
                "query": kw,
                "raw": ent["raw"],
                "artist": ent["artist"],
                "title": ent["title"],
                "candidates_total": len(rows),
                "audio_total": len(scored),
                "chosen": ({
                    "title": chosen["title"], "site": chosen["site"], "site_name": chosen["site_name"],
                    "size_gb": chosen["size_gb"], "seeders": chosen["seeders"],
                    "downloadvolumefactor": chosen["downloadvolumefactor"], "score": chosen["score"],
                } if chosen else None),
                "chosen_reasons": (chosen["reasons"] if chosen else []),
                "candidates": [{
                    "title": c["title"], "site": c["site"], "site_name": c["site_name"],
                    "size_gb": c["size_gb"], "seeders": c["seeders"],
                    "downloadvolumefactor": c["downloadvolumefactor"], "score": c["score"],
                } for c in cands],
                "excluded": excluded,          # 被硬过滤的（只给前 per_item 条，便于排查）
                "_chosen_row": (dict(chosen) if chosen else None),   # 内部：grab 用，对外剔除
                "empty_reason": ("" if chosen else ("无候选（站点没搜到）" if not rows else "候选全被硬过滤（视频/MV）")),
            })
        return {
            "items": items,
            "summary": {
                "entries": len(entries), "chosen": n_chosen, "empty": n_empty,
                "excluded_video": n_excluded, "sites": base_sites,
                "per_item": per_item,
            },
            "policy": {
                "search": "MoviePilot SearchChain（mtype=music），只搜指定站点，按站计 PV",
                "exclude": "标题含分辨率/视频编码/视频容器/演唱会 → 硬排除",
                "score": "无损+40 / 高解析+15 / 分轨+5 / 免费+20 / 2x+5 / 做种(≤50)+0~10 / 体积合理+5",
                "note": "本端点只读：不下载、不写账本、不碰 qB（真下载见下一步 grab）",
            },
        }

    # ------------------------------------------------------------------ 对外（剔除内部行）
    @staticmethod
    def _music_public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
        """去掉 ``_chosen_row``（带 cookie）后的对外计划。"""
        out = dict(plan or {})
        items = []
        for it in out.get("items") or []:
            it = dict(it)
            it.pop("_chosen_row", None)
            items.append(it)
        out["items"] = items
        return out

    # ------------------------------------------------------------------ 加种（写）
    def _music_save_path(self, override: str = "") -> str:
        """音乐保存目录：入参 > 设置 > 默认 ``/vol6/1000/music``。

        ★ 坑：设置项属性名为 ``_music_save_dir``（**不能**同方法同名，
        否则 ``getattr(self, "_music_save_path")`` 拿到的是本方法自身）。
        """
        override = str(override or "").strip()
        if override:
            return override
        cfg = str(getattr(self, "_music_save_dir", "") or "").strip()
        return cfg or MUSIC_SAVE_PATH_DEFAULT

    # ------------------------------------------------------------------
    # 音乐线隔离（★15.8.0）：音乐种不进任何魔力/刷流任务
    # ------------------------------------------------------------------
    def _is_music_line(self, obj: Any) -> bool:
        """该种是否属于「音乐线」（qB 分类 = ``音乐``）。

        Master 口径：**音乐单独一条线，不与刷流抢** —— 音乐种不纳管进魔力/刷流任务、
        不参与其清理与账本（否则「无进度 / 无上传」会把它当低效种删掉）。
        兼容 ``TorrentInfo`` 对象与 qB 原始 dict。
        """
        try:
            if isinstance(obj, dict):
                if str(obj.get("category") or "").strip() == MUSIC_CATEGORY:
                    return True
                return False
            if str(getattr(obj, "category", "") or "").strip() == MUSIC_CATEGORY:
                return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def _music_untag_duty(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """摘掉音乐种上的「魔力 / 刷流」职务标签（幂等；默认干跑）。

        音乐种被魔力任务当同站种纳管过 → 会带上 ``魔流-<站点>-魔力``，从而
        暴露给任务的清理。本方法只摘这一种职务标签，其它标签一律不动。
        """
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "scanned": 0,
                              "candidates": 0, "cleaned": 0, "failed": 0, "samples": []}
        try:
            dl = self._get_downloader("qbittorrent")
            idx = dl.get_all_torrents_index() if dl is not None else {}
        except Exception as err:  # noqa: BLE001
            return {**rep, "ok": False, "error": str(err)}
        cap = int(limit or 0)
        for h, t in (idx or {}).items():
            if not self._is_music_line(t):
                continue
            rep["scanned"] = int(rep["scanned"]) + 1
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or []) if str(x).strip()]
            removed = [x for x in tags if _MUSIC_DUTY_STRIP_RE.match(x)]
            if not removed:
                continue
            rep["candidates"] = int(rep["candidates"]) + 1
            if cap and int(rep["candidates"]) > cap:
                continue
            keep = [x for x in tags if x not in removed]
            if len(rep["samples"]) < 10:
                rep["samples"].append({"hash": str(h)[:12], "removed": removed, "keep": keep})
            if not apply:
                continue
            try:
                if callable(getattr(dl, "replace_torrent_tags", None)) and dl.replace_torrent_tags(str(h), keep):
                    rep["cleaned"] = int(rep["cleaned"]) + 1
                else:
                    rep["failed"] = int(rep["failed"]) + 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"音乐线:摘职务标签失败 {str(h)[:12]}:{err}", "warning")
        return rep

    def _music_grab_one(self, row: Dict[str, Any], save_path: str,
                        existing: Optional[set] = None) -> Dict[str, Any]:
        """加一颗音乐种（走现有词子：取 .torrent → 下载器加种 → H&R 开账）。

        tag = ``魔流-<站>-静默-资源``（同点播）→ 后续自动进账本 / 静默池 / H&R / 闸门 / 报表。
        幂等：本地先算 infohash，已在下载器 → ``skipped``，不重复加。
        """
        dl = self._get_downloader("qbittorrent")
        if dl is None or not getattr(dl, "is_available", False):
            return {"ok": False, "message": "下载器不可用"}
        sid = int(row.get("site") or 0)
        if sid and (self._pv_block_reason(sid) or not self._pv_allow(sid, "crossseed", want=1)):
            return {"ok": False, "message": "PV 闸门拦截（站点预算不足/被封，稍后再试）"}
        content = self._crossseed_torrent_bytes(SimpleNamespace(**row))
        if not content:
            return {"ok": False, "message": "取 .torrent 失败（站点拒绝/种子已删，换一条候选）"}
        try:
            h0 = str(info_hash(content)).lower()
        except Exception:  # noqa: BLE001
            h0 = ""
        if h0 and existing and h0 in existing:
            return {"ok": True, "hash": h0, "skipped": True, "message": "已在下载器"}
        site_name = str(row.get("site_name") or "")
        tag = tag_for(site_name, STATE_SILENT, SUB_RESOURCE) if site_name else ""
        try:
            dom = self._site_domain_by_name(site_name) or ""
        except Exception:  # noqa: BLE001
            dom = ""
        try:
            hs, err = dl.add_torrent(content=content, download_dir=save_path, tag=tag,
                                     category=MUSIC_CATEGORY, site_domain=dom,
                                     hit_and_run=bool(row.get("hit_and_run")))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"添加失败: {e}"}
        if not hs:
            return {"ok": False, "message": f"添加失败: {err or '未知'}"}
        h = str(hs[0] if isinstance(hs, (list, tuple)) else hs).lower()
        return {"ok": True, "hash": h, "tag": tag, "save_path": save_path}

    def _music_grab(self, text: str, sites: str = "",
                    per_item: int = MUSIC_PLAN_PER_ITEM_DEFAULT,
                    limit: int = MUSIC_PLAN_LIMIT_DEFAULT,
                    save_path: str = "") -> Dict[str, Any]:
        """歌单 → 计划 → 逐首加种（写）。本方法假定调用方已确认 ``confirm``。"""
        plan = self._music_plan(text, sites=sites, per_item=per_item, limit=limit)
        sp = self._music_save_path(save_path)
        try:
            existing = {str(k).lower() for k in (self._tag_all_torrents() or {})}
        except Exception:  # noqa: BLE001
            existing = set()
        added: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for it in plan.get("items") or []:
            row = it.get("_chosen_row")
            q = str(it.get("query") or "")
            if not row:
                skipped.append({"query": q, "reason": it.get("empty_reason") or "无候选"})
                continue
            res = self._music_grab_one(row, sp, existing=existing)
            if res.get("ok") and res.get("hash"):
                existing.add(str(res["hash"]).lower())
                rec = {"query": q, "title": row.get("title") or "", "hash": res["hash"],
                       "site": row.get("site") or 0, "site_name": row.get("site_name") or "",
                       "size_gb": round(float(row.get("size") or 0) / 1024 ** 3, 2),
                       "free": _music_is_free(row.get("downloadvolumefactor"))}
                if res.get("skipped"):
                    rec["reason"] = res.get("message") or "已在下载器"
                    skipped.append(rec)
                else:
                    added.append(rec)
            else:
                failed.append({"query": q, "title": row.get("title") or "",
                               "message": str(res.get("message") or "添加失败")})
            time.sleep(MUSIC_GRAB_SLEEP)
        if added:
            try:
                self._store.journal.record(
                    task_id="", kind="selection",
                    items=[OperationItem(hash=a["hash"], title=f"音乐 {a['title']}",
                                         reason=f"源 {a['site_name']}" + ("·免费" if a.get("free") else ""),
                                         source="music") for a in added],
                )
            except Exception as e:  # noqa: BLE001
                self._log(f"音乐:journal 落盘失败 {e}", "warning")
        self._log(f"音乐:歌单 {len(plan.get('items') or [])} 条 → 新增 {len(added)} / 跳过 {len(skipped)} / 失败 {len(failed)}")
        return {
            "applied": True,
            "save_path": sp,
            "category": MUSIC_CATEGORY,
            "added": added,
            "skipped": skipped,
            "failed": failed,
            "summary": {"entries": len(plan.get("items") or []), "added": len(added),
                        "skipped": len(skipped), "failed": len(failed)},
            "plan": self._music_public_plan(plan),
            "policy": plan.get("policy"),
        }
