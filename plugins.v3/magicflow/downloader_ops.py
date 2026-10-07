"""
MagicFlow 下载器操作模块

封装 qBittorrent 和 Transmission 的操作，
用于添加种子、同步做种状态、删除种子等。

复用 brushflow 的下载器逻辑，适配 MagicFlow 的魔力评分需求。
"""

import base64
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .fingerprint import Entry, entries_fingerprint, info_hash
from .qbsync import QB_SYNC_INCREMENTAL, get_qb_sync_store

# ★ 辅种/复用标记（与 tags.MARK_REUSE 保持一致；此模块不反向依赖 tags，避免循环导入）
REUSE_MARK = "魔流-辅种"

# 运行时导入（在 MoviePilot 环境才导入）
logger = logging.getLogger("magicflow")
DownloaderHelper = None

# hash -> (ts, domain)；空 tracker 种的归属兜底缓存（announce 域名几乎不变）
# ★ 15.3.1：缓存本身挂到 persistence._shared() 进程级单例上（热重载不丢），兜底用模块级 dict。
_TRACKER_DOMAIN_KEY = "tracker_domain_cache"
_TRACKER_DOMAIN_CACHE: Dict[str, Tuple[float, str]] = {}
_TRACKER_DOMAIN_TTL = 1800.0
_TRACKER_DOMAIN_MAX = 4000  # 软上限：超过就淘汰最旧的一半（防跨重载长期膨胀）


def _tracker_domain_cache() -> Dict[str, Tuple[float, str]]:
    """取/建「hash → (ts, domain)」缓存（跨热重载共享的进程级单例）。

    模块级 dict 会在插件热重载时被清空 → 冷启动要对每个种子逐 hash 调
    ``torrents_trackers``（~1368 次 ≈ 27s）。挂到 ``persistence._shared().singletons``
    后重载不丢；**纯内存**（不写 Redis、不落盘）。取不到共享容器时退化为模块级。
    """
    try:
        from .persistence import _shared  # noqa: PLC0415
        sh = _shared()
        with sh.lock:
            cache = sh.singletons.get(_TRACKER_DOMAIN_KEY)
            if not isinstance(cache, dict):
                cache = {}
                sh.singletons[_TRACKER_DOMAIN_KEY] = cache
        return cache
    except Exception:  # noqa: BLE001
        return _TRACKER_DOMAIN_CACHE


def _tracker_domain_store(cache: Dict[str, Tuple[float, str]], h: str, ts: float, host: str) -> None:
    """写缓存 + 软上限淘汰（超 _TRACKER_DOMAIN_MAX 丢最旧的一半）。"""
    try:
        if len(cache) >= _TRACKER_DOMAIN_MAX and h not in cache:
            for k in sorted(cache, key=lambda k: cache[k][0])[: len(cache) // 2]:
                cache.pop(k, None)
        cache[h] = (ts, host)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# ★ 删除闸门安装器 / fail-closed 策略（Master 2026-10-05「删除令出一门」补洞）
#   - set_gate_installer(fn)：注册「适配器一构造就自动挂闸门」的进程级安装器。
#     ``DownloaderAdapter.__init__`` 末尾会调用它 → **裸构造**（不经 _get_downloader 的
#     ``DownloaderAdapter(...)``）也会自动带上 gate/deletion_log，消除「类属性 _global_gate
#     至少要设过一次」的顺序依赖（热重载后类属性归零 → 裸构造先跑 → 删种无闸门）。
#   - set_gate_fail_closed(flag)：运行时切换「闸门缺失/异常时是否阻断删除」。
#     默认 True（安全）：拿不到硬保护判定就宁可不删；False=旧行为（fail-open 放行）。
# ---------------------------------------------------------------------------
_INSTALL = None                 # 安装器：fn(adapter) -> None；None = 未注册（安全默认由 installer 兜底）
_GATE_FAIL_CLOSED = True        # ★ 安全默认：与 common.DELETE_GATE_FAIL_CLOSED 对齐

# ★ 10.2.0 下载即开账（影子记账）：添加成功后回调的 H&R 开账钩子。
#   签名：fn(hash_string, site_domain, tag, content, hit_and_run)；异常必须被吞掉、绝不影响添加。
#   11.7.0：新增第 5 参 ``hit_and_run``（逐种 H&R 标记，qB 侧无此信息，只能下载瞬间带入）。
_HR_OPEN = None


def set_hr_open_hook(fn) -> None:
    """注册「下载即开账」钩子：``fn(hash_string, site_domain, tag, content, hit_and_run)``。

    在 ``add_torrent`` **成功后**被调用（异常吞掉 + 记 error，绝不影响添加）。传 ``None`` 注销。
    """
    global _HR_OPEN
    _HR_OPEN = fn


def set_gate_installer(fn) -> None:
    """注册删除闸门安装器：``fn(adapter)`` 在每个 DownloaderAdapter 构造末尾被调用。

    ``fn`` 应给适配器挂上 ``gate``（硬保护判定）与 ``deletion_log``（统一台账），并同步类属性
    ``_global_gate`` / ``_global_dlog``（向后兼容）。传 ``None`` 可注销。
    """
    global _INSTALL
    _INSTALL = fn


def set_gate_fail_closed(flag: bool) -> None:
    """设置删除闸门「失败即封」策略（True=安全默认；False=回退旧 fail-open 行为）。"""
    global _GATE_FAIL_CLOSED
    _GATE_FAIL_CLOSED = bool(flag)


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


# ---------------------------------------------------------------- 换票地址解析
# 部分站点（馒头 / HDH / 肉丝 / 红叶 / 时光 … 这类「API 站」）的 enclosure 不是直链，
# 而是 `[base64(json)]url`：先请求 url（换票接口）拿到返回里的临时下载地址，再下真正的种子。
# MoviePilot 本体在下载链里会解这个格式（app/chain/download/submission.py
# `_resolve_indirect_download_url`），但我们自己取种字节时也要解，
# 否则只会去 GET 那个 API 地址 → 永远「无法打开链接」。
_INDIRECT_URL_RE = re.compile(r"^\[(.*?)](.*)$", re.S)


def _resolve_indirect_download_url(
    url: str,
    cookie: Optional[str] = None,
    user_agent: Optional[str] = None,
    proxies: Optional[str] = None,
    referer: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """把换票地址解析成真实下载地址，返回 ``(直接可用地址, 错误信息)``。

    非换票地址原样返回（``err=None``）；解析失败返回 ``("", 原因)``。
    参数语义与 MoviePilot 下载链保持一致（`params` 走查询串、`header` 整包替换）。
    """
    raw = str(url or "").strip()
    match = _INDIRECT_URL_RE.match(raw)
    if not match:
        return raw, None
    encoded, request_url = match.group(1), match.group(2)
    if not encoded:
        return request_url, None
    try:
        spec = json.loads(base64.b64decode(encoded.encode("utf-8")).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return "", f"换票请求解析失败:{e}"
    if not isinstance(spec, dict):
        return "", "换票请求格式错误"
    _headers = spec.get("header") if isinstance(spec.get("header"), dict) else None
    _params = spec.get("params") if isinstance(spec.get("params"), dict) else None
    _cookie = cookie if spec.get("cookie") else None
    try:
        from app.sdk.network import RequestUtils

        req = RequestUtils(
            headers=_headers or None,
            cookies=_cookie,
            proxies=proxies,
            ua=user_agent,
            referer=referer,
            timeout=30,
        )
        _dl_gate()
        if str(spec.get("method") or "post").lower() == "get":
            resp = req.get_res(url=request_url, params=_params)
        else:
            resp = req.post_res(url=request_url, params=_params)
    except Exception as e:  # noqa: BLE001
        return "", f"换票请求异常:{e}"
    if resp is None:
        return "", "换票请求无响应"
    if not getattr(resp, "ok", False):
        _code = getattr(resp, "status_code", "?")
        if _code in (429, 503):
            _dl_note_flow_control()
        return "", f"换票请求失败:{_code}"
    result_path = spec.get("result")
    if not result_path:
        return str(resp.text or "").strip(), None
    try:
        data: Any = resp.json()
    except Exception as e:  # noqa: BLE001
        return "", f"换票响应非 JSON:{e}"
    success_key = spec.get("success")
    if success_key and isinstance(data, dict) and not data.get(success_key):
        return "", "换票接口返回失败标记"
    for key in str(result_path).split("."):
        if not isinstance(data, dict):
            data = None
            break
        data = data.get(key)
        if not data:
            break
    if not data:
        return "", "换票响应缺少下载地址"
    return str(data).strip(), None


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

# ★ qB 会话失效（旧 SID 过期/ qB 重启）时，几乎所有 API 都返回 403 Forbidden
_QB_AUTH_ERROR_HINTS = ("Forbidden", "Forbidden403Error", "Unauthorized", "Unauthorized401Error", "LoginFailed", "403", "401")


def _is_auth_error(err: Any) -> bool:
    """判断异常/返回值是否属于「会话失效」类错误（可重连自救）。"""
    s = f"{type(err).__name__}: {err}"
    return any(k in s for k in _QB_AUTH_ERROR_HINTS)


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
    last_activity: float = 0.0   # 最后一次活动时间戳（秒；qB last_activity，用于停滞估算）
    completion_on: float = 0.0   # ★ 11.6.1 完成时间戳（秒；qB completion_on，H&R 做种时长的保守上界）
    content_path: str = ""
    is_zero_bonus: bool = False
    is_free: bool = False
    is_double_free: bool = False
    # ★ 11.7.0：该字段**只由候选构造**（fetcher 从站点列表读到的逐种标记），qB 侧没有此信息、
    #   也不在 ``_from_qb`` 映射里；账单的 ``rule`` 必须在**下载瞬间**用候选值落账，不得回读 qB 快照。
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


def seed_hours_for_hr(torrent: Any, now: float = 0.0) -> float:
    """H&R 口径的「已挂做种小时数」——**保守**取值。

    ★ 11.6.1 修：qB ``seeding_time`` 在部分情形会把「未下完的时段」也算进去
    （实测 CARPT 目标 ``fe00726e1dd4``：added 06:49、真正完成 22:42，qB 却报 16.0h）。
    直接采信 → 「挂够 24h」提前达成 → 账单提前结清 → 提前删种 → **真欠 H&R**。
    故取：① 未下完（``progress < 0.999``）→ 0；② 已下完 → ``min(qB seeding_time, now - completion_on)``。
    只会往**小**里算（= 保护更久），不会让欠账被低估。
    """
    try:
        prog = float(getattr(torrent, "progress", 0) or 0)
    except (TypeError, ValueError):
        prog = 0.0
    if prog < 0.999:
        return 0.0
    try:
        sec = float(getattr(torrent, "seed_time", 0) or 0)
    except (TypeError, ValueError):
        sec = 0.0
    try:
        comp = float(getattr(torrent, "completion_on", 0) or 0)
    except (TypeError, ValueError):
        comp = 0.0
    if comp > 0:
        try:
            _now = float(now or 0) or time.time()
        except Exception:  # noqa: BLE001
            _now = time.time()
        sec = min(sec, max(0.0, _now - comp))
    return max(0.0, sec) / 3600.0


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
        self.tags_enabled = True  # ★ 标签写开关（show_qb_tags=False 时由上层关掉）
        # ★ 删除唯一入口（Master 2026-10-05「删除令出一门」）：由插件挂上
        #   gate=硬保护判定回调 / deletion_log=统一台账回调。见 features/deletegate.py。
        self.gate = None
        self.deletion_log = None
        self._init_downloader()
        # ★ 裸构造也自动挂闸门：注册在案的安装器（见 set_gate_installer）在构造末尾执行 →
        #   消除「类属性 _global_gate 至少要设过一次」的顺序依赖（热重载后归零 → 裸构造无闸门）。
        #   安装器本身失败也不放行：delete_torrents 的 fail-closed 兜底会把删种全阻断。
        if _INSTALL is not None:
            try:
                _INSTALL(self)
            except Exception as _ins_err:  # noqa: BLE001
                logger.error(f"删除闸门安装器执行失败（fail-closed 兜底仍生效）: {_ins_err}")

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

    def _reconnect_downloader(self) -> bool:
        """★ 强制重连下载器（qB 会话失效返回 403 时自愈）。

        背景：MP 的 qB 客户端是**长连接单例**；qB 侧会话过期（``WebUI\\SessionTimeout``）
        或 qB 重启后，旧 SID 一律 403 Forbidden。而 MP 的 ``is_inactive()`` 只在
        「从未登录成功」时为真 → **不会自动重连**，表现为插件所有 qB 调用持续 Forbidden。
        这里主动调 MP 客户端的 ``reconnect()``（内部会重新 ``auth_log_in``）。
        """
        try:
            fn = getattr(self._downloader, "reconnect", None)
            if not callable(fn):
                return False
            fn()
            return bool(getattr(self._downloader, "qbc", None))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"下载器重连失败: {e}")
            return False

    def _qb_call(self, method: str, *args, **kwargs) -> Any:
        """调用底层 qB 客户端方法；遇 403/401（会话失效）时**强制重连并重试一次**。"""
        qbc = self._qb_client()
        fn = getattr(qbc, method, None) if qbc is not None else None
        if not callable(fn):
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if not _is_auth_error(e):
                raise
            logger.warning(f"qB 会话失效（{e}），重连后重试: {method}")
            if not self._reconnect_downloader():
                raise
            fn = getattr(self._qb_client(), method, None)
            if not callable(fn):
                return None
            return fn(*args, **kwargs)

    @property
    def is_available(self) -> bool:
        """检查下载器是否可用。"""
        return self._downloader is not None

    def normalize_path(self, path: str) -> str:
        """把下载器返回的（宿主）路径反向映射为 MoviePilot 可访问（容器）路径。

        依据下载器配置里的 ``path_mapping``（每项 ``[容器路径, 宿主路径]``）做前缀替换；
        无法映射时原样返回（例如本就已是容器路径）。
        """
        if not path:
            return path
        try:
            _ensure_sdk()
            conf = None
            if DownloaderHelper is not None:
                try:
                    conf = DownloaderHelper().get_config(name=self.downloader_name)
                except Exception:  # noqa: BLE001
                    conf = None
            mapping = getattr(conf, "path_mapping", None) or []
            norm = path.rstrip("/") or "/"
            for pair in mapping:
                try:
                    storage_path, download_path = (list(pair) + [None, None])[:2]
                except Exception:  # noqa: BLE001
                    continue
                if not storage_path or not download_path:
                    continue
                dp = str(download_path).rstrip("/")
                sp = str(storage_path).rstrip("/")
                if dp and (norm == dp or norm.startswith(dp + "/")):
                    return sp + norm[len(dp):]
        except Exception as _e:  # noqa: BLE001
            logger.warning(f"[路径映射] 失败: {_e}")
        return path

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

        # ★ 15.3.0：qB 走增量快照（/sync/maindata?rid=），本地过滤；不可用则回退全量。
        snap = self._snapshot_torrent_infos(tags=tags, status=status)
        if snap is not None:
            return snap, None

        try:
            torrents, error = self._downloader.get_torrents()
            if error:
                # ★ qB 会话失效会一直报错 → 强制重连后重试一次（自愈）
                if self._reconnect_downloader():
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

    def _snapshot_torrent_infos(
        self,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> Optional[List[TorrentInfo]]:
        """由 qB **增量快照**本地过滤出 TorrentInfo 列表；不可用返回 None（调用方回退全量）。

        数据源 = ``qbsync.QbSyncStore``（``/sync/maindata?rid=`` 增量合并，纯内存）。
        返回的每行字段与 ``torrents_info()`` 一致（``hash`` 已注入）→ 语义等价。
        """
        if not QB_SYNC_INCREMENTAL or self.downloader_name != "qbittorrent":
            return None
        qbc = self._qb_client()
        if qbc is None:
            return None
        try:
            rows = get_qb_sync_store(self.downloader_name).torrents(qbc)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"qB 增量快照不可用（回退全量）: {err}")
            return None
        if rows is None:
            return None
        out: List[TorrentInfo] = []
        for row in rows:
            if tags:
                row_tags = _split_tags(_kv(row, "tags", ""))
                if not any(t in row_tags for t in tags):
                    continue
            if status:
                st = str(_kv(row, "state", "") or "").strip().lower()
                if status == "seeding" and st not in QB_SEEDING_STATES:
                    continue
                if status == "downloading" and st not in QB_DOWNLOADING_STATES:
                    continue
                if status == "paused" and st not in QB_PAUSED_STATES:
                    continue
            try:
                out.append(self._parse_torrent_info(row))
            except Exception:  # noqa: BLE001
                continue
        return out

    def qb_sync_stats(self) -> Dict[str, Any]:
        """qB 增量快照观测（``/agent/qb/snapshot``）：全量/增量/无变化次数 + 上次增量规模。"""
        try:
            return get_qb_sync_store(self.downloader_name).stats()
        except Exception as err:  # noqa: BLE001
            return {"downloader": self.downloader_name, "error": str(err)}

    def get_raw_torrents(self) -> List[Any]:
        """获取下载器中**全部**种子（不限标签）。"""
        if not self._downloader:
            return []
        # ★ 15.3.0：qB 增量快照（字段齐全的行，含 hash）；不可用则回退全量。
        if QB_SYNC_INCREMENTAL and self.downloader_name == "qbittorrent":
            qbc = self._qb_client()
            if qbc is not None:
                try:
                    rows = get_qb_sync_store(self.downloader_name).torrents(qbc)
                except Exception as err:  # noqa: BLE001
                    logger.debug(f"qB 增量快照不可用（回退全量）: {err}")
                    rows = None
                if rows is not None:
                    return list(rows)
        try:
            torrents, error = self._downloader.get_torrents()
            if error:
                if self._reconnect_downloader():
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

    def tracker_domain(self, hash_string: str) -> str:
        """按需从 ``torrents_trackers`` 解析站点域名（qB 的 ``tracker`` 字段常为空时的兜底）。

        实测 qB ``torrents_info`` 的 tracker 字段会为空（实测 250/726），但逐 hash 的
        ``torrents_trackers`` 能拿到真实 announce 地址 —— 只在需要归属判定时调用。

        ★ 带 TTL 缓存：纳管/同站识别每轮都会问，而 announce 域名几乎不变；
          不缓存的话每个任务每轮要为「空 tracker」的种打 200+ 次 qB 请求。
        """
        h = str(hash_string or "").strip().lower()
        if not h:
            return ""
        _cache = _tracker_domain_cache()
        _now = time.time()
        _hit = _cache.get(h)
        if _hit and (_now - _hit[0]) < _TRACKER_DOMAIN_TTL:
            return _hit[1]
        try:
            qbc = self._qb_client()
            rows = self._qb_call("torrents_trackers", torrent_hash=h) or []
        except Exception:  # noqa: BLE001
            return ""
        for x in rows:
            url = str((x or {}).get("url") or "")
            if not url or url.startswith("**"):
                continue
            m = re.search(r"https?://([^/]+)", url)
            host = (m.group(1) if m else url).lower().split(":")[0]
            for pre in ("tracker.", "www."):
                if host.startswith(pre) and len(host) > len(pre) + 3:
                    host = host[len(pre):]
            if host:
                _tracker_domain_store(_cache, h, _now, host)
                return host
        _tracker_domain_store(_cache, h, _now, "")
        return ""

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

        # 0.5) 换票地址（API 站）：先解出真实下载地址，再走原来的下载逻辑。
        _raw_url = url
        if str(url).lstrip().startswith("["):
            _direct, _err = _resolve_indirect_download_url(
                url, cookie=cookie, user_agent=user_agent, proxies=proxies, referer=referer
            )
            if not _direct:
                logger.warning(f"换票地址解析失败 {str(url)[:60]}: {_err}")
                return None
            if str(_direct).startswith("magnet:"):
                logger.info(f"换票地址返回磁力链接，跳过字节下载：{str(_direct)[:60]}")
                return None
            _hit = _torrent_cache_get(_direct)
            if _hit is not None:
                _torrent_cache_put(_raw_url, _hit)
                return _hit
            url = _direct

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
                    if _raw_url != url:
                        _torrent_cache_put(_raw_url, _bytes)
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
        """等待校验结束，返回进度（0~1）。**超时（仍在校验）返回 None**。"""
        deadline = time.time() + max(timeout, 5)
        pending = {"checkingdl", "checkingup", "checkingresume", "moving", "allocating", "metadl"}
        progress = None
        _last_log = 0.0
        while time.time() < deadline:
            raw = self._find_raw_torrent(hash_string)
            if raw is None:
                time.sleep(2)
                continue
            state = str(_kv(raw, "state", "") or "").lower()
            progress = float(_kv(raw, "progress", 0) or 0)
            if state not in pending and not state.startswith("checking"):
                return progress
            # 大种子校验很慢（几十 GB 常要数分钟）→ 每 20s 记一次，方便判断它到底在不在动
            if time.time() - _last_log >= 20:
                _last_log = time.time()
                logger.info(f"[标签审计] 辅种校验中 {hash_string[:10]} state={state} "
                            f"progress={progress:.1%}")
            time.sleep(2)
        return None  # 到点还在校验 → 视为「未完成」，由调用方撤销

    def add_torrent_reuse(
        self,
        torrent_bytes: bytes,
        save_path: str,
        tag: Optional[str] = None,
        cookie: Optional[str] = None,
        verify: bool = True,
        timeout: int = 120,
        start: bool = True,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        辅种：把候选种子指向本机已有文件添加做种。

        流程：以**暂停**方式添加（不下载）→ recheck → 校验通过后开始做种；
        校验不通过（文件对不上）则**撤销**该种子（未下载任何数据）。

        ``start=False``：校验通过后**不启动**（停在 paused，交由静默闸 / 任务纳管决定）——
        用于「入池即暂停」不变量（11.11.0）。

        Returns:
            (种子 hash, 错误信息)
        """
        if not self._downloader:
            return None, "下载器不可用"
        if not str(save_path or "").strip():
            return None, "未配置保存目录，已跳过（避免落到下载器默认目录）"
        if not torrent_bytes:
            return None, "种子内容为空"

        # ★ 一律带上「辅种」标记：它是复用种（不是下载种），自动清理/清理机制必须放过它
        tag_list = [tag] if tag else []
        if REUSE_MARK not in tag_list:
            tag_list.append(REUSE_MARK)

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

        # ★ 等 qB 先「认识」这颗新种：add 返回 ≠ 立即可见；
        #   若立刻 recheck，qB 会因为找不到该 hash 而静默忽略 → 状态停在 stopped/paused 0% → 误判「文件不匹配」
        _appeared = False
        for _try in range(30):
            if self._find_raw_torrent(hash_string) is not None:
                _appeared = True
                break
            time.sleep(0.5)
        if not _appeared:
            return None, _delete_added("添加后未出现在下载器，已撤销")

        # 重新校验：指向已有文件，若命中则瞬时 100%
        try:
            _raw = self._find_raw_torrent(hash_string) or {}
            logger.info(
                f"[标签审计] ADD-REUSE recheck hash={hash_string} "
                f"qb_save_path={_kv(_raw, 'save_path', '')} "
                f"qb_content_path={_kv(_raw, 'content_path', '')} "
                f"size={_kv(_raw, 'size', 0)}"
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            self._downloader.recheck_torrents(hash_string)
        except Exception as e:
            logger.warning(f"触发校验失败 {hash_string}: {e}")

        if verify:
            # ★ 校验时长按体积给：NAS 上 100GB 的种抽查要十几分钟，写死 120s 会把好种当坏种删掉
            try:
                _r = self._find_raw_torrent(hash_string) or {}
                _size = float(_kv(_r, "size", 0) or 0)
            except Exception:  # noqa: BLE001
                _size = 0.0
            _need = int(300 + (_size / 1024 ** 3) * 20) if _size else int(timeout)
            timeout = max(int(timeout), _need)
            progress = self._wait_checked(hash_string, timeout=timeout)
            if progress is None:
                # 校验超时/无法确认 → 撤销，避免留下「暂停·0%」僵尸种
                return None, _delete_added("校验超时/未知，已撤销（避免残留）")
            if progress < 0.999:
                # 文件不匹配 → 撤销，避免白白下载
                return None, _delete_added(f"文件不匹配（校验 {progress:.1%}），已撤销")

        # 开始做种（start=False 时保持暂停，入池即暂停）
        if start:
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
            torrent = self._find_raw_torrent(hash_string)
            if torrent is None and hasattr(self._downloader, "get_torrent"):
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
        content_path = str(_kv(torrent, "content_path", "") or "")
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
        # ★ 11.2.1：最后活动时间（qB ``last_activity``）——用于「停滞估算」
        try:
            last_activity = float(_kv(torrent, "last_activity", 0) or 0)
        except (TypeError, ValueError):
            last_activity = 0.0
        # ★ 11.6.1：完成时间戳（qB ``completion_on``）——H&R 做种时长保守上界
        try:
            completion_on = float(_kv(torrent, "completion_on", 0) or 0)
        except (TypeError, ValueError):
            completion_on = 0.0

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
            content_path=content_path,
            progress=progress,
            downloaded=downloaded,
            added_on=added_on,
            last_activity=last_activity,
            completion_on=completion_on,
            tracker=str(_kv(torrent, "tracker", "") or ""),
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
        site_domain: str = "",
        hit_and_run: bool = False,
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
            site_domain: 站点域名（10.2.0 下载即开账；可选，默认空）
            hit_and_run: ★ 11.7.0 逐种 H&R 标记（如 YemaPT ``hrPunishEnable``）。qB 无此字段，
                只能在**下载瞬间**由候选带入开账钩子；带默认值，老调用点行为不变。

        Returns:
            (种子 hash, 错误信息)
        """
        if not self._downloader:
            return None, "下载器不可用"
        if not str(download_dir or "").strip():
            return None, "未配置保存目录，已跳过（避免落到下载器默认目录）"

        result: Tuple[Optional[str], Optional[str]] = (None, None)
        try:
            if self.downloader_name == "qbittorrent":
                result = self._add_torrent_qbittorrent(
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
                result = self._add_torrent_transmission(
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

        # ★ 10.2.0 下载即开账（影子记账）：添加成功后回调 H&R 开账钩子（异常吞掉，绝不影响添加）
        _hs, _err = result or (None, None)
        if _hs and not _err:
            try:
                _fn = _HR_OPEN
                if callable(_fn):
                    _fn(str(_hs), str(site_domain or ""), str(tag or ""), content,
                        bool(hit_and_run))
            except Exception:  # noqa: BLE001
                logger.error("HR 开账钩子异常", exc_info=True)
        return result

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
        reason: str = "",
        source: str = "",
    ) -> Tuple[int, Optional[str]]:
        """
        删除种子。

        ★ 这是插件内**唯一**的删种物理入口（Master 2026-10-05「删除令出一门」）。
        删除前先过 ``self.gate``（硬保护：欠 H&R / 跨站来源份 / 已认领 / 手动保留）——
        受保护的一律拒删；删完（含失败 / 拦截）写 ``self.deletion_log`` 统一台账。

        Args:
            hashes: 种子 hash 列表
            delete_file: 是否删除文件
            reason: 删除原因（进统一台账，便于排障）
            source: 调用来源（模块.函数；留空则由台账自动从调用栈推断）

        Returns:
            (成功删除数量, 错误信息)
        """
        if not self._downloader:
            return 0, "下载器不可用"

        if not hashes:
            return 0, None

        # ★ 硬保护闸门：任何路径都不得删「欠 H&R / 跨站来源份 / 已认领 / 手动保留」的种。
        #   ★ 2026-10-05 补两个洞（fail-closed，默认开，见 common.DELETE_GATE_FAIL_CLOSED）：
        #     ① fail-silent：gate 取值链**拿不到任何回调**（含热重载后类属性归零 + 裸构造）→ 旧代码整段跳过；
        #     ② fail-open：gate 回调**抛异常** → 旧代码 _blk=set() 照样删。
        #   现在两者都 → **全部阻断**（不删、返回 0、台账标注 blocked_by=gate_error）。
        #   set_gate_fail_closed(False) 可回退旧行为（放行 / 仅记日志）。
        _blocked: List[str] = []
        _gate = getattr(self, "gate", None) or getattr(type(self), "_global_gate", None)
        if _gate is None:
            if _GATE_FAIL_CLOSED:
                logger.error(
                    "[删除闸门] 未安装闸门（fail-closed）：拒绝删除全部 %d 个种子（硬保护无法判定）"
                    % len(hashes)
                )
                _blocked = list(hashes)
                self._emit_delete_log(
                    [], delete_file, reason, source,
                    "删除闸门未安装（fail-closed），已全部阻断",
                    _blocked, blocked_by="gate_error",
                )
                return 0, "删除闸门未安装（fail-closed），已全部阻断"
            # 兼容旧行为：拿不到闸门 → 放行
            logger.warning("[删除闸门] 未安装闸门，按旧行为放行（fail-open）")
        else:
            try:
                _blk = {str(x).strip().lower() for x in (_gate(list(hashes)) or set())}
            except Exception as _g_err:  # noqa: BLE001
                if _GATE_FAIL_CLOSED:
                    logger.error(
                        "[删除闸门] 闸门异常（fail-closed）：拒绝删除全部 %d 个种子: %s"
                        % (len(hashes), _g_err)
                    )
                    _blocked = list(hashes)
                    self._emit_delete_log(
                        [], delete_file, reason, source,
                        f"删除闸门异常（fail-closed），已全部阻断: {_g_err}",
                        _blocked, blocked_by="gate_error",
                    )
                    return 0, f"删除闸门异常（fail-closed），已全部阻断: {_g_err}"
                # 兼容旧行为：闸门异常 → 放行
                logger.error(f"删除闸门异常（放行）: {_g_err}")
                _blk = set()
            if _blk:
                _blocked = [h for h in hashes if str(h or "").strip().lower() in _blk]
                hashes = [h for h in hashes if str(h or "").strip().lower() not in _blk]
                logger.warning(
                    f"[删除闸门] 拦截 {len(_blocked)} 个受硬保护种子"
                    f"（欠 H&R / 跨站来源份 / 已认领 / 手动保留）"
                )

        if not hashes:
            self._emit_delete_log([], delete_file, reason, source, None, _blocked)
            return 0, None

        # ★★ 11.12.0：删除前「账单直查断言」+「滚动窗口熔断」（独立于闸门推导链，fail-closed）。
        #   目的：防「闸门推导链被 bug 绕过」把真欠 H&R 的种删掉（2026-10-05 事故根因），
        #   并防失控循环把同一批种反复删除。任一抛异常 → 全阻断（不删）。
        try:
            _ba = getattr(self, "_delete_bill_assert", None)
            _bill_why = _ba(list(hashes)) if callable(_ba) else {}
        except Exception as _ba_err:  # noqa: BLE001
            _bill_why = {str(h or "").strip().lower(): f"账单断言异常:{_ba_err}" for h in hashes}
        _brk_why: Dict[str, str] = {}
        try:
            _bk = getattr(self, "_delete_breaker_check", None)
            if callable(_bk):
                _brk_blocked, _brk_info = _bk(
                    hashes, delete_file=delete_file, reason=reason, source=source)
                for h in (_brk_blocked or set()):
                    _brk_why[str(h).strip().lower()] = str(_brk_info.get("reason") or "删除熔断")
        except Exception as _brk_err:  # noqa: BLE001
            _brk_why = {str(h or "").strip().lower(): f"删除熔断异常:{_brk_err}" for h in hashes}
        _assert_why: Dict[str, str] = {**_bill_why, **_brk_why}
        if _assert_why:
            _eb = [h for h in hashes if str(h or "").strip().lower() in _assert_why]
            if _eb:
                _blocked.extend(_eb)
                hashes = [h for h in hashes if str(h or "").strip().lower() not in _assert_why]
                _first = next(iter(_assert_why.values()), "")
                logger.warning(
                    f"[删除断言/熔断] 阻断 {len(_eb)} 个种子（{_first}）"
                )
                try:
                    self._emit_delete_log([], delete_file, reason, source,
                                          None, list(_eb), blocked_by="bill_assert/breaker")
                except Exception:  # noqa: BLE001
                    pass
        if not hashes:
            self._emit_delete_log([], delete_file, reason, source, None, _blocked)
            return 0, "删除被账单断言/熔断阻断"

        # ★ 删种前先向 tracker 报到一次：站点更快把状态从「下载中/做种中」更新为已停止，
        #   对症「站点一直显示下载中」。尽力而为，失败仅记日志、不阻断删除。
        try:
            _rn, _rn_err = self.reannounce(hashes)
            if _rn:
                logger.info(f"[报到] 删除前已重新报到 {_rn} 个种子")
        except Exception as _rn_exc:  # noqa: BLE001
            logger.debug(f"删除前重新报到异常（忽略）: {_rn_exc}")

        # ★★ 共享文件护栏（2026-10-01）：要连文件删时，先看这些种的文件是否被**别的**种子共用
        #   （跨站辅种 / 多任务同一份资源）。共用则只删种、不删文件 —— 否则会把别人的文件一起干掉
        #   （2026-10-01 事故：多站辅种共用同一份文件，其中一路删种连文件 → 其余站全成空壳）。
        shared: Set[str] = set()
        if delete_file:
            shared = self._shared_file_hashes(hashes)
            if shared:
                logger.info(
                    f"[共享护栏] {len(shared)}/{len(hashes)} 个种的文件被其它种子共用 → 降级为只删种不删文件"
                )

        try:
            success_count = 0
            _ok_hashes: List[str] = []
            for hash_string in hashes:
                _df = bool(delete_file) and str(hash_string or "").strip().lower() not in shared
                if self._downloader.delete_torrents(ids=[hash_string], delete_file=_df):
                    success_count += 1
                    _ok_hashes.append(hash_string)

            _err: Optional[str] = None
            if success_count < len(hashes):
                _err = f"部分种子删除失败 ({success_count}/{len(hashes)})"
            elif _blocked and success_count == 0:
                _err = f"{len(_blocked)} 个种子受硬保护，已拦截（未删除）"
            self._emit_delete_log(_ok_hashes, delete_file, reason, source, _err, _blocked)
            return success_count, _err

        except Exception as e:
            logger.error(f"删除种子失败: {e}")
            self._emit_delete_log([], delete_file, reason, source, str(e), _blocked)
            return 0, str(e)

    def _emit_delete_log(
        self,
        hashes: List[str],
        delete_file: bool,
        reason: str,
        source: str,
        error: Optional[str],
        blocked: Optional[List[str]],
        blocked_by: str = "",
    ) -> None:
        """调用插件挂上的统一台账回调（未挂则忽略）。

        ``blocked_by``：阻断原因分类（如 ``"gate_error"`` 表示闸门故障导致 fail-closed 全阻断）；
        旧签名回调（无该形参）自动退化为 6 参调用，保证向后兼容。
        """
        cb = getattr(self, "deletion_log", None) or getattr(type(self), "_global_dlog", None)
        if not cb:
            return
        try:
            cb(list(hashes or []), bool(delete_file), str(reason or ""),
               str(source or ""), error, list(blocked or []), blocked_by=str(blocked_by or ""))
        except TypeError:
            # 兼容旧签名回调：退回 6 参调用
            try:
                cb(list(hashes or []), bool(delete_file), str(reason or ""),
                   str(source or ""), error, list(blocked or []))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _shared_file_hashes(self, hashes: List[str]) -> Set[str]:
        """返回这些 hash 中「文件被下载器里别的种子共用」的子集（小写）。

        判定：下载器里存在**别的**种子，其 ``save_path`` 与本种相同且 ``content_path``
        的顶层目录名/文件名相同（同一份资源被多站/多任务挂）。取不到索引时返回空集
        （保持原行为，绝不因为查不到就阻断删除）。
        """
        want = {str(h or "").strip().lower() for h in (hashes or []) if str(h or "").strip()}
        if not want:
            return set()
        try:
            index = self.get_all_torrents_index()
        except Exception as err:  # noqa: BLE001
            logger.debug(f"[共享护栏] 取种子索引失败（跳过检查）: {err}")
            return set()
        if not index:
            return set()
        buckets: Dict[Tuple[str, str], List[str]] = {}
        for h, t in index.items():
            cp = str(getattr(t, "content_path", "") or "").strip()
            if not cp:
                continue
            key = (str(getattr(t, "save_path", "") or "").strip(),
                   cp.rstrip("/").rsplit("/", 1)[-1])
            buckets.setdefault(key, []).append(str(h).lower())
        out: Set[str] = set()
        for h in want:
            t = index.get(h)
            if t is None:
                continue
            cp = str(getattr(t, "content_path", "") or "").strip()
            if not cp:
                continue
            key = (str(getattr(t, "save_path", "") or "").strip(),
                   cp.rstrip("/").rsplit("/", 1)[-1])
            # ★ 只认「不在本批删除集合里」的别人（同批一起删的互不算共用）
            if any(x not in want for x in buckets.get(key, [])):
                out.add(h)
        return out

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
        if not self.tags_enabled:  # ★ 标签写已关闭（纯账本模式）
            return False
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

    def _tags_of(self, hash_string: str) -> List[str]:
        """读单个种子当前标签（qB 返回可能是逗号串）。"""
        raw = None
        try:
            raw = self._find_raw_torrent(hash_string)
        except Exception:  # noqa: BLE001
            raw = None
        if raw is None:
            return []
        raw_tags = getattr(raw, "tags", None)
        if raw_tags is None:
            try:
                raw_tags = raw.get("tags")  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                raw_tags = None
        if isinstance(raw_tags, str):
            return [x.strip() for x in raw_tags.split(",") if x.strip()]
        if isinstance(raw_tags, (list, tuple)):
            return [str(x).strip() for x in raw_tags if str(x).strip()]
        return []

    def add_torrents_tag(self, hashes: List[str], tag: str) -> Tuple[int, Optional[str]]:
        """批量**追加**一个标签（只加不减），**带校验**。

        ★ 用于给一票种统一打「魔流-H&R」这类**管理标记**。
        ⚠ 踩过：``torrents_add_tags(hashes=[...])`` 传 list 时 qB 侧静默不生效
        （273 个只落了 1 个）→ 这里先试「pipe 串」批量，**读回校验**，不行再逐个补。
        """
        if not self.tags_enabled:  # ★ 标签写已关闭（纯账本模式）
            return 0, None
        tg = str(tag or "").strip()
        hs = [str(h).strip().lower() for h in (hashes or []) if str(h).strip()]
        if not tg or not hs:
            return 0, None
        qbc = getattr(self, "_qb_client", None)
        qbc = qbc() if callable(qbc) else None
        if qbc is not None:
            try:
                self._qb_call("torrents_add_tags", tags=tg, hashes="|".join(hs))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"批量打标签(pipe)失败: {e}")
        # 校验前若干个；不够就逐个补
        sample = hs[:5]
        hit = sum(1 for h in sample if tg in self._tags_of(h))
        if sample and hit == 0:
            logger.info("批量打标签未生效 → 回退逐个补")
        ok = 0
        for h in hs:
            try:
                if tg in self._tags_of(h) or self.set_torrent_tags(h, [tg]):
                    ok += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"打标签失败 {h}: {e}")
        # 最终校验（抽样）
        miss = [h for h in hs[:5] if tg not in self._tags_of(h)]
        err = None if not miss else f"校验未过({len(miss)}/{len(sample)})"
        return ok, err

    def force_start_torrents(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """★ **强制开始**做种/下载（qB ``torrents_set_force_start``）。

        与 ``resume_torrents`` 的区别：force start **绕过队列/排队**，
        「没到时间却被暂停」的 H&R 种必须能立刻挂起来（Master 2026-09-28 01:37）。
        """
        hs = [str(h).strip().lower() for h in (hashes or []) if str(h).strip()]
        if not hs:
            return 0, None
        qbc_fn = getattr(self, "_qb_client", None)
        qbc = qbc_fn() if callable(qbc_fn) else None
        if qbc is not None:
            ok = 0
            for h in hs:  # ★ 逐个（批量传 list 在 qB 侧同样不生效）
                try:
                    self._qb_call("torrents_set_force_start", hashes=h)
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"强制开始失败 {h}: {e}")
            if ok:
                # 校验：读回状态，仍是 paused/stopped 的再用 resume 兜一层
                stuck: List[str] = []
                for h in hs:
                    try:
                        st = str(getattr(self.get_torrent_info(h), "state", "") or "").lower()
                    except Exception:  # noqa: BLE001
                        st = ""
                    if st.startswith("paused") or st.startswith("stopped"):
                        stuck.append(h)
                if stuck:
                    self.resume_torrents(stuck)
                return ok, (None if not stuck else f"另有 {len(stuck)} 个已改 resume")
        return self.resume_torrents(hs)

    def release_force_start_torrents(self, hashes: List[str]) -> Tuple[int, Optional[str]]:
        """★ **取消强挂**：把 ``forcedUP`` 的种降回普通做种（qB ``torrents_set_force_start(enable=False)``）。

        与 ``force_start_torrents`` 相反。**不暂停、不删、不动文件** —— 只撤掉「强制绕过队列」这层，
        种继续正常做种（Master 2026-09-28 13:21「到时间摘标签就不挂了」）。
        """
        hs = [str(h).strip().lower() for h in (hashes or []) if str(h).strip()]
        if not hs:
            return 0, None
        qbc_fn = getattr(self, "_qb_client", None)
        qbc = qbc_fn() if callable(qbc_fn) else None
        if qbc is None:
            return 0, "无 qB 客户端"
        ok = 0
        for h in hs:  # ★ 逐个（与 force_start 同理：批量传 list 在 qB 侧不生效）
            try:
                self._qb_call("torrents_set_force_start", enable=False, torrent_hashes=h)
                ok += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"取消强挂失败 {h}: {e}")
        return ok, None

    def replace_torrent_tags(self, hash_string: str, tags: List[str]) -> bool:
        """★ 真正「替换」标签：先删差集、再补新增。

        MP 适配器的 ``set_torrents_tag`` 实际是 ``torrents_add_tags``（只加不删），
        迁移/改状态时必须用本方法，否则老标签会一直堆着。
        """
        if not self.tags_enabled:  # ★ 标签写已关闭（纯账本模式）
            return False
        if not self._downloader or not hash_string:
            return False
        target = [str(t).strip() for t in (tags or []) if str(t).strip()]
        cur: List[str] = []
        raw = self._find_raw_torrent(hash_string)
        if raw is not None:
            raw_tags = getattr(raw, "tags", None)
            if isinstance(raw_tags, str):
                cur = [x.strip() for x in raw_tags.split(",") if x.strip()]
            elif isinstance(raw_tags, (list, tuple)):
                cur = [str(x).strip() for x in raw_tags if str(x).strip()]
        drop = [t for t in cur if t not in target]
        add = [t for t in target if t not in cur]
        if not drop and not add:
            return True
        ok = True
        try:
            if drop and hasattr(self._downloader, "remove_torrents_tag"):
                if not self._downloader.remove_torrents_tag(hash_string, drop):
                    ok = False
            if add and hasattr(self._downloader, "set_torrents_tag"):
                self._downloader.set_torrents_tag(ids=hash_string, tags=add)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[标签审计] REPLACE-ERR hash={hash_string}: {e}")
            return False
        logger.info(f"[标签审计] REPLACE hash={hash_string} del={drop} add={add}")
        return ok

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

    def upload_limit_stats(self) -> Dict[str, int]:
        """单种上传限速分布（诊断用）。"""
        qbc = self._qb_client()
        if qbc is None:
            return {}
        try:
            info = list(self._qb_call("torrents_info") or [])
        except Exception:  # noqa: BLE001
            return {}
        out: Dict[str, int] = {}
        for t in info:
            try:
                lim = int(t.get("up_limit") or 0)
            except Exception:  # noqa: BLE001
                lim = 0
            key = "不限" if lim <= 0 else f"{lim} B/s"
            out[key] = int(out.get(key, 0)) + 1
        return out

    def set_upload_limit(self, hashes: Any, kbps: float) -> Tuple[int, Optional[str]]:
        """**单种**上传限速（KB/s；0 = 不限）。返回 (成功条数, 错误信息)。

        只支持 qBittorrent（``torrents/setUploadLimit``）；一次最多 200 个 hash，
        避免 URL 过长。
        """
        qbc = self._qb_client()
        if qbc is None:
            return 0, f"下载器 {self.downloader_name} 不支持单种限速"
        hs = [str(h).strip().lower() for h in (hashes or []) if str(h or "").strip()]
        if not hs:
            return 0, None
        try:
            limit = int(max(0.0, float(kbps or 0.0)) * 1024)
        except (TypeError, ValueError):
            limit = 0
        done = 0
        err: Optional[str] = None
        for i in range(0, len(hs), 200):
            chunk = hs[i:i + 200]
            try:
                self._qb_call("torrents_set_upload_limit", limit=limit, torrent_hashes="|".join(chunk))
                done += len(chunk)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
        return done, err

    def get_app_preferences(self) -> Tuple[Dict[str, Any], Optional[str]]:
        """读取 qBittorrent 应用级偏好（本插件关心的子集）。

        Returns:
            (偏好字典, 错误信息)。速度类字段返回**字节/秒**原值。
        """
        qbc = self._qb_client()
        if qbc is None:
            return {}, f"下载器 {self.downloader_name} 不支持读取全局参数"
        try:
            prefs = self._qb_call("app_preferences") or {}
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
            self._qb_call("app_set_preferences", payload)
            return True, None
        except Exception as e:
            logger.error(f"写入 qBittorrent 全局参数失败: {e}")
            return False, str(e)


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
