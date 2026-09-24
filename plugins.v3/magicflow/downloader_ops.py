"""
MagicFlow 下载器操作模块

封装 qBittorrent 和 Transmission 的操作，
用于添加种子、同步做种状态、删除种子等。

复用 brushflow 的下载器逻辑，适配 MagicFlow 的魔力评分需求。
"""

import math
import logging
import threading
import time
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
_DL_GATE_MAX = 15.0
_FLOW_MARKERS = (
    "流控", "429", "too many requests", "rate limit", "ratelimit",
    "稍后重试", "请求过于频繁", "too frequent",
)


def _is_flow_control(text: Any) -> bool:
    t = str(text or "").lower()
    return any(m in t for m in _FLOW_MARKERS)


def _dl_gate() -> None:
    """全局串行限速：两次 .torrent 下载至少间隔当前动态间隔。"""
    with _DL_GATE_LOCK:
        wait = _DL_GATE_INTERVAL[0] - (time.time() - _DL_GATE_AT[0])
        if wait > 0:
            time.sleep(wait)
        _DL_GATE_AT[0] = time.time()


def _dl_note_flow_control() -> None:
    """命中流控：指数加大全局限速间隔（上限 _DL_GATE_MAX）。"""
    with _DL_GATE_LOCK:
        _DL_GATE_INTERVAL[0] = min(_DL_GATE_MAX, max(_DL_GATE_INTERVAL[0] * 2, 2.0))
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
        _ensure_sdk()

        # 0) 全局自适应限速闸门（流控时自动降速）
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
                    _dl_note_success()
                    return content if isinstance(content, bytes) else str(content).encode("utf-8")
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
        hash_string: Optional[str] = None
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
                    hash_string = next(iter(ids))
                if not ok and not hash_string:
                    return None, "qBittorrent 添加种子失败"
        except Exception as e:
            return None, f"添加种子失败: {e}"

        if not hash_string:
            hash_string = self._get_torrent_hash_by_tag(tag or "temp")
        if not hash_string:
            return None, "添加成功但未获取到 hash"

        # 重新校验：指向已有文件，若命中则瞬时 100%
        try:
            self._downloader.recheck_torrents(hash_string)
        except Exception as e:
            logger.warning(f"触发校验失败 {hash_string}: {e}")

        if verify:
            progress = self._wait_checked(hash_string, timeout=timeout)
            if progress is None:
                return hash_string, "校验状态未知（保留种子待人工确认）"
            if progress < 0.999:
                # 文件不匹配 → 撤销，避免白白下载
                try:
                    self._downloader.delete_torrents(ids=[hash_string], delete_file=False)
                except Exception:
                    pass
                return None, f"文件不匹配（校验 {progress:.1%}），已撤销"

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
            hash_string = ids[0] if ids else self._get_torrent_hash_by_tag(tag or "temp")
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
        """通过标签获取种子 hash。"""
        try:
            hash_string = self._downloader.get_torrent_id_by_tag(tags=tag)
            return hash_string
        except Exception as e:
            logger.warning(f"获取种子 hash 失败: {e}")
            return None

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

        try:
            # 优先 append 语义（qB: torrents_add_tags），避免覆盖已有标签
            if hasattr(self._downloader, "add_torrent_tag"):
                if self._downloader.add_torrent_tag(hash_string, tags):
                    return True
            if hasattr(self._downloader, "set_torrents_tag"):
                self._downloader.set_torrents_tag(ids=hash_string, tags=list(tags or []))
                return True
            return False
        except Exception as e:
            logger.error(f"设置种子标签失败: {e}")
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
