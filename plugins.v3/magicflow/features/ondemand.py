# -*- coding: utf-8 -*-
"""魔流 · ondemand —— 点播口子（MODEL.md §1「权威来源 1 = Master 主动声明」）。

流程（与 MODEL.md §1 一致）：
  输入片名 / 豆瓣·TMDB·IMDB 链接
    → **识别唯一资源**（``recognize`` / 按 id 识别）
    → 搜索选源（**免费优先**，其次做种数）
    → 下载
    → **直接转「资源」**（不观察、不分拣）。

实现上复用既有链路：``_mp_search_title``（MP 自带搜索）取候选、``_crossseed_torrent_bytes``
取 .torrent 字节、``downloader.add_torrent`` 落盘，最后只把「身份」这一步从自动扫描
换成手动指定 —— 下载中的 hash 记进 ``ondemand_pending``，一旦形成资源组
（``ResourceLedgerStore``）就 ``set_identity(资源)`` 并摘掉待办；在此期间分拣
（``_silent_triage``）**跳过**这些种，保证「不观察、不分拣」。
"""

from __future__ import annotations

import re
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set

from app.schemas import Response

from ..recommend import recognize
from ..persistence import OperationItem
from ..tags import SUB_NEW, SUB_RESOURCE, STATE_ONDEMAND, STATE_SILENT, identity_of, retag, tag_for
from ..sitestore import slot_callbacks

_DOUBAN_RE = re.compile(r"movie\.douban\.com/subject/(\d+)")
_TMDB_RE = re.compile(r"themoviedb\.org/(?:movie|tv)/(\d+)")
_IMDB_RE = re.compile(r"imdb\.com/title/(tt\d+)")

# 最近一次搜索结果的短时缓存（秒）：让「选某一条」不必把站点再搜一遍（原搜索要 60~75s）
_OD_CACHE_TTL = 600


def _od_is_free(dv: Any) -> bool:
    """下载因子是否「免费」。

    ★ 坑：不能写成 `float(dv or 1) <= 0` —— ``dv=0``（免费）会被 `or` 吃成 1。
    ``None``/异常 = 未如 → 按「不免费」处理。
    """
    try:
        v = 1.0 if dv is None else float(dv)
    except Exception:  # noqa: BLE001
        v = 1.0
    return v <= 0.0

_OD_KEY = "ondemand_pending"


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
        """★ 15.8.4：把「点播在途」的种挂到 ``__ondemand__`` 伪任务（职务=点播）。

        贴职务标签（身份轴 ``魔流-<站>-静默-<子类>`` 永久保留）+ 写账本（``taken_by=__ondemand__``）。
        效果：账本 ``state=点播`` ≠ 静默 → 静默池的**暂停闸**与**清理闸**
        （``_silent_purge_incomplete`` / ``_silent_drop_incomplete_now`` / ``_silent_audit``）双双跳过
        → 「没下完的点播种」不再被当静默半成品删/暂停。**不动下载状态**（正在下，不 pause、不 force_start）。
        幂等：已 ``taken_by=__ondemand__`` 的跳过。
        """
        from ..common import ONDEMAND_TASK_ID, ONDEMAND_TASK_NAME  # 惰性导入（离线测试不碰 common）
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
            _rec0 = store.get(hh) or {}
            if str(_rec0.get("taken_by") or "") == ONDEMAND_TASK_ID:
                continue  # 已挂点播宿主
            live = (snap or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            _i_site, _i_sub = identity_of(cur)
            _sub = str(sub or "") or str(_rec0.get("sub") or "") or _i_sub or SUB_RESOURCE
            _site = str(site or "") or str(_rec0.get("site") or "") or _i_site \
                or self._torrent_site_name(cur, "")
            if cur:
                new_tags = retag(cur, site=_site, state=STATE_ONDEMAND, sub=_sub)
            else:
                new_tags = [tag_for(_site, STATE_SILENT, _sub), tag_for(_site, STATE_ONDEMAND)]
            try:
                done = fn(hh, new_tags) if callable(fn) else downloader.set_torrent_tags(hh, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                continue
            try:
                store.put(hh, {
                    "site": _site, "state": STATE_ONDEMAND, "sub": _sub,
                    "taken_by": ONDEMAND_TASK_ID, "task": ONDEMAND_TASK_NAME,
                    "taken_at": _now, "lease_until": 0,
                    "title": str(getattr(live, "title", "") or "") if live is not None else "",
                })
            except Exception:  # noqa: BLE001
                pass
            n += 1
        if n:
            self._log(f"点播:挂 __ondemand__ {n} 个（{reason or '在途'}）")
        return n

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
        to_assign = [h for h in pend
                     if str((items.get(h) or {}).get("taken_by") or "") != ONDEMAND_TASK_ID]
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
        """识别唯一资源：片名走默认识别链；链接按 id 识别。"""
        kw = str(q.get("keyword") or "").strip()
        if kw:
            return recognize(kw)
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

    def _ondemand_search(self, keyword: str, site_ids: List[int]) -> List[Dict[str, Any]]:
        """搜候选（**不过滤免费**，点播要的是这个资源本身）。"""
        kw = str(keyword or "").strip()
        ids = [i for i in (site_ids or []) if i]
        if not kw or not ids:
            return []
        allowed = [
            i for i in ids
            if not self._pv_block_reason(i) and self._pv_allow(i, "ondemand", want=1)
        ]
        if not allowed:
            self._log("点播:候选站点 PV 预算不足/已封，跳过检索", "warning")
            return []
        try:
            hits = self._mp_search_title(kw, allowed)
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:MP 搜索失败: {e}", "warning")
            hits = []
        finally:
            for i in allowed:
                self._pv_spend(i, "ondemand", 1)
        rows: List[Dict[str, Any]] = []
        for ti in hits or []:
            url = str(getattr(ti, "enclosure", "") or "")
            if not url:
                continue
            _dv = getattr(ti, "downloadvolumefactor", None)
            try:
                dv = 1.0 if _dv is None else float(_dv)
            except Exception:  # noqa: BLE001
                dv = 1.0
            try:
                seeders = int(getattr(ti, "seeders", 0) or 0)
            except Exception:  # noqa: BLE001
                seeders = 0
            rows.append({
                "title": str(getattr(ti, "title", "") or ""),
                "size": float(getattr(ti, "size", 0.0) or 0.0),
                "seeders": seeders,
                "peers": int(getattr(ti, "peers", 0) or 0),
                "enclosure": url,
                "page_url": str(getattr(ti, "page_url", "") or ""),
                "site": int(getattr(ti, "site", 0) or 0),
                "site_name": str(getattr(ti, "site_name", "") or ""),
                "site_cookie": getattr(ti, "site_cookie", None),
                "site_ua": getattr(ti, "site_ua", None),
                "site_proxy": bool(getattr(ti, "site_proxy", False)),
                "downloadvolumefactor": dv,
                "hit_and_run": bool(getattr(ti, "hit_and_run", False)),
            })
        self._log(f"点播:MP 搜索「{kw}」{len(allowed)} 站 → 候选 {len(rows)} 条")
        return rows

    def _ondemand_pick(self, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """选源：**免费优先** → 做种数多 → 体积大。"""
        if not rows:
            return None

        def _k(r: Dict[str, Any]) -> tuple:
            try:
                free = 1 if _od_is_free(r.get("downloadvolumefactor")) else 0
            except Exception:  # noqa: BLE001
                free = 0
            return (free, int(r.get("seeders", 0) or 0), float(r.get("size", 0.0) or 0.0))

        return max(rows, key=_k)

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

    def _ondemand_download(self, row: Dict[str, Any], task: Any = None) -> Dict[str, Any]:
        dl = self._get_downloader("qbittorrent")
        if dl is None or not getattr(dl, "is_available", False):
            return {"ok": False, "message": "下载器不可用"}
        content = self._crossseed_torrent_bytes(SimpleNamespace(**row))
        if not content:
            return {"ok": False, "message": "取 .torrent 失败（PV 闸门/站点拒绝）"}
        site_name = str(row.get("site_name") or "")
        save_path = str(getattr(task, "save_path", "") or "") if task is not None else ""
        if not save_path:
            save_path = self._ondemand_default_save_path()
        if not save_path:
            return {"ok": False, "message": "没有可用的保存目录：请在弹窗上方选一个任务，或到「设置 → 下载目录」填「任务保存目录」"}
        tag = tag_for(site_name, STATE_SILENT, SUB_RESOURCE) if site_name else ""
        # ★ 10.2.0 下载即开账：只传域名（绝不传展示名），拿不到就留空
        try:
            _dom = self._site_domain_by_name(site_name) or ""
        except Exception:  # noqa: BLE001
            _dom = ""
        try:
            hs, err = dl.add_torrent(content=content, download_dir=save_path, tag=tag,
                                     site_domain=_dom,
                                     hit_and_run=bool(row.get("hit_and_run")))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"添加失败: {e}"}
        if not hs:
            return {"ok": False, "message": f"添加失败: {err or '未知'}"}
        h = str(hs[0] if isinstance(hs, (list, tuple)) else hs).lower()
        # ★ 15.8.4：加种即挂 __ondemand__ 伪任务（职务=点播）→ 未下完不被静默池删/暂停
        try:
            self._od_assign([h], site=site_name, sub=SUB_RESOURCE, reason="加种")
        except Exception as _oae:  # noqa: BLE001
            self._log(f"点播:挂伪任务失败 {h[:12]}: {_oae}", "warning")
        return {
            "ok": True, "hash": h, "tag": tag,
            "site": int(row.get("site") or 0), "save_path": save_path,
        }

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
        pend = self._ondemand_all()
        if not pend:
            return {"settled": 0}
        try:
            files = self._tag_groups()
        except Exception:  # noqa: BLE001
            return {"settled": 0}
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
                continue   # 资源组还没建立 → 等对账/纳管
            try:
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
            self._ondemand_import(h, gid, _title)
            # ★ 11.11.0：转资源后入池即暂停（静默硬不变量；任务纳管时才做种）
            try:
                self._silent_pause_gate(h)
            except Exception:  # noqa: BLE001
                pass
        return {"settled": done}

    def _ondemand_import(self, h: str, gid: str = "", title: str = "") -> bool:
        """点播种转「资源」后整理入库（复用推荐链路的 MP ``TransferChain.manual_transfer``）。

        识别失败/取种失败都只记日志、**不阻断**（文件留在下载目录，可下次再整理）。
        """
        _h = str(h or "").lower()
        if not _h:
            return False
        try:
            ok, msg = self._recommend_import(_h, {"title": str(title or ""), "group_id": str(gid or "")})
        except Exception as e:  # noqa: BLE001
            self._log(f"点播:整理入库异常 {_h[:12]}: {e}", "warning")
            return False
        self._log(
            f"点播:整理入库 {_h[:12]} 「{title}」→ {'完成' if ok else '未整理'} {msg or ''}".rstrip()
        )
        return bool(ok)

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

    @staticmethod
    def _ondemand_hist_title(title: str) -> str:
        """历史行的展示名：把 journal 里的「点播 xxx」前缀去掉。"""
        t = str(title or "").strip()
        if t.startswith("点播"):
            t = t[len("点播"):].strip()
        return t

    @staticmethod
    def _ondemand_hist_site(reason: str) -> str:
        """从 journal 的 reason（如「源 财神·免费」）回填站点名——种已被删、账本无行时的兜底。"""
        r = str(reason or "").strip()
        if r.startswith("源"):
            r = r[len("源"):].strip()
        for sep in ("·", " ", "，", ","):
            if sep in r:
                r = r.split(sep)[0].strip()
                break
        return r

    def _ondemand_inflight_row(self, h: str, info: Dict[str, Any], t: Any, rec: Dict[str, Any]) -> Dict[str, Any]:
        """进行中一行：基本信息 + qB 进度（progress/state/speed/剩余/ETA）。"""
        row: Dict[str, Any] = {
            "hash": h,
            "title": str(info.get("title") or info.get("media") or ""),
            "year": str(info.get("year") or ""),
            "site": str(info.get("site") or ""),
            "free": bool(info.get("free")),
            "hit_and_run": bool(info.get("hit_and_run")),
            "added_at": float(info.get("ts") or 0.0),
            "in_qb": t is not None,
            "progress": 0.0, "state": "", "size_gb": 0.0, "left_gb": 0.0,
            "speed": 0.0, "eta_s": None, "ratio": 0.0,
            "stage": "gone", "stage_text": "已不在下载器",
        }
        if t is None:
            return row
        prog = float(getattr(t, "progress", 0) or 0.0)
        size_gb = float(getattr(t, "size_gb", 0) or 0.0)
        spd = float(getattr(t, "download_speed", 0) or 0.0)
        left_gb = max(0.0, size_gb * (1.0 - prog))
        row.update({
            "progress": round(prog, 4),
            "state": str(getattr(t, "state", "") or ""),
            "size_gb": round(size_gb, 3),
            "left_gb": round(left_gb, 3),
            "speed": round(spd, 1),
            "ratio": round(float(getattr(t, "ratio", 0) or 0.0), 3),
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
            row["stage"] = "pending_settle"
            row["stage_text"] = "已下完，待转「资源」"
        return row

    def _ondemand_hist_row(self, h: str, it: Any, rec_op: Any, t: Any, rec: Dict[str, Any]) -> Dict[str, Any]:
        """历史一行：journal 的点播记录 + **现况回查**（不新增真值源）。"""
        sub = str((rec or {}).get("sub") or "")
        inlib = bool((rec or {}).get("in_library"))
        row: Dict[str, Any] = {
            "hash": h,
            "title": self._ondemand_hist_title(str(getattr(it, "title", "") or "")),
            "site": str((rec or {}).get("site") or "") or self._ondemand_hist_site(getattr(it, "reason", "")),
            "reason": str(getattr(it, "reason", "") or ""),
            "size_gb": round(float(getattr(it, "size_gb", 0) or 0.0), 3),
            "ts": float(getattr(rec_op, "created_at", 0) or 0.0),
            "in_qb": t is not None,
            "in_library": inlib,
            "sub": sub,
            "settled_at": float((rec or {}).get("identity_at") or 0.0),
            "progress": 0.0,
            "result": "gone", "result_text": "已移出下载器",
        }
        if t is None:
            return row
        prog = float(getattr(t, "progress", 0) or 0.0)
        row["progress"] = round(prog, 4)
        row["state"] = str(getattr(t, "state", "") or "")
        if prog < 0.999:
            row["result"], row["result_text"] = "downloading", "下载中"
        elif sub == SUB_RESOURCE or inlib:
            row["result"] = "resource"
            row["result_text"] = "已转「资源」" + ("·已入库" if inlib else "")
        else:
            row["result"], row["result_text"] = "settling", "已下完，待转「资源」"
        return row

    def _ondemand_items(self, limit: int = 50) -> Dict[str, Any]:
        """点播清单：进行中（带下载进度）+ 已完成（历史 + 现况）。

        真值源（只读，不新造）：
          - 进行中 = ``ondemand_pending``（``mf_seed.pending``）× qB 快照（进度/状态/速度）；
          - 历史 = journal（``items[].source == "ondemand"``）＋ 种子账本（state/sub/in_library）。
        """
        try:
            cap = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            cap = 50
        pend = self._ondemand_all()
        snap = self._ondemand_snapshot()
        inflight: List[Dict[str, Any]] = []
        for h, info in pend.items():
            inflight.append(self._ondemand_inflight_row(h, info, snap.get(h), self._ondemand_seed_rec(h)))
        inflight.sort(key=lambda r: float(r.get("added_at") or 0.0), reverse=True)
        history: List[Dict[str, Any]] = []
        seen: Set[str] = set(pend.keys())
        try:
            recs = self._store.journal.list_recent(limit=5000) if self._store is not None else []
        except Exception:  # noqa: BLE001
            recs = []
        for r in recs:
            for it in (getattr(r, "items", None) or []):
                if str(getattr(it, "source", "") or "") != "ondemand":
                    continue
                h = str(getattr(it, "hash", "") or "").lower()
                if not h or h in seen:
                    continue
                seen.add(h)
                history.append(self._ondemand_hist_row(h, it, r, snap.get(h), self._ondemand_seed_rec(h)))
                if len(history) >= cap:
                    break
            if len(history) >= cap:
                break
        history.sort(key=lambda r: float(r.get("ts") or 0.0), reverse=True)
        return {
            "inflight": inflight,
            "history": history,
            "totals": {
                "inflight": len(inflight),
                "downloading": sum(1 for r in inflight if r.get("stage") == "downloading"),
                "history": len(history),
                "left_gb": round(sum(float(r.get("left_gb") or 0.0) for r in inflight), 3),
            },
        }

    # ------------------------------------------------------------ 操作（行内：暂停/继续/移除）

    _OD_ACTS = ("pause", "resume", "remove")

    def _ondemand_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """点播「进行中」的行内操作：``pause`` / ``resume`` / ``remove``（只读清单之外的唯一写口）。

        ``remove`` **走唯一删除闸门**（``DownloaderAdapter.delete_torrents``）：欠 H&R /
        跨站来源份 / 已认领 / 手动保留 **一律硬拦**（fail-closed，不绕过）——被拦时
        ``ok=false``、``blocked=true`` 并附原因，前端如实展示。
        删种**同时删文件**（未完成的下载无保留价值，避免又添孤儿文件）。
        """
        h = str(hash or "").strip().lower()
        act = str(action or "").strip().lower()
        if not h:
            return {"ok": False, "message": "缺少 hash"}
        if act not in self._OD_ACTS:
            return {"ok": False, "message": f"未知操作:{action}"}
        pend = self._ondemand_all()
        if h not in pend:
            return {"ok": False, "message": "该种不在点播进行中（可能已完成/已移除）"}
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"下载器不可用:{e}"}
        if dl is None or not getattr(dl, "is_available", False):
            return {"ok": False, "message": "下载器不可用"}
        if act in ("pause", "resume"):
            try:
                n, err = (dl.pause_torrents([h]) if act == "pause" else dl.resume_torrents([h]))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "message": f"{act} 失败:{e}"}
            if err or not n:
                return {"ok": False, "message": f"{act} 失败:{err or '未命中'}"}
            self._log(f"点播:{'暂停' if act == 'pause' else '继续'} {h[:12]}")
            return {"ok": True, "hash": h, "action": act,
                    "message": "已暂停" if act == "pause" else "已继续"}
        # ---- remove：唯一删除闸门（不绕过）
        try:
            n, err = dl.delete_torrents(hashes=[h], delete_file=True,
                                        reason="点播移除（进行中）", source="ondemand")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"移除失败:{e}"}
        if not n:
            return {"ok": False, "blocked": True,
                    "message": err or "被删除闸门拦下（欠 H&R / 受保护），未移除"}
        self._ondemand_unmark(h)
        self._log(f"点播:移除 {h[:12]}（删种+删文件）")
        return {"ok": True, "hash": h, "action": "remove", "message": "已移除（删种+删文件）"}

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
        if pick:
            # ★ 手动选源：优先吃上次搜索结果（命中则秒回，不必再搜一次）
            title = q["keyword"] or q["query"]
            rows = self._ondemand_cache_get(q["query"], sites) or []
        if not rows:
            # 未指定来源 / 手动指定但缓存失效 → 正常识别 + 搜索
            media = self._ondemand_media(q)
            if media is not None and not title:
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
            self._ondemand_cache_put(q["query"], sites, rows)
        auto = self._ondemand_pick(rows)
        picked: Optional[Dict[str, Any]] = None
        if pick:
            picked = next((r for r in rows if str(r.get("enclosure") or "") == pick), None)
            if picked is None:
                return Response(success=False, message="指定的候选不在本次搜索结果里（列表可能已刷新）")
        else:
            picked = auto
        out: Dict[str, Any] = {
            "resource": {"title": title, "year": year,
                         "recognized": media is not None,
                         "media_source": getattr(media, "media_source", None) and str(
                             getattr(getattr(media, "media_source"), "value", getattr(media, "media_source"))),
                         "media_id": str(getattr(media, "media_id", "") or "")},
            "sites": sites,
            "save_path": (str(getattr(task, "save_path", "") or "") if task is not None else "")
                         or self._ondemand_default_save_path(),
            "candidates": sorted(rows, key=lambda r: (
                0 if _od_is_free(r.get("downloadvolumefactor")) else 1,
                -int(r.get("seeders", 0) or 0), -float(r.get("size", 0.0) or 0.0)))[:20],
            "picked": picked,
            "auto_pick": (auto or {}).get("enclosure") or "",
            "manual": bool(pick),
        }
        if not picked:
            return Response(success=False, message="没搜到可用候选（免费优先）", data=out)
        if not apply:
            out["applied"] = False
            return Response(success=True, message="预览（apply=false，未下载）", data=out)
        res = self._ondemand_download(picked, task)
        out["applied"] = True
        out["added"] = res.get("hash") or ""
        if not res.get("ok"):
            return Response(success=False, message=str(res.get("message") or "下载失败"), data=out)
        self._ondemand_mark(str(res.get("hash") or ""), {
            "title": picked.get("title") or "",
            "media": title, "year": year,
            "site": picked.get("site_name") or "",
            "site_id": picked.get("site") or 0,
            "free": _od_is_free(picked.get("downloadvolumefactor")),
            "hit_and_run": bool(picked.get("hit_and_run")),
        })
        try:
            self._store.journal.record(
                task_id=(task.id if task is not None else ""), kind="selection",
                items=[OperationItem(
                    hash=str(res.get("hash") or ""), title=f"点播 {title} {year}".strip(),
                    reason=f"源 {picked.get('site_name') or picked.get('site')}"
                           + ("·免费" if _od_is_free(picked.get("downloadvolumefactor")) else ""),
                    source="ondemand",
                )],
            )
        except Exception:  # noqa: BLE001
            pass
        self._log(
            f"点播:「{title}」{year} → 下 {str(res.get('hash'))[:12]}"
            f"（{picked.get('site_name') or picked.get('site')}·"
            + ("免费" if _od_is_free(picked.get("downloadvolumefactor")) else "计流量") + "）"
        )
        return Response(success=True, message=f"已点播：{title}（下载中，完成后直接转「资源」）", data=out)
