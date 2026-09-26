"""
MagicFlow 下载器操作模块

封装 qBittorrent 和 Transmission 的操作，
用于添加种子、同步做种状态、删除种子等。

复用 brushflow 的下载器逻辑，适配 MagicFlow 的魔力评分需求。
"""

import math
import base64
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .fingerprint import Entry, entries_fingerprint, info_hash, load_torrent_entries

# 运行时导入（在 MoviePilot 环境才导入）
logger = logging.getLogger("magicflow")
DownloaderHelper = None


class TorrentFetchFlowControl(RuntimeError):
    """站点对 .torrent 下载接口触发流控（429 / 限速）。

    属**可重试的临时错误**：调用方应本轮跳过、下轮再试，且**不要**把它记入
    dead（否则会因临时限流把候选冷却数小时）。
    """


# ---------------------------------------------------------------------------
# 自适应下载限速闸门
#   - 所有 .torrent 下载（含 SDK 路径与回落路径）都先过 _dl_gate()，保证全局
#     两次下载至少间隔 _DL_GATE_INTERVAL 秒；
#   - 命中流控 → 间隔指数加大（上限 _DL_GATE_MAX），成功则缓慢回落到基准；
#   - 这样对 hdfans 这类宽松站点几乎无感，对 PT时间 这类强流控站点自动降速。
# ---------------------------------------------------------------------------
_DL_GATE_LOCK = threading.Lock()
_DL_GATE_AT = [0.0]
_DL_GATE_INTERVAL = [1.0]
_DL_GATE_BASE = 1.0
_DL_GATE_MAX = 30.0

# .torrent 字节缓存：以 enclosure URL 为键（passkey/uid 通常稳定 → 同一种子 URL 不变）。
# 命中即免网络、**免限速闸门**。目的：稳定种子池下「分类取种」每轮会重复下载同一批
# .torrent（每轮 ~N 次，各自至少受 1s 闸门约束），正是「任务卡在分类排序」的主因；
# 缓存后重复轮近乎零耗时。注意：只在真正发起外网请求前过闸门，缓存命中直接返回。
_TORRENT_BYTES_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_TORRENT_BYTES_CACHE_MAX = 300
_TORRENT_BYTES_LOCK = threading.Lock()


def _torrent_cache_get(url: str) -> Optional[bytes]:
    """读取缓存的 .torrent 字节（命中则移到队尾，LRU）。"""
    if not url:
        return None
    with _TORRENT_BYTES_LOCK:
        v = _TORRENT_BYTES_CACHE.get(url)
        if v is not None:
            _TORRENT_BYTES_CACHE.move_to_end(url)
        return v


def _torrent_cache_put(url: str, content: Any) -> None:
    """写入 .torrent 字节缓存（LRU 淘汰）。"""
    if not url or not content:
        return
    try:
        data = content if isinstance(content, bytes) else bytes(content)
    except Exception:
        return
    if not data:
        return
    with _TORRENT_BYTES_LOCK:
        _TORRENT_BYTES_CACHE[url] = data
        _TORRENT_BYTES_CACHE.move_to_end(url)
        while len(_TORRENT_BYTES_CACHE) > _TORRENT_BYTES_CACHE_MAX:
            _TORRENT_BYTES_CACHE.popitem(last=False)
_FLOW_MARKERS = (
    "流控", "429", "too many requests", "rate limit", "ratelimit",
    "稍后重试", "请求过于频繁", "too frequent",
)


def _is_flow_control(text: Any) -> bool:
    t = str(text or "").lower()
    return any(m in t for m in _FLOW_MARKERS)


def _looks_like_torrent(data: Any) -> bool:
    """粗略校验是否为有效 .torrent（bencode dict 且含 info 段）。

    站点流控/未登录时可能返回 200 + HTML 提示页；这类内容喂给下载器会表现为
    「添加种子失败」。这里提前识别，避免把垃圾字节当成种子。
    """
    if not data:
        return False
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    if not isinstance(data, (bytes, bytearray)):
        return False
    raw = bytes(data)
    if raw.lstrip()[:1] != b"d":
        return False
    return b"4:info" in raw[:65536]


def _dl_gate() -> None:
    """全局串行限速：两次 .torrent 下载至少间隔当前动态间隔。"""
    with _DL_GATE_LOCK:
        wait = _DL_GATE_INTERVAL[0] - (time.time() - _DL_GATE_AT[0])
        if wait > 0:
            time.sleep(wait)
        _DL_GATE_AT[0] = time.time()


def set_dl_gate_base(seconds: float) -> None:
    """由插件全局设置「请求间隔」驱动的基准间隔（秒）。

    站点请求间隔（request_interval）此前只作用于浏览列表翻页，并不影响 .torrent
    下载；而 PT时间 这类站点的流控恰好打在下种接口上。这里把同一设置下推到下载
    闸门：设置越大 → 两次下种的最小间隔越大 → 越不容易被流控。传 0 恢复基准 1s。
    """
    global _DL_GATE_BASE
    try:
        v = max(0.0, float(seconds or 0))
    except (TypeError, ValueError):
        v = 0.0
    with _DL_GATE_LOCK:
        _DL_GATE_BASE = max(1.0, v)
        if _DL_GATE_INTERVAL[0] < _DL_GATE_BASE:
            _DL_GATE_INTERVAL[0] = _DL_GATE_BASE


def _dl_note_flow_control() -> None:
    """命中流控：指数加大全局限速间隔（上限 _DL_GATE_MAX）。"""
    with _DL_GATE_LOCK:
        _DL_GATE_INTERVAL[0] = min(_DL_GATE_MAX, max(_DL_GATE_INTERVAL[0] * 2, _DL_GATE_BASE))
        logger.warning(f"MagicFlow：.torrent 下载命中站点流控，限速间隔调整为 {_DL_GATE_INTERVAL[0]:.1f}s")


def _dl_note_success() -> None:
    """成功一次：限速间隔缓慢回落（避免长期停留在高位）。"""
    with _DL_GATE_LOCK:
        if _DL_GATE_INTERVAL[0] > _DL_GATE_BASE:
            _DL_GATE_INTERVAL[0] = max(_DL_GATE_BASE, round(_DL_GATE_INTERVAL[0] * 0.7, 2))


def _retry_after(response: Any) -> Optional[float]:
    """读取 429/503 响应的 Retry-After 头（秒）。"""
    try:
        headers = getattr(response, "headers", None)
        raw = headers.get("Retry-After") if headers is not None else None
        return float(raw) if raw else None
    except Exception:
        return None


def _kv(obj: Any, key: str, default: Any = None) -> Any:
    """同时兼容 dict 与对象属性两种取值方式（qb 返回 TorrentDictionary）。"""
    if obj is None:
        return default
    try:
        if isinstance(obj, dict):
            return obj.get(key, default)
    except Exception:
        pass
    return getattr(obj, key, default)


def _split_tags(raw: Any) -> List[str]:
    """把 qB 的逗号分隔标签串 / 列表统一规整为去空白的字符串列表。"""
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    try:
        return [str(x).strip() for x in (raw or []) if str(x).strip()]
    except Exception:
        return []


def _magnet_infohash(magnet: Any) -> Optional[str]:
    """从磁力链解析 btih（v1 infohash，小写 40 位 hex）。"""
    try:
        m = re.search(r"xt=urn:btih:([A-Za-z0-9]+)", str(magnet or ""))
        if not m:
            return None
        raw = m.group(1)
        if len(raw) == 40:
            return raw.lower()
        if len(raw) == 32:  # base32
            return base64.b32decode(raw.upper()).hex()
    except Exception:
        return None
    return None


# qBittorrent 原始状态字符串（低层客户端不归一，直接用 qb 自身取值）
# 「做种中」只含**真正在向 tracker 汇报/上传**的状态；pausedUP/pausedDL 是
# 用户（或插件）明确停下的种子，tracker 不再计入做种，故归入 QB_PAUSED_STATES。
QB_SEEDING_STATES = {
    "uploading", "stalledup", "forcedup", "queuedup", "checkingup",
    "allocating",
}
QB_DOWNLOADING_STATES = {
    "downloading", "metadl", "forceddl", "stalleddl", "queueddl",
    "checkingdl", "checkingresumedata",
}
QB_PAUSED_STATES = {"pausedup", "pauseddl"}

# 「没进度」状态：元数据/下载停滞、出错、文件丢失——这类种子长期占位却不产出魔力
QB_DEAD_STATES = {
    "stalleddl", "metadl", "error", "missingfiles", "unknown",
}

# qBittorrent 应用级偏好里本插件读写的键
#   速度类（dl_limit / up_limit）单位为**字节/秒**，0 = 不限。
QB_APP_PREF_KEYS = (
    "dl_limit",
    "up_limit",
    "max_connec",
    "max_connec_per_torrent",
    "max_uploads",
    "max_uploads_per_torrent",
    "max_active_downloads",
    "max_active_torrents",
    "max_active_uploads",
    "queueing_enabled",
    "save_path",
    "temp_path",
    "temp_path_enabled",
)


def _ensure_sdk():
    """延迟导入 MoviePilot SDK。"""
    global logger, DownloaderHelper
    if DownloaderHelper is None:
        try:
            from app.sdk.logging import logger as _logger
            from app.sdk.services import DownloaderHelper as _dh
            logger = _logger
            DownloaderHelper = _dh
        except ImportError:
            # 独立测试环境
            logger = logging.getLogger("magicflow")
            class FakeDownloaderHelper:
                @staticmethod
                def get_service(name=None):
                    return None
            DownloaderHelper = FakeDownloaderHelper


# ============================================================
# 数据模型
# ============================================================

@dataclass
class TorrentInfo:
    """下载器中的种子信息。"""
    # 无默认值的字段（必需）
    hash: str
    title: str
    size: float              # 大小（字节）
    state: str               # 状态

    # 有默认值的字段
    size_gb: float = 0.0
    seeder: int = 0
    leecher: int = 0
    seed_time: float = 0.0
    seed_time_hours: float = 0.0
    seed_time_weeks: float = 0.0
    ratio: float = 0.0
    uploaded: float = 0.0      # 已上传字节
    upload_speed: float = 0.0
    download_speed: float = 0.0
    category: str = ""
    tags: List[str] = field(default_factory=list)
    save_path: str = ""
    progress: float = 0.0        # 下载进度 0~1
    downloaded: float = 0.0      # 已下载字节
    added_on: float = 0.0        # 加入下载器的时间戳（秒）
    content_path: str = ""
    is_zero_bonus: bool = False
    is_free: bool = False
    is_double_free: bool = False
    hit_and_run: bool = False
    tracker: str = ""
    volume_factor: float = 1.0

    def __post_init__(self):
        # 计算派生字段（仅当值为0/空时计算）
        if self.size <= 0 and self.size_gb <= 0:
            self.size_gb = 0.0
        elif not self.size_gb:
            self.size_gb = self.size / (1024 ** 3)

        if self.seed_time > 0 and self.seed_time_hours <= 0:
            self.seed_time_hours = self.seed_time / 3600

        if self.seed_time_hours > 0 and self.seed_time_weeks <= 0:
            self.seed_time_weeks = self.seed_time_hours / (7 * 24)

    @property
    def age_weeks(self) -> float:
        """生存周数（等同于做种时间）。"""
        return self.seed_time_weeks or (self.seed_time / 3600 / (7 * 24) if self.seed_time else 0.0)


@dataclass
class DownloaderResult:
    """下载器操作结果。"""
    success: bool
    message: str
    data: Optional[Any] = None


# ============================================================
# 下载器适配器
# ============================================================

class DownloaderAdapter:
    """
    下载器统一适配器。

    封装 qBittorrent 和 Transmission 的差异。
    """

    def __init__(self, downloader_name: str = "qbittorrent"):
        """
        初始化下载器适配器。

        Args:
            downloader_name: 下载器名称 ("qbittorrent" | "transmission")
        """
        self.downloader_name = downloader_name
        self._downloader = None
        self._service = None
        self._init_downloader()

    def _init_downloader(self) -> None:
        """初始化下载器实例。"""
        _ensure_sdk()

        try:
            downloader_helper = DownloaderHelper()
            self._service = downloader_helper.get_service(name=self.downloader_name)
            if self._service and self._service.instance:
                self._downloader = self._service.instance
                logger.info(f"下载器适配器初始化成功: {self.downloader_name}")
            else:
                logger.warning(f"下载器 {self.downloader_name} 不可用")
        except Exception as e:
            logger.error(f"下载器适配器初始化失败: {e}")
            self._downloader = None

    @property
    def is_available(self) -> bool:
        """检查下载器是否可用。"""
        return self._downloader is not None

    def get_torrents(
        self,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[TorrentInfo], Optional[str]]:
        """
        获取种子列表。

        Args:
            tags: 标签过滤（可选）
            status: 状态过滤（可选，"seeding" | "downloading" | "paused"）

        Returns:
            (种子列表, 错误信息)
        """
        if not self._downloader:
            return [], "下载器不可用"

        try:
            torrents, error = self._downloader.get_torrents()
            if error:
                return [], error

            result = []
            for torrent in torrents:
                # 标签过滤
                if tags:
                    torrent_tags = getattr(torrent, "tags", []) or []
                    if isinstance(torrent_tags, str):
                        torrent_tags = [t.strip() for t in torrent_tags.split(",")]
                    if not any(tag in torrent_tags for tag in tags):
                        continue

                # 状态过滤（qb 原始状态：uploading / stalledUP / pausedUP ...）
                if status:
                    torrent_state = str(_kv(torrent, "state", "") or "").strip().lower()
                    if status == "seeding":
                        if torrent_state not in QB_SEEDING_STATES:
                            continue
                    elif status == "downloading":
                        if torrent_state not in QB_DOWNLOADING_STATES:
                            continue
                    elif status == "paused":
                        if torrent_state not in QB_PAUSED_STATES:
                            continue

                # 转换为 TorrentInfo
                info = self._parse_torrent_info(torrent)
                result.append(info)

            return result, None

        except Exception as e:
            logger.error(f"获取种子列表失败: {e}")
            return [], str(e)

    def get_seeding_torrents(
        self,
        tag: Optional[str] = None,
    ) -> Tuple[List[TorrentInfo], Optional[str]]:
        """
        获取做种中的种子列表。

        Args:
            tag: 标签过滤

        Returns:
            (做种列表, 错误信息)
        """
        tags = [tag] if tag else None
        return self.get_torrents(tags=tags, status="seeding")

    # ---------------------------------------------------------
    # 存量复用（辅种）支持
    # ---------------------------------------------------------

    def get_raw_torrents(self) -> List[Any]:
        """获取下载器中**全部**种子（不限标签）。"""
        if not self._downloader:
            return []
        try:
            torrents, error = self._downloader.get_torrents()
            if error:
                return []
            return list(torrents or [])
        except Exception as e:
            logger.error(f"获取全部种子失败: {e}")
            return []

    def get_all_torrents_index(self) -> Dict[str, TorrentInfo]:
        """全部种子索引：hash(小写) -> TorrentInfo（不限标签，用于复用判定）。"""
        index: Dict[str, TorrentInfo] = {}
        for torrent in self.get_raw_torrents():
            try:
                info = self._parse_torrent_info(torrent)
            except Exception:
                continue
            if info.hash:
                index[info.hash.lower()] = info
        return index

    def get_torrents_by_tag(self) -> Tuple[Dict[str, List[TorrentInfo]], Optional[str]]:
        """**一次**拉取全部种子，按标签分组返回：tag -> [TorrentInfo]。

        性能：qBittorrent 的 ``torrents_info()``（无 tag 过滤）会一次返回**全部**种子，
        再由客户端过滤标签。旧做法是「每个任务各调一次 get_torrents(tags=[tag])」→
        N 个任务 = N 次全量拉取（N×数百条），是 /status 冷启动 2~3s 的主因。
        这里一次拉取 + 内存分组，让总览/做种明细等共用同一份数据。
        """
        groups: Dict[str, List[TorrentInfo]] = {}
        raw = self.get_raw_torrents()
        for torrent in raw:
            try:
                info = self._parse_torrent_info(torrent)
            except Exception:
                continue
            for tag in (getattr(info, "tags", None) or []):
                tg = str(tag).strip()
                if tg:
                    groups.setdefault(tg, []).append(info)
        return groups, None

    def get_file_entries(self, hash_string: str) -> List[Entry]:
        """获取指定种子的文件列表 [(相对路径, 大小)]。"""
        if not self._downloader or not hash_string:
            return []
        try:
            files = self._downloader.get_files(hash_string)
        except Exception as e:
            logger.debug(f"获取种子文件列表失败 {hash_string}: {e}")
            return []
        entries: List[Entry] = []
        for item in files or []:
            name = _kv(item, "name", "")
            size = _kv(item, "size", 0)
            if name:
                entries.append((str(name), int(size or 0)))
        return entries

    def get_torrent_fingerprint(self, hash_string: str) -> Optional[str]:
        """由下载器中种子的文件列表计算特征码。"""
        entries = self.get_file_entries(hash_string)
        return entries_fingerprint(entries) if entries else None

    def fetch_torrent_bytes(
        self,
        url: str,
        cookie: Optional[str] = None,
        user_agent: Optional[str] = None,
        proxies: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> Optional[bytes]:
        """下载 .torrent 原始字节（用于计算特征码 / 辅种）。

        优先走宿主 SDK 自带的 ``TorrentHelper.download_torrent``：它像 MoviePilot
        本体一样**手动跟 301/302 链（重发请求带上 cookie/UA/referer）**，并处理
        NexusPHP「首次下载提示页」；裸 RequestUtils 对这类站点（如 PT时间）会拿到
        301/中间页 → 非 200 → 拿不到种子。失败再回落到裸 RequestUtils。
        """
        if not url:
            return None
        # 0) 本地字节缓存命中：免网络、**免限速闸门**（同一 URL 在稳定种子池下重复轮近乎零耗时）
        _cached = _torrent_cache_get(url)
        if _cached is not None:
            return _cached
        _ensure_sdk()

        # 1) 全局自适应限速闸门（流控时自动降速）
        _dl_gate()

        # 1) 宿主 SDK 的种子下载（与本体一致，处理 301 链 + 首次下载页）
        try:
            from app.application.torrent.download import TorrentHelper  # noqa: WPS433
        except Exception:
            TorrentHelper = None  # type: ignore
        if TorrentHelper is not None:
            try:
                _path, content, _folder, _files, err = TorrentHelper().download_torrent(
                    url=url,
                    cookie=cookie,
                    ua=user_agent,
                    referer=referer,
                    proxy=False,
                    cache_invalid=False,
                )
                if content:
                    _bytes = content if isinstance(content, bytes) else str(content).encode("utf-8")
                    if not _looks_like_torrent(_bytes):
                        # 拿到 200 但不是有效种子（多半是站点流控/登录提示页）
                        logger.warning(f"TorrentHelper 返回内容非有效种子（疑似流控）{url}")
                        _dl_note_flow_control()
                        raise TorrentFetchFlowControl("返回内容非有效种子（疑似站点流控/登录页）")
                    _dl_note_success()
                    _torrent_cache_put(url, _bytes)
                    return _bytes
                if err:
                    logger.warning(f"TorrentHelper 下载种子未成功 {url}: {err}")
                    if _is_flow_control(err):
                        # 站点流控：回落路径打的是同一站点，重试只会加剧限流，
                        # 记一笔流控（抬高全局间隔）后直接抛出，交由调用方本轮跳过。
                        _dl_note_flow_control()
                        raise TorrentFetchFlowControl(str(err))
            except TorrentFetchFlowControl:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(f"TorrentHelper 下载种子异常 {url}: {e}")

        # 2) 回落：裸 RequestUtils（带 http→https 与 429 退避重试）
        try:
            from app.sdk.network import RequestUtils

            _req = RequestUtils(cookies=cookie, proxies=proxies, ua=user_agent, referer=referer)

            def _get(u: str):
                try:
                    _dl_gate()
                    return _req.get_res(url=u)
                except Exception:
                    return None

            response = _get(url)
            ok = bool(response and response.ok)
            if not ok and str(url).lower().startswith("http://"):
                response = _get("https://" + url.split("://", 1)[1])
                ok = bool(response and response.ok)
            for _wait in (2.0, 4.0, 8.0):
                if ok:
                    break
                if getattr(response, "status_code", None) not in (429, 503):
                    break
                _dl_note_flow_control()
                time.sleep(_retry_after(response) or _wait)
                response = _get(url)
                ok = bool(response and response.ok)
            if not ok:
                _status = getattr(response, "status_code", None)
                logger.warning(f"下载种子文件非成功 {_status or '?'} {url}")
                if _status in (429, 503):
                    _dl_note_flow_control()
                    raise TorrentFetchFlowControl(f"HTTP {_status}")
                return None
            _dl_note_success()
            if not _looks_like_torrent(response.content):
                _dl_note_flow_control()
                raise TorrentFetchFlowControl("返回内容非有效种子（疑似站点流控/登录页）")
            _torrent_cache_put(url, response.content)
            return response.content
        except ImportError:
            return None
        except TorrentFetchFlowControl:
            raise
        except Exception as e:
            logger.warning(f"下载种子文件失败 {url}: {e}")
            return None

    def _find_raw_torrent(self, hash_string: str) -> Optional[Any]:
        try:
            torrents, error = self._downloader.get_torrents(ids=[hash_string])
            if not error and torrents:
                return torrents[0]
        except Exception:
            pass
        return None

    def _wait_checked(self, hash_string: str, timeout: int = 120) -> Optional[float]:
        """等待校验结束，返回进度（0~1）。超时返回 None。"""
        deadline = time.time() + max(timeout, 5)
        pending = {"checkingdl", "checkingup", "checkingresume", "moving", "allocating", "metadl"}
        progress = None
        while time.time() < deadline:
            raw = self._find_raw_torrent(hash_string)
            if raw is None:
                time.sleep(2)
                continue
            state = str(_kv(raw, "state", "") or "").lower()
            progress = float(_kv(raw, "progress", 0) or 0)
            if state not in pending and not state.startswith("checking"):
                return progress
            time.sleep(2)
        return progress

    def add_torrent_reuse(
        self,
        torrent_bytes: bytes,
        save_path: str,
        tag: Optional[str] = None,
        cookie: Optional[str] = None,
        verify: bool = True,
        timeout: int = 120,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        辅种：把候选种子指向本机已有文件添加做种。

        流程：以**暂停**方式添加（不下载）→ recheck → 校验通过后开始做种；
        校验不通过（文件对不上）则**撤销**该种子（未下载任何数据）。

        Returns:
            (种子 hash, 错误信息)
        """
        if not self._downloader:
            return None, "下载器不可用"
        if not torrent_bytes:
            return None, "种子内容为空"

        tag_list = [tag] if tag else []

        # 添加前记录该标签下的 hash，用于可靠定位「刚添加的这颗」（不靠猜）
        before_hashes: set = set()
        if tag:
            try:
                _b, _ = self._downloader.get_torrents(tags=tag)
                before_hashes = {str(t.get("hash", "")).lower() for t in (_b or [])}
            except Exception:
                before_hashes = set()

        # 兜底 hash：本地直接算 infohash（不依赖下载器回查，也绝不触发标签删除）
        local_hash: Optional[str] = None
        try:
            local_hash = str(info_hash(torrent_bytes)).lower()
        except Exception:
            local_hash = None

        hash_string: Optional[str] = None
        # 🔎 标签审计：辅种复用添加种子
        logger.info(f"[标签审计] ADD-REUSE dir={save_path or '-'} tags={tag_list} paused=True")
        try:
            result = self._downloader.add_torrent(
                content=torrent_bytes,
                download_dir=save_path or "",
                is_paused=True,
                tag=tag_list,
                category="",
                ignore_category_check=True,
            )
            # 兼容 (bool, [ids]) 与 bool 两种返回
            if isinstance(result, tuple) and len(result) == 2:
                ok, ids = result
                if ids:
                    hash_string = str(next(iter(ids))).lower()
                if not ok and not hash_string and not local_hash:
                    return None, "qBittorrent 添加种子失败"
        except Exception as e:
            return None, f"添加种子失败: {e}"

        if not hash_string:
            hash_string = local_hash
        if not hash_string and tag:
            # 最后兜底：取该标签下「添加前不存在」的种子（最新的那颗）
            try:
                _a, _ = self._downloader.get_torrents(tags=tag)
                new = [t for t in (_a or [])
                       if str(t.get("hash", "")).lower() not in before_hashes]
                if new:
                    new.sort(key=lambda t: t.get("added_on") or 0)
                    hash_string = str(new[-1].get("hash", "")).lower()
            except Exception:
                hash_string = None
        if not hash_string:
            # 定位不到新种子 → 不冒险操作别的种，直接放弃本次辅种
            return None, "添加成功但未能定位新种子 hash（已放弃辅种）"

        def _delete_added(reason: str) -> str:
            """撤销刚添加的辅种种（不删文件），并复核确已删除。"""
            for _try in range(2):
                try:
                    self._downloader.delete_torrents(ids=[hash_string], delete_file=False)
                except Exception as e:
                    logger.warning(f"撤销辅种删除失败 {hash_string}: {e}")
                try:
                    _chk, _ = self._downloader.get_torrents(ids=hash_string)
                    if not _chk:
                        return reason
                except Exception:
                    return reason
                time.sleep(1.5)
            logger.warning(f"撤销辅种后种子仍存在（需人工清理）: {hash_string}")
            return reason

        # 重新校验：指向已有文件，若命中则瞬时 100%
        try:
            self._downloader.recheck_torrents(hash_string)
        except Exception as e:
            logger.warning(f"触发校验失败 {hash_string}: {e}")

        if verify:
            progress = self._wait_checked(hash_string, timeout=timeout)
            if progress is None:
                # 校验超时/无法确认 → 撤销，避免留下「暂停·0%」僵尸种
                return None, _delete_added("校验超时/未知，已撤销（避免残留）")
            if progress < 0.999:
                # 文件不匹配 → 撤销，避免白白下载
                return None, _delete_added(f"文件不匹配（校验 {progress:.1%}），已撤销")

        # 开始做种
        try:
            self._downloader.start_torrents(hash_string)
        except Exception as e:
            logger.warning(f"启动做种失败 {hash_string}: {e}")
        return hash_string, None

    def get_torrent_info(self, hash_string: str) -> Optional[TorrentInfo]:
        """
        获取指定种子的详细信息。

        Args:
            hash_string: 种子 hash

        Returns:
            种子信息或 None
        """
        if not self._downloader:
            return None

        try:
            torrent = self._downloader.get_torrent(hash_string)
            if not torrent:
                return None
            return self._parse_torrent_info(torrent)
        except Exception as e:
            logger.error(f"获取种子信息失败: {e}")
            return None

    def _parse_torrent_info(self, torrent: Any) -> TorrentInfo:
        """
        解析种子信息为 TorrentInfo。

        兼容 qBittorrent 和 Transmission 的字段差异。
        """
        # 通用字段提取
        hash_string = _kv(torrent, "hash", "") or _kv(torrent, "hash_string", "")
        title = _kv(torrent, "name", "") or _kv(torrent, "title", "")
        size = float(_kv(torrent, "size", 0) or 0)
        state = _kv(torrent, "state", "")
        seeder = int(_kv(torrent, "seeder", 0) or _kv(torrent, "num_seeds", 0) or 0)
        leecher = int(_kv(torrent, "leecher", 0) or _kv(torrent, "num_leechers", 0) or 0)
        seed_time = float(_kv(torrent, "seeding_time", 0) or _kv(torrent, "seed_time", 0) or 0)
        ratio = float(_kv(torrent, "ratio", 0) or 0)
        uploaded = float(_kv(torrent, "uploaded", 0) or _kv(torrent, "uploadedEver", 0) or 0)
        # 注意：qBittorrent 原始字段是 upspeed/dlspeed（字节/秒），
        # 旧代码只读 up_speed/dl_speed → qB 下恒为 0（慢速清理因此拿不到速度）。
        upload_speed = float(_kv(torrent, "up_speed", 0) or _kv(torrent, "upspeed", 0) or 0)
        download_speed = float(_kv(torrent, "dl_speed", 0) or _kv(torrent, "dlspeed", 0) or 0)
        category = _kv(torrent, "category", "") or ""
        save_path = _kv(torrent, "save_path", "") or ""
        # 进度与加入时间（qb: progress 0~1 / added_on；tr: percent_done / added_date）
        progress_raw = _kv(torrent, "progress", None)
        if progress_raw is None:
            progress_raw = _kv(torrent, "percent_done", 0) or 0
        try:
            progress = float(progress_raw or 0)
        except (TypeError, ValueError):
            progress = 0.0
        try:
            downloaded = float(_kv(torrent, "downloaded", 0) or 0)
        except (TypeError, ValueError):
            downloaded = 0.0
        added_on_raw = _kv(torrent, "added_on", None)
        if added_on_raw is None:
            added_on_raw = _kv(torrent, "added_date", 0)
        try:
            added_on = float(added_on_raw or 0)
        except (TypeError, ValueError):
            added_on = 0.0

        # 标签（qB 可能是字符串或列表，Tr 可能是列表）
        tags_raw = _kv(torrent, "tags", []) or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = list(tags_raw)

        # 零魔/免费检测（通过标签或站点信息）
        is_zero_bonus = False
        is_free = False
        is_double_free = False

        # 检查标签
        for tag in tags:
            tag_lower = tag.lower()
            if "零魔" in tag or "zerobonus" in tag_lower:
                is_zero_bonus = True
            if "免费" in tag or "free" in tag_lower:
                is_free = True
            if "双倍" in tag or "2xfree" in tag_lower:
                is_double_free = True

        # 体积因子
        volume_factor = 1.0
        if is_double_free:
            volume_factor = 0.5
        elif is_free:
            volume_factor = 0.5

        return TorrentInfo(
            hash=hash_string,
            title=title,
            size=size,
            state=state,
            size_gb=size / (1024 ** 3) if size else 0.0,
            seeder=seeder,
            leecher=leecher,
            seed_time=seed_time,
            seed_time_hours=seed_time / 3600 if seed_time else 0.0,
            seed_time_weeks=seed_time / 3600 / (7 * 24) if seed_time else 0.0,
            ratio=ratio,
            uploaded=uploaded,
            upload_speed=upload_speed,
            download_speed=download_speed,
            category=category,
            tags=tags,
            save_path=save_path,
            progress=progress,
            downloaded=downloaded,
            added_on=added_on,
            is_zero_bonus=is_zero_bonus,
            is_free=is_free,
            is_double_free=is_double_free,
            volume_factor=volume_factor,
        )

    def add_torrent(
        self,
        content: Union[str, bytes],
        download_dir: str = "",
        tag: Optional[str] = None,
        category: str = "",
        upload_limit: Optional[int] = None,
        download_limit: Optional[int] = None,
        cookie: Optional[str] = None,
        user_agent: Optional[str] = None,
        proxies: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        添加种子到下载器。

        Args:
            content: 种子内容（URL、磁力链或种子文件字节）
            download_dir: 下载目录
            tag: 标签
            category: 分类（qB 专用）
            upload_limit: 上传限速（KB/s）
            download_limit: 下载限速（KB/s）
            cookie: 站点 Cookie
            user_agent: User-Agent
            proxies: 代理

        Returns:
            (种子 hash, 错误信息)
        """
        if not self._downloader:
            return None, "下载器不可用"

        try:
            if self.downloader_name == "qbittorrent":
                return self._add_torrent_qbittorrent(
                    content=content,
                    download_dir=download_dir,
                    tag=tag,
                    category=category,
                    upload_limit=upload_limit,
                    download_limit=download_limit,
                    cookie=cookie,
                    user_agent=user_agent,
                    proxies=proxies,
                )
            elif self.downloader_name == "transmission":
                return self._add_torrent_transmission(
                    content=content,
                    download_dir=download_dir,
                    labels=[tag] if tag else None,
                    upload_limit=upload_limit,
                    download_limit=download_limit,
                    cookie=cookie,
                    user_agent=user_agent,
                    proxies=proxies,
                )
            else:
                return None, f"不支持的下载器: {self.downloader_name}"

        except Exception as e:
            logger.error(f"添加种子失败: {e}")
            return None, str(e)

    def _add_torrent_qbittorrent(
        self,
        content: Union[str, bytes],
        download_dir: str,
        tag: Optional[str],
        category: str,
        upload_limit: Optional[int],
        download_limit: Optional[int],
        cookie: Optional[str],
        user_agent: Optional[str],
        proxies: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """添加种子到 qBittorrent。"""
        # 处理磁力链
        if isinstance(content, str) and content.startswith("magnet:"):
            tag_list = [tag] if tag else []
            result = self._downloader.add_torrent(
                content=content,
                download_dir=download_dir,
                category=category,
                tag=tag_list,
                upload_limit=upload_limit,
                download_limit=download_limit,
            )
            ok, ids = self._normalize_add_result(result)
            if not ok:
                return None, "qBittorrent 添加种子失败"
            hash_string = str(ids[0]).lower() if ids else _magnet_infohash(content)
            if not hash_string:
                hash_string = self._get_torrent_hash_by_tag(tag or "temp")
            return hash_string, None

        # 处理 URL 或种子文件
        if isinstance(content, str) and not content.startswith("magnet"):
            # 下载种子文件
            _ensure_sdk()
            try:
                from app.sdk.network import RequestUtils

                response = RequestUtils(
                    cookies=cookie,
                    proxies=proxies,
                    ua=user_agent,
                ).get_res(url=content, raise_exception=True)

                if not response or not response.ok:
                    return None, f"下载种子文件失败: {response.status_code if response else '无响应'}"

                content = response.content
            except ImportError:
                return None, "下载种子文件需要 MoviePilot 环境"
            except Exception as e:
                return None, f"下载种子文件失败: {e}"

        # 添加种子
        tag_list = [tag] if tag else []
        # 🔎 标签审计：添加种子时带的标签只作用于该种子，不会删除标签定义。
        logger.info(f"[标签审计] ADD dir={download_dir or '-'} tags={tag_list}")
        result = self._downloader.add_torrent(
            content=content,
            download_dir=download_dir,
            category=category,
            tag=tag_list,
            upload_limit=upload_limit,
            download_limit=download_limit,
            cookie=cookie,
        )

        ok, ids = self._normalize_add_result(result)
        if not ok:
            return None, "qBittorrent 添加种子失败"

        # 获取 hash：优先用客户端返回的种子 ID，其次由种子内容直接算 infohash，最后回退按标签查
        hash_string = ids[0] if ids else None
        if not hash_string and isinstance(content, bytes):
            try:
                hash_string = info_hash(content)
            except Exception:
                hash_string = None
        if not hash_string:
            hash_string = self._get_torrent_hash_by_tag(tag or "temp")
        return hash_string, None

    @staticmethod
    def _normalize_add_result(result: Any) -> Tuple[bool, List[str]]:
        """把下载器 add_torrent 的返回值统一规整为 (是否成功, 种子ID列表)。"""
        if isinstance(result, tuple):
            ok = bool(result[0]) if len(result) > 0 else False
            raw_ids = result[1] if len(result) > 1 else []
            ids = [str(i) for i in raw_ids if i] if isinstance(raw_ids, (list, tuple)) else []
            return ok, ids
        return bool(result), []

    def _get_torrent_hash_by_tag(self, tag: str) -> Optional[str]:
        """按标签读取种子 hash（**只读**，绝不删除标签）。

        ⚠️ 严禁使用 MoviePilot 的 ``get_torrent_id_by_tag()``：它会把手里的 tag
        当作“临时标签”，查完就调用 ``delete_torrents_tag()`` 把它**全局删除**。
        魔流过去把任务的正式标签（brush_tag，如「魔流-聆音刷流」）传了进去，
        于是每加一次种子就把该标签从下载器里抹掉 —— 所有托管种子瞬间掉标签，
        工作台表现为“托管 0 个 / 任务被清空”。这里改为只读查询：列出带该标签
        的种子，取最新加入的一个。
        """
        if not self._downloader or not tag:
            return None
        # 🔎 标签审计：确认走的是“只读”路径（绝不调用 MoviePilot 的 get_torrent_id_by_tag）。
        logger.info(f"[标签审计] LOOKUP(read-only) tag={tag}")
        try:
            torrents, _err = self._downloader.get_torrents(tags=[tag])
        except Exception:
            torrents = None
        if not torrents:
            try:
                all_t, _err = self._downloader.get_torrents()
                torrents = [t for t in (all_t or []) if tag in _split_tags(_kv(t, "tags", ""))]
            except Exception:
                torrents = []
        if not torrents:
            return None

        def _added_on(t: Any) -> float:
            try:
                return float(_kv(t, "added_on", 0) or _kv(t, "added_date", 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        try:
            torrents = sorted(torrents, key=_added_on, reverse=True)
        except Exception:
            pass
        h = str(
            _kv(torrents[0], "hash", "") or _kv(torrents[0], "hash_string", "") or ""
        ).strip().lower()
        return h or None

    def _add_torrent_transmission(
        self,
        content: Union[str, bytes],
        download_dir: str,
        labels: Optional[List[str]],
        upload_limit: Optional[int],
        download_limit: Optional[int],
        cookie: Optional[str],
        user_agent: Optional[str],
        proxies: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """添加种子到 Transmission。"""
        # 处理磁力链
        if isinstance(content, str) and content.startswith("magnet:"):
            result = self._downloader.add_torrent(
                content=content,
                download_dir=download_dir,
                labels=labels,
            )
            if result:
                return result.hashString, None
            return None, "Transmission 添加种子失败"

        # 处理 URL 或种子文件
        if isinstance(content, str) and not content.startswith("magnet"):
            _ensure_sdk()
            try:
                from app.sdk.network import RequestUtils

                response = RequestUtils(
                    cookies=cookie,
                    proxies=proxies,
                    ua=user_agent,
                ).get_res(url=content, raise_exception=True)

                if not response or not response.ok:
                    return None, f"下载种子文件失败: {response.status_code if response else '无响应'}"

                content = response.content
            except ImportError:
                return None, "下载种子文件需要 MoviePilot 环境"
            except Exception as e:
                return None, f"下载种子文件失败: {e}"

        # 添加种子
        result = self._downloader.add_torrent(
            content=content,
            download_dir=download_dir,
            labels=labels,
        )

        if not result:
            return None, "Transmission 添加种子失败"

        # 设置限速
        if upload_limit or download_limit:
            self._downloader.change_torrent(
                hash_string=result.hashString,
                upload_limit=upload_limit,
                download_limit=download_limit,
            )

        return result.hashString, None

    def delete_torrents(
        self,
        hashes: List[str],
        delete_file: bool = False,
    ) -> Tuple[int, Optional[str]]:
        """
        删除种子。

        Args:
            hashes: 种子 hash 列表
            delete_file: 是否删除文件

        Returns:
            (成功删除数量, 错误信息)
        """
        if not self._downloader:
            return 0, "下载器不可用"

        if not hashes:
            return 0, None

        # ★ 删种前先向 tracker 报到一次：站点更快把状态从「下载中/做种中」更新为已停止，
        #   对症「站点一直显示下载中」。尽力而为，失败仅记日志、不阻断删除。
        try:
            _rn, _rn_err = self.reannounce(hashes)
            if _rn:
                logger.info(f"[报到] 删除前已重新报到 {_rn} 个种子")
        except Exception as _rn_exc:  # noqa: BLE001
            logger.debug(f"删除前重新报到异常（忽略）: {_rn_exc}")

        try:
            success_count = 0
            for hash_string in hashes:
                if self._downloader.delete_torrents(ids=[hash_string], delete_file=delete_file):
                    success_count += 1

            if success_count < len(hashes):
                return success_count, f"部分种子删除失败 ({success_count}/{len(hashes)})"

            return success_count, None

        except Exception as e:
            logger.error(f"删除种子失败: {e}")
            return 0, str(e)

    def reannounce(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """向 tracker 重新报到（尽力而为，失败不阻断）。

        主要用于删种前报到一次，让站点更快更新状态。

        Returns:
            (成功数量, 错误信息)
        """
        hashes = [h for h in (hashes or []) if h]
        if not hashes:
            return 0, None
        try:
            client = self._qb_client()
            if client is not None:
                client.torrents_reannounce(torrent_hashes=hashes)
                return len(hashes), None
            func = getattr(self._downloader, "reannounce_torrents", None)
            if func:
                func(hashes)
                return len(hashes), None
            return 0, "下载器不支持重新报到"
        except Exception as e:  # noqa: BLE001
            return 0, str(e)

    def set_torrent_tags(
        self,
        hash_string: str,
        tags: List[str],
    ) -> bool:
        """
        设置种子标签。

        Args:
            hash_string: 种子 hash
            tags: 标签列表

        Returns:
            是否成功
        """
        if not self._downloader or not hash_string:
            return False

        # 🔎 标签审计：任何对种子的标签写操作都留痕，方便日后定位“掉标签/被清空”。
        logger.info(
            f"[标签审计] SET hash={hash_string} tags={list(tags or [])} "
            f"（本次只影响该种子，不删除标签定义）"
        )
        try:
            # 优先 append 语义（qB: torrents_add_tags），避免覆盖已有标签
            if hasattr(self._downloader, "add_torrent_tag"):
                if self._downloader.add_torrent_tag(hash_string, tags):
                    logger.info(f"[标签审计] SET-OK(append) hash={hash_string}")
                    return True
            if hasattr(self._downloader, "set_torrents_tag"):
                logger.info(f"[标签审计] SET-FALLBACK(replace) hash={hash_string} tags={list(tags or [])}")
                self._downloader.set_torrents_tag(ids=hash_string, tags=list(tags or []))
                return True
            logger.warning(f"[标签审计] SET-FAIL 下载器不支持标签操作 hash={hash_string}")
            return False
        except Exception as e:
            logger.error(f"[标签审计] SET-ERR hash={hash_string}: {e}")
            return False

    def resume_torrent(self, hash_string: str) -> bool:
        """恢复/启动一个种子（暂停或错误状态 -> 开始做种）。"""
        if not self._downloader or not hash_string:
            return False
        try:
            self._downloader.start_torrents(hash_string)
            return True
        except Exception as e:
            logger.warning(f"恢复种子失败 {hash_string}: {e}")
            return False

    def _control_torrents(
        self,
        hashes: List[str],
        action: str,
    ) -> Tuple[int, Optional[str]]:
        """批量控制种子（pause / resume / recheck）。

        Args:
            hashes: 种子 hash 列表
            action: pause（暂停）/ resume（恢复做种）/ recheck（强制校验）

        Returns:
            (成功数量, 错误信息)
        """
        if not self._downloader:
            return 0, "下载器不可用"
        hashes = [h for h in (hashes or []) if h]
        if not hashes:
            return 0, None
        method = {
            "pause": "stop_torrents",
            "resume": "start_torrents",
            "recheck": "recheck_torrents",
        }.get(action)
        func = getattr(self._downloader, method or "", None)
        if not func:
            return 0, f"下载器不支持该操作（{method}）"
        success = 0
        for hash_string in hashes:
            try:
                if func(hash_string) is not False:
                    success += 1
            except Exception as e:
                logger.warning(f"种子操作 {action} 失败 {hash_string}: {e}")
        if success < len(hashes):
            return success, f"部分种子操作失败 ({success}/{len(hashes)})"
        return success, None

    def pause_torrents(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """暂停种子（停止做种/下载）。"""
        return self._control_torrents(hashes, "pause")

    def resume_torrents(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """恢复做种（暂停 -> 开始）。"""
        return self._control_torrents(hashes, "resume")

    def recheck_torrents(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """强制重新校验。"""
        return self._control_torrents(hashes, "recheck")

    def get_downloader_info(self) -> Dict[str, Any]:
        """获取下载器信息。"""
        if not self._service:
            return {"available": False}

        return {
            "available": True,
            "name": self.downloader_name,
            "display_name": self._service.display_name if self._service else "",
            "config_name": self._service.name if self._service else "",
        }

    # ---------------------------------------------------------------
    # qBittorrent 应用级偏好（全局参数，影响所有用该下载器的插件）
    # ---------------------------------------------------------------

    def _qb_client(self) -> Any:
        """返回底层 qbittorrentapi.Client（仅 qBittorrent 且已登录时可用）。"""
        if self.downloader_name != "qbittorrent" or not self._downloader:
            return None
        return getattr(self._downloader, "qbc", None)

    def get_app_preferences(self) -> Tuple[Dict[str, Any], Optional[str]]:
        """读取 qBittorrent 应用级偏好（本插件关心的子集）。

        Returns:
            (偏好字典, 错误信息)。速度类字段返回**字节/秒**原值。
        """
        qbc = self._qb_client()
        if qbc is None:
            return {}, f"下载器 {self.downloader_name} 不支持读取全局参数"
        try:
            prefs = qbc.app_preferences()
            data = {}
            for key in QB_APP_PREF_KEYS:
                try:
                    data[key] = prefs.get(key)
                except Exception:
                    data[key] = None
            return data, None
        except Exception as e:
            logger.error(f"读取 qBittorrent 全局参数失败: {e}")
            return {}, str(e)

    def set_app_preferences(self, prefs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """写入 qBittorrent 应用级偏好（仅传入的键会生效）。

        Args:
            prefs: 偏好字典（速度类字段为**字节/秒**）。

        Returns:
            (是否成功, 错误信息)
        """
        qbc = self._qb_client()
        if qbc is None:
            return False, f"下载器 {self.downloader_name} 不支持写入全局参数"
        payload = {k: v for k, v in (prefs or {}).items() if k in QB_APP_PREF_KEYS}
        if not payload:
            return False, "无可写入的参数"
        try:
            qbc.app_set_preferences(payload)
            return True, None
        except Exception as e:
            logger.error(f"写入 qBittorrent 全局参数失败: {e}")
            return False, str(e)


# ============================================================
# 便捷函数
# ============================================================

def get_downloader_adapter(name: str = "qbittorrent") -> DownloaderAdapter:
    """
    获取下载器适配器。

    Args:
        name: 下载器名称

    Returns:
        DownloaderAdapter 实例
    """
    return DownloaderAdapter(downloader_name=name)


def sync_task_torrents(
    downloader_name: str,
    tag: str,
) -> Tuple[List[TorrentInfo], Optional[str]]:
    """
    同步任务的做种种子列表。

    Args:
        downloader_name: 下载器名称
        tag: 任务标签

    Returns:
        (做种列表, 错误信息)
    """
    adapter = DownloaderAdapter(downloader_name=downloader_name)
    return adapter.get_seeding_torrents(tag=tag)


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MagicFlow 下载器操作模块测试")
    print("=" * 60)

    # 测试下载器适配器初始化（不依赖真实下载器）
    print("\n1. 测试下载器适配器初始化：")
    adapter = DownloaderAdapter("qbittorrent")
    info = adapter.get_downloader_info()
    print(f"   下载器信息: {info}")

    # 测试解析（模拟数据）
    print("\n2. 测试种子信息解析：")

    class MockTorrent:
        hash = "abc123def456"
        name = "test.torrent"
        size = 5 * 1024 * 1024 * 1024  # 5GB
        state = "seeding"
        seeder = 10
        leecher = 2
        seeding_time = 3 * 24 * 3600  # 3天
        ratio = 1.5
        up_speed = 1024 * 1024  # 1MB/s
        dl_speed = 0
        category = "movie"
        tags = "刷流,免费"
        save_path = "/downloads/test"

    mock = MockTorrent()
    info = adapter._parse_torrent_info(mock)
    print(f"   Hash: {info.hash}")
    print(f"   标题: {info.title}")
    print(f"   大小: {info.size_gb:.2f} GB")
    print(f"   做种人数: {info.seeder}")
    print(f"   做种时间: {info.seed_time_weeks:.2f} 周")
    print(f"   魔力产出: {info.age_weeks:.2f} 周")
    print(f"   分享率: {info.ratio}")
    print(f"   零魔: {info.is_zero_bonus}")
    print(f"   免费: {info.is_free}")
    print(f"   体积因子: {info.volume_factor}")

    # 测试 TorrentInfo dataclass
    print("\n3. 测试 TorrentInfo dataclass：")
    t = TorrentInfo(
        hash="test123",
        title="Test Torrent",
        size=10 * 1024**3,
        state="seeding",
        seeder=5,
        leecher=1,
        seed_time=7 * 24 * 3600,
    )
    print(f"   size_gb: {t.size_gb:.2f}")
    print(f"   seed_time_hours: {t.seed_time_hours:.2f}")
    print(f"   seed_time_weeks: {t.seed_time_weeks:.2f}")
    print(f"   age_weeks: {t.age_weeks:.2f}")

    print("\n" + "=" * 60)
    print("测试完成（下载器连接测试需要真实环境）")
    print("=" * 60)
