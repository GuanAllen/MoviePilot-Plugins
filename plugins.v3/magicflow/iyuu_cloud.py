"""IYUU 云端辅种接入（可选，仅用云端 Token）。

设计口径（与主人 2026-09-26 确认一致）：
- **不填 Token** → 完全不启用，退回插件内置的「跨站特征码复用」方案。
- **填了 Token** → 用 IYUU 云端做辅种匹配；构造下载链所需的站点凭证按优先级解析：
  ① 用户在「插件设置 → IYUU」里手填的 passkey/uid/downhash → ② MoviePilot 站点配置
  （apikey/token 等）→ ③ 用站点 cookie 抓页面自动提取 → ④ 都不行 → 该站跳过、回退内置方案。

仅依赖公开云端 API（不依赖本地 IYUU 容器）：
  - GET  /reseed/sites/index             站点表（sid / 域名 / 下载页模板 / 是否必须 cookie）
  - POST /reseed/sites/reportExisting    上报持有站点 → sid_sha1（云端声明有效期 7 天）
  - POST /reseed/index/index             批量查询：我的 infohash 列表 → 他站同资源
  - GET  /reseed/users/profile           账号信息（用于「测试 Token」）

任何网络/解析失败都返回空结果，由调用方回退，绝不抛给主流程。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

IYUU_BASE = "https://2025.iyuu.cn"
# 云端部分接口会校验 version 字段，给一个较新的合法值即可。
IYUU_VERSION = "8.2.0"

_SITES_TTL = 24 * 3600.0        # 站点表缓存
_REPORT_TTL = 7 * 24 * 3600.0   # sid_sha1 缓存（云端声明 7 天）
_QUERY_MIN_INTERVAL = 3.0       # 两次辅种查询之间的最小间隔（秒）——云端有严格限流
_RATE_BACKOFF = 60.0            # 命中「访问频率过快」后的冷却

_PASSKEY_RE = re.compile(r"passkey=([0-9a-fA-F]{16,64})")
_HASH_RE = re.compile(r"(?:downhash|hash)=([0-9a-zA-Z]{8,64})")


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class IyuuCloud:
    """IYUU 云端客户端（Token 为空则 `enabled=False`，所有方法直接返回空）。"""

    def __init__(self, token: str = "", logger: Any = None) -> None:
        self._token = (token or "").strip()
        self._log = logger
        self._lock = threading.Lock()
        self._sites: Optional[Dict[str, Dict[str, Any]]] = None
        self._sites_at = 0.0
        self._sid_sha1: Optional[str] = None
        self._sid_sha1_at = 0.0
        self._last_query_at = 0.0
        self._blocked_until = 0.0

    # ---------------------------------------------------------------- 基础
    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def set_token(self, token: str) -> None:
        token = (token or "").strip()
        if token != self._token:
            self._token = token
            self._sites = None
            self._sid_sha1 = None
            self._blocked_until = 0.0

    def _warn(self, msg: str) -> None:
        if self._log is not None:
            try:
                self._log(f"IYUU：{msg}", "warning")
            except Exception:
                pass

    def _request(self, method: str, path: str, params: Optional[dict] = None,
                 form: Optional[dict] = None, timeout: int = 20) -> Optional[dict]:
        """发一个请求并返回云端 JSON（code==0 才算成功）。失败返回 None。"""
        if not self.enabled:
            return None
        url = IYUU_BASE + path
        if params:
            url += "?" + urlencode(params)
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433 惰性导入
        except Exception:
            return None
        try:
            req = RequestUtils(headers={"token": self._token}, timeout=timeout)
            if method.upper() == "GET":
                resp = req.get_res(url=url)
            else:
                resp = req.post(url=url, data=form or {})
            if not resp or not resp.ok:
                self._warn(f"{path} 请求失败 status={getattr(resp, 'status_code', '?')}")
                return None
            data = resp.json()
        except Exception as err:  # noqa: BLE001
            self._warn(f"{path} 请求异常：{err}")
            return None
        if not isinstance(data, dict):
            return None
        code = data.get("code", 0)
        if code:
            msg = str(data.get("msg") or "")
            if code == 429 or "频率" in msg or "过快" in msg:
                # 限流：退避，别把云端惹毛
                self._blocked_until = time.time() + _RATE_BACKOFF
            self._warn(f"{path} 返回 code={code} msg={msg}")
            return None
        return data

    # ---------------------------------------------------------------- 站点表
    def sites(self, force: bool = False) -> Dict[str, Dict[str, Any]]:
        """站点表：site(小写英文名) -> 站点元数据（含 sid / 域名 / 下载页模板）。"""
        now = time.time()
        if not force and self._sites is not None and now - self._sites_at < _SITES_TTL:
            return self._sites
        data = self._request("GET", "/reseed/sites/index")
        table: Dict[str, Dict[str, Any]] = {}
        if data:
            for item in (data.get("data") or {}).get("sites") or []:
                name = str(item.get("site") or "").strip().lower()
                if name:
                    table[name] = item
        if table:
            self._sites = table
            self._sites_at = now
        return self._sites or {}

    def sid_by_domain(self, domain: str) -> Optional[int]:
        """按域名（base_url）反查 IYUU sid。"""
        dom = (domain or "").strip().lower().lstrip(".")
        if not dom:
            return None
        if dom.startswith("www."):
            dom = dom[4:]
        for item in self.sites().values():
            base = str(item.get("base_url") or "").strip().lower().lstrip(".")
            if base and (base == dom or base.endswith("." + dom) or dom.endswith("." + base)):
                try:
                    return int(item.get("id"))
                except (TypeError, ValueError):
                    return None
        return None

    # ------------------------------------------------------------ 持有站点哈希
    def sid_sha1(self, sids: Optional[List[int]] = None) -> Optional[str]:
        """上报持有站点 → sid_sha1（内部缓存；sids 变化时重新上报）。"""
        now = time.time()
        key = ",".join(str(int(s)) for s in sorted(sids or []))
        if (self._sid_sha1 and self._sid_sha1_at and now - self._sid_sha1_at < _REPORT_TTL
                and key == self._sid_sha1_key):
            return self._sid_sha1
        if not sids:
            return None
        # bracket 形式：sid_list[]=3&sid_list[]=6 …（json 形式会被云端拒）
        form = {f"sid_list[{i}]": int(s) for i, s in enumerate(sids)}
        data = self._request("POST", "/reseed/sites/reportExisting", form=form)
        sha1 = ((data or {}).get("data") or {}).get("sid_sha1")
        if sha1:
            self._sid_sha1 = str(sha1)
            self._sid_sha1_key = key
            self._sid_sha1_at = now
        return self._sid_sha1

    # ------------------------------------------------------------ 辅种批量查询
    def query(self, infohashes: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """批量查询：提交 infohash 列表 → {我的hash: [{info_hash, sid, torrent_id}, ...]}。

        命中限流/失败一律返回空字典（调用方回退）。
        """
        hashes = sorted({(h or "").strip().lower() for h in infohashes if h})
        if not self.enabled or not hashes:
            return {}
        now = time.time()
        if now < self._blocked_until:
            return {}
        sids = []
        for item in self.sites().values():
            try:
                sids.append(int(item.get("id")))
            except (TypeError, ValueError):
                continue
        sid_sha1 = self.sid_sha1(sids)
        if not sid_sha1:
            return {}
        wait = _QUERY_MIN_INTERVAL - (now - self._last_query_at)
        if wait > 0:
            time.sleep(min(wait, _QUERY_MIN_INTERVAL))
        payload = json.dumps(hashes, separators=(",", ":"))
        data = self._request("POST", "/reseed/index/index", form={
            "hash": payload,
            "sha1": _sha1(payload),
            "sid_sha1": sid_sha1,
            "timestamp": int(time.time()),
            "version": IYUU_VERSION,
        }, timeout=25)
        self._last_query_at = time.time()
        if not data:
            return {}
        result = data.get("data") or {}
        out: Dict[str, List[Dict[str, Any]]] = {}
        if isinstance(result, dict):
            for key, val in result.items():
                rows = (val or {}).get("torrent") if isinstance(val, dict) else None
                if isinstance(rows, list) and rows:
                    out[str(key).lower()] = [r for r in rows if isinstance(r, dict)]
        return out

    def sibling_hashes(self, infohashes: List[str]) -> Dict[str, List[str]]:
        """{我的hash: [他站同资源 infohash, ...]} —— 只取 infohash，用于本机命中判定。"""
        out: Dict[str, List[str]] = {}
        for key, rows in self.query(infohashes).items():
            sibs: List[str] = []
            for r in rows:
                ih = str(r.get("info_hash") or "").strip().lower()
                if ih and ih not in sibs:
                    sibs.append(ih)
            if sibs:
                out[key] = sibs
        return out

    # ------------------------------------------------------------ 测试连通
    def profile(self) -> Optional[dict]:
        data = self._request("GET", "/reseed/users/profile")
        return (data or {}).get("data") if data else None


# ---------------------------------------------------------------------------
# 下载链构造 + 站点凭证解析（模块级纯函数，便于单测）
# ---------------------------------------------------------------------------

def harvest_passkey(cookie: str, base_url: str, is_https: int = 2,
                    timeout: int = 15, referer: str = "") -> Optional[str]:
    """用站点 cookie 抓「浏览页/个人页」把 passkey 抠出来（NexusPHP 通用）。

    返回 None 表示没抠到（调用方回退手填配置）。
    """
    if not cookie or not base_url:
        return None
    scheme = "https" if int(is_https or 0) in (1, 2) else "http"
    biz = base_url.strip().strip("/")
    if biz.startswith("http"):
        biz = biz.split("://", 1)[1]
    candidates = [
        f"{scheme}://{biz}/torrents.php",
        f"{scheme}://{biz}/getusertorrentlistajax.php",
        f"{scheme}://{biz}/usercp.php",
    ]
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433
    except Exception:
        return None
    for url in candidates:
        try:
            resp = RequestUtils(cookies=cookie, timeout=timeout,
                                referer=referer or f"{scheme}://{biz}/").get_res(url=url)
            if not resp or not resp.ok:
                continue
            text = resp.text or ""
            m = _PASSKEY_RE.search(text)
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


def resolve_link_vars(domain: str, user_fill: Optional[Dict[str, str]],
                      mp_site: Optional[Dict[str, Any]] = None,
                      cookie: str = "", base_url: str = "",
                      is_https: int = 2) -> Dict[str, str]:
    """解析下载链模板变量（passkey/uid/downhash/hash/apikey）。

    优先级：用户手填 > MoviePilot 站点配置 > 自动抓取。都不行则返回已拿到的部分。
    """
    variables: Dict[str, str] = {}
    mp_site = mp_site or {}
    user_fill = user_fill or {}
    # ① 用户手填
    for key in ("passkey", "uid", "downhash", "authkey", "rsskey"):
        val = str(user_fill.get(key) or "").strip()
        if val:
            variables[key] = val
    # ② MoviePilot 站点配置
    mp_apikey = str(mp_site.get("apikey") or "").strip()
    mp_token = str(mp_site.get("token") or "").strip()
    if mp_apikey and "apikey" not in variables:
        variables["apikey"] = mp_apikey
    if mp_token and "token" not in variables:
        variables["token"] = mp_token
    # ③ 自动抓取 passkey（仅在需要且缺 passkey 时）
    if "passkey" not in variables and cookie and base_url:
        got = harvest_passkey(cookie, base_url, is_https=is_https)
        if got:
            variables["passkey"] = got
    return variables


def build_download_url(template: str, base_url: str, is_https: int, torrent_id: Any,
                       variables: Dict[str, str]) -> Optional[str]:
    """按云端 `download_page` 模板拼下载链。缺模板/缺变量返回 None。"""
    if not template:
        return None
    scheme = "https" if int(is_https or 0) in (1, 2) else "http"
    biz = (base_url or "").strip().strip("/")
    if biz.startswith("http"):
        biz = biz.split("://", 1)[1]
    if not biz:
        return None
    path = template.replace("{}", str(torrent_id or ""))
    missing = []
    for name in re.findall(r"\{([a-zA-Z0-9_]+)\}", path):
        val = str(variables.get(name) or "").strip()
        if not val:
            missing.append(name)
            continue
        path = path.replace("{" + name + "}", val)
    if missing:
        return None
    return f"{scheme}://{biz}/{path.lstrip('/')}"
