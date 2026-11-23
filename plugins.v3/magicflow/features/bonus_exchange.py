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

from typing import Any, Dict, List, Optional

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


class BonusExchangeMixin:
    """魔力兑换：看板 + 手动兑换上传量。"""

    def _be_skip(self, site: Dict[str, Any]) -> bool:
        domain = str(site.get("domain") or site.get("url") or "").lower()
        return any(d in domain for d in _SKIP_DOMAINS)

    def _be_fetch(self, site_id: int, site: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
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
        """魔力兑换看板：逐站（或单站）当前魔力 + 三类兑换项（上传量 / 邀请 / 临时邀请）。只读。"""
        force = bool(_as_bool_arg(refresh))
        only = int(site_id) if str(site_id or "").isdigit() else None
        sites: List[Dict[str, Any]] = []
        try:
            all_sites = self._list_sites() or []
        except Exception:  # noqa: BLE001
            all_sites = []
        for s in all_sites:
            if not isinstance(s, dict):
                continue
            sid = int(s.get("id", 0) or 0)
            if not sid or (only and sid != only) or self._be_skip(s):
                continue
            sites.append(s)
        rows: List[Dict[str, Any]] = []
        for s in sites:
            sid = int(s.get("id", 0))
            r = self._be_fetch(sid, s, force=force)
            rows.append({
                "site_id": sid,
                "site_name": str(s.get("name") or s.get("domain") or sid),
                "domain": str(s.get("domain") or ""),
                "ok": r.get("ok", False),
                "balance": r.get("balance"),
                "currency": r.get("currency") or "",
                "items": r.get("items") or [],
                "kinds": r.get("kinds") or {},
                "form_count": int(r.get("form_count") or 0),
                "why": r.get("why") or "",
            })
        ok_cnt = sum(1 for r in rows if r["ok"])
        by_kind = {"upload": 0, "invite": 0, "temp_invite": 0}
        can_kind = {"upload": 0, "invite": 0, "temp_invite": 0}
        for r in rows:
            for it in r["items"]:
                k = it.get("kind") or "upload"
                if k in by_kind:
                    by_kind[k] += 1
                    if not it.get("disabled"):
                        can_kind[k] += 1
        items_all = sum(by_kind.values())
        can_all = sum(can_kind.values())
        # ★ 对账铁律：items_all == upload+invite+temp_invite，can_all == 各类可换之和；
        #   前端统计条与各站角标相加都必须等于这两个数。
        return Response(success=True, data={
            "sites": rows,
            "totals": {
                "sites": len(rows), "ok": ok_cnt, "failed": len(rows) - ok_cnt,
                "items": items_all, "exchangeable": can_all,
                "by_kind": by_kind, "exchangeable_by_kind": can_kind,
                "upload_items": by_kind["upload"], "invite_items": by_kind["invite"],
                "temp_invite_items": by_kind["temp_invite"],
            },
            "note": ("只读看板：可换上传量 / 邀请名额 / 临时邀请。灰色=站点判定不可换"
                     "（分享率已很高 / 魔力不足 / 等级不足）。点兑换需二次确认，提交前会重抓页面核对。"),
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
        # ★ 写成功后前端带 refresh=1 重新拉看板（ttl=0 强制重抓）→ 余额/可换状态才更新。
        #   这里不直接动 collect 缓存（门面无 invalidate；靠显式 force 重抓更可控）。
        return Response(success=bool(ok), message=msg,
                        data={"site_id": sid, "option": opt, "status": status,
                              "evidence": evidence, "item": target, "refresh": bool(ok)})
