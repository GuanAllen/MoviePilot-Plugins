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

import errno
import hashlib
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from ..fingerprint import info_hash
from ..persistence import OperationItem
from ..sitestore import slot_callbacks
from .. import shared                      # ★ 19.12.0：入库账本读改写锁 + 扫描去抖状态（跨热重载）
from ..tags import (MEDIA_CAND_TTL, MUSIC_CATEGORY, SUB_RESOURCE, STATE_HR, STATE_KEEP,
                    STATE_MUSIC,
                    STATE_SILENT, fmt_iso_ts, identity_of, is_freeleech, is_music_line,
                    media_act, media_cand_get, media_cand_put, media_grab,
                    media_pin_location, media_row_from_ti, media_totals,
                    strip_media_prefix, tag_for)

# ---------------------------------------------------------------------------
# 常量（打分口径，集中在这里，便于以后做成可配权重）
# ---------------------------------------------------------------------------
MUSIC_PLAN_PER_ITEM_DEFAULT = 3      # 每首保留候选条数
MUSIC_PLAN_LIMIT_DEFAULT = 40        # 歌单条数上限
MUSIC_FREE_RATIO = 0.0               # downloadvolumefactor <= 0 → 免费
#: 音乐落盘目录（qB 宿主路径）——★ 17.2.0：音乐单独落 ``/music/下载``（MP 视角），
#: 不能和影视同根：fnOS 的 project quota 让跨 project 硬链接直接 EXDEV
#: （/movie 与 /music 同盘同 st_dev 也链不动），MP 整理只能靠同 project 硬链接。
MUSIC_SAVE_PATH_DEFAULT = "/vol6/1000/music/下载"
#: 每轮 Check 最多补几张专辑的 MP 历史（别让一次 Check 写太多行）
MUSIC_SETTLE_LIMIT = 3
#: 只结算「最近 N 天下完」的种（秒）；历史库里 17 张已手工硬链，重跑会把它们再搬一遍
MUSIC_SETTLE_MAX_AGE = 3 * 86400
#: ★ 19.9.2：同一 hash「数据搬回下载目录」的最小重试间隔（秒）。
#: 成因（2026-10-25 现场）：qB 记的 ``save_path`` 已是音乐目录、数据却在 ``/movie/下载`` 时，
#: ``setLocation`` 是空操作（路径已等值），下一轮 Check 又判定「不在音乐目录」→ 每轮重试。
#: 17 个任务 × 每轮 → 实测 41 行/秒、容器 CPU 90%。加冷却后同一 hash 最多 1 次/小时。
MUSIC_RELOCATE_COOLDOWN = 3600
#: qB 分类 = ``音乐``（常量与判定在 ``common.py``：清理/纳管/任务也要用，必须是纯函数）
MUSIC_GRAB_SLEEP = 1.0               # 两次加种之间的小间隔（别猛打站点/下载器）

# ---------------------------------------------------------------------------
# ★ 19.12.0 · 散曲自建入库（Master 2026-11-03：「这次是我们手动整理的，这个功能需要做进去，
#   是不是要增加排队机制」）
# ---------------------------------------------------------------------------
#: MP 目录配置里音乐库的 ``media_type`` 取值（真值源 = MoviePilot「设置 → 目录」）
MUSIC_MEDIA_TYPE = "音乐"
#: 读不到 MP 目录配置时的库根兜底（容器视角）
MUSIC_LIBRARY_FALLBACK = "/music/library"
#: 判「像专辑」的曲目数上限 —— 超过这个数基本是「合集」而不是专辑。
#: 依据：MP 历史成功整理的专辑平均 9 首、最大 24 首；1258 首那种平铺合集交过去，
#: MP 会逐首走在线识别（每请求 16 次预算，无 Album 的曲子一首吃约 8 次）→ 实际跑不完。
MUSIC_ALBUM_MAX_TRACKS = 24
#: 入库账本槽（``mf_run``）：每颗种的入库结果 —— 幂等判断 + 断点续的真值源
MUSIC_IMPORT_KEY = "music_import"
#: 账本最多留多少条（超出按时间淘汰最旧）
MUSIC_IMPORT_KEEP = 400
#: 每处理多少首落一次账 —— 插件重启后可接着跑，不必重读全部标签
MUSIC_IMPORT_FLUSH_EVERY = 25
#: 扫描去抖：最后一次入库完成后等这么久才触发媒体库扫描（秒）——
#: 连续入库多颗种时不能每颗都触发一次全扫（Navidrome 的 startScan 是全局单例，会互相打断）
MUSIC_SCAN_DEBOUNCE_SEC = 45.0
#: 扫描单飞：上一次请求后多久内不再重复触发（秒）
MUSIC_SCAN_COOLDOWN_SEC = 600.0
#: 只有这些类型的媒体服务器会被刷新 —— MP 的 ``refresh_root_library`` 是**整根库重扫**，
#: 配了影视服务器（trimemedia / emby / jellyfin）时按名字刷会把几 TB 的影视库一起扫一遍。
#: Navidrome 是音乐库；Subsonic/Airsonic 同族（若装了也一并刷）。其余类型一律跳过并记日志。
MUSIC_SCAN_SERVER_TYPES = frozenset(("navidrome", "subsonic", "airsonic"))
#: 可入库的音频扩展名（小写，含点）
MUSIC_AUDIO_EXTS = frozenset((
    ".flac", ".mp3", ".m4a", ".aac", ".wav", ".ape", ".wv", ".dsf", ".dff",
    ".ogg", ".opus", ".wma", ".aif", ".aiff", ".tak", ".tta",
))
#: 文件名里不能出现的字符（Linux 只有 ``/`` 与 NUL 致命，其余一并替换：
#: 库会被 SMB / Navidrome / 播放器跨系统读，统一按最严口径清洗）
_MUSIC_BAD_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')

#: 候选缓存有效期 —— ★ 19.10.11 统一到 tags.MEDIA_CAND_TTL（音乐/点播同一「候选有效期」口径，
#: 人/AI 同一挑选入口）。保留别名供旧引用；MUSIC_CAND_MAX（LRU 上限）随底座换 TierCache 移除
#: —— TierCache 无 scan，靠 TTL 过期控规模（候选一次几十条，上限本就不触发）。
MUSIC_CAND_TTL = MEDIA_CAND_TTL
_MUSIC_CAND_REGION = "musiccand"     # 候选缓存分区（与点播 odpool 分开，互不串味）

#: ★ 音乐线职务标签（不许出现在音乐种上）：音乐单独一条线，**不进魔力/刷流任务**
#: 匹配形如 ``魔流-<站点>-魔力`` / ``魔流-<站点>-刷流``（任务标签）。
_MUSIC_DUTY_STRIP_RE = re.compile(r"^魔流-.+-(魔力|刷流)$")
#: ★ 19.9.0：音乐**在途**职务（``魔流-<站点>-音乐``，归 ``__music__`` 伪任务）。
#: 与上面两个"一律摘"的职务不同：音乐职务只在**下完之后**摘（下载中要免疫静默池）。
_MUSIC_STATE_RE = re.compile(r"^魔流-.+-音乐$")

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

    # ------------------------------------------------------------ §3 搜索自描述（★ 15.9.0）

    @staticmethod
    def _music_row_from_ti(ti: Any) -> Optional[Dict[str, Any]]:
        """TorrentInfo（对象 / dict）→ 音乐候选行（含 ``uploadvolumefactor``）。

        ★ 19.10.11：本体搬到 ``tags.media_row_from_ti``（与点播同源），这里只留薄委托。
        """
        return media_row_from_ti(ti)

    # ---------------------------------------------------------- 候选缓存（★ 15.9.0 §1 → 19.10.11 统一到底座）
    @staticmethod
    def _music_cid(row: Dict[str, Any]) -> str:
        key = f"{int(row.get('site') or 0)}|{str(row.get('enclosure') or '')}"
        return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:12]

    def _music_cand_put(self, cid: str, row: Dict[str, Any]) -> None:
        """候选入池 —— 委托 ``tags.media_cand_put``（脱敏 + 落 TierCache）。"""
        media_cand_put(self, _MUSIC_CAND_REGION, cid, row, MUSIC_CAND_TTL)

    def _music_cand_get(self, cid: str) -> Optional[Dict[str, Any]]:
        """取候选 —— 委托 ``tags.media_cand_get``（过期→None + 按 site 回填凭据）。"""
        cid = str(cid or "").strip()
        if not cid:
            return None
        return media_cand_get(self, _MUSIC_CAND_REGION, cid, MUSIC_CAND_TTL)

    @staticmethod
    def _music_cand_public(row: Dict[str, Any]) -> Dict[str, Any]:
        """候选对外投影：带 ``cid``，**不含** enclosure / cookie / ua / page_url。"""
        def _dv(key: str) -> float:
            v = row.get(key)
            return 1.0 if v is None else float(v)
        return {
            "cid": str(row.get("cid") or ""),
            "title": str(row.get("title") or ""),
            "site": int(row.get("site") or 0),
            "site_name": str(row.get("site_name") or ""),
            "size": float(row.get("size") or 0.0),
            "size_gb": round(float(row.get("size") or 0.0) / 1024 ** 3, 3),
            "seeders": int(row.get("seeders") or 0),
            "downloadvolumefactor": _dv("downloadvolumefactor"),
            "uploadvolumefactor": _dv("uploadvolumefactor"),
            "free": is_freeleech(row.get("downloadvolumefactor")),
            "hit_and_run": bool(row.get("hit_and_run")),
            "score": int(row.get("score") or 0),
            "relevance": float(row.get("relevance") or 0.0),
            "excluded": bool(row.get("excluded")),
            "exclude_reason": str(row.get("exclude_reason") or ""),
        }

    def _music_download_cids(self, cids: List[str], save_path: str = "") -> Dict[str, Any]:
        """★ 15.9.0 §1：按 AI 选中的候选 ``cid`` 逐条加种（写）。

        与 ``_music_grab``（歌单自动计划）不同：这里**不选种**，只把 AI 指定的那几条落下去。
        """
        want = [str(c).strip() for c in (cids or []) if str(c).strip()]
        sp = self._music_save_path(save_path)
        try:
            existing = {str(k).lower() for k in (self._tag_all_torrents() or {})}
        except Exception:  # noqa: BLE001
            existing = set()
        added: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for cid in want:
            row = self._music_cand_get(cid)
            if not row:
                failed.append({"cid": cid, "message": "候选已过期或不存在（请重新搜索）"})
                continue
            res = self._music_grab_one(row, sp, existing=existing)
            base = {"cid": cid, "title": str(row.get("title") or ""),
                    "site": int(row.get("site") or 0), "site_name": str(row.get("site_name") or ""),
                    "size_gb": round(float(row.get("size") or 0) / 1024 ** 3, 2),
                    "free": is_freeleech(row.get("downloadvolumefactor"))}
            if res.get("ok") and res.get("hash"):
                existing.add(str(res["hash"]).lower())
                rec = {**base, "hash": res["hash"]}
                if res.get("skipped"):
                    rec["message"] = res.get("message") or "已在下载器"
                    skipped.append(rec)
                else:
                    added.append(rec)
            else:
                failed.append({**base, "message": str(res.get("message") or "添加失败")})
            time.sleep(MUSIC_GRAB_SLEEP)
        if added:
            try:
                self._store.journal.record(
                    task_id="", kind="selection",
                    items=[OperationItem(hash=a["hash"], title=f"音乐 {a['title']}",
                                         reason=f"源 {a['site_name']}" + ("·免费" if a.get("free") else ""),
                                         free=bool(a.get("free")),
                                         source="music") for a in added],
                )
            except Exception as e:  # noqa: BLE001
                self._log(f"音乐:journal 落盘失败 {e}", "warning")
        self._log(f"音乐:按选择下载 选中 {len(want)} → 新增 {len(added)} / 跳过 {len(skipped)} / 失败 {len(failed)}")
        return {"applied": True, "save_path": sp, "category": MUSIC_CATEGORY,
                "added": added, "skipped": skipped, "failed": failed,
                "summary": {"picked": len(want), "added": len(added), "skipped": len(skipped), "failed": len(failed)},
                "policy": {"flow": "search(cid) → AI 选 → download(cids)；凭据只存服务端候选缓存（30min）"}}

    @staticmethod
    def _music_relevance(title: Any, keyword: Any) -> float:
        """标题相关度（0~1.x）：关键词 token 命中率 + 整串命中加成。用于候选排序（相关度优先）。"""
        t = str(title or "").lower()
        kw = str(keyword or "").lower().strip()
        if not t or not kw:
            return 0.0
        toks = [x for x in re.split(r"[\s\-_/]+", kw) if x]
        if not toks:
            return 0.0
        hit = sum(1 for x in toks if x in t)
        rel = hit / len(toks)
        if kw in t:
            rel += 0.5
        return round(rel, 4)

    async def _music_search_sources(self, keyword: str, site_ids: List[int],
                                    page: int = 0, source: str = "") -> Dict[str, Any]:
        """★ 15.9.0 §3（音乐）：音乐候选 + **每站事实** —— 试透传 MP 原生单页分页（``mtype=Music``）。

        与点播同一套：``SearchChain().search_page_events(params={keyword, mtype, sites, page, source})``。
        MP 的 HTTP 端点对 ``MUSIC`` 禁用 manual_paging，但 chain 层自身无此闸；本端点即实测出入口。
        类型判定仍听 MP（``mtype=MediaType.MUSIC``）；我们只搬事实（``sources[]``）+ 候选归一行。
        """
        kw = str(keyword or "").strip()
        try:
            pg = max(0, int(page or 0))
        except (TypeError, ValueError):
            pg = 0
        src = str(source or "").strip()
        ids: List[int] = []
        for i in (site_ids or []):
            try:
                _i = int(i)
            except (TypeError, ValueError):
                continue
            if _i and _i not in ids:
                ids.append(_i)
        out: Dict[str, Any] = {
            "keyword": kw, "page": pg, "source": src, "sites": ids, "media_type": "music",
            "sources": [], "candidates": [], "total_items": 0, "candidate_items": 0,
        }
        if not kw and not src:
            return out
        target_ids = ids or self._ondemand_sites()
        pkw = kw
        if src:
            _s, _kw = self._od_decode_source(src)
            target_ids = [_s] if _s else []
            pkw = _kw or kw
            out["keyword"] = pkw
        allowed = [i for i in target_ids
                   if not self._pv_block_reason(i) and self._pv_allow(i, "ondemand", want=1)]
        if not allowed:
            self._log("音乐计划:搜索站点 PV 预算不足/已封，跳过", "warning")
            return out
        out["sites"] = allowed
        try:
            from app.chain.search import SearchChain  # noqa: WPS433
            from app.schemas.types import MediaType  # noqa: WPS433
            mtype = MediaType.MUSIC
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"当前 MP 无 SearchChain/MediaType:{e}")
        params: Dict[str, Any] = {"page": pg, "mtype": mtype}
        if src:
            params["source"] = src
            params["keyword"] = pkw
        else:
            params["keyword"] = kw
            params["sites"] = allowed
        chain = SearchChain()
        ev = getattr(chain, "search_page_events", None)
        if not callable(ev):
            raise RuntimeError("当前 MP 无 search_page_events（需 v3.1.2+）")
        facts: List[Dict[str, Any]] = []
        items: List[Any] = []
        try:
            async for event in ev(params=params):
                et = str((event or {}).get("type") or "")
                if et == "error":
                    raise RuntimeError(str(event.get("message") or "搜索失败"))
                if et == "replace":
                    raw = event.get("sources")
                    if raw:
                        facts = [self._od_source_fact(x) for x in raw]
                    items = list(event.get("items") or [])
                    try:
                        out["total_items"] = int(event.get("total_items") or 0)
                    except (TypeError, ValueError):
                        pass
                    try:
                        out["candidate_items"] = int(event.get("candidate_items") or 0)
                    except (TypeError, ValueError):
                        pass
                elif et == "done":
                    raw = event.get("sources")
                    if raw:
                        facts = [self._od_source_fact(x) for x in raw]
        finally:
            for i in allowed:
                self._pv_spend(i, "ondemand", 1)
        out["sources"] = facts
        rows: List[Dict[str, Any]] = []
        for it in items:
            ti = it.get("torrent_info") if isinstance(it, dict) else None
            if ti is None and isinstance(it, dict):
                ti = it
            r = self._music_row_from_ti(ti) if ti is not None else None
            if r:
                rows.append(r)
        scored: List[Dict[str, Any]] = []
        for r in rows:
            s = self._music_score(r)
            r = dict(r)
            r["score"] = s["score"]
            r["excluded"] = bool(s["excluded"])
            r["exclude_reason"] = str(s.get("exclude_reason") or "")
            scored.append(r)
        for r in scored:
            r["cid"] = self._music_cid(r)
            r["relevance"] = self._music_relevance(r.get("title"), pkw)
            if not r["excluded"]:
                self._music_cand_put(r["cid"], r)
        # 排序（Master 2026-10-10）：**标题相关度优先** → 评分 → 做种；被硬过滤的排最后。
        scored.sort(key=lambda r: (1 if r["excluded"] else 0, -float(r.get("relevance") or 0.0),
                                   -int(r["score"] or 0), -int(r.get("seeders") or 0)))
        out["candidates"] = [self._music_cand_public(r) for r in scored]
        self._log(f"音乐:MP 分页搜索「{kw or '(续页)'}」page={pg} → 来源 {len(facts)} / 候选 {len(rows)}")
        return out

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

    # ------------------------------------------------------------------ 加种（写）
    def _music_save_path(self, override: str = "") -> str:
        """音乐保存目录：入参 > 设置 > 默认 ``/vol6/1000/movie/下载``（与点播同根，MP 可监控并硬链进 ``/music``）。

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
        """该种是否属于「音乐线」（qB 分类 = ``音乐``）——委托 ``common.is_music_line``。

        Master 口径：**音乐单独一条线，不与刷流抢** —— 音乐种不纳管进魔力/刷流任务、
        不参与其清理与账本（否则「无进度 / 无上传」会把它当低效种删掉）。
        """
        return is_music_line(obj)

    def _music_untag_duty(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """摘掉音乐种上的「魔力 / 刷流」职务标签（幂等；默认干跑）。

        ★ 19.9.0：音乐在途职务（``魔流-<站>-音乐``，``__music__`` 伪任务）也在本方法摘，
        但**只在下完之后**（``progress>=0.999``）—— 下载中它是免疫静默池的唯一凭据。

        音乐种被魔力任务当同站种纳管过 → 会带上 ``魔流-<站点>-魔力``，从而
        暴露给任务的清理。本方法只摘这一种职务标签，其它标签一律不动。

        ★ 15.8.11：本方法**只动 qB 标签**；账本那一半（``mf_seed.task_id`` 归还静默）
        由 ``TagsMixin._music_ledger_release`` 负责 —— 两者同一轮里先后跑。分开是因为
        账本真值源在 tags 侧（``_tag_state`` 进程级单例），音乐线这里只认 qB 快照；
        返回的 ``stripped``（本轮真摘了标签的整串 hash）给调用方做交叉核对。
        """
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "scanned": 0,
                               "candidates": 0, "cleaned": 0, "failed": 0,
                               "stripped": [], "samples": []}
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
            # ★ 19.9.0：音乐职务（``魔流-<站>-音乐``）只在**下完**后摘；下载中摘掉就回静默池了
            try:
                _done = float(getattr(t, "progress", 0) or 0) >= 0.999
            except Exception:  # noqa: BLE001
                _done = False
            removed = [x for x in tags
                       if _MUSIC_DUTY_STRIP_RE.match(x)
                       or (_done and _MUSIC_STATE_RE.match(x))]
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
                    rep["stripped"].append(str(h).strip().lower())
                else:
                    rep["failed"] = int(rep["failed"]) + 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"音乐线:摘职务标签失败 {str(h)[:12]}:{err}", "warning")
        return rep

    def _music_grab_one(self, row: Dict[str, Any], save_path: str,
                        existing: Optional[set] = None) -> Dict[str, Any]:
        """加一颗音乐种（★ 19.10.11：核心收归 ``tags.media_grab``，本方法只做音乐尾段）。

        ★ 19.9.0：加种即打「身份 ``魔流-<站>-静默-资源`` + 职务 ``魔流-<站>-音乐``」，
        并挂 ``__music__`` 伪任务（账本 ``state=音乐``）→ 下载中免疫静默池；下完由
        ``_music_untag_duty`` 摘职务、``_music_ledger_release`` 归还静默池（成为「资源」）。
        取种/标签/幂等/钉目录全在共享实现里；这里只挂伪任务（task_id 真值源在 common.py）。
        """
        res = media_grab(self, row, save_path, kind="music",
                         existing=existing, downloader_name="qbittorrent",
                         pv_gate=True, infohash=info_hash)
        if not res.get("ok") or res.get("skipped"):
            return res
        h = res["hash"]
        site_name = str(row.get("site_name") or "")
        # ★ 19.9.0：加种即挂 __music__ 伪任务（职务=音乐）→ 同点播语义
        try:
            self._music_assign([h], site=site_name, sub=SUB_RESOURCE, reason="加种")
        except Exception as _mae:  # noqa: BLE001
            self._log(f"音乐线:挂伪任务失败 {str(h)[:12]}: {_mae}", "warning")
        return res

    # ---------------------------------------------------------- MP 整理入库（★ 17.2.0）

    def _music_mp_path(self, path: Any) -> str:
        """下载器宿主路径 → MP（容器）视角路径（按 downloader 的 path_mapping 反向映射）。"""
        raw = str(path or "").strip()
        if not raw:
            return ""
        try:
            dl = self._get_downloader("qbittorrent")
            if dl is not None and getattr(dl, "is_available", False):
                return str(dl.normalize_path(raw) or raw)
        except Exception:  # noqa: BLE001
            pass
        return raw

    @staticmethod
    def _music_transferred(h: str) -> bool:
        """该 hash 是否已有**成功**整理记录（MP transferhistory status=1）。"""
        try:
            from app.db.oper.transferhistory import TransferHistoryOper  # noqa: WPS433
            rows = TransferHistoryOper().list_by_hash(str(h or "").lower()) or []
        except Exception:  # noqa: BLE001
            return False
        return any(bool(getattr(r, "status", False)) for r in rows)

    def _music_transfer_dest(self, h: str) -> str:
        """该 hash 最近一条成功整理的``目标目录``（事件没收到时用历史行补库记）。"""
        try:
            from app.db.oper.transferhistory import TransferHistoryOper  # noqa: WPS433
            rows = TransferHistoryOper().list_by_hash(str(h or "").lower()) or []
        except Exception:  # noqa: BLE001
            return ""
        for r in reversed(rows):
            if bool(getattr(r, "status", False)):
                return str(getattr(r, "dest", "") or "")
        return ""

    #: ★ 19.9.3：入库完成但**仍在下**的种，账本 sub 临时钉在这里 ——
    #: 不能直接写「资源」：清单的「已完成」Tab 判据就是 sub==资源，
    #: 分片/音频先到而整体 progress 还没到 1 时会被误判成已完成（19.8.1 引入）。
    SUB_DOWNLOADING = "下载中"


    def _music_release_done(self, h: str, sub: str = SUB_RESOURCE) -> bool:
        """★ 19.9.4：音乐下完 → 摘「音乐」职务，交回静默池（与点播 _od_release 同构）。

        在途（progress<1）只记账本身份「下载中」，职务 魔流-<站>-音乐 留在种子上；
        下完：本方法摘职务（qB 标签回 魔流-<站>-静默-<子>）+ 账本 taken_by/task 清空
        → 归静默闸管辖，清单落到「已完成」。幂等：没有音乐职务也没有占用时直接 True。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        try:
            store = self._tag_state()
            dl = self._get_downloader("qbittorrent")
            live = (self._tag_all_torrents() or {}).get(hh)
        except Exception:  # noqa: BLE001
            return False
        if dl is None or not getattr(dl, "is_available", False):
            return False
        cur = [str(x).strip() for x in (getattr(live, "tags", None) or []) if str(x).strip()] \
            if live is not None else []
        _site, _cur_sub = identity_of(cur)
        rec = store.get(hh) or {}
        _site = str(rec.get("site") or "") or _site
        _sub = str(sub or "") or str(rec.get("sub") or "") or _cur_sub or SUB_RESOURCE
        if _sub == self.SUB_DOWNLOADING:
            _sub = SUB_RESOURCE
        need_tag = bool(cur) and any(_MUSIC_STATE_RE.match(x) for x in cur)
        if need_tag:
            new_tags = [x for x in cur if not _MUSIC_STATE_RE.match(x)]
            if not any(identity_of([x])[0] for x in new_tags):
                new_tags.insert(0, tag_for(_site, STATE_SILENT, _sub))
            try:
                fn = getattr(dl, "replace_torrent_tags", None)
                ok = fn(hh, new_tags) if callable(fn) else dl.set_torrent_tags(hh, new_tags)
            except Exception as err:  # noqa: BLE001
                self._log(f"音乐:摘职务失败 {hh[:12]}:{err}", "warning")
                return False
            if not ok:
                return False
        # ★ 19.10.8：下完**先过 H&R 检查站**——欠债的交 ``__hr_host__`` 保种。
        #   （静默池不变量是「一律 pause」，裸归静默 = 把做种时钟停在那一刻；
        #   2026-10-27 现场：CARPT 8 颗音乐种只挂到 ~22h，站方 H&R 还差 2h。）
        # ★ 19.12.37：判据改用 ``_hr_should_hold`` —— 先过「该不该记」的两道门槛。
        #   直接用 ``_hr_obligation`` 会让「站点规则未知」走未知保守 24h，馒头（m-team.cc）
        #   的音乐种因此被反复搬进保种又被释放（线上日志每秒刷屏）。
        try:
            _owed = bool(live is not None and self._hr_should_hold(_site, live))
        except Exception:  # noqa: BLE001
            _owed = False
        if _owed:
            try:
                if self._hr_host_assign([hh], reason="音乐下完欠 H&R"):
                    self._log(f"音乐:{hh[:12]} 下完仍欠 H&R → 交保种宿主（不归静默）")
                    return True
            except Exception as err:  # noqa: BLE001
                self._log(f"音乐:交保种失败 {hh[:12]}:{err}", "warning")
        try:
            store.release(hh)
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐:账本归还失败 {hh[:12]}:{err}", "warning")
            return False
        return True
    def _music_mark_library(self, h: str, dest: str) -> None:
        """把已整理的音乐种写进「库记」（``TransferComplete`` 事件偶发收不到时兜底）。

        ★ 19.9.3：**下完才写「资源」**。种子还在下载（``progress<0.999``）时只写库记，
        身份保持「下载中」（原来直接 set_asset(sub="资源") → 清单把它算进「已完成」，
        现场症状：「进行中不显示，反而出现在已完成里」）。
        """
        # ★ 19.10.8：**幂等** —— 同一 (hash, 库路径) 只处理一次。
        #   原来每轮 Check 对每颗已整理的音乐种都跑一遍 ``release()``：
        #   ① 实测每 5 秒刷 8 行「音乐:库记」（日志风暴，把真问题埋掉）；
        #   ② 更致命：``release()`` 会把 ``taken_by=__hr_host__`` 清掉 →
        #      欠 H&R 的种被踢出保种宿主 → 静默闸立刻 pause → 做种时长冻住。
        _hh0 = str(h or "").strip().lower()
        try:
            _seen = getattr(self, "_music_lib_seen", None)
            if not isinstance(_seen, set):
                _seen = set()
                self._music_lib_seen = _seen
            _sig = f"{_hh0}:{str(dest or '')[:48]}"
            if _hh0 and _sig in _seen:
                return
            if _hh0:
                if len(_seen) > 5000:
                    _seen.clear()
                _seen.add(_sig)
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..common import HR_HOST_TASK_ID, KEEP_TASK_ID  # noqa: WPS433 惰性导入（离线测试不碰 common）
        except Exception:  # noqa: BLE001
            HR_HOST_TASK_ID = "__hr_host__"
            KEEP_TASK_ID = "__keep__"
        try:
            gid = self._tag_groups().queue_library(h, path=dest or "", media_id="")
            _state_store = self._tag_state()  # 复用
            try:
                _live = (self._tag_all_torrents() or {}).get(_hh0)
            except Exception:  # noqa: BLE001
                _live = None
            # ★ 19.10.8：欠 H&R 的种归 ``__hr_host__`` 保种 —— 账本**一个字都不许动**。
            try:
                _rec = _state_store.get(h) or {}
            except Exception:  # noqa: BLE001
                _rec = {}
            #   ★ 19.12.38：职务拆开后「保种」= __keep__（STATE_KEEP），「H&R」= __hr_host__。
            #   两者都不许动（人工点名的种被 H&R 线 release 掉 = 让「长期做种」名存实亡）。
            _hr_hosted = (str(_rec.get("taken_by") or "") in (HR_HOST_TASK_ID, KEEP_TASK_ID)
                          or str(_rec.get("state") or "") in (STATE_HR, STATE_KEEP))
            # 19.9.4: 职务与身份分开写 ---- 下载中的种保留 __music__ 职务，只把身份钉成下载中
            if _hr_hosted:
                pass
            elif _live is None or float(getattr(_live, "progress", 0) or 0.0) >= 0.999:
                _state_store.release(h)
            else:
                _state_store.set_asset(h, sub=self.SUB_DOWNLOADING)
            if gid:
                self._log(f"音乐:库记 {h[:12]} → 资源 {gid[:46]} 路径 {dest or '-'}")
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐:库记失败 {h[:12]}:{err}", "warning")

    def _music_relocate(self, h: str, dest: str) -> bool:
        """把种子数据搬回指定目录 → 薄委托 ``tags.media_pin_location``（★ 19.10.11 合一）。

        qB「自动管理」会把任务放到默认下载目录（movie project）→ 硬链进 ``/music``
        被 EXDEV 拒绝。音乐踩过的坑，点播加种同样受益（`media_grab` 统一钉目录）。
        本方法名保留（settle 路径与测试调用点不动）。
        """
        return media_pin_location(self, h, dest)

    def _music_transfer_now(self, h: str, t: Any, mp_path: str) -> Tuple[bool, str]:
        """直调 MP ``manual_transfer`` 整理入库（与点播同一条路线）。

        ★ 2026-10-24 铁牛复核：音乐线不再「补历史 + 打 MOVIEPILOT → 等 MP 定时任务」——
        那条路在 ``transfer_type=link`` 下会让 MP 每分钟重扫同一批源文件（日志刷
        「已整理过」），且魔流的标签卫生会把 MP 的「已整理」摘掉，两个插件互相打架。
        直调一次完成：不打 MP 标签 → MP 定时任务天然扫不到，不会并发；
        失败时用 ``_transfer_already_done`` 兜底（「已整理过」= 文件早在库）。
        """
        key = str(h or "").strip().lower()
        try:
            import os  # noqa: WPS433

            from app.chain.transfer import TransferChain  # noqa: WPS433
            from app.schemas.file import FileItem  # noqa: WPS433
            from app.schemas.types import MediaType  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return False, f"MP 整理接口不可用: {err}"
        path = str(mp_path or "").rstrip("/")
        if not path or not key:
            return False, "缺少整理路径或 hash"
        fileitem = FileItem(path=path, storage="local",
                            type="dir" if os.path.isdir(path) else "file",
                            name=os.path.basename(path))
        try:
            ok, msg = TransferChain().manual_transfer(
                fileitem=fileitem,
                mtype=MediaType.MUSIC,
                music_type="album",
                downloader="qbittorrent",
                download_hash=key,
                skip_success=True,
            )
        except Exception as err:  # noqa: BLE001
            return False, f"整理异常: {err}"
        if not ok and self._transfer_already_done(str(msg or "")):
            return True, str(msg or "已整理过")
        return bool(ok), str(msg or "")

    def _music_settle_import(self, apply: bool = True, limit: int = 0) -> Dict[str, int]:
        """★ 17.2.0 §1 音乐：下完成的专辑 → 入库（★ 19.12.0 起**入队后台跑**）。

        - 只认**音乐线**（qB 分类 ``音乐``）且落在音乐下载目录下、``progress >= 0.999`` 的种；
        - 只结算 3 天内下完的种（历史手工硬链专辑不能再搬一次）；
        - ★ 19.12.0：本方法只做**发现 + 入队**，真正的搬动在 JobQueue 后台线程里
          （``_music_import_run``）。原因：原来是同步直调 MP ``manual_transfer``，
          而它一次要几十秒到几小时 —— 挂在刷流 Check 里会被全局并发闸门常年饿死，
          挂在前端请求里则客户端一断就中止（手动整理那次就是这么断的）。
        - 入库路线由 ``_music_import_route`` 按标签完备度分流：标签齐的走 MP 整理，
          散曲/缺 Album 的走自建硬链接；
        - 已有成功整理记录的直接 skipped + 补库记；失败只计数，下轮重试。
        """
        rep: Dict[str, int] = {"scanned": 0, "pending": 0, "settled": 0,
                               "skipped": 0, "failed": 0, "written": 0,
                               "relocated": 0, "reloc_skip": 0, "queued": 0}
        try:
            idx = self._tag_all_torrents() or {}
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐:整理入库跳过本轮（下载器快照不可用）: {err}", "warning")
            return rep
        try:
            save_root = str(self._music_save_path() or "").rstrip("/")
        except Exception:  # noqa: BLE001
            save_root = ""
        cap = int(limit or 0) or MUSIC_SETTLE_LIMIT
        done = 0
        # ★ 19.9.2：relocate 冷却表（进程级）——同一 hash 一小时最多试一次
        reloc_ts = getattr(self, "_music_reloc_ts", None)
        if not isinstance(reloc_ts, dict):
            reloc_ts = {}
            self._music_reloc_ts = reloc_ts
        now = time.time()
        for h, t in (idx or {}).items():
            try:
                if not self._is_music_line(t):
                    continue
                rep["scanned"] += 1
                if float(getattr(t, "progress", 0) or 0) < 0.999:
                    continue
                raw = (str(getattr(t, "content_path", "") or "").strip()
                       or str(getattr(t, "save_path", "") or "").strip())
                key = str(h or "").strip().lower()
                if not key:
                    continue
                if save_root and not (raw == save_root or raw.startswith(save_root + "/")):
                    # 只结算魔流自己下进来的种，别动历史手工库；
                    # 但 qB「自动管理」可能把数据落到默认目录 → 搬回音乐下载目录，下轮再结算
                    # ★ 19.9.2：qB 记的 save_path 已经是目标目录时，setLocation 是**空操作**
                    #   （数据在别处、路径却已改写）→ 直接跳过，否则每轮 Check 都会重试刷屏空转。
                    if str(getattr(t, "save_path", "") or "").rstrip("/") == save_root:
                        rep["reloc_skip"] = int(rep["reloc_skip"]) + 1
                        continue
                    if not apply:
                        continue
                    if now - float(reloc_ts.get(key) or 0.0) < MUSIC_RELOCATE_COOLDOWN:
                        rep["reloc_skip"] = int(rep["reloc_skip"]) + 1
                        continue
                    reloc_ts[key] = now
                    if self._music_relocate(key, save_root):
                        rep["relocated"] = int(rep["relocated"]) + 1
                        self._log(f"音乐:数据搬回下载目录 {key[:12]} → {save_root}")
                    continue
                added = float(getattr(t, "added_on", 0) or 0)
                if added > 0 and time.time() - added > MUSIC_SETTLE_MAX_AGE:
                    continue  # 老种（已在库/手工硬链过的）不重复搬
                rep["pending"] += 1
                if not apply:
                    continue
                if self._music_transferred(key):
                    rep["skipped"] += 1
                    self._music_mark_library(key, self._music_transfer_dest(key))
                    continue
                # ★ 19.12.0：自建入库完成的种（账本 done 且无失败）同样算结案 ——
                #   本方法只认 MP transferhistory 的话，散曲合集会被每轮重复入队
                #   （虽然队列里会被账本立即挡回，但白占槽位、日志也会刷屏）。
                if self._music_import_done(key):
                    rep["skipped"] += 1
                    try:
                        self._music_release_done(key)
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                if done >= cap:
                    continue
                done += 1
                mp_path = self._music_mp_path(raw)
                if not mp_path:
                    rep["failed"] += 1
                    continue
                # ★ 19.12.0：入库改为**入队**（原来是同步直调 MP 整理）。
                #   同一 hash 在队列里已有 queued/running 任务时 ``dedup_key`` 直接返回既有那条，
                #   所以每轮 Check 都能放心调，不会把同一颗种排 N 次。
                _title = str(getattr(t, "title", "") or getattr(t, "name", "") or "")
                _job = self._music_import_submit(key, _title, reason="下完自动")
                if _job.get("id"):
                    rep["settled"] += 1
                    rep["queued"] = int(rep["queued"]) + 1
                    if not _job.get("dedup"):
                        self._log(f"音乐:入库已入队 {key[:12]}「{_title[:40]}」"
                                  f"（job {_job.get('id')}，后台跑，关页面不中断）", "debug")
                else:
                    rep["failed"] += 1
                    self._log(f"音乐:入库入队失败 {key[:12]}", "warning")
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"音乐:整理入库异常 {str(h)[:12]}: {err}", "warning")
        return rep

    # ---------------------------------------------------------- §1 音乐清单（★ 15.9.0）

    _MUSIC_ACTS = ("pause", "resume", "remove")


    @staticmethod
    def _music_free(op: Any, t: Any) -> bool:
        """音乐线「是否免费」：qB 有折扣值就信 qB，没有就回落到加种当时记的站点真值。

        ★ 19.11.23：``downloadvolumefactor`` **不在** qB ``/torrents/info`` 的返回字段里，
        只读 qB 恒得 ``None`` → ``is_freeleech(None)`` 全判「非免费」，与 ``source_note``
        写的「源 xx·免费」自相矛盾（会让人以为在下计下载量的种）。
        qB 真给了值以 qB 为准；给不出才用 journal 操作项上留的底。
        """
        dvf = getattr(t, "downloadvolumefactor", None) if t is not None else None
        if dvf is not None:
            return is_freeleech(dvf)
        if getattr(op, "free", False):
            return True
        # 老记录（19.11.23 之前落盘）没有 free 字段，从 dict 还原只会拿到默认 False。
        # reason 是**本模块自己写的固定格式**（"源 xx" / "源 xx·免费"，见 _music_download_cids），
        # 属于同源折扣数据的降级表示，不是对站点事实的猜测；只认明确带「·免费」的。
        return "·免费" in str(getattr(op, "reason", "") or "")


    def _music_item_row(self, h: str, t: Any, rec: Dict[str, Any],
                        op: Any = None, jr: Any = None) -> Dict[str, Any]:
        """音乐清单一行（**字段与点播 Item 同构**，``module="music"``）。

        ``t``=qB 快照对象（历史行可为 None）；``rec``=账本行；``op``=journal 操作项；``jr``=journal 记录。
        """
        prog = float(getattr(t, "progress", 0) or 0.0) if t is not None else 0.0
        size_gb = float(getattr(t, "size_gb", 0) or 0.0) if t is not None else 0.0
        spd = float(getattr(t, "download_speed", 0) or 0.0) if t is not None else 0.0
        left_gb = max(0.0, size_gb * (1.0 - prog))
        if t is not None:
            title = str(getattr(t, "title", "") or "")
        else:
            title = strip_media_prefix(str(getattr(op, "title", "") or ""), "music")
        base_ts = float(getattr(jr, "created_at", 0) or 0.0)
        row: Dict[str, Any] = {
            "hash": h,
            "module": "music",
            "stage": "gone", "stage_text": "已不在下载器",
            "title": title, "year": "",
            "site": str((rec or {}).get("site") or ""),
            "progress": 0.0, "percent": 0.0, "state": "",
            "size_gb": round(size_gb, 3), "downloaded_gb": round(size_gb * prog, 3),
            "left_gb": round(left_gb, 3), "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": self._music_free(op, t),
            "hit_and_run": bool(getattr(t, "hit_and_run", False)) if t is not None else bool((rec or {}).get("hit_and_run")),
            "in_qb": t is not None,
            "in_library": bool((rec or {}).get("in_library")),
            "save_path": str(getattr(t, "save_path", "") or "") if t is not None else "",
            "added_at": fmt_iso_ts(base_ts),
            "settled_at": fmt_iso_ts((rec or {}).get("identity_at")),
            "source_note": str(getattr(op, "reason", "") or ""),
            "_ts": base_ts,
        }
        if t is None:
            return row
        row["progress"] = round(prog, 4)
        row["percent"] = round(prog * 100.0, 2)
        row["state"] = str(getattr(t, "state", "") or "")
        row["speed"] = round(spd, 1)
        row["ratio"] = round(float(getattr(t, "ratio", 0) or 0.0), 3)
        if prog < 0.999:
            row["stage"] = "downloading"
            row["stage_text"] = "下载中"
            if spd > 0:
                row["eta_s"] = int(left_gb * (1024 ** 3) / spd)
        elif str((rec or {}).get("sub") or "") == SUB_RESOURCE:
            row["stage"] = "resource"
            row["stage_text"] = "已转「资源」" + ("·已入库" if row["in_library"] else "")
        elif str((rec or {}).get("sub") or "") == self.SUB_DOWNLOADING:
            # ★ 19.9.3：已入库但**还没下完**（分片/音频先到）—— 仍是「进行中」，
            #   不能被算成已完成；进度条照常显示。
            row["stage"] = "downloading"
            row["stage_text"] = "下载中·已入库"
        else:
            row["stage"] = "settling"
            row["stage_text"] = "已下完，待转「资源」"
        return row

    def _music_hist_row(self, h: str, t: Any, rec: Dict[str, Any],
                        op: Any = None, jr: Any = None) -> Dict[str, Any]:
        """音乐**下载记录**一行（与点播 ``_ondemand_hist_row`` 同口径）。

        ★ 19.8.1（2026-10-25 Master「任务结束了，你什么状态跟我音乐任务没关系了，你顶多留个
        下载记录，具体可以参照点播」）：音乐线**交棒给静默池之后**（账本 ``sub=资源``）或
        种已不在下载器 → 本窗口只留一条**静态下载记录**，不再回查 qB 现况
        （``state`` / 进度 / 速度 / ``in_qb`` 一律不取）—— 否则静默池的 ``pausedUP`` 会被
        当成音乐任务的毛病。``t`` 只用来补标题/体积（只读，不取其状态）。
        """
        sub = str((rec or {}).get("sub") or "")
        prog = 1.0 if sub == SUB_RESOURCE else 0.0
        size_gb = float(getattr(t, "size_gb", 0) or 0) if t is not None else 0.0
        if t is not None:
            title = str(getattr(t, "title", "") or "")
        else:
            title = strip_media_prefix(str(getattr(op, "title", "") or ""), "music")
        inlib = bool((rec or {}).get("in_library"))
        stage = "resource" if prog else "gone"
        base_ts = float(getattr(jr, "created_at", 0) or 0.0)
        return {
            "hash": h,
            "module": "music",
            "stage": stage,
            "stage_text": ("已转「资源」" + ("·已入库" if inlib else "")) if stage == "resource" else "已结案",
            "title": title, "year": "",
            "site": str((rec or {}).get("site") or ""),
            "progress": round(prog, 4), "percent": round(prog * 100.0, 2),
            "state": "",
            "size_gb": round(size_gb, 3),
            "downloaded_gb": round(size_gb * prog, 3),
            "left_gb": 0.0, "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": self._music_free(op, t),
            "hit_and_run": (bool(getattr(t, "hit_and_run", False)) if t is not None
                            else bool((rec or {}).get("hit_and_run"))),
            "in_qb": False,
            "in_library": inlib,
            "save_path": "",
            "added_at": fmt_iso_ts(base_ts),
            "settled_at": fmt_iso_ts((rec or {}).get("identity_at")),
            "source_note": str(getattr(op, "reason", "") or ""),
            "_ts": base_ts,
        }

    def _music_deleted_hashes(self) -> Set[str]:
        """★ 2026-10-10（Master「音乐线一样的」）：**音乐撤单成功**过的 hash。

        真值源：删除台账（mf_deletions，离线回退 deletions.jsonl），``source=="music"`` 且 ``ok`` 且未被闸门拦。
        用途：一颗被音乐线**撤单**拿掉的种，如果之后又出现在下载器里，说明它已被**别的线
        （辅种/补源/手动）接管**，不再是音乐线的 → 音乐窗口不认。
        """
        out: Set[str] = set()
        try:
            fn = getattr(self, "_agent_deletions_rows", None)
            rows = fn() if callable(fn) else []
        except Exception:  # noqa: BLE001
            return out
        for r in (rows or []):
            try:
                if str((r or {}).get("source") or "") != "music":
                    continue
                if not (r or {}).get("ok") or (r or {}).get("blocked"):
                    continue
                h = str((r or {}).get("hash") or "").strip().lower()
                if h:
                    out.add(h)
            except Exception:  # noqa: BLE001
                continue
        return out

    def _music_items(self, limit: int = 50) -> Dict[str, Any]:
        """音乐干净清单（★ 15.9.0）：**单列表** ``items[]``（与点播同构）+ ``totals``。

        真值源（只读，不新造）：
          - **进行中** = qB 快照里 ``is_music_line``（qB 分类=音乐）**且尚未交棒**的种
            （进度/状态/速度）；
          - **下载记录** = 已交棒静默池（账本 ``sub=资源``）或已不在下载器的行 —— 静态记录，
            **不取 qB 现况**（``_music_hist_row``；★ 19.8.1 参照点播历史口径）；
          - 身份/入库标记 = 种子账本（site/sub/in_library/identity_at）。
        """
        try:
            cap = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            cap = 50
        snap_l: Dict[str, Any] = {}
        try:
            for k, v in (self._tag_all_torrents() or {}).items():
                snap_l[str(k).lower()] = v
        except Exception:  # noqa: BLE001
            snap_l = {}
        try:
            recs = self._store.journal.list_recent(limit=5000) if self._store is not None else []
        except Exception:  # noqa: BLE001
            recs = []
        jop: Dict[str, Any] = {}
        jr: Dict[str, Any] = {}
        for r in recs:
            for it in (getattr(r, "items", None) or []):
                if str(getattr(it, "source", "") or "") != "music":
                    continue
                hh = str(getattr(it, "hash", "") or "").lower()
                if hh and hh not in jop:
                    jop[hh] = it
                    jr[hh] = r
        seen: Set[str] = set()
        _m_deleted = self._music_deleted_hashes()
        # ★ 19.9.3：旧版把「在下载但已入库」的种误标成身份=资源 → 这里按 qB 真值纠正回来
        #   （否则它们在「已完成」里常驻；只需修一次，之后就由 mark_library 按进度写对）。
        try:
            _store = self._tag_state()
            _snapfix = self._tag_all_torrents() or {}
            for _h, _t in _snapfix.items():
                if not self._is_music_line(_t):
                    continue
                try:
                    _p = float(getattr(_t, "progress", 0) or 0)
                except Exception:  # noqa: BLE001
                    continue
                if _p >= 0.999:
                    continue
                _r = _store.get(_h) or {}
                if str(_r.get("sub") or "") == SUB_RESOURCE:
                    _store.set_asset(_h, sub=self.SUB_DOWNLOADING)
                    self._log(f"音乐:纠正误标 在下载却记作资源 {str(_h)[:12]}")
        except Exception:  # noqa: BLE001
            pass
        rows: List[Dict[str, Any]] = []
        for h, t in snap_l.items():
            if not self._is_music_line(t):
                continue
            seen.add(h)
            rec = self._ondemand_seed_rec(h)
            # ★ 19.8.1：已交棒静默池（账本 sub=资源）→ 只留下载记录，不取 qB 现况。
            if str((rec or {}).get("sub") or "") == SUB_RESOURCE:
                rows.append(self._music_hist_row(h, t, rec, jop.get(h), jr.get(h)))
            else:
                rows.append(self._music_item_row(h, t, rec, jop.get(h), jr.get(h)))
        for h, it in jop.items():
            if h in seen:
                continue
            seen.add(h)
            # ★ 本线撤单过、却又回到下载器里 → 已被别的线接管，本窗口不认。
            if h in _m_deleted and snap_l.get(h) is not None:
                continue
            # ★ 19.8.1：只剩 journal/账本、或已交棒 → 记录行（与点播历史同口径）。
            rows.append(self._music_hist_row(h, snap_l.get(h), self._ondemand_seed_rec(h),
                                             it, jr.get(h)))
        rows.sort(key=lambda x: float(x.get("_ts") or 0.0), reverse=True)
        rows = rows[:cap]
        for x in rows:
            x.pop("_ts", None)
        totals = media_totals(rows)
        return {"items": rows, "totals": totals}

    def _music_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """音乐行内操作：``pause`` / ``resume`` / ``remove``（音乐线仅限 qB 分类=音乐的种）。

        ★ 19.10.11：写口搬到 ``tags.media_act``（与点播**共用同一个删除闸门**），
        本方法只剩「归属判定」（在下载器 + qB 分类=音乐）这一个音乐特有的前置。
        回执统一 ``{ok, hash, action, message, blocked}``；``remove`` 走唯一删除闸门（不绕）。
        """
        def _belong(h: str) -> Optional[str]:
            try:
                snap = {str(k).lower(): v for k, v in (self._tag_all_torrents() or {}).items()}
            except Exception as e:  # noqa: BLE001
                return f"下载器不可用:{e}"
            t = snap.get(h)
            if t is None:
                return "该种不在下载器（音乐清单只操作在库种）"
            if not self._is_music_line(t):
                return "该种不属于音乐线（拒绝操作）"
            return None

        return media_act(self, hash, action, kind="music",
                         acts=self._MUSIC_ACTS, belong=_belong)

    # ============================================================
    # ★ 19.12.0 · 音乐散曲自建入库（Master 2026-11-03）
    #
    # 「这次是我们手动整理的，这个功能需要做进去，是不是要增加排队机制」——手动那次的做法
    # （全量读标签 → 按 ``歌手/专辑`` 算目标路径 → ``ln`` 硬链接 → 触发媒体库扫描）固化成能力。
    #
    # 为什么不能只靠 MP 整理（实测，不是推测）：
    #   1258 首的散曲合集里 **1139 首没有 Album 标签**。MP 的 ``music_tags_are_usable`` 要求
    #   title+album+artist 齐全，缺一个就转 MusicBrainz 在线识别；而每次请求只有
    #   ``request_limit=16`` 次识别预算，无专辑曲目一首吃约 8 次 → **一次只能过 2 首**，
    #   第 3 首直接 ``budget_exhausted``（不可重试兜底）。1139 首要 600+ 次请求、十几小时，
    #   且中文老歌 MB 基本查不到 → 表现就是「一直在扫、库零新增、没有任何报错」。
    #
    # 所以按标签完备度分流（判据见 ``_music_import_route``），两条路都留：
    #   * 标签齐 + 曲目数像专辑 → MP ``manual_transfer``（要它的刮削与媒体库回写）
    #   * 其余（散曲合集 / 缺专辑标签）→ 自建硬链接（读标签算路径，秒级完成）
    #
    # 三条硬约束：
    #   1. **只硬链接，不复制不移动** —— 源文件 links 从 1→2，零额外占用，qB 做种不受影响；
    #   2. 目标已存在先比 inode：同 inode = 自己链过的（幂等跳过）；不同 = 真重名 →
    #      加 `` (2)`` 后缀，**绝不覆盖**（500 位歌手 1258 首里一定有同名不同版本）；
    #   3. 跨 project 链不动（fnOS 的 project quota 让 ``/movie`` 与 ``/music`` 同盘也报 EXDEV）
    #      → 记 ``exdev`` 并明确报出，**不静默降级成复制**（复制会真占空间、且没人知道）。
    # ============================================================

    def _music_lib_dirs(self) -> Tuple[str, str]:
        """音乐库 / 音乐下载目录（**MP 视角**路径）→ ``(library_path, download_path)``。

        真值源 = MoviePilot「设置 → 目录」里 ``media_type == 音乐`` 的那条记录。
        不写死路径：用户换盘/改目录后这里自动跟上，写死会默默往旧盘写。
        读不到配置时回退 ``MUSIC_LIBRARY_FALLBACK`` / ``MUSIC_SAVE_PATH_DEFAULT``。
        """
        lib = dl = ""
        try:
            from app.application.directory import DirectoryHelper  # noqa: WPS433
            for d in (DirectoryHelper().get_dirs() or []):
                if str(getattr(d, "media_type", "") or "").strip() != MUSIC_MEDIA_TYPE:
                    continue
                lib = str(getattr(d, "library_path", "") or "").strip().rstrip("/")
                dl = str(getattr(d, "download_path", "") or "").strip().rstrip("/")
                break
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐入库:读 MP 目录配置失败（回退默认路径）: {err}", "warning")
        return (lib or MUSIC_LIBRARY_FALLBACK), (dl or MUSIC_SAVE_PATH_DEFAULT)

    @staticmethod
    def _music_audio_files(root: str, limit: int = 0) -> List[str]:
        """递归列出 ``root`` 下的音频文件（按路径排序，便于断点续时顺序稳定）。

        ``root`` 可能是单文件（单轨种）也可能是目录（合集）；非音频扩展名一律跳过。
        """
        try:
            if os.path.isfile(root):
                ext = os.path.splitext(root)[1].lower()
                return [root] if ext in MUSIC_AUDIO_EXTS else []
            if not os.path.isdir(root):
                return []
        except OSError:
            return []
        out: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() not in MUSIC_AUDIO_EXTS:
                    continue
                out.append(os.path.join(dirpath, name))
                if limit and len(out) >= limit:
                    return sorted(out)
        return sorted(out)

    @staticmethod
    def _music_read_tags(path: str) -> Dict[str, str]:
        """读一首歌的 ``artist`` / ``album`` / ``title``（mutagen easy 模式，缺的留空串）。

        容器内 mutagen 1.47.0 可用（实测）。用 ``easy=True`` 拿规整后的字符串列表，
        不碰二进制帧；读失败不抛（标签坏了不该让整批整理停摆），只把 title 用文件名兜底。
        """
        out: Dict[str, str] = {"artist": "", "album": "", "title": ""}
        try:
            from mutagen import File as _MutagenFile  # noqa: WPS433
            f = _MutagenFile(path, easy=True)
            if f is not None:
                for k in out:
                    v = f.get(k)
                    if isinstance(v, (list, tuple)):
                        v = v[0] if v else ""
                    out[k] = str(v or "").strip()
        except Exception:  # noqa: BLE001
            pass
        if not out["title"]:
            out["title"] = os.path.splitext(os.path.basename(path))[0]
        return out

    @staticmethod
    def _music_safe_name(raw: Any, default: str = "") -> str:
        """文件名/目录名清洗：替换跨系统非法字符、压空白、去首尾点、截断到 120 字。

        库会被 SMB / Navidrome / 各种播放器读，按最严口径（Windows 非法字符）清洗，
        免得只在一部分客户端上炸。
        """
        t = _MUSIC_BAD_CHARS.sub("_", str(raw or "")).strip().strip(".")
        t = re.sub(r"\s+", " ", t)
        return t[:120] or default or "未知"

    def _music_import_plan(self, h: str, t: Any, lib: str, cap: int = 0) -> Dict[str, Any]:
        """扫一颗种 → 入库计划（**干跑**：只读标签、算目标路径，不碰文件系统）。

        返回 ``{"route": mp|link|skip, "items": [...], "total", "reason"}``；
        每项 ``{src, dst, artist, album, title, ext, size}``。
        """
        raw = (str(getattr(t, "content_path", "") or "").strip()
               or str(getattr(t, "save_path", "") or "").strip())
        mp_path = self._music_mp_path(raw)
        if not mp_path:
            return {"route": "skip", "items": [], "total": 0, "reason": "该种没有落盘路径"}
        files = self._music_audio_files(mp_path, limit=cap)
        if not files:
            return {"route": "skip", "items": [], "total": 0,
                    "reason": "种内没有可入库的音频文件"}
        items: List[Dict[str, Any]] = []
        for src in files:
            tg = self._music_read_tags(src)
            ext = os.path.splitext(src)[1].lower()
            artist = self._music_safe_name(tg.get("artist"), "未知歌手")
            title = self._music_safe_name(tg.get("title"),
                                          os.path.splitext(os.path.basename(src))[0])
            # ★ 空专辑**不兜底**：``_music_safe_name`` 的 default 会兜成「未知」，
            #   那等于凭空造一张「未知」专辑 —— 与手工那次落的 ``库/歌手/歌名.flac`` 不是同一路径，
            #   重跑会再链一份（1258 首全被复制一遍）。空就是空，路径直接省掉专辑层。
            album = (self._music_safe_name(tg.get("album"), "")
                     if str(tg.get("album") or "").strip() else "")
            parts = [lib, artist] + ([album] if album else []) + [title + ext]
            items.append({
                "src": src,
                "dst": "/".join(parts),
                "artist": artist,
                "album": album,
                "title": title,
                "ext": ext,
                "size": 0,
            })
        return {"route": self._music_import_route(items), "items": items,
                "total": len(items), "reason": ""}

    @staticmethod
    def _music_import_route(items: List[Dict[str, Any]]) -> str:
        """分流判据：``mp``（交给 MP 整理）/ ``link``（自建硬链接）/ ``skip``。

        走 MP 的条件**全部满足**才算专辑：
          * 每首的 artist / album / title 都不为空（MP 的 ``music_tags_are_usable`` 同口径）；
          * 全部曲目属于同一张专辑（专辑名只有一个）；
          * 曲目数 ≤ ``MUSIC_ALBUM_MAX_TRACKS``（24）—— 超过就是合集，MP 会逐首在线识别。
        任一条不满足就走自建：散曲、多专辑、缺标签，都别指望 MP。
        """
        if not items:
            return "skip"
        if len(items) > MUSIC_ALBUM_MAX_TRACKS:
            return "link"
        albums = {str(i.get("album") or "") for i in items}
        complete = all(str(i.get("artist") or "") and str(i.get("album") or "")
                       and str(i.get("title") or "") for i in items)
        if complete and len(albums) == 1 and "" not in albums:
            return "mp"
        return "link"

    @staticmethod
    def _music_link_one(src: str, dst: str) -> Tuple[str, str]:
        """把一个文件硬链接到目标 → ``(状态, 实际落点)``。

        状态口径：
          * ``same``    —— 目标已是同一 inode（自己链过的），幂等跳过；
          * ``created`` —— 新建链接（零额外占用，源文件 links +1）；
          * ``renamed`` —— 目标被别的内容占着 → 落到 `` (2)`` / `` (3)`` …，**不覆盖**；
          * ``exdev``   —— 跨 project 链不动（fnOS project quota），调用方须明确报出；
          * ``error``   —— 其他失败，第二项带原因。

        覆盖是绝对禁止的：源文件是种子本体，覆盖别人的文件等于毁库，而且找不回来。
        """
        try:
            src_st = os.stat(src)
        except OSError as err:
            return "error", f"源文件不可读:{err}"
        base, ext = os.path.splitext(dst)
        for idx in range(0, 10):
            target = dst if idx == 0 else f"{base} ({idx + 1}){ext}"
            try:
                tst = os.stat(target)
            except OSError:
                tst = None
            if tst is not None:
                if tst.st_dev == src_st.st_dev and tst.st_ino == src_st.st_ino:
                    return "same", target
                continue                       # 真重名（不同内容）→ 换下一个后缀
            try:
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                os.link(src, target)
                return ("created" if idx == 0 else "renamed"), target
            except OSError as err:
                if getattr(err, "errno", 0) == errno.EXDEV:
                    return "exdev", target
                return "error", f"{target}|{err}"
        return "error", f"{dst}|重名后缀已用尽"

    # ------------------------------------------------------------------ 账本
    def _music_import_records(self) -> Dict[str, Any]:
        """读入库账本（``mf_run[music_import]``）→ ``{hash: 记录}``。

        账本是真值源，不是缓存：入库是否做过、做到第几首，全看它。
        直接改库后要让账本失效得 touch ``common.py``（进程级 memo，非 TTL）。
        """
        try:
            data = slot_callbacks(self, MUSIC_IMPORT_KEY)[0]() or {}
        except Exception:  # noqa: BLE001
            data = {}
        rows = (data.get("rows") if isinstance(data, dict) else data) or {}
        if not isinstance(rows, dict):
            return {}
        return {str(k): v for k, v in rows.items() if isinstance(v, dict)}

    def _music_import_rec(self, h: str, **fields: Any) -> None:
        """落一条入库记录（按 hash 幂等覆盖；超出 ``MUSIC_IMPORT_KEEP`` 淘汰最旧）。

        整表读改写必须持锁：多颗种同时下完会并发入队，两个线程各自读到同一份旧快照
        再写回，后写的那份会把先写的整条冲掉（点播历史 19.10.72 踩过同一个坑）。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return
        try:
            with shared.lock("music_import_rec"):
                rows = self._music_import_records()
                rec = dict(rows.get(hh) or {})
                rec.update(fields)
                rec["hash"] = hh
                rec["ts"] = float(fields.get("ts") or time.time())
                rows[hh] = rec
                if len(rows) > MUSIC_IMPORT_KEEP:
                    keep = sorted(rows.values(), key=lambda r: float(r.get("ts") or 0.0))
                    rows = {str(r.get("hash")): r for r in keep[-MUSIC_IMPORT_KEEP:]}
                slot_callbacks(self, MUSIC_IMPORT_KEY)[1](
                    value={"seeded": True, "rows": rows})
                # ★ 写完**读回一次**：``sitestore.get/save`` 是**白名单路由**，未登记的槽
                #   既不抛错也不落盘（19.12.0 就漏登记了 ``SLOT_MUSIC_IMPORT`` → 账本永远空
                #   → 同一颗种每轮 Check 都被重新入队，实测堆出 33 个重复任务）。
                #   这种「静默失效」必须在第一次就喊出来，否则表现为「老是重复整理」查不到根。
                if (not getattr(self, "_music_import_slot_warned", False)
                        and hh not in self._music_import_records()):
                    self._music_import_slot_warned = True
                    self._log("音乐入库:账本写入后读不回来（槽未登记或落盘失败）—— "
                              "入库会被反复重跑，先查 sitestore 的 SLOT_MUSIC_IMPORT 登记",
                              "warning")
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐入库:账本落盘失败 {hh[:12]}: {err}", "warning")

    def _music_import_done(self, h: str) -> Optional[Dict[str, Any]]:
        """该 hash 是否已「全部入库完成」（账本 stage=done 且没有失败项）。"""
        rec = self._music_import_records().get(str(h or "").strip().lower())
        if not rec:
            return None
        if str(rec.get("stage") or "") == "done" and not int(rec.get("failed") or 0):
            return rec
        return None

    # -------------------------------------------------------------- 媒体库扫描
    def _music_scan_state(self) -> Dict[str, Any]:
        """扫描去抖状态（进程级共享槽，热重载不丢）。"""
        return shared.singleton("music_scan_state",
                                lambda: {"pending": 0.0, "last": 0.0, "hits": 0})

    def _music_scan_request(self, reason: str = "") -> None:
        """登记「有新的入库，需要扫一次库」——**只登记，不立刻扫**。

        为什么不当场扫：Navidrome 的 ``startScan`` 是**全局单例**。连续入库多颗种时
        每颗都触发一次，后一次会打断前一次，可能一直扫不完（实测扫描 2873→4000 首要几分钟）。
        所以统一走 ``_music_scan_tick``：最后一次入库后静默 ``MUSIC_SCAN_DEBOUNCE_SEC`` 再扫一次。
        """
        try:
            st = self._music_scan_state()
            st["pending"] = time.time()
            self._log(f"音乐入库:登记媒体库扫描（{reason or '入库完成'}）", "debug")
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐入库:登记扫描失败（忽略）: {err}", "warning")

    def _music_scan_tick(self) -> Dict[str, Any]:
        """到点触发一次媒体库扫描（在 Check 里每轮调，开销只有几次比较）。

        三个闸门同时满足才动手：有 pending、静默期已过、距上次请求超过冷却期。
        扫描用的是 MP 自己的媒体服务器实例（``refresh_root_library``）——
        凭据在 MP 配置里，插件不另存一份密码。

        ★ 只扫**音乐类**媒体服务器（``MUSIC_SCAN_SERVER_TYPES``）。实测这台机器上配了
        「Navidrome」(navidrome) 与「服务器1」(trimemedia 影视库) 两台，第一版没做类型过滤，
        于是每入库一次都会顺带把**影视库**整根刷一遍 —— 那是几 TB 的重扫，与音乐无关。
        """
        out: Dict[str, Any] = {"scanned": False, "reason": ""}
        try:
            st = self._music_scan_state()
            pend = float(st.get("pending") or 0.0)
            if not pend:
                out["reason"] = "无待扫请求"
                return out
            now = time.time()
            if now - pend < MUSIC_SCAN_DEBOUNCE_SEC:
                out["reason"] = "等静默期"
                return out
            if now - float(st.get("last") or 0.0) < MUSIC_SCAN_COOLDOWN_SEC:
                out["reason"] = "冷却中"
                return out
            ok = False
            try:
                from app.sdk.services import MediaServerHelper as _MSH  # noqa: WPS433
            except Exception:  # noqa: BLE001
                try:
                    from app.application.mediaserver import MediaServerHelper as _MSH  # noqa: WPS433, WPS440
                except Exception:  # noqa: BLE001
                    _MSH = None  # type: ignore[assignment]
            if _MSH is None:
                out["reason"] = "MP 媒体服务器服务不可用"
                return out
            services = _MSH().get_services() or {}
            names: List[str] = []
            skipped: List[str] = []
            for name, svc in services.items():
                stype = str(getattr(svc, "type", "") or "").strip().lower()
                if stype and stype not in MUSIC_SCAN_SERVER_TYPES:
                    # 非音乐库（影视/图库）一律不碰：刷它的整根库既慢又与音乐无关
                    skipped.append(f"{name}({stype})")
                    continue
                # 取不到 type（宿主改名/包装变化）时**放行**：宁可多刷一次，也不能让入库后
                # 静默不扫 —— 那会让「库里没有新歌」看起来像入库失败，排查方向全错。
                inst = getattr(svc, "instance", None)
                refresh = getattr(inst, "refresh_root_library", None)
                if not callable(refresh):
                    continue
                try:
                    if refresh() is not False:
                        names.append(str(name))
                        ok = True
                except Exception as err:  # noqa: BLE001
                    self._log(f"音乐入库:媒体库 {name} 扫描请求失败: {err}", "warning")
            st["pending"] = 0.0
            st["last"] = now
            st["hits"] = int(st.get("hits") or 0) + 1
            out["scanned"] = ok
            out["servers"] = names
            out["reason"] = "" if ok else "没有可刷新的媒体服务器"
            if skipped:
                out["skipped"] = skipped
            if ok:
                self._log(f"音乐入库:已请求媒体库扫描（{', '.join(names)}）"
                          f"{('；跳过非音乐库 ' + ', '.join(skipped)) if skipped else ''}")
        except Exception as err:  # noqa: BLE001
            out["reason"] = f"扫描异常:{err}"
        return out

    # ---------------------------------------------------------------- 主流程
    def _music_import_apply(self, h: str, plan: Dict[str, Any]) -> Dict[str, int]:
        """按计划执行硬链接（**每 MUSIC_IMPORT_FLUSH_EVERY 首落一次账**，可断点续）。

        断点续的意义：1258 首规模下插件中途重启/热重载会很常见；不落账就得从头再读一遍
        全部标签（那一步是整条链最慢的）。落了账，重启后账本里记着做到第几首，
        下一轮直接跳过已完成的。
        """
        rep: Dict[str, int] = {"created": 0, "same": 0, "renamed": 0,
                               "exdev": 0, "error": 0, "total": 0}
        items = list(plan.get("items") or [])
        rep["total"] = len(items)
        lib, _dl = self._music_lib_dirs()
        done_n = 0
        for it in items:
            status, _where = self._music_link_one(str(it.get("src") or ""),
                                                  str(it.get("dst") or ""))
            if status in rep:
                rep[status] = int(rep[status]) + 1
            else:
                rep["error"] = int(rep["error"]) + 1
            done_n += 1
            if done_n % MUSIC_IMPORT_FLUSH_EVERY == 0:
                self._music_import_rec(h, stage="running", lib=lib, **rep)
        return rep

    def _music_import_run(self, h: str) -> Tuple[bool, str]:
        """单颗种的完整入库（★ JobQueue 的执行体，跑在后台线程里）。

        三条出口：
          * 账本已 done → 直接返回（幂等，重复入队不会重复搬）；
          * 分流 ``mp`` → 走 MP ``manual_transfer``（要刮削与库回写）；
          * 分流 ``link`` → 自建硬链接（散曲合集走这条，秒级完成）。
        完成后**只登记**一次媒体库扫描，不在这里直接触发（去抖见 ``_music_scan_tick``）。
        """
        hh = str(h or "").strip().lower()
        try:
            idx = self._tag_all_torrents() or {}
        except Exception as err:  # noqa: BLE001
            return False, f"下载器快照不可用:{err}"
        t = None
        for k, v in idx.items():
            if str(k).strip().lower() == hh:
                t = v
                break
        if t is None:
            return False, "该种不在下载器"
        if self._music_import_done(hh):
            return True, "已入库过（账本 done），跳过"
        raw = (str(getattr(t, "content_path", "") or "").strip()
               or str(getattr(t, "save_path", "") or "").strip())
        mp_path = self._music_mp_path(raw)
        lib, _dl = self._music_lib_dirs()
        plan = self._music_import_plan(hh, t, lib)
        route = str(plan.get("route") or "skip")
        if route == "skip":
            self._music_import_rec(hh, stage="skip", reason=str(plan.get("reason") or ""))
            return False, str(plan.get("reason") or "没有可入库内容")
        title = str(getattr(t, "title", "") or getattr(t, "name", "") or "")[:80]
        # ---- 走 MP 整理（标签齐、像专辑）----
        if route == "mp":
            ok, msg = self._music_transfer_now(hh, t, mp_path)
            if ok:
                dest = self._music_transfer_dest(hh)
                self._music_mark_library(hh, dest)
                try:
                    self._music_release_done(hh)
                except Exception:  # noqa: BLE001
                    pass
                self._music_import_rec(hh, stage="done", route="mp", total=plan.get("total"),
                                       failed=0, dest=dest, msg=msg[:160])
                self._music_scan_request(f"MP 整理 {hh[:12]}")
            else:
                self._music_import_rec(hh, stage="failed", route="mp", msg=msg[:160])
            return bool(ok), (f"MP 整理「{title}」" + ("完成" if ok else f"失败：{msg[:120]}"))
        # ---- 自建硬链接（散曲 / 缺专辑标签 / 合集）----
        self._music_import_rec(hh, stage="running", route="link", total=plan.get("total"))
        rep = self._music_import_apply(hh, plan)
        bad = int(rep.get("exdev") or 0) + int(rep.get("error") or 0)
        stage = "done" if not bad else "partial"
        self._music_import_rec(hh, stage=stage, route="link", failed=bad,
                               lib=lib, **rep)
        if int(rep.get("created") or 0) or int(rep.get("renamed") or 0):
            self._music_scan_request(f"入库 {hh[:12]}")
        got = int(rep.get("created") or 0) + int(rep.get("renamed") or 0)
        msg = (f"硬链接入库「{title}」：新建 {got}"
               f"（已存在 {rep.get('same', 0)} / 重名另存 {rep.get('renamed', 0)}"
               f" / 跨盘 {rep.get('exdev', 0)} / 失败 {rep.get('error', 0)}）")
        if int(rep.get("exdev") or 0):
            msg += "；跨 project 链不动，需把库与下载区放同一 project"
        return (not bad), msg

    def _music_import_submit(self, h: str, title: str = "", reason: str = "") -> Dict[str, Any]:
        """把一颗种丢进后台队列（**提交即返回**，页面关掉也会跑完）。

        为什么必须入队：手动那次整理跑在一个前端请求里，客户端一断就中止；
        挂在刷流 Check 里则会被全局并发闸门（``GLOBAL_WORKER_LIMIT=6``）常年饿死。
        入队后这两件事都不再成立：任务跑在插件进程的后台线程，进度到「后台任务」面板看。
        """
        hh = str(h or "").strip().lower()
        try:
            return self._job_submit(
                kind="music_import",
                title=f"音乐入库「{str(title or hh[:12])[:40]}」",
                fn=(lambda _h=hh: self._music_import_run(_h)),
                dedup_key=f"music_import:{hh}",
                params={"hash": hh, "reason": str(reason or "")[:60]},
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐入库:入队失败 {hh[:12]}: {err}", "warning")
            return {}

    def _music_import_one(self, h: str, apply: bool = False) -> Dict[str, Any]:
        """单颗种的入库：干跑回计划 / 真跑入队。**AI 路由层只调这一个口**。

        收成一个口的理由：路由层（``agentapi``）不该知道「库目录怎么找、标签怎么读、
        队列怎么投」这些细节 —— 它只需要「给我这颗种的处理结果」。本方法**不抛异常**，
        所有失败都折成 ``{"ok": False, "error": "..."}``，调用方只管转信封。
        """
        hh = str(h or "").strip().lower()
        out: Dict[str, Any] = {"ok": False, "error": "", "payload": {}}
        try:
            idx = self._tag_all_torrents() or {}
        except Exception as err:  # noqa: BLE001
            out["error"] = f"下载器不可用:{err}"
            return out
        t = None
        for k, v in idx.items():
            if str(k).strip().lower() == hh:
                t = v
                break
        if t is None:
            out["error"] = "该种不在下载器"
            return out
        lib, dl = self._music_lib_dirs()
        plan = self._music_import_plan(hh, t, lib)
        items = list(plan.get("items") or [])
        payload: Dict[str, Any] = {
            "hash": hh,
            "route": str(plan.get("route") or ""),
            "total": int(plan.get("total") or 0),
            "library": lib,
            "download_dir": dl,
            "reason": str(plan.get("reason") or ""),
            # 只回前 20 条：1258 首全回会把 MCP 响应撑爆（有 30KB 截断护栏）
            "sample": [{"from": os.path.basename(str(i.get("src") or "")),
                        "to": str(i.get("dst") or "")} for i in items[:20]],
            "sample_truncated": len(items) > 20,
        }
        if apply:
            _title = str(getattr(t, "title", "") or getattr(t, "name", "") or "")
            job = self._music_import_submit(hh, _title, reason="手动")
            payload["queued"] = bool(job.get("id"))
            payload["job_id"] = job.get("id")
            payload["dedup"] = bool(job.get("dedup"))
            payload["note"] = ("已入队后台入库，可在「后台任务」看进度"
                               if job.get("id") else "入队失败（详见插件日志）")
            out["ok"] = bool(job.get("id"))
            out["error"] = "" if out["ok"] else "入队失败（详见插件日志）"
        else:
            payload["note"] = "干跑（confirm 未置 1，只回计划未入队）"
            out["ok"] = bool(plan.get("route") and plan.get("route") != "skip")
            out["error"] = str(plan.get("reason") or "没有可入库内容")
        out["payload"] = payload
        return out
