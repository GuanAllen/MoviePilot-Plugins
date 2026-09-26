"""魔流元数据兜底（fallback.py）

痛点
----
MoviePilot 的刮削默认只认 TheMovieDB。中日番剧 / 国漫的**特别篇、前传、B站特供、
总集篇**在 TMDB 上常常「根本没有」（或被塞进 Season 0 的「特别篇」里），一旦离了
TMDB，库里就只剩一个认不出的文件 —— 播放器 / 飞牛影视 里显示空白或「未识别」。

做法（**只写文本，绝不动媒体文件**）
------------------------------------
1. **多源识别**：``themoviedb → bangumi → douban``（顺序可配）。依次搜索，取第一个
   能对上的来源，拿到该作品的**季 / 集分布**（``MediaInfo.seasons``）。
2. **补 NFO**：库里已整理好的集，若没有同名 ``.nfo`` → 写一个最小 ``episodedetails``
   （标题取文件名，季 / 集号照实填）；剧集目录缺 ``tvshow.nfo`` 也补一个。
   Emby / Jellyfin / Kodi / 飞牛影视 都读本地 NFO → 显示什么由我们说了算。
3. **特别篇归位（可选）**：某一集在**所有源里都不存在**（典型如「第 0 集」）→ 可将其
   改归 ``Season 0`` 的特别篇序号（S00E01…），与 TMDB / Bangumi 口径对齐。

所有写入**幂等**：已存在的 NFO 一律不覆盖；``apply=False``（演练）只报告不落盘。
本模块不删除、不移动媒体文件（``sp_to_s00`` 只在显式开启时改名，且限于库内）。
"""
import os
import re
import threading
import time
import xml.sax.saxutils as _sax
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_SOURCES = ("themoviedb", "bangumi", "douban")
SOURCE_LABELS = {
    "themoviedb": "TMDB",
    "bangumi": "Bangumi",
    "douban": "豆瓣",
    "anilist": "AniList",
    "tvdb": "TVDB",
    "imdb": "IMDb",
}

VIDEO_EXTS = {".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".flv", ".rmvb", ".iso", ".mpg", ".mpeg"}
SIDECAR_EXTS = {".ass", ".srt", ".ssa", ".sub", ".idx", ".sup", ".vtt"}

# 中文季号（用于「第N季」变体搜索）
_CN_NUM = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
    7: "七", 8: "八", 9: "九", 10: "十", 11: "十一", 12: "十二",
}

# 库根下这些目录不是「剧集」（下载区 / 刷流区 / 临时区），扫描时直接跳过
EXCLUDE_DIR_NAMES = {
    "下载", "刷流", "下载区", "临时", "临时下载", "未整理", "回收站",
    "download", "downloads", "temp", "tmp", "incomplete", "trash",
}

# 「原始发行名」目录（下载残留，不是整理后的库目录）——带清晰度/压制组/容器后缀
_RELEASE_DIR_RE = re.compile(
    r"(?i)(\b\d{3,4}p\b|\b\d{3,4}i\b|\b4k\b|web-?dl|webrip|bluray|blu-ray|remux|hdtv|"
    r"x26[45]|h\.?26[45]|hevc|avc|ddp\d?|\bdts\b|truehd|atmos|aac\d?|\bflac\b|"
    r"\bhdr\b|\bdv\b|\bcomplete\b|\brepack\b|\bproper\b|diy@|"
    r"\.torrent$|\.!qb$|\.mkv$|\.mp4$|\.ts$|\.ass$|\.srt$)"
)


def looks_like_release_dir(name: str) -> bool:
    """目录名看着像「未整理的发行目录」→ 不当作库内剧集。"""
    text = (name or "").strip()
    if not text:
        return False
    return bool(_RELEASE_DIR_RE.search(text))

_SE_RE = re.compile(r"[Ss](\d{1,3})[Ee](\d{1,4})")
_SEASON_DIR_RE = re.compile(r"^(?:season|s)\s*(\d{1,3})$", re.IGNORECASE)
_SPECIAL_DIR_RE = re.compile(r"^(?:特别篇|特典|specials?|extras?|ova|oad)$", re.IGNORECASE)
_SHOW_YEAR_RE = re.compile(r"^(?P<title>.+?)\s*[\(\[]\s*(?P<year>19\d{2}|20\d{2})\s*[\)\]]\s*$")
_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

NFO_HEAD = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'


def _norm(s: Any) -> str:
    """标题归一化（去标点 / 空格、小写），用于跨源比对。"""
    return _NORM_RE.sub("", str(s or "").lower())


def _esc(text: Any) -> str:
    """XML 文本转义（含引号），保证 NFO 始终合法。"""
    return _sax.escape(str(text or ""), {'"': "&quot;", "'": "&apos;"})


def parse_show_dirname(name: str) -> Tuple[str, str]:
    """``冬城猎凶 (2026)`` → ``("冬城猎凶", "2026")``；无年份则原样返回。"""
    raw = str(name or "").strip()
    m = _SHOW_YEAR_RE.match(raw)
    if m:
        return m.group("title").strip(), m.group("year")
    return raw, ""


def parse_season_dirname(name: str) -> Optional[int]:
    """``Season 1`` → 1；``Season 0`` / ``特别篇`` / ``Specials`` → 0；其余 → None。"""
    raw = str(name or "").strip()
    m = _SEASON_DIR_RE.match(raw)
    if m:
        return int(m.group(1))
    if _SPECIAL_DIR_RE.match(raw):
        return 0
    return None


def parse_episode(filename: str) -> Optional[Tuple[int, int]]:
    """从文件名解析 ``(season, episode)``（取最后一处 SxxExx）。"""
    hits = _SE_RE.findall(str(filename or ""))
    if not hits:
        return None
    s, e = hits[-1]
    return int(s), int(e)


def episode_title(filename: str) -> str:
    """从 ``剧名 - S01E13 - 第 13 集.mkv`` 提取「第 13 集」；提取不到返回空串。"""
    stem = Path(str(filename or "")).stem
    marker = _SE_RE.search(stem)
    if not marker:
        return ""
    tail = stem[marker.end():].strip(" -._")
    return tail


def _show_is_candidate(d: Path) -> bool:
    """判断一个目录是否像「剧集目录」：含 Season/特别篇子目录，或直接放 SxxExx 视频。"""
    try:
        children = list(d.iterdir())
    except Exception:  # noqa: BLE001
        return False
    for c in children:
        if c.is_dir():
            if parse_season_dirname(c.name) is not None:
                return True
        elif c.is_file() and c.suffix.lower() in VIDEO_EXTS and parse_episode(c.name):
            return True
    return False


class FallbackEngine:
    """多源识别 + 元数据兜底引擎（线程安全、全容错）。"""

    def __init__(self, plugin: Any, cfg: Optional[Dict[str, Any]] = None):
        self.plugin = plugin
        self.cfg = dict(cfg or {})
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
        self._last_report: Optional[Dict[str, Any]] = None
        # 游标：库很大时每轮只扫 scan_max 部，下轮从上次结束处继续（跑完一圈归零）
        self._cursor: int = 0

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(msg, level)
        except Exception:  # noqa: BLE001
            pass

    def set_cfg(self, cfg: Dict[str, Any]) -> None:
        self.cfg = dict(cfg or {})

    def sources(self) -> List[str]:
        raw = self.cfg.get("sources")
        if not isinstance(raw, (list, tuple)) or not raw:
            raw = DEFAULT_SOURCES
        out: List[str] = []
        for s in raw:
            key = str(s or "").strip().lower()
            if key and key not in out:
                out.append(key)
        return out or list(DEFAULT_SOURCES)

    def library_paths(self) -> List[str]:
        """兜底扫描的库根目录：优先设置里的显式路径，否则取 MoviePilot 目录配置。"""
        raw = self.cfg.get("paths")
        paths: List[str] = []
        if isinstance(raw, (list, tuple)):
            for p in raw:
                p = str(p or "").strip()
                if p and p not in paths:
                    paths.append(p)
        if paths:
            return paths
        try:
            from app.application.directory import DirectoryHelper  # type: ignore  # noqa: WPS433
            for d in (DirectoryHelper().get_dirs() or []):
                lp = str(getattr(d, "library_path", "") or "").strip()
                if lp and lp not in paths:
                    paths.append(lp)
        except Exception as err:  # noqa: BLE001
            self._log(f"读取 MoviePilot 媒体库目录失败（忽略）：{err}", "warning")
        return paths

    # ------------------------------------------------------------------
    # 多源识别
    # ------------------------------------------------------------------
    @staticmethod
    def _pick(results: List[Any], title: str, year: str = "", want_tv: bool = True) -> Optional[Any]:
        """从候选里挑最匹配的一条（标题完全一致 > 含年份一致 > 电视剧类型 > 第一条）。"""
        if not results:
            return None
        nt = _norm(title)
        best, best_score = None, -1
        for item in results:
            score = 0
            it = _norm(getattr(item, "title", ""))
            if it and it == nt:
                score += 4
            elif it and nt and (nt in it or it in nt):
                score += 1
            if year and str(getattr(item, "year", "") or "") == str(year):
                score += 3
            mtype = str(getattr(getattr(item, "type", None), "value", None) or getattr(item, "type", "") or "")
            if want_tv and mtype in ("电视剧", "TV", "tv"):
                score += 2
            if getattr(item, "media_id", None):
                score += 1
            seasons = getattr(item, "seasons", None) or {}
            if seasons:
                score += 1
            if score > best_score:
                best, best_score = item, score
        return best

    def _search_source(self, title: str, source: str) -> List[Any]:
        from app.schemas.types import MediaSource  # type: ignore  # noqa: WPS433
        from app.chain.media import MediaChain  # type: ignore  # noqa: WPS433
        try:
            _meta, results = MediaChain().search(title, media_source=MediaSource(source), limit=10)
        except Exception as err:  # noqa: BLE001
            self._log(f"多源识别 [{SOURCE_LABELS.get(source, source)}] 搜索失败：{err}", "warning")
            return []
        return list(results or [])

    def _detail_source(self, source: str, media_id: str, mtype: Any = None) -> Optional[Any]:
        """拉单条媒体详情——**季/集分布（``seasons``）只在详情里**，搜索结果里是空的。"""
        if not media_id:
            return None
        try:
            from app.schemas.types import MediaSource  # type: ignore  # noqa: WPS433
            from app.chain.media import MediaChain  # type: ignore  # noqa: WPS433
            return MediaChain().recognize_media(
                media_source=MediaSource(source), media_id=str(media_id),
                mtype=mtype if mtype else None,
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"多源识别 [{SOURCE_LABELS.get(source, source)}] 详情获取失败：{err}", "warning")
            return None

    def resolve(self, title: str, year: str = "") -> Optional[Dict[str, Any]]:
        """按配置顺序多源识别；返回含季 / 集分布的字典，全部失败返回 None。"""
        title = str(title or "").strip()
        if not title:
            return None
        key = f"{_norm(title)}|{year}"
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and (now - float(hit[0])) < 6 * 3600.0:
                return hit[1]
        out: Optional[Dict[str, Any]] = None
        for src in self.sources():
            item = self._pick(self._search_source(title, src), title, year)
            if not item:
                continue
            # 搜索结果只有基本信息；季/集分布要再拉一次详情
            detail = self._detail_source(src, str(getattr(item, "media_id", "") or ""), getattr(item, "type", None))
            src_item = detail if detail is not None else item
            seasons: Dict[int, Set[int]] = {}
            raw_seasons = getattr(src_item, "seasons", None) or getattr(item, "seasons", None) or {}
            try:
                for k, v in dict(raw_seasons).items():
                    try:
                        skey = int(k)
                    except (TypeError, ValueError):
                        continue
                    eps: Set[int] = set()
                    for e in (v or []):
                        try:
                            eps.add(int(e))
                        except (TypeError, ValueError):
                            continue
                    if eps:
                        seasons[skey] = eps
            except Exception:  # noqa: BLE001
                seasons = {}
            out = {
                "source": src,
                "source_label": SOURCE_LABELS.get(src, src),
                "media_id": str(getattr(src_item, "media_id", "") or getattr(item, "media_id", "") or ""),
                "title": str(getattr(src_item, "title", "") or getattr(item, "title", "") or title),
                "year": str(getattr(src_item, "year", "") or year or ""),
                "overview": str(getattr(src_item, "overview", "") or ""),
                "seasons": seasons,
            }
            break
        with self._lock:
            self._cache[key] = (now, out)
        if out is None:
            self._log(f"多源识别：『{title}』在 {len(self.sources())} 个来源里都没命中", "warning")
        return out

    def _season_entry(self, title: str, season: int) -> Tuple[Set[int], str]:
        """该季可能被拆成**独立条目**（TMDB / 豆瓣常这么干）——按「第N季」再搜一轮。

        例：库里 `时光代理人 (2021)` 里的 `S03E07`，TMDB 的 2026 条目另开一页。
        """
        base = _norm(title)
        if not base or season <= 0:
            return set(), ""
        cn = _CN_NUM.get(season)
        variants = [f"{title} Season {season}", f"{title} S{season:02d}", f"{title} {season}"]
        if cn:
            variants.insert(0, f"{title} 第{cn}季")
        for src in self.sources():
            for variant in variants:
                for item in self._search_source(variant, src):
                    iname = _norm(str(getattr(item, "title", "") or ""))
                    if not iname.startswith(base):
                        continue
                    detail = self._detail_source(
                        src, str(getattr(item, "media_id", "") or ""), getattr(item, "type", None),
                    )
                    raw = getattr(detail if detail is not None else item, "seasons", None) or {}
                    if not raw:
                        continue
                    got: Set[int] = set()
                    try:
                        keys = list(raw.keys())
                        if len(keys) == 1:
                            for e in (raw.get(keys[0]) or []):
                                try:
                                    got.add(int(e))
                                except (TypeError, ValueError):
                                    continue
                        elif season in [int(k) for k in keys if str(k).lstrip("-").isdigit()]:
                            for e in (raw.get(season) or raw.get(str(season)) or []):
                                try:
                                    got.add(int(e))
                                except (TypeError, ValueError):
                                    continue
                    except Exception:  # noqa: BLE001
                        got = set()
                    if got:
                        self._log(
                            f"多源兜底：『{title}』第 {season} 季按独立条目匹配到 {SOURCE_LABELS.get(src, src)}（{len(got)} 集）",
                            "info",
                        )
                        return got, src
        return set(), ""

    def extra_seasons(self, title: str, year: str, exclude: str = "",
                      season: Optional[int] = None) -> Dict[str, Any]:
        """主源没覆盖某集时，再用**其余来源**补一遍（结果缓存 6h）。

        返回 ``{"seasons": {季: {集}}, "source": "bangumi"}``。
        """
        key = f"x|{_norm(title)}|{year}|{exclude}|{season}"
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and (now - float(hit[0])) < 6 * 3600.0:
                return hit[1] or {"seasons": {}, "source": ""}
        merged: Dict[int, Set[int]] = {}
        hit_src = ""
        for src in self.sources():
            if src == exclude:
                continue
            item = self._pick(self._search_source(title, src), title, year)
            if not item:
                continue
            detail = self._detail_source(src, str(getattr(item, "media_id", "") or ""), getattr(item, "type", None))
            raw = getattr(detail if detail is not None else item, "seasons", None) or {}
            got = False
            try:
                for k, v in dict(raw).items():
                    try:
                        skey = int(k)
                    except (TypeError, ValueError):
                        continue
                    for e in (v or []):
                        try:
                            merged.setdefault(skey, set()).add(int(e))
                            got = True
                        except (TypeError, ValueError):
                            continue
            except Exception:  # noqa: BLE001
                continue
            if got and not hit_src:
                hit_src = src
        # 该季被拆成独立条目？
        if season is not None and season not in merged:
            got, got_src = self._season_entry(title, season)
            if got:
                merged.setdefault(int(season), set()).update(got)
                hit_src = hit_src or got_src
        out = {"seasons": merged, "source": hit_src}
        with self._lock:
            self._cache[key] = (now, out)
        return out

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    @staticmethod
    def _write_new(path: Path, text: str) -> bool:
        """**只在文件不存在时**写入（``x`` 模式），保证幂等 / 不覆盖。"""
        try:
            if path.exists():
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "x", encoding="utf-8") as fh:
                fh.write(text)
            return True
        except FileExistsError:
            return False
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _show_nfo_text(title: str, year: str = "", overview: str = "", source: str = "") -> str:
        lines = [
            NFO_HEAD,
            "<tvshow>\n",
            f"  <title>{_esc(title)}</title>\n",
        ]
        if year:
            lines.append(f"  <year>{_esc(year)}</year>\n")
            lines.append(f"  <premiered>{_esc(year)}-01-01</premiered>\n")
        if overview:
            lines.append(f"  <plot>{_esc(overview)}</plot>\n")
        lines.append("  <studio>魔流</studio>\n")
        if source:
            lines.append(f"  <tag>{_esc(source)}</tag>\n")
        lines.append("</tvshow>\n")
        return "".join(lines)

    @staticmethod
    def _episode_nfo_text(title: str, show: str, season: int, episode: int,
                          plot: str = "", source: str = "") -> str:
        lines = [
            NFO_HEAD,
            "<episodedetails>\n",
            f"  <title>{_esc(title or f'S{season:02d}E{episode:02d}')}</title>\n",
            f"  <showtitle>{_esc(show)}</showtitle>\n",
            f"  <season>{int(season)}</season>\n",
            f"  <episode>{int(episode)}</episode>\n",
        ]
        if plot:
            lines.append(f"  <plot>{_esc(plot)}</plot>\n")
        if source:
            lines.append(f"  <tag>{_esc(source)}</tag>\n")
        lines.append("  <studio>魔流</studio>\n")
        lines.append("</episodedetails>\n")
        return "".join(lines)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def _iter_season_dirs(self, show_dir: Path) -> List[Tuple[int, Path]]:
        out: List[Tuple[int, Path]] = []
        try:
            children = sorted(show_dir.iterdir())
        except Exception:  # noqa: BLE001
            return out
        for child in children:
            if not child.is_dir():
                continue
            season = parse_season_dirname(child.name)
            if season is not None:
                out.append((season, child))
        return out

    def _scan_show(self, show_dir: Path, apply: bool) -> Dict[str, Any]:
        """处理单个剧集目录；返回本目录的动作明细。"""
        result = {
            "show": show_dir.name,
            "resolved": None,
            "show_nfo": False,
            "episodes": [],
            "renumbered": [],
        }
        title, year = parse_show_dirname(show_dir.name)
        info = self.resolve(title, year)
        src_label = (info or {}).get("source_label", "")
        result["resolved"] = src_label or None
        seasons = (info or {}).get("seasons") or {}
        show_title = (info or {}).get("title") or title
        overview = (info or {}).get("overview") or ""
        # 主源没覆盖的集→再用其他源兜一次（惰性，命中才查）
        extra_checked = False
        extra: Dict[str, Any] = {"seasons": {}, "source": ""}

        # 剧集级 NFO（缺才写）
        show_nfo = show_dir / "tvshow.nfo"
        if not show_nfo.exists():
            if apply:
                ok = self._write_new(
                    show_nfo,
                    self._show_nfo_text(show_title, (info or {}).get("year") or year,
                                        overview=overview, source=src_label or "本地"),
                )
            else:
                ok = True
            if ok:
                result["show_nfo"] = True

        for season, season_dir in self._iter_season_dirs(show_dir) + [(None, show_dir)]:
            try:
                files = sorted(season_dir.iterdir())
            except Exception:  # noqa: BLE001
                continue
            for path in files:
                if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
                    continue
                se = parse_episode(path.name)
                if not se:
                    continue
                ep_season, ep_num = se
                # 目录季号优先（MP 整理后的目录比文件名更可信）
                season_num = season if season is not None else ep_season
                known = bool(seasons.get(season_num) and ep_num in seasons[season_num])
                has_data = bool(seasons)
                via = ""
                if not known:
                    # 主源没盖住→问问其他来源（同一个剧只查一次）
                    if not extra_checked and info:
                        extra_checked = True
                        extra = self.extra_seasons(
                            title, year, exclude=str((info or {}).get("source") or ""),
                            season=season_num,
                        )
                    ex_seasons = extra.get("seasons") or {}
                    if ex_seasons.get(season_num) and ep_num in ex_seasons[season_num]:
                        known = True
                        via = str(extra.get("source") or "")
                        if not has_data:
                            has_data = True
                missing_anywhere = has_data and not known and not any(
                    ep_num in (seasons.get(s) or set()) for s in seasons
                )
                ep_nfo = path.with_suffix(".nfo")
                wrote = False
                if not ep_nfo.exists():
                    plot = overview
                    if apply:
                        wrote = self._write_new(
                            ep_nfo,
                            self._episode_nfo_text(
                                episode_title(path.name), show_title, season_num, ep_num,
                                plot=plot, source=src_label or "本地",
                            ),
                        )
                    else:
                        wrote = True
                status = "known" if known else ("missing" if has_data else "nodata")
                record = {
                    "file": path.name,
                    "season": season_num,
                    "episode": ep_num,
                    "status": status,
                    "nfo": wrote,
                }
                if via:
                    record["via"] = SOURCE_LABELS.get(via, via)
                result["episodes"].append(record)

                # 可选：源里不存在的集 → 归到 Season 0 特别篇
                if (
                    bool(self.cfg.get("sp_to_s00"))
                    and missing_anywhere
                    and season_num != 0
                    and season is not None
                ):
                    moved = self._renumber_to_specials(
                        show_dir, season_dir, path, show_title, ep_num, apply=apply,
                    )
                    if moved:
                        result["renumbered"].append(record["file"])
        return result

    def _renumber_to_specials(self, show_dir: Path, season_dir: Path, path: Path,
                              show_title: str, episode: int, apply: bool) -> bool:
        """把「源里不存在」的集改名为 ``Season 0 / S00EXX``（含同名外挂字幕）。"""
        specials = show_dir / "Season 0"
        target_stem = f"{show_title} - S00E{episode:02d}"
        try:
            if apply:
                specials.mkdir(parents=True, exist_ok=True)
            stem = path.stem
            for sib in sorted(season_dir.iterdir()):
                if not sib.is_file() or not sib.name.startswith(stem):
                    continue
                suffix = sib.name[len(stem):]
                ext = sib.suffix.lower()
                if ext not in VIDEO_EXTS and ext not in SIDECAR_EXTS:
                    continue
                dest = specials / f"{target_stem}{suffix}"
                if dest.exists() or sib == path and sib.parent == specials:
                    continue
                if apply:
                    os.replace(str(sib), str(dest))
            self._log(
                f"特别篇归位：『{show_title}』第 {episode} 集（源中不存在）→ Season 0/S00E{episode:02d}"
                + ("" if apply else "（演练）")
            )
            return True
        except Exception as err:  # noqa: BLE001
            self._log(f"特别篇归位失败：{path.name}（{err}）", "warning")
            return False

    @staticmethod
    def _collect_show_dirs(root: Path) -> List[Path]:
        """从库根目录收集「剧集目录」。

        兼容两种布局：
        - ``<root>/<剧名 (年)>/Season N/``（library_path 直接就是剧集父目录）
        - ``<root>/<分类>/<剧名 (年)>/Season N/``（MoviePilot 目录配置里的 ``/movie``，
          下面还有 ``电视剧 / 电影`` 一层）
        故最多下钻两层，只把「看着像剧集目录」的收进来；电影目录没有 Season 子目录，自然跳过。
        """
        out: List[Path] = []
        try:
            level1 = sorted([p for p in root.iterdir() if p.is_dir()])
        except Exception:  # noqa: BLE001
            return out
        for child in level1:
            if child.name.startswith((".", "@")) or child.name.strip().lower() in EXCLUDE_DIR_NAMES:
                continue
            if looks_like_release_dir(child.name):
                continue
            if _show_is_candidate(child):
                out.append(child)
                continue
            try:
                level2 = sorted([p for p in child.iterdir() if p.is_dir()])
            except Exception:  # noqa: BLE001
                continue
            for sub in level2:
                if sub.name.startswith((".", "@")) or sub.name.strip().lower() in EXCLUDE_DIR_NAMES:
                    continue
                if looks_like_release_dir(sub.name):
                    continue
                if _show_is_candidate(sub):
                    out.append(sub)
        return out

    def scan(self, apply: bool = True, limit: Optional[int] = None) -> Dict[str, Any]:
        """扫描库目录做兜底。``apply=False`` 为演练（不落盘）。"""
        started = time.time()
        try:
            max_shows = int(limit if limit is not None else (self.cfg.get("scan_max") or 30))
        except (TypeError, ValueError):
            max_shows = 30
        report: Dict[str, Any] = {
            "applied": bool(apply),
            "paths": [],
            "shows": [],
            "scanned": [],
            "stats": {
                "shows": 0, "resolved": 0, "show_nfo": 0, "episodes": 0,
                "ep_nfo": 0, "missing": 0, "nodata": 0, "renumbered": 0,
                "skipped": 0, "total_shows": 0, "via_extra": 0,
            },
            "cursor": 0,
            "duration": 0.0,
        }
        for root in self.library_paths():
            root_path = Path(root)
            if not root_path.is_dir():
                continue
            report["paths"].append(root)
            entries = self._collect_show_dirs(root_path)
            total = len(entries)
            report["stats"]["total_shows"] += total
            if not total:
                continue
            with self._lock:
                start = int(self._cursor) % total
            if max_shows and total > max_shows:
                seq = [entries[(start + i) % total] for i in range(max_shows)]
                with self._lock:
                    self._cursor = (start + max_shows) % total
                report["stats"]["skipped"] += total - max_shows
            else:
                seq = entries
                with self._lock:
                    self._cursor = 0
            for show_dir in seq:
                item = self._scan_show(show_dir, apply)
                report["stats"]["shows"] += 1
                if item["resolved"]:
                    report["stats"]["resolved"] += 1
                if item["show_nfo"]:
                    report["stats"]["show_nfo"] += 1
                report["stats"]["renumbered"] += len(item["renumbered"])
                for ep in item["episodes"]:
                    report["stats"]["episodes"] += 1
                    if ep["status"] == "missing":
                        report["stats"]["missing"] += 1
                    elif ep["status"] == "nodata":
                        report["stats"]["nodata"] += 1
                    if ep["nfo"]:
                        report["stats"]["ep_nfo"] += 1
                    if ep.get("via"):
                        report["stats"]["via_extra"] += 1
                if item["show_nfo"] or any(e["nfo"] for e in item["episodes"]) or item["renumbered"]:
                    report["shows"].append(item)
                report["scanned"].append({
                    "show": item["show"],
                    "resolved": item["resolved"],
                    "episodes": len(item["episodes"]),
                    "ep_nfo": sum(1 for e in item["episodes"] if e["nfo"]),
                    "missing": sum(1 for e in item["episodes"] if e["status"] == "missing"),
                    "nodata": sum(1 for e in item["episodes"] if e["status"] == "nodata"),
                    "renumbered": len(item["renumbered"]),
                    "problems": [
                        {"season": e["season"], "episode": e["episode"], "file": e["file"], "status": e["status"]}
                        for e in item["episodes"] if e["status"] == "missing"
                    ][:20],
                })
        report["cursor"] = self._cursor
        report["duration"] = round(time.time() - started, 2)
        with self._lock:
            self._last_report = report
        try:
            self.plugin.save_data("fallback_report", report)
        except Exception:  # noqa: BLE001
            pass
        return report

    # ------------------------------------------------------------------
    # 对外
    # ------------------------------------------------------------------
    def last_report(self) -> Optional[Dict[str, Any]]:
        """最近一次扫描报告；**内存没了就从插件数据里读**（热重载不丢）。"""
        with self._lock:
            if self._last_report is not None:
                return self._last_report
        try:
            data = self.plugin.get_data("fallback_report")
            if isinstance(data, dict):
                with self._lock:
                    self._last_report = data
                return data
        except Exception:  # noqa: BLE001
            pass
        return self._last_report
