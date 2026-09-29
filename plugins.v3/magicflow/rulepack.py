"""类型规则包加载器（YAML 数据驱动）★ 3.40.0

**规则数据在 ``conf/frameworks.yml``，解析引擎在代码里。**
加一个站点类型 = 改 YAML（不改代码）；YAML 读不到时，调用方各自保留的默认值兜底，
所以「读不到规则包」永远不会让插件起不来。

对外只有几件事：
    · :func:`load_pack` / :func:`reload_pack` —— 读（带缓存）/ 重读
    · :func:`framework_cfg` —— 某个框架的完整配置（含 defaults 合并）
    · :func:`framework_names` —— 有哪些框架
    · :func:`builtin_domains` —— 已知域名 → 框架
    · :func:`markers` —— 框架识别用的特征串（顺序敏感：先匹配到的赢）
    · :func:`rx` —— 按 key 取编译好的正则（带缓存）
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, Any]] = None
_RX_CACHE: Dict[str, Any] = {}

PACK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "conf", "frameworks.yml"
)


def load_pack(force: bool = False) -> Dict[str, Any]:
    """读规则包（进程内缓存；``force=True`` 重读文件）。"""
    global _CACHE
    with _LOCK:
        if _CACHE is not None and not force:
            return _CACHE
        data: Dict[str, Any] = {}
        try:
            import yaml  # MoviePilot 环境自带；离线单测可能没有

            with open(PACK_PATH, encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                data = loaded
        except Exception:  # noqa: BLE001
            data = {}
        _CACHE = data
        _RX_CACHE.clear()
        return _CACHE


def reload_pack() -> Dict[str, Any]:
    """强制重读（改完 YAML 调一次，不用重启插件）。"""
    return load_pack(force=True)


def pack_ok() -> bool:
    """规则包是否真的读到了（``False`` = 全是代码默认值兜底）。"""
    return bool(load_pack().get("frameworks"))


def framework_names() -> List[str]:
    fw = load_pack().get("frameworks") or {}
    return [str(k) for k in fw] if isinstance(fw, dict) else []


def framework_cfg(framework: str) -> Dict[str, Any]:
    """某框架的配置（未知/未列出 → ``unknown`` 档，再不行 → 空 dict）。"""
    pack = load_pack()
    fws = pack.get("frameworks") or {}
    defaults = pack.get("defaults") or {}
    name = str(framework or "").strip().lower() or "unknown"
    cfg = dict(fws.get(name) or fws.get("unknown") or {})
    if not cfg:
        cfg = {}
    # defaults 只补缺（框架段优先）
    for key, val in (defaults or {}).items():
        cfg.setdefault(key, val)
    cfg["name"] = name
    return cfg


def framework_defaults(framework: str) -> Dict[str, Any]:
    """**阈值兜底**：一律是 ``None``（未知）；YAML 里若真写了值，也是站点级结论的下限。"""
    cfg = framework_cfg(framework)
    d = cfg.get("defaults") if isinstance(cfg.get("defaults"), dict) else {}
    out: Dict[str, Any] = {"hr": None, "seed_hours": None, "seed_need_hours": None, "seed_cap": None}
    out.update({k: (d or {}).get(k) for k in ("hr", "seed_hours", "seed_need_hours", "seed_cap")})
    return out


def framework_note(framework: str) -> str:
    cfg = framework_cfg(framework)
    return str(cfg.get("note") or "")


def framework_probe_paths(framework: str) -> Tuple[str, ...]:
    cfg = framework_cfg(framework)
    paths = cfg.get("probe_paths") or (load_pack().get("defaults") or {}).get("probe_paths")
    if not paths:
        paths = ("rules.php", "myhr.php")
    return tuple(str(p) for p in paths if str(p).strip())


def framework_parser_name(framework: str) -> str:
    cfg = framework_cfg(framework)
    return str(cfg.get("parser") or "generic").strip().lower()


def tokens(framework: str, kind: str) -> List[str]:
    """取某框架某类正则片段（``hr``/``seed``/``need``/``exclude``/``permit_withdraw``）。"""
    cfg = framework_cfg(framework)
    tk = cfg.get("tokens") if isinstance(cfg.get("tokens"), dict) else {}
    vals = (tk or {}).get(kind) or []
    return [str(v) for v in vals if str(v).strip()]


def cap_reject(framework: str) -> List[str]:
    """上限解析要拒绝的上下文词（如「集」＝集数不是做种数）。"""
    return tokens(framework, "cap_reject")


def pattern(framework: str, key: str) -> Any:
    """取某框架的具名正则片段（字符串或字符串列表）。"""
    cfg = framework_cfg(framework)
    pats = cfg.get("patterns") if isinstance(cfg.get("patterns"), dict) else {}
    return (pats or {}).get(key)


def alternation(items: List[str], default: str = "") -> str:
    """把正则片段拼成 ``a|b|c``（空 → default）。"""
    vals = [str(i) for i in items if str(i).strip()]
    return "|".join(f"(?:{v})" for v in vals) if vals else default


def rx(key: str, pattern_text: str, flags: int = re.I) -> Any:
    """按 key 编译正则（带缓存，避免热路径重复编译）。"""
    ck = f"{key}|{flags}|{pattern_text}"
    got = _RX_CACHE.get(ck)
    if got is None:
        try:
            got = re.compile(pattern_text, flags)
        except re.error:
            got = re.compile(r"(?!x)x")  # 永不匹配，避免坏正则炸掉整条链
        _RX_CACHE[ck] = got
    return got


def builtin_domains() -> Dict[str, str]:
    """已知域名 → 框架。"""
    doms = load_pack().get("builtin_domains") or {}
    if not isinstance(doms, dict):
        return {}
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in doms.items() if str(v).strip()}


def capabilities(framework: str) -> Dict[str, Any]:
    """取某框架的能力表（free_index / free_spstates / free_url / page_param / promo_in_list）。"""
    cfg = framework_cfg(framework)
    caps = cfg.get("capabilities") if isinstance(cfg.get("capabilities"), dict) else {}
    out: Dict[str, Any] = {}
    if isinstance(caps, dict):
        out = dict(caps)
    if "free_spstates" in out and not isinstance(out["free_spstates"], (list, tuple)):
        out["free_spstates"] = ()
    return out


def builtin_capabilities() -> Dict[str, Dict[str, Any]]:
    """代码兜底能力表（YAML 读不到时 sitecap 用它；与 3.39.x 一致）。"""
    return {
        "nexusphp": {
            "free_index": True,
            "free_spstates": (2, 4),
            "free_url": "{base}/torrents.php?incldead=1&spstate={sp}&page={page}",
            "page_param": "works",
            "promo_in_list": True,
        },
        "gazelle": {"free_index": False, "free_spstates": (), "page_param": "unknown", "promo_in_list": False},
        "unit3d": {"free_index": False, "free_spstates": (), "page_param": "unknown", "promo_in_list": True},
        "mteam": {"free_index": False, "free_spstates": (), "page_param": "unknown", "promo_in_list": True},
        "custom": {"free_index": False, "free_spstates": (), "page_param": "unknown"},
        "unknown": {"free_index": False, "free_spstates": (), "page_param": "unknown"},
    }


def markers() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """框架识别特征（顺序敏感：先匹配到的赢），返回 ``((framework, (marker, ...)), ...)``。"""
    pack = load_pack()
    fws = pack.get("frameworks") or {}
    out: List[Tuple[str, Tuple[str, ...]]] = []
    if isinstance(fws, dict):
        for name, cfg in fws.items():
            if not isinstance(cfg, dict):
                continue
            mk = cfg.get("markers") or []
            vals = tuple(str(m).strip().lower() for m in mk if str(m).strip())
            if vals:
                out.append((str(name).strip().lower(), vals))
    return tuple(out)


def builtin_markers() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """代码兜底用的最小特征表（YAML 读不到时 sitecap 用它）。"""
    return (
        ("nexusphp", ("powered by nexusphp", "nexusphp", "spstate=", "downloadvolumefactor")),
        ("gazelle", ("powered by gazelle", "gazelle", "ajax.php?action=browse")),
        ("unit3d", ("unit3d", "powered by unit3d")),
        ("mteam", ("api.m-team", "m-team.cc", "mteam")),
    )


def api_channels() -> Dict[str, Any]:
    """★ 3.45.0 API 通道表（``api_channels`` 段），读不到返回 ``{}``。

    通道 = 「这个站怎么调后台 API」：根地址模板 / 认证头 / 成功判定 / 端点表。
    采集层只认这张表；代码里不许再写站点专属 URL 或认证头。
    """
    pack = load_pack()
    ch = pack.get("api_channels") or {}
    return ch if isinstance(ch, dict) else {}


def api_channels_fallback() -> Dict[str, Any]:
    """代码兜底的最小通道表（YAML 读不到时 collect 用它）。"""
    return {
        "mteam": {
            "markers": ["m-team", "mteam"],
            "base": "https://api.{domain}/api",
            "auth": {"header": "x-api-key", "field": "apikey", "prefix": ""},
            "envelope": {"ok_field": "code", "ok_value": "0", "err_field": "message"},
            "body": "json",
            "endpoints": {
                "profile": {"path": "/member/profile", "body": "json"},
                "search": {"path": "/torrent/search", "body": "json"},
                "detail": {"path": "/torrent/detail", "body": "form", "param": "id"},
                "dl": {"path": "/torrent/genDlToken", "body": "form", "param": "id"},
            },
        },
        "yemapt": {
            "markers": ["yemapt"],
            "base": "https://www.yemapt.org/openApi",
            "auth": {"header": "Authorization", "field": "apikey", "prefix": ""},
            "envelope": {"ok_field": "success", "ok_value": True, "err_field": "errorMessage"},
            "body": "json",
            "endpoints": {
                "profile": {"path": "/user/fetchBasicInfo.json", "body": "json"},
                "list": {"path": "/torrent/fetchOpenTorrentList.json", "body": "json"},
                "dl": {"path": "/torrent/generateDownloadKey.json", "body": "json", "param": "id"},
                "hash": {"path": "/torrent/fetchTorrentIdWithPiecesHash.json", "body": "json"},
            },
            "dl_url": "https://www.yemapt.org/api/torrent/download1?token={key}",
        },
    }


def builtin_domains_fallback() -> Dict[str, str]:
    """代码兜底的最小域名表（YAML 读不到时 sitecap 用它）。"""
    return {
        "hdfans.org": "nexusphp",
        "pttime.org": "nexusphp",
        "hdtime.org": "nexusphp",
        "cspt.top": "nexusphp",
        "m-team.cc": "mteam",
        "soulvoice.club": "custom",
    }
