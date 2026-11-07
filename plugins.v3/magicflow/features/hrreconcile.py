# -*- coding: utf-8 -*-
"""魔流 · hrreconcile —— H&R 站点对账（**只读的第三视角**）。

抓站点 ``myhr.php`` 拿到「站点认为你欠什么」，再跟本机下载器里的种、``hr_bills.json``
里的账单做三方对照，产出报告。这一层的方法**默认都不写**：不开账、不改账单状态、
不自动重下 —— 唯一的真写动作是 ``_hr_reconcile_add_one``（同站重下），
必须由 ``confirm=1`` 显式触发，且 ``_hr_reconcile_round`` 不调用它。

为什么从 ``features/hrbills.py`` 拆出来（19.10.34）：
  那个文件原本混了两件事 —— **账单状态机**（开账 / 作废 / 结清 / 违约判定，写账本）与
  **站点对账**（抓页面 / 粗配 / 退避，读站点）。前者改的理由是「账本口径变了」，
  后者改的理由是「站点页面变了」，从来不是同一件事；放在一起时每次碰 H&R 都得先
  花时间确认自己在哪半边。拆开后 ``hrbills.py`` 只剩账单状态机。

⚠ **依赖方向**：本模块单向 import ``.hrbills``（取 4 个账单状态常量 + 8 个对账参数）。
  ``hrbills.py`` **绝不**反向 import 本模块（会成环）—— 它只通过
  ``self._hr_reconcile_site`` / ``self._hr_reconcile_apply`` 在运行时调用
  （见 ``HrBillsMixin._hrbills_breach_reconcile``）：两个 Mixin 拼在同一个类上，
  ``self`` 上自然都有。

组件：
  - ``HrReconcileMixin``：对账主体（站点列表 / 抓 myhr 页 / 三方对照 / 粗配 / 重下 / 报告）；
  - ``HrReconcileCache``：派生缓存（``tid→infohash`` 索引 / 每站退避 / 上次报告），
    **不挂 ``MagicFlowStore``**（进程级单例热重载不重建）。
"""

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..collect import parse_myhr_page as _hr_myhr_page
from ..fingerprint import info_hash
from ..persistence import _shared
from .hrbills import (
    BILL_STATE_SETTLED,
    BILL_STATE_VOID,
    HR_RECONCILE_BACKOFF_HOURS,
    HR_RECONCILE_ENABLED,
    HR_RECONCILE_HOURS,
    HR_RECONCILE_MAX_FETCH,
    HR_RECONCILE_MAX_PAGES,
    HR_RECONCILE_TAG_SUFFIX,
    HR_RECONCILE_TIME_BUDGET,
    HR_RECONCILE_TTL,
)


def _hr_list_complete(page_ok: Any, records_total: Any,
                      cert: Any) -> Tuple[bool, str]:
    """★ 19.12.41：这份 ``myhr.php`` 列表**能不能自证完整** → ``(bool, 原因)``。

    列表本身没有完整性的自证能力（实测四站：分页控件是纯文本、没有「下一页」href、
    也没有「共 N 条」；``?page=1`` 只有一条指回首页）。所以完整性只能靠**页头 H&R 聚合
    计数**反向检验 —— 它是同一份债的另一种渲染，且不受分页/改版影响：

      · 计数不可解（``H&R: 0`` 这种单数字形态 / 缺栏 / 没抓到）→ 判不了；
      · 计数过期（> ``HR_SITE_EVIDENCE_MAX_HOURS``）→ 判不了；
      · 计数 ≠ 明细条数 → **明确矛盾**（抓漏了 / 抓到登录页或改版页）→ 判不了；
      · 计数 == 明细条数 → 这份列表就是该站的全部未结清记录（0 条也成立）。

    ★ 为什么「相等」也认：分页只影响「能看多少行」，而计数是**总数**；两者相等即证明
    本页已经包含了全部记录。这一条同时灭掉「中途空页」问题 —— 空页若真，计数必为 0。
    """
    if not page_ok:
        return False, "page_invalid"
    c = cert if isinstance(cert, dict) else {}
    if not c.get("known"):
        return False, "bar_unknown"
    if c.get("stale"):
        return False, "bar_stale"
    _total = c.get("total")
    if not isinstance(_total, int) or isinstance(_total, bool):
        return False, "bar_unknown"
    try:
        _n = int(records_total or 0)
    except (TypeError, ValueError):
        _n = 0
    if int(_total) != _n:
        return False, "bar_mismatch"
    return True, ""


class HrReconcileMixin:
    """站点 ``myhr.php`` 定期对账：只读第三方视角，不写账本、不自动重下。

    所有方法都假设宿主类上还有 ``HrBillsMixin``（``self._hrbills_store`` /
    ``self._hrbills_norm_domain``）以及采集出口 ``self.http``；单独实例化没有意义。
    """

    # ======================================== 11.8.0 站点 myhr 定期对账（第三视角）
    def _hr_reconcile_cache(self) -> "HrReconcileCache":
        """对账缓存（模块级工厂，**绝不挂 MagicFlowStore**：进程级单例热重载不重建）。"""
        try:
            data_dir = self.get_data_path()
        except Exception:  # noqa: BLE001
            data_dir = Path(".")
        try:
            kv = getattr(self, "_hot", None)
        except Exception:  # noqa: BLE001
            kv = None
        return get_hr_reconcile_cache(Path(data_dir), kv=kv)

    def _hr_reconcile_sites(self) -> List[Dict[str, Any]]:
        """对账对象：站点规则里 ``hr is True`` 的站（站点级 H&R）。按 MP 站点 id 去重（含域名别名）。"""
        cands: List[str] = []
        try:
            for row in (self._list_sites() or []):
                d = str((row or {}).get("domain") or "")
                if d:
                    cands.append(d)
        except Exception:  # noqa: BLE001
            pass
        try:
            for dom, rec in dict(self._site_rules().items() or {}).items():
                if (rec or {}).get("hr") is True:
                    cands.append(str(dom))
        except Exception:  # noqa: BLE001
            pass
        out: List[Dict[str, Any]] = []
        seen_dom: Set[str] = set()
        seen_sid: Set[int] = set()
        for dom in cands:
            d = self._hrbills_norm_domain(dom)
            if not d or d in seen_dom:
                continue
            seen_dom.add(d)
            try:
                if self._site_hr_flag(d) is not True:
                    continue
            except Exception:  # noqa: BLE001
                continue
            sid = self._hr_reconcile_site_id(d)
            if sid and sid in seen_sid:
                continue
            if sid:
                seen_sid.add(sid)
            hours = 24.0
            try:
                rec = dict(self._site_rules().get(d) or {})
                hours = float(rec.get("seed_hours") or 24.0)
            except Exception:  # noqa: BLE001
                hours = 24.0
            out.append({"domain": d, "need_h": hours, "site_id": sid})
        return out

    def _hr_reconcile_site_id(self, domain: str) -> int:
        """域名 → MP 站点 id（抓页/取 cookie 用）。找不到返回 0。"""
        d = self._hrbills_norm_domain(domain)
        if not d:
            return 0
        try:
            rows = self._list_sites() or []
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            try:
                rd = self._hrbills_norm_domain((row or {}).get("domain") or "")
            except Exception:  # noqa: BLE001
                rd = ""
            if rd and (rd == d or rd.endswith("." + d) or d.endswith("." + rd)):
                try:
                    return int((row or {}).get("id") or 0)
                except Exception:  # noqa: BLE001
                    return 0
        return 0

    def _hr_reconcile_fetch(self, site_id: int, domain: str,
                            max_pages: int = HR_RECONCILE_MAX_PAGES) -> Dict[str, Any]:
        """抓该站 ``myhr.php``（走采集出口：配额闸门 + PV 熔断 + 页缓存）。**只读**。

        失败语义（pro 定）：**任何一页拿不到 → ``ok=False`` + ``partial=True``**，
        调用方必须**零写入**（绝不从半份数据推「站点说干净」）。
        """
        out: Dict[str, Any] = {"ok": False, "records": [], "pages": [], "partial": False,
                               "error": "", "page_ok": False, "empty_asserted": False,
                               "visible_rows": 0, "total_declared": None, "audit": []}
        c = None
        try:
            c = self._collect_ref()
        except Exception:  # noqa: BLE001
            c = None
        if c is None:
            out["error"] = "采集模块未就绪"
            return out
        base = f"https://{self._hrbills_norm_domain(domain)}"
        for page in range(0, max(1, int(max_pages))):
            # ★ 19.12.41：删掉「上一页不满 10 条 → 已到末页」这条推断。实测四站分页控件
            #   没有可用 ``href``、也没有「共 N 条」，这个 10 完全是猜的；默认 ``max_pages=1``
            #   只抓首页，完整性交给页头 H&R 计数交叉验证（``hrbills._hr_bar_cert``）。
            url = f"{base}/myhr.php" + (f"?page={page}" if page else "")
            try:
                if not self._pv_allow(site_id, "hr", want=1):
                    out["partial"] = True
                    out["error"] = "站点 PV 预算不足或被熔断"
                    return out
            except Exception:  # noqa: BLE001
                pass
            try:
                res = c.http.text(int(site_id), url, kind="hr", ttl=HR_RECONCILE_TTL)
            except Exception as e:  # noqa: BLE001
                out["partial"] = True
                out["error"] = f"抓取异常:{e}"
                return out
            try:
                self._pv_spend(int(site_id), "hr", 1)
            except Exception:  # noqa: BLE001
                pass
            if res is None or not bool(getattr(res, "ok", False)):
                out["partial"] = True
                out["error"] = str(getattr(res, "error", "") or "抓取失败")
                return out
            text = str(getattr(res, "text", "") or "")
            cert = _hr_myhr_page(text)
            # ★ 审计只留**必要元数据**：页码 / 状态 / 是否重定向 / 字节数 / sha1 前 12 位 /
            #   解析结论 / 两类行数。**不存正文、cookie、UA、标题、用户名**。
            out["audit"].append({
                "page": page,
                "status": int(getattr(res, "status", 0) or 0),
                "redirected": bool(getattr(res, "redirected", False)),
                "bytes": len(text.encode("utf-8")),
                "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "",
                "parse": "ok" if cert.get("ok") else str(cert.get("why") or "invalid"),
                "n_rows": len(cert.get("rows") or []),
                "visible_rows": int(cert.get("visible_rows") or 0),
                "empty_asserted": bool(cert.get("empty_asserted")),
                "total_declared": cert.get("total_declared"),
            })
            if not cert.get("ok"):
                if page == 0:
                    # 首页都不可作证据 → 整份报告作废（调用方零写入）
                    out["partial"] = True
                    out["error"] = "页面不可作证据:%s" % (cert.get("why") or "invalid")
                    return out
                # 额外页不可读 → 停止翻页，但首页结论仍然有效（完整性不靠翻页）
                break
            if page == 0:
                out["page_ok"] = True
                out["empty_asserted"] = bool(cert.get("empty_asserted"))
                out["visible_rows"] = int(cert.get("visible_rows") or 0)
                out["total_declared"] = cert.get("total_declared")
            rows = list(cert.get("rows") or [])
            out["pages"].append(page)
            out["records"].extend(rows)
            if not rows:
                break
        out["ok"] = True
        return out

    def _hr_reconcile_site(self, domain: str, snap: Any = None) -> Dict[str, Any]:
        """单站三方对账（**只读**）：站点欠不欠 × 本机有没有种 × 账本有没有账单。

        产出三桶（**没有 settle 判定**）：
          - ``missing_local``：站点欠、本机没有 → 「需补种」（写动作走 ``confirm=1``）
          - ``present_no_bill``：站点欠、本机有、账本没账单 → 提示回填开账
          - ``safe_rotate_candidate``：本机有、站点未列欠、账本已结清 → 仅**提示**可轮换
            （**仅当本轮 infohash 覆盖完整时**才输出，避免半份数据误判）
        """
        dom = self._hrbills_norm_domain(domain)
        t0 = time.time()
        rep: Dict[str, Any] = {
            "site": dom, "ok": False, "partial": False, "error": "",
            "records_total": 0, "pages_fetched": 0,
            "missing_local": [], "present_no_bill": [], "safe_rotate_candidate": [],
            "cache_hits": 0, "torrents_fetched": 0, "hash_coverage_complete": False,
            "deferred": 0,
            "records": [],
            "page_ok": False, "list_complete": False, "list_complete_why": "",
            "empty_asserted": False, "visible_rows": 0, "total_declared": None,
            "bar": {}, "audit": [],
            "took_ms": 0,
        }
        site_id = self._hr_reconcile_site_id(dom)
        if not site_id:
            rep["error"] = "MP 站点表里找不到该域名（无法取 cookie）"
            rep["took_ms"] = int((time.time() - t0) * 1000)
            return rep
        fetched = self._hr_reconcile_fetch(site_id, dom)
        rep["pages_fetched"] = len(fetched.get("pages") or [])
        rep["error"] = str(fetched.get("error") or "")
        rep["partial"] = bool(fetched.get("partial"))
        if not fetched.get("ok"):
            rep["took_ms"] = int((time.time() - t0) * 1000)
            return rep
        records: List[Dict[str, Any]] = list(fetched.get("records") or [])
        rep["records_total"] = len(records)
        rep["page_ok"] = bool(fetched.get("page_ok"))
        rep["audit"] = list(fetched.get("audit") or [])
        if snap is None:
            try:
                snap = self._tag_all_torrents() or {}
            except Exception:  # noqa: BLE001
                snap = {}
        try:
            store = self._hrbills_store()
        except Exception:  # noqa: BLE001
            store = None
        cache = self._hr_reconcile_cache()
        now = time.time()
        # 本机该站的种（hash → TorrentInfo）：域名取 tracker 主机名，回退标签推断
        local: Dict[str, Any] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            dt = ""
            try:
                tr = str(getattr(t, "tracker", "") or "").strip().lower()
            except Exception:  # noqa: BLE001
                tr = ""
            if tr:
                dt = tr.split("://")[-1].split("/")[0].split(":")[0].strip()
            if not dt:
                try:
                    dt = self._hrbills_norm_domain(self._hr_domain("", t))
                except Exception:  # noqa: BLE001
                    dt = ""
            if dt and (dt == dom or dt.endswith("." + dom) or dom.endswith("." + dt)):
                local[hh] = t
        # 逐条记录解析 infohash（缓存优先；只对未命中且**粗配不上**的记录拉种）
        fetch_budget = int(HR_RECONCILE_MAX_FETCH)
        rec_hashes: Set[str] = set()
        claimed: Set[str] = set()      # 本机种**一对一**占用（防两个站点行粗配到同一种）
        coverage = True
        deferred = 0
        conn: Dict[str, Any] = {}
        rec_detail: List[Dict[str, Any]] = []   # 逐条明细（供 /agent/site/seeds 等站点级报表）
        for rec in records:
            tid = str(rec.get("tid") or "").strip()
            if not tid:
                coverage = False
                continue
            hit = cache.tid_get(dom, tid)
            if not hit:
                rough = self._hr_reconcile_rough_match(rec, local, claimed)
                if rough:
                    claimed.add(rough)
                    cache.tid_put(dom, tid, str(rough), str(rec.get("title") or ""),
                                  float(rec.get("size_gb") or 0.0), now)
                    hit = str(rough)
                elif fetch_budget > 0:
                    if not conn:
                        try:
                            conn = self._reseed_site_conn(site_id) or {}
                        except Exception:  # noqa: BLE001
                            conn = {}
                    hh = self._hr_reconcile_fetch_hash(site_id, dom, tid, conn)
                    fetch_budget -= 1
                    rep["torrents_fetched"] = int(rep["torrents_fetched"] or 0) + 1
                    if hh:
                        claimed.add(str(hh).strip().lower())
                        cache.tid_put(dom, tid, hh, str(rec.get("title") or ""),
                                      float(rec.get("size_gb") or 0.0), now)
                        hit = str(hh)
                else:
                    coverage = False
                    deferred += 1
            else:
                rep["cache_hits"] = int(rep["cache_hits"] or 0) + 1
                hit = str(hit.get("h") or "")
                if hit:
                    claimed.add(str(hit).strip().lower())
            if not hit:
                coverage = False
                rec_detail.append({
                    "tid": tid, "infohash": "", "title": str(rec.get("title") or "")[:160],
                    "size_gb": round(float(rec.get("size_gb") or 0.0), 3),
                    "need_left": str(rec.get("need_left") or ""),
                    "in_qb": False, "billed": False, "bill_state": "", "bill_rule": "",
                    "resolved": False,
                })
                continue
            rec_hashes.add(str(hit).strip().lower())
            hh = str(hit).strip().lower()
            present = hh in local
            bill = None
            try:
                bill = store.get(hh) if store is not None else None
            except Exception:  # noqa: BLE001
                bill = None
            rec_detail.append({
                "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:160],
                "size_gb": round(float(rec.get("size_gb") or 0.0), 3),
                "need_left": str(rec.get("need_left") or ""),
                "in_qb": bool(present), "billed": bool(bill is not None),
                "bill_state": str((bill or {}).get("state") or ""),
                "bill_rule": str((bill or {}).get("rule") or ""),
                "resolved": True,
            })
            if not present:
                rep["missing_local"].append({
                    "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:120],
                    "size_gb": float(rec.get("size_gb") or 0.0),
                    "need_h_left": str(rec.get("need_left") or ""),
                    "site": dom,
                    "reason_chain": [{
                        "rule": "hr_reconcile/missing_local", "verdict": "needs_reseed",
                        "inputs": {"tid": tid, "infohash": hh, "in_qb": False},
                        "source_of_truth": f"站点 myhr.php（{dom}） + 下载器快照 + hr_bills.json",
                        "at": now,
                    }],
                })
            elif bill is None:
                rep["present_no_bill"].append({
                    "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:120],
                    "site": dom,
                    "action_hint": "打魔流标签后跑 hrbills_tick 回填开账（只增保护）",
                })
        rep["hash_coverage_complete"] = bool(coverage)
        rep["deferred"] = int(deferred)
        rep["records"] = rec_detail
        if coverage:
            for hh, t in local.items():
                if hh in rec_hashes:
                    continue
                bill = None
                try:
                    bill = store.get(hh) if store is not None else None
                except Exception:  # noqa: BLE001
                    bill = None
                st = str((bill or {}).get("state") or "")
                if bill is not None and st in (BILL_STATE_SETTLED, BILL_STATE_VOID):
                    rep["safe_rotate_candidate"].append({
                        "infohash": hh, "title": str(getattr(t, "title", "") or "")[:120],
                        "bill_state": st, "site": dom,
                        "action_hint": "站点未列欠 + 账本已结清 → 可人工考虑轮换（**不自动删**）",
                    })
        # ★ 19.12.41：列表能不能自证完整 —— 用**页头聚合计数**做反向检验。
        #   · 计数不可解（单数字 / 缺栏 / 没抓到）或过期 → 判不了；
        #   · 计数与明细条数**不相等** → 明确矛盾（抓漏了 / 抓住改版页）→ 判不了；
        #   · 两者相等 → 这份列表就是该站的全部未结清记录（0 条也成立）。
        #   这一条取代了旧的「上一页不满 10 条 → 已到末页」猜测（实测无分页证据）。
        try:
            _cert0 = self._hr_bar_cert(dom, site_id=site_id, now=now)
        except Exception:  # noqa: BLE001
            _cert0 = {}
        rep["page"] = (fetched.get("audit") or [{}])[0] if fetched.get("audit") else {}
        rep["audit"] = list(fetched.get("audit") or [])
        rep["empty_asserted"] = bool(fetched.get("empty_asserted"))
        rep["visible_rows"] = int(fetched.get("visible_rows") or 0)
        rep["total_declared"] = fetched.get("total_declared")
        # 报告里只留**薄快照**（供闸门在实时快照缺失时回退；不含 cookie/正文）
        rep["bar"] = {
            "ok": bool(_cert0.get("src")),
            "ts": float(_cert0.get("ts") or 0.0),
            "hr": {"raw": _cert0.get("raw") or "",
                   "form": _cert0.get("form") or "",
                   "assessing": _cert0.get("assessing"),
                   "unfinished": _cert0.get("unfinished"),
                   "limit": _cert0.get("limit")},
        }
        _bar_total = _cert0.get("total")
        rep["bar_known"] = bool(_cert0.get("known"))
        rep["bar_stale"] = bool(_cert0.get("stale"))
        rep["bar_total"] = _bar_total
        _lc, _lc_why = _hr_list_complete(rep.get("page_ok"), rep.get("records_total"), _cert0)
        rep["list_complete"] = bool(_lc)
        rep["list_complete_why"] = _lc_why
        # ★ 17.3.0：ok 必须在**落盘之前**置 True。此前顺序相反，缓存里每份报告都带
        #   ok=false（无论 myhr.php 抓得多成功），于是 /agent/site/seeds 的 hr 列、
        #   records_total、missing_local 全被当成「这站还没对过账」——口径假象的根因。
        rep["ok"] = True
        # ★ 19.12.4：报告自带「证据时刻」。账单结清闸门（``hrbills._hr_site_verdict``）要拿
        #   它把 ``need_left`` 按时间衰减外推；缺这个字段就只能退化成 ``last_ok_ts``，
        #   而那是「最后一次成功」的时刻，跟这份报告未必同源。放这里（而不是初值）是因为
        #   **只有成功拿到完整视图的报告才配当证据**。
        rep["at"] = float(now)
        rep["took_ms"] = int((time.time() - t0) * 1000)
        try:
            cache.put_report(dom, {k: v for k, v in rep.items() if k != "took_ms"})
            cache.save()
        except Exception:  # noqa: BLE001
            pass
        return rep

    @staticmethod
    def _hr_title_tokens(s: Any) -> Set[str]:
        """标题 → 归一化 token 集合（数字/拉丁/汉字；丢掉分隔符与大小写差异）。"""
        t = unicodedata.normalize("NFKC", str(s or "")).lower()
        t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", t)
        return {x for x in t.split() if x}

    @classmethod
    def _hr_reconcile_rough_match(cls, rec: Dict[str, Any], local: Dict[str, Any],
                                  claimed: Optional[Set[str]] = None) -> str:
        """标题 token 粗配（压拉种量）：高分且**唯一**才认 → 返回本机 hash，否则 ``""``（去拉种）。

        ★ 实测：站点标题是**罗马化**（``Zheng Tu 2026 S01 E11-E12 ... -PTerWEB``），
        而 qB 名字常带中文（``征途.Zheng.Tu.2026...``）→ 旧的「前缀相等」命中率 ~0；
        改 **token Jaccard ≥ 0.80（且交集 ≥ 2）且与次优差距 ≥ 0.1**（避免同剧不同集互吃）。
        例：站点 ``The Old Story of Yu Hong 2026 S01 E14-E17 2160p ... PTerWEB`` vs qB
        ``余红旧事.The.Old.Story.of.Yu.Hong.2026.S01.2160p...PTerWEB`` → Jaccard 0.84 → 命中。

        ★ 例外：站点行**不带体积**（myhr 列里的 GB 是上传/下载量，**不是种子体积**）
        → 粗配**不得拿体积当闸门**（旧版因此把 CARPT 全判不中）。
        """
        A = cls._hr_title_tokens(rec.get("title"))
        if not A:
            return ""
        claimed = claimed or set()
        scored: List[Any] = []
        for hh, t in (local or {}).items():
            key = str(hh or "").strip().lower()
            if not key or key in claimed:
                continue
            B = cls._hr_title_tokens(getattr(t, "title", ""))
            if not B:
                continue
            inter = len(A & B)
            if inter < 2:
                continue
            jac = inter / max(1, len(A | B))
            if jac >= 0.5:
                scored.append((jac, key))
        if not scored:
            return ""
        scored.sort(reverse=True)
        top = scored[0]
        if top[0] < 0.80:
            return ""
        if len(scored) > 1 and (top[0] - scored[1][0]) < 0.1:
            return ""          # 同分双胞胎（同剧不同集）→ 不敢认，去拉种
        return top[1]

    def _hr_reconcile_fetch_hash(self, site_id: int, dom: str, tid: str,
                                 conn: Dict[str, Any]) -> str:
        """取该 tid 的 ``.torrent`` 算 infohash（NexusPHP ``download.php?id=`` 唯一可靠路径）。"""
        url = f"https://{dom}/download.php?id={tid}"
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None:
            return ""
        data = None
        try:
            data = dl.fetch_torrent_bytes(url, cookie=(conn or {}).get("cookie"),
                                          user_agent=(conn or {}).get("ua"),
                                          referer=((conn or {}).get("url") or None))
        except Exception:  # noqa: BLE001
            data = None
        finally:
            try:
                self._pv_spend(int(site_id), "hr", 1)
            except Exception:  # noqa: BLE001
                pass
        if not data or data[:1] != b"d":
            return ""
        try:
            return str(info_hash(data) or "").strip().lower()
        except Exception:  # noqa: BLE001
            return ""

    def _hr_reconcile_target_task(self, dom: str) -> Dict[str, Any]:
        """该站对应的任务（取保存目录 + 标签）。找不到 → 空。"""
        try:
            tasks = list((self._task_configs or {}).values())
        except Exception:  # noqa: BLE001
            tasks = []
        for task in tasks:
            cand = ""
            for attr in ("site_domain", "site"):
                try:
                    cand = self._hrbills_norm_domain(getattr(task, attr, "") or "")
                except Exception:  # noqa: BLE001
                    cand = ""
                if cand:
                    break
            if cand and (cand == dom or cand.endswith("." + dom) or dom.endswith("." + cand)):
                return {
                    "task_id": str(getattr(task, "id", "") or ""),
                    "save_path": str(getattr(task, "save_path", "") or ""),
                    "tag": str(getattr(task, "brush_tag", "") or ""),
                    "site_domain": dom,
                }
        return {}

    def _hr_reconcile_add_one(self, dom: str, tid: str, infohash: str = "",
                              save_path: str = "") -> Dict[str, Any]:
        """**同站重下**（写动作，必须由 ``confirm=1`` 显式触发后调用）。

        ★ 与 ``rescue`` 的区别（pro 评审否决了复用 rescue）：rescue 语义是「从**无 H&R
        的他站**补同 Release 来辅」，且 ``rescue_source_blocked`` 对 ``hr=True`` 的站一律
        禁用 —— 拿它补欠债站自己的种，会被自己拦掉。这里是**还自己的债**：从**同一个
        欠债站**按 ``download.php?id=<tid>`` 重下原始种。
        三重保护：① 该 infohash 已在 qB → 不下；② 缓存到 infohash 永久化；③ 只在此函数写。
        """
        dom = self._hrbills_norm_domain(dom)
        tgt = self._hr_reconcile_target_task(dom)
        dest = str(save_path or tgt.get("save_path") or "").strip()
        if not dest:
            return {"tid": tid, "ok": False, "err": "未配置保存目录（避免落到下载器默认目录）"}
        site_id = self._hr_reconcile_site_id(dom)
        if not site_id:
            return {"tid": tid, "ok": False, "err": "MP 站点表里找不到该域名"}
        if infohash:
            try:
                if str(infohash).strip().lower() in (self._tag_all_torrents() or {}):
                    return {"tid": tid, "ok": False, "skipped": "已在下载器",
                            "err": "该 infohash 已在下载器（跳过，避免重复下载）"}
            except Exception:  # noqa: BLE001
                pass
        try:
            conn = self._reseed_site_conn(site_id) or {}
        except Exception:  # noqa: BLE001
            conn = {}
        url = f"https://{dom}/download.php?id={tid}"
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None:
            return {"tid": tid, "ok": False, "err": "下载器不可用"}
        data = None
        try:
            data = dl.fetch_torrent_bytes(url, cookie=conn.get("cookie"),
                                          user_agent=conn.get("ua"),
                                          referer=(conn.get("url") or None))
        except Exception as e:  # noqa: BLE001
            data = None
            return {"tid": tid, "ok": False, "err": f"取种失败:{e}"}
        finally:
            try:
                self._pv_spend(site_id, "hr", 1)
            except Exception:  # noqa: BLE001
                pass
        if not data or data[:1] != b"d":
            return {"tid": tid, "ok": False, "err": "取到的不是种子（站点拒绝 / 需登录 / PV 拦截）"}
        try:
            nh = str(info_hash(data) or "").strip().lower()
        except Exception:  # noqa: BLE001
            nh = ""
        if not nh:
            return {"tid": tid, "ok": False, "err": "算不出 infohash（种子损坏？）"}
        if nh in (self._tag_all_torrents() or {}):
            return {"tid": tid, "ok": False, "new_hash": nh, "skipped": "已在下载器"}
        tag = str(tgt.get("tag") or "") or f"魔流-{dom.split('.')[0]}-{HR_RECONCILE_TAG_SUFFIX}"
        try:
            got, err = dl.add_torrent(content=data, download_dir=dest, tag=tag,
                                      site_domain=dom)
        except Exception as e:  # noqa: BLE001
            return {"tid": tid, "ok": False, "err": str(e)}
        if not got:
            return {"tid": tid, "ok": False, "err": str(err or "添加失败")}
        try:
            cache = self._hr_reconcile_cache()
            cache.tid_put(dom, str(tid), str(got), "", 0.0, time.time())
            cache.save()
        except Exception:  # noqa: BLE001
            pass
        self._hr_reconcile_journal(dom, str(tid), str(got))
        self._log(f"站点对账:按站点 myhr 从 {dom} 重下欠 H&R 种 tid={tid}（{str(got)[:12]}…）")
        return {"tid": tid, "ok": True, "new_hash": str(got), "tag": tag, "save_path": dest}

    def _hr_reconcile_journal(self, dom: str, tid: str, new_hash: str) -> None:
        """对账重下台账（journal kind=hr_reconcile；写失败静默）。"""
        try:
            journal = getattr(getattr(self, "_store", None), "journal", None)
            fn = getattr(journal, "record", None) if journal is not None else None
            if not callable(fn):
                return
            from ..persistence import OperationItem  # noqa: WPS433
            fn(task_id="", kind="hr_reconcile", items=[OperationItem(
                hash=str(new_hash), title=f"站点对账重下 {dom} tid={tid}",
                reason=f"站点 myhr 显示欠 H&R、本机没有种 → 同站重下（{str(new_hash)[:12]}…）",
                size_gb=0.0, source="hr_reconcile")])
        except Exception:  # noqa: BLE001
            pass

    def _hr_reconcile_round(self, force: bool = False) -> Dict[str, Any]:
        """一轮站点对账（**只读 + 只回填提示**；**不**自动重下、**不**改任何账单状态）。

        写动作（重下）只在 ``?action=hr_reconcile&confirm=1`` 里逐条发生。
        """
        if not HR_RECONCILE_ENABLED and not force:
            return {"enabled": False, "reason": "HR_RECONCILE_ENABLED=False"}
        cache = self._hr_reconcile_cache()
        now = time.time()
        try:
            last = float(cache.last_run_ts() or 0.0)
        except Exception:  # noqa: BLE001
            last = 0.0
        if not force and (now - last) < float(HR_RECONCILE_HOURS) * 3600.0:
            return {"enabled": True, "skipped": "interval", "last_run_ts": last}
        reports: List[Dict[str, Any]] = []
        deadline = now + float(HR_RECONCILE_TIME_BUDGET)
        for s in self._hr_reconcile_sites():
            dom = str(s.get("domain") or "")
            if not force:
                try:
                    if not cache.site_due(dom, time.time()):
                        continue
                except Exception:  # noqa: BLE001
                    pass
            if time.time() > deadline:
                reports.append({"site": dom, "ok": False, "error": "本轮时间预算用尽，下轮继续"})
                break
            try:
                rep = self._hr_reconcile_site(dom)
            except Exception as e:  # noqa: BLE001
                rep = {"site": dom, "ok": False, "error": str(e)}
            try:
                cache.note_result(dom, bool(rep.get("ok")), time.time(),
                                  int(rep.get("fail_count") or 0) + (0 if rep.get("ok") else 1))
            except Exception:  # noqa: BLE001
                pass
            reports.append(rep)
        if reports:
            try:
                cache.set_last_run(time.time())
            except Exception:  # noqa: BLE001
                pass
        try:
            cache.flush()
        except Exception:  # noqa: BLE001
            pass
        summary = {"enabled": True, "sites": len(reports), "reports": reports,
                   "missing_total": sum(len(r.get("missing_local") or []) for r in reports),
                   "at": time.time()}
        try:
            _miss = int(summary["missing_total"] or 0)
            if _miss:
                self._log(f"站点 H&R 对账:{summary['sites']} 站 · **{_miss} 条「站点说欠、本机没有」**"
                          f"（需人工确认后重下；只报不动）", "warning")
        except Exception:  # noqa: BLE001
            pass
        return summary

    def _hr_reconcile_report(self, site: str = "") -> Dict[str, Any]:
        """读上一次对账结果（**默认不联网**，秒回）；``live`` 由 AI 端点显式要求。

        ★ 19.12.4：报告的 key 是 **MP 站点域名**（实测 ``pt.btschool.club``），而调用方
        通常传**裸域**（``btschool.club``）→ ``get_report(裸域)`` 永远取不到，端点回
        「该站还没有对账结果」（明明刚对过）。现按「互为后缀」再找一次，与
        ``hrbills._hr_site_verdict`` 的域名口径统一。
        """
        cache = self._hr_reconcile_cache()
        dom = self._hrbills_norm_domain(site)
        try:
            if dom:
                rep = cache.get_report(dom)
                if not rep:
                    for _k, _v in (cache.reports() or {}).items():
                        _k = str(_k or "")
                        if isinstance(_v, dict) and _k and (
                                _k == dom or _k.endswith("." + dom) or dom.endswith("." + _k)):
                            rep = dict(_v)
                            break
                if not rep:
                    return {"enabled": bool(HR_RECONCILE_ENABLED), "site": dom,
                            "ok": False, "error": "该站还没有对账结果（先跑一轮）",
                            "sites": [], "write": {"run_now": "GET /agent/hr/reconcile?live=1"}}
                return {"enabled": bool(HR_RECONCILE_ENABLED), "site": dom, "ok": True,
                        "report": rep, "last_run_ts": cache.last_run_ts()}
            return {"enabled": bool(HR_RECONCILE_ENABLED),
                    "sites": cache.reports(), "last_run_ts": cache.last_run_ts(),
                    "interval_hours": float(HR_RECONCILE_HOURS),
                    "site_status": cache.site_status()}
        except Exception as e:  # noqa: BLE001
            return {"enabled": bool(HR_RECONCILE_ENABLED), "ok": False, "error": str(e)}

    def _hr_reconcile_apply(self, site: str, tids: Any = None,
                            confirm: Any = None, save_path: str = "") -> Dict[str, Any]:
        """按站点 myhr 的「需补种」清单重下（**默认干跑**；真写必须 ``confirm=1``）。

        只处理**站点当前确实还欠**且**本机没有**的记录（重跑一次实时对账取准），
        逐条走 ``_hr_reconcile_add_one``（同站重下）。**只加不删**。
        """
        dom = self._hrbills_norm_domain(site)
        if not dom:
            return {"ok": False, "error": "缺少 site（域名）"}
        try:
            want = {str(t).strip() for t in (tids if isinstance(tids, (list, tuple, set))
                                             else str(tids or "").split(",")) if str(t).strip()}
        except Exception:  # noqa: BLE001
            want = set()
        rep = self._hr_reconcile_site(dom)
        if not rep.get("ok"):
            return {"ok": False, "error": rep.get("error") or "对账失败", "site": dom}
        pool = [r for r in (rep.get("missing_local") or [])
                if not want or str(r.get("tid")) in want]
        dry = not bool(confirm)
        plan: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        for r in pool:
            if dry:
                plan.append({"tid": r.get("tid"), "action": "add", "dry": True,
                             "title": r.get("title"), "size_gb": r.get("size_gb"),
                             "need_h_left": r.get("need_h_left")})
                continue
            res = self._hr_reconcile_add_one(dom, str(r.get("tid") or ""),
                                             str(r.get("infohash") or ""), save_path=save_path)
            results.append(res)
            plan.append({"tid": r.get("tid"), "action": "add", "ok": bool(res.get("ok")),
                         "new_hash": res.get("new_hash") or "", "err": res.get("err") or ""})
        out = {"ok": True, "dry_run": dry, "site": dom, "candidates": len(pool),
               "plan": plan}
        if not dry:
            out["results"] = results
            out["added"] = sum(1 for r in results if r.get("ok"))
        else:
            out["would_add"] = len(plan)
        return out


# ============================================================================
# ★ 11.8.0 模块级：对账缓存（**不挂 MagicFlowStore**）
# ============================================================================
#   页面解析（``myhr.php`` → 行 dict / 页面凭证）已按铁律 1 搬进
#   ``collect_parse.parse_myhr_page``，上面经 ``collect`` 的 re-export 以
#   ``_hr_myhr_page`` 别名导入（★ 19.12.41：只要这一个符号 —— 旧的
#   ``parse_myhr_rows`` 别名已无用，留着只会多一条 import 期契约）。

class HrReconcileCache:
    """对账缓存（**派生数据，不是真值源**）：``tid→infohash`` 索引 + 每站退避 + 上次报告。

    持久化 ``hr_reconcile.json``（原子写 tmp→rename）；**绝不挂 ``MagicFlowStore``**
    （进程级单例热重载不重建）。tid→infohash 对同一种子近似不可变 → 主策略**永久缓存**
    （按 ``seen_at`` 90 天修剪防无界膨胀）。
    """

    kv_region = "hrreconcile"
    FILE_MIN_INTERVAL = 5.0
    TID_TTL_DAYS = 90.0

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "hr_reconcile.json"
        self.data: Dict[str, Any] = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}
        self._lock = threading.RLock()
        self._last_file_write = 0.0
        self._pending = False
        self.kv = kv
        self.load()

    def kv_bind(self, kv: Any) -> None:
        self.kv = kv

    # ------------------------------------------------------------ 载入 / 落盘
    def load(self) -> None:
        """读 ``hr_reconcile.json``，只收 dict 类型的四个分区，其余一律回落到空表。

        为什么不是「读不到就抛」：这份是**派生缓存**（可随时重算），坏文件只该让对账
        变慢，不该让插件加载失败；代价是坏文件会一直留在盘上供取证，不会自愈。
        """
        try:
            if self.file.exists():
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    base = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}
                    for k in base:
                        v = data.get(k)
                        if isinstance(v, dict):
                            base[k] = v
                    self.data = base
        except Exception:  # noqa: BLE001
            self.data = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}

    def _write_file(self) -> None:
        """原子落盘：先写 ``.tmp`` 再 rename，避免半截 JSON 被下次载入读到。

        写失败**静默**（目录只读 / 磁盘满都当没发生）：缓存丢了下一轮会重算，
        但抛异常会把对账整轮打断 —— 脏数据比办不成事更麻烦。
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:  # noqa: BLE001
            pass

    def save(self, force: bool = False) -> None:
        """落盘（默认节流）：5 秒内多次调用只留最后一次，由 ``flush()`` 补写。

        为什么要节流：一轮对账对每个站点都会 ``note_result`` / ``tid_put``，几十站
        逐个全量写 JSON 会把这次对账变成磁盘 IO 压测。
        """
        with self._lock:
            now = time.time()
            if force or (now - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file()
                self._last_file_write = now
                self._pending = False
            else:
                self._pending = True

    def flush(self) -> None:
        """补写被 ``save()`` 节流掉的那次改动（进程退出 / 轮次结束前必须调）。

        不调也不会丢真值 —— 丢的只是「下次少学一遍 tid→hash」，代价是重拉页面。
        """
        with self._lock:
            if self._pending or (time.time() - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file()
                self._last_file_write = time.time()
                self._pending = False

    # ------------------------------------------------------------ 运行状态
    def last_run_ts(self) -> float:
        """上一轮对账的时刻（0 = 从没跑过）。读不出来按 0 算 = 「该跑了」的保守方向。"""
        try:
            return float((self.data.get("meta") or {}).get("last_run_ts") or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    def set_last_run(self, ts: float) -> None:
        with self._lock:
            self.data.setdefault("meta", {})["last_run_ts"] = float(ts)
            self.save()

    def site_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.data.get("sites") or {})

    def site_due(self, domain: str, now: float) -> bool:
        """该站是否到了下一次可抓的时刻（退避窗口已过）。

        读不出 ``next_try_ts`` 时返回 True：退避是**省流量**用的，不是安全边界，
        数据坏了就该照常抓，别因为缓存脏了把整站永久跳过。
        """
        d = str(domain or "").strip().lower()
        with self._lock:
            st = (self.data.get("sites") or {}).get(d) or {}
        try:
            return now >= float(st.get("next_try_ts") or 0.0)
        except Exception:  # noqa: BLE001
            return True

    def note_result(self, domain: str, ok: bool, now: float, fail_count: int = 0) -> None:
        """记一次结果：成功 → 清退避；失败 → 指数退避（阶梯封顶）。"""
        d = str(domain or "").strip().lower()
        if not d:
            return
        with self._lock:
            st = dict((self.data.get("sites") or {}).get(d) or {})
            if ok:
                st.update({"last_ok_ts": float(now), "fail_count": 0, "next_try_ts": 0.0})
            else:
                fc = max(1, int(fail_count or 1))
                steps = list(HR_RECONCILE_BACKOFF_HOURS) or [6.0]
                backoff = float(steps[min(fc - 1, len(steps) - 1)]) * 3600.0
                st.update({"fail_count": fc, "next_try_ts": float(now) + backoff})
            self.data.setdefault("sites", {})[d] = st
            self.save()

    # ------------------------------------------------------------ tid 索引
    def tid_get(self, domain: str, tid: str) -> Optional[Dict[str, Any]]:
        """取该站该 tid 已算出的 infohash（命中就省一次 ``.torrent`` 下载）。

        返 ``None`` = 没算过或缓存过期；调用方据此去拉 .torrent，不做二次推测。
        """
        d = str(domain or "").strip().lower()
        t = str(tid or "").strip()
        with self._lock:
            row = ((self.data.get("tid_index") or {}).get(d) or {}).get(t)
        return dict(row) if isinstance(row, dict) else None

    def tid_put(self, domain: str, tid: str, infohash: str, title: str = "",
                size_gb: float = 0.0, now: float = 0.0) -> None:
        """记一条 ``tid → infohash``（永久缓存主力：同一种子的 hash 近似不可变）。

        只在三个值都齐时才写；``tid_put`` 顺带在本站索引上做一次过期修剪，
        **不落盘** —— 由调用方统一 ``save()``，一轮几十站只写一次文件。
        """
        d = str(domain or "").strip().lower()
        t = str(tid or "").strip()
        h = str(infohash or "").strip().lower()
        if not (d and t and h):
            return
        with self._lock:
            idx = self.data.setdefault("tid_index", {}).setdefault(d, {})
            idx[t] = {"h": h, "t": str(title or "")[:120], "s": round(float(size_gb or 0.0), 3),
                      "at": float(now or time.time())}
            self._prune_locked(d)

    def _prune_locked(self, domain: str) -> None:
        """按 ``seen_at`` 修剪（默认 90 天），防索引无界膨胀。"""
        try:
            idx = (self.data.get("tid_index") or {}).get(domain) or {}
            cutoff = time.time() - float(self.TID_TTL_DAYS) * 86400.0
            dead = [k for k, v in idx.items()
                    if isinstance(v, dict) and float(v.get("at") or 0.0) < cutoff]
            for k in dead:
                idx.pop(k, None)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 报告
    def put_report(self, domain: str, report: Dict[str, Any]) -> None:
        """存该站上一轮对账报告（给「秒回」端点用，不必重新联网）。"""
        d = str(domain or "").strip().lower()
        if not d:
            return
        with self._lock:
            self.data.setdefault("reports", {})[d] = dict(report or {})

    def get_report(self, domain: str) -> Optional[Dict[str, Any]]:
        """读该站上一轮报告；``None`` = 没跑过，调用方**不得**当成「站点说不欠」。"""
        d = str(domain or "").strip().lower()
        with self._lock:
            rep = (self.data.get("reports") or {}).get(d)
        return dict(rep) if isinstance(rep, dict) else None

    def reports(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.data.get("reports") or {})


def get_hr_reconcile_cache(data_dir: Path, kv: Any = None) -> HrReconcileCache:
    """取/建**进程级**对账缓存（按 data_dir 单例，跨热重载存活）。

    ★ 照 ``get_hr_bills_store`` / ``persistence.get_gate_store`` 一模一样：用同一套
    ``_shared()`` 注册表单独持有实例，热重载后仍指向同一对象（否则新类拿不到旧实例）。
    """
    key = f"hrreconcile:{Path(data_dir)}"
    sh = _shared()
    with sh.lock:
        obj = sh.singletons.get(key)
        if obj is not None and not isinstance(obj, HrReconcileCache):
            try:
                obj.flush()
            except Exception:  # noqa: BLE001
                pass
            obj = None
        if obj is None:
            obj = HrReconcileCache(data_dir, kv=kv)
            sh.singletons[key] = obj
        elif kv is not None:
            try:
                obj.kv_bind(kv)
            except Exception:  # noqa: BLE001
                pass
    return obj
