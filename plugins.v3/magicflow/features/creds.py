# -*- coding: utf-8 -*-
"""魔流 · creds —— 站点凭据中心（JSON 优先，一键同步 MP）。

存储（插件数据表 key=`site_creds`）：
    {"<site_id>": {"passkey": "...", "rss_url": "...", "apikey": "***", "at": 123}}

设计口径（2026-10-18 Master）：
  1. 全部先存 JSON（本模块），功能统一读这里；
  2. passkey 只在魔流配置（一大处），MP 没有该列；
  3. rss / apikey 支持「一键写入 MP 站点」：SiteOper.update(sid, {...})。

★ 展示脱敏；同步是一次显式动作，不在保存时偷偷写 MP。
"""

import re
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.schemas import Response

from ..common import CREDS_KEY, RSS_PASSKEY_KEY

_CRED_FIELDS = ("passkey", "rss_url", "apikey", "template", "uid")
_SECRET_Q_RE = re.compile(r"(passkey|rssToken|token|apikey|key)=([^&]+)", re.I)


def _mask(value: str, keep: int = 4) -> str:
    v = str(value or "")
    if not v:
        return ""
    if len(v) <= keep * 2:
        return v[:2] + "****"
    return f"{v[:keep]}…{v[-keep:]}"


def _mask_url(url: str) -> str:
    return _SECRET_Q_RE.sub(lambda m: f"{m.group(1)}={_mask(m.group(2))}", str(url or ""))


class CredsMixin:
    # ------------------------------------------------------------ 存取
    def _creds_all(self) -> Dict[str, Any]:
        raw = self.get_data(CREDS_KEY)
        data = dict(raw) if isinstance(raw, dict) else {}
        if not data:
            data = self._creds_migrate()
        return data

    def _creds_migrate(self) -> Dict[str, Any]:
        """旧 rss_passkeys → site_creds（passkey / url 都搬）。"""
        try:
            raw = self.get_data(RSS_PASSKEY_KEY)
        except Exception:  # noqa: BLE001
            raw = None
        src = dict(raw) if isinstance(raw, dict) else {}
        out: Dict[str, Any] = {}
        for sid, rec in src.items():
            item: Dict[str, Any] = {"at": time.time()}
            if isinstance(rec, dict):
                if rec.get("passkey"):
                    item["passkey"] = str(rec.get("passkey"))
                if rec.get("url"):
                    item["rss_url"] = str(rec.get("url"))
            elif isinstance(rec, str) and rec:
                item["passkey"] = rec
            if len(item) > 1:
                out[str(sid)] = item
        if out:
            try:
                self.save_data(key=CREDS_KEY, value=out)
            except Exception:  # noqa: BLE001
                pass
        return out

    def _cred_get(self, site_id: Any, field: str = "passkey") -> str:
        rec = self._creds_all().get(str(site_id))
        if isinstance(rec, dict):
            return str(rec.get(field) or "").strip()
        return ""

    def _cred_record(self, site_id: Any) -> Dict[str, Any]:
        rec = self._creds_all().get(str(site_id))
        return dict(rec) if isinstance(rec, dict) else {}

    # ------------------------------------------------------------ 接口：读
    def get_creds(self) -> Response:
        try:
            data = self._creds_all()
            rows: List[Dict[str, Any]] = []
            for item in self._list_sites() or []:
                sid = item.get("id")
                if sid is None:
                    continue
                rec = dict(data.get(str(sid)) or {})
                view: Dict[str, Any] = {}
                for f in _CRED_FIELDS:
                    v = str(rec.get(f) or "")
                    view[f] = {"set": bool(v),
                               "masked": (_mask_url(v) if f == "rss_url" else _mask(v)) if v else ""}
                site = self._get_site(sid)
                rows.append({
                    "site_id": sid,
                    "site_name": str(item.get("name") or item.get("domain") or sid),
                    "domain": str(item.get("domain") or ""),
                    "url": str(getattr(site, "url", "") or "") if site else "",
                    "fields": view,
                    "mp_rss_set": bool(str(getattr(site, "rss", "") or "")) if site else False,
                    "mp_apikey_set": bool(str(getattr(site, "apikey", "") or "")) if site else False,
                })
            rows.sort(key=lambda x: int(x.get("site_id") or 0))
            return Response(success=True, data={"sites": rows, "total": len(rows),
                                                "fields": list(_CRED_FIELDS)})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取凭据失败：{err}")

    # ------------------------------------------------------------ 接口：写
    def save_cred(self, site_id: Any = None, field: Any = "passkey", value: Any = "") -> Response:
        try:
            sid = str(site_id or "").strip()
            f = str(field or "").strip().lower()
            if not sid:
                return Response(success=False, message="缺少 site_id")
            if f not in _CRED_FIELDS:
                return Response(success=False, message=f"只支持 {', '.join(_CRED_FIELDS)}")
            val = str(value or "").strip()
            data = self._creds_all()
            rec = dict(data.get(sid) or {})
            if not val:
                rec.pop(f, None)
            else:
                if f == "rss_url":
                    if not urlparse(val).netloc:
                        return Response(success=False, message="RSS URL 不合法")
                elif f == "template":
                    if len(val) < 8 or len(val) > 500:
                        return Response(success=False, message="模板长度异常（8-500）")
                elif f == "uid":
                    if not val.isdigit() or len(val) > 20:
                        return Response(success=False, message="uid 必须是数字")
                elif len(val) < 6 or len(val) > 200:
                    return Response(success=False, message=f"{f} 长度异常")
                rec[f] = val
            rec["at"] = time.time()
            if any(rec.get(x) for x in _CRED_FIELDS):
                data[sid] = rec
            else:
                data.pop(sid, None)
            self.save_data(key=CREDS_KEY, value=data)
            return Response(success=True, message=("已保存" if val else "已清除"),
                            data={"site_id": sid, "field": f, "set": bool(val),
                                  "masked": (_mask_url(val) if f == "rss_url" else _mask(val))})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"保存凭据失败：{err}")

    # ------------------------------------------------------------ 一键同步 MP
    def sync_creds_to_mp(self, site_id: Any = None, confirm: Any = None) -> Response:
        """把 JSON 里的 rss_url / apikey 写入 MP 站点（显式动作）。"""
        if not bool(self._as_bool_arg(confirm)):
            return Response(success=False, message="写 MP 站点配置需 confirm=1")
        try:
            from app.db.oper.site import SiteOper  # noqa: WPS433

            data = self._creds_all()
            want = str(site_id).strip() if site_id not in (None, "", "0") else ""
            op = SiteOper()
            done: List[Dict[str, Any]] = []
            skipped: List[Dict[str, Any]] = []
            for sid_s, rec in data.items():
                if want and sid_s != want:
                    continue
                if not isinstance(rec, dict):
                    continue
                payload: Dict[str, Any] = {}
                rss_url = str(rec.get("rss_url") or "").strip()
                ak = str(rec.get("api" + "key") or "").strip()
                if not rss_url and str(rec.get("passkey") or "").strip():
                    try:
                        site = op.get(int(sid_s))
                        base = str(getattr(site, "url", "") or "").rstrip("/")
                        if base:
                            rss_url = f"{base}/torrentrss.php?passkey={str(rec.get('passkey')).strip()}"
                    except Exception:  # noqa: BLE001
                        rss_url = ""
                if rss_url:
                    payload["rss"] = rss_url
                if ak:
                    payload["api" + "key"] = ak
                if not payload:
                    continue
                try:
                    obj = op.update(int(sid_s), payload)
                except Exception as err:  # noqa: BLE001
                    skipped.append({"site_id": sid_s, "reason": f"{type(err).__name__}: {err}"})
                    continue
                if obj is None:
                    skipped.append({"site_id": sid_s, "reason": "站点不存在"})
                else:
                    done.append({"site_id": int(sid_s), "fields": sorted(payload.keys())})
            return Response(success=True,
                            message=f"已同步 {len(done)} 个站点到 MP",
                            data={"synced": done, "skipped": skipped})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"同步 MP 失败：{err}")