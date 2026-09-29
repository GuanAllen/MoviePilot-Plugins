# -*- coding: utf-8 -*-
"""魔流 · 公共层（常量 / 纯工具 / 模型 / 跨模块状态）。

本模块是**叶子模块**：不 import 插件其它内部模块（除各功能子模块），
任何模块都可以安全 `from ..common import ...`，不会产生循环导入。
"""

__version__ = "5.1.0"

import bisect
import copy
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from app.plugins import _PluginBase
from app.schemas import Response
from app.schemas.types import EventType
from app.sdk.events import eventmanager

from .bonus import (
    TorrentBonusInfo,
)
from .fingerprint import (
    fingerprint,
    inner_fingerprint,
    load_torrent_entries,
    total_size,
)
from .fetcher import (
    SiteCandidateTorrent,
)


# ============================================================
# 以下由 __init__.py 原样搬出（常量 / 工具 / 模型）

# ============================================================

def _torrent_entries_digest(raw: Any) -> Dict[str, Any]:
    """把一个 .torrent 拆成易读摘要（诊断用）：文件数 / 根目录名 / 内外特征码。

    `fp` = 完整特征码（含根目录名）；`inner_fp` = 去掉根目录名后的特征码。
    两者相等说明「同一个 Release、且根目录名也一样」；仅 `inner_fp` 相等
    说明「同一 Release 只是根目录名不同」。
    """
    out: Dict[str, Any] = {"n": 0, "root": "", "fp": None, "inner_fp": None, "size_gb": 0.0}
    try:
        entries = load_torrent_entries(raw)
    except Exception as e:  # noqa: BLE001
        out["err"] = f"解析失败:{e}"
        return out
    if not entries:
        out["err"] = "空文件列表"
        return out
    out["n"] = len(entries)
    try:
        out["fp"] = fingerprint(entries)
        out["inner_fp"] = inner_fingerprint(entries)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["size_gb"] = round(float(total_size(entries)) / (1024 ** 3), 2)
    except Exception:  # noqa: BLE001
        pass
    _ps = [str(p or "").replace("\\", "/").split("/", 1)[0] for p, _ in entries]
    if _ps and len(set(_ps)) == 1:
        out["root"] = _ps[0]
    out["sample"] = [str(p or "") for p, _ in entries[:4]]
    return out


# 候选扩充:站点列表页翻页数(拿更多、更老的种子)。
# 注意:是否能翻页取决于 fork 的 TorrentsChain.browse 是否支持 page 参数(启动时会记日志探测)。
BROWSE_PAGES = 3
SWAP_INTERVAL = 1800.0       # 自动换种最小间隔(秒):换种要抓候选+下载,不宜过频
SWAP_MAX_PER_ROUND = 3       # 单轮最多换几对(安全阀:避免一次性大批换下线)
SWAP_SOFT_MARGIN_MULT = 2.0  # 库内/自有种(软保护)换出所需净收益门槛 = 基础 × 该倍数
SWAP_MAX_IN_GB = 30.0        # 换入候选单个体积上限(GB,默认;任务可覆盖;0=不限)
SWAP_MAX_ADD_GB = 25.0       # 单轮换入累计「多占磁盘」上限(GB):防拿小种换进巨物
SWAP_DAY_DL_GB = 20.0        # 每任务每日换种「实际下载」上限(GB):按真实下载量计,不是磁盘增量
SWAP_DAY_DL_GB_TOTAL = 40.0  # 全局(所有任务合计)每日换种下载上限(GB):防多任务叠加把流量烧穿
SWAP_MIN_GAIN_PER_GB = 0.05  # 每 GB 下载至少要换回的魔力(/h):过滤「几十GB换零点几/h」的赔本买卖
# 游标深翻:翻页游标上限;超过则回到首页重扫(避免越翻越深拿到无效/超老页面)。
MAX_PAGE_CURSOR = 60
# 分类阶段并发预取 .torrent 的线程数(原为逐个串行,TopN=100 会耗时数分钟)。
# 注意:部分站点(如 PT时间)对下载接口有流控(429),并发过高会大面积失败,
# 故并发与最小间隔共同限速(见 TORRENT_DL_MIN_INTERVAL)。
TORRENT_FETCH_WORKERS = 3
# 下载 .torrent 的最小间隔(秒,全局串行限速)与单种子重试次数。
TORRENT_DL_MIN_INTERVAL = 1.0
TORRENT_DL_RETRIES = 3
# 分类阶段「取种」整段时长上限(秒):超过则不再等待剩余候选(个别请求可能卡死),
# 本轮跳过、下轮重试;避免把整轮拖到运行超时(600s)而触发「判定为卡死」。
TORRENT_FETCH_DEADLINE = 120.0
# 分类阶段「单次取种」硬超时(秒):若在飞请求连续这么久都没有任何完成(典型=请求卡死/站点限速),
# 则放弃等待剩余候选、立即进入处理阶段,避免个别慢请求把整段拖满。
TORRENT_FETCH_PER_TIMEOUT = 20.0
# 复用扫描上限:TopN 之外额外取回「体积邻近本机」候选做辅种判定的最大数量。
# 原为 60,会让单轮取种数达到 TopN+60(如 30+55≈85),叠加站点 .torrent 限速后
# 单轮分类阶段动辄上百秒,正是「任务卡在分类排序」的主因之一;收敛到 15。
REUSE_SCAN_MAX = 15
# ★ 辅种慢扫(独立 worker):把「复用/辅种」从主刷流流程里切出来,单独低频跑。
#   - 间隔(分钟):比刷流间隔长很多,慢慢扫,避免短时间大量取种触发站点流控。
#   - 每轮批量:一次只取这么多个候选的 .torrent 做辅种判定。
REUSE_INTERVAL_MINUTES = 15
SILENT_HOST_INTERVAL_MINUTES = 60  # ⭐「静默托管」常驻 worker 周期(分钟，低频)
SILENT_HOST_TASK_ID = "__silent_host__"  # ⭐「静默托管」常驻任务在任务列表里的只读条目 id
# 跨站免费取种的「回辅」轮询周期(分钟)：B/C/D… 站点下完后，尽快把它辅回目标站。
CROSSSEED_INTERVAL_MINUTES = 5
# 跨站检索结果的缓存 TTL(秒)：同一关键词 6 小时内不重复检索(省 PV)。
CROSSSEED_CACHE_TTL = 6 * 3600
# 跨站候选池：每轮最多把几个「本站非免费但其他条件合格」的候选拿去跨站取种。
#   —— 每个候选要在本站取一次 .torrent(1 PV)才能拿特征码，所以要封顶。
CROSSSEED_EXTRA_SCAN = 5
# 跨站候选池的构建上限(池子本身可以大一点，实际探测由 CROSSSEED_EXTRA_SCAN 封顶)。
CROSSSEED_POOL_MAX = 12
# ★ 来源份 H&R 保护：来源站未单独指定时的最短保种时长(小时)。
CROSSSEED_SEED_HOURS_DEFAULT = 24.0
# ★ 已知站点 H&R 保种时长默认值（可在设置面板「跨站」页改）。
#   学校 BTSchool 要求挂种 10h（用户实测告知）。
CROSSSEED_SITE_HOURS_DEFAULT = ["pt.btschool.club=240"]
# ★ 站点规则库(3.12.0)：用户不填「域名=小时」也能自动按站保种
RULES_INTERVAL_MINUTES = 7 * 24 * 60     # 站点规则自动刷新周期(分钟) -- 每周一次(低频探测)
RULES_PROBE_DELAY = (1.5, 3.5)           # 逐站探测之间的随机间隔(秒，礼貌限速)

# ★ 单种上传限速(KB/s)：按「种子当前状态」分档，对每个托管种子单独限速（0 = 不限）。
#   刷流档：正在刷流的种子（要冲量，给足速度，默认 5 MB/s）；
#   挂种档：魔力养护 / 跨站来源份 / 推荐（长期挂着，压低速度，默认 200 KB/s）。
#   注：咖啡等站有「恶意限速判定：单人做种 6h 内稳定 <100Kb/s」→ 挂种档不要低于 200。
SEED_UP_LIMIT_KBPS_DEFAULT = 200.0
BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT = 5120.0
SEED_UP_LIMIT_APPLY_INTERVAL = 600.0      # 最快多久重扫一次（秒），避免频繁全量写

# ★ 标签模型（3.13.0）：状态账本 + 文件组账本 + 快照
TAG_SNAPSHOT_INTERVAL = 6 * 3600.0        # 账本快照间隔（秒）
TAG_NEW_TIMEOUT = 24 * 3600.0             # 「静默-新」超时自动归「静默-普通」


def _cs_parse_site_hours(raw: Any) -> Dict[str, float]:
    """解析「站点保种时长」配置 → {域名: 小时}。

    接受两种形式：
      - list[str]：``["pt.btschool.club=10", "hdfans.org=24"]``（设置面板用）
      - dict：``{"pt.btschool.club": 10}``（兼容旧/直接写配置）
    域名统一去协议、去路径、转小写；小时钳在 0~720。
    """
    out: Dict[str, float] = {}
    items: List[Any] = []
    if isinstance(raw, dict):
        items = [f"{k}={v}" for k, v in raw.items()]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    elif isinstance(raw, str):
        items = raw.replace("\n", ",").split(",")
    for it in items:
        s = str(it or "").strip()
        if not s or "=" not in s:
            continue
        dom, _, hrs = s.partition("=")
        dom = dom.strip().lower()
        dom = re.sub(r"^https?://", "", dom).split("/")[0].strip()
        if not dom:
            continue
        try:
            val = float(str(hrs).strip())
        except (TypeError, ValueError):
            continue
        out[dom] = max(0.0, min(720.0, val))
    return out

REUSE_WORKER_BATCH = 5
# ★ 推荐甄别(刷流种价值生命周期):独立低频 worker,同样插件级单 worker + 轮转。
RECOMMEND_INTERVAL_MINUTES = 60
RECOMMEND_SCAN_MAX = 15
# 推荐/已在库检查:是否额外实时查媒体服务器(链);默认可关(trimemedia 实现会报错刷日志)
RECOMMEND_LIVE_LIBRARY_CHECK = False
# 站点级候选抓取共享缓存 TTL(秒):同站点的多个任务在此时窗内只抓**一份**候选,
# 避免 N 个任务重复打同一站点 → 触发流控(这正是「几十个任务」的主要压力来源)。
# 站点候选缓存 TTL(秒)--★3.7.1 与 PV 预算对齐:同站 1 次/小时,降低配额消耗。
#   改动要点:缓存改由 dtier.TierCache 托管(内存热层 + FileCache 冷层),热重载/重启不丢;
#   缓存 key 含 start_page(修正旧代码只按 site|pages 命中、游标深翻永远读第 0 页的 bug)。
SITE_FETCH_TTL = 3600.0
# 站点 PV 日预算(次/天):0=不限。抓取前查 dtier.PvLedger 今日已用;达到预算就不再打站点。
#   默认 0(不限),按站点覆盖见 settings.pv_budget;对 PTT 这类「300PV/天」的站请设 300。
PV_DEFAULT_DAILY_BUDGET = 0
PV_BUDGET_RESERVE = 20

# ★ 免费索引每轮翻页数：免费池很小且每小时只动几条，稳态 1 页就够。
#   主列表的 browse_pages（任务配置）只用于「非 NexusPHP / 拿不到免费索引」的回退路径。
FREE_INDEX_PAGES = 1          # 预算预留:接近上限时提前收手,给实时/签到留额度
# ★ 全局并发闸门:插件级限制「同时在飞」的 worker 数(刷流/检查/辅种慢扫合计)。
#   几十个任务若同刻开火,会一起抢线程池 + 集中打站点 → 撞流控;这里做全局封顶。
GLOBAL_WORKER_LIMIT = 6
# 站点抓取失败后的冷却(秒):失败站点在此时窗内不再重试抓取(共享给同站所有任务)。
SITE_FETCH_BACKOFF = 180.0
# 站点魔力公式抓取缓存 TTL(秒);抓取失败时只缓存 SHORT 秒后重试。
SITE_FORMULA_TTL = 12 * 3600
SITE_FORMULA_RETRY = 30 * 60
# /status 实时统计(每任务一次下载器查询)缓存 TTL(秒):
# 同一请求内「总览」与「任务列表」会各算一次,缓存可去重;也令 30s 轮询与二次进入更廉价。
STATS_TTL = 20
# 下载器「全部种子按标签分组」快照 TTL(秒):一次拉取全部种子(qB 一次 torrents_info),
# 供所有任务共用(替代「每任务各拉一次全量」)。冷启动 /status 由 N 次全量 → 1 次。
TAG_SNAPSHOT_TTL = 20.0
# 展示用标签快照的「最久可容忍陈旧」秒数：超过就阻塞重拉（防一直吃旧数据）
TAG_SNAPSHOT_STALE_MAX = 300.0
# 站点用户数据行缓存 TTL(秒):SiteOper.get_userdata_latest() 走 DB + 循环找域名,
# 一次 _status_heavy 含 7 任务 = 7 次同表 DB 查询。缓存使本轮 / 跨轮复用,DB 1 次/TTL。
USERDATA_ROW_TTL = 60.0
# 站点/下载器「下拉选项」缓存 TTL(秒):站点表/下载器表几乎不变,随 /status 重复拉取很浪费。
OPTIONS_TTL = 300.0
# ── 媒体资产价值闸门(2026-09-26)───────────────────────────────────────
#  我们是「影视管理」类插件:下了的资源除了刷魔力/刷流,还有「看 / 收藏」的价值。
#  命中下列标签的种子 = 已整理入库 / 跨站辅种(撑分享率)的「真·资产」
#  → 删种时**永不删除**,绝不为提效把主人真正要看/收藏的资源连文件一起删(delete_files 默认 True!)。
MEDIA_ASSET_TAGS: Tuple[str, ...] = ("已整理", "辅种")
#  另外,命中「下载历史」的种子也视为资产(覆盖"手动下的、还没被整理"的情况)。
#  历史集合按任务托管种批量查询,结果在此时长内缓存(秒),避免每轮都打 DB。
MEDIA_ASSET_HISTORY_TTL = 120.0
# ── 限时免费(促销到期)闸门(2026-09-26)──────────────────────────────
#  Pttime 等站的「免费/2X免费」是**限时**促销,到期后继续下按原价计流量。
#  候选已带出剩余免费时间(`SiteCandidateTorrent.free_remaining_sec`):
#  剩余 < 预估下载耗时 + 余量 → 不下(下了就是白送流量/魔力)。
#  参数(速度/余量)在 fetcher.FREE_ASSUMED_SPEED_MBPS / FREE_MIN_MARGIN_SEC。
#  被跳过的候选进 dead 冷却(沿用 `_dead_cooldown`,6h),避免反复评估同一颗。
# /status 整包重数据缓存 TTL(秒)--stale-while-revalidate:命中秒回,过期后台静默刷新。
# 与前端轮询 30s 对齐:TTL=30 → 每轮 30s 轮询只撞一次过期(后台静默刷新,前端秒回)。
STATUS_TTL = 30

# 元数据兜底:每轮最多处理的剧集目录数(其余下轮继续)
FALLBACK_SCAN_MAX = 30

# 云盘归档(夸克冷库):默认轮询周期 / 每轮上限
CLOUD_INTERVAL_MINUTES = 360
CLOUD_SCAN_MAX = 50

# ── 站点实时数据 + 站点流量监控(2026-09-26)────────────────────────────
#  MoviePilot 的站点账号数据走它自己的「站点数据刷新」任务(默认 6 小时一轮),
#  对展示够用,但对魔流的**决策**(任务目标达标 / 救号分享率 / 兑换提醒 / 下载量异常增长)太滞后。
#  这里直连站点用户栏页拿实时值,站点级缓存 + single-flight;抓不到自动回退 MP 数据。
LIVE_DEFAULT_TTL = 1800.0           # 抓取缓存 TTL(秒)--30min 缓存,同站 30min 内最多 1 次真实抓取
LIVE_INTERVAL_MINUTES = 30          # 看门狗轮询周期(分钟),避免 PTT 300PV/天 配额迅速耗尽
# 站点签到 / 模拟登录(借鉴「站点自动签到」插件)
SIGNIN_INTERVAL_MINUTES = 360       # 签到 worker 轮询周期(分钟)--同站当天已成功自动跳过
SIGNIN_RETRY_KEYWORD = "错误|失败"   # 失败文案命中则重试一次
SIGNIN_QUEUE = 5                    # 并发站点数
LIVE_DOWNLOAD_ALERT_MB = 50.0       # 下载量增长告警阈值(MB/分钟)
LIVE_RATIO_TARGET = 0.5             # 分享率目标线(低于则告警)
LIVE_ALERT_COOLDOWN_MIN = 30        # 同类告警去重窗口(分钟),避免刷屏
# 官种(official)列表抓取:缓存 TTL 与翻页数。
# 官种加成是「单种自身」的加成,会影响选种/删种排序,值得缓存抓取;
# 后宫加成依赖他人种子(用户级),与「选哪一颗」无关,不参与决策,故不抓取。
SITE_OFFICIAL_TTL = 12 * 3600
SITE_OFFICIAL_STALE_TTL = 7 * 86400   # 封禁/超预算时允许使用的「过期但可用」官种列表上限
OFFICIAL_PAGES = 2

# 下载限速:已下沉到 downloader_ops 的「自适应限速闸门」(_dl_gate / _dl_note_flow_control)。
# 命中流控时间隔指数加大、成功则回落;所有 .torrent 下载(含 SDK 与回落路径)统一走它。
# 旧的 _torrent_dl_throttle 已废弃(保留常量供参考)。


# ============================================================
# 复用:按「体积接近」预筛本机种子
# ============================================================

def _has_media_asset_tag(torrent: Any, extra_tags: Any = None) -> bool:
    """种子是否带「媒体资产」标签(已整理 / 辅种,或任务自定义排除标签)→ 删种时永不删除。"""
    tags = getattr(torrent, "tags", None) or []
    if not tags:
        return False
    if any(t in MEDIA_ASSET_TAGS for t in tags):
        return True
    if extra_tags and any(t in extra_tags for t in tags):
        return True
    return False


def _torrent_hash(torrent: Any) -> str:
    """取种子 infohash(小写)。"""
    return str(getattr(torrent, "hash", "") or "").strip().lower()


class _SizeIndex:
    """本机种子按体积索引,支持「邻近体积」查询。

    站点列表页给出的体积是**显示文本**(如 "67.93 GB"),经 `parse_size` 转成
    「四舍五入到 0.01GB」的近似字节,而下载器里的是**精确字节** → 原来用「精确相等」
    预筛几乎永远命中不了,导致跨站存量辅种恒为 0。这里改成按容差取邻近体积,
    真正是否同一资源仍由**文件列表特征码**精确判定(放宽预筛不会误辅种)。
    """

    __slots__ = ("_items", "_sizes", "_tol")

    def __init__(self, torrents: List[Any], tol: float = 0.05):
        self._tol = max(float(tol or 0.0), 0.0)
        items = []
        for t in torrents or []:
            try:
                s = int(getattr(t, "size", 0) or 0)
            except (TypeError, ValueError):
                s = 0
            if s > 0:
                items.append((s, t))
        items.sort(key=lambda x: x[0])
        self._items = items
        self._sizes = [s for s, _ in items]

    def near(self, size: int) -> List[Any]:
        """返回本机「体积与 size 相差在容差内」的种子列表(可能为空)。"""
        try:
            size = int(size or 0)
        except (TypeError, ValueError):
            return []
        if size <= 0 or not self._sizes:
            return []
        tol = self._tol
        lo = int(size * (1.0 - tol))
        hi = int(size * (1.0 + tol)) + 1
        a = bisect.bisect_left(self._sizes, lo)
        b = bisect.bisect_right(self._sizes, hi)
        return [t for _, t in self._items[a:b]]

    def __len__(self) -> int:
        return len(self._items)


# ============================================================
# 任务配置模型
# ============================================================

@dataclass
class MagicFlowTaskConfig:
    """魔流任务配置。"""
    id: str = ""
    name: str = ""
    enabled: bool = True
    site_id: int = 0
    site_domain: str = ""
    site_name: str = ""
    downloader: str = "qbittorrent"
    brush_tag: str = ""
    save_path: str = ""
    # 任务类型:bonus=刷魔力(默认);brush=刷流
    task_type: str = "bonus"
    # 运行状态(三态):running=运行中(调度开、种子正常下载/做种)
    #   seeding=做种中(停调度 + 未完成种暂停 + 已完成种继续做种)
    #   stopped=已停止(停调度 + 全部托管种暂停,保文件可逆)
    # enabled 为其派生值:enabled = (run_mode == "running")
    run_mode: str = "running"

    # 调度配置
    brush_interval: int = 5      # 刷流间隔(分钟)
    check_interval: int = 1      # 检查间隔(分钟)
    cron_expression: str = ""    # Cron 表达式(可选)
    active_time_range: str = ""  # 活跃时间段,如 "00:00-23:59"

    # 魔力配置(None = 自动推算)
    min_bonus_per_hour: Optional[float] = None   # 每小时最低魔力产出(None=按种子分布自动)
    max_keep_torrents: Optional[int] = None      # 最多保留种子数(None=按保种体积推算/不限)
    bonus_protect_threshold: Optional[float] = None  # 魔力保护阈值(None=站点当前魔力)
    min_bonus_to_keep: float = 0.0               # 最低魔力保留值(保底)
    disk_size_gb: Optional[float] = None         # 保种体积上限(GB,None=不限)
    refill_when_empty: bool = True               # 清理后主动补种
    max_add_per_run: int = 10                    # 单轮最多新增种子数(无总量上限时的每轮名额)
    max_download_concurrent: int = 10            # 本任务同时「下载中」上限(queued 不计)
    top_n: int = 30                              # 每轮参与排序处理的候选上限(≈ 每轮新增名额的 3 倍)
    browse_pages: int = 3                        # 每轮站点列表翻页数(游标深翻)

    # 存量复用(辅种)
    reuse_existing: bool = True                  # 复用本机已有资源,避免重复下载
    reuse_verify: bool = True                    # 辅种前先校验,不匹配自动撤销
    # ★ 自动换种:名额/磁盘/站点上限吃紧时,按边际魔力把低价值托管种换成高价值候选(程序自己决定换哪个)
    #   3.36.0 起**默认关**;且换入默认只做「零下载辅种」——绝不为几个魔力下载几十 GB 流量。
    auto_swap: bool = False                      # 开关(默认关)
    swap_allow_download: bool = False            # 允许「取种换入」(默认关;开启后只走免费渠道:本站免费/跨站免费副本,绝不付费下载)
    swap_ceiling_pct: float = 70.0               # 站点魔力占用 ≥ 该值 → 视为接近上限,参与换种
    swap_min_gain_pct: float = 25.0              # 净收益 ≥ 被撤种边际的该比例才动手
    swap_max_in_gb: Optional[float] = 30.0       # 换入候选单个体积上限(GB;0=不限)——不拿全盘换几个魔力
    swap_daily_dl_gb: float = 20.0               # 每任务每日换种「实际下载」上限(GB;按真实下载量计)
    swap_min_gain_per_gb: float = 0.05           # 每 GB 下载至少要换回的魔力(/h)
    swap_min_in_seeders: int = 3                 # 下载换入候选的最少做种人数(没源就下不动)
    # 跨站免费取种（3.9.0）：目标站的种子若不免费，去他站找免费同一 Release 下回来，再回辅目标站
    crossseed_enabled: bool = False              # 开关（默认关，开了才会走跨站）
    crossseed_max_per_round: int = 3             # 每轮最多发起几个跨站取种
    crossseed_max_size_gb: float = 20.0          # 单个种子大小上限（GB）
    crossseed_max_sites: int = 6                 # 每个候选最多探测几个站（PV 上限）

    # 无进度清理
    cleanup_no_progress: bool = True             # 每次运行清理「没进度」的种子
    no_progress_minutes: int = 30                # 加入下载器超过该分钟数仍无进度才清理

    # 慢速清理(用「下载速度 ÷ 体积」估算,长期下不完的种子占着下载名额)
    cleanup_slow_progress: bool = True           # 清理「下载过慢」的种子
    slow_progress_grace_minutes: int = 60        # 加入后多少分钟内不判「慢」(给新种起步时间)
    slow_progress_max_hours: float = 48.0        # 按当前速度预计还要超过该小时数才下完 → 判「过慢」

    # 促销失效清理:下载中的种子若站点已不再免费(促销过期/非免费)→ 删,避免白拉流量
    purge_unfree_incomplete: bool = True         # 下载中但站点已不再免费 → 清理(回站点核对促销)

    # 自动恢复被暂停的已完成种子(暂停 = 0 产出)
    auto_resume_paused: bool = True

    # 刷流模式(task_type=brush):以「上传产出」为准的清理
    brush_grace_minutes: int = 15    # 新种加入后多少分钟内不判「无上传」
    upload_idle_minutes: int = 10    # 连续多少分钟上传低于门槛 → 清理(0=自动≈2×检查间隔)
    upload_min_kbps: int = 200       # 平均上传速率门槛(KB/s):低于此值视为「无上传」
    brush_min_leechers: int = 1      # 刷流选种标准:最小下载人数(有下载需求才下)
    brush_seed_days: int = 2         # 刷流:做种满 N 天清理换新(0=回退「无上传」判定)
    # 产出换种(刷流):单种已上传达标 / 分享率达标 → 清理换新(None=不看)
    rotate_upload_gb: Optional[float] = None
    rotate_ratio: Optional[float] = None
    # 选种排除订阅命中(刷流)
    except_subscribe: bool = True

    # 完美种保护:非零魔 ∧ 站内做种人数≤上限 ∧ 做种周数≥下限 的优质老种永久保留
    protect_perfect: bool = True
    perfect_max_seeders: int = 3
    perfect_min_weeks: float = 4.0

    # 任务目标:达到后任务自动停止(bonus=站点魔力值;brush=站点上传量 GB;None=未设)
    goal_value: Optional[float] = None

    # 考核下载模式(新手考核的「下载增量」项):本站下载量新增目标(GB)。
    # >0 且 allow_unfree_download=True 时,刷流会**允许下载非免费种**(优先大体积),
    # 直到站点下载增量凑够 download_target_gb 就自动转「做种中」(停下载、保种)。
    download_target_gb: Optional[float] = None
    allow_unfree_download: bool = False

    # Ti 口径:publish(默认,= 自发布时间,站点文档口径;配合站点真实 Ni 与站点 A 吻合)
    #          seed_time(= qB 做种时长;无发布时间时的回落值)
    ti_source: str = "publish"

    # 已处理去重
    seen_cooldown_hours: float = 24.0            # 同一候选在多少小时内不重复拉取(0=不跳过)

    # 魔力公式参数(高级,None=用站点默认 / NexusPHP 标准式)
    bonus_t0: Optional[float] = None       # 生存时间参数 T0
    bonus_n0: Optional[int] = None         # 做种人数参数 N0
    bonus_b0: Optional[float] = None       # 每小时魔力上限 B0
    bonus_l: Optional[float] = None        # 曲线参数 L
    bonus_zero_weight: Optional[float] = None  # 零魔种子权重 Wi

    # 选种配置
    size: str = ""        # 大小范围,如 "1-50"(GB)
    seeder: str = ""      # 做种人数范围,如 "1-20"
    pubtime: str = ""     # 发布时间范围(分钟)
    include: str = ""     # 包含正则
    exclude: str = ""     # 排除正则
    freeleech: str = ""   # 免费过滤
    hr: str = ""          # H&R 过滤

    # 删除配置
    min_seed_time: int = 0      # 最低做种时间(小时)
    min_ratio: float = 0.0      # 最低分享率
    delete_files: bool = True   # 删除时是否删除文件
    exclude_zero_bonus: bool = True  # 排除零魔种子
    delete_except_tags: str = ""  # 永不删除的标签(逗号分隔,叠加「已整理/辅种」之上)

    # RSS 配置
    rss_support: bool = False   # 是否使用 RSS 模式

    # 限速配置
    up_speed: Optional[int] = None   # 上传限速(KB/s)
    dl_speed: Optional[int] = None   # 下载限速(KB/s)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "site_id": self.site_id,
            "site_domain": self.site_domain,
            "site_name": self.site_name,
            "downloader": self.downloader,
            "brush_tag": self.brush_tag,
            "save_path": self.save_path,
            "task_type": self.task_type,
            "run_mode": self.run_mode,
            "brush_interval": self.brush_interval,
            "check_interval": self.check_interval,
            "cron_expression": self.cron_expression,
            "active_time_range": self.active_time_range,
            "min_bonus_per_hour": self.min_bonus_per_hour,
            "max_keep_torrents": self.max_keep_torrents,
            "bonus_protect_threshold": self.bonus_protect_threshold,
            "min_bonus_to_keep": self.min_bonus_to_keep,
            "disk_size_gb": self.disk_size_gb,
            "refill_when_empty": self.refill_when_empty,
            "max_add_per_run": self.max_add_per_run,
            "max_download_concurrent": self.max_download_concurrent,
            "top_n": self.top_n,
            "browse_pages": self.browse_pages,
            "reuse_existing": self.reuse_existing,
            "reuse_verify": self.reuse_verify,
            "auto_swap": bool(getattr(self, "auto_swap", False)),
            "swap_allow_download": bool(getattr(self, "swap_allow_download", False)),
            "swap_ceiling_pct": getattr(self, "swap_ceiling_pct", 70.0),
            "swap_min_gain_pct": getattr(self, "swap_min_gain_pct", 25.0),
            "swap_max_in_gb": getattr(self, "swap_max_in_gb", 30.0),
            "swap_daily_dl_gb": getattr(self, "swap_daily_dl_gb", 20.0),
            "swap_min_gain_per_gb": getattr(self, "swap_min_gain_per_gb", 0.05),
            "swap_min_in_seeders": int(getattr(self, "swap_min_in_seeders", 3) or 3),
            "crossseed_enabled": self.crossseed_enabled,
            "crossseed_max_per_round": self.crossseed_max_per_round,
            "crossseed_max_size_gb": self.crossseed_max_size_gb,
            "crossseed_max_sites": self.crossseed_max_sites,
            "cleanup_no_progress": self.cleanup_no_progress,
            "no_progress_minutes": self.no_progress_minutes,
            "cleanup_slow_progress": self.cleanup_slow_progress,
            "slow_progress_grace_minutes": self.slow_progress_grace_minutes,
            "slow_progress_max_hours": self.slow_progress_max_hours,
            "purge_unfree_incomplete": self.purge_unfree_incomplete,
            "auto_resume_paused": self.auto_resume_paused,
            "brush_grace_minutes": self.brush_grace_minutes,
            "upload_idle_minutes": self.upload_idle_minutes,
            "upload_min_kbps": self.upload_min_kbps,
            "brush_min_leechers": self.brush_min_leechers,
            "brush_seed_days": self.brush_seed_days,
            "rotate_upload_gb": self.rotate_upload_gb,
            "rotate_ratio": self.rotate_ratio,
            "except_subscribe": self.except_subscribe,
            "protect_perfect": self.protect_perfect,
            "perfect_max_seeders": self.perfect_max_seeders,
            "perfect_min_weeks": self.perfect_min_weeks,
            "goal_value": self.goal_value,
            "download_target_gb": self.download_target_gb,
            "allow_unfree_download": self.allow_unfree_download,
            "ti_source": self.ti_source,
            "seen_cooldown_hours": self.seen_cooldown_hours,
            "bonus_t0": self.bonus_t0,
            "bonus_n0": self.bonus_n0,
            "bonus_b0": self.bonus_b0,
            "bonus_l": self.bonus_l,
            "bonus_zero_weight": self.bonus_zero_weight,
            "size": self.size,
            "seeder": self.seeder,
            "pubtime": self.pubtime,
            "include": self.include,
            "exclude": self.exclude,
            "freeleech": self.freeleech,
            "hr": self.hr,
            "min_seed_time": self.min_seed_time,
            "min_ratio": self.min_ratio,
            "delete_files": self.delete_files,
            "delete_except_tags": self.delete_except_tags,
            "exclude_zero_bonus": self.exclude_zero_bonus,
            "rss_support": self.rss_support,
            "up_speed": self.up_speed,
            "dl_speed": self.dl_speed,
        }

    @staticmethod
    def from_dict(d: dict) -> "MagicFlowTaskConfig":
        config = MagicFlowTaskConfig()
        for key, value in (d or {}).items():
            if hasattr(config, key):
                setattr(config, key, value)
        # run_mode 为「运行状态」唯一真源;历史配置缺该字段时按 enabled 回退。
        raw = d or {}
        mode = normalize_run_mode(raw.get("run_mode"), raw.get("enabled", True))
        config.run_mode = mode
        config.enabled = enabled_of_run_mode(mode)
        return config


# ============================================================
# 插件主类
# ============================================================

# ★ 整理完成事件订阅（「库记」的权威来源）：直接抄本机在用的写法（episodegroupmeta/personmeta）
try:
    from app.sdk.events import eventmanager as _mf_eventmanager
    from app.schemas.types import EventType as _MFEventType
    _MF_EVENTS_READY = True
except Exception:  # noqa: BLE001
    _mf_eventmanager = None
    _MFEventType = None
    _MF_EVENTS_READY = False

# 热重载会产生新实例：只让「当前活跃实例」处理事件，避免旧实例重复写账本
_MF_ACTIVE: Any = None


def _mf_on_event(event_name: str):
    """安全注册事件处理器；没有事件总线时退化成普通方法。"""
    def _deco(fn):
        if _MF_EVENTS_READY and _MFEventType is not None:
            try:
                _etype = getattr(_MFEventType, event_name)
                return _mf_eventmanager.register(_etype)(fn)
            except Exception:  # noqa: BLE001
                return fn
        return fn
    return _deco


# ============================================================
# 跨模块可变状态（唯一真值在 common，其它模块只经访问器读写）

# ============================================================

def _mf_set_active(obj: Any) -> None:
    """记录当前活跃插件实例（热重载后旧实例不再处理事件）。"""
    global _MF_ACTIVE
    _MF_ACTIVE = obj

def _mf_active_is(obj: Any) -> bool:
    """给定实例是否为当前活跃实例。"""
    return _MF_ACTIVE is obj


# ============================================================
# ★ 契约①：任务状态机（运行状态唯一真值源 = run_mode）
# ============================================================
# 三态语义（与 UI 一致）：
#   running  运行中 —— 调度开：刷流/补种/清理 + 盯站
#   seeding  做种中 —— 调度停，但**继续盯站/纳管**（不刷流流程）
#   stopped  已停止 —— 停调度、托管种暂停（保文件、可逆）
#
# 铁律：
#   * `run_mode` 是唯一真值源；`enabled` 只是它的派生镜像（enabled = running）。
#   * 任何模块**不得**直接读 `.enabled` 做判断，一律用下面的访问器；
#     写法（赋值）只能经 `enabled_of_run_mode()`。
#   * 新增运行状态必须先在此登记，再动其它代码。
RUN_MODE_RUNNING = "running"
RUN_MODE_SEEDING = "seeding"
RUN_MODE_STOPPED = "stopped"
RUN_MODES: Tuple[str, ...] = (RUN_MODE_RUNNING, RUN_MODE_SEEDING, RUN_MODE_STOPPED)


def normalize_run_mode(mode: Any, enabled: Any = None) -> str:
    """规整运行状态到三态之一；非法/缺失时按 `enabled` 回退（默认 running）。"""
    text = str(mode or "").strip().lower()
    if text in RUN_MODES:
        return text
    if enabled is None:
        return RUN_MODE_RUNNING
    return RUN_MODE_RUNNING if bool(enabled) else RUN_MODE_STOPPED


def enabled_of_run_mode(mode: Any, enabled: Any = None) -> bool:
    """`enabled` 的唯一算法：只有「运行中」才算 enabled。"""
    return normalize_run_mode(mode, enabled) == RUN_MODE_RUNNING


def run_mode_of(task: Any) -> str:
    """读任务的运行状态（历史配置缺 run_mode 时按 enabled 回退）。"""
    return normalize_run_mode(
        getattr(task, "run_mode", "") or "",
        getattr(task, "enabled", True),
    )


def task_is_participating(task: Any) -> bool:
    """任务是否参与调度域（running 或 seeding；= 未被用户停止）。"""
    return run_mode_of(task) != RUN_MODE_STOPPED


def task_is_running(task: Any) -> bool:
    """任务是否「运行中」（会跑刷流/补种/清理流程）。"""
    return run_mode_of(task) == RUN_MODE_RUNNING


def task_is_seeding_only(task: Any) -> bool:
    """任务是否「只做种」（停调度但仍纳管/盯站）。"""
    return run_mode_of(task) == RUN_MODE_SEEDING


def task_watches_site(task: Any) -> bool:
    """任务是否应参与站点观测（running + seeding 都要盯站，只有 stopped 不盯）。"""
    return run_mode_of(task) != RUN_MODE_STOPPED
