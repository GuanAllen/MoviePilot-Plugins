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
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 常量（打分口径，集中在这里，便于以后做成可配权重）
# ---------------------------------------------------------------------------
MUSIC_PLAN_PER_ITEM_DEFAULT = 3      # 每首保留候选条数
MUSIC_PLAN_LIMIT_DEFAULT = 40        # 歌单条数上限
MUSIC_FREE_RATIO = 0.0               # downloadvolumefactor <= 0 → 免费

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

        # R1 无损 / 有损
        lossless = [t for t in _MUSIC_LOSSLESS_TOKENS if t in title]
        lossy = [t for t in _MUSIC_LOSSY_TOKENS if t in title]
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
        else:
            _r("music.format", "+0", {"note": "未识别格式字样"})

        # R2 高解析（位深/采样率）
        hires = [t for t in _MUSIC_HIRES_TOKENS if t in title]
        if hires:
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

    # ------------------------------------------------------------------ AI 端点
