"""
MagicFlow 云盘归档（cloud_archive.py）

目标：**本地当热区、夸克当冷库**。把本地库里的成品大文件上传到夸克（经 OpenList），
本地腾空；OpenList 的 Strm 视图会自动生成播放指针，飞牛影视直接能播。

链路（2026-09-26 实测）::

    本地文件  --PUT /api/fs/put-->  OpenList `/quark`(Quark cookie 驱动, 可写)
                                       └─ 同一夸克账号目录 = OpenList `/quark_tv`(只读)
                                            └─ Strm 视图 `/movie` 自动生成 <name>.strm
                                                 └─ 飞牛挂载 /vol02/.../movie/<name>.strm → 影视播放

设计红线：
- **默认 dry-run**；**默认不删本地**；删本地必须显式 `delete_local=True` 且由上层确认。
- 只依赖 OpenList HTTP API（不碰远程挂载、不碰 MP 核心、不碰别人插件）。
- 所有网络调用失败都返回错误信息，不抛出到主流程。
"""
import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

# 视为「媒体文件」的扩展名
VIDEO_EXTS = (
    ".mp4", ".mkv", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".flv",
    ".rmvb", ".webm", ".iso", ".mpg", ".mpeg", ".m4v",
)

# 默认忽略的目录名（下载区/刷流区/回收站/蓝光原盘结构等）
DEFAULT_EXCLUDE_DIRS = {
    "下载", "刷流", "下载区", "临时", "临时下载", "未整理", "回收站",
    "download", "downloads", "temp", "tmp", "incomplete", "trash",
    "@eaDir", "#recycle",
    # 蓝光原盘（BDMV 是一个目录结构，不能当单片上传；整盘归档需单独处理）
    "BDMV", "CERTIFICATE",
}

# 默认排除路径（相对库根）
DEFAULT_EXCLUDE_PATHS = ("/movie/刷流", "/movie/下载")

DEFAULT_TARGET_TEMPLATE = "/quark/movie/{rel}"

CATEGORY_DIRS = ("电影", "电视剧")

_RE_YEAR = re.compile(r"\((\d{4})\)")


class OpenListError(Exception):
    """OpenList 调用异常。"""


class _ProgressReader:
    """包一层文件对象：让 requests 能算出 Content-Length，同时支持进度回调与限速。"""

    def __init__(self, fh, size: int, progress_cb: Optional[Callable[[int, int], None]] = None, limit_bps: float = 0.0):
        self._fh = fh
        self._size = int(size or 0)
        self._sent = 0
        self._cb = progress_cb
        self._limit = float(limit_bps or 0.0)
        self._t0 = time.time()

    # requests/urllib3 需要这些
    def __len__(self) -> int:
        return self._size

    def tell(self) -> int:
        return self._sent

    def read(self, n: int = -1) -> bytes:
        chunk = self._fh.read(n if n and n > 0 else 1024 * 1024)
        if not chunk:
            return b""
        self._sent += len(chunk)
        if self._cb:
            try:
                self._cb(self._sent, self._size)
            except Exception:  # noqa: BLE001
                pass
        if self._limit > 0:
            expect = self._sent / self._limit
            elapsed = time.time() - self._t0
            if expect > elapsed:
                time.sleep(min(5.0, expect - elapsed))
        return chunk

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass

    # 部分客户端（如 requests 重试）会检查这些属性
    @property
    def closed(self) -> bool:
        return getattr(self._fh, "closed", False)

    def seekable(self) -> bool:
        return False

    def readable(self) -> bool:
        return True


class OpenListClient:
    """OpenList（v4.x，AList 分支）HTTP 客户端（只读+上传）。

    鉴权：OpenList 设置的 **令牌（token）** —— 放在 `Authorization` 头里。
    """

    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base = str(base_url or "").rstrip("/")
        self.token = str(token or "").strip()
        self.timeout = float(timeout or 60.0)
        self._session = None

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    @property
    def session(self):
        if self._session is None:
            import requests  # 惰性：仅在真正用时导入

            s = requests.Session()
            s.headers.update({"Authorization": self.token})
            self._session = s
        return self._session

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def _post(self, path: str, payload: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        try:
            r = self.session.post(
                self._url(path),
                data=json.dumps(payload or {}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=timeout or self.timeout,
            )
        except Exception as err:  # noqa: BLE001
            raise OpenListError(f"请求失败：{err}") from err
        if r.status_code in (401, 403):
            raise OpenListError("鉴权失败（token 无效或无权限）")
        try:
            data = r.json()
        except Exception as err:  # noqa: BLE001
            raise OpenListError(f"响应不是 JSON（HTTP {r.status_code}）") from err
        if str(data.get("code")) not in ("200", "None") and data.get("code") != 200:
            raise OpenListError(str(data.get("message") or f"code={data.get('code')}"))
        return data.get("data") if isinstance(data.get("data"), (dict, list)) else {}

    def _get(self, path: str, params: Optional[dict] = None, timeout: Optional[float] = None) -> Any:
        try:
            r = self.session.get(self._url(path), params=params or {}, timeout=timeout or self.timeout)
        except Exception as err:  # noqa: BLE001
            raise OpenListError(f"请求失败：{err}") from err
        if r.status_code in (401, 403):
            raise OpenListError("鉴权失败（token 无效或无权限）")
        try:
            data = r.json()
        except Exception as err:  # noqa: BLE001
            raise OpenListError(f"响应不是 JSON（HTTP {r.status_code}）") from err
        return data.get("data")

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------
    def debug_put(self, remote_path: str = "", size: int = 1024) -> Dict[str, Any]:
        """诊断：把 1KB 随机数据用几种方式 PUT 到 OpenList，返回每种的结果。

        用于定位「容器内上传失败但宿主 curl 成功」这类环境差异。
        """
        import os as _os

        out: Dict[str, Any] = {}
        payload = _os.urandom(max(1, int(size)))
        path = str(remote_path or "/quark/.mf_diag.bin")
        hdr = quote(path, safe="")
        out["remote"] = path
        out["encoded"] = hdr
        out["encoded_len"] = len(hdr)
        url = self._url("/api/fs/put")

        def _try(label, **kw):
            try:
                r = self.session.put(url, timeout=(10.0, 120.0), **kw)
                out[label] = {"http": r.status_code, "ctype": r.headers.get("Content-Type"), "text": r.text[:200]}
            except Exception as err:  # noqa: BLE001
                out[label] = {"error": f"{type(err).__name__}: {err}"}

        _try("bytes_hdr", headers={"File-Path": hdr, "Content-Type": "application/octet-stream"}, data=payload)
        _try("bytes_noct", headers={"File-Path": hdr}, data=payload)
        _try("short_path", headers={"File-Path": quote("/quark/.mf_d2.bin", safe=""), "Content-Type": "application/octet-stream"}, data=payload)
        # 清理
        for p, name in ((os.path.dirname(path) or "/quark", os.path.basename(path)), ("/quark", ".mf_d2.bin")):
            try:
                self.remove(p, [name])
            except Exception:  # noqa: BLE001
                pass
        return out

    def debug_get(self, remote_path: str = "") -> Dict[str, Any]:
        """诊断：把 `/api/fs/get` 的原始响应打回来（定位 stat 为何返回 None）。"""
        out: Dict[str, Any] = {}
        path = str(remote_path or "/quark/movie")
        out["path"] = path
        for label, url, kw in (
            ("get", self._url("/api/fs/get"), {"json": {"path": path}}),
            ("list", self._url("/api/fs/list"), {"json": {"path": path, "page": 1, "per_page": 50, "refresh": True, "password": ""}}),
        ):
            try:
                r = self.session.post(url, timeout=60.0, **kw)
                out[label] = {"http": r.status_code, "ctype": r.headers.get("Content-Type"), "text": r.text[:400]}
            except Exception as err:  # noqa: BLE001
                out[label] = {"error": f"{type(err).__name__}: {err}"}
        try:
            out["stat"] = self.stat(path)
        except Exception as err:  # noqa: BLE001
            out["stat_error"] = f"{type(err).__name__}: {err}"
        return out

    def storages(self) -> List[dict]:
        """列出 OpenList 存储（含挂载点/驱动/状态），用于健康检查。

        注意：`/api/admin/*` 在某些情况下（如登录锁定）会返回 SPA HTML 而非 JSON，
        这里容错为「拿不到就返回空」，绝不因此阻断归档主流程（归档只用 `/api/fs/*`）。
        """
        try:
            d = self._post("/api/admin/storage/list")
        except Exception:  # noqa: BLE001
            return []
        return list((d or {}).get("content") or []) if isinstance(d, dict) else []

    def list_dir(self, path: str, refresh: bool = False, per_page: int = 200) -> List[dict]:
        """列目录（返回 content 数组）。"""
        out = self._post("/api/fs/list", {
            "path": path, "page": 1, "per_page": int(per_page),
            "refresh": bool(refresh), "password": "",
        })
        if not isinstance(out, dict):
            return []
        return list(out.get("content") or [])

    def stat(self, path: str, refresh: bool = True) -> Optional[dict]:
        """取单个条目元信息（不存在返回 None）。

        ★ 用「列父目录」实现，**不用 `/api/fs/get`**（2026-09-26 实测）：
        Quark 驱动下 `/api/fs/get` 对文件经常返回 `object not found`（缓存/实现问题，结果不可靠），
        而 `/api/fs/list` 一直稳定。归档的「是否已存在 / 大小校验 / strm 是否生成」都靠它。
        """
        p = str(path or "").rstrip("/")
        if not p or p == "/":
            return None
        parent = os.path.dirname(p) or "/"
        name = os.path.basename(p)
        try:
            items = self.list_dir(parent, refresh=refresh)
        except OpenListError as err:
            if "not found" in str(err).lower():
                return None
            raise
        for it in items:
            if str(it.get("name")) == name:
                return it
        return None

    def exists(self, path: str) -> bool:
        return self.stat(path) is not None

    def mkdir(self, path: str) -> None:
        self._post("/api/fs/mkdir", {"path": path})

    def ensure_dir(self, path: str) -> None:
        """逐级建目录（幂等：已存在则忽略）。"""
        parts = [p for p in str(path or "").strip("/").split("/") if p]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}"
            try:
                self.mkdir(cur)
            except OpenListError as err:
                msg = str(err).lower()
                if "exist" in msg or "file exists" in msg or "已经存在" in msg:
                    continue
                # 有些驱动建已存在目录会报别的错；用 stat 兜底确认
                if self.stat(cur):
                    continue
                raise

    def remove(self, parent: str, names: List[str]) -> None:
        self._post("/api/fs/remove", {"dir": parent, "names": list(names)})

    def put_file(
        self,
        remote_path: str,
        local_path: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        limit_bps: float = 0.0,
        timeout: float = 3600.0,
    ) -> int:
        """流式上传本地文件到 OpenList（返回字节数）。

        - 显式带 `Content-Length`（OpenList 需要），body 用生成器以便「限速 + 进度」。
        - `limit_bps`：字节/秒上限，0 = 不限。
        """
        size = os.path.getsize(local_path)
        headers = {
            "File-Path": quote(str(remote_path), safe=""),
            "Content-Type": "application/octet-stream",
        }

        # ★ 用「文件对象」而不是生成器（2026-09-26 实测教训）：
        #   生成器 + 显式 Content-Length 会让服务端判为非法请求 → 报 "header line too long"。
        #   交 requests 自行计算 Content-Length 即可（进度/限速用包一层 reader 实现）。
        body: Any = _ProgressReader(open(local_path, "rb"), size, progress_cb, limit_bps)
        try:
            r = self.session.put(
                self._url("/api/fs/put"), data=body, headers=headers, timeout=(15.0, timeout),
            )
        except Exception as err:  # noqa: BLE001
            raise OpenListError(f"上传失败：{err}") from err
        finally:
            try:
                body.close()
            except Exception:  # noqa: BLE001
                pass
        if r.status_code in (401, 403):
            raise OpenListError("上传鉴权失败（token 无效或无权限）")
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            raise OpenListError(f"上传响应异常（HTTP {r.status_code}）")
        if data.get("code") != 200:
            raise OpenListError(str(data.get("message") or "上传失败"))
        return size


class ArchiveEngine:
    """云盘归档引擎：扫描候选 → 上传 → 校验 → （可选）删本地。

    由插件实例驱动（需要 `_store.cloud`、`_log` 等）。
    """

    def __init__(self, plugin: Any, cfg: Optional[dict] = None):
        self.plugin = plugin
        self._cfg: Dict[str, Any] = dict(cfg or {})
        self._client: Optional[OpenListClient] = None
        self._lock = threading.RLock()
        self._last_plan: List[dict] = []
        self._last_report: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 配置 / 客户端
    # ------------------------------------------------------------------
    def set_cfg(self, cfg: dict) -> None:
        with self._lock:
            self._cfg = dict(cfg or {})
            # 地址/token 变了 → 重建客户端
            self._client = None

    @property
    def cfg(self) -> Dict[str, Any]:
        return dict(self._cfg or {})

    def client(self) -> OpenListClient:
        with self._lock:
            if self._client is None:
                self._client = OpenListClient(
                    self._cfg.get("url") or "",
                    self._cfg.get("token") or "",
                )
            return self._client

    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(f"[归档] {msg}", level)
        except Exception:  # noqa: BLE001
            pass

    def store(self):
        try:
            return self.plugin._store.cloud
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------
    def test(self) -> Dict[str, Any]:
        """连通性自检：列源挂载根 + 列 strm 挂载根（+ 尝试列出存储，失败不致命）。"""
        out: Dict[str, Any] = {"ok": False}
        src = str(self._cfg.get("source_mount") or "/quark")
        strm = str(self._cfg.get("strm_mount") or "/movie")
        try:
            out["storages"] = [
                {"mount_path": s.get("mount_path"), "driver": s.get("driver"),
                 "status": s.get("status"), "disabled": s.get("disabled")}
                for s in self.client().storages()
            ]
            out["source_items"] = len(self.client().list_dir(src, refresh=False))
            out["strm_items"] = len(self.client().list_dir(strm, refresh=False))
            out["ok"] = True
        except Exception as err:  # noqa: BLE001
            out["error"] = str(err)
        return out

    # ------------------------------------------------------------------
    # 候选扫描
    # ------------------------------------------------------------------
    def _exclude_paths(self) -> List[str]:
        raw = self._cfg.get("exclude_paths")
        if not isinstance(raw, (list, tuple)) or not raw:
            raw = DEFAULT_EXCLUDE_PATHS
        return [str(p).rstrip("/") for p in raw if str(p or "").strip()]

    def _is_excluded(self, path: str) -> bool:
        p = str(path or "")
        for pref in self._exclude_paths():
            if p == pref or p.startswith(pref + "/"):
                return True
        for part in p.split("/"):
            if part in DEFAULT_EXCLUDE_DIRS:
                return True
        return False

    def _library_roots(self) -> List[str]:
        roots = self._cfg.get("paths")
        if isinstance(roots, (list, tuple)) and roots:
            return [str(r).rstrip("/") or "/" for r in roots if str(r or "").strip()]
        base = str(self._cfg.get("library_root") or "/movie").rstrip("/") or "/movie"
        return [base]

    def candidates(self, limit: Optional[int] = None) -> List[dict]:
        """扫描库内可归档的媒体文件（只读，不动任何东西）。"""
        try:
            min_size = float(self._cfg.get("min_size_gb") or 0) * (1024 ** 3)
            max_size = float(self._cfg.get("max_size_gb") or 0) * (1024 ** 3)
            min_age_days = float(self._cfg.get("min_age_days") or 0)
        except (TypeError, ValueError):
            min_size, max_size, min_age_days = 0.0, 0.0, 0.0
        now = time.time()
        out: List[dict] = []
        st = self.store()
        for root in self._library_roots():
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS and not d.startswith(".")]
                if self._is_excluded(dirpath):
                    dirnames[:] = []
                    continue
                for fn in filenames:
                    if fn.startswith(".") or os.path.splitext(fn)[1].lower() not in VIDEO_EXTS:
                        continue
                    full = os.path.join(dirpath, fn)
                    if self._is_excluded(full):
                        continue
                    try:
                        stat = os.stat(full)
                    except OSError:
                        continue
                    size = int(stat.st_size)
                    if size <= 0:
                        continue
                    if min_size and size < min_size:
                        continue
                    if max_size and size > max_size:
                        continue
                    if min_age_days > 0 and (now - float(stat.st_mtime)) < min_age_days * 86400:
                        continue
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                    parts = rel.split("/")
                    category = parts[0] if len(parts) > 1 else ""
                    title_dir = parts[1] if len(parts) > 2 else ""
                    year = ""
                    m = _RE_YEAR.search(title_dir or "")
                    if m:
                        year = m.group(1)
                    item = {
                        "path": full,
                        "name": fn,
                        "rel": rel,
                        "size": size,
                        "size_gb": round(size / (1024 ** 3), 2),
                        "category": category,
                        "title": title_dir,
                        "year": year,
                        "mtime": float(stat.st_mtime),
                        "remote": self.remote_path(rel),
                        "status": "candidate",
                    }
                    if st is not None:
                        rec = st.get(full) or {}
                        if rec.get("status") in ("uploaded", "verified"):
                            item["status"] = "done"
                    out.append(item)
        out.sort(key=lambda x: x["size"], reverse=True)
        if limit:
            out = out[: max(1, int(limit))]
        return out

    def make_item(self, path: str) -> Optional[dict]:
        """由本地路径构造一个候选条目（用于单个文件上传）。"""
        path = str(path or "")
        if not path or not os.path.isfile(path):
            return None
        try:
            stat = os.stat(path)
        except OSError:
            return None
        root = (self._library_roots() or ["/movie"])[0]
        rel = os.path.relpath(path, root).replace(os.sep, "/") if path.startswith(root) else os.path.basename(path)
        parts = rel.split("/")
        title_dir = parts[1] if len(parts) > 2 else (parts[0] if len(parts) == 1 else "")
        m = _RE_YEAR.search(title_dir or "")
        return {
            "path": path,
            "name": os.path.basename(path),
            "rel": rel,
            "size": int(stat.st_size),
            "size_gb": round(stat.st_size / (1024 ** 3), 2),
            "category": parts[0] if len(parts) > 1 else "",
            "title": title_dir,
            "year": m.group(1) if m else "",
            "mtime": float(stat.st_mtime),
            "remote": self.remote_path(rel),
            "status": "candidate",
        }

    def remote_path(self, rel: str) -> str:
        """本地相对路径 → 远端路径（默认与库结构同构，strm 视图才能对齐）。"""
        tpl = str(self._cfg.get("target_template") or DEFAULT_TARGET_TEMPLATE)
        rel = str(rel or "").lstrip("/")
        try:
            return tpl.format(rel=rel, name=os.path.basename(rel))
        except Exception:  # noqa: BLE001
            return f"{str(self._cfg.get('source_mount') or '/quark').rstrip('/')}/movie/{rel}"

    def strm_path(self, rel: str) -> str:
        """对应的 strm 视图路径（OpenList Strm 驱动生成的 `<name>.strm`）。"""
        mount = str(self._cfg.get("strm_mount") or "/movie").rstrip("/")
        rel = str(rel or "").lstrip("/")
        base, _ = os.path.splitext(rel)
        return f"{mount}/{base}.strm"

    # ------------------------------------------------------------------
    # 计划 / 执行
    # ------------------------------------------------------------------
    def plan(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """生成归档计划（dry-run：仅读取远端做比对，不写）。"""
        items = self.candidates(limit=limit)
        try:
            cli = self.client()
        except Exception:  # noqa: BLE001
            cli = None
        for it in items:
            if it.get("status") == "done":
                continue
            if cli is not None:
                try:
                    r = cli.stat(it["remote"])
                    if r and int(r.get("size") or 0) == int(it["size"]):
                        it["status"] = "remote_exists"
                except Exception as err:  # noqa: BLE001
                    it["status"] = "remote_error"
                    it["reason"] = str(err)
        total = sum(int(i["size"]) for i in items if i.get("status") == "candidate")
        report = {
            "items": items,
            "stats": {
                "candidates": len(items),
                "pending": sum(1 for i in items if i.get("status") == "candidate"),
                "remote_exists": sum(1 for i in items if i.get("status") == "remote_exists"),
                "done": sum(1 for i in items if i.get("status") == "done"),
                "pending_gb": round(total / (1024 ** 3), 2),
            },
            "dry_run": True,
            "at": time.time(),
        }
        self._last_plan = items
        return report

    def _verify(self, item: dict, timeout: float = 60.0, skip_strm_wait: bool = False) -> Tuple[bool, str]:
        """校验上传结果。

        判定以**源侧**（`/quark`，我们唯一能写的存储）为准：文件存在 + 大小一致 = 成功。
        strm 视图（`/movie`）是 OpenList Strm 驱动的缓存视图，可能晚几分钟才刷新，
        **不能因为查不到 strm 就判上传失败**（否则会把已成功的上传误报为失败）。
        """
        cli = self.client()
        meta = cli.stat(item["remote"])
        if not meta:
            return False, "远端文件不存在"
        if int(meta.get("size") or 0) != int(item["size"]):
            return False, f"大小不一致：远端 {meta.get('size')} vs 本地 {item['size']}"
        if skip_strm_wait:
            return True, "已上传（源侧校验通过）"
        deadline = time.time() + max(0.0, timeout)
        sp = self.strm_path(item["rel"])
        while time.time() < deadline:
            try:
                if cli.stat(sp):
                    return True, "strm 已生成"
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
        return True, "已上传（源侧校验通过；strm 稍后自动出现）"

    def upload(self, item: dict, dry_run: bool = True) -> Dict[str, Any]:
        """上传单个候选并校验（默认 dry-run）。"""
        out = dict(item)
        out["ok"] = False
        if dry_run:
            out["status"] = "dry_run"
            out["message"] = "演练：未上传"
            return out
        st = self.store()
        try:
            cli = self.client()
            remote = item["remote"]
            # ★ 冲突守卫：远端已有同名文件时绝不上传（否则夸克会悄悄改名成 xxx(1)
            #   或覆盖掉别的文件）。同大小 = 已归档好；不同大小 = 报告并跳过。
            existing = None
            try:
                existing = cli.stat(remote)
            except Exception:  # noqa: BLE001
                existing = None
            if existing:
                rsize = int(existing.get("size") or 0)
                if rsize == int(item["size"]):
                    out.update({
                        "ok": True,
                        "status": "remote_exists",
                        "message": f"远端已有同大小文件（{rsize}），跳过上传",
                        "bytes": 0,
                        "duration": 0.0,
                        "speed_mbps": 0.0,
                        "strm": self.strm_path(item["rel"]),
                    })
                    if st is not None:
                        st.upsert(item["path"], status="uploaded", remote=remote,
                                  size=item["size"], rel=item["rel"], uploaded_at=time.time(),
                                  verified=True, error="")
                    self._log(f"跳过上传（远端已存在）{item['rel']}")
                    return out
                out.update({
                    "ok": False,
                    "status": "conflict",
                    "message": f"远端同名文件已存在但大小不同（远端 {rsize} vs 本地 {item['size']}），已跳过",
                    "bytes": 0,
                    "duration": 0.0,
                    "speed_mbps": 0.0,
                    "strm": self.strm_path(item["rel"]),
                })
                if st is not None:
                    st.upsert(item["path"], status="failed", remote=remote, size=item["size"],
                              rel=item["rel"], error=out["message"])
                self._log(f"冲突跳过 {item['rel']}：{out['message']}")
                return out
            parent = os.path.dirname(remote)
            if parent:
                cli.ensure_dir(parent)
            speed_limit = 0.0
            try:
                mbps = float(self._cfg.get("upload_limit_mbps") or 0)
                speed_limit = mbps * 1024 * 1024 / 8.0 if mbps > 0 else 0.0
            except (TypeError, ValueError):
                speed_limit = 0.0
            if st is not None:
                st.upsert(item["path"], status="uploading", remote=remote,
                          size=item["size"], rel=item["rel"])
            t0 = time.time()
            size = cli.put_file(remote, item["path"], limit_bps=speed_limit)
            dur = max(0.001, time.time() - t0)
            ok, msg = self._verify(item, timeout=30.0)
            out.update({
                "ok": bool(ok),
                "status": "uploaded" if ok else "verify_failed",
                "message": msg,
                "bytes": size,
                "duration": round(dur, 1),
                "speed_mbps": round(size / dur / 1024 / 1024, 2),
                "strm": self.strm_path(item["rel"]),
            })
            if st is not None:
                st.upsert(item["path"], status="uploaded" if ok else "failed",
                          remote=remote, size=item["size"], rel=item["rel"],
                          uploaded_at=time.time(), verified=bool(ok), error="" if ok else msg)
            self._log(f"上传完成 {item['rel']} → {remote}（{out.get('speed_mbps')} MB/s, {msg}）")
        except Exception as err:  # noqa: BLE001
            out.update({"status": "error", "message": str(err)})
            self._log(f"上传失败 {item.get('rel')}：{err}", "warning")
            if st is not None:
                try:
                    st.upsert(item["path"], status="failed", error=str(err))
                except Exception:  # noqa: BLE001
                    pass
        return out

    def delete_local(self, item: dict) -> bool:
        """删除本地实体文件（**危险操作**：调用方必须先确认）。

        仅删除单个文件；不做递归、不动目录。删前再次校验远端存在且大小一致。
        """
        try:
            ok, msg = self._verify(item, timeout=10)
            if not ok:
                self._log(f"拒绝删本地（校验未通过：{msg}）：{item.get('path')}", "warning")
                return False
            os.remove(item["path"])
            st = self.store()
            if st is not None:
                st.upsert(item["path"], status="archived", deleted_at=time.time())
            self._log(f"已删本地：{item['path']}")
            return True
        except Exception as err:  # noqa: BLE001
            self._log(f"删本地失败 {item.get('path')}：{err}", "warning")
            return False

    def run(
        self,
        limit: Optional[int] = None,
        dry_run: Optional[bool] = None,
        delete_local: Optional[bool] = None,
        progress: Optional[Callable[[dict], None]] = None,
    ) -> Dict[str, Any]:
        """跑一轮归档（默认按配置：dry-run 开、不删本地）。"""
        cfg = self.cfg
        dry = bool(cfg.get("dry_run", True)) if dry_run is None else bool(dry_run)
        dele = bool(cfg.get("delete_local", False)) if delete_local is None else bool(delete_local)
        self._log(f"开始归档（dry_run={dry} delete_local={dele}）")
        plan = self.plan(limit=limit)
        items = [i for i in plan["items"] if i.get("status") == "candidate"]
        results: List[dict] = []
        for it in items:
            if progress:
                try:
                    progress(it)
                except Exception:  # noqa: BLE001
                    pass
            res = self.upload(it, dry_run=dry)
            if not dry and res.get("ok") and dele:
                res["deleted"] = self.delete_local(it)
            results.append(res)
        stats = {
            "planned": len(plan["items"]),
            "uploaded": sum(1 for r in results if r.get("status") == "uploaded"),
            "skipped": sum(1 for r in results if r.get("status") == "remote_exists"),
            "conflict": sum(1 for r in results if r.get("status") == "conflict"),
            "failed": sum(1 for r in results if r.get("status") in ("error", "verify_failed")),
            "deleted": sum(1 for r in results if r.get("deleted")),
            "bytes": sum(int(r.get("bytes") or 0) for r in results),
            "dry_run": dry,
        }
        report = {"items": results, "stats": stats, "at": time.time()}
        self._last_report = report
        self._journal(report)
        self._log(f"归档结束：{stats}")
        return report

    def _journal(self, report: Dict[str, Any]) -> None:
        """写一条操作流水（全局归档：task_id 用固定占位）。"""
        try:
            from .persistence import OperationItem

            items = []
            for r in report.get("items") or []:
                items.append(OperationItem(
                    hash="",
                    title=str(r.get("name") or r.get("rel") or ""),
                    reason=str(r.get("message") or r.get("status") or ""),
                    size_gb=float(r.get("size_gb") or 0),
                    source="cloud",
                ))
            self.plugin._store.journal.record(task_id="__cloud__", kind="cloud", items=items)
        except Exception as err:  # noqa: BLE001
            self._log(f"写操作流水失败：{err}", "warning")

    def last_report(self) -> Dict[str, Any]:
        if self._last_report:
            return dict(self._last_report)
        try:
            data = self.plugin.get_data("cloud_report") or {}
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
        return {}

    def state(self) -> Dict[str, Any]:
        """给前端的归档状态快照（配置 + 最近计划/结果 + 已归档记录数）。"""
        st = self.store()
        records = st.list() if st is not None else []
        return {
            "cfg": self.cfg,
            "plan": self._last_plan,
            "report": self.last_report(),
            "records": records[:200],
            "record_count": len(records),
        }
