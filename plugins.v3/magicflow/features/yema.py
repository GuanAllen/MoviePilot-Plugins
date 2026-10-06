# -*- coding: utf-8 -*-
"""魔流 · 野马PT（YemaPT）逐种 H&R 权威接口（11.9.0）。

野马PT 的 H&R **没有站点级规则**，是**发布者逐种开关** ``hrPunishEnable``（Master 2026-10-05
定论）→ 唯一权威来源是「问站点」。站点自带后台接口（**cookie 鉴权**，必须容器内跑）：

  · ``POST /api/torrent/fetchUserTorrentList`` body ``{"pageParam":{"current":N,"pageSize":20}}``
      → 逐种：``torrentId / showName / shortDesc / fileSize / hrPunishEnable / hrStatus``
      · ``pageSize > 20`` → 返回 0 行（**必须分页**）
      · 不带 ``Accept: application/json`` → ``{"success":false}``（**实测**，看着像没登录）
  · ``POST /api/torrent/fetchUserTorrentCount`` → 当前用户种子总数
  · ``GET  /api/torrent/download?id=<tid>`` → **原始 .torrent**（算 infohash，把站点行与账本/下载器
      精确对上；``fetchTorrentIdWithPiecesHash`` 反查的是「pieces 哈希」不是 infohash，**实测为空**）
  · ``POST /api/userTorrent/absolve`` body ``{"torrentId":N}`` → **免罪**（扣站点积分；写操作）

本模块只做两件事：

  ① **对账（只读）**：站点说「还欠」的种 × 本机有没有 × 账本记没记 → 漏记/漏挂可见；
  ② **免罪写路径**：默认**干跑**（只报目标行 + 成本说明），``confirm=1`` 才真写。

★ 铁律（与 11.8.0「第三视角」一致，长期有效）：
  · 站点视角**只能判「还欠」**；``settled`` 永远只归 ``seed_hours_for_hr``
    → 本模块**不产 settled、不自动作废任何账单**；
  · 应用动作**只增保护**（给「本机有、站点说欠、账本没记」的种补开账单）；摘保护仍走人工作废；
  · 绝不在日志/响应里回显 cookie / apikey / token（出口统一 ``_agent_scrub``）。
"""

import time
from typing import Any, Dict, List, Optional

from .hrbills import (
    BILL_STATE_ACTIVE,
    BILL_STATE_VOID,
    RULE_HIT_AND_RUN,
    RULE_SITE_HR,
    RULE_UNKNOWN,
    get_hr_reconcile_cache,
)

# ── 常量（★ 必须在类定义之前求值：写进函数默认参数会在「定义时」求值）
YEMA_ENABLED = True
YEMA_ABSOLVE_ENABLED = True
YEMA_DOMAINS = ("yemapt.org", "www.yemapt.org")
YEMA_LIST_PATH = "/api/torrent/fetchUserTorrentList"
YEMA_COUNT_PATH = "/api/torrent/fetchUserTorrentCount"
YEMA_DOWNLOAD_PATH = "/api/torrent/download"
YEMA_ABSOLVE_PATH = "/api/userTorrent/absolve"
YEMA_PAGE_SIZE = 20
YEMA_MAX_PAGES = 30
YEMA_TIME_BUDGET = 240.0
YEMA_KIND = "hr"
YEMA_HOURS = 6.0
YEMA_REPORT_KEY = "yema"
#: 站点的 ``hrStatus`` → 是否仍属「欠」的状态（保守：Pass/Absolve 才是已了结）
YEMA_OPEN_STATES = ("NotStart", "Running", "Fail")
YEMA_DONE_STATES = ("Pass", "Absolve")


# ============================================================ 纯函数（可单测）

def yema_domain_of(tracker: str) -> str:
    """从 tracker/announce 串取域名（小写）。"""
    t = str(tracker or "").strip()
    if not t:
        return ""
    try:
        host = t.split("://")[-1].split("/")[0].split(":")[0].strip().lower()
    except Exception:  # noqa: BLE001
        return ""
    return host


def yema_is_yema_domain(domain: str) -> bool:
    """站点域名是否野马PT（含子域）。"""
    d = str(domain or "").strip().lower()
    return any(d == x or d.endswith("." + x) for x in YEMA_DOMAINS)


def yema_row_obligation(row: Dict[str, Any]) -> Dict[str, Any]:
    """一行站点记录 → 「还欠不欠」判定（**纯函数**）。

    判据只有两个字段：``hrPunishEnable``（发布者逐种开关）+ ``hrStatus``（考核状态）。
    ``hrStatus`` 语义（站点枚举）：``Default`` 未启用 / ``NotStart`` 未开始 / ``Running``
    考核中 / ``Pass`` 已通过 / ``Fail`` 未达标 / ``Absolve`` 已免罪。

    ★ 保守方向：``hrPunishEnable=True`` 且状态**不是** Pass/Absolve → 一律算「欠」
    （含未知状态）；只有明确 `Pass/Absolve` 或 `hrPunishEnable=False` 才算不欠。
    """
    st = str((row or {}).get("hrStatus") or "").strip()
    punish = bool((row or {}).get("hrPunishEnable"))
    if st in YEMA_DONE_STATES:
        return {"owes": False, "why": f"站点状态 {st}（已通过/已免罪）", "status": st, "punish": punish}
    if punish:
        _w = "考核中" if st in YEMA_OPEN_STATES else f"状态 {st or '(空)'}"
        return {"owes": True, "why": f"逐种标记 hrPunishEnable=true（{_w}）", "status": st, "punish": punish}
    if st in YEMA_OPEN_STATES:
        return {"owes": False, "why": f"{st} 但 hrPunishEnable=false（发布者未开考核）", "status": st, "punish": punish}
    return {"owes": False, "why": f"状态 {st or '(空)'} 且未开逐种考核 → 不判义务", "status": st, "punish": punish}


def yema_row_view(row: Dict[str, Any]) -> Dict[str, Any]:
    """一行站点记录 → 精简视图（无密）。"""
    r = dict(row or {})
    try:
        size_gb = round(float(r.get("fileSize") or 0) / (1024 ** 3), 3)
    except Exception:  # noqa: BLE001
        size_gb = 0.0
    _ob = yema_row_obligation(r)
    return {
        "tid": int(r.get("torrentId") or 0),
        "name": str(r.get("showName") or "")[:120],
        "desc": str(r.get("shortDesc") or "")[:80],
        "size_gb": size_gb,
        "punish": bool(r.get("hrPunishEnable")),
        "hr_status": _ob.get("status") or "",
        "owes": bool(_ob.get("owes")),
        "why": _ob.get("why") or "",
        "is_seeder": str(r.get("isSeeder") or "") == "y",
        "finished": str(r.get("isFinish") or "") == "y",
    }


# ============================================================ Mixin

class YemaHrMixin:
    """野马PT 逐种 H&R：对账（只读）+ 免罪（写，默认干跑）。"""

    # ------------------------------------------------------------ 定位 / 开关
    def _yema_enabled(self) -> bool:
        return bool(YEMA_ENABLED)

    def _yema_site_row(self) -> Optional[Dict[str, Any]]:
        """找野马PT 的 MP 站点记录（按域名，**不猜站名**）。

        取 ``_reseed_mp_sites()``（``SiteOper`` 优先，含未启用站；实测 ``_list_sites()``
        在插件上下文外常常拿不到全量），拿不到再回落 ``_list_sites()``。
        """
        rows: List[Dict[str, Any]] = []
        try:
            rows = list(self._reseed_mp_sites() or [])
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            try:
                rows = list(self._list_sites() or [])
            except Exception:  # noqa: BLE001
                rows = []
        for row in rows:
            dom = str(row.get("domain") or "").strip().lower()
            if not yema_is_yema_domain(dom):
                # ★ 与 rescue 同款：MP 站点项可能只有中文名（`domain` 空）→ 名→域名 解析。
                try:
                    dom = str(self._site_domain_by_name(str(row.get("name") or ""))
                              or dom).strip().lower()
                except Exception:  # noqa: BLE001
                    pass
            if yema_is_yema_domain(dom):
                return row
        return None

    def _yema_cache(self) -> Any:
        """复用 11.8.0 的模块级对账缓存（tid→infohash 索引 + 报告；**热重载后仍同一对象**）。"""
        try:
            data_dir = self.get_data_path()
        except Exception:  # noqa: BLE001
            data_dir = "."
        try:
            kv = getattr(self, "_hot", None)
        except Exception:  # noqa: BLE001
            kv = None
        try:
            return get_hr_reconcile_cache(data_dir, kv=kv)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------ 列种子（API）
    def _yema_rows(self, *, force: bool = False, max_pages: int = 0) -> Dict[str, Any]:
        """拉全量「我的种子」列表（分页；撞上限如实返回 ``truncated``）。"""
        site = self._yema_site_row()
        if not site:
            return {"ok": False, "error": "未找到野马PT 站点（域名 yemapt.org）", "rows": []}
        sid = int(site.get("id") or 0)
        c = self._collect_ref()
        if c is None:
            return {"ok": False, "error": "采集模块未就绪", "rows": [], "site_id": sid}
        view = c.site(sid)
        cap = int(max_pages or YEMA_MAX_PAGES)
        rows: List[Dict[str, Any]] = []
        pages = 0
        err = ""
        for p in range(1, cap + 1):
            res = view.post_json(
                YEMA_LIST_PATH,
                {"pageParam": {"current": p, "pageSize": YEMA_PAGE_SIZE}},
                kind=YEMA_KIND,
                force=force,
            )
            if not res.get("ok"):
                err = str(res.get("error") or "请求失败")
                break
            data = res.get("data")
            page_rows = None
            if isinstance(data, dict):
                page_rows = data.get("data")
                if page_rows is None and data.get("success") is False:
                    err = "站点拒绝（success=false → 检查 cookie / Accept 头）"
                    break
            if not isinstance(page_rows, list):
                err = "响应结构不含 data[]"
                break
            rows.extend([x for x in page_rows if isinstance(x, dict)])
            pages += 1
            if len(page_rows) < YEMA_PAGE_SIZE:
                break
        return {
            "ok": not err,
            "error": err,
            "rows": rows,
            "pages": pages,
            "truncated": bool(pages >= cap and len(rows) >= cap * YEMA_PAGE_SIZE),
            "site_id": sid,
        }

    def _yema_count(self) -> int:
        """站点侧「我的种子总数」（只用来对账页数是否吃全）。"""
        site = self._yema_site_row()
        if not site:
            return 0
        c = self._collect_ref()
        if c is None:
            return 0
        try:
            res = c.site(int(site.get("id") or 0)).post_json(YEMA_COUNT_PATH, {}, kind=YEMA_KIND)
            if res.get("ok") and isinstance(res.get("data"), int):
                return int(res.get("data") or 0)
            d = res.get("data")
            if isinstance(d, dict):
                return int(d.get("data") or 0)
        except Exception:  # noqa: BLE001
            return 0
        return 0

    def _yema_hash_for_tid(self, tid: Any, site: Dict[str, Any], cache: Any) -> Dict[str, Any]:
        """站点 ``torrentId`` → infohash（**下载原始 .torrent 再算**；结果永久缓存）。

        ★ 为什么不用 ``fetchTorrentIdWithPiecesHash``：它反查的是「pieces 哈希」
        （客户端算的 sha1(pieces)），**不是** infohash —— 实测我们 15 个种的 infohash
        传给它是空结果。
        """
        dom = "yemapt.org"
        t = str(tid or "").strip()
        if not t:
            return {"ok": False, "error": "缺少 tid"}
        if cache is not None:
            hit = cache.tid_get(dom, t)
            if isinstance(hit, dict) and hit.get("h"):
                return {"ok": True, "hash": str(hit.get("h")), "cached": True}
        try:
            conn = self._reseed_site_conn(int(site.get("id") or 0)) or {}
        except Exception:  # noqa: BLE001
            conn = {}
        base = str(conn.get("url") or site.get("url") or f"https://{site.get('domain')}").rstrip("/")
        url = f"{base}{YEMA_DOWNLOAD_PATH}?id={t}"
        try:
            dl = self._get_downloader("qbittorrent")
            raw = dl.fetch_torrent_bytes(
                url, cookie=conn.get("cookie"), user_agent=conn.get("ua"), referer=f"{base}/"
            ) if dl is not None else None
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": f"取种失败: {err}"}
        if not raw:
            return {"ok": False, "error": "取种失败（无字节）"}
        h = ""
        try:
            from ..fingerprint import info_hash  # noqa: WPS433

            h = str(info_hash(raw) or "").strip().lower()
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": f"算 infohash 失败: {err}"}
        if not h:
            return {"ok": False, "error": "算 infohash 失败（空）"}
        if cache is not None:
            try:
                cache.tid_put(dom, t, h)
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "hash": h, "cached": False}

    # ------------------------------------------------------------ 本机 / 账本
    def _yema_local(self) -> Dict[str, Any]:
        """本机野马PT 的种（hash → TorrentInfo）。"""
        out: Dict[str, Any] = {}
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        for h, t in snap.items():
            if yema_is_yema_domain(yema_domain_of(getattr(t, "tracker", ""))):
                out[str(h).strip().lower()] = t
        return out

    def _yema_bills(self) -> Dict[str, Any]:
        """野马PT 的账单（hash → bill）。"""
        out: Dict[str, Any] = {}
        try:
            store = self._hrbills_store()
            for h, b in (store.all() or {}).items():
                if not isinstance(b, dict):
                    continue
                if yema_is_yema_domain(str(b.get("site") or "")):
                    out[str(h).strip().lower()] = b
        except Exception:  # noqa: BLE001
            pass
        return out

    # ------------------------------------------------------------ 对账（只读）
    def _yema_reconcile(self, live: int = 0, force: int = 0) -> Dict[str, Any]:
        """野马PT 逐种 H&R 对账：站点（权威）× 本机 × 账本。**只读、只增线索**。"""
        cache = self._yema_cache()
        if not YEMA_ENABLED:
            return {"enabled": False, "domain": "yemapt.org", "ok": True,
                    "notes": "功能已关闭（YEMA_ENABLED=False）"}
        if not int(live or 0):
            rep = cache.get_report(YEMA_REPORT_KEY) if cache is not None else None
            if isinstance(rep, dict) and rep:
                out = dict(rep)
                out["cached"] = True
                return out
            return {"enabled": True, "domain": "yemapt.org", "ok": False, "cached": True,
                    "error": "无缓存报告 → 先跑一次 ?live=1 联机对账",
                    "reason_chain": self._yema_reason_chain()}

        t0 = time.time()
        site = self._yema_site_row()
        if not site:
            return {"enabled": True, "domain": "yemapt.org", "ok": False,
                    "error": "未找到野马PT 站点（域名 yemapt.org）", "reason_chain": self._yema_reason_chain()}
        lst = self._yema_rows(force=bool(force))
        if not lst.get("ok"):
            return {"enabled": True, "domain": "yemapt.org", "site_id": int(site.get("id") or 0),
                    "ok": False, "error": str(lst.get("error") or "拉列表失败"),
                    "rows_total": len(lst.get("rows") or []), "pages": lst.get("pages") or 0,
                    "reason_chain": self._yema_reason_chain(), "took_ms": int((time.time() - t0) * 1000)}

        rows = [r for r in (lst.get("rows") or []) if isinstance(r, dict)]
        local = self._yema_local()
        bills = self._yema_bills()
        obligations: List[Dict[str, Any]] = []
        missing_local: List[Dict[str, Any]] = []
        present_no_bill: List[Dict[str, Any]] = []
        done_rows: List[Dict[str, Any]] = []
        unverified: List[Dict[str, Any]] = []
        hash_fetched = 0
        cache_hits = 0
        deferred = 0
        for r in rows:
            v = yema_row_view(r)
            if not v.get("owes"):
                if str(v.get("hr_status") or "") in YEMA_DONE_STATES:
                    done_rows.append(v)
                continue
            res = self._yema_hash_for_tid(v.get("tid"), site, cache)
            if not res.get("ok"):
                deferred += 1
                unverified.append({**v, "note": str(res.get("error") or "拿不到 infohash")})
                continue
            if res.get("cached"):
                cache_hits += 1
            else:
                hash_fetched += 1
            h = str(res.get("hash") or "")
            b = bills.get(h) or {}
            t = local.get(h)
            item = {
                **v,
                "hash": h,
                "in_qb": bool(t is not None),
                "qb_state": str(getattr(t, "state", "") or "") if t is not None else "",
                "bill": ({"rule": str(b.get("rule") or ""), "state": str(b.get("state") or ""),
                          "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                          "need_h": round(float(b.get("need_h") or 0.0), 2)} if b else None),
            }
            obligations.append(item)
            _protected = bool(b) and str(b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN) \
                and str(b.get("state") or "") != BILL_STATE_VOID
            if t is None:
                missing_local.append(item)
            elif not _protected:
                present_no_bill.append(item)
            if time.time() - t0 > YEMA_TIME_BUDGET:
                deferred += 1

        # 账本里 rule=unknown 的野马账单（=11.7.0 遗留 E：历史/旁路加种可能漏记）
        tid_index = {}
        try:
            tid_index = dict(((cache.data or {}).get("tid_index") or {}).get("yemapt.org") or {})
        except Exception:  # noqa: BLE001
            tid_index = {}
        rev = {str(v.get("h") or ""): k for k, v in tid_index.items() if isinstance(v, dict)}
        unknown_bills: List[Dict[str, Any]] = []
        for h, b in bills.items():
            if str(b.get("state") or "") == BILL_STATE_VOID:
                continue
            if str(b.get("rule") or RULE_UNKNOWN) != RULE_UNKNOWN:
                continue
            unknown_bills.append({
                "hash": h,
                "title": str(b.get("title") or "")[:80],
                "state": str(b.get("state") or ""),
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "tid": int(rev.get(h) or 0),
                "in_qb": bool(h in local),
            })

        rep = {
            "enabled": True,
            "ok": True,
            "domain": "yemapt.org",
            "site_id": int(site.get("id") or 0),
            "live": True,
            "at": time.time(),
            "rows_total": len(rows),
            "pages": int(lst.get("pages") or 0),
            "truncated": bool(lst.get("truncated")),
            "site_count": self._yema_count(),
            "obligations_total": len(obligations),
            "missing_local": missing_local,
            "present_no_bill": present_no_bill,
            "unknown_bills": unknown_bills,
            "unverified": unverified,
            "done_rows": done_rows[:20],
            "hash_fetched": hash_fetched,
            "cache_hits": cache_hits,
            "deferred": deferred,
            "took_ms": int((time.time() - t0) * 1000),
            "reason_chain": self._yema_reason_chain(),
            "notes": ("站点视角**只判「还欠」**：Pass/Absolve 只作线索，摘保护仍走人工作废；"
                      "present_no_bill=本机有、站点说欠、账本没记 → 可补开账单（只增保护）；"
                      "missing_local=站点说欠、本机没有 → **H&R 违规风险**，需同站重下（逐条人工）。"),
        }
        if cache is not None:
            try:
                cache.put_report(YEMA_REPORT_KEY, rep)
            except Exception:  # noqa: BLE001
                pass
        return rep

    @staticmethod
    def _yema_reason_chain() -> List[Dict[str, Any]]:
        return [
            {"rule": "site/yema/list",
             "inputs": {"source_of_truth": "站点后台接口 /api/torrent/fetchUserTorrentList（cookie 鉴权）"},
             "verdict": "逐种 H&R 权威：hrPunishEnable（发布者开关）+ hrStatus；站点级无 H&R 规则"},
            {"rule": "tid/infohash",
             "inputs": {"source_of_truth": "GET /api/torrent/download?id=<tid> → info_hash（永久缓存）"},
             "verdict": "把站点行与下载器/账本**精确**对上（不用标题猜）"},
            {"rule": "bill/protect",
             "inputs": {"source_of_truth": "hr_bills.json 的 rule/state"},
             "verdict": "rule∈{site_hr,hit_and_run} 且非 void = 受保护；unknown = 可能漏记"},
        ]

    # ------------------------------------------------------------ 应用（只增保护）
    def _yema_apply(self, confirm: int = 0, limit: int = 0) -> Dict[str, Any]:
        """把「本机有、站点说欠、账本没记」的种**补开账单**（只增保护；默认干跑）。

        ★ **必须现算**（``live=1``）：写路径绝不能拿上一轮缓存里可能过期的清单下手。
        """
        rep = self._yema_reconcile(live=1)
        if not rep.get("ok"):
            return {"ok": False, "error": str(rep.get("error") or "无可用对账报告"), "source": "yema"}
        rows = list(rep.get("present_no_bill") or [])
        if int(limit or 0) > 0:
            rows = rows[: int(limit)]
        plan = [{"hash": r.get("hash"), "tid": r.get("tid"), "name": r.get("name"),
                 "hr_status": r.get("hr_status"), "size_gb": r.get("size_gb"),
                 "action": ("upgrade" if str((r.get("bill") or {}).get("rule") or "") == RULE_UNKNOWN
                            and str((r.get("bill") or {}).get("state") or "") != BILL_STATE_VOID
                            else "open")} for r in rows]
        if not int(confirm or 0):
            return {"ok": True, "dry_run": True, "would_open": len(plan), "plan": plan, "source": "yema"}
        opened: List[str] = []
        upgraded: List[str] = []
        failed: List[Dict[str, Any]] = []
        for r in rows:
            h = str(r.get("hash") or "")
            if not h:
                continue
            _b = r.get("bill") or {}
            _rule = str(_b.get("rule") or "")
            _state = str(_b.get("state") or "")
            try:
                # ★ 11.7.0-E 收口：存量 rule=unknown 的账单 → **升级**为 hit_and_run
                #   （站点逐种确认 punish=True；不新增账单、不造第二真值源）。
                if _rule == RULE_UNKNOWN and _state != BILL_STATE_VOID:
                    got = self._hrbills_store().patch(
                        h, rule=RULE_HIT_AND_RUN, state=BILL_STATE_ACTIVE,
                        site="yemapt.org", upgraded_from=RULE_UNKNOWN, upgraded_at=time.time())
                    if got:
                        upgraded.append(h)
                    else:
                        failed.append({"hash": h, "error": "升级失败（账单不存在）"})
                else:
                    got = self._hrbills_open(h, "yemapt.org", "魔流-野马PT-做种", None, True)
                    if got:
                        opened.append(h)
                    else:
                        failed.append({"hash": h, "error": "开账被跳过（crossseed/已存在）"})
            except Exception as err:  # noqa: BLE001
                failed.append({"hash": h, "error": str(err)})
        try:
            self._log(f"[野马PT] 按站点权威行补保护：新开 {len(opened)} 张 / 升级为逐种 H&R "
                      f"{len(upgraded)} 张（站点说欠+本机有+账本未保护）")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "dry_run": False, "opened": len(opened), "hashes": opened,
                "upgraded": len(upgraded), "upgraded_hashes": upgraded, "failed": failed,
                "source": "yema"}

    # ------------------------------------------------------------ 免罪（写）
    def _yema_absolve(self, tid: Any, confirm: int = 0) -> Dict[str, Any]:
        """野马PT「免罪」（``POST /api/userTorrent/absolve``）：默认**干跑**，``confirm=1`` 才写。

        ★ 写操作、**扣站点积分且不可逆** → 逐条人工；本方法只执行「点名的那一条」。
        """
        if not YEMA_ABSOLVE_ENABLED:
            return {"ok": False, "error": "免罪写路径已关闭（YEMA_ABSOLVE_ENABLED=False）"}
        try:
            tid_i = int(str(tid or "").strip() or 0)
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "tid 必须是数字（站点 torrentId）"}
        if tid_i <= 0:
            return {"ok": False, "error": "缺少 torrentId"}
        site = self._yema_site_row()
        if not site:
            return {"ok": False, "error": "未找到野马PT 站点（域名 yemapt.org）"}
        # 目标行（从缓存报告里找；找不到就照实说「未知」，不猜）
        row_view: Optional[Dict[str, Any]] = None
        try:
            rep = self._yema_reconcile(live=0)
            for bucket in ("present_no_bill", "missing_local", "unverified", "done_rows"):
                for r in (rep.get(bucket) or []):
                    if int(r.get("tid") or 0) == tid_i:
                        row_view = dict(r)
                        break
                if row_view:
                    break
        except Exception:  # noqa: BLE001
            row_view = None
        base = {
            "tid": tid_i,
            "row": row_view,
            "cost_note": "免罪按站点计价**扣积分**，且**不可逆**；先确认站点 HR 列表里确实有这一条。",
            "reason_chain": self._yema_reason_chain(),
        }
        if not int(confirm or 0):
            return {**base, "ok": True, "written": False, "dry_run": True,
                    "confirm_required": "GET /agent/yema/absolve?tid=<tid>&confirm=1"}
        c = self._collect_ref()
        if c is None:
            return {**base, "ok": False, "written": False, "error": "采集模块未就绪"}
        res = c.site(int(site.get("id") or 0)).post_json(
            YEMA_ABSOLVE_PATH, {"torrentId": tid_i}, kind=YEMA_KIND, cache=False, force=True
        )
        data = res.get("data")
        ok = bool(res.get("ok")) and not (isinstance(data, dict) and data.get("success") is False)
        out = {**base, "ok": ok, "written": ok, "dry_run": False,
               "response": (data if isinstance(data, (dict, list)) else str(data))}
        if not ok:
            out["error"] = str(res.get("error") or (data or {}).get("errorMessage") if isinstance(data, dict)
                               else res.get("error") or "站点拒绝")
        try:
            self._log(f"[野马PT] 免罪 {'成功' if ok else '失败'} tid={tid_i}")
        except Exception:  # noqa: BLE001
            pass
        return out

    # ------------------------------------------------------------ worker 入口
    def _yema_round(self, force: int = 0) -> Dict[str, Any]:
        """周期对账（挂在「标签账本维护」worker 上，独立 try 块；失败不影响其它）。

        自带 ``YEMA_HOURS`` 周期门（用报告自己的 ``at`` 计时，**不碰共享 meta**） +
        撞时间预算就退避到下一轮，失败=**本轮零写入**。
        """
        if not YEMA_ENABLED:
            return {"ok": True, "skipped": "disabled"}
        if not int(force or 0):
            cache = self._yema_cache()
            try:
                rep0 = (cache.get_report(YEMA_REPORT_KEY) or {}) if cache is not None else {}
                at = float(rep0.get("at") or 0.0)
                if at and (time.time() - at) < float(YEMA_HOURS) * 3600.0:
                    return {"ok": True, "skipped": "not_due", "at": at}
            except Exception:  # noqa: BLE001
                pass
        try:
            rep = self._yema_reconcile(live=1, force=0)
        except Exception as err:  # noqa: BLE001
            self._log(f"[野马PT] 对账异常（本轮零写入）：{err}", "warning")
            return {"ok": False, "error": str(err)}
        if rep.get("ok"):
            try:
                self._log(
                    f"[野马PT] 逐种 H&R 对账：种 {rep.get('rows_total')} · 义务 {rep.get('obligations_total')} · "
                    f"漏挂 {len(rep.get('missing_local') or [])} · 漏记 {len(rep.get('present_no_bill') or [])} · "
                    f"unknown {len(rep.get('unknown_bills') or [])} · 拉种 {rep.get('hash_fetched')}"
                )
            except Exception:  # noqa: BLE001
                pass
        return rep
