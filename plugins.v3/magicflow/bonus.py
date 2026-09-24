"""
MagicFlow 魔力评分引擎

根据站点魔力公式计算每个种子的魔力产出效率，
用于选种决策和删种决策。

魔力公式（HDFans/NexusPHP）：
    A = Σ((1 - 10^(-Ti/T0)) × Si × (1 + √2 × 10^(-(Ni-1)/(N0-1))) × Wi)
    B = B0 × 2/π × arctan(A/L)

参数：
    Ti  - 种子生存时间（周）
    T0  - 生存时间参数，固定 5
    Si  - 种子大小（GB）
    Ni  - 当前做种人数
    N0  - 做种人数参数，固定 7
    Wi  - 权重（普通=1，零魔=0.2）
    B0  - 小时魔力上限，固定 100
    L   - 曲线参数，固定 300
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 魔力公式参数
# ============================================================

@dataclass
class BonusParams:
    """魔力公式（NexusPHP 标准式）可调参数。

    不同 NexusPHP 站点的公式常数可能不同，通过本对象覆盖；
    默认值等价于 NexusPHP 标准公式（HDFans 等站点即用此默认）。
    """
    t0: float = 5.0            # 生存时间参数（周）
    n0: int = 7                # 做种人数参数
    b0: float = 100.0          # 每小时魔力上限
    l: float = 300.0           # 曲线参数
    zero_weight: float = 0.2   # 零魔种子权重 Wi
    normal_weight: float = 1.0 # 普通种子权重 Wi
    official_coef: float = 0.0 # 官种加成系数（官种单独算 A 后乘以此系数）
    harem_coef: float = 0.0    # 后宫加成系数（后宫时魔之和 × 此系数）
    per_torrent_flat: float = 0.0  # 每个做种种子的固定时魔（NexusPHP「做种数 × 每种子」低保）
    seeding_count_cap: int = 200   # 上述固定项计入的做种数上限

    @staticmethod
    def normalized(params: Optional["BonusParams"] = None) -> "BonusParams":
        """把 None 归一化为默认参数，避免每个调用点重复判空。"""
        return params if isinstance(params, BonusParams) else DEFAULT_PARAMS

    def merged(self, **overrides: Any) -> "BonusParams":
        """返回叠加了非空覆盖值的新参数对象（不修改自身）。"""
        data = {
            "t0": self.t0,
            "n0": self.n0,
            "b0": self.b0,
            "l": self.l,
            "zero_weight": self.zero_weight,
            "normal_weight": self.normal_weight,
            "official_coef": self.official_coef,
            "harem_coef": self.harem_coef,
            "per_torrent_flat": self.per_torrent_flat,
            "seeding_count_cap": self.seeding_count_cap,
        }
        for key, value in overrides.items():
            if value is not None and key in data:
                data[key] = value
        return BonusParams(**data)


DEFAULT_PARAMS = BonusParams()

# 兼容旧引用的模块级常量（等价于 DEFAULT_PARAMS）
T0 = DEFAULT_PARAMS.t0
N0 = DEFAULT_PARAMS.n0
B0 = DEFAULT_PARAMS.b0
L = DEFAULT_PARAMS.l
SQRT2 = math.sqrt(2)


@dataclass
class TorrentBonusInfo:
    """单个种子的魔力产出信息。"""
    hash: str
    title: str
    size_gb: float              # 种子大小（GB）
    seeders: int                # 当前做种人数
    leechers: int               # 当前下载人数
    age_weeks: float            # 生存时间（周）
    volume_factor: float        # 体积因子（免费=0.5，普通=1.0）
    is_zero_bonus: bool         # 是否零魔
    is_free: bool               # 是否免费
    is_double_free: bool        # 是否双倍
    hit_and_run: bool           # 是否 H&R
    is_official: bool = False   # 是否官种（有额外加成）

    # 计算结果
    time_factor: float = 0.0    # 时间因子 (1 - 10^(-Ti/5))
    people_factor: float = 0.0  # 人数因子 (1 + √2 × 10^(-(Ni-1)/6))
    weight: float = 1.0         # 权重（普通=1，零魔=0.2）
    bonus_score: float = 0.0    # 魔力产出评分（相对值，未归一化）
    bonus_per_hour: float = 0.0 # 估算每小时魔力产出

    # 附加信息
    pubdate: Optional[str] = None  # 发布时间
    page_url: Optional[str] = None # 种子页面 URL


@dataclass
class RankedCandidate:
    """魔力排序后的候选种子。"""
    torrent: TorrentBonusInfo
    rank: int                   # 魔力排名（1=最高）
    score: float                # 综合魔力评分
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    recommendation: str = "keep"  # "keep" | "consider_adding" | "low_priority"


@dataclass
class DeletionCandidate:
    """待删除候选。"""
    torrent: TorrentBonusInfo
    reason: str                 # 删除原因
    priority: int               # 删除优先级（数字越大越优先删除）


@dataclass
class DeletionResult:
    """删种决策结果。"""
    to_delete: List[DeletionCandidate]  # 待删除列表（已排序）
    to_keep: List[TorrentBonusInfo]     # 保留列表
    total_bonus_before: float           # 删除前总魔力产出
    total_bonus_after: float            # 删除后总魔力产出
    estimated_bonus_gain: float         # 预计魔力产出提升


@dataclass
class MagicPolicy:
    """魔力管家策略配置。"""
    # 魔力阈值
    min_bonus_per_hour: float = 0.0     # 每小时最低魔力产出阈值
    bonus_protect_threshold: float = float('inf')  # 魔力保护阈值（超过此值不删种）
    min_bonus_to_keep: float = 0.0      # 最低魔力保留值（低于此值停止删种）

    # 做种配置
    max_keep_torrents: Optional[int] = 50   # 最多保留种子数（None=不限，由保种体积决定）
    min_seed_time_hours: float = 0.0    # 最低做种时间（小时）

    # 评分权重（用于综合魔力评分）
    weight_time_factor: float = 1.0     # 时间因子权重
    weight_people_factor: float = 1.0   # 人数因子权重
    weight_size: float = 0.5            # 大小因子权重
    weight_zero_penalty: float = 2.0    # 零魔惩罚乘数

    # 删种偏好
    prefer_delete_zero_bonus: bool = True   # 优先删除零魔种子
    prefer_delete_high_ratio: bool = False  # 优先删除高分享率种子（与 BrushFlow 相反）
    prefer_delete_large: bool = False       # 优先删除大文件


def calc_time_factor(age_weeks: float, params: Optional[BonusParams] = None) -> float:
    """
    计算时间因子。

    公式: time_factor = 1 - 10^(-Ti/T0)

    特性（默认 T0=5）：
        - Ti=0 时，time_factor = 0
        - Ti=5 时，time_factor ≈ 0.63
        - Ti=10 时，time_factor ≈ 0.90
        - Ti→∞ 时，time_factor → 1

    Args:
        age_weeks: 种子生存时间（周）
        params: 公式参数，None 用默认值

    Returns:
        时间因子 (0 ~ 1)
    """
    p = BonusParams.normalized(params)
    if age_weeks <= 0:
        return 0.0
    return 1 - math.pow(10, -age_weeks / p.t0)


def calc_people_factor(seeders: int, params: Optional[BonusParams] = None) -> float:
    """
    计算人数因子。

    公式: people_factor = 1 + √2 × 10^(-(Ni-1)/(N0-1))

    特性（默认 N0=7）：
        - Ni=1 时，people_factor ≈ 1 + 1.414 ≈ 2.414（最高）
        - Ni=7 时，people_factor ≈ 1 + 0.236 ≈ 1.236
        - Ni=100 时，people_factor ≈ 1 + 0.0015 ≈ 1.002（最低）

    Args:
        seeders: 当前做种人数
        params: 公式参数，None 用默认值

    Returns:
        人数因子 (1 ~ 2.414)
    """
    p = BonusParams.normalized(params)
    if seeders <= 0:
        return 1.0
    return 1 + SQRT2 * math.pow(10, -(seeders - 1) / (p.n0 - 1))


def calc_weight(is_zero_bonus: bool, params: Optional[BonusParams] = None) -> float:
    """
    计算种子权重。

    Args:
        is_zero_bonus: 是否为零魔种子
        params: 公式参数，None 用默认值

    Returns:
        权重（默认：普通=1.0，零魔=0.2）
    """
    p = BonusParams.normalized(params)
    return p.zero_weight if is_zero_bonus else p.normal_weight


def calc_bonus_score(
    size_gb: float,
    seeders: int,
    age_weeks: float,
    is_zero_bonus: bool = False,
    params: Optional[BonusParams] = None,
) -> float:
    """
    计算种子魔力产出评分（相对值，未归一化）。

    公式: bonus_score = time_factor × Si × people_factor × Wi

    Args:
        size_gb: 种子大小（GB）
        seeders: 当前做种人数
        age_weeks: 生存时间（周）
        is_zero_bonus: 是否零魔

    Returns:
        魔力产出评分（相对值）
    """
    time_factor = calc_time_factor(age_weeks, params)
    people_factor = calc_people_factor(seeders, params)
    weight = calc_weight(is_zero_bonus, params)

    return time_factor * size_gb * people_factor * weight


def calc_bonus_per_hour(
    size_gb: float,
    seeders: int,
    age_weeks: float,
    is_zero_bonus: bool = False,
    params: Optional[BonusParams] = None,
) -> float:
    """
    估算每小时魔力产出。

    使用简化公式估算：B ≈ B0 × 2/π × arctan(A/L)
    其中 A = time_factor × Si × people_factor × Wi

    Args:
        size_gb: 种子大小（GB）
        seeders: 当前做种人数
        age_weeks: 生存时间（周）
        is_zero_bonus: 是否零魔

    Returns:
        估算每小时魔力产出
    """
    p = BonusParams.normalized(params)
    a = calc_bonus_score(size_gb, seeders, age_weeks, is_zero_bonus, params=p)
    # 魔力值曲线
    bonus = p.b0 * 2 / math.pi * math.atan(a / p.l)
    return bonus


def calc_aggregate_bonus_per_hour(
    torrents: List["TorrentBonusInfo"],
    params: Optional[BonusParams] = None,
    official_coef: Optional[float] = None,
    harem_hourly: float = 0.0,
    harem_coef: Optional[float] = None,
    seeding_count: int = 0,
) -> float:
    """站点口径的「每小时合计魔力」。

    站点公式对**合计 A** 只取一次 arctan，而不是对每个种子分别 arctan 再相加：
        B = B0 * 2/π * arctan(A_total / L)
    官方/后宫加成按站点规则分别计算：
        合计 = 基础 + 官种(仅官种 A 算一次, ×official_coef) + 后宫(harem_hourly × harem_coef)

    Args:
        torrents: 做种列表（TorrentBonusInfo）
        params: 公式参数
        official_coef / harem_coef: 覆盖系数（None 用 params 里的值）
        harem_hourly: 后宫成员时魔之和（外部提供，无则 0）

    Returns:
        每小时合计魔力
    """
    return aggregate_breakdown(
        torrents, params,
        official_coef=official_coef,
        harem_hourly=harem_hourly,
        harem_coef=harem_coef,
        seeding_count=seeding_count,
    )["total"]


def aggregate_breakdown(
    torrents: List["TorrentBonusInfo"],
    params: Optional[BonusParams] = None,
    official_coef: Optional[float] = None,
    harem_hourly: float = 0.0,
    harem_coef: Optional[float] = None,
    seeding_count: int = 0,
) -> Dict[str, float]:
    """站点口径合计魔力，并返回中间量（供「魔力计算」页展示推导链）。

    返回 dict：
        a_total / a_official   合计 A、官种 A（该项只算一次 arctan）
        b_base / b_flat / b_official / b_harem  三段拆分
        total                  每小时合计魔力
    """
    p = BonusParams.normalized(params)
    oc = p.official_coef if official_coef is None else official_coef
    hc = p.harem_coef if harem_coef is None else harem_coef
    a_total = 0.0
    a_official = 0.0
    for t in torrents or []:
        wi = t.weight if t.weight else calc_weight(t.is_zero_bonus, p)
        a_i = calc_time_factor(t.age_weeks, p) * t.size_gb * calc_people_factor(t.seeders, p) * wi
        a_total += a_i
        if getattr(t, "is_official", False):
            a_official += a_i
    b_base = p.b0 * 2 / math.pi * math.atan(a_total / p.l)
    b_official = (p.b0 * 2 / math.pi * math.atan(a_official / p.l)) * oc if oc else 0.0
    b_harem = (harem_hourly or 0.0) * hc if hc else 0.0
    # NexusPHP「做种固定奖励」：每种子 × per_torrent_flat（做种数封顶）；与公式 B 相加构成总时魔。
    n_flat = min(int(seeding_count or 0), int(p.seeding_count_cap or 0)) if p.seeding_count_cap else int(seeding_count or 0)
    b_flat = p.per_torrent_flat * max(n_flat, 0)
    return {
        "a_total": a_total,
        "a_official": a_official,
        "b_base": b_base,
        "b_flat": b_flat,
        "b_official": b_official,
        "b_harem": b_harem,
        "total": b_base + b_flat + b_official + b_harem,
    }


DEFAULT_CANDIDATE_REF_WEEKS = 4.0


def calc_candidate_bonus_per_hour(
    size_gb: float,
    seeders: int,
    age_weeks: float,
    is_zero_bonus: bool = False,
    ref_weeks: float = DEFAULT_CANDIDATE_REF_WEEKS,
    params: Optional[BonusParams] = None,
) -> float:
    """候选种子「预计魔力/时」。

    站点浏览（browse）只能拿到最新种子，实际年龄 Ti≈0，
    直接代入公式恒为 ~0/h → 排序失去意义。
    这里把年龄下限抬到 ref_weeks（默认 4 周），用「稳定期产出」
    给候选排序，体现大小 / 做种人数 / 权重差异。
    """
    eff = max(float(age_weeks or 0.0), float(ref_weeks or 0.0))
    return calc_bonus_per_hour(size_gb, seeders, eff, is_zero_bonus, params)


def calc_torrent_bonus(
    hash: str,
    title: str,
    size_gb: float,
    seeders: int,
    leechers: int = 0,
    age_weeks: float = 0.0,
    volume_factor: float = 1.0,
    is_zero_bonus: bool = False,
    is_free: bool = False,
    is_double_free: bool = False,
    hit_and_run: bool = False,
    pubdate: Optional[str] = None,
    page_url: Optional[str] = None,
    params: Optional[BonusParams] = None,
) -> TorrentBonusInfo:
    """
    计算单个种子的完整魔力产出信息。

    Args:
        hash: 种子 hash
        title: 种子标题
        size_gb: 种子大小（GB）
        seeders: 当前做种人数
        leechers: 当前下载人数
        age_weeks: 生存时间（周）
        volume_factor: 体积因子（免费=0.5，普通=1.0）
        is_zero_bonus: 是否零魔
        is_free: 是否免费
        is_double_free: 是否双倍上传
        hit_and_run: 是否 H&R
        pubdate: 发布时间
        page_url: 种子页面 URL

    Returns:
        TorrentBonusInfo: 包含完整魔力信息的对象
    """
    time_factor = calc_time_factor(age_weeks, params)
    people_factor = calc_people_factor(seeders, params)
    weight = calc_weight(is_zero_bonus, params)
    bonus_score = calc_bonus_score(size_gb, seeders, age_weeks, is_zero_bonus, params)
    bonus_per_hour = calc_bonus_per_hour(size_gb, seeders, age_weeks, is_zero_bonus, params)

    return TorrentBonusInfo(
        hash=hash,
        title=title,
        size_gb=size_gb,
        seeders=seeders,
        leechers=leechers,
        age_weeks=age_weeks,
        volume_factor=volume_factor,
        is_zero_bonus=is_zero_bonus,
        is_free=is_free,
        is_double_free=is_double_free,
        hit_and_run=hit_and_run,
        time_factor=time_factor,
        people_factor=people_factor,
        weight=weight,
        bonus_score=bonus_score,
        bonus_per_hour=bonus_per_hour,
        pubdate=pubdate,
        page_url=page_url,
    )


def rank_candidates(
    torrents: List[TorrentBonusInfo],
    policy: MagicPolicy,
) -> List[RankedCandidate]:
    """
    按魔力产出对候选种子排序。

    排序逻辑（与 BrushFlow 相反）：
        1. 魔力产出高的优先保留
        2. 做种人数少的优先保留
        3. 做种时间长的优先保留
        4. 零魔种子降低优先级

    Args:
        torrents: 候选种子列表
        policy: 魔力策略配置

    Returns:
        按魔力产出排序的结果
    """
    if not torrents:
        return []

    # 计算综合魔力评分
    scored_torrents = []
    for t in torrents:
        # 基础魔力评分
        score = t.bonus_score

        # 零魔惩罚
        if t.is_zero_bonus:
            score *= (1.0 / policy.weight_zero_penalty)

        # 大小加成（魔力与大小正相关，但非线性）
        size_score = math.log1p(t.size_gb) * policy.weight_size
        score += size_score

        scored_torrents.append((t, score))

    # 按魔力评分降序排序
    scored_torrents.sort(key=lambda x: x[1], reverse=True)

    # 构建排名结果
    ranked = []
    for rank, (torrent, score) in enumerate(scored_torrents, 1):
        # 决定推荐操作
        if torrent.is_zero_bonus and policy.prefer_delete_zero_bonus:
            recommendation = "low_priority"
        elif score < policy.min_bonus_per_hour:
            recommendation = "low_priority"
        else:
            recommendation = "keep"

        ranked.append(RankedCandidate(
            torrent=torrent,
            rank=rank,
            score=score,
            score_breakdown={
                "base_score": torrent.bonus_score,
                "time_factor": torrent.time_factor,
                "people_factor": torrent.people_factor,
                "weight": torrent.weight,
                "size_score": math.log1p(torrent.size_gb) * policy.weight_size,
            },
            recommendation=recommendation,
        ))

    return ranked


def decide_deletions(
    seeding_torrents: List[TorrentBonusInfo],
    policy: MagicPolicy,
    protected_hashes: Optional[set] = None,
) -> DeletionResult:
    """
    确定删除名单（魔力优先，与 BrushFlow 相反）。

    核心原则：
        - 只有「确实低效」的种子才删：零魔（Wi=0.2）、站内做种人数过多（魔力被打折）、
          魔力产出低于门槛、以及超出保留数量上限时按魔力从低到淘汰。
        - **绝不因为「没人下载 / 下载量为 0」而删除**：没人下完全不影响魔力，
          而「只有我们在挂」恰恰是人数因子最高（Ni=1 → 2.41）的优质种子。
        - ``min_seed_time_hours`` 是**保护期**：做种时间不足的种子不参与删种。
        - 手动保护（protected_hashes）与 H&R 种子永不删除。

    保护阈值语义：
        - 总魔力 >= ``bonus_protect_threshold`` → 本轮不删任何种子；
        - 总魔力 <= ``min_bonus_to_keep`` → 本轮不删任何种子（保底）。

    Args:
        seeding_torrents: 当前做种的种子列表
        policy: 魔力策略配置
        protected_hashes: 手动保护的种子 hash 集合

    Returns:
        DeletionResult: 删除决策结果
    """
    protected_hashes = protected_hashes or set()

    if not seeding_torrents:
        return DeletionResult(
            to_delete=[],
            to_keep=[],
            total_bonus_before=0.0,
            total_bonus_after=0.0,
            estimated_bonus_gain=0.0,
        )

    total_bonus_before = sum(t.bonus_per_hour for t in seeding_torrents)

    # 保护阈值：总魔力足够高，停手不动
    if total_bonus_before >= policy.bonus_protect_threshold:
        return DeletionResult(
            to_delete=[],
            to_keep=list(seeding_torrents),
            total_bonus_before=total_bonus_before,
            total_bonus_after=total_bonus_before,
            estimated_bonus_gain=0.0,
        )

    # 保底：总魔力太低时先不删，避免越删越少
    if total_bonus_before <= policy.min_bonus_to_keep:
        return DeletionResult(
            to_delete=[],
            to_keep=list(seeding_torrents),
            total_bonus_before=total_bonus_before,
            total_bonus_after=total_bonus_before,
            estimated_bonus_gain=0.0,
        )

    to_delete: List[DeletionCandidate] = []
    to_keep: List[TorrentBonusInfo] = []

    for torrent in seeding_torrents:
        # 手动保护 / H&R：绝不删除
        if torrent.hash in protected_hashes or torrent.hit_and_run:
            to_keep.append(torrent)
            continue

        # 保护期：做种时间不足的种子不参与删种
        if policy.min_seed_time_hours > 0 and torrent.age_weeks * 168 < policy.min_seed_time_hours:
            to_keep.append(torrent)
            continue

        reasons: List[str] = []
        priority = 0

        # 零魔种子（Wi=0.2）产出极低，优先淘汰
        if torrent.is_zero_bonus and policy.prefer_delete_zero_bonus:
            reasons.append("零魔种子（权重 0.2）")
            priority = max(priority, 100)

        # 站内做种人数过多 → 人数因子被摊销
        people_factor = calc_people_factor(torrent.seeders)
        if people_factor < 1.5:
            reasons.append(f"站内做种人数 {torrent.seeders} 过多，魔力被打折")
            priority = max(priority, 80)

        # 大文件效率低（可选）
        if policy.prefer_delete_large and torrent.size_gb > 20:
            reasons.append(f"大文件 {torrent.size_gb:.1f}GB，魔力效率低")
            priority = max(priority, 70)

        # 低于魔力门槛
        if torrent.bonus_per_hour < policy.min_bonus_per_hour:
            reasons.append(
                f"魔力 {torrent.bonus_per_hour:.3f}/h 低于门槛 {policy.min_bonus_per_hour:.3f}/h"
            )
            priority = max(priority, 60)

        if reasons:
            to_delete.append(
                DeletionCandidate(
                    torrent=torrent,
                    reason="；".join(reasons),
                    priority=priority,
                )
            )
        else:
            to_keep.append(torrent)

    # 数量上限：仅当显式设置了 max_keep_torrents 时才按数量淘汰
    if policy.max_keep_torrents is not None and len(to_keep) > policy.max_keep_torrents:
        to_keep.sort(key=lambda t: t.bonus_per_hour)
        overflow = len(to_keep) - policy.max_keep_torrents
        for torrent in to_keep[:overflow]:
            to_delete.append(
                DeletionCandidate(
                    torrent=torrent,
                    reason="超出保留数量上限，按魔力从低到淘汰",
                    priority=20,
                )
            )
        to_keep = to_keep[overflow:]

    # 按删除优先级降序排序（优先级高的先删）
    to_delete.sort(key=lambda c: c.priority, reverse=True)

    total_bonus_after = sum(t.bonus_per_hour for t in to_keep)
    return DeletionResult(
        to_delete=to_delete,
        to_keep=to_keep,
        total_bonus_before=total_bonus_before,
        total_bonus_after=total_bonus_after,
        estimated_bonus_gain=total_bonus_before - total_bonus_after,
    )

def preview_deletions(
    seeding_torrents: List[TorrentBonusInfo],
    policy: MagicPolicy,
    protected_hashes: Optional[set] = None,
) -> Dict[str, Any]:
    """
    预览删除决策（返回可序列化的 dict）。

    Args:
        seeding_torrents: 当前做种的种子列表
        policy: 魔力策略配置
        protected_hashes: 手动保护的种子 hash 集合

    Returns:
        可序列化的预览结果
    """
    result = decide_deletions(seeding_torrents, policy, protected_hashes)

    return {
        "total_torrents": len(seeding_torrents),
        "to_delete_count": len(result.to_delete),
        "to_keep_count": len(result.to_keep),
        "total_bonus_before": round(result.total_bonus_before, 4),
        "total_bonus_after": round(result.total_bonus_after, 4),
        "estimated_bonus_gain": round(result.estimated_bonus_gain, 4),
        "deletion_candidates": [
            {
                "hash": c.torrent.hash,
                "title": c.torrent.title,
                "size_gb": c.torrent.size_gb,
                "seeders": c.torrent.seeders,
                "age_weeks": round(c.torrent.age_weeks, 2),
                "bonus_per_hour": round(c.torrent.bonus_per_hour, 4),
                "is_zero_bonus": c.torrent.is_zero_bonus,
                "reason": c.reason,
                "priority": c.priority,
            }
            for c in result.to_delete
        ],
        "keep_candidates": [
            {
                "hash": t.hash,
                "title": t.title,
                "size_gb": t.size_gb,
                "seeders": t.seeders,
                "age_weeks": round(t.age_weeks, 2),
                "bonus_per_hour": round(t.bonus_per_hour, 4),
                "is_zero_bonus": t.is_zero_bonus,
            }
            for t in result.to_keep
        ],
    }


def calc_age_weeks(pubdate: Optional[str]) -> float:
    """
    从发布时间计算生存周数。

    Args:
        pubdate: 发布时间字符串（ISO 格式或站点特定格式）

    Returns:
        生存周数
    """
    if not pubdate:
        return 0.0

    try:
        from datetime import datetime, timezone
        # 尝试解析 ISO 格式
        dt = datetime.fromisoformat(pubdate.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600
        return max(0.0, age_hours / (7 * 24))
    except Exception:
        return 0.0


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MagicFlow 魔力评分引擎测试")
    print("=" * 60)

    # 测试用例：对比不同场景的魔力产出
    test_cases = [
        # (名称, 大小GB, 做种人数, 周数, 是否零魔)
        ("热门新种", 5, 100, 1, False),
        ("冷门老种", 5, 1, 10, False),
        ("普通种子", 5, 10, 3, False),
        ("零魔大文件", 20, 5, 5, True),
        ("零魔小文件", 1, 2, 8, True),
        ("无人老种", 10, 1, 20, False),
    ]

    print("\n魔力产出对比：")
    print("-" * 80)
    print(f"{'名称':<12} {'大小GB':>8} {'做种人':>8} {'周数':>8} {'零魔':>6} "
          f"{'时间因子':>10} {'人数因子':>10} {'魔力/h':>10}")
    print("-" * 80)

    for name, size, seeders, weeks, zero_bonus in test_cases:
        tf = calc_time_factor(weeks)
        pf = calc_people_factor(seeders)
        bonus = calc_bonus_per_hour(size, seeders, weeks, zero_bonus)

        print(f"{name:<12} {size:>8.1f} {seeders:>8} {weeks:>8.1f} "
              f"{'是' if zero_bonus else '否':>6} "
              f"{tf:>10.4f} {pf:>10.4f} {bonus:>10.4f}")

    print("-" * 80)

    # 测试排序
    print("\n候选排序测试（按魔力产出从高到低）：")
    torrents = [
        calc_torrent_bonus(
            hash=f"hash_{i}",
            title=f"种子_{i}",
            size_gb=size,
            seeders=seeders,
            age_weeks=weeks,
            is_zero_bonus=zero_bonus,
        )
        for i, (name, size, seeders, weeks, zero_bonus) in enumerate(test_cases)
    ]

    policy = MagicPolicy(
        min_bonus_per_hour=0.1,
        max_keep_torrents=3,
        prefer_delete_zero_bonus=True,
    )

    ranked = rank_candidates(torrents, policy)

    print("-" * 60)
    for rc in ranked:
        t = rc.torrent
        print(f"{rc.rank:>2}. {t.title:<12} 魔力={rc.score:>8.2f} "
              f"({t.bonus_per_hour:.4f}/h) [{rc.recommendation}]")
    print("-" * 60)

    # 测试删种决策
    print("\n删种决策测试：")
    result = decide_deletions(torrents, policy)
    print(f"总魔力产出: {result.total_bonus_before:.4f}/h")
    print(f"删除后魔力产出: {result.total_bonus_after:.4f}/h")
    print(f"预计魔力提升: {result.estimated_bonus_gain:.4f}/h")
    print(f"待删除: {len(result.to_delete)} 个")
    print(f"保留: {len(result.to_keep)} 个")

    print("\n删除详情：")
    for dc in result.to_delete:
        print(f"  - {dc.torrent.title}: {dc.reason} (优先级={dc.priority})")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
