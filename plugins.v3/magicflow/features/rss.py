# -*- coding: utf-8 -*-
"""魔流 · rss —— 站点 RSS 订阅（只读）+ 凭据管理。

两类站点都支持：
  · NexusPHP：`/torrentrss.php?passkey=<passkey>`（只需 passkey）
  · 自有接口：整条 RSS URL（如 YemaPT `/api/rss/torrents?rssToken=...`）

凭据存插件数据表（`rss_passkeys`），回显一律脱敏；本模块只发 GET。
"""

import hashlib
import re
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.schemas import Response
from app.sdk.logging import logger

from ..common import RSS_PASSKEY_KEY
from ..kvstore import cache_get, cache_set
from ..collect import parse_rss_items

RSS_TTL = 300.0
_PK_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
_SECRET_Q_RE = re.compile(r"(passkey|rssToken|token|key)=([^&]+)", re.I)


class RssMixin:
    # ------------------------------------------------------------ 凭据存储
    def _rss_store(self) -> Dict[str, Any]:
        try:
            raw = self.get_data(RSS_PASSKEY_KEY)
            return dict(raw) if isinstance(raw, dict) else {}
        except Exception as err:  # noqa: BLE001
            logger.debug(f"rss 凭据读取失败: {err}")
            return {}

    def _rss_save_store(self, data: Dict[str, Any]) -> None:
        self.save_data(key=RSS_PASSKEY_KEY, value=dict(data or {}))

    def _rss_entry_of(self, sid: Any) -> Dict[str, Any]:
        # MP 站点表已有 rss 列 → 优先用；passkey 由插件补（MP 没有该列）
        # ★ JSON 优先：creds 里的 rss_url / passkey
        try:
            cred = self._cred_record(sid)
            if str(cred.get("rss_url") or "").strip():
                return {"url": str(cred.get("rss_url")).strip(), "at": 0}
            if str(cred.get("passkey") or "").strip():
                return {"passkey": str(cred.get("passkey")).strip(), "at": 0}
        except Exception:  # noqa: BLE001
            pass
        # MP 站点 rss（历史/手工配置）兜底
        try:
            site = self._get_site(sid)
            rss_url = str(getattr(site, "rss", "") or "").strip() if site else ""
            if rss_url:
                return {"url": rss_url, "at": 0}
        except Exception:  # noqa: BLE001
            pass
        rec = self._rss_store().get(str(sid))
        if isinstance(rec, dict):
            return dict(rec)
        if isinstance(rec, str) and rec:
            return {"passkey": rec}
        return {}
    @staticmethod
    def _rss_mask_secret(value: str) -> str:
        value = str(value or "")
        if not value:
            return ""
        if len(value) <= 8:
            return value[:2] + "****"
        return f"{value[:4]}…{value[-4:]}"

    @classmethod
    def _rss_mask_url(cls, url: str) -> str:
        def _sub(m):
            return f"{m.group(1)}={cls._rss_mask_secret(m.group(2))}"
        return _SECRET_Q_RE.sub(_sub, str(url or ""))

    def _rss_entry_view(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        url = str(rec.get("url") or "")
        pk = str(rec.get("passkey") or "")
        if url:
            return {"kind": "url", "masked": self._rss_mask_url(url), "configured": True}
        if pk:
            return {"kind": "passkey", "masked": self._rss_mask_secret(pk), "configured": True}
        return {"kind": "", "masked": "", "configured": False}

    def _rss_url_of(self, site: Any) -> str:
        rec = self._rss_entry_of(getattr(site, "id", ""))
        url = str(rec.get("url") or "").strip()
        if url:
            return url
        pk = str(rec.get("passkey") or "").strip()
        base = str(getattr(site, "url", "") or "").rstrip("/")
        if pk and base:
            return f"{base}/torrentrss.php?passkey={pk}"
        return ""

    # ------------------------------------------------------------ 配置 / 保存
    def get_rss_config(self) -> Response:
        # passkey 我们存；RSS / API Key 读 MP 站点（MP 已有列）
        try:
            rows: List[Dict[str, Any]] = []
            for item in self._list_sites() or []:
                sid = item.get("id")
                if sid is None:
                    continue
                site = self._get_site(sid)
                rss_url = str(getattr(site, "rss", "") or "") if site else ""
                apikey = str(getattr(site, "apikey", "") or "") if site else ""
                pk = self._cred_get(sid, "passkey")
                rows.append({
                    "site_id": sid,
                    "site_name": str(item.get("name") or item.get("domain") or sid),
                    "domain": str(item.get("domain") or ""),
                    "has_passkey": bool(pk),
                    "configured": bool(pk),
                    "kind": "passkey" if pk else "",
                    "masked": self._rss_mask_secret(pk),
                    "mp_rss_set": bool(rss_url),
                    "mp_apikey_set": bool(apikey),
                    "saved_at": 0,
                })
            rows.sort(key=lambda x: int(x.get("site_id") or 0))
            return Response(success=True, data={
                "sites": rows,
                "saved": sum(1 for r in rows if r.get("configured")),
                "total": len(rows),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取 RSS 配置失败：{err}")
    def save_rss_passkey(self, site_id: Any = None, passkey: Any = "") -> Response:
        # 只收 passkey；RSS URL / API Key 在 MP 站点里配
        try:
            sid = str(site_id or "").strip()
            if not sid:
                return Response(success=False, message="缺少 site_id")
            raw = str(passkey or "").strip()
            if raw.lower().startswith(("http://", "https://")):
                return Response(success=False,
                                message="RSS URL 请在 MP 站点配置里填（这里只存 passkey）")
            return self.save_cred(site_id=sid, field="passkey", value=raw)
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"保存 passkey 失败：{err}")
    # ------------------------------------------------------------ 抓取 / 解析

    # 19.10.30：RSS 解析已下沉 ``collect.parse_rss_items``（铁律 1「解析归采集」）。
    #   这里只剩「抓 + 判是不是 RSS + 缓存」；调用点见 ``_rss_fetch``。

    def _rss_fetch(self, site: Any, limit: int) -> Dict[str, Any]:
        """抓一次站点 RSS 并给出「能不能用」的结论（**不做解析**）。

        解析已归 ``collect.parse_rss_items``；这里只负责三件事：取 passkey 拼 URL、
        抓回来判「是不是 RSS」（有些站返回登录页 / passkey 被拒）、把结果连同
        ``ok/message`` 一起交给上层缓存。失败一律降级成 ``ok=False`` + 人话 message，
        不抛 —— 这个入口是给 UI 刷新用的，抛异常会白屏。
        """
        sid = str(getattr(site, "id", "") or "")
        url = self._rss_url_of(site)
        rec = self._rss_entry_of(sid)
        view = self._rss_entry_view(rec)
        out: Dict[str, Any] = {"has_passkey": bool(view.get("configured")),
                               "configured": bool(view.get("configured")),
                               "kind": view.get("kind") or "",
                               "ok": False, "items": [],
                               "message": "", "fetched_at": time.time()}
        if not url:
            out["message"] = "未配置 passkey / RSS 链接"
            return out
        # ★ 19.10.31：抓取改走 collect 唯一出口（铁律 2「只有一只手碰网络」）。
        #   两条实质收益，不只是「统一」：
        #     · RSS URL 是**用户可配**的（creds.rss_url 任意字符串）→ 裸 RequestUtils
        #       等于开了一个 SSRF 口子，谁都能让插件去抓内网地址；走门面后自动过
        #       ``_url_allowed_for_site`` 的同域校验。
        #     · 原先这 16 个站的 RSS 请求**完全不出现在 PV 账本和观测里**（盲区），
        #       现在过闸门 + 记账 + ``kind="rss"`` 可观测。
        #   ⚠ 行为差异（已评估接受）：
        #     · 门面 timeout 固定 60（原 site.timeout=15）→ 慢站点更宽容、卡住时更久；
        #     · 原 ``site.proxy`` 分支取消 —— 门面不支持站级代理。实测生产 16 站
        #       proxy 全为 0，当前无影响；将来真要支持代理，应在门面 ``_request``
        #       里统一加，而不是让每个采集点自己拼 RequestUtils。
        coll = getattr(self, "collect", None)
        if coll is None:
            out["message"] = "采集门面未就绪（插件尚未初始化完成）"
            return out
        got = coll.http.text(sid, url, kind="rss")
        if not got.ok:
            out["message"] = got.error or "站点无响应"
            return out
        text = got.text or ""
        low = text[:200].lower()
        if not text:
            out["message"] = "站点无响应"
            return out
        if "passkey" in low and "<rss" not in low and "<?xml" not in low:
            out["message"] = text[:80] or "passkey 被拒绝"
            return out
        if "rss" not in low and "<rss" not in text and "<?xml" not in text:
            out["message"] = "返回不是 RSS（可能未登录或被拦截）"
            return out
        try:
            out["items"] = parse_rss_items(text, max(1, int(limit or 30)))
            out["ok"] = True
            out["message"] = f"{len(out['items'])} 条"
            out["rss_url"] = self._rss_mask_url(url)
            return out
        except Exception as err:  # noqa: BLE001
            out["message"] = f"{type(err).__name__}: {err}"
            return out

    def get_rss_state(self, site_id: Any = None, limit: Any = 30, refresh: Any = None) -> Response:
        try:
            lim = max(1, min(200, int(limit or 30)))
            force = bool(self._as_bool_arg(refresh))
            want = str(site_id).strip() if site_id not in (None, "", "0") else ""
            rows: List[Dict[str, Any]] = []
            for item in self._list_sites() or []:
                sid = item.get("id")
                if sid is None or (want and str(sid) != want):
                    continue
                site = self._get_site(sid)
                if not site:
                    continue
                rec = self._rss_entry_of(sid)
                token = str(rec.get("url") or rec.get("passkey") or "")
                key = f"{sid}:{lim}:{hashlib.sha1(token.encode()).hexdigest()[:8] if token else 'none'}"
                data = None if force else cache_get(self, "rss", key, RSS_TTL)
                if not isinstance(data, dict):
                    data = self._rss_fetch(site, lim)
                    cache_set(self, "rss", key, data, RSS_TTL)
                row = dict(data)
                row.update({
                    "site_id": sid,
                    "site_name": str(item.get("name") or item.get("domain") or sid),
                    "domain": str(item.get("domain") or ""),
                })
                rows.append(row)
            return Response(success=True, data={
                "sites": rows,
                "total": sum(len(r.get("items") or []) for r in rows),
                "with_passkey": sum(1 for r in rows if r.get("configured")),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取 RSS 失败：{err}")
