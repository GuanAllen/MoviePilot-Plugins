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
from xml.etree import ElementTree as ET

from app.schemas import Response
from app.sdk.logging import logger

from ..common import RSS_PASSKEY_KEY
from ..kvstore import cache_get, cache_set

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
    @staticmethod
    def _rss_parse(xml_text: str, limit: int) -> List[Dict[str, Any]]:
        import re as _re

        root = ET.fromstring(xml_text)
        out: List[Dict[str, Any]] = []
        promo_re = _re.compile(r"[\[\(【]\s*(免费|Freeleech|Free|2x|2X|50%|30%|70%)\s*[\]\)】]", _re.I)
        seed_re = _re.compile(r"(?:seeders?|做种(?:数|者)?|种(?:子)?数)\D{0,8}(\d+)", _re.I)
        leech_re = _re.compile(r"(?:leechers?|下载(?:数|者)?|完成(?:数)?)\D{0,8}(\d+)", _re.I)
        for it in root.iter("item"):
            def _g(tag: str) -> str:
                el = it.find(tag)
                return (el.text or "").strip() if el is not None else ""
            size = ""
            enc = it.find("enclosure")
            if enc is not None:
                size = str(enc.get("length") or "")
            if not size:
                # 有些站把体积写进标题（M-Team 的 [大小] 格式）
                msz = _re.search(r"(\d+(?:\.\d+)?)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)", _g("title"), _re.I)
                if msz:
                    _num = float(msz.group(1))
                    _unit = msz.group(2).upper().rstrip("IB").rstrip("B")
                    _mult = {"T": 1024 ** 4, "G": 1024 ** 3, "M": 1024 ** 2, "K": 1024}.get(_unit[:1], 0)
                    if _mult:
                        size = str(int(_num * _mult))
            title = _g("title")
            desc = _g("description")
            blob = f"{title} {desc[:1200]}"
            m = promo_re.search(blob)
            ms = seed_re.search(blob)
            ml = leech_re.search(blob)
            out.append({
                "title": title,
                "link": _g("link"),
                "guid": _g("guid"),
                "pub": _g("pubDate"),
                "category": _g("category"),
                "comments": _g("comments"),
                "size": size,
                "enclosure": (enc.get("url") if enc is not None else "") or "",
                "promo": m.group(1) if m else "",
                "seeders": int(ms.group(1)) if ms else None,
                "leechers": int(ml.group(1)) if ml else None,
                "desc": desc[:200],
            })
            if len(out) >= limit:
                break
        return out
    def _rss_fetch(self, site: Any, limit: int) -> Dict[str, Any]:
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
        try:
            from app.utils.http import RequestUtils  # noqa: WPS433

            proxies = None
            if bool(getattr(site, "proxy", 0)):
                try:
                    from app.core.config import settings as _s  # noqa: WPS433
                    proxies = _s.PROXY
                except Exception:  # noqa: BLE001
                    proxies = None
            req = RequestUtils(
                cookies=str(getattr(site, "cookie", "") or ""),
                ua=str(getattr(site, "ua", "") or ""),
                proxies=proxies,
                timeout=int(getattr(site, "timeout", 0) or 0) or 20,
                referer=str(getattr(site, "url", "") or ""),
            )
            res = req.get_res(url=url)
            text = (res.text if res is not None else "") or ""
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
            out["items"] = self._rss_parse(text, max(1, int(limit or 30)))
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
