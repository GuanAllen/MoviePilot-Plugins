# -*- coding: utf-8 -*-
"""魔流 · recon —— 站点账本对账（PT 站层；MP 是内容层，不管这件事）。

**为什么需要它**：MP 关心的是「片子下没下到」，不关心「种挂着但站点不认账」。
2026-11-02 实测：10 颗辅种的 announce 只剩 ``?passkey=<账号口令>``、没有主机名，
在 qB 里挂了 13 天、357GB 上传 0，**本地任何信号都看不出来**——
``tracker`` 字段为空的种全库 196 颗（多数是暂停里的静默池种）、
「暂停 + 零上传 + 超 7 天」1248 颗（静默池常态）。

两个判据，互相兜底：

1. **announce 能不能用**（本地可判，最硬）：**在跑的**种 ``trackers_count > 0`` 但
   ``tracker`` 取不出 → 一个可用的 tracker 都没有，不用问站点。站点侧取不到时**也照报**。
   成因可能是地址本身坏了（HDDolby 那 10 颗 ``?passkey=`` 没主机名），也可能域名还在、
   只是 passkey 失效或被站拒（Depth Studio 那 28 颗域名 ``dstudio.me`` 正常）——
   所以这一项只报「发不出去」，不猜原因。
   ⚠ 必须带「在跑」这一条：qB 的 ``tracker`` 是「第一个**可用**的 tracker」，
   暂停中的种从不 announce、天然为空 —— 只按「空 + 有 tracker」判会刷出 153 颗假坏链。
2. **跟站点对账**：站点这一侧的口径是「**正在**做种的种」，所以本地也必须先滤成
   活跃种（``RECON_ACTIVE_STATES``）。滤掉 paused 后逐站与站点行数一致到 ±1
   （March 85/85、NovaHD 118/118、蟹黄堡 115/115、高清时间 169/169、咖啡 201/201）；
   不滤的话学校 213 对 4、财神 187 对 92 —— 差额数正好等于 paused 数，那不是问题，是口径。

三方口径：

    A 本地实际   qB 里**归属该站且在跑**的种（``_site_report_torrent_site`` 按标签判定，
                 不靠 tracker）；停着不做的单独计数，不参与差额
    B 站点认账   站点「我正在做种」清单：HDDolby ``api/v1/user/peers``（peer 视图，
                 永远只当局部参考）；其余站走「我的种子」页（抓全才能判差额）
    C 台账       ``mf_seed``（按 **hash** 关联，避开「内部 id vs MP id」两套口径）

站点行**不带 info_hash**（peers 只有 ``id/team/size``，「我的种子」页只有 tid+标题+体积），
所以体积是唯一共同键：先精确、再容差 + 标题仲裁；匹配不上一律如实分到两侧，不猜。

⚠ 与 ``health.py`` 的分工：health 的铁律是「零外部请求」（只看已落库数据）。
对账必须主动拉站点，所以**不塞进 /health**，走独立 ``GET /recon``，按需触发 + 单站缓存。
"""

import difflib
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import Response

#: 体积容差：站点按「种子总大小」、qB 按「全部文件」，个别压制会差几 KB
RECON_SIZE_TOL = 0.02

#: 单站对账结果缓存秒数（站点请求有成本；``refresh=1`` 绕过）
RECON_TTL = 600

#: 新挂种宽限期（秒）：站点要过一个 announce 周期才在 peers 里认账，
#: 刚加入 qB 的种必然「本地有、站点没有」——那是正常态，不能算差额。
#: 实测（2026-11-02）：当天新挂的两颗 0.0 天，站点侧确实是 0。
RECON_NEW_GRACE = 900

#: 差额容差（颗）：announce 有周期，刚暂停/刚恢复的种会在「本地在跑 ↔ 站点在做种」
#: 之间抖动 1~2 颗。实测（2026-11-02）学校 3 对 4、财神 93 对 92 都是这种过渡态，
#: 因此 ≤3 颗只在明细里列出、不把该站标成 diff —— 否则每次刷新都有几个站闪红。
#: 真正的洞（Depth Studio 66 对 38、28 颗 announce 不生效）远超这个量级，不会漏掉。
RECON_DIFF_TOL = 3

#: 明细默认条数 / 上限
RECON_ITEMS_DEFAULT = 20
RECON_ITEMS_MAX = 100

#: 「在跑」的 qB 状态。站点只统计**正在做种**的种，静默池里 paused 的种站点不当在做种，
#: 所以本地这一侧必须先滤成活跃种再跟站点比 —— 否则每颗静默种都变成一条假差额。
#: 实测（2026-11-02，46.5s 全站）：滤掉 paused 后逐站与站点行数一致到 ±1
#: （March 85/85、NovaHD 118/118、蟹黄堡 115/115、高清时间 169/169、咖啡 201/201、
#:  CARPT 143/142）。不滤的话学校 213 对 4、财神 187 对 92，全是假差额。
RECON_ACTIVE_STATES = frozenset({
    "uploading", "forcedUP", "stalledUP", "seeding",
    "queuedUP", "checkingUP", "moving", "forcedMetaDL", "metaDL",
})

_UNIT = {
    "b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4,
    "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
}


def _rc_size_of(v: Any) -> int:
    """体积归一成整数字节。

    数字直取；文本（认领页给的是 ``40.64 GB``）按单位换算——两种来源混在一起比。
    """
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return 0
    s = str(v or "").strip().lower().replace(",", "")
    if not s:
        return 0
    m = re.match(r"([\d.]+)\s*([a-z]*)", s)
    if not m:
        return 0
    try:
        num = float(m.group(1))
    except (TypeError, ValueError):
        return 0
    return int(round(num * _UNIT.get(m.group(2) or "b", 1)))


def _rc_norm_title(s: Any) -> str:
    """标题归一（小写 / 去标点 / 压空白），只用于容差区间的仲裁。"""
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", str(s or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def _rc_sim(a: str, b: str) -> float:
    """两个已归一的标题的相似度（0~1）。"""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _rc_match(
    site_rows: List[Dict[str, Any]],
    qb_rows: List[Dict[str, Any]],
    tol: float = RECON_SIZE_TOL,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """站点认账行 ↔ 本地种，按体积匹配。

    站点行不给 info_hash，体积是唯一共同键：先按字节精确，再落 ``tol`` 容差区间；
    区间内多于一颗时用标题相似度仲裁（站点会改写标题/转拼音，所以只仲裁不单判）。

    Returns:
        ``(matched, site_only, local_only)``。第三项是「本地有、站点不认」——
        正是「在跑但站点不认」的那一类（announce 不生效 / 站点已删种），必须报出来。
    """
    sizes = [_rc_size_of(q.get("size")) for q in qb_rows]
    by_size: Dict[int, List[int]] = {}
    for i, sz in enumerate(sizes):
        if sz > 0:
            by_size.setdefault(sz, []).append(i)

    used: set = set()
    matched: List[Dict[str, Any]] = []
    site_only: List[Dict[str, Any]] = []

    for s in site_rows:
        sz = _rc_size_of(s.get("size"))
        cand = [i for i in by_size.get(sz, []) if i not in used]
        if not cand and sz > 0:
            lo, hi = sz * (1.0 - tol), sz * (1.0 + tol)
            cand = [i for i in range(len(qb_rows)) if i not in used and lo <= sizes[i] <= hi]
            if len(cand) > 1:
                want = _rc_norm_title(s.get("title"))
                if want:
                    cand.sort(key=lambda i: -_rc_sim(want, _rc_norm_title(qb_rows[i].get("title"))))
        if not cand:
            site_only.append(dict(s))
            continue
        i = cand[0]
        used.add(i)
        matched.append({
            "tid": s.get("tid"),
            "hash": qb_rows[i].get("hash"),
            "size": sz,
            "size_qb": sizes[i],
            "title": s.get("title") or qb_rows[i].get("title") or "",
        })

    local_only = [dict(q) for i, q in enumerate(qb_rows) if i not in used]
    return matched, site_only, local_only


class ReconMixin:
    """站点账本对账（``GET /recon``）：本地实际 / 站点认账 / 台账。"""

    def get_recon(self, site_id: Any = None, refresh: Any = None, limit: Any = None) -> Response:
        """功能端点：站点账本对账。

        Args:
            site_id: MP 站点 id，只对一站；空=全部启用站。
            refresh: 三态布尔，1 绕过单站缓存（站点请求有成本）。
            limit: 每类明细返回条数，默认 20、上限 100（汇总数字始终是全量）。
        """
        try:
            only = int(site_id) if str(site_id or "").strip() not in ("", "0") else 0
        except (TypeError, ValueError):
            only = 0
        try:
            cap = max(1, min(int(limit or RECON_ITEMS_DEFAULT), RECON_ITEMS_MAX))
        except (TypeError, ValueError):
            cap = RECON_ITEMS_DEFAULT
        fresh = bool(self._as_bool_arg(refresh))

        try:
            known = set(self._tag_site_names() or [])
            qb = self._tag_all_torrents() or {}
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"对账失败：读下载器快照出错（{err}）")

        try:
            ledger = self._recon_ledger_rows()
        except Exception:  # noqa: BLE001
            ledger = {}

        sites: List[Dict[str, Any]] = []
        try:
            infos = self._list_sites() or []
        except Exception:  # noqa: BLE001
            infos = []
        for info in infos:
            if not isinstance(info, dict):
                continue
            sid = self._recon_int(info.get("id"))
            if only and sid != only:
                continue
            sites.append(self._recon_one(info, qb, known, ledger, fresh, cap))

        checked = [s for s in sites if s.get("verdict") != "unknown"]
        diff = [s for s in checked if s.get("verdict") == "diff"]
        partial = [s for s in checked if s.get("verdict") == "partial"]
        data = {
            "sites": sites,
            "summary": {
                "sites": len(sites),
                "checked": len(checked),
                "unknown": len(sites) - len(checked),
                "diff_sites": len(diff),
                "partial_sites": len(partial),
                "local_only_count": sum(int((s.get("local_only") or {}).get("hard_count") or 0)
                                        for s in checked),
                "local_only_gb": round(sum(float((s.get("local_only") or {}).get("hard_gb") or 0)
                                           for s in checked), 2),
                "fresh_count": sum(int((s.get("local_only") or {}).get("fresh_count") or 0)
                                   for s in checked),
                "active_seeding": sum(int((s.get("qb") or {}).get("count") or 0)
                                      for s in checked),
                "idle_seeding": sum(int((s.get("qb") or {}).get("idle_count") or 0)
                                    for s in checked),
                "site_only_count": sum(int((s.get("site_only") or {}).get("count") or 0)
                                       for s in checked),
                "orphan_count": sum(int((s.get("orphans") or {}).get("count") or 0)
                                    for s in checked),
                "orphan_gb": round(sum(float((s.get("orphans") or {}).get("size_gb") or 0)
                                       for s in checked), 2),
                "checked_at": time.time(),
            },
        }
        if diff:
            # local_only 在「站点侧取不到但发现空 announce 种」时是 None → 先 or {}，
            # 否则这里 None.get 崩在汇总日志上（差额最该报的那一类反而报不出来）
            top = "、".join(
                "{}({})".format(
                    s.get("name"),
                    (s.get("local_only") or {}).get("count")
                    or (s.get("orphans") or {}).get("count")
                    or 0,
                )
                for s in diff[:3]
            )
            self._log(f"站点对账:{len(diff)} 站有差额 → {top}"
                      + ("…" if len(diff) > 3 else ""), "warning")
        return Response(success=True, data=data)

    def _recon_one(
        self,
        info: Dict[str, Any],
        qb: Dict[str, Any],
        known: set,
        ledger: Dict[str, Dict[str, Any]],
        fresh: bool,
        cap: int,
    ) -> Dict[str, Any]:
        """单站对账：组装 A/B/C 三方与差额结论。

        ★ 本地这一侧**先滤成活跃种**（``RECON_ACTIVE_STATES``）：站点只统计正在做种的
        种，静默池里 paused 的种在站点侧本来就不存在。不滤的话「本地全部种 vs 站点
        在做种」必然差出一大截，且差额数正好等于 paused 数 —— 那不是问题，是口径。
        """
        sid = self._recon_int(info.get("id"))
        name = str(info.get("name") or "").strip()
        dom = str(info.get("domain") or "").strip().lower()
        qb_rows = self._recon_qb_rows(name, qb, known)
        site_rows, source, meta = self._recon_site_rows(sid, fresh)
        active = [r for r in qb_rows
                  if str(r.get("state") or "") in RECON_ACTIVE_STATES]

        out: Dict[str, Any] = {
            "site_id": sid,
            "name": name,
            "domain": dom,
            "source": source,
            "qb": self._recon_side(active, cap=False),
        }
        # 停着不做的种单独计数：它们是「静默池常态」，不是差额，也不参与匹配
        out["qb"]["idle_count"] = len(qb_rows) - len(active)

        # announce 地址坏掉（**本地可判**，不依赖站点侧口径）—— 这是最硬的信号。
        # ★ 必须在「站点侧取不到」的早退**之前**算：站点没有全量清单 / 拿不到 apikey，
        #   恰恰是最需要这个信号的情形。判据本身只认活跃种（见 ``_recon_orphans``）。
        orphans = self._recon_orphans(active)
        out["orphans"] = self._recon_side(orphans, cap=cap)
        if source == "none":
            # 站点拿不到 ≠ 站点数量为 0（铁律 8：算不出来必须可见）
            out["site"] = None
            out["local_only"] = None
            out["site_only"] = None
            out["ledger"] = None
            if orphans:
                out["verdict"] = "diff"
                out["why"] = "站点侧取不到，但本地发现「在跑却没有可用 tracker」的种"
            elif not active:
                # 一颗都没在跑：站点本来就不会统计 paused 的种，没有可比对象
                out["verdict"] = "ok"
                out["why"] = "本站无活跃做种（paused 不计），无需比对"
            else:
                out["verdict"] = "unknown"
                out["why"] = ("站点侧取不到（无 apikey / 无「我的种子」页）"
                              if qb_rows else "双侧都取不到")
            return out

        matched, site_only, local_only = _rc_match(site_rows, active)
        now = time.time()
        for row in local_only:
            rec = ledger.get(str(row.get("hash") or "").lower()) or {}
            row["in_ledger"] = bool(rec)
            row["sub"] = rec.get("sub") or ""
            added = float(row.get("added_on") or 0)
            row["age_days"] = round((now - added) / 86400.0, 1) if added else None
            # 刚挂上的种站点还没 announce 到 → 正常态，不算差额（否则每次刷流都刷屏）
            row["fresh"] = bool(added) and (now - added) < RECON_NEW_GRACE
        local_only.sort(key=lambda r: -float(r.get("size") or 0))

        hard = [r for r in local_only if not r.get("fresh")]
        out["site"] = self._recon_side(site_rows, cap=False)
        out["matched"] = len(matched)
        out["local_only"] = self._recon_side(local_only, cap=cap)
        out["local_only"]["hard_count"] = len(hard)
        out["local_only"]["hard_gb"] = round(
            sum(_rc_size_of(r.get("size")) for r in hard) / (1024 ** 3), 2
        )
        out["local_only"]["fresh_count"] = len(local_only) - len(hard)
        out["site_only"] = self._recon_side(site_only, cap=cap)
        out["ledger"] = {
            "count": sum(1 for r in qb_rows
                         if str(r.get("hash") or "").lower() in ledger),
        }

        # ★ 站点侧可信度：两种来源都只列「正在做种的种」，对得上活跃种（实测见
        #   ``RECON_ACTIVE_STATES`` 注释）。但 ```` 只有真正抓全（分页抓满 /
        #   declared_total 未被截断）才能判差额；截断了就降级成 partial。
        reliable = source in ("api:peers", "seeding_page") and not meta.get("truncated")
        bad = False
        if reliable:
            # ≤RECON_DIFF_TOL 颗是 announce 过渡态抖动（刚暂停/刚恢复），明细照列不判 red
            bad = len(hard) > RECON_DIFF_TOL or len(site_only) > RECON_DIFF_TOL
        if orphans:
            bad = True
        if bad:
            out["verdict"] = "diff"
            return out
        out["verdict"] = "ok" if reliable else "partial"
        if not reliable:
            out["why"] = (meta.get("why")
                          or "站点侧清单没抓全，只当局部参考（不判差额）")
        elif hard or site_only:
            out["why"] = (f"差额 {len(hard)} 缺 / {len(site_only)} 多，在容差 "
                          f"{RECON_DIFF_TOL} 颗以内（announce 过渡态，明细已列）")
        return out

    @staticmethod
    def _recon_orphans(active_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """**在跑但没有可用 announce** 的种（本地可判，不依赖站点侧口径）。

        判据：**在跑**（``RECON_ACTIVE_STATES``）＋ ``trackers_count > 0`` ＋ ``tracker``
        为空 —— 条目在、正在做种、却连一个可用的 tracker 都没有。
        注意这**只说明 announce 没生效**，不说明地址本身坏了：2026-11-02 实测
        Depth Studio 那 28 颗域名 ``dstudio.me`` 好好的，是 passkey/站点侧不认账；
        而 HDDolby 那 10 颗是真的只剩 ``?passkey=``、主机名都没了。

        ⚠ 三条必须同时成立，少一条就会刷屏（2026-11-02 实测）：
        qB 的 ``tracker`` 字段语义是「第一个**可用**的 tracker，没有可用则为空」，
        静默池里 paused 的种从不 announce，天然为空 —— 只按「空 + trackers_count>0」
        判会在全站刷出 153 颗假坏链（正好等于静默池 paused 的数量）。
        加上「在跑」这一条后只剩真正在发 announce 却没地址的那几颗。
        DHT-only 种 ``trackers_count == 0`` 也不会误报。
        """
        out: List[Dict[str, Any]] = []
        for r in active_rows:
            if int(r.get("trackers_count") or 0) <= 0:
                continue
            if str(r.get("tracker") or "").strip():
                continue
            out.append(r)
        out.sort(key=lambda r: -float(r.get("size") or 0))
        return out

    @staticmethod
    def _recon_side(rows: List[Dict[str, Any]], cap: Optional[int] = 0) -> Dict[str, Any]:
        """一侧的汇总 + 明细（``cap=None`` 只给汇总，不给明细）。"""
        total = 0
        for r in rows:
            total += _rc_size_of(r.get("size"))
        out: Dict[str, Any] = {"count": len(rows), "size_gb": round(total / (1024 ** 3), 2)}
        if cap:
            out["items"] = rows[:int(cap)]
        return out

    def _recon_qb_rows(
        self, name: str, qb: Dict[str, Any], known: set
    ) -> List[Dict[str, Any]]:
        """A 侧：qB 里归属该站的种（按标签判站，不信 tracker 字段）。"""
        want = str(name or "").strip().lower()
        if not want:
            return []
        out: List[Dict[str, Any]] = []
        for h, t in (qb or {}).items():
            try:
                tsn = self._site_report_torrent_site(t, known)
            except Exception:  # noqa: BLE001
                tsn = ""
            if str(tsn or "").strip().lower() != want:
                continue
            out.append({
                "hash": h,
                "title": str(getattr(t, "title", "") or ""),
                "size": getattr(t, "size", 0),
                "state": str(getattr(t, "state", "") or ""),
                "uploaded": float(getattr(t, "uploaded", 0) or 0),
                "added_on": float(getattr(t, "added_on", 0) or 0),
                "tracker": str(getattr(t, "tracker", "") or ""),
                "trackers_count": int(getattr(t, "trackers_count", 0) or 0),
            })
        return out

    def _recon_site_rows(
        self, site_id: int, fresh: bool = False
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """B 侧：站点「我在做种」清单 → ``(rows, source, meta)``。

        两级取数：

        1. HDDolby 类官方 API ``user/peers``（有 apikey 时最快，字段只有 id/size/seeders）；
        2. NexusPHP 通用「我的种子」列表 ``_claim_site_rows``（``getusertorrentlistajax
           .php?type=seeding``，分页抓全，自带 10 分钟缓存）。

        ⚠ **不能用认领页（``claim.php``）当这一侧**：它只列「可认领/已认领」的种，
        不是「我在做种的全部」。认领页是「这批能不能领」的答案，不是「我在做什么种」。

        ⚠ 站点这一侧的口径是「**正在**做种」（paused 的种不计），所以调用方必须先把
        本地滤成活跃种再比 —— 见 ``RECON_ACTIVE_STATES``。

        ``meta`` 描述这一侧抓得全不全：``declared_total`` 是站点自己声明的条数，
        ``len(rows) < declared_total`` 即被截断 → 调用方降级成 ``partial``，不判差额。
        两级都拿不到 → ``([], "none", {})``，由调用方标 ``unknown``，**不能当成 0**。
        """
        cache = getattr(self, "_recon_cache", None)
        if cache is None:
            cache = {}
            try:
                self._recon_cache = cache
            except Exception:  # noqa: BLE001
                pass
        hit = cache.get(site_id)
        if hit and not fresh and (time.time() - float(hit.get("at") or 0)) < RECON_TTL:
            return (list(hit.get("rows") or []), str(hit.get("source") or "none"),
                    dict(hit.get("meta") or {}))

        site = self._get_site(site_id)
        rows: List[Dict[str, Any]] = []
        source = "none"
        meta: Dict[str, Any] = {}
        if site is not None:
            peers = self._hd_api_json(site_id, "api/v1/user/peers") or {}
            # ★ status=0 即「接口可用」：data 为空是**真的 0 颗**（站点把种删光了），
            #   不能与「取不到」混为一谈 —— 否则最该报的「站点全删」会被标 unknown。
            if peers.get("status") == 0:
                rows = [
                    {"tid": str(p.get("id") or ""), "title": "", "size": p.get("size")}
                    for p in peers.get("data") or []
                ]
                source = "api:peers"
                # peers 是「当前有 peer 在做种」的视图，本就不保证是全集（同一站在
                # 三轮实测里给过 52 / 41 / 9 行）→ 永远只当局部参考。
                meta = {"truncated": True,
                        "why": "站点只提供 peer 视图（数量随在线 peer 波动，不是全部做种）"}
            if source == "none":
                try:
                    got = self._claim_site_rows(site, refresh=fresh) or {}
                except Exception:  # noqa: BLE001
                    got = {}
                for r in got.get("rows") or []:
                    if not isinstance(r, dict):
                        continue
                    rows.append({
                        "tid": str(r.get("tid") or ""),
                        "title": str(r.get("title") or ""),
                        "size": r.get("size_bytes") or 0,
                    })
                if rows:
                    source = "seeding_page"
                    declared = self._recon_int(got.get("declared_total"))
                    meta = {"declared_total": declared, "fetched": len(rows),
                            "pages": self._recon_int(got.get("pages"))}
                    if declared and len(rows) < declared:
                        meta["truncated"] = True
                        meta["why"] = (f"站点声明 {declared} 条、只抓到 {len(rows)} 条"
                                       "（分页没抓全，不判差额）")
        # 取不到就不缓存：一次瞬时失败不该把该站锁在 unknown 十分钟
        if source != "none":
            cache[site_id] = {"at": time.time(), "rows": rows,
                              "source": source, "meta": dict(meta)}
        return rows, source, meta

    def _recon_ledger_rows(self) -> Dict[str, Dict[str, Any]]:
        """C 侧：台账 hash → 精简行（只用于解释「本地有但没台账」，不参与匹配）。

        ★ 走 ``SeedLedgerStore.items()``（``load_seeds`` 是 ``LedgerBackend`` 的方法，
          ``SeedLedgerStore`` 上不存在 —— 19.11.8 实测被 except 吞成空表、count 恒 0）。
        """
        from ..ledger import SeedLedgerStore, get_backend  # noqa: WPS433

        seeds = SeedLedgerStore(get_backend(self), log=self._log).items() or {}
        out: Dict[str, Dict[str, Any]] = {}
        for h, rec in seeds.items():
            if not isinstance(rec, dict):
                continue
            key = str(h or "").strip().lower()
            if not key:
                continue
            out[key] = {
                "sub": str(rec.get("sub") or ""),
                "state": str(rec.get("state") or ""),
                "site_id": rec.get("site_id"),
            }
        return out

    @staticmethod
    def _recon_int(v: Any) -> int:
        """宽松转 int（站点 id 可能来自 JSON 的 str/float）。"""
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
