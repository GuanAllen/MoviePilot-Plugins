# -*- coding: utf-8 -*-
"""魔流 · bonus_exchange —— 魔力兑换（看板 + 手动兑换，★ 19.16.29）。

边界（19.16.28 首发只做上传量；19.16.29 按用户要求扩到邀请）：
  * 接三类兑换项：**上传量**（标题含「上传 / upload」）、**邀请名额**（含「邀请」不含
    「临时」）、**临时邀请**（含「临时邀请」，通常 7 天有效）。头衔 / VIP / 赠送 /
    捐赠 / 消 H&R 等其余类型一律不碰（不可逆或需额外参数）。
  * **看板只读**：逐站抓 mybonus.php 解析出当前魔力 + 三类项 + 站点 disabled 状态。
  * **写动作必须 confirm=1**，且在提交前**重新抓一次当次页面核对 option 仍是可换项**
    —— 防「用户点的是刚才看板里的便宜项，页面变了/被别处换过」导致换错。
  * 站点 disabled（分享率已很高 / 魔力不足 / 等级不足）→ 即便 confirm 也不发请求。
  * 邀请类**比上传量更不可逆**（名额换回来退不掉），前端二次确认按 kind 给不同警示。

抓/解析全走 collect 出口：``c.http.text(sid, url, kind="bonus_exchange")`` →
``parse_bonus_exchange_page``；写动作委托 ``sites/bonus_exchange.py``（R2 护栏）。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import Response

# ★ 19.16.28 发版实测：线上 common.py 没有 as_bool_arg 这个符号（离线测试里 stub 过，
#   掩盖了它），直接导入会让整个插件加载失败。这里内联实现，与测试 stub 语义一致、彻底解耦。
def _as_bool_arg(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# 直接从 L0 解析层导入（不 import ..collect，避免离线测试拉起整个采集依赖链；
# collect.py 里也 re-export 了这个函数，供其它调用点用）
from ..collect_parse import parse_bonus_exchange_page

BONUS_EXCHANGE_KIND = "bonus_exchange"
# 上传量项价格/数量会变，但不频繁；TTL 10min，手动兑换前强制重抓（ttl=0）
BONUS_EXCHANGE_TTL = 600.0
# SPA / 无 HTML 兑换表站（抓不到 form 会自然跳过，这里仍显式列出便于审计）
_SKIP_DOMAINS = ("m-team.cc", "yemapt.org", "dstudio.me")
# ★ 19.16.33：各站最近一次抓取快照（站点清单直接读它显示状态，**不发请求**）
BONUS_EXCHANGE_SNAP = "bonus_exchange_snap"


class BonusExchangeMixin:
    """魔力兑换：看板 + 手动兑换上传量。"""

    def _be_skip(self, site: Dict[str, Any]) -> bool:
        domain = str(site.get("domain") or site.get("url") or "").lower()
        return any(d in domain for d in _SKIP_DOMAINS)

    # ------------------------------------------------------------------ 快照
    def _be_snap_get(self) -> Dict[str, Any]:
        # ★ 走 MP 自带 kv（get_data/save_data）。别用 sitestore.slot_callbacks：
        #   它的 SiteStore.get/save 是**固定槽白名单**，未知槽会被静默丢弃（实测写不进去）。
        try:
            raw = self.get_data(BONUS_EXCHANGE_SNAP)
        except Exception:  # noqa: BLE001
            return {}
        return raw if isinstance(raw, dict) else {}

    def _be_snap_put(self, site_id: int, r: Dict[str, Any]) -> None:
        """把单站抓取结果写进快照（清单状态/余额用，读它不再抓页面）。"""
        try:
            snap = self._be_snap_get()
            items = r.get("items") or []
            snap[str(site_id)] = {
                "ok": bool(r.get("ok")), "why": str(r.get("why") or "")[:120],
                "balance": r.get("balance"), "currency": str(r.get("currency") or ""),
                "items": len(items),
                "exchangeable": sum(1 for it in items if not it.get("disabled")),
                "ts": time.time(),
            }
            now = time.time()
            for k in [k for k, v in snap.items()
                      if not isinstance(v, dict) or now - float(v.get("ts") or 0) > 30 * 86400]:
                snap.pop(k, None)
            self.save_data(key=BONUS_EXCHANGE_SNAP, value=snap)
        except Exception as err:  # noqa: BLE001
            try:
                from ..envops import log as _log
                _log(f"币兑换快照写入失败：{err}", "warning")
            except Exception:  # noqa: BLE001
                pass

    def _be_fetch(self, site_id: int, site: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
        """抓单站 mybonus.php（带快照落库）；失败={ok:False}。"""
        r = self._be_fetch_raw(site_id, site, force=force)
        self._be_snap_put(int(site_id), r)
        return r

    def _be_fetch_raw(self, site_id: int, site: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
        """抓单站 mybonus.php → 解析结果（走 collect 出口 + PV 闸门）。失败={ok:False}。"""
        out: Dict[str, Any] = {"ok": False, "items": [], "balance": None, "currency": "",
                               "kinds": {"upload": 0, "invite": 0, "temp_invite": 0},
                               "form_count": 0, "why": ""}
        c = None
        try:
            c = self._collect_ref()
        except Exception:  # noqa: BLE001
            c = None
        if c is None:
            out["why"] = "采集模块未就绪"
            return out
        try:
            if not self._pv_allow(int(site_id), BONUS_EXCHANGE_KIND, want=1):
                out["why"] = "站点 PV 预算不足或被熔断"
                return out
        except Exception:  # noqa: BLE001
            pass
        # ★ 19.16.28 实测：_list_sites() 的 domain 是**完整 URL**（https://carpt.net/），
        #   再拼一次 https:// 会变成 https://https://... → 采集出口判「非本站域名」拦截。
        #   写动作路径的 MP 站点对象 url 才是干净的，两条路径都要兼容「已带 scheme」。
        raw = str(site.get("url") or site.get("domain") or "").strip()
        base = (raw if "://" in raw else "https://" + raw).rstrip("/") if raw else ""
        url = f"{base}/mybonus.php"
        try:
            res = c.http.text(int(site_id), url, kind=BONUS_EXCHANGE_KIND,
                              ttl=0.0 if force else BONUS_EXCHANGE_TTL)
        except Exception as err:  # noqa: BLE001
            out["why"] = f"抓取异常：{err}"
            return out
        try:
            self._pv_spend(int(site_id), BONUS_EXCHANGE_KIND, 1)
        except Exception:  # noqa: BLE001
            pass
        if res is None or not bool(getattr(res, "ok", False)):
            out["why"] = str(getattr(res, "error", "") or "抓取失败")
            return out
        return parse_bonus_exchange_page(getattr(res, "text", "") or "")

    def get_bonus_exchange_state(self, site_id: Any = None, refresh: Any = None) -> Response:
        """魔力兑换看板：站点清单（状态取上次抓取快照，零请求）+ 选中站实时结果（只读）。

        ★ 19.16.33：不再逐站拉 mybonus 页面 —— 打开弹窗只读快照清单（不发任何站点请求），
        选中哪站才抓哪站（10 分钟内复用采集缓存），刷新只强刷当前站。
        """
        force = bool(_as_bool_arg(refresh))
        only = int(site_id) if str(site_id or "").isdigit() else 0
        try:
            all_sites = self._list_sites() or []
        except Exception:  # noqa: BLE001
            all_sites = []
        snap = self._be_snap_get()
        site_list: List[Dict[str, Any]] = []
        picked: Optional[Dict[str, Any]] = None
        for s in all_sites:
            if not isinstance(s, dict):
                continue
            sid = int(s.get("id", 0) or 0)
            if not sid or self._be_skip(s):
                continue
            st = snap.get(str(sid)) if isinstance(snap.get(str(sid)), dict) else {}
            site_list.append({
                "site_id": sid,
                "site_name": str(s.get("name") or s.get("domain") or sid),
                "domain": str(s.get("domain") or ""),
                "cached": bool(st),
                "ok": st.get("ok"),
                "exchangeable": int(st.get("exchangeable") or 0) if st else None,
                "balance": st.get("balance"),
                "currency": st.get("currency") or "",
                "why": st.get("why") or "",
                "ts": st.get("ts"),
            })
            if only and sid == only:
                picked = s
        note = "只抓选中站点（10 分钟内复用缓存）；清单状态来自上次抓取，不额外请求。"
        if not only:
            return Response(success=True, data={
                "sites": [], "site_list": site_list,
                "totals": {"sites": 0, "ok": 0, "failed": 0, "items": 0, "exchangeable": 0,
                           "by_kind": {"upload": 0, "invite": 0, "temp_invite": 0},
                           "exchangeable_by_kind": {"upload": 0, "invite": 0, "temp_invite": 0},
                           "upload_items": 0, "invite_items": 0, "temp_invite_items": 0},
                "note": note,
            })
        if not picked:
            return Response(success=False, message="站点不存在，或不在可兑换站点列表里")
        r = self._be_fetch(only, picked, force=force)
        row = {
            "site_id": only,
            "site_name": str(picked.get("name") or picked.get("domain") or only),
            "domain": str(picked.get("domain") or ""),
            "ok": r.get("ok", False),
            "balance": r.get("balance"),
            "currency": r.get("currency") or "",
            "items": r.get("items") or [],
            "kinds": r.get("kinds") or {},
            "form_count": int(r.get("form_count") or 0),
            "why": r.get("why") or "",
        }
        by_kind = {"upload": 0, "invite": 0, "temp_invite": 0}
        can_kind = {"upload": 0, "invite": 0, "temp_invite": 0}
        for it in row["items"]:
            k = it.get("kind") or "upload"
            if k in by_kind:
                by_kind[k] += 1
                if not it.get("disabled"):
                    can_kind[k] += 1
        return Response(success=True, data={
            "sites": [row],
            "site_list": site_list,
            "totals": {
                "sites": 1, "ok": 1 if row["ok"] else 0, "failed": 0 if row["ok"] else 1,
                "items": sum(by_kind.values()), "exchangeable": sum(can_kind.values()),
                "by_kind": by_kind, "exchangeable_by_kind": can_kind,
                "upload_items": by_kind["upload"], "invite_items": by_kind["invite"],
                "temp_invite_items": by_kind["temp_invite"],
            },
            "note": note,
        })

    def bonus_exchange_act(self, site_id: Any = None, option: Any = None,
                           confirm: Any = None) -> Response:
        """手动兑换一个可换项（上传量 / 邀请名额 / 临时邀请）：默认干跑；``confirm=1`` 才真写。"""
        # ★ option 合法值含 0（多站第一项就是 opt=0），不能用 `str(option or '')` 判空
        def _to_int(v: Any, default: int) -> int:
            try:
                return int(str(v).strip())
            except (TypeError, ValueError):
                return default
        sid = _to_int(site_id, 0)
        opt = _to_int(option, -1)
        if not sid or opt < 0:
            return Response(success=False, message="缺少 site_id / option")
        site = self._get_site(sid)
        if not site:
            return Response(success=False, message="站点不存在")
        site_d = site if isinstance(site, dict) else {
            "id": sid, "name": getattr(site, "name", ""), "domain": getattr(site, "domain", ""),
            "url": getattr(site, "url", ""), "cookie": getattr(site, "cookie", ""),
            "ua": getattr(site, "ua", ""), "timeout": getattr(site, "timeout", 20),
        }
        # ★ 提交前强制重抓当次页面核对 option 仍是「可换项」（三类都认）
        cur = self._be_fetch(sid, site_d, force=True)
        target = next((it for it in (cur.get("items") or []) if int(it.get("option", -1)) == opt), None)
        if not target:
            return Response(success=False, message=(
                "该项不在当前页面的兑换列表里（页面可能变了），请刷新看板后再试"),
                data={"why": cur.get("why", "")})
        if target.get("disabled"):
            return Response(success=False, message=(
                f"站点当前判定不可换：{target.get('disabled_reason') or '按钮灰色'}"), data={"item": target})
        kind = str(target.get("kind") or "upload")
        kind_cn = {"upload": "上传量", "invite": "邀请名额", "temp_invite": "临时邀请"}.get(kind, "兑换项")
        preview = {"site": site_d.get("name") or site_d.get("domain"), "item": target,
                   "kind": kind, "kind_cn": kind_cn,
                   "balance": cur.get("balance"), "currency": cur.get("currency")}
        if not bool(_as_bool_arg(confirm)):
            # 邀请类不可退回，文案单独提示；上传量照旧
            tip = ("需 confirm=1 才提交兑换（会真实扣魔力，不可逆）" if kind == "upload"
                   else f"需 confirm=1 才提交「{kind_cn}」兑换（会真实扣魔力，名额换回不退，不可逆）")
            return Response(success=False, message=tip,
                            data={**preview, "need_confirm": True})

        from ..sites.bonus_exchange import exchange_upload, site_base  # noqa: WPS433

        base = site_base(site_d)
        cookie = str(site_d.get("cookie") or "")
        ua = str(site_d.get("ua") or "")
        timeout = int(site_d.get("timeout") or 20)
        proxies = None
        if bool(site_d.get("proxy")):
            try:
                from app.core.config import settings as _settings  # noqa: WPS433

                proxies = _settings.PROXY
            except Exception:  # noqa: BLE001
                proxies = None
        ok, status, msg, evidence = exchange_upload(base, opt, cookie, ua=ua,
                                                    timeout=timeout, proxies=proxies,
                                                    submit=str(target.get("submit") or "交换"))
        # ★ 19.16.32：兑换后立刻回读同一页面核对结果（余额 / 上传量 前后对比），
        #   结论直接返回给用户，不再让人自己去站点核对。
        #   写成功后前端带 refresh=1 重新拉看板（ttl=0 强制重抓）→ 余额/可换状态才更新；
        #   这里不直接动 collect 缓存（门面无 invalidate；靠显式 force 重抓更可控）。
        after: Dict[str, Any] = {}
        try:
            after = self._be_fetch(sid, site_d, force=True)
        except Exception as err:  # noqa: BLE001
            after = {"ok": False,
                     "why": f"回读异常：{type(err).__name__}: {str(err)[:120]}"}
        try:
            good, msg, verdict = self._be_verdict(kind, kind_cn, cur, after, target, ok, msg)
        except Exception as err:  # noqa: BLE001
            good = bool(ok)
            verdict = {"verified": False, "state": "unknown",
                       "verify_error": f"{type(err).__name__}: {str(err)[:120]}"}
        return Response(success=bool(good), message=msg,
                        data={"site_id": sid, "option": opt, "status": status,
                              "evidence": evidence, "item": target,
                              "refresh": True, **verdict})

    def _be_verdict(self, kind: str, kind_cn: str, before: Dict[str, Any],
                    after: Dict[str, Any], target: Dict[str, Any],
                    ok: bool, raw_msg: str) -> Tuple[bool, str, Dict[str, Any]]:
        """兑换回读裁决：用「兑换前」与「兑换后」两次回读的余额 / 上传量说话（★ 19.16.32）。

        NexusPHP 兑换是同步生效的：POST 返回后立刻重抓同一页面，余额应恰好少掉票价、
        上传量应增加对应 GB。据此给出可核实的结论，不把「去站点自己看」丢给用户。
        """
        def _f(v: Any) -> Optional[float]:
            try:
                return None if v is None else float(v)
            except (TypeError, ValueError):
                return None

        def _m(v: float) -> str:
            return f"{v:,.1f}"

        cur_cn = str(before.get("currency") or after.get("currency") or "魔力")
        b0, b1 = _f(before.get("balance")), _f(after.get("balance"))
        up0, up1 = _f(before.get("uploaded_gb")), _f(after.get("uploaded_gb"))
        price = _f(target.get("price"))
        size_gb = _f(target.get("size_gb"))
        spent = None if (b0 is None or b1 is None) else round(b0 - b1, 3)
        gained = None if (up0 is None or up1 is None) else round(up1 - up0, 3)
        data: Dict[str, Any] = {
            "balance_before": b0, "balance_after": b1,
            "uploaded_before": up0, "uploaded_after": up1,
            "spent": spent, "gained": gained, "price": price,
        }
        # 上传类：把「到账了多少上传量」写进结论（回读有上传量就用实测差值）
        up_note = ""
        if kind == "upload":
            if gained is not None and gained > 0:
                up_note = f"，上传量 +{gained:.2f} GB（{up0:.2f} → {up1:.2f} GB）"
            elif size_gb:
                up_note = f"，换得 {size_gb:.2f} GB 上传量"

        tol = max(0.5, (price or 0.0) * 0.02)
        paid = spent is not None and price is not None and spent >= price - tol
        # 明显没扣：扣得不足票价的一半（含 0 / 负数）
        zero = spent is not None and price is not None and spent < price * 0.5
        money = f"扣 {_m(spent)} {cur_cn}（余额 {_m(b0)} → {_m(b1)}）" if paid else ""
        if paid:
            data.update(verified=True, state="success")
            if ok:
                return True, f"兑换成功：已核实{money}{up_note}", data
            return True, (f"兑换成功：已核实{money}{up_note}"
                          f"（站点回显异常：{raw_msg}，但扣费已发生）"), data
        if zero:
            note = ("；" + raw_msg) if not ok else ""
            data.update(verified=True, state="failed")
            return False, (f"兑换未生效：已核对余额未扣减（{_m(b1)} {cur_cn}）{note}"), data
        if spent is not None:
            # 余额变动但和票价对不上（站点扣费口径不同 / 同时有别的扣费）
            note = ("；" + raw_msg) if not ok else ""
            data.update(verified=False, state="unknown")
            return bool(ok), (f"兑换结果待定：余额变动 {-spent:+,.1f} {cur_cn}，"
                              f"票价 {_m(price)}{up_note}{note}"), data
        # 余额读不到：保留站点原话，明确说没取到，不把核实责任甩给用户
        why = str(after.get("why") or "").strip()
        data.update(verified=False, state="unknown")
        if ok:
            return True, f"{raw_msg}；回读页面未取到余额，无法核对扣费", data
        return False, (f"{raw_msg}；回读站点页面失败（{why or '页面不可用'}），"
                       f"无法核对是否扣费"), data
