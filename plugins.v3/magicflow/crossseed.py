"""魔流 · 跨站免费取种 + 回辅目标站（3.9.0）

**玩法**：目标站 A 上「下载量大」的种子若在 A **不免费**，就别在 A 下（烧流量/拉低分享率）。
改去**任意他站**（B / C / D / E …）找**同一 Release 且免费**的副本下下来，
再把这批文件**辅种回 A** —— 对 A 来说是「零下载纯做种」，白赚 A 站上传与魔力。

**选源顺序**（同一资源多个站都有时挑一个最优的）::

    免费（硬门槛，查各站免费视图）→ 有源（列表 row 带种子数）→ PV 便宜（已在缓存里）
    → 站点可用（未被 PV 封 / cookie 有效）

**判同 Release 的硬标准**：`fingerprint()` 完整特征码（文件列表 + 根目录名）一致；
根目录名不同一律不自动辅种（在 qB 里会变成两个目录/对不上）。

**为什么不用「.torrent 里的免费标记」**：免费状态不在种子文件里，是站点侧促销；
所以必须从**站点的免费视图**（`spstate`）拿候选 —— 这同时也保证了「拿到的必是免费种」。

本模块只依赖 stdlib + `.fingerprint`，不反向依赖插件主模块（避免热重载循环导入）。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .fingerprint import fingerprint

# 下载器里给「跨站取种」打的标签（回辅完成后仍在，用于甄别与统计）
CROSSSEED_TAG = "魔流-跨站"
# 待回辅记录（PluginData 持久化；重启/重装不丢）
PENDING_KEY = "crossseed_pending"
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
    sites: Optional[List[Any]] = None,
    free_search: Callable[[Any, str], List[Any]],
    torrent_bytes: Callable[[Any, Any], Optional[bytes]],
    limit_sites: int = 6,
    log: Optional[Callable[..., Any]] = None,
) -> Optional[Dict[str, Any]]:
    """在候选站点里挑一个「免费且同一 Release」的源。

    Args:
        title: 目标站候选标题（用于站点内检索与标题比对）
        size_bytes: 目标站候选体积（字节，用于体积邻近过滤）
        fp: 目标站候选的**完整特征码**（`fingerprint(A.raw)`）
        sites: 候选站点对象列表（**已按优先级排好序**，且不含目标站自己）
        free_search: ``(site, keyword) -> List[row]``，站点免费视图检索（走 PV 闸门+缓存）
        torrent_bytes: ``(site, row) -> Optional[bytes]``，取该行 .torrent 字节（走 PV 记帐）
        limit_sites: 最多探测几个站点（PV 上限）

    Returns:
        ``{"site", "row", "torrent", "site_name", "site_domain"}`` 或 ``None``
    """
    if not fp:
        _log(log, "跨站:目标种特征码为空,放弃", "warning")
        return None
    kw = search_key(title)
    if not kw:
        _log(log, "跨站:标题无法生成检索词,放弃", "warning")
        return None
    cap = max(int(limit_sites or 0), 0)
    probed = 0
    for site in sites or []:
        if probed >= cap:
            break
        probed += 1
        sname = site_name(site)
        try:
            rows = free_search(site, kw) or []
        except Exception as err:  # noqa: BLE001
            _log(log, f"跨站:{sname} 免费检索失败:{err}", "warning")
            continue
        if not rows:
            _log(log, f"跨站:{sname} 免费视图无「{kw}」")
            continue
        tried = 0
        for row in rows[:MAX_ROWS_SCAN]:
            if not title_like(getattr(row, "title", ""), title):
                continue
            if not size_close(getattr(row, "size", 0), size_bytes):
                continue
            if tried >= MAX_TORRENT_PER_SITE:
                break
            tried += 1
            try:
                tb = torrent_bytes(site, row)
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
                _log(
                    log,
                    f"跨站:命中免费源 {sname} <{getattr(row, 'title', '')}>",
                )
                return {
                    "site": site,
                    "row": row,
                    "torrent": tb,
                    "site_name": sname,
                    "site_domain": site_domain(site),
                }
            _log(log, f"跨站:{sname} 标题相符但特征码不同(非同一 Release),跳过")
        _log(log, f"跨站:{sname} 免费列表 {len(rows)} 条,无可用同 Release")
    return None


# --------------------------------------------------------------------------- 待回辅账本

class CrossSeedPending:
    """跨站取种的「待回辅」账本。

    - **权威持久化**走 `save_data(PENDING_KEY)`（PluginData 表，随 MP 备份，重装不丢）；
    - 目标站 A 的 `.torrent` 字节**落盘**到 `<data_dir>/crossseed/<a_hash>.torrent`
      （种子文件动辄几万字节，塞进 PluginData 会把整表撑大）。
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
            _log(self._log, f"跨站:待回辅账本写入失败:{err}", "error")

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
        """清掉超时/种子文件丢失的记录，返回被清掉的 hash 列表。"""
        ts = float(now if now is not None else time.time())
        data = self.items()
        dead: List[str] = []
        for sib, rec in list(data.items()):
            try:
                created = float(rec.get("created") or 0)
            except Exception:  # noqa: BLE001
                created = 0.0
            path = str(rec.get("a_torrent") or "")
            if (created and (ts - created) > ttl) or (path and not Path(path).exists()):
                dead.append(sib)
                data.pop(sib, None)
        if dead:
            self._write(data)
        return dead

    # ---- A 的 .torrent 落盘
    def put_torrent(self, a_hash: str, raw: bytes) -> str:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / f"{str(a_hash or 'x').lower()}.torrent"
            tmp = path.with_suffix(".torrent.tmp")
            tmp.write_bytes(raw or b"")
            tmp.replace(path)
            return str(path)
        except Exception as err:  # noqa: BLE001
            _log(self._log, f"跨站:A 站种子落盘失败:{err}", "error")
            return ""

    def read_torrent(self, path: str) -> Optional[bytes]:
        try:
            return Path(path).read_bytes()
        except Exception as err:  # noqa: BLE001
            _log(self._log, f"跨站:读取 A 站种子失败 {path}:{err}", "warning")
            return None

    def cleanup_torrent(self, path: str) -> None:
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
        except Exception:  # noqa: BLE001
            pass
