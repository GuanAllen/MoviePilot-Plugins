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

import hashlib
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..fingerprint import info_hash
from ..persistence import OperationItem
from ..tags import (MUSIC_CATEGORY, SUB_RESOURCE, STATE_MUSIC, STATE_SILENT,
                    identity_of, is_music_line, tag_for)

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
MUSIC_CAND_TTL = 30 * 60             # 候选缓存有效期（秒）：search→download 之间 AI 挑选窗口
MUSIC_CAND_MAX = 500                 # 候选缓存上限（条）

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

    # ------------------------------------------------------------ §3 搜索自描述（★ 15.9.0）

    @staticmethod
    def _music_row_from_ti(ti: Any) -> Optional[Dict[str, Any]]:
        """TorrentInfo（对象 / dict）→ 音乐候选行（只读归一，含 ``uploadvolumefactor``）。"""
        def _g(k: str, d: Any = None) -> Any:
            if isinstance(ti, dict):
                return ti.get(k, d)
            return getattr(ti, k, d)

        url = str(_g("enclosure", "") or "")
        if not url:
            return None

        def _f(k: str, d: float) -> float:
            try:
                return float(_g(k, d) or 0.0)
            except Exception:  # noqa: BLE001
                return d

        def _i(k: str, d: int = 0) -> int:
            try:
                return int(_g(k, d) or 0)
            except Exception:  # noqa: BLE001
                return d

        return {
            "title": str(_g("title", "") or ""),
            "size": _f("size", 0.0),
            "seeders": _i("seeders"),
            "site": _i("site"),
            "site_name": str(_g("site_name", "") or ""),
            "downloadvolumefactor": _f("downloadvolumefactor", 1.0),
            "uploadvolumefactor": _f("uploadvolumefactor", 1.0),
            "hit_and_run": bool(_g("hit_and_run", False)),
            "enclosure": url,
            "page_url": str(_g("page_url", "") or ""),
            "site_cookie": _g("site_cookie", None),
            "site_ua": _g("site_ua", None),
            "site_proxy": bool(_g("site_proxy", False)),
        }

    # ---------------------------------------------------------- 候选缓存（★ 15.9.0 §1）
    def _music_cand_cache(self) -> Dict[str, Any]:
        """候选缓存 ``{cid: [ts, row]}``（进程级实例属性）。

        只用于 search→download 之间存回**下载所需的凭据真值**（enclosure/cookie/ua/page_url）；
        对外候选一律不带这些（防 passkey 外泄）。reload 即清空 → AI 重搜即可。
        """
        c = getattr(self, "_music_cand_store", None)
        if not isinstance(c, dict):
            c = {}
            self._music_cand_store = c
        return c

    @staticmethod
    def _music_cid(row: Dict[str, Any]) -> str:
        key = f"{int(row.get('site') or 0)}|{str(row.get('enclosure') or '')}"
        return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:12]

    def _music_cand_put(self, cid: str, row: Dict[str, Any]) -> None:
        cache = self._music_cand_cache()
        cache[cid] = [time.time(), row]
        if len(cache) > MUSIC_CAND_MAX:
            for k in sorted(cache, key=lambda x: cache[x][0])[: len(cache) - MUSIC_CAND_MAX]:
                cache.pop(k, None)

    def _music_cand_get(self, cid: str) -> Optional[Dict[str, Any]]:
        cid = str(cid or "").strip()
        ent = self._music_cand_cache().get(cid)
        if not ent:
            return None
        if time.time() - float(ent[0]) > MUSIC_CAND_TTL:
            self._music_cand_cache().pop(cid, None)
            return None
        return ent[1]

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
            "free": _music_is_free(row.get("downloadvolumefactor")),
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
                    "free": _music_is_free(row.get("downloadvolumefactor"))}
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
        """加一颗音乐种（走现有词子：取 .torrent → 下载器加种 → H&R 开账）。

        ★ 19.9.0：加种即打「身份 ``魔流-<站>-静默-资源`` + 职务 ``魔流-<站>-音乐``」，
        并挂 ``__music__`` 伪任务（账本 ``state=音乐``）→ 下载中免疫静默池；下完由
        ``_music_untag_duty`` 摘职务、``_music_ledger_release`` 归还静默池（成为「资源」）。
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
        # ★ 19.9.0：**加种即打「身份 + 职务」两个标签**（同点播 15.8.6）——
        #   身份轴 ``静默-资源`` 永久保留；职务轴 ``音乐`` 让账本 state=音乐 ≠ 静默，
        #   下载中天然免疫静默池（不再依赖 15.8.11 的 progress<1 例外）。
        if site_name:
            tag = ", ".join([tag_for(site_name, STATE_SILENT, SUB_RESOURCE),
                             tag_for(site_name, STATE_MUSIC)])
        else:
            tag = ""
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
        # ★ 19.9.0：加种即挂 __music__ 伪任务（职务=音乐）→ 同点播语义
        try:
            self._music_assign([h], site=site_name, sub=SUB_RESOURCE, reason="加种")
        except Exception as _mae:  # noqa: BLE001
            self._log(f"音乐线:挂伪任务失败 {str(h)[:12]}: {_mae}", "warning")
        # qB「自动管理」会把任务改放到默认下载目录（/vol6/1000/movie/下载），
        # 那里属 movie project → 硬链进 /music 会被 EXDEV 拒绝；加完立刻钉到音乐目录。
        self._music_relocate(h, save_path)
        return {"ok": True, "hash": h, "tag": tag, "save_path": save_path}

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
        try:
            gid = self._tag_groups().queue_library(h, path=dest or "", media_id="")
            _state_store = self._tag_state()  # 复用
            try:
                _live = (self._tag_all_torrents() or {}).get(str(h or "").strip().lower())
            except Exception:  # noqa: BLE001
                _live = None
            # 19.9.4: 职务与身份分开写 ---- 下载中的种保留 __music__ 职务，只把身份钉成下载中
            if _live is None or float(getattr(_live, "progress", 0) or 0.0) >= 0.999:
                _state_store.release(h)
            else:
                _state_store.set_asset(h, sub=self.SUB_DOWNLOADING)
            if gid:
                self._log(f"音乐:库记 {h[:12]} → 资源 {gid[:46]} 路径 {dest or '-'}")
        except Exception as err:  # noqa: BLE001
            self._log(f"音乐:库记失败 {h[:12]}:{err}", "warning")

    def _music_relocate(self, h: str, dest: str) -> bool:
        """把种子数据搬回指定目录（qB 自动管理会把任务放到默认下载目录）。

        先关该任务的自动管理，再 ``setLocation``；搬完（qB 重新写入文件）后
        文件就落在音乐 project 里，硬链进 ``/music`` 才不会被 EXDEV 拒绝。
        """
        try:
            dl = self._get_downloader("qbittorrent")
            mod = getattr(dl, "_downloader", None)
            qbc = getattr(mod, "qbc", None)
            if qbc is None or mod is None:
                return False
            try:
                qbc.torrents_set_auto_management(hashes=h, enable=False)
            except Exception:  # noqa: BLE001
                pass
            return bool(mod.set_torrent_location(h, dest))
        except Exception:  # noqa: BLE001
            return False

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
        """★ 17.2.0 §1 音乐：下完成的专辑 → MP 整理入库（与点播同一条链）。

        - 只认**音乐线**（qB 分类 ``音乐``）且落在音乐下载目录下、``progress >= 0.999`` 的种；
        - 只结算 3 天内下完的种（历史手工硬链专辑不能再搬一次）；
        - **直调** ``TransferChain().manual_transfer``（``mtype=MUSIC, music_type=album``）：
          不打 MP 的 ``TORRENT_TAG``、不写 downloadhistory ⇒ MP 定时整理任务扫不到这些种，
          不会与它并发；成功后补库记（``TransferComplete`` 事件偶发收不到时兜底）。
        - 已有成功整理记录的直接 skipped + 补库记；失败只计数，下轮重试。
        """
        rep: Dict[str, int] = {"scanned": 0, "pending": 0, "settled": 0,
                               "skipped": 0, "failed": 0, "written": 0,
                               "relocated": 0, "reloc_skip": 0}
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
                if done >= cap:
                    continue
                done += 1
                mp_path = self._music_mp_path(raw)
                if not mp_path:
                    rep["failed"] += 1
                    continue
                ok, msg = self._music_transfer_now(key, t, mp_path)
                if ok:
                    rep["settled"] += 1
                    # ★ 19.9.3：直调整理耗时数十秒，期间可能又有分片/新轨在下载 →
                    #   mark_library 内部会重读 qB 进度决定写「资源」还是「下载中」。
                    self._music_mark_library(key, self._music_transfer_dest(key))
                    # 19.9.4: 下完即摘音乐职务（点播同构）---- 清单此时才算已完成
                    try:
                        self._music_release_done(key)
                    except Exception:  # noqa: BLE001
                        pass
                    self._log(f"音乐:整理入库 {key[:12]} 「{getattr(t, 'title', '')}」"
                              f"→ 完成{('（' + msg[:40] + '）') if msg else ''}".rstrip())
                else:
                    rep["failed"] += 1
                    self._log(f"音乐:整理入库失败 {key[:12]}: {msg[:160]}", "warning")
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"音乐:整理入库异常 {str(h)[:12]}: {err}", "warning")
        return rep

    # ---------------------------------------------------------- §1 音乐清单（★ 15.9.0）

    _MUSIC_ACTS = ("pause", "resume", "remove")

    @staticmethod
    def _music_hist_title(title: str) -> str:
        """历史行展示名：把 journal 里的「音乐 xxx」前缀去掉。"""
        t = str(title or "").strip()
        if t.startswith("音乐"):
            t = t[len("音乐"):].strip()
        return t

    @staticmethod
    def _m_iso(ts: Any) -> Optional[str]:
        """裸 epoch 秒 → ISO8601（带本地时区）；缺/非法/``<=0`` → ``None``。"""
        try:
            v = float(ts or 0.0)
        except (TypeError, ValueError):
            return None
        if v <= 0.0:
            return None
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None

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
            title = self._music_hist_title(str(getattr(op, "title", "") or ""))
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
            "free": _music_is_free(getattr(t, "downloadvolumefactor", None) if t is not None else None),
            "hit_and_run": bool(getattr(t, "hit_and_run", False)) if t is not None else bool((rec or {}).get("hit_and_run")),
            "in_qb": t is not None,
            "in_library": bool((rec or {}).get("in_library")),
            "save_path": str(getattr(t, "save_path", "") or "") if t is not None else "",
            "added_at": self._m_iso(base_ts),
            "settled_at": self._m_iso((rec or {}).get("identity_at")),
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
            title = self._music_hist_title(str(getattr(op, "title", "") or ""))
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
            "free": _music_is_free(getattr(t, "downloadvolumefactor", None) if t is not None else None),
            "hit_and_run": (bool(getattr(t, "hit_and_run", False)) if t is not None
                            else bool((rec or {}).get("hit_and_run"))),
            "in_qb": False,
            "in_library": inlib,
            "save_path": "",
            "added_at": self._m_iso(base_ts),
            "settled_at": self._m_iso((rec or {}).get("identity_at")),
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
        totals = {
            "count": len(rows),
            "downloading": sum(1 for r in rows if r.get("stage") == "downloading"),
            "settling": sum(1 for r in rows if r.get("stage") == "settling"),
            "resource": sum(1 for r in rows if r.get("stage") == "resource"),
            "gone": sum(1 for r in rows if r.get("stage") == "gone"),
            "left_gb": round(sum(float(r.get("left_gb") or 0.0) for r in rows), 3),
        }
        return {"items": rows, "totals": totals}

    def _music_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """音乐行内操作：``pause`` / ``resume`` / ``remove``（音乐线仅限 qB 分类=音乐的种）。

        回执统一 ``{ok, hash, action, message, blocked}``；``remove`` 走唯一删除闸门（不绕）。
        """
        h = str(hash or "").strip().lower()
        act = str(action or "").strip().lower()

        def _rep(ok: bool, msg: str, *, blocked: bool = False) -> Dict[str, Any]:
            return {"ok": bool(ok), "hash": h, "action": act,
                    "message": str(msg or ""), "blocked": bool(blocked)}

        if not h:
            return _rep(False, "缺少 hash")
        if act not in self._MUSIC_ACTS:
            return _rep(False, f"未知操作:{action}")
        try:
            snap = {str(k).lower(): v for k, v in (self._tag_all_torrents() or {}).items()}
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"下载器不可用:{e}")
        t = snap.get(h)
        if t is None:
            return _rep(False, "该种不在下载器（音乐清单只操作在库种）")
        if not self._is_music_line(t):
            return _rep(False, "该种不属于音乐线（拒绝操作）")
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"下载器不可用:{e}")
        if dl is None or not getattr(dl, "is_available", False):
            return _rep(False, "下载器不可用")
        if act in ("pause", "resume"):
            try:
                n, err = (dl.pause_torrents([h]) if act == "pause" else dl.resume_torrents([h]))
            except Exception as e:  # noqa: BLE001
                return _rep(False, f"{act} 失败:{e}")
            if err or not n:
                return _rep(False, f"{act} 失败:{err or '未命中'}")
            return _rep(True, "已暂停" if act == "pause" else "已继续")
        try:
            n, err = dl.delete_torrents(hashes=[h], delete_file=True,
                                        reason="音乐移除", source="music")
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"移除失败:{e}")
        if not n:
            return _rep(False, err or "被删除闸门拦下（欠 H&R / 受保护），未移除", blocked=True)
        self._log(f"音乐:{h[:12]} 已移除（删种+删文件）")
        return _rep(True, "已移除（删种+删文件）")
