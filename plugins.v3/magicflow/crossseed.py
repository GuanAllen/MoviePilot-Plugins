"""魔流 · 跨站免费取种（3.9.0；★ 14.0.0 起「下完分诊」，回辅目标站交「全站辅种」）

**玩法**：目标站 A 上「下载量大」的种子若在 A **不免费**，就别在 A 下（烧流量/拉低分享率）。
改去**任意他站**（B / C / D / E …）找**同一 Release 且免费**的副本下下来，
再把这批文件**辅种回 A** —— 对 A 来说是「零下载纯做种」，白赚 A 站上传与魔力。

**选源**：用 **MoviePilot 自带搜索**（`SearchChain.search_by_title`）一次搜多个站 ——
返回的 `torrent_info` 天然带 `downloadvolumefactor`（免不免费）、`seeders`（有没有源）、
`freedate`（促销到期）、`enclosure`（下载链）、站点 cookie，**免不免费不用再单独查**。
调用方负责把结果过滤成「免费且在做种」的行再交进来（`rows_provider`）。

**判同 Release 的硬标准**：`fingerprint()` 完整特征码（文件列表 + 根目录名）一致；
根目录名不同一律不自动辅种（在 qB 里会变成两个目录/对不上）。

**为什么不用「.torrent 里的免费标记」**：免费状态不在种子文件里，是站点侧促销；
所以免费只能来自站点侧数据（MP 搜索的列表解析 / 免费视图 `spstate`）。

本模块只依赖 stdlib + `.fingerprint`，不反向依赖插件主模块（避免热重载循环导入）。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .fingerprint import fingerprint

# 下载器里给「跨站取种」打的标签（完成后仍在，用于甄别与统计）
CROSSSEED_TAG = "魔流-跨站"
# 取种台账（PluginData 持久化；重启/重装不丢）
PENDING_KEY = "crossseed_pending"
# ★ 来源站份(他站那份)的保护名单:H&R 保种期内任何任务不得删除/改标签
SOURCES_KEY = "crossseed_sources"
# 超时未完成的记录直接丢弃（避免无限等待）
PENDING_TTL = 24 * 3600.0
# 标题相似度门槛（特征码才是最终判据，这里只用来少取几个 .torrent）
TITLE_MIN_RATIO = 0.72
# 体积容差（同一 Release 体积必然一致，留 2% 容忍列表页四舍五入）
SIZE_TOL = 0.02
# 每个站点最多取几个 .torrent 做特征码校验
MAX_TORRENT_PER_SITE = 2
# 每个站点最多扫多少行免费列表
MAX_ROWS_SCAN = 120


def _log(log: Optional[Callable[..., Any]], msg: str, level: str = "info") -> None:
    if not log:
        return
    try:
        log(msg, level)
    except Exception:  # noqa: BLE001
        pass


def site_name(site: Any) -> str:
    return str(getattr(site, "name", "") or getattr(site, "domain", "") or site or "?")


def site_domain(site: Any) -> str:
    return str(getattr(site, "domain", "") or getattr(site, "url", "") or "").strip().lower()


# --------------------------------------------------------------------------- 标题/体积

_CN_TAG_RE = re.compile(
    r"[\[【(（][^\]】)）]{0,28}(免费|Free|FREE|free|限时|置顶|推薦|推荐|官方|首发)[^\]】)）]{0,28}[\]】)）]"
)
_LEAD_TAG_RE = re.compile(r"^\s*[\[【(（][^\]】)）]{1,28}[\]】)）]\s*")


def _core_title(text: Any) -> str:
    """规范化标题：小写、只留字母数字与 CJK（去掉分隔符/站点前缀/促销后缀）。"""
    s = str(text or "").lower()
    s = _CN_TAG_RE.sub(" ", s)
    s = _LEAD_TAG_RE.sub(" " if s.lstrip().startswith("[") else "", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)
    return s


def _bigrams(s: str) -> set:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def title_like(a: Any, b: Any, min_ratio: float = TITLE_MIN_RATIO) -> bool:
    """标题是否极可能是同一 Release（宽松判定；最终由特征码确认）。"""
    ca, cb = _core_title(a), _core_title(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    short, long_ = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    if len(short) >= 8 and short in long_:
        return True
    ba, bb = _bigrams(ca), _bigrams(cb)
    if not ba or not bb:
        return False
    inter = len(ba & bb)
    return (2.0 * inter / (len(ba) + len(bb))) >= float(min_ratio)


def size_close(x: Any, y: Any, tol: float = SIZE_TOL) -> bool:
    """体积是否一致（容差内）。任一为 0 视为「无法比较」→ True（交给特征码判）。"""
    try:
        xi, yi = float(x or 0), float(y or 0)
    except Exception:  # noqa: BLE001
        return True
    if xi <= 0 or yi <= 0:
        return True
    return abs(xi - yi) / max(xi, yi) <= max(float(tol or 0), 0.0)


def search_key(title: Any, limit: int = 36) -> str:
    """把标题裁成站点搜索关键词（去站点前缀/促销后缀，取前若干字符）。"""
    t = _CN_TAG_RE.sub(" ", str(title or ""))
    t = _LEAD_TAG_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        t = t[:limit]
    return t.strip(" .-_·")


# --------------------------------------------------------------------------- 选源

def pick_source(
    *,
    title: Any,
    size_bytes: int = 0,
    fp: Optional[str] = None,
    rows_provider: Callable[[str], List[Any]],
    torrent_bytes: Callable[[Any], Optional[bytes]],
    max_torrents: int = MAX_TORRENT_PER_SITE * 2,
    log: Optional[Callable[..., Any]] = None,
) -> Optional[Dict[str, Any]]:
    """在「跨站搜索」结果里挑一个「免费且同一 Release」的源。

    Args:
        title: 目标站候选标题（用于站点内检索与标题比对）
        size_bytes: 目标站候选体积（字节，用于体积邻近过滤）
        fp: 目标站候选的**完整特征码**（`fingerprint(A.raw)`）
        rows_provider: ``(keyword) -> List[row]``；调用方内部用 **MP 搜索**一次查多站，
            并已过滤为「免费（`downloadvolumefactor<=0`）且在做种（`seeders>=1`）」
        torrent_bytes: ``(row) -> Optional[bytes]``，取该行 .torrent 字节（走 PV 记帐）
        max_torrents: 最多取几个 .torrent 做特征码定论（PV 上限）

    Returns:
        ``{"row", "torrent", "site_name", "site_domain", "site"}`` 或 ``None``
    """
    if not fp:
        _log(log, "跨站:目标种特征码为空,放弃", "warning")
        return None
    kw = search_key(title)
    if not kw:
        _log(log, "跨站:标题无法生成检索词,放弃", "warning")
        return None
    try:
        rows = rows_provider(kw) or []
    except Exception as err:  # noqa: BLE001
        _log(log, f"跨站:跨站检索失败:{err}", "warning")
        rows = []
    if not rows:
        _log(log, f"跨站:多站搜索「{kw}」无「免费且有源」结果")
        return None
    # 体积最接近的优先试（同 Release 体积必然一致）
    try:
        rows = sorted(rows, key=lambda r: abs(float(getattr(r, "size", 0) or 0) - float(size_bytes or 0)))
    except Exception:  # noqa: BLE001
        pass
    tried = 0
    for row in rows[:MAX_ROWS_SCAN]:
        if tried >= max(int(max_torrents or 0), 1):
            break
        sname = str(getattr(row, "site_name", "") or getattr(row, "site", "") or "?")
        if not title_like(getattr(row, "title", ""), title):
            continue
        if not size_close(getattr(row, "size", 0), size_bytes):
            continue
        tried += 1
        try:
            tb = torrent_bytes(row)
        except Exception as err:  # noqa: BLE001
            _log(log, f"跨站:{sname} 取种失败:{err}", "warning")
            continue
        if not tb:
            continue
        try:
            f2 = fingerprint(tb)
        except Exception:  # noqa: BLE001
            f2 = None
        if f2 and f2 == fp:
            _log(log, f"跨站:命中免费源 {sname} <{getattr(row, 'title', '')}>")
            return {
                "site": int(getattr(row, "site", 0) or 0),
                "row": row,
                "torrent": tb,
                "site_name": sname,
                "site_domain": str(getattr(row, "site_name", "") or ""),
            }
        _log(log, f"跨站:{sname} 标题/体积相符但特征码不同(非同一 Release),跳过")
    return None


# --------------------------------------------------------------------------- 取种台账

class CrossSeedPending:
    """跨站取种的「取种台账」（★ 14.0.0 起不再回辅，仅记录在飞取种的生命周期）。

    - **权威持久化**走站点槽位（``slot_callbacks(self, "crossseed_pending")`` → ``mf_site`` 表）；
    - 每条 = 一次跨站取种（他站 B 的 sib_hash + 来源站/H&R 判定/去重基线），
      由全局真任务「跨站取种」的 Check 周期（``_crossseed_tick``）负责分诊销账。
    """

    def __init__(
        self,
        get_data: Callable[[str], Any],
        save_data: Callable[..., Any],
        dir_path: Any,
        log: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._get_data = get_data
        self._save_data = save_data
        self._log = log
        try:
            self.dir = Path(dir_path)
        except Exception:  # noqa: BLE001
            self.dir = Path(".")

    # ---- 记录
    def items(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self._get_data(PENDING_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self._save_data(PENDING_KEY, data)
        except Exception as err:  # noqa: BLE001
            _log(self._log, f"跨站:取种台账写入失败:{err}", "error")

    def add(self, rec: Dict[str, Any]) -> None:
        sib = str(rec.get("sib_hash") or "").lower()
        if not sib:
            return
        data = self.items()
        data[sib] = rec
        self._write(data)

    def drop(self, sib_hash: str) -> None:
        sib = str(sib_hash or "").lower()
        data = self.items()
        if sib in data:
            data.pop(sib, None)
            self._write(data)

    def clear(self) -> int:
        data = self.items()
        n = len(data)
        if n:
            self._write({})
        return n

    def prune(self, now: Optional[float] = None, ttl: float = PENDING_TTL) -> List[str]:
        """清掉超时记录，返回被清掉的 hash 列表。"""
        ts = float(now if now is not None else time.time())
        data = self.items()
        dead: List[str] = []
        for sib, rec in list(data.items()):
            try:
                created = float(rec.get("created") or 0)
            except Exception:  # noqa: BLE001
                created = 0.0
            if created and (ts - created) > ttl:
                dead.append(sib)
                data.pop(sib, None)
        if dead:
            self._write(data)
        return dead


class CrossSeedSources:
    """★ 来源站份（他站那份）的「H&R 保护」账本。

    他站免费下载 → 数据到手后，那份**来源种**在来源站的 H&R 保种要求还没结束
    （例：学校 BTSchool 要求挂种 10h）。它**不属于任何任务**，因此之前会被来源站
    同站纳管逻辑抢走标签、被任务清理顺手删掉（还带删文件）→ 既踩来源站 H&R，
    又可能连累目标站正在做种的同一批文件。

    这里持久化它：``{sib_hash: {title, site_b_domain, site_a, a_hash, created,
    seed_until, hours, hit_and_run, downloader, files_shared, ...}}``，
    （12.1.0 起存 ``mf_crossseed`` 表，经 ``SiteStore`` 回调读写），
    清理逻辑（``_media_asset_hashes`` 闸门同一处）会并入保护集合。
    """

    def __init__(
        self,
        get_data: Callable[[str], Any],
        save_data: Callable[..., Any],
        log: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._get_data = get_data
        self._save_data = save_data
        self._log = log

    def items(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self._get_data(SOURCES_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self._save_data(SOURCES_KEY, data)
        except Exception as err:  # noqa: BLE001
            _log(self._log, f"跨站:来源份保护账本写入失败:{err}", "error")

    def add(self, rec: Dict[str, Any]) -> None:
        sib = str(rec.get("sib_hash") or "").lower()
        if not sib:
            return
        data = self.items()
        data[sib] = rec
        self._write(data)

    def drop(self, sib_hash: str) -> None:
        sib = str(sib_hash or "").lower()
        data = self.items()
        if sib in data:
            data.pop(sib, None)
            self._write(data)

    def clear(self) -> int:
        data = self.items()
        n = len(data)
        if n:
            self._write({})
        return n

    def hashes(self) -> Set[str]:
        return set(self.items().keys())

    def put(self, sib_hash: str, patch: Dict[str, Any]) -> None:
        """局部更新一条来源份记录（不改其它字段）。"""
        sib = str(sib_hash or "").lower()
        data = self.items()
        rec = dict(data.get(sib) or {})
        rec.update(patch or {})
        data[sib] = rec
        self._write(data)

    def active(self, now: Optional[float] = None, live: bool = True) -> Set[str]:
        """**仍需要保护**的来源份 hash。

        义务已履行（实测做种时长 ≥ 要求，``done``）的条目不再保护 —— 免费做种挂够就行，
        挂着不动也是占位（Master：连挂挂满就能撤）。
        """
        out: Set[str] = set()
        for h, rec in self.items().items():
            if rec.get("done"):
                continue
            out.add(h)
        return out

    def due(self, now: Optional[float] = None) -> List[Tuple[str, Dict[str, Any]]]:
        """已过 H&R 保种期的条目（可回收）。"""
        ts = float(now if now is not None else time.time())
        out: List[Tuple[str, Dict[str, Any]]] = []
        for h, rec in self.items().items():
            try:
                until = float(rec.get("seed_until") or 0.0)
            except (TypeError, ValueError):
                until = 0.0
            if not until or ts >= until:
                out.append((h, rec))
        return out

    def prune(self, live_hashes: Optional[Set[str]] = None) -> List[str]:
        """清掉「下载器里已不存在」的条目（手动删了/被别处删了），返回被清列表。"""
        if live_hashes is None:
            return []
        data = self.items()
        dead = [h for h in list(data.keys()) if h not in live_hashes]
        for h in dead:
            data.pop(h, None)
        if dead:
            self._write(data)
        return dead
