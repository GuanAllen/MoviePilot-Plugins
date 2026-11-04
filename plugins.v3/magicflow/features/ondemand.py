# -*- coding: utf-8 -*-
"""魔流 · ondemand —— 点播口子（MODEL.md §1「权威来源 1 = Master 主动声明」）。

流程（与 MODEL.md §1 一致）：
  输入片名 / 豆瓣·TMDB·IMDB 链接
    → **识别唯一资源**（``recognize`` / 按 id 识别）
    → 搜索选源（**免费优先**，其次做种数）
    → 下载
    → **直接转「资源」**（不观察、不分拣）。

实现上复用既有链路：``_mp_search_title``（MP 自带搜索）取候选、``_od_fetch_torrent``
取 .torrent 字节（★ 19.10.0 起不再走跨站通道、也不判本地 PV 预算）、``downloader.add_torrent`` 落盘，最后只把「身份」这一步从自动扫描
换成手动指定 —— 下载中的 hash 记进 ``ondemand_pending``，一旦形成资源组
（``ResourceLedgerStore``）就 ``set_identity(资源)`` 并摘掉待办；在此期间分拣
（``_silent_triage``）**跳过**这些种，保证「不观察、不分拣」。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas import Response

from ..recommend import recognize
from ..persistence import OperationItem
from ..tags import (
    MEDIA_CAND_TTL, SUB_NEW, SUB_RESOURCE, STATE_ONDEMAND, STATE_SILENT,
    duty_assign, duty_of, fmt_iso_ts, identity_of, is_freeleech,
    media_act, media_cand_get, media_cand_hydrate, media_cand_put,
    media_fetch_torrent, media_grab, media_row_from_ti, media_totals,
    promo_factor, promo_label,
    retag, strip_media_prefix, tag_for,
)
from ..sitestore import slot_callbacks
from .. import shared                     # ★ 19.10.72 点播历史表的读改写锁（跨热重载）
from ..fingerprint import info_hash, load_torrent_entries, total_size
from ..sites.formula_fetch import fetch_torrent_promotion

# 运行时导入（只有 MoviePilot 环境有 app.sdk）：离线单测无 app 包 → 退回标准 logging
logger = logging.getLogger("magicflow")
try:  # noqa: BLE001
    from app.sdk.logging import logger as _mp_logger  # noqa: WPS433
    logger = _mp_logger
except Exception:  # noqa: BLE001
    pass

_DOUBAN_RE = re.compile(r"movie\.douban\.com/subject/(\d+)")
_TMDB_RE = re.compile(r"themoviedb\.org/(?:movie|tv)/(\d+)")
_IMDB_RE = re.compile(r"imdb\.com/title/(tt\d+)")

# 最近一次搜索结果的短时缓存（秒）：让「选某一条」不必把站点再搜一遍（原搜索要 60~75s）
_OD_CACHE_TTL = 600

# ★ 19.10.0 候选池：候选一旦返回给前端，**就必须在服务端活着**，直到用户点它。
#   键 = ``enclosure``，与关键词 / 站点集合 / 分页**全部无关** → 「搜完必能下」，落地零请求。
#   落点 = 缓存层（``TierCache``：Redis → 文件 → 内存，代码零分支）；丢了最多少抓一次，不影响正确性。
_OD_POOL_REGION = "odpool"   # 候选缓存分区（与音乐 musiccand 分开，互不串味）
# TTL 已统一到 tags.MEDIA_CAND_TTL（原 _OD_PICK_TTL=7200：人的决策时间，先比体积、比做种）

# ★ 17.1.1：``/agent/ondemand/add`` 找不到 pick 时的**续页上限**（搜第 0..N-1 页）。
#   根因：MP ``search_by_title(page=)`` 一次只给一页，pick 排在**第 2+ 页**时原来永远命中不了
#   （``/agent/ondemand/search`` 翻页看得到、add 却说「候选未命中」）。逐页搜、命中即停，有界。
_OD_ADD_MAX_PAGES = 3

# ★ 19.11.0：``/ondemand/batch`` 一次最多点几条。
#   上限不是性能考虑（落种很快），是**人的手误**：全选 20 条再点错一次就是几十 GB
#   计流量下载 + 一堆 H&R 义务。真要更多，搜准一点再点，别一次全勾。
_OD_BATCH_MAX = 30


#: ★ 17.2.0 直连加种：促销状态 → 下载计费系数（真值源 = ``sites/formula_fetch.parse_torrent_promotion`` 的词表）。
#  ``unknown``（页面拿不到/模板变了）**按全额计**：宁可把免费当收费记账，也不把收费当免费白嫖。
_OD_PROMO_DV = {"free": 0.0, "2xfree": 0.0, "twoup": 1.0, "none": 1.0, "unknown": 1.0}


def _od_price(row: Dict[str, Any]) -> float:
    """候选行的**单价系数**（= 下载系数 dvf：免费 0 / 五折 0.5 / 全额 1）—— 排序首要键。

    ★ 19.11.14：原来排序首选 ``is_freeleech(dv)`` 的**布尔**，于是 50% / 30% / 全额
    三者完全等价，「打折」在决策里等于不存在。改用系数本身：免费(0) < 三折(0.3) <
    五折(0.5) < 全额(1)，**是布尔口径的单调扩展**（免费仍第一，只是档位不再被抹平）。

    为什么不用「实扣体积」当排序键：实扣 = 体积 × 系数，按它升序会让 500MB 全额
    排在 60GB 全额前面（更省钱但画质崩），而点播最后是要看的。实扣体积照常**可见**
    （``_od_cost`` / 行内 ``counted_gb``），由人来权衡。
    系数拿不到 → 按全额计（与 ``tagspec.is_freeleech`` 同口径）。
    """
    try:
        return max(0.0, promo_factor(row.get("downloadvolumefactor")))
    except (TypeError, ValueError):
        return 1.0


def _od_cost(row: Dict[str, Any]) -> float:
    """候选行的**计费体积**（GB）= 体积 × 下载系数，即真正扣流量的量。

    用途：**展示与记账**（候选行的「实扣 X GB」、干跑 plan 的 ``counted_gb``）。
    不参与排序 —— 排序用 ``_od_price``（单价），理由见那里。
    """
    try:
        size = float(row.get("size") or 0.0)
    except (TypeError, ValueError):
        size = 0.0
    if size > 0:
        # 先按 size×dv 现算（9 位小数留精度）：候选行里的 ``counted_gb`` 只保留 2 位 GB，
        # 小体积会被舍成 0.0，跟「真免费」撞成同一档；9 位同时吃掉浮点表示误差。
        return max(0.0, round(size / 1e9 * promo_factor(row.get("downloadvolumefactor")), 9))
    try:
        return max(0.0, float(row.get("counted_gb") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _od_promo_of(row: Dict[str, Any]) -> str:
    """候选行的促销人话；行里没带 ``promo`` 的就地算（老缓存 / 别的构造路径）。"""
    label = str(row.get("promo") or "").strip()
    if label:
        return label
    return promo_label(promo_factor(row.get("downloadvolumefactor")),
                       promo_factor(row.get("uploadvolumefactor")))


def _od_promo_dv(promotion: Any, raw: Any = "") -> float:
    """促销 → ``downloadvolumefactor``（``partial`` 从原文括号里的 ``N%`` 反解，解不出按全额）。"""
    p = str(promotion or "").strip().lower()
    if p in _OD_PROMO_DV:
        return _OD_PROMO_DV[p]
    if p == "partial":
        m = re.search(r"(\d{1,3})\s*%", str(raw or ""))
        if m:
            try:
                return max(0.0, min(1.0, float(m.group(1)) / 100.0))
            except Exception:  # noqa: BLE001
                return 1.0
    return 1.0


_OD_KEY = "ondemand_pending"
# 17.1.0: ondemand history = persisted record slot (mf_run table).
_OD_HIST_KEY = "ondemand_history"
_OD_HIST_KEEP = 500

# ★ 19.10.70：点播「整理入库」失败重试（治本）。
#   入库是**一次性**动作：那次 MP 识别失败（典型：MP 无外网 → TMDB ConnectTimeout），
#   种就永远停在「已转资源 · 未入库」，既不告警也不重试 —— 实测小猪佩奇 82ef219a
#   就这样把 52 集漏在下载目录（2026-11-01 手工补整理才进库）。
#   退避表 = 「第 n 次失败后再等多久」，末项即长期稳态；总跨度 ≈ 2 天，覆盖断网类故障。
_OD_IMPORT_BACKOFF = (300, 900, 1800, 3600, 7200, 21600, 21600)
_OD_IMPORT_MAX_TRY = 12
# 两轮补整理的最小间隔（秒）：Check 可能 30~60s 一轮，不必每轮都去刷 MP
_OD_IMPORT_ROUND_MIN = 600

# ★ 19.11.4：合法文件特征码（与 assets._FP_OK 同口径：sha1 十六进制 32~64 位）。
#   资源组建组只认它；没有它 ``group_of`` 恒空 → 点播结算会卡死（见 ``_ondemand_fp_ensure``）。
_OD_FP_OK = re.compile(r"^[0-9a-f]{32,64}$")

# ───────────────────────────── 片名相关性（★ 19.11.6）─────────────────────────────
# 现场（2026-11-02，Master 报「点播搜欢迎来到龙餐馆全是别的剧」）：
#   1. 正片名是《欢迎来龙餐馆》（TMDB 1391021），输入多打一个「到」→ ``recognize`` 认不出；
#   2. 认不出就退回**原串**去搜站点，站点按「欢迎来到」前缀命中一堆《IT 欢迎来到德里镇》；
#   3. ``_ondemand_pick`` 只按「免费 → 做种数 → 体积」排，**完全不看是不是同一部片** →
#      自动选中 53GB 的《IT 欢迎来到德里镇》，点一下「下载」就下错剧。
# 三条规矩（顺序即优先级）：
#   ① 认不出先降级再认（去虚词 / 取尾词），命中后必须过相似度闸门；
#   ② 候选按「是否真的沾这部片」分级，粗筛噪音沉底并打 ``rel=0``；
#   ③ **没有强相关就绝不自动选源** —— 候选照给（人来判断），但机器不替你下。
_OD_FUZZY_MIN = 0.60          # 降级认出来的片名与原输入的相似度下限
_OD_CN_NOISE = "来到去了的之与和及是在有为把被从对就都还又很这那"
#   英文停用词 + 「标题里到处都是、但区分不了片」的词（welcome/to 正是这次踩的坑）
_OD_EN_NOISE = frozenset({
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "for", "with",
    "welcome", "movie", "film", "series", "season", "complete", "edition", "part",
})
# 技术词：判相关性前清掉，避免「2160p/WEB-DL」之类的字面命中
_OD_TECH_RE = re.compile(
    r"\b(?:s\d{1,2}(?:e\d{1,3})?|e\d{1,3}|ep\d{1,3}|\d{3,4}p|\d{2,3}fps|h\.?26[45]|hevc|avc|"
    r"x26[45]|aac|dts|ddp?\d?(?:\.\d)?|truehd|atmos|flac|web-?dl|webrip|blu-?ray|remux|"
    r"hdr\d*|dv|dovi|10bit|8bit|multi|complete)\b",
    re.I,
)


def _od_norm_text(s: Any) -> str:
    """比对用的归一：小写 + 清技术词 + 标点转空格。**只用于比对，不做任何改写。**"""
    t = str(s or "").lower()
    t = _OD_TECH_RE.sub(" ", t)
    t = re.sub(r"[\.\-_\[\]()（）【】:,;，；/|+*'\"!?]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _od_name_sim(a: Any, b: Any) -> float:
    """两个片名的相似度（0~1）。用于「降级认出来的这条到底是不是你说的那部」。"""
    x, y = str(a or "").strip(), str(b or "").strip()
    if not x or not y:
        return 0.0
    from difflib import SequenceMatcher  # noqa: WPS433

    return float(SequenceMatcher(None, x, y).ratio())


def _od_title_variants(kw: str) -> List[str]:
    """识别失败时的**降级片名**（去副标题 / 去「第X季」/ 去中文虚词 / 取尾部 3~4 字）。

    只治「多打一个字、少打一个字、带了季集后缀」这类手误；命中后还要 ``_OD_FUZZY_MIN`` 闸门。
    """
    base = str(kw or "").strip()
    out: List[str] = []

    def _add(v: str) -> None:
        v = str(v or "").strip(" ·-—:：")
        if len(v) >= 2 and v != base and v not in out:
            out.append(v)

    _add(re.split(r"[：:·\-—]", base)[0])                       # ① 去副标题
    core = re.sub(r"第\s*[0-9一二三四五六七八九十]+\s*[季部集期]", "", base)
    core = re.sub(r"[（(][^)）]*[)）]", "", core).strip()
    _add("".join(ch for ch in core if ch not in _OD_CN_NOISE))   # ② 去虚词：欢迎来到龙餐馆→欢迎龙餐馆
    for n in (4, 3):                                            # ③ 尾词：龙餐馆
        if len(core) > n:
            _add(core[-n:])
    return out


def _od_target_names(media: Any) -> List[str]:
    """识别结果 → 别名表（中文/英文/港台/原名 + ``names``）。识别不到 → ``[]``（= 没有身份）。"""
    names: List[str] = []
    if media is None:
        return names
    for field in ("title", "en_title", "hk_title", "tw_title", "sg_title",
                  "original_title", "original_name"):
        try:
            v = str(getattr(media, field, "") or "").strip()
        except Exception:  # noqa: BLE001
            v = ""
        if v and v not in names:
            names.append(v)
    try:
        for n in (getattr(media, "names", None) or []):
            n = str(n or "").strip()
            if n and n not in names:
                names.append(n)
    except Exception:  # noqa: BLE001
        pass
    return names


def _od_profile(names: List[str]) -> Tuple[List[str], List[Set[str]]]:
    """别名表 → (中文全名列表, 英文特征词组列表)。

    英文**按名字分组**而不是并成一个大集合：一部片常有 en_title / original_title / 各种译名，
    并集要求「所有名字的所有词都命中」等于永远不命中；按组比才是「任一名对得上就算」。
    组内先剔掉停用词与短词（``welcome`` / ``to`` / ``it`` 这类词区分不了片）。
    """
    cn: List[str] = []
    en: List[Set[str]] = []
    for n in names or []:
        if re.search(r"[\u4e00-\u9fff]", n):
            if n not in cn:
                cn.append(n)
        else:
            toks = {w for w in _od_norm_text(n).split()
                    if len(w) >= 3 and w not in _OD_EN_NOISE}
            # 单词别名（「Remedy」这种）区分度太低，容易被别的片名整词命中 → 至少 4 个字母才认
            if len(toks) == 1 and len(next(iter(toks))) < 4:
                continue
            if toks and toks not in en:
                en.append(toks)
    return cn, en


def _od_relevance(row: Dict[str, Any], cn: List[str], en: List[Set[str]]) -> int:
    """候选相关性：``2`` 强相关（含中文全名 / 某个英文名整组命中）· ``1`` 沾边 · ``0`` 不相干。

    只看 ``title`` + ``description``（站点原文），不猜、不翻译。
    """
    if not cn and not en:
        return 0
    raw = "%s %s" % (str(row.get("title") or ""), str(row.get("description") or ""))
    for n in cn:
        if n and n in raw:
            return 2
    if en:
        hay = set(_od_norm_text(raw).split())
        best = 0
        for group in en:
            hit = len(group & hay)
            if hit >= len(group):
                return 2
            if hit:
                best = 1
        return best
    return 0


class OnDemandMixin:
    """点播：手动指定资源 → 搜索选源 → 下载 → 直接转「资源」。"""

    # ------------------------------------------------------------ 待办账

    # ------------------------------------------------------------ 搜索结果短时缓存

    def _ondemand_cache_get(self, raw: str, sites: List[int]) -> Optional[List[Dict[str, Any]]]:
        c = getattr(self, "_od_last", None)
        if not c:
            return None
        if time.time() - float(c.get("ts") or 0) > _OD_CACHE_TTL:
            return None
        if str(c.get("raw") or "") != str(raw or ""):
            return None
        if sorted(int(x) for x in (c.get("sites") or [])) != sorted(int(x) for x in (sites or [])):
            return None
        return list(c.get("rows") or [])

    def _ondemand_cache_put(self, raw: str, sites: List[int], rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        self._od_last = {
            "raw": str(raw or ""), "sites": [int(x) for x in (sites or [])],
            "rows": list(rows), "ts": time.time(),
        }

    # ------------------------------------------------------------ 候选池（★ 19.10.0 → 19.10.11 统一到底座）

    def _od_pool_store(self, key: str, item: Dict[str, Any]) -> None:
        """候选池写入唯一出口 —— 委托 ``tags.media_cand_put``（脱敏 + 落缓存层）。"""
        media_cand_put(self, _OD_POOL_REGION, key, item, MEDIA_CAND_TTL)

    def _od_pool_put(self, rows: List[Dict[str, Any]], keyword: str = "") -> int:
        """把候选**逐条**放进缓存层（键 = ``enclosure``），返回入池条数。

        与 ``_od_last`` 的区别：那是**单槽 + 整批 + 绑关键词**（第二次搜索就覆盖第一次），
        这是**按候选索引** —— 所以「搜 3 个站、逐条比体积、2 小时后才点」也照样能落种。
        凭据脱敏 + 回填已收进 ``tags.media_cand_put / media_cand_hydrate``。
        """
        kw = str(keyword or "")[:120]
        now = time.time()
        n = 0
        for r in (rows or []):
            u = str((r or {}).get("enclosure") or "")
            if not u:
                continue
            item = dict(r)
            item["_kw"] = kw
            self._od_pool_store(u, item)
            n += 1
        if n:
            # 自证键：``TierCache`` 没有 scan，池里有几条从外面看不到 → 留一个索引（可随响应带出）
            self._od_pool_store("__last__", {"ts": now, "n": n, "kw": kw})
        return n

    def _od_pool_get(self, pick: str) -> Optional[Dict[str, Any]]:
        """按 ``enclosure`` 取候选；未命中 / 过期 → ``None``（**绝不在这里回退成重搜**）。"""
        u = str(pick or "").strip()
        if not u:
            return None
        row = media_cand_get(self, _OD_POOL_REGION, u, MEDIA_CAND_TTL)
        if not row or not row.get("enclosure"):
            return None
        return row

    def _od_pool_hydrate(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """按 site id 回填凭据 —— 委托 ``tags.media_cand_hydrate``。"""
        return media_cand_hydrate(self, row)

    # ------------------------------------------------------------ 站点闸（★ 19.10.0）

    def _od_site_gate(self, ids: List[int]) -> List[int]:
        """点播/直连路径的站点过滤：**只看「站点已暂停抓取」，不看本地 PV 预算**。

        为什么不再判 ``_pv_allow``：这条链路的请求是 **MP 发的**（``SearchChain`` / ``TorrentHelper``），
        插件自己一个都没发；判本地预算拦不住任何对站点的请求，只会「关掉自己」。
        更糟的是 ``_pv_spend`` 落的是 ``mf_site.pv_usage``，而 ``_pv_allow`` 读 ``today_total(site)``
        且 **不分 kind** —— 记这笔**估算账**等于拿假账挤占后台真实采集（``collect.py``）的预算。
        被跳过的站不静默丢弃：写进 ``self._od_skipped``，由调用方透到 ``sources[]`` 让用户看见。
        """
        blocked: Dict[int, str] = {}
        for i in (ids or []):
            why = self._pv_block_reason(i)
            if why:
                blocked[i] = why
        self._od_skipped = [
            {"site": i, "outcome": "pv_blocked", "error": f"暂停抓取至 {blocked[i]}"}
            for i in (ids or []) if blocked.get(i)
        ]
        return [i for i in (ids or []) if not blocked.get(i)]

    def _od_skipped_facts(self, page: int = 0) -> List[Dict[str, Any]]:
        """被站点闸跳过的站 → 统一 ``sources[]`` 条目（形状同 ``_od_source_fact``）。

        不静默丢弃：用户要能看到「这个站没搜，因为它被标了暂停至 HH:MM」，而不是「候选少了几个」。
        """
        return [{
            "source": "", "site": x.get("site"), "site_name": "",
            "page": int(page or 0), "can_continue": False,
            "outcome": "pv_blocked", "error": str(x.get("error") or ""),
            "note": "站点已暂停抓取，本次未检索",
        } for x in (getattr(self, "_od_skipped", None) or [])]

    def _ondemand_all(self) -> Dict[str, Dict[str, Any]]:
        try:
            rows = slot_callbacks(self, _OD_KEY)[0]() or {}
            return {str(k).lower(): dict(v or {}) for k, v in rows.items()}
        except Exception:  # noqa: BLE001
            return {}

    def _od_inflight_set(self) -> Set[str]:
        """★ 15.8.3（Master「下完之前别暂停」）：点播 in-flight hash 集。

        提供给 ``SilentGateMixin._silent_audit`` / ``_silent_enforce_pause`` 走单点过滤，
        避免 silent.py 跨域 self 调用（棘轮阻挡）。下完之后移出本集合，恢复静默闸管辖。
        """
        try:
            return {str(k).strip().lower() for k in (self._ondemand_all() or {})}
        except Exception:  # noqa: BLE001
            return set()

    def _ondemand_is_pending(self, h: str) -> bool:
        return str(h or "").lower() in self._ondemand_all()

    def _ondemand_mark(self, h: str, info: Dict[str, Any]) -> None:
        rows = self._ondemand_all()
        rows[str(h or "").lower()] = dict(info or {}, ts=time.time())
        try:
            slot_callbacks(self, _OD_KEY)[1](value=rows)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:待办落盘失败 {e}", "warning")

    def _ondemand_unmark(self, h: str) -> None:
        rows = self._ondemand_all()
        if rows.pop(str(h or "").lower(), None) is not None:
            try:
                slot_callbacks(self, _OD_KEY)[1](value=rows)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ 15.8.4 点播伪任务（__ondemand__）

    def _od_assign(self, hashes: Any, *, site: str = "", sub: str = "", reason: str = "") -> int:
        """★ 19.10.11：薄委托 → ``tags.duty_assign(kind="ondemand")``。

        音乐/点播是**同一条流水线**（搜→下→挂职务→入库），只差媒体 type ——
        挂职务的唯一实现已收归 ``tags.duty_assign``，差异全在 ``tags.MEDIA_KINDS``。
        本方法名保留（调用点与测试不动），仅作 ``kind="ondemand"`` 的别名。
        """
        from ..common import ONDEMAND_TASK_ID, ONDEMAND_TASK_NAME  # 惰性导入（离线测试桩只给这两个）
        return duty_assign(self, hashes, kind="ondemand",
                           task_id=ONDEMAND_TASK_ID, task_name=ONDEMAND_TASK_NAME,
                           site=site, sub=sub, reason=reason)

    def _od_release(self, hashes: Any, *, reason: str = "") -> int:
        """★ 15.8.4：点播结算（下完转资源）后，把种从 ``__ondemand__`` 释放回静默。

        退「点播」职务标签 + 清账本 ``taken_by/task`` → 回静默闸管辖（此后按资源身份入池 paused）。
        """
        from ..common import ONDEMAND_TASK_ID  # 惰性导入
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        hs = [str(h or "").strip().lower() for h in hs if str(h or "").strip()]
        if not hs:
            return 0
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        store = self._tag_state()
        fn = getattr(downloader, "replace_torrent_tags", None)
        snap = self._tag_all_torrents()
        n = 0
        _now = time.time()
        for h in hs:
            hh = str(h or "").strip().lower()
            _rec = store.get(hh) or {}
            if str(_rec.get("taken_by") or "") not in ("", ONDEMAND_TASK_ID):
                continue  # 已被别的宿主接管，不抢
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            _sub = str(_rec.get("sub") or "") or _i_sub or SUB_RESOURCE
            _site = str(_rec.get("site") or "") or _i_site or self._torrent_site_name(cur, "")
            new_tags = retag(cur, site=_site, state=STATE_SILENT, sub=_sub) \
                if cur else [tag_for(_site, STATE_SILENT, _sub)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {
                    "site": _site, "state": STATE_SILENT, "sub": _sub,
                    "taken_by": "", "task": "", "lease_until": 0,
                    "od_released_at": _now, "od_released_reason": str(reason or ""),
                })
            except Exception:  # noqa: BLE001
                pass
            n += 1
        if n:
            try:
                self._silent_pause_gate(hs)
            except Exception:  # noqa: BLE001
                pass
            self._log(f"点播:释放 __ondemand__ {n} 个（{reason or '结算'}）")
        return n

    def _ondemand_duty_reconcile(self) -> Dict[str, int]:
        """★ 15.8.4：点播「点播」职务对账（每 Check 轮一次，廉价）。

        ① pending 里未挂 ``__ondemand__`` 的 → 补挂（防漏）；
        ② 挂了 ``__ondemand__`` 但已不在 pending（已结算/被移除）的 → 释放回静默（防占）。
        """
        from ..common import ONDEMAND_TASK_ID  # 惰性导入
        pend = set((self._ondemand_all() or {}).keys())
        try:
            items = self._tag_state().items() or {}
        except Exception:  # noqa: BLE001
            return {"assigned": 0, "released": 0}
        # ★ 15.8.6：把**所有** pending 交给 ``_od_assign``——它按「账本已挂 **且** qB 职务标签
        #   在位」幂等过滤（治「加种抢先于 qB 登记」的漏标），本函数不再自带快照。
        to_assign = list(pend)
        to_release = [th for th, rec in items.items()
                      if str((rec or {}).get("taken_by") or "") == ONDEMAND_TASK_ID and th not in pend]
        a = self._od_assign(to_assign, reason="对账补挂") if to_assign else 0
        r = self._od_release(to_release, reason="对账释放") if to_release else 0
        return {"assigned": a, "released": r}

    # ------------------------------------------------------------ 第 1 步：识别

    @staticmethod
    def _ondemand_parse(query: str) -> Dict[str, str]:
        q = str(query or "").strip()
        out = {"query": q, "keyword": q, "doubanid": "", "tmdbid": "", "imdbid": ""}
        for pat, key in (
            (_DOUBAN_RE, "doubanid"), (_TMDB_RE, "tmdbid"), (_IMDB_RE, "imdbid"),
        ):
            m = pat.search(q)
            if m:
                out[key] = m.group(1)
                out["keyword"] = ""
        return out

    def _ondemand_media(self, q: Dict[str, str]) -> Optional[Any]:
        """识别唯一资源：片名走默认识别链（认不出→降级重试）；链接按 id 识别。"""
        kw = str(q.get("keyword") or "").strip()
        if kw:
            media = recognize(kw)
            if media is None:
                # ★ 19.11.6：多打/少打一个字（欢迎来到龙餐馆 → 欢迎来龙餐馆）不该整套流程陪着降级
                media = self._ondemand_media_fuzzy(kw)
            return media
        kwargs: Dict[str, Any] = {}
        if q.get("doubanid"):
            kwargs["doubanid"] = q["doubanid"]
        if q.get("tmdbid"):
            kwargs["tmdbid"] = q["tmdbid"]
        if q.get("imdbid"):
            kwargs["imdbid"] = q["imdbid"]
        if not kwargs:
            return None
        try:
            from app.chain.media import MediaChain  # noqa: WPS433
            return MediaChain().recognize_media(**kwargs)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:按 id 识别失败 {kwargs}: {e}", "warning")
            return None

    def _ondemand_media_fuzzy(self, kw: str) -> Optional[Any]:
        """★ 19.11.6：认不出片名时的**降级重试**（``_od_title_variants`` → 再认）。

        两级：先 ``recognize(变体)``；仍认不出就 ``search_medias`` 拿候选列表，挑「与原输入
        相似度最高」的那条 —— 只靠 ``recognize`` 会漏：短名（「龙餐馆」）在 TMDB 有两部相近的
        片子时它宁可不给答案，而列表里第一条正是《欢迎来龙餐馆》。

        命中不算数：``_od_name_sim(认出标题, 输入) >= _OD_FUZZY_MIN``。没有这道闸门，
        「龙餐馆」会把《金龙餐馆圣诞夜》也认进来 —— 那比认不出更坏。
        """
        for v in _od_title_variants(kw):
            cands: List[Any] = []
            try:
                media = recognize(v)
            except Exception:  # noqa: BLE001
                media = None
            if media is not None:
                cands = [media]
            else:
                cands = self._od_search_medias(v)
            best: Any = None
            best_sim = 0.0
            for c in cands:
                got = (str(getattr(c, "title", "") or "")
                       or str(getattr(c, "original_title", "") or "")
                       or str(getattr(c, "en_title", "") or ""))
                sim = _od_name_sim(got, kw)
                if sim > best_sim:
                    best, best_sim = c, sim
            if best is not None and best_sim >= _OD_FUZZY_MIN:
                self._log("点播:片名「%s」直接认不出 → 降级「%s」→《%s》(相似度 %.2f)"
                          % (kw, v, str(getattr(best, "title", "") or ""), best_sim))
                return best
            if cands:
                self._log("点播:降级「%s」认出 %d 条但与「%s」都对不上(最高 %.2f)，不采纳"
                          % (v, len(cands), kw, best_sim), "warning")
        return None

    @staticmethod
    def _od_search_medias(name: str) -> List[Any]:
        """按片名搜媒体（**不是**识别）：给降级识别兜底。任何异常 → 空列表。"""
        try:
            from app.sdk.media import MetaInfo  # noqa: WPS433
            from app.chain.media import MediaChain  # noqa: WPS433
            res = MediaChain().search_medias(MetaInfo(str(name)))
            return list(res or [])
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------ 第 2 步：搜索

    def _ondemand_sites(self, task: Any = None, site_ids: str = "") -> List[int]:
        """候选站点集合：显式 site_ids > **全部已配置站点**。

        ★ 2026-10-01（Master「点播入口一定要挂在任务下么」）：点播**不再依赖任务**。
        此前不选任务 = 「所有启用任务的站点」（下拉却写着「全部站点」，名不副实）；
        现在不勾站点 = **MP 里所有站点**，``task`` 只决定保存目录，不再限定搜索范围。

        :param task: 兼容旧签名；**不再**用于限定站点（只影响保存目录，见 ``_ondemand_default_save_path``）。
        """
        ids: List[int] = []
        for x in str(site_ids or "").replace("，", ",").split(","):
            try:
                _i = int(str(x).strip())
            except Exception:  # noqa: BLE001
                continue
            if _i and _i not in ids:
                ids.append(_i)
        if ids:
            return ids
        try:
            for it in self._list_sites() or []:
                _i = int((it or {}).get("id") or 0)
                if _i and _i not in ids:
                    ids.append(_i)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:列出站点失败: {e}", "warning")
        return ids

    def _ondemand_search(self, keyword: str, site_ids: List[int],
                         page: int = 0) -> List[Dict[str, Any]]:
        """搜候选（**不过滤免费**，点播要的是这个资源本身）。

        ★ 17.1.1：``page`` 透传给 MP ``search_by_title(page=)`` —— MP 一次只回一页，
        要多页由调用方续（见 ``_ondemand_find_pick``）。★ 19.10.0：每页候选逐条入池，且不再记 PV。
        """
        kw = str(keyword or "").strip()
        ids = [i for i in (site_ids or []) if i]
        if not kw or not ids:
            return []
        try:
            pg = max(0, int(page or 0))
        except (TypeError, ValueError):
            pg = 0
        allowed = self._od_site_gate(ids)
        if not allowed:
            self._log("点播:候选站点均处于「暂停抓取」，跳过检索", "warning")
            return []
        try:
            hits = self._mp_search_title(kw, allowed, page=pg)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:MP 搜索失败: {e}", "warning")
            hits = []
        rows: List[Dict[str, Any]] = []
        for ti in hits or []:
            r = self._od_row_from_ti(ti)
            if r:
                rows.append(r)
        # ★ 19.10.0：候选入池（键 = enclosure）—— 前端拿到列表后无论多久点，都能落种
        self._od_pool_put(rows, kw)
        self._log(f"点播:MP 搜索「{kw}」page={pg} {len(allowed)} 站 → 候选 {len(rows)} 条")
        return rows

    def _ondemand_find_pick(self, title: str, year: str, sites: List[int],
                            pick: str) -> List[Dict[str, Any]]:
        """★ 17.1.1：**逐页搜到 pick 命中为止**（有界），返回「到此为止已见过的候选」。

        根因（Master 2026-10-10 报）：``_ondemand_add`` 原来只搜 MP 的**第 1 页**，
        候选排在第 2+ 页时永远命中不了 → 「搜索翻页看得到、add 加不进去」（真缺口：能看不能下）。

        边界（别把站点搜爆）：
        - 每关键词最多 ``_OD_ADD_MAX_PAGES`` 页（第 0..N-1 页），命中即停（**不多搜一页**）；
        - 某页**空**（无结果 / 站点暂停抓取）→ 判为页尾，停止续页；
        - 第一个关键词有货就不再试「片名+年份」（与改前 `_ondemand_add` 的口径一致）。
        """
        want = str(pick or "").strip()
        acc: Dict[str, Dict[str, Any]] = {}
        keys = [str(title or "").strip()]
        if str(year or "").strip():
            keys.append("%s %s" % (keys[0], str(year).strip()))
        for kw in keys:
            if not kw:
                continue
            for pg in range(_OD_ADD_MAX_PAGES):
                # 异常不私吞（同改前：直接冒到 ``/agent/ondemand/add`` 的错误回报），
                # 且 ``_ondemand_search`` 内部已记「MP 搜索失败」日志 —— 这里不再重复记。
                rows = self._ondemand_search(kw, sites, page=pg) or []
                for r in rows:
                    acc[str(r.get("enclosure") or "")] = r
                if any(str(r.get("enclosure") or "") == want for r in rows):
                    return list(acc.values())
                if not rows:
                    break          # 页尾（或站点暂停抓取）→ 本关键词不再续页
            if acc:
                break              # 第一个关键词有货：不再试「片名+年份」
        return list(acc.values())

    # ------------------------------------------------------------ §3 搜索自描述（★ 15.9.0）

    @staticmethod
    def _od_row_from_ti(ti: Any) -> Optional[Dict[str, Any]]:
        """TorrentInfo（对象 / dict）→ 点播候选行（真值源 = MP 的 TorrentInfo）。

        ★ 19.10.11：本体搬到 ``tags.media_row_from_ti``（与音乐同源），这里只留薄委托。
        """
        return media_row_from_ti(ti)

    @staticmethod
    def _od_decode_source(source: str):
        """MP 续页令牌（``base64([site, keyword, search_id])``）→ ``(site:int, keyword:str)``（解不出 → ``(0, "")``）。"""
        try:
            from app.chain.search.manual import decode_source  # noqa: WPS433
            site, keyword, _sid = decode_source(str(source or ""))
            return (int(site) if str(site).isdigit() else 0), str(keyword or "")
        except Exception:  # noqa: BLE001
            return 0, ""

    @classmethod
    def _od_source_site(cls, source: str) -> int:
        """从 MP 续页令牌解出站点 id（解不出→0）。"""
        return cls._od_decode_source(source)[0]

    @classmethod
    def _od_source_fact(cls, raw: Any) -> Dict[str, Any]:
        """MP 单页分页来源事实 → 统一 ``sources[]`` 条目（§3.3）。**不平定义，只归一**。"""
        raw = raw if isinstance(raw, dict) else {}
        err = raw.get("error")
        err = str(err) if err else None
        if not err:
            outcome = "ok"
        elif "超时" in err or "timeout" in err.lower():
            outcome = "timeout"
        else:
            outcome = "error"
        tok = str(raw.get("source") or "")
        site: Any = cls._od_source_site(tok)
        if not site:
            site = None
        return {
            "source": tok,
            "site": site,
            "site_name": str(raw.get("site_name") or ""),
            "page": int(raw.get("page") or 0),
            "can_continue": bool(raw.get("can_continue")),
            "outcome": outcome,
            "error": err,
            "note": "",
        }

    async def _ondemand_search_sources(self, keyword: str, site_ids: List[int],
                                       page: int = 0, source: str = "") -> Dict[str, Any]:
        """★ 15.9.0 §3：点播候选 + **每站事实** —— **直接透传 MP 原生单页分页**。

        MP v3.1.2 自带 ``SearchChain().search_page_events(params=…)``（``app/chain/search/manual.py``）：

        - **客户端指定单页**（``page``），MP **不自留**分页进度；
        - 每个来源回 ``{source, site_name, page, can_continue, error}``，与我们的 ``sources[]`` 同构；
        - ``source`` 是**续页令牌**（回传它 + ``page=N+1`` 即续该站下一页；含 ``search_id`` 隔离本轮）；
        - 上限 ``MAX_SEARCH_PAGES=100``；复用 MP 的站点流控 / 别名回退 / 识别 / 过滤。

        我们**不做第二真值源**：类型判定 / 分页能力 / 别名 / 过滤全部听 MP。
        """
        kw = str(keyword or "").strip()
        pg = 0
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
            "keyword": kw, "page": pg, "source": src, "sites": ids,
            "sources": [], "candidates": [], "total_items": 0, "candidate_items": 0,
        }
        if not kw and not src:
            return out
        # 站点集合 + 站点闸（与 ``_ondemand_search`` 同源；续页只针对令牌里的那个站）
        target_ids = ids or self._ondemand_sites()
        pkw = kw
        if src:
            _s, _kw = self._od_decode_source(src)
            target_ids = [_s] if _s else []
            pkw = _kw or kw   # 续页：MP 的 ``_prepare_page`` 仍需 ``keyword`` 在场（随后会被令牌覆盖）
            out["keyword"] = pkw
        allowed = self._od_site_gate(target_ids)
        skipped = self._od_skipped_facts(pg)
        if not allowed:
            out["sources"] = skipped
            self._log("点播:搜索站点均处于「暂停抓取」，跳过", "warning")
            return out
        out["sites"] = allowed
        params: Dict[str, Any] = {"page": pg}
        if src:
            params["source"] = src
            params["keyword"] = pkw
        else:
            params["keyword"] = kw
            params["sites"] = allowed
        try:
            from app.chain.search import SearchChain  # noqa: WPS433
            chain = SearchChain()
            ev = getattr(chain, "search_page_events", None)
            if not callable(ev):
                raise RuntimeError("当前 MP 无 search_page_events（需 v3.1.2+）")
            facts: List[Dict[str, Any]] = []
            items: List[Any] = []
            # ★ 19.10.0：这里**不再记 PV**（请求是 MP 发的，且旧实现会把估算账写进共享池，
            #   反倒挤掉后台 collect.py 的真实预算）。逐站暂停抓取已在上面由 ``_od_site_gate`` 拦。
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
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:MP 分页搜索失败: {e}", "warning")
            raise
        out["sources"] = list(facts) + skipped
        rows: List[Dict[str, Any]] = []
        for it in items:
            ti = it.get("torrent_info") if isinstance(it, dict) else None
            if ti is None and isinstance(it, dict):
                ti = it
            r = self._od_row_from_ti(ti) if ti is not None else None
            if r:
                rows.append(r)
        out["candidates"] = sorted(rows, key=lambda r: (
            _od_price(r),
            -int(r.get("seeders", 0) or 0), -float(r.get("size", 0.0) or 0.0)))
        self._log(f"点播:MP 分页搜索「{kw or '(续页)'}」page={pg} → 来源 {len(facts)} / 候选 {len(rows)}")
        # ★ 17.1.1：本轮候选喂给「最近一次搜索」短时缓存 —— 让 /agent/ondemand/search →
        #   /agent/ondemand/add 真正衔接（add 命中即秒回，不再自己重搜一页 / 白烧 PV）。
        #   键 = 生效关键词（续页时取自令牌）+ 实际检索站点，与 add 的 ``_ondemand_cache_get`` 同口径。
        self._ondemand_cache_put(str(out.get("keyword") or ""), allowed, out["candidates"])
        # ★ 19.10.0：逐条入池（键 = enclosure）—— 这是「搜完必能下」的正解
        self._od_pool_put(out["candidates"], str(out.get("keyword") or ""))
        return out

    def _ondemand_pick(self, rows: List[Dict[str, Any]],
                       names: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """选源：**单价低**（下载系数：免费 0 / 三折 0.3 / 五折 0.5 / 全额 1）→ 做种多 → 体积大。

        ★ 19.11.14：首要键从「是否免费」的布尔换成**系数本身**。布尔下 50% 与 100%
        完全等价，「打折」在决策里等于不存在；换成系数是单调扩展（免费仍第一）。
        不用「实扣体积」当键：按它排会让 500MB 全额压过 60GB 全额，省钱但画质崩 ——
        点播是要看的。

        ★ 19.11.6：``names`` 是识别出来的片名/别名表，语义是**「机器知不知道这部片是谁」**：

        - ``names=None``：调用方不提供身份 → 旧行为（只按免费/做种/体积），仅供内部兼容调用；
        - ``names=[]``（认不出片名）：**绝不自动选源** —— 拿不到身份就没有「是不是同一部片」
          的判断依据，此时替用户选一条等于掷骰子（实测会选中《IT 欢迎来到德里镇》53GB）；
        - ``names=[...]``：只在**强相关**（``_od_relevance == 2``）的行里选；一条都不相关 → ``None``。

        注意：候选列表本身是**照常返回**的 —— 不自动选 ≠ 不给，人可以从列表里手点。
        """
        if not rows:
            return None
        if names is not None:
            cn, en = _od_profile(names)
            if not cn and not en:
                return None
            rows = [r for r in rows if _od_relevance(r, cn, en) >= 2]
            if not rows:
                return None

        def _k(r: Dict[str, Any]) -> tuple:
            # ★ 19.11.14：单价系数升序（取负给 max 用：免费 0 最强）→ 做种多 → 体积大
            return (-_od_price(r),
                    int(r.get("seeders", 0) or 0), float(r.get("size", 0.0) or 0.0))

        return max(rows, key=_k)

    def _ondemand_rank(self, rows: List[Dict[str, Any]], names: Optional[List[str]]) -> List[Dict[str, Any]]:
        """★ 19.11.6：候选排序 + 打标 —— 强相关在前，关键词粗筛的噪音沉底并标 ``rel=0``。

        只改**顺序与标记**，不删行：站点用的是各种译名/拼音，删了可能把真候选也删掉，
        所以把「判断权」交回给人（前端可按 ``rel`` 灰显），机器只用它来拒绝自动选源。
        """
        cn, en = _od_profile(names or [])
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            try:
                r["rel"] = _od_relevance(r, cn, en) if (cn or en) else 0
            except Exception:  # noqa: BLE001
                r["rel"] = 0
            out.append(r)
        return sorted(out, key=lambda r: (
            -int(r.get("rel") or 0),
            _od_price(r),
            -int(r.get("seeders", 0) or 0),
            -float(r.get("size", 0.0) or 0.0),
        ))

    @staticmethod
    def _od_no_pick_reason(rows: List[Dict[str, Any]], media: Any,
                           title: str, sites: List[int]) -> str:
        """没自动选源时**把原因说清楚** —— 「搜到一堆但都不沾边」和「压根没搜到」不是一回事。"""
        n = len(rows or [])
        if not n:
            return "没搜到任何候选（%d 个站点都没有）" % len(sites or [])
        if media is None:
            return ("没认出片名（TMDB 查不到《%s》），不替你自动选源：下面是站点按关键词的粗筛结果"
                    "（%d 条），可能完全不相关，确认是哪部再勾选" % (title, n))
        return ("站点里没有与《%s》匹配的资源（已搜 %d 站，回来 %d 条但都不沾边）；"
                "下面只是关键词粗筛结果，供人工确认" % (title, len(sites or []), n))

    # ------------------------------------------------------------ 第 3 步：下载

    def _ondemand_default_save_path(self) -> str:
        """未选任务（或任务没配保存目录）时的兜底目录：

        ① 插件设置「默认任务模板」的 ``save_path``；② 下载器（qB）全局 ``save_path``。
        （★ Master 报过：任务选「（全部站点）」时点下载 → 报「没填下载目录」。）
        """
        try:
            p = str((getattr(self, "_defaults", {}) or {}).get("save_path") or "").strip()
            if p:
                return p
        except Exception:  # noqa: BLE001
            pass
        try:
            res = self.get_downloader_prefs()
            data = getattr(res, "data", None) or {}
            p = str((data or {}).get("save_path") or "").strip()
            if p:
                return p
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _od_fetch_torrent(self, row: Dict[str, Any]) -> Any:
        """取 ``.torrent`` 字节 → 薄委托 ``tags.media_fetch_torrent``（★ 19.10.11 合一）。

        返回 ``(content, code, message)``；成功时 ``code``/``message`` 为 ``("", "")``。

        PV 口径（两边优点合并）：**记账必做、闸门只拦自动流** —— 点播是用户点名要下的，
        不因预算拦人，但请求打到站点上照样进账本。用户可读的错误仍逐条写日志（19.10.1）。
        """
        content, code, msg = media_fetch_torrent(self, row, pv_gate=False)
        if not content:
            _name = str((row or {}).get("site_name") or (row or {}).get("site") or "")
            logger.warning(f"魔流点播:取种失败 {_name}（{code}）—— {msg}")
        return content, code, msg

    # ------------------------------------------------- 识别结果贯穿（★ 19.11.2）

    @staticmethod
    def _media_identity(media: Any) -> Dict[str, str]:
        """把 MP 的 ``MediaInfo`` 压成三个可落盘的标量（空值一律 ``""``）。

        ``MediaSource`` 是 ``str`` 枚举 → 存 ``"themoviedb"`` 即可原样用回；
        ``MediaType`` 是普通枚举、值是中文（``"电视剧"``）→ 存中文，读时再还原成员。
        """
        out = {"media_id": "", "media_source": "", "media_type": ""}
        if media is None:
            return out
        try:
            out["media_id"] = str(getattr(media, "media_id", "") or "")
            _ms = getattr(media, "media_source", None)
            if _ms is not None:
                out["media_source"] = str(getattr(_ms, "value", _ms) or "")
            _mt = getattr(media, "type", None)
            if _mt is not None:
                out["media_type"] = str(getattr(_mt, "value", _mt) or "")
        except Exception:  # noqa: BLE001
            return {"media_id": "", "media_source": "", "media_type": ""}
        return out

    def _ondemand_stamp_media(self, rows: List[Dict[str, Any]], media: Any) -> None:
        """把已识别到的媒体身份**盖到每条候选行上**（原地改，纯增量字段）。

        盖在行上而不是加参数，是为了让**批量点播**也吃到：候选池里存的就是这些行，
        ``_ondemand_batch`` 只从池里取行、不经搜索，参数传法覆盖不到它。
        """
        ident = self._media_identity(media)
        if not ident["media_id"]:
            return
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            try:
                r.update(ident)
            except Exception:  # noqa: BLE001
                pass

    def _ondemand_media_index(self) -> Dict[str, Dict[str, str]]:
        """``hash → 下载时已识别的媒体身份``（只收台账里真落过 media_id 的行）。

        结算时建一次，供整轮整理复用 —— 别在循环里逐条读台账（那是整表读改写）。
        """
        idx: Dict[str, Dict[str, str]] = {}
        try:
            for r in self._ondemand_history_read():
                mid = str(r.get("media_id") or "")
                hh = str(r.get("hash") or "").lower()
                if mid and hh:
                    idx[hh] = {"media_id": mid,
                               "media_source": str(r.get("media_source") or ""),
                               "media_type": str(r.get("media_type") or "")}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播:媒体身份索引失败（忽略）：{e}")
        return idx

    def _ondemand_media_hint(self, h: str) -> Optional[Dict[str, str]]:
        """单条查（补整理走这里，没有现成索引）。"""
        hh = str(h or "").lower()
        if not hh:
            return None
        return self._ondemand_media_index().get(hh)

    def _ondemand_download(self, row: Dict[str, Any], task: Any = None,
                           title: str = "", year: str = "",
                           content: Optional[bytes] = None) -> Dict[str, Any]:
        """落种（点播通道）→ ★ 19.10.11：核心收归 ``tags.media_grab``，本方法只做点播尾段。

        ``content`` 给了就不再取一次 .torrent（★ 17.2.0 直连加种复用取种结果）。
        尾段 = 挂 ``__ondemand__`` 伪任务 + inflight 槽 + 历史落一条 —— 那才是点播真差异。
        """
        want_dl = str(getattr(task, "downloader", "") or "").strip() or "qbittorrent"
        save_path = str(getattr(task, "save_path", "") or "") if task is not None else ""
        if not save_path:
            save_path = self._ondemand_default_save_path()
        if not save_path:
            return {"ok": False, "code": "no_save_path",
                    "message": "没有可用的保存目录：请在弹窗上方选一个任务，或到「设置 → 下载目录」填「任务保存目录」"}
        res = media_grab(self, row, save_path, kind="ondemand",
                         content=content, downloader_name=want_dl,
                         pv_gate=False, infohash=info_hash)
        if not res.get("ok"):
            return {"ok": False, "code": str(res.get("code") or ""),
                    "message": str(res.get("message") or "添加失败")}
        h = res["hash"]
        site_name = str(row.get("site_name") or "")
        # ★ 15.8.4：加种即挂 __ondemand__ 伪任务（职务=点播）→ 未下完不被静默池删/暂停
        try:
            self._od_assign([h], site=site_name, sub=SUB_RESOURCE, reason="加种")
        except Exception as _oae:  # noqa: BLE001
            self._log(f"点播:挂伪任务失败 {h[:12]}: {_oae}", "warning")
        # ★ 16.0.1：同时写「点播 inflight」槽 → 静默闸 _silent_audit 跳过
        #   （只靠 _od_assign 写账本会撞「qB 还没登记新种」的竞态 → 在途种被判违规补暂停）
        try:
            self._ondemand_mark(h, {
                "title": str(row.get("title") or ""),
                "site": site_name,
                "site_id": int(row.get("site") or 0),
                "free": is_freeleech(row.get("downloadvolumefactor")),
                "hit_and_run": bool(row.get("hit_and_run")),
            })
        except Exception as _ome:  # noqa: BLE001
            self._log(f"点播:inflight 槽落盘失败 {h[:12]}: {_ome}", "warning")
        # 17.1.0：点播时落一条历史记录（清单只读它，此后不再现算/回查）
        try:
            _odf = is_freeleech(row.get("downloadvolumefactor"))
            _ods = site_name or str(int(row.get("site") or 0))
            self._ondemand_history_put(h, {
                # ★ 19.11.0：中文名优先（站点原标题常常是拼音/英文，清单里看不懂是哪部片）
                "title": str(title or row.get("cn_title") or row.get("title") or ""),
                "subtitle": str(row.get("subtitle") or ""),
                "year": str(year or ""),
                "site": site_name,
                "site_id": int(row.get("site") or 0),
                "free": _odf,
                "hit_and_run": bool(row.get("hit_and_run")),
                "size_gb": round(float(row.get("size") or 0.0) / (1024 ** 3), 3),
                "source_note": f"源 {_ods}" + ("·免费" if _odf else ""),
                # ★ 19.11.2：**下载时已识别到的媒体身份**——整理直接拿它，不再用中文短名
                #   重新识别一次。下载期的识别用的是站点完整标题（带季号/来源），比台账里的
                #   中文短名精确；存下来后整理也不必再依赖 TMDB 是否可达。
                "media_id": str(row.get("media_id") or ""),
                "media_source": str(row.get("media_source") or ""),
                "media_type": str(row.get("media_type") or ""),
                "stage": "downloading",
                "added_at": time.time(),
                "settled_at": 0.0,
                "in_library": False,
            })
        except Exception as _ohe:  # noqa: BLE001
            logger.warning(f"魔流点播历史写入跳过 {h[:12]}: {_ohe}")
        return {
            "ok": True, "hash": h, "tag": res.get("tag") or "",
            "site": int(row.get("site") or 0), "save_path": save_path,
        }

    def _ondemand_add(self, query: str = "", site_ids: str = "", pick: str = "",
                      task_id: str = "", apply: bool = True) -> Dict[str, Any]:
        """★ 16.0.0：**只按 AI 指定的源加种**（绝不自动选源）。

        与 `on_demand`（自动优选）区分：本方法要求 `pick` = 候选 `enclosure`，
        命中即下这条；未命中 → 如实回报「候选未命中，请先 search」，
        **不调** `_ondemand_pick`（选源权归 AI）。

        ★ 17.1.1：找 pick 由 ``_ondemand_find_pick`` 分页续搜（前 ``_OD_ADD_MAX_PAGES`` 页，有界），
        不再只认第 1 页 —— 修「搜索翻页看得到、add 加不进去」。
        """
        q = self._ondemand_parse(query)
        if not q["query"]:
            return {"ok": False, "message": "缺少 query（片名或链接）"}
        task = self._get_task_config(task_id) if task_id else None
        sites = self._ondemand_sites(task, site_ids)
        if not sites:
            return {"ok": False, "message": "没有可搜的站点（site_ids / 任务站点均为空）"}
        pick = str(pick or "").strip()
        if not pick:
            return {"ok": False, "message": "缺少 pick（候选 enclosure / 下载链接）"}
        title = year = ""
        # ★ 19.10.0：候选池优先 —— 命中即零请求（不重搜、不记账、不看预算）
        row = self._od_pool_get(pick)
        if row is not None:
            title = str(row.get("title") or "")
        if row is None:
            rows = self._ondemand_cache_get(q["query"], sites) or []
            if not rows:
                media = self._ondemand_media(q)
                if media is not None:
                    try:
                        title = str(getattr(media, "title", "") or "")
                        year = str(getattr(media, "year", "") or "")
                    except Exception:  # noqa: BLE001
                        title, year = "", ""
                if not title:
                    title = q["keyword"] or q["query"]
                # ★ 17.1.1：命中失败不再只看 MP 第 1 页 —— 逐页续搜（有界）到 pick 命中/页尾/上限
                rows = self._ondemand_find_pick(title, year, sites, pick)
                # ★ 19.11.2：识别结果盖到候选行上（随池一起存 / 随池一起取）
                self._ondemand_stamp_media(rows, media)
                self._ondemand_cache_put(q["query"], sites, rows)
                self._od_pool_put(rows[:20], str(q.get("query") or ""))
            row = next((r for r in rows if str(r.get("enclosure") or "") == pick), None)
        if row is None:
            return {"ok": False, "code": "cand_expired",
                    "message": "候选已不在（超过 2 小时或站点已下架；已续搜前 %d 页，候选可能更靠后），请重新搜索"
                               % _OD_ADD_MAX_PAGES}
        save_path = (str(getattr(task, "save_path", "") or "") if task is not None else "")\
            or self._ondemand_default_save_path()
        plan = {
            "title": row.get("title") or "",
            "size": row.get("size"),
            "downloadvolumefactor": row.get("downloadvolumefactor"),
            "free": is_freeleech(row.get("downloadvolumefactor")),
            "hit_and_run": bool(row.get("hit_and_run")),
            # ★ 19.11.14：不再 `float(dv or 0.0)`（未知会被算成免费）→ 统一走 _od_cost
            "counted_gb": _od_cost(row),
            "promo": _od_promo_of(row),
            "save_path": save_path,
            "site": row.get("site_name") or row.get("site") or "",
        }
        if not apply:
            return {"ok": True, "applied": False, "dry_run": True, "plan": plan}
        res = self._ondemand_download(row, task, title=title, year=year)
        if not res.get("ok"):
            return {"ok": False, "message": str(res.get("message") or "下载失败"), "plan": plan}
        return {"ok": True, "applied": True, "hash": res.get("hash") or "", "plan": plan}

    # ------------------------------------------------- 直连加种（★ 17.2.0）

    @staticmethod
    def _direct_download_url(url: str, base: str, tid: str) -> str:
        """把用户给的链接归一成「取 .torrent 的下载链接」（只换端点，不猜站点）。"""
        u = str(url or "").strip()
        if not u:
            return ""
        if "://" not in u and not u.startswith("//"):
            u = "https://" + u.lstrip("/")
        low = u.lower()
        if low.endswith(".torrent") or "download.php" in low or "/download?" in low:
            return u
        if tid and base:
            return f"{base}/download.php?id={tid}"
        return u

    @staticmethod
    def _direct_torrent_meta(content: bytes) -> Dict[str, Any]:
        """从 .torrent 字节读「标题 + 体积」（真值源 = ``fingerprint`` 的 bencode 解析，不自己 parse）。"""
        title, size = "", 0
        try:
            entries = load_torrent_entries(content)
            size = int(total_size(entries))
            if entries:
                title = str(entries[0][0] or "").split("/")[0].strip()
        except Exception:  # noqa: BLE001
            pass
        return {"title": title, "size": size}

    def _ondemand_add_direct(self, url: str = "", site_ids: str = "",
                             task_id: str = "", apply: bool = True) -> Dict[str, Any]:
        """★ 17.2.0：**按种子链接直接加种**（不经过 search / 不选源 / 不猜站点）。

        与 ``_ondemand_add`` 的区别：那个要「先 search 拿候选 → pick 命中候选」；
        本方法只认链接本身（``details.php?id=N`` / ``download.php?id=N`` / ``.torrent`` 直链），
        用**指定站点**的 cookie 取种 → 走同一条点播落地（标签/伪任务/账本/静默闸全复用）。

        账号口径（诚实记账，绝不假装免费）：
          · 促销 ``dv`` 来自详情页抗取（``fetch_torrent_promotion``）；**拿不到 → dv=1.0 按全额计**；
          · ``H&R`` **不自造逐种标记**：详情页解析不出 ≠ 欠 H&R，判定归 H&R 模块
            （站点规则账本 ``_site_hr_flag``：True→site_hr；False→不开账；未知→unknown）。
        """
        from .claim import _torrent_id_of  # noqa: WPS433（惰性：claim 硬依赖 app.sdk.logging，离线单测无它）

        raw_url = str(url or "").strip()
        if not raw_url:
            return {"ok": False,
                    "message": "缺少 url（种子链接：details.php?id=N / download.php?id=N / .torrent 直链）"}
        task = self._get_task_config(task_id) if task_id else None
        sites = self._ondemand_sites(task, site_ids)
        if len(sites) != 1:
            return {"ok": False,
                    "message": "直连加种必须指定**唯一**站点 id（要拿该站 cookie 取种）；现收到 %d 个：%s"
                               % (len(sites), ",".join(str(x) for x in sites[:5]))}
        sid = int(sites[0])
        site = self._get_site(sid)
        if site is None:
            return {"ok": False, "message": f"站点 {sid} 不存在（site_ids）"}
        site_name = str(getattr(site, "name", "") or getattr(site, "domain", "") or "").strip()
        domain = str(getattr(site, "domain", "") or "").strip()
        base = str(getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
        tid = _torrent_id_of(raw_url)
        low = raw_url.lower()
        page_url = ""
        if "details.php" in low or "/details" in low:
            page_url = raw_url if "://" in raw_url else f"https://{raw_url.lstrip('/')}"
        elif tid and base:
            page_url = f"{base}/details.php?id={tid}"
        row: Dict[str, Any] = {
            "title": "", "size": 0.0, "seeders": 0, "peers": 0,
            "enclosure": self._direct_download_url(raw_url, base, tid),
            "page_url": page_url,
            "site": sid, "site_name": site_name,
            "site_cookie": getattr(site, "cookie", None),
            "site_ua": str(getattr(site, "ua", "") or "").strip() or None,
            "site_proxy": bool(getattr(site, "proxy", False)),
            "downloadvolumefactor": 1.0, "free": False, "counted_gb": 0.0,
            # ★ 不传逐种 H&R 标记：详情页解析不出 ≠ 欠 H&R。H&R 判定归 H&R 模块，
            #   按站点规则账本（features/hrbills.py::_site_hr_flag）判：
            #   site_hr=True→site_hr；site_hr=False→不开账；未知→unknown。
        }
        promo, promo_raw, promo_note = "unknown", "", "详情页拿不到 → 按全额计"
        if page_url:
            try:
                info = fetch_torrent_promotion(site, page_url) or {}
                promo = str(info.get("promotion") or "unknown")
                promo_raw = str(info.get("raw") or "")
                if promo != "unknown":
                    promo_note = f"详情页抗取 {promo}" + (f"（{promo_raw}）" if promo_raw else "")
                else:
                    promo_note = f"详情页解析不出({info.get('error') or '无促销区'}) → 按全额计"
            except Exception as e:  # noqa: BLE001
                promo_note = f"详情页异常({e}) → 按全额计"
        dv = _od_promo_dv(promo, promo_raw)
        row["downloadvolumefactor"] = dv
        row["free"] = dv <= 0.0
        content, _fcode, _fmsg = self._od_fetch_torrent(row)
        if not content:
            return {"ok": False, "code": _fcode, "message": _fmsg}
        meta = self._direct_torrent_meta(content)
        title = str(meta.get("title") or "")
        size = float(meta.get("size") or 0.0)
        row["title"] = title
        row["size"] = size
        row["counted_gb"] = round(size / 1e9 * dv, 2)
        save_path = (str(getattr(task, "save_path", "") or "") if task is not None else "") \
            or self._ondemand_default_save_path()
        plan = {
            "title": title,
            "size": size,
            "downloadvolumefactor": dv,
            "free": dv <= 0.0,
            "hit_and_run": bool(row.get("hit_and_run", False)),
            "counted_gb": row["counted_gb"],
            "save_path": save_path,
            "site": site_name or sid,
            "site_id": sid,
            "url": row["enclosure"],
            "page_url": page_url,
            "torrent_id": tid,
            "promotion": promo,
            "promotion_note": promo_note,
            "meta_source": ".torrent（fingerprint.load_torrent_entries）",
        }
        if not apply:
            return {"ok": True, "applied": False, "dry_run": True, "plan": plan,
                    "note": "干跑也取了一次 .torrent 读元数据（MP 侧请求），但**没有落种**"}
        res = self._ondemand_download(row, task, title=title, year="", content=content)
        if not res.get("ok"):
            return {"ok": False, "message": str(res.get("message") or "下载失败"), "plan": plan}
        return {"ok": True, "applied": True, "hash": res.get("hash") or "",
                "plan": dict(plan, save_path=str(res.get("save_path") or save_path))}

    # ------------------------------------------------------------ 结算（下载完 → 资源）

    def _ondemand_settle(self, task: Any = None) -> Dict[str, int]:
        """把已形成资源组的点播种子**直接转「资源」**（不观察、不分拣）。"""
        # ★ 15.8.4：先对账「点播」职务（补挂漏的 / 释放已结算的），再干活
        try:
            _rc = self._ondemand_duty_reconcile()
            if _rc.get("assigned") or _rc.get("released"):
                self._log(f"点播:职务对账 补挂 {_rc.get('assigned')} / 释放 {_rc.get('released')}")
        except Exception as _rce:  # noqa: BLE001
            self._log(f"点播:职务对账异常: {_rce}", "warning")
        # ★ 19.10.70：先把历史「已转资源 · 未入库」的补整理一遍（治本）。
        #   刻意放在 pending 判断**之前** —— 没有在途点播时也要补，
        #   否则断网期漏整理的那些永远等不到下一轮（正是小猪佩奇卡住的形态）。
        #   同文件自调用，不给 brush.py 新增跨界边；内部自带 10 分钟节流与逐项异常隔离。
        #   外层异常由 brush 的 settle 包装统一兜（不在这里再记一条）。
        _retry: Dict[str, Any] = self._ondemand_import_retry()
        # ★ 19.11.2：一轮只建一次「hash → 下载期媒体身份」索引，循环里别逐条读台账
        _midx = self._ondemand_media_index()
        pend = self._ondemand_all()
        if not pend:
            return dict({"settled": 0}, **_retry)
        try:
            files = self._tag_groups()
        except Exception:  # noqa: BLE001
            return dict({"settled": 0}, **_retry)
        snap = self._tag_all_torrents() or {}
        done = 0
        for h, info in list(pend.items()):
            t = snap.get(h)
            if t is None:
                continue   # 还没进下载器（或已被移走）→ 继续等
            # ★ 必须等**下载完成**才结算：进度没到 100% 就整理入库，会把半截文件
            #   硬链接进媒体库（MP 整理的是文件不是种子，不管下没下完）。
            try:
                _prog = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                _prog = 0.0
            if _prog < 0.999:
                continue
            gid = ""
            try:
                gid = files.group_of(h)
            except Exception:  # noqa: BLE001
                gid = ""
            if not gid:
                # ★ 19.10.71：**组未成形但账本已是「资源」身份** → 不必再设身份，直接收尾。
                #   点播单种常不被目录扫描建组，旧代码在此裸 `continue` ⇒ 永远停在 pending：
                #   既走不到补整理（历史里没这条，重试机制看不见它），也退不掉「点播」职务标签
                #   与静默闸互掐。实测小猪佩奇 82ef219a：52 集早已入库，pending + 双职务标签
                #   却挂了一整天，靠人肉才查出来。
                try:
                    _rec0 = self._tag_state().get(h) or {}
                    _ident = str(_rec0.get("sub") or "")
                except Exception:  # noqa: BLE001
                    _rec0, _ident = {}, ""
                if _ident != SUB_RESOURCE:
                    # ★ 19.11.4：无组 + 账本无身份。旧代码在此裸 continue「等对账/纳管建组」，
                    #   可**没有文件特征码的种按「无码不建资源」的设计永远不会成组** → 死等。
                    #   实测小城良方 S01E05-S01E06 / S01E09-S01E10：7.9GB 已下完、文件在盘上，
                    #   却在「已下完，待转资源」挂着不动；补一次码当轮就建组走完。
                    #   这里自己补码建组（不依赖 tags_watch 的 60 分钟周期），补不到就收尾，
                    #   绝不无限等 —— 但**有码却没组**说明组只是还没成形，继续等是对的。
                    _fp = self._ondemand_fp_ensure(h, _rec0)
                    if _fp:
                        gid = self._ondemand_group_ensure(h, _fp, t, _rec0)
                    if not gid:
                        if _fp:
                            continue      # 有码、组还没成形 → 再等一轮
                        self._log(f"点播:无特征码也收尾 {h[:12]}（不建组，直接整理入库）")
            try:
                if gid:
                    files.set_identity(gid, SUB_RESOURCE, by="ondemand")
            except Exception as e:  # noqa: BLE001
                self._log(f"点播:转资源失败 {h[:12]}: {e}", "warning")
                continue
            self._ondemand_unmark(h)
            # ★ 15.8.4：转资源即退「点播」职务 → 交回静默闸管辖
            try:
                self._od_release([h], reason="结算转资源")
            except Exception:  # noqa: BLE001
                pass
            done += 1
            _title = str(info.get("title") or info.get("media") or "")
            self._log(f"点播:转「资源」 {h[:12]} 「{_title}」")
            # ★ 2026-10-01：点播是「我要看这部片」→ 转资源后**顺手整理入库**
            #   （MP 手动整理：transfer_type=link → 硬链接进媒体库，种子照旧做种，不删不移）
            _ok_import, _import_msg = self._ondemand_import_ex(
                h, gid, _title, media_hint=_midx.get(str(h or "").lower()))
            # 17.1.0：点播历史记录 → 已转「资源」（落盘记录，清单只读它）
            # ★ 19.10.70：入库失败不再是静默终局 —— 落 retry_at/import_msg，
            #   由 ``_ondemand_import_retry`` 按退避表自动补整理。
            _hist_fields: Dict[str, Any] = {
                "stage": "resource", "settled_at": time.time(),
                "in_library": bool(_ok_import), "import_msg": str(_import_msg or ""),
            }
            if not _ok_import:
                _hist_fields.update(retry_n=0, retry_stop=False,
                                    retry_at=time.time() + _OD_IMPORT_BACKOFF[0])
            self._ondemand_history_update(h, **_hist_fields)
            # ★ 11.11.0：转资源后入池即暂停（静默硬不变量；任务纳管时才做种）
            try:
                self._silent_pause_gate(h)
            except Exception:  # noqa: BLE001
                pass
        return dict({"settled": done}, **_retry)

    def _ondemand_import(self, h: str, gid: str = "", title: str = "") -> bool:
        """点播种转「资源」后整理入库（复用推荐链路的 MP ``TransferChain.manual_transfer``）。

        识别失败/取种失败都只记日志、**不阻断**（文件留在下载目录，可下次再整理）。
        19.10.70 起失败不再是终点：行会进「补整理」队列，由
        ``_ondemand_import_retry`` 按退避表自动重跑。
        """
        ok, _msg = self._ondemand_import_ex(h, gid, title)
        return bool(ok)

    def _ondemand_import_ex(self, h: str, gid: str = "", title: str = "",
                            media_hint: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
        """同 ``_ondemand_import``，但把 MP 的失败原因带回来（落进历史记录 → 用户可见）。

        失败原因是排障的唯一线索：以前只返回 bool，日志里只有「未整理」三个字，
        分不清「没外网」「识别不出」「没权限」——所以单开一个带 msg 的版本。

        ``media_hint``（★ 19.11.2）= 下载时已识别的媒体身份；不传就按 ``h`` 回台账查一次
        （补整理走这条）。传了就不会再用中文短名去 ``recognize`` 一遍。
        """
        _h = str(h or "").lower()
        if not _h:
            return False, "缺少 hash"
        if media_hint is None:
            media_hint = self._ondemand_media_hint(_h)
        try:
            ok, msg = self._recommend_import(
                _h, {"title": str(title or ""), "group_id": str(gid or "")},
                media_hint=media_hint)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:整理入库异常 {_h[:12]}: {e}", "warning")
            return False, f"整理异常:{e}"
        self._log(
            f"点播:整理入库 {_h[:12]} 「{title}」→ {'完成' if ok else '未整理'} {msg or ''}"
            + (f" [按下载期识别 {str((media_hint or {}).get('media_id'))[:12]}]"
               if (media_hint or {}).get("media_id") else "").rstrip()
        )
        return bool(ok), str(msg or "")

    def _ondemand_import_retry(self, force: bool = False) -> Dict[str, Any]:
        """点播「整理入库」失败重试（19.10.70）—— 每轮 Check 一遍，内部 10 分钟节流。

        真值源 = ``ondemand_history`` 落盘记录：``stage=resource`` 且 ``in_library=False``
        的行就是「待补整理」。四种处置，**只有真试过才消耗次数**：

          ① 种已不在下载器 → 标 ``retry_stop``（没有 content_path，重试必然失败）；
          ② 未到 ``retry_at`` / 次数用完 → 跳过（不硬刷 MP，避免拖慢检查周期）；
          ③ 成功 → ``in_library=True`` + ``imported_at``，清空重试状态；
          ④ 失败 → 次数 +1、按退避表定下次时间、``import_msg`` 记原因。

        ``force=True``：忽略节流/退避/次数上限并清零计数（人工「全部重跑」入口）。
        下载器整体不可用时整轮跳过且**不计次数**（否则 qB 重启一次就把上限烧光）。
        """
        now = time.time()
        if not force:
            _last = float(getattr(self, "_od_import_round_ts", 0.0) or 0.0)
            if now - _last < _OD_IMPORT_ROUND_MIN:
                return {"retried": 0, "ok": 0, "fail": 0, "skipped": 0}
        self._od_import_round_ts = now
        # ★ 19.10.72：先按账本把「明明转了资源、历史却记成 gone」的行校正回来，
        #   否则这些行既进不了补整理队列（只看 stage=resource），界面上还挂着「已结案」。
        try:
            self._ondemand_history_reconcile()
        except Exception as _rce:  # noqa: BLE001
            self._log(f"点播:历史校正异常: {_rce}", "warning")
        rows = self._ondemand_history_read()
        todo = [
            r for r in rows
            if str(r.get("stage") or "") == "resource"
            and not bool(r.get("in_library"))
            and (force or not bool(r.get("retry_stop")))
        ]
        if not todo:
            return {"retried": 0, "ok": 0, "fail": 0, "skipped": 0}
        snap = self._ondemand_snapshot()
        if not snap:
            return {"retried": 0, "ok": 0, "fail": 0, "skipped": len(todo),
                    "note": "下载器不可用，本轮不消耗重试次数"}
        n_ok = n_fail = n_skip = 0
        for r in todo:
            h = str(r.get("hash") or "").lower()
            if not h:
                continue
            if snap.get(h) is None:
                r["retry_stop"] = True
                r["import_msg"] = "种已不在下载器，无法补整理"
                n_skip += 1
                continue
            _n = 0 if force else int(r.get("retry_n") or 0)
            if not force:
                if now < float(r.get("retry_at") or 0.0):
                    n_skip += 1
                    continue
                if _n >= _OD_IMPORT_MAX_TRY:
                    r["retry_stop"] = True
                    r["import_msg"] = str(r.get("import_msg") or "") or f"已重试 {_n} 次仍未入库"
                    n_skip += 1
                    continue
            ok, msg = self._ondemand_import_ex(
                h, "", str(r.get("title") or ""),
                media_hint=({"media_id": str(r.get("media_id") or ""),
                             "media_source": str(r.get("media_source") or ""),
                             "media_type": str(r.get("media_type") or "")}
                            if r.get("media_id") else None))
            if ok:
                r["in_library"] = True
                r["imported_at"] = time.time()
                r["import_msg"] = str(msg or "")
                r["retry_n"] = 0
                r["retry_at"] = 0
                r["retry_stop"] = False
                n_ok += 1
            else:
                r["retry_n"] = _n + 1
                r["retry_at"] = time.time() + _OD_IMPORT_BACKOFF[min(_n, len(_OD_IMPORT_BACKOFF) - 1)]
                r["import_msg"] = str(msg or "整理失败")
                n_fail += 1
        # 落盘失败由 ``_ondemand_history_save`` 自己 logger.warning，这里不再重复记（省一条 self._log）
        self._ondemand_history_save(rows)
        if n_ok or n_fail:
            self._log(f"点播:补整理 重试 {n_ok + n_fail} 个 → 成功 {n_ok} / 失败 {n_fail}")
        return {"retried": n_ok + n_fail, "ok": n_ok, "fail": n_fail, "skipped": n_skip}

    # ------------------------------------------------------------ 清单（进度 + 历史）

    def _ondemand_snapshot(self) -> Dict[str, Any]:
        """qB 快照（hash → TorrentInfo）；拿不到就退化为空（清单不报错）。"""
        try:
            return self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            return {}

    def _ondemand_seed_rec(self, h: str) -> Dict[str, Any]:
        """读种子账本行（真值源 ``SeedLedgerStore``）：state/sub/in_library/identity_at。"""
        try:
            return self._tag_state().get(str(h or "").lower()) or {}
        except Exception:  # noqa: BLE001
            return {}

    def _ondemand_fp_ensure(self, h: str, rec: Optional[Dict[str, Any]] = None) -> str:
        """确保这颗种有「合法文件特征码」，没有就当场补一次（★ 19.11.4）。

        为什么结算链路需要它：资源组建组只认**完整特征码**（``_resource_gid``：无合法码 →
        不建资源，10.0.0 定的，防「体积档冒充身份」把不同内容并成一条）。而点播下来的是
        **单个种**，常不被目录扫描建组；账本里一旦没有码，``group_of`` 恒空 → settle 里
        「无组 + 账本非资源」直接 ``continue`` → **永远停在「已下完，待转资源」**。
        全库补码在 ``tags_watch``（60 分钟一轮、limit=40），靠它兜意味着最长等一小时，
        实测小城良方 S01E05-S01E06 / S01E09-S01E10：7.9GB 文件早在盘上，却一直不整理。

        这里在结算现场补一次（一次 qB 调用），补到就写账本复用，不必等下一轮 worker。
        """
        _rec = rec if isinstance(rec, dict) else (self._ondemand_seed_rec(h) or {})
        _fp = str(_rec.get("fp") or "").strip().lower()
        if _OD_FP_OK.fullmatch(_fp):
            return _fp
        try:
            _dl = self._get_downloader()
            if _dl is None or not getattr(_dl, "is_available", False):
                return ""
            _fp = str(_dl.get_torrent_fingerprint(h) or "").strip().lower()
        except Exception:  # noqa: BLE001
            return ""
        if not _OD_FP_OK.fullmatch(_fp):
            return ""
        try:
            self._tag_state().put(h, {"fp": _fp})
        except Exception:  # noqa: BLE001
            pass
        return _fp

    def _ondemand_group_ensure(self, h: str, fp: str, t: Any,
                               rec: Optional[Dict[str, Any]] = None) -> str:
        """按特征码把这颗种单独入组（O(1)，不走全量 ``sync_resources``），返回组号。"""
        try:
            _gid = str(self._resource_gid("", 0.0, fp) or "")
            if not _gid:
                return ""
            _rec = rec if isinstance(rec, dict) else {}
            self._tag_groups().add_member(
                _gid, h,
                site=str(_rec.get("site") or ""),
                size_gb=float(getattr(t, "size_gb", 0) or _rec.get("size_gb") or 0.0),
                downloaded=True, progress=1.0, fp=fp,
                dl_bytes=float(getattr(t, "downloaded", 0) or 0),
                completed_at=float(getattr(t, "completion_on", 0) or 0),
                added_at=float(getattr(t, "added_on", 0) or 0),
            )
            return _gid
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:单颗建组失败 {str(h)[:12]}: {e}", "warning")
            return ""

    # ------------------------------------------------------------ 点播历史（17.1.0 落盘记录）


    @staticmethod
    def _ondemand_hist_site(reason: str) -> str:
        """从 journal 的 reason（如「源 财神·免费」）回填站点名（仅一次性迁移用）。"""
        r = str(reason or "").strip()
        if r.startswith("源"):
            r = r[len("源"):].strip()
        for sep in ("·", " ", "，", ","):
            if sep in r:
                r = r.split(sep)[0].strip()
                break
        return r


    def _ondemand_history_read(self, limit: int = _OD_HIST_KEEP) -> List[Dict[str, Any]]:
        """读点播历史记录（新 → 旧）。

        17.1.0（Master 2026-10-13：「没必要动态，做个记录就好」）：真值源 = ondemand_history 槽
        （mf_run 表，点播时**落一条记录**）—— 清单只读它，**不再**每次动态拼 journal + 现况回查。
        """
        try:
            data = slot_callbacks(self, _OD_HIST_KEY)[0]() or {}
        except Exception:  # noqa: BLE001
            data = {}
        rows = (data.get("rows") if isinstance(data, dict) else data) or []
        rows = [r for r in rows if isinstance(r, dict)]
        rows.sort(key=lambda r: float(r.get("added_at") or 0.0), reverse=True)
        try:
            n = max(1, min(int(limit or _OD_HIST_KEEP), _OD_HIST_KEEP))
        except (TypeError, ValueError):
            n = _OD_HIST_KEEP
        return rows[:n]

    def _ondemand_history_save(self, rows: List[Dict[str, Any]]) -> None:
        """写点播历史记录（保留最近 _OD_HIST_KEEP 条）。"""
        try:
            slot_callbacks(self, _OD_HIST_KEY)[1](value={"seeded": True, "rows": list(rows or [])[:_OD_HIST_KEEP]})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史落盘失败（忽略）：{e}")

    def _ondemand_history_put(self, h: str, fields: Dict[str, Any]) -> None:
        """17.1.0：点播时落一条历史记录（按 hash 幂等；新记录置顶）。

        ★ 19.10.72：读改写整表必须持锁 —— 多部片同时点播时（实测小猪佩奇 S10/S11/S12
        一分钟内连着下），两个线程各自 read 到同一份旧快照再 save，后写的那份会把先写的
        **整行冲掉或冲回旧字段**，落盘记录于是丢 ``stage``，清单按 ``gone`` 兜底 → 明明
        下完转好了资源，界面却显示「已结案」。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return
        try:
            with shared.lock("ondemand_history", legacy="od_hist_lock"):
                rows = [r for r in self._ondemand_history_read() if str(r.get("hash") or "") != hh]
                rec: Dict[str, Any] = {"hash": hh}
                rec.update({k: v for k, v in dict(fields or {}).items() if v is not None})
                rows.insert(0, rec)
                self._ondemand_history_save(rows)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史写入失败（忽略）：{e}")

    def _ondemand_hist_seed_fields(self, h: str) -> Dict[str, Any]:
        """补建历史行前，从 pending / qB / 账本反查展示字段。

        ★ 19.11.3：19.10.72 引入「找不到就补建」后，补建出来的行只有 ``hash`` + ``stage``，
        ``title`` / ``site`` / ``size_gb`` 全空 —— 清单里于是出现「标题空白却写着已入库」的空壳行
        （线上实测 3 条）。补建必须先尽力反查；反查不到也不能假装正常成功，
        由 ``_ondemand_hist_row`` 的「记录缺失」兜底如实说明。

        三处来源按可信度排：pending（点播时写入，含中文名）> qB 快照（含体积）> 账本身份。
        """
        out: Dict[str, Any] = {}
        hh = str(h or "").strip().lower()
        if not hh:
            return out
        try:
            info = (self._ondemand_all() or {}).get(hh) or {}
            if info:
                out["title"] = str(info.get("title") or info.get("media") or "")
                out["year"] = str(info.get("year") or "")
                out["site"] = str(info.get("site") or "")
                out["free"] = bool(info.get("free"))
                out["hit_and_run"] = bool(info.get("hit_and_run"))
        except Exception:  # noqa: BLE001
            pass
        try:
            t = (self._ondemand_snapshot() or {}).get(hh)
            if t is not None:
                if not out.get("title"):
                    out["title"] = str(getattr(t, "title", "") or "")
                if not out.get("site"):
                    out["site"] = str(getattr(t, "site", "") or "")
                _sg = float(getattr(t, "size_gb", 0) or 0.0)
                if _sg > 0:
                    out["size_gb"] = round(_sg, 3)
        except Exception:  # noqa: BLE001
            pass
        return {k: v for k, v in out.items() if v not in (None, "")}

    def _ondemand_history_update(self, h: str, **fields: Any) -> None:
        """更新一条历史记录（结算转「资源」/ 撤单标 removed）。

        ★ 19.10.72：**找不到就补建，不再静默 return**。旧实现在行缺失时什么都不做、也不留日志，
        于是「转资源成功」这一步在历史里凭空蒸发，清单只好按 ``gone`` 兜底成「已结案」。
        行怎么会缺：历史表由 ``_OD_HIST_KEEP`` 截断、并发 put 覆盖、或旧版本迁移漏写。

        ★ 19.11.3：补建前必须反查展示字段（见 ``_ondemand_hist_seed_fields``），
        否则补出的是**空壳行**：状态写「已入库」，标题却是空白。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return
        try:
            with shared.lock("ondemand_history", legacy="od_hist_lock"):
                rows = self._ondemand_history_read()
                for r in rows:
                    if str(r.get("hash") or "") != hh:
                        continue
                    r.update({k: v for k, v in fields.items() if v is not None})
                    self._ondemand_history_save(rows)
                    return
                # 行不在表里 → 按本次字段补建（宁可多一条，也不能让状态静默消失）
                # ★ 19.11.3：先反查展示字段，否则补出「标题空白·却写着已入库」的空壳行
                rec: Dict[str, Any] = {"hash": hh, "added_at": time.time()}
                try:
                    rec.update(self._ondemand_hist_seed_fields(hh))
                except Exception:  # noqa: BLE001
                    pass
                rec.update({k: v for k, v in fields.items() if v is not None})
                rows.insert(0, rec)
                self._ondemand_history_save(rows)
                logger.warning(f"魔流点播历史缺行已补建 {hh[:12]}："
                               f"stage={rec.get('stage') or '?'} "
                               f"title={'有' if str(rec.get('title') or '').strip() else '**缺**'}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"魔流点播历史更新失败（忽略）：{e}")

    def _ondemand_history_reconcile(self, snap: Optional[Dict[str, Any]] = None) -> int:
        """按账本**单向**校正历史表：``stage != resource`` 但账本已是「资源」身份的行改回 resource。

        ★ 19.10.72：只做 gone → resource，**绝不反向**。反方向一旦账本被清/重建，就会把
        真正转好资源的行打回 gone，那是把事实改坏；而少一条 resource 只是少补整理一次。
        返回修正条数（0 表示无需校正，热路径上几乎零成本）。

        ★ 19.10.72 补第二个真值源：**qB 标签**。账本会被别的职务覆盖 —— 实测佩奇 S10 转资源
        1 分钟后被刷流接管，qB 标签是「魔流-馒头-刷流 + 魔流-馒头-静默-资源」（retag 只加不减，
        资源身份从未撤销），账本却已经是刷流身份 → 光看账本永远修不回来。标签是下载器侧真值，
        比可能被覆盖的账本更接近事实，故作为兜底（要求「静默」与「资源」同时出现）。
        """
        try:
            rows = self._ondemand_history_read()
        except Exception:  # noqa: BLE001
            return 0
        fix = [r for r in rows if str(r.get("stage") or "") != "resource"]
        if not fix:
            return 0
        try:
            state = self._tag_state() or {}
        except Exception:  # noqa: BLE001
            return 0
        n = 0
        for r in fix:
            h = str(r.get("hash") or "").lower()
            if not h:
                continue
            rec = state.get(h) or {}
            _sub = str(rec.get("sub") or "")
            _inlib = bool(rec.get("in_library"))
            if _sub != SUB_RESOURCE and not _inlib:
                if snap is None:
                    try:
                        snap = self._ondemand_snapshot()
                    except Exception:  # noqa: BLE001
                        snap = {}
                _t = (snap or {}).get(h)
                _tags = " ".join(str(x) for x in (getattr(_t, "tags", None) or []))
                if not (STATE_SILENT in _tags and SUB_RESOURCE in _tags):
                    continue
            if not r.get("settled_at"):
                r["settled_at"] = float(rec.get("identity_at") or 0.0) or time.time()
            r["stage"] = "resource"
            if _inlib:
                r["in_library"] = True
            n += 1
        if n:
            try:
                with shared.lock("ondemand_history", legacy="od_hist_lock"):
                    self._ondemand_history_save(rows)
                self._log(f"点播:历史校正 {n} 条（账本已转资源 → 状态回归「已转资源」）")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"魔流点播历史校正落盘失败（忽略）：{e}")
                return 0
        return n

    def _ondemand_history_backfill(self) -> None:
        """★ 17.1.0 一次性迁移：槽还没落过记录时，把 journal 里已有的点播记录灌成落盘记录。

        只跑一次（写回时置 seeded 标记）；此后清单只看落盘记录，不再回看 journal / 现况回查。
        """
        try:
            data = slot_callbacks(self, _OD_HIST_KEY)[0]() or {}
        except Exception:  # noqa: BLE001
            data = {}
        if isinstance(data, dict) and data.get("seeded"):
            return
        rows: List[Dict[str, Any]] = []
        try:
            recs = self._store.journal.list_recent(limit=5000) if self._store is not None else []
        except Exception:  # noqa: BLE001
            recs = []
        try:
            snap = self._ondemand_snapshot()
        except Exception:  # noqa: BLE001
            snap = {}
        for r in recs:
            for it in (getattr(r, "items", None) or []):
                if str(getattr(it, "source", "") or "") != "ondemand":
                    continue
                h = str(getattr(it, "hash", "") or "").lower()
                if not h or any(str(x.get("hash") or "") == h for x in rows):
                    continue
                rec = self._ondemand_seed_rec(h)
                inlib = bool((rec or {}).get("in_library"))
                sub = str((rec or {}).get("sub") or "")
                size_gb = 0.0
                try:
                    size_gb = float(getattr(it, "size_gb", 0) or 0.0)
                except (TypeError, ValueError):
                    size_gb = 0.0
                if not size_gb and snap.get(h) is not None:
                    try:
                        size_gb = float(getattr(snap.get(h), "size_gb", 0) or 0.0)
                    except (TypeError, ValueError):
                        size_gb = 0.0
                _reason = str(getattr(it, "reason", "") or "")
                rows.append({
                    "hash": h,
                    "title": strip_media_prefix(str(getattr(it, "title", "") or ""), "ondemand"),
                    "year": "",
                    "site": str((rec or {}).get("site") or "") or self._ondemand_hist_site(_reason),
                    "site_id": 0,
                    "free": bool((rec or {}).get("free")),
                    "hit_and_run": bool((rec or {}).get("hit_and_run")),
                    "size_gb": round(size_gb, 3),
                    "source_note": _reason,
                    "stage": "resource" if (sub == SUB_RESOURCE or inlib) else "gone",
                    "added_at": float(getattr(r, "created_at", 0) or 0.0),
                    "settled_at": float((rec or {}).get("identity_at") or 0.0),
                    "in_library": inlib,
                })
        self._ondemand_history_save(rows)


    def _ondemand_inflight_row(self, h: str, info: Dict[str, Any], t: Any, rec: Dict[str, Any]) -> Dict[str, Any]:
        """进行中一行（干净清单 Item）：身份 + qB 进度。

        ★ 15.9.0 换皮：字段与历史行**同构**（stage / percent / downloaded_gb / ISO 时间…）。
        内部 ``_ts`` 仅用于排序，出清单前会剥掉。
        """
        base_ts = info.get("ts") or 0.0
        row: Dict[str, Any] = {
            "hash": h,
            "module": "ondemand",
            "stage": "gone", "stage_text": "已不在下载器",
            "title": str(info.get("title") or info.get("media") or ""),
            "year": str(info.get("year") or ""),
            "site": str(info.get("site") or ""),
            "progress": 0.0, "percent": 0.0, "state": "",
            "size_gb": 0.0, "downloaded_gb": 0.0, "left_gb": 0.0,
            "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": bool(info.get("free")),
            "hit_and_run": bool(info.get("hit_and_run")),
            "in_qb": t is not None,
            "in_library": bool((rec or {}).get("in_library")),
            "save_path": "",
            "added_at": fmt_iso_ts(base_ts),
            "settled_at": fmt_iso_ts((rec or {}).get("identity_at")),
            "source_note": "",
            "_ts": float(base_ts or 0.0),
        }
        if t is None:
            return row
        prog = float(getattr(t, "progress", 0) or 0.0)
        size_gb = float(getattr(t, "size_gb", 0) or 0.0)
        spd = float(getattr(t, "download_speed", 0) or 0.0)
        left_gb = max(0.0, size_gb * (1.0 - prog))
        row.update({
            "progress": round(prog, 4),
            "percent": round(prog * 100.0, 2),
            "state": str(getattr(t, "state", "") or ""),
            "size_gb": round(size_gb, 3),
            "downloaded_gb": round(size_gb * prog, 3),
            "left_gb": round(left_gb, 3),
            "speed": round(spd, 1),
            "ratio": round(float(getattr(t, "ratio", 0) or 0.0), 3),
            "save_path": str(getattr(t, "save_path", "") or ""),
        })
        if prog < 0.999:
            row["stage"] = "downloading"
            row["stage_text"] = "下载中"
            if spd > 0:
                row["eta_s"] = int(left_gb * (1024 ** 3) / spd)
        elif str((rec or {}).get("sub") or "") == SUB_RESOURCE:
            row["stage"] = "resource"
            row["stage_text"] = "已转「资源」"
        else:
            row["stage"] = "settling"
            row["stage_text"] = "已下完，待转「资源」"
        return row

    @staticmethod
    def _od_episode_tag(title: str, subtitle: str = "") -> str:
        """从标题/副标题里抽「第N-M集」这类集号，拼进展示标题用。

        ★ 19.11.3：同一部剧连续点播时（实测「小城良方」9 条），历史行的 ``title``
        取的是**中文片名**（19.11.0 有意为之：站点原标题常是拼音），而中文片名不带集号
        → 列表里 9 条一模一样，用户必须逐条展开副标题才知道是第几集。
        集号只在 ``subtitle`` 的 ``| 第N-M集 |`` 段里，这里把它提到标题上。

        已在标题里带集号（``S01E05`` / ``第5集``）时返回空，避免重复拼接。
        """
        t = str(title or "")
        if re.search(r"S\d{1,2}\s*E\d{1,3}", t, re.I) or re.search(r"第\s*\d{1,3}\s*集", t):
            return ""
        m = re.search(r"第\s*(\d{1,3})\s*(?:[-–~]\s*(\d{1,3})\s*)?集", str(subtitle or ""))
        if not m:
            return ""
        a, b = m.group(1), m.group(2)
        return f"第{a}-{b}集" if (b and b != a) else f"第{a}集"

    def _ondemand_hist_row(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """历史一行（干净清单 Item）：**只读落盘记录**。

        17.1.0：不再动态拼 journal / 现况回查（qB、账本）—— 行内一切取自 ondemand_history
        记录；stage 由记录定：resource = 已转「资源」；其余 = 已结案。字段与进行中行**同构**。
        """
        _raw_stage = str(rec.get("stage") or "")
        stage = _raw_stage or "gone"
        size_gb = round(float(rec.get("size_gb") or 0.0), 3)
        # ★ 19.11.3：标题缺失的行不再冒充「正常成功」—— 空壳行（历史记录只剩 hash）
        #   要么是旧版补建留下的，要么是记录被覆盖；如实说明比显示一条空白强。
        _title_raw = str(rec.get("title") or "").strip()
        _title_lost = not _title_raw
        _title = _title_raw or f"未知（{str(rec.get('hash') or '')[:8]}）"
        # ★ 19.11.3：把集号提到标题上（否则同剧连点时一屏标题全一样，分不清第几集）
        _ep = self._od_episode_tag(_title_raw, str(rec.get("subtitle") or ""))
        if _ep:
            _title = f"{_title} · {_ep}"
        _retry_n = int(rec.get("retry_n") or 0)
        _retry_stop = bool(rec.get("retry_stop"))
        if stage == "resource":
            if rec.get("in_library"):
                stage_text = "已转「资源」·已入库" if not _title_lost else "已入库（历史记录缺失）"
            elif _retry_stop:
                stage_text = "已转「资源」·未入库（已放弃）"
            elif _retry_n:
                stage_text = f"已转「资源」·未入库（待重试 {_retry_n}）"
            else:
                stage_text = "已转「资源」·未入库（待补整理）"
        elif not _raw_stage:
            # ★ 19.10.72：缺字段不再兜底成「已结案」—— 那会把「状态丢了」说成「事情办完了」
            stage_text = "状态未知（历史记录缺字段）"
        else:
            stage_text = "已结束·未转资源"
        return {
            "hash": str(rec.get("hash") or ""),
            "module": "ondemand",
            "stage": "resource" if stage == "resource" else "gone",
            "stage_text": stage_text,
            "title": _title,
            "subtitle": str(rec.get("subtitle") or ""),
            "year": str(rec.get("year") or ""),
            "site": str(rec.get("site") or ""),
            "progress": 1.0 if stage == "resource" else 0.0,
            "percent": 100.0 if stage == "resource" else 0.0,
            "state": "",
            "size_gb": size_gb,
            "downloaded_gb": size_gb if stage == "resource" else 0.0,
            "left_gb": 0.0,
            "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "free": bool(rec.get("free")),
            "hit_and_run": bool(rec.get("hit_and_run")),
            "in_qb": False,
            "in_library": bool(rec.get("in_library")),
            "import_msg": str(rec.get("import_msg") or ""),
            "retry_n": _retry_n,
            "retry_at": fmt_iso_ts(rec.get("retry_at")),
            "retry_stop": _retry_stop,
            "save_path": "",
            "added_at": fmt_iso_ts(rec.get("added_at")),
            "settled_at": fmt_iso_ts(rec.get("settled_at")),
            "source_note": str(rec.get("source_note") or ""),
            "_ts": float(rec.get("added_at") or 0.0),
        }

    def _ondemand_items(self, limit: int = 50) -> Dict[str, Any]:
        """点播干净清单：**单列表** items[]（进行中+历史**同构**）+ totals。

        真值源（只读）：
          - 进行中 = ondemand_pending（mf_seed.pending）× qB 快照（进度/状态/速度）；
          - 历史 = **点播历史落盘记录**（ondemand_history 槽；点播时写、结算/撤单时更新）
            —— 17.1.0 起不再动态拼 journal + 现况回查。
        """
        try:
            cap = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            cap = 50
        self._ondemand_history_backfill()   # 17.1.0：一次性把已有 journal 点播灌成落盘记录
        pend = self._ondemand_all()
        snap = self._ondemand_snapshot()
        rows: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for h, info in pend.items():
            seen.add(h)
            rows.append(self._ondemand_inflight_row(h, info, snap.get(h), self._ondemand_seed_rec(h)))
        for rec in self._ondemand_history_read():
            h = str(rec.get("hash") or "").lower()
            if not h or h in seen:
                continue
            if str(rec.get("stage") or "") == "removed":
                continue   # 本线撤单过 → 点播窗口不展示
            seen.add(h)
            rows.append(self._ondemand_hist_row(rec))
        rows.sort(key=lambda x: float(x.get("_ts") or 0.0), reverse=True)
        rows = rows[:cap]
        for x in rows:                      # 内部排序键不出清单
            x.pop("_ts", None)
        totals = media_totals(rows)
        return {"items": rows, "totals": totals}

    # ------------------------------------------------------------ 操作（行内：暂停/继续/移除）

    _OD_ACTS = ("pause", "resume", "remove")

    def _ondemand_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """点播「进行中」的行内操作：``pause`` / ``resume`` / ``remove``（只读清单之外的唯一写口）。

        ★ 15.9.0 回执统一：**恒**返回 ``{ok, hash, action, message, blocked}``（5 键齐全）。
        ``remove`` **走唯一删除闸门**（``DownloaderAdapter.delete_torrents``）：欠 H&R /
        跨站来源份 / 已认领 / 手动保留 **一律硬拦**（fail-closed，不绕过）——被拦时
        ``ok=false``、``blocked=true`` 并附原因，前端如实展示。
        删种**同时删文件**（未完成的下载无保留价值，避免又添孤儿文件）。

        ★ 19.10.11：写口搬到 ``tags.media_act``（与音乐**共用同一个删除闸门**），
        本方法只剩点播特有的两件事：**归属**（在 pending 槽里）与
        **移除后收尾**（撤 pending 槽 + 历史标 ``removed`` —— 否则撤单过的种会复活）。
        """
        def _belong(h: str) -> Optional[str]:
            if h not in self._ondemand_all():
                return "该种不在点播进行中（可能已完成/已移除）"
            return None

        def _removed(h: str) -> None:
            self._ondemand_unmark(h)
            # 17.1.0：撤单 → 历史记录标 removed（点播窗口不再展示）
            self._ondemand_history_update(h, stage="removed", removed_at=time.time())

        return media_act(self, hash, action, kind="ondemand",
                         acts=self._OD_ACTS, belong=_belong, removed=_removed)

    # ------------------------------------------------------------ API

    def ondemand_act(self, hash: str = "", action: str = "") -> Response:
        """``POST /ondemand/act`` —— 点播行内操作（pause / resume / remove）。"""
        try:
            rep = self._ondemand_act(hash=hash, action=action)
            return Response(success=bool(rep.get("ok")), message=str(rep.get("message") or ""), data=rep)
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"点播操作失败:{e}")

    def ondemand_items(self, limit: int = 50) -> Response:
        """``GET /ondemand/items`` —— 点播清单（进行中带进度 + 历史）。只读。"""
        try:
            return Response(success=True, data=self._ondemand_items(limit=limit))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"读取点播清单失败:{e}")

    def ondemand_repair(self, force: str = "1") -> Response:
        """``POST /ondemand/repair`` —— 人工「全部重跑」：把「已转资源·未入库」的历史行重跑整理。

        ``force``（默认 1）：忽略退避/次数上限并清零计数 —— 修好 MP 的识别能力
        （例如补上 PROXY_HOST 让 TMDB 能连）之后，用它一次把历史漏整理的补回来。
        """
        _force = str(force).strip().lower() not in ("0", "false", "no", "off", "")
        try:
            rep = self._ondemand_import_retry(force=_force)
            return Response(
                success=True,
                message=(f"补整理：重试 {rep.get('retried')} / 成功 {rep.get('ok')} / "
                         f"失败 {rep.get('fail')} / 跳过 {rep.get('skipped')}"),
                data=rep,
            )
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"补整理失败:{e}")

    def on_demand(
        self,
        query: str = "",
        task_id: str = "",
        site_ids: str = "",
        apply: bool = True,
        pick: str = "",
    ) -> Response:
        """POST /ondemand：点播（片名 / 豆瓣·TMDB·IMDB 链接）→ 直接转「资源」。

        ``pick`` = 候选的 ``enclosure``（下载链接）：**手动指定源**，不做自动优选；
        命中最近一次搜索缓存则直接下（秒回），缓存过期/不匹配就如实报错让前端重搜。
        """
        q = self._ondemand_parse(query)
        if not q["query"]:
            return Response(success=False, message="缺少 query（片名或链接）")
        task = self._get_task_config(task_id) if task_id else None
        sites = self._ondemand_sites(task, site_ids)
        if not sites:
            return Response(success=False, message="没有可搜的站点（site_ids / 任务站点均为空）")
        pick = str(pick or "").strip()
        media = None
        title = year = ""
        rows: List[Dict[str, Any]] = []
        picked: Optional[Dict[str, Any]] = None
        if pick:
            # ★ 19.10.0：候选池优先 —— 命中即零请求（不重搜、不记账、不看预算）。
            #   这是「搜完必能下」的关键：候选留在服务端，落地时不再推导一次。
            picked = self._od_pool_get(pick)
            if picked is not None:
                rows = [picked]
                title = str(picked.get("title") or "")
        if picked is None:
            if pick:
                # 池未命中（旧池 / 池被淘汰）→ 退「最近一次搜索」单槽再试一次
                rows = self._ondemand_cache_get(q["query"], sites) or []
            if not rows:
                # 未指定来源 / 手动指定但缓存失效 → 正常识别 + 搜索
                media = self._ondemand_media(q)
                if media is not None:
                    try:
                        title = str(getattr(media, "title", "") or "")
                        year = str(getattr(media, "year", "") or "")
                    except Exception:  # noqa: BLE001
                        title, year = "", ""
                if not title:
                    # ★ 识别不到（如 TMDB 不可达）**不阻断**：Master 的「主动声明」本身已是最硬信号（§1），
                    #   识别只用来拼搜索关键词 → 退回原串（可直接粘种子名）。
                    title = q["keyword"] or q["query"]
                keyword = title
                rows = self._ondemand_search(keyword, sites)
                if not rows and year:
                    rows = self._ondemand_search(f"{title} {year}", sites)
                # ★ 19.11.2：识别结果盖到候选行上 → 落种时随台账存下 → 整理直接复用
                self._ondemand_stamp_media(rows, media)
                self._ondemand_cache_put(q["query"], sites, rows)
                # 覆盖入池：弹窗「勾选 → 批量」取的是池里的副本，不覆盖就拿不到身份。
                # **只写前 20 条**（= 返回给用户能勾选的那批）——全量重写会翻倍写盘，
                # 实测 806 条直接把请求拖到超时。注意 out 还没组装，别引用它。
                self._od_pool_put(rows[:20], str(q["query"] or ""))
        # ★ 19.11.6：把「这片是谁」传给选源 —— ``None`` 表示调用方不给身份（旧行为），
        #   ``[]`` 表示**没认出来**（那就别替用户选，见 ``_ondemand_pick`` 的注释）。
        _names = _od_target_names(media)
        auto = self._ondemand_pick(rows, None if not rows else _names)
        if pick:
            if picked is None:
                picked = next((r for r in rows if str(r.get("enclosure") or "") == pick), None)
            if picked is None:
                logger.warning(f"魔流点播:候选池未命中 {pick[:80]}（TTL={MEDIA_CAND_TTL}s）")
                return Response(success=False,
                                message="候选已不在（超过 2 小时或站点已下架），请重新搜索",
                                data={"code": "cand_expired"})
        else:
            picked = auto
        out: Dict[str, Any] = {
            "resource": {"title": title, "year": year,
                         "recognized": media is not None,
                         "media_source": getattr(media, "media_source", None) and str(
                             getattr(getattr(media, "media_source"), "value", getattr(media, "media_source"))),
                         "media_id": str(getattr(media, "media_id", "") or ""),
                         "names": _names},
            "sites": sites,
            "save_path": (str(getattr(task, "save_path", "") or "") if task is not None else "")
                         or self._ondemand_default_save_path(),
            "candidates": self._ondemand_rank(rows, _names)[:20],
            "picked": picked,
            "auto_pick": (auto or {}).get("enclosure") or "",
            "manual": bool(pick),
        }
        if not picked:
            return Response(success=False, message=self._od_no_pick_reason(rows, media, title, sites), data=out)
        if not apply:
            out["applied"] = False
            return Response(success=True, message="预览（apply=false，未下载）", data=out)
        res = self._ondemand_download(picked, task, title=title, year=year)
        out["applied"] = True
        out["added"] = res.get("hash") or ""
        if not res.get("ok"):
            out["code"] = str(res.get("code") or "")
            return Response(success=False, message=str(res.get("message") or "下载失败"), data=out)
        self._ondemand_mark(str(res.get("hash") or ""), {
            "title": picked.get("title") or "",
            "media": title, "year": year,
            "site": picked.get("site_name") or "",
            "site_id": picked.get("site") or 0,
            "free": is_freeleech(picked.get("downloadvolumefactor")),
            "hit_and_run": bool(picked.get("hit_and_run")),
        })
        try:
            self._store.journal.record(
                task_id=(task.id if task is not None else ""), kind="selection",
                items=[OperationItem(
                    hash=str(res.get("hash") or ""), title=f"点播 {title} {year}".strip(),
                    reason=f"源 {picked.get('site_name') or picked.get('site')}"
                           + ("·免费" if is_freeleech(picked.get("downloadvolumefactor")) else ""),
                    source="ondemand",
                )],
            )
        except Exception:  # noqa: BLE001
            pass
        self._log(
            f"点播:「{title}」{year} → 下 {str(res.get('hash'))[:12]}"
            f"（{picked.get('site_name') or picked.get('site')}·"
            + ("免费" if is_freeleech(picked.get("downloadvolumefactor")) else "计流量") + "）"
        )
        return Response(success=True, message=f"已点播：{title}（下载中，完成后直接转「资源」）", data=out)

    # ------------------------------------------------------------ 多选一并下载（★ 19.11.0）

    def on_demand_batch(self, picks: str = "", task_id: str = "",
                        site_ids: str = "") -> Response:
        """POST /ondemand/batch：**一次点播多条**候选（多选一并下载 · ★ 19.11.0）。

        根因（Master 2026-11-01「能够多选一并下载」）：点播原来只能一次一条 ——
        补齐佩奇 8 季要点 8 次、搜 8 次。批量只是把「搜」省掉：候选早已在池里
        （``_od_pool_put`` 按 ``enclosure`` 索引，TTL 2h），点几条就落几条。

        ``picks`` = 候选 ``enclosure`` 列表（换行 / 逗号分隔）；其余参数同 ``/ondemand``。
        ``site_ids`` 只为签名兼容保留 —— 批量不搜索，站点在这里没有话语权。

        三条边界（都是「别把批量做成新的失控入口」）：

          · **不重搜**：池里没有的直接判失败并说明原因（「候选已过期，请重新搜索」），
            绝不为了一条冷门候选再搜一遍全站 —— 那是 N 次批量 = N 轮站点请求；
          · **逐条独立的成败**：一条失败不影响后面的（``_ondemand_download`` 内部已 fail-closed），
            回执 ``ok[]`` / ``fail[]`` 分开列，前端如实展示；
          · **幂等**：同一 ``enclosure`` 重复勾选只下一次；已在点播中的 hash 直接标
            ``already``，不重复落种也不重复写台账。

        落种走的是与单条**同一个** ``_ondemand_download`` —— 标签 / 伪任务 / H&R 台账口径
        完全一致，不存在「批量版绕开纳管」的第二条路径。
        """
        urls: List[str] = []
        for u in re.split(r"[\r\n,]+", str(picks or "")):
            u = u.strip()
            if u and u not in urls:
                urls.append(u)
        if not urls:
            return Response(success=False, message="缺少 picks（要点播的候选链接）")
        if len(urls) > _OD_BATCH_MAX:
            return Response(success=False,
                            message=f"一次最多点播 {_OD_BATCH_MAX} 条（本次给了 {len(urls)} 条）")
        task = self._get_task_config(task_id) if task_id else None
        # 批量不搜索（候选全在池里）→ 不需要站点集合；保存目录缺失由 ``_ondemand_download``
        # 自己 fail-closed 报「没有可用的保存目录」（那里是唯一真值源，别在这里二次判断）。
        before = set(self._ondemand_all().keys())
        ok_rows: List[Dict[str, Any]] = []
        fail_rows: List[Dict[str, Any]] = []
        for u in urls:
            row = self._od_pool_get(u)
            if row is None:
                fail_rows.append({"enclosure": u, "title": "", "message": "候选已过期（超过 2 小时）或站点已下架，请重新搜索"})
                continue
            label = str(row.get("cn_title") or row.get("title") or "")
            res = self._ondemand_download(row, task, title=label, year="")
            if not res.get("ok"):
                fail_rows.append({"enclosure": u, "title": label,
                                  "message": str(res.get("message") or "下载失败")})
                continue
            h = str(res.get("hash") or "")
            ok_rows.append({
                "enclosure": u, "hash": h, "title": label,
                "site": str(row.get("site_name") or row.get("site") or ""),
                "already": h in before,
            })
            before.add(h)
        if ok_rows:
            try:
                self._store.journal.record(
                    task_id=(task.id if task is not None else ""), kind="selection",
                    items=[OperationItem(
                        hash=str(r.get("hash") or ""),
                        title=str(r.get("title") or ""),
                        reason="批量点播",
                        source="ondemand",
                    ) for r in ok_rows],
                )
            except Exception:  # noqa: BLE001
                pass
        self._log(
            f"点播:批量 {len(urls)} 条 → 成功 {len(ok_rows)} / 失败 {len(fail_rows)}"
            + ("（" + "、".join(str(r.get("title") or "")[:16] for r in fail_rows[:3]) + "）"
               if fail_rows else "")
        )
        out = {"total": len(urls), "ok": ok_rows, "fail": fail_rows,
               "ok_count": len(ok_rows), "fail_count": len(fail_rows)}
        if not ok_rows:
            return Response(success=False, message=f"全部失败（{len(fail_rows)} 条）："
                            + str((fail_rows[0] or {}).get("message") or ""), data=out)
        msg = f"已点播 {len(ok_rows)} 条（完成后直接转「资源」）"
        if fail_rows:
            msg += f"；{len(fail_rows)} 条失败"
        return Response(success=True, message=msg, data=out)

