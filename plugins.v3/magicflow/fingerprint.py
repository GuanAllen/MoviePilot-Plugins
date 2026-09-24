"""
MagicFlow 种子指纹模块

用于在本机已有资源与站点候选之间判定「同一份资源」，支撑辅种（存量复用）。

思路（参考 IYUU，但完全本地化、零云端依赖）：
- 一段种子的「文件列表」（相对路径 + 文件大小）规范化（排序）后取 SHA1 作为**特征码**；
- 不同站点、不同发布标题，只要文件列表一致 → 特征码一致 → 判为同一资源；
- 于是可以让候选种子直接指向本机已有文件做种（skip_checking / recheck），无需重新下载。

提供：
- ``bdecode`` / ``bencode``：极简 bencode 编解码（只需处理 .torrent）
- ``load_torrent_entries``：从 .torrent 原始字节提取文件列表
- ``fingerprint`` / ``inner_fingerprint``：完整特征码 / 去根目录特征码
- ``entries_fingerprint``：由下载器返回的文件列表计算特征码
- ``info_hash``：计算种子 info hash
"""

from __future__ import annotations

import gzip
import hashlib
import io
import zipfile
from typing import Any, Dict, List, Optional, Tuple

Entry = Tuple[str, int]  # (相对路径, 字节大小)

__all__ = [
    "bdecode",
    "bencode",
    "load_torrent_entries",
    "fingerprint",
    "inner_fingerprint",
    "entries_fingerprint",
    "info_hash",
    "total_size",
    "Entry",
]


# ============================================================
# bencode
# ============================================================

def _decode(data: bytes, pos: int) -> Tuple[Any, int]:
    if pos >= len(data):
        raise ValueError("bencode: 数据意外结束")
    ch = data[pos:pos + 1]
    if ch == b"i":
        end = data.index(b"e", pos)
        return int(data[pos + 1:end]), end + 1
    if ch == b"l":
        pos += 1
        items: List[Any] = []
        while data[pos:pos + 1] != b"e":
            value, pos = _decode(data, pos)
            items.append(value)
        return items, pos + 1
    if ch == b"d":
        pos += 1
        result: Dict[Any, Any] = {}
        while data[pos:pos + 1] != b"e":
            key, pos = _decode(data, pos)
            value, pos = _decode(data, pos)
            result[key] = value
        return result, pos + 1
    if ch.isdigit():
        colon = data.index(b":", pos)
        length = int(data[pos:colon])
        start = colon + 1
        return data[start:start + length], start + length
    raise ValueError(f"bencode: 非法字符 {ch!r} @ {pos}")


def bdecode(data: bytes) -> Any:
    """解析 bencode 数据。"""
    value, _ = _decode(data, 0)
    return value


def _bencode_sort_key(key: Any) -> bytes:
    if isinstance(key, bytes):
        return key
    return str(key).encode("utf-8")


def bencode(value: Any) -> bytes:
    """编码为 bencode（用于重算 info hash）。"""
    if isinstance(value, bool):
        return b"i1e" if value else b"i0e"
    if isinstance(value, int):
        return b"i%de" % value
    if isinstance(value, bytes):
        return b"%d:%s" % (len(value), value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"%d:%s" % (len(raw), raw)
    if isinstance(value, (list, tuple)):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        parts = [b"d"]
        for key in sorted(value.keys(), key=_bencode_sort_key):
            parts.append(bencode(key))
            parts.append(bencode(value[key]))
        parts.append(b"e")
        return b"".join(parts)
    raise TypeError(f"bencode: 不支持的类型 {type(value)!r}")


# ============================================================
# .torrent 解析
# ============================================================

def _maybe_decompress(raw: bytes) -> bytes:
    """部分站点返回 gzip / zip 包裹的种子文件。"""
    if not raw:
        return raw
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except Exception:
            return raw
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in archive.namelist():
                    if name.lower().endswith(".torrent"):
                        return archive.read(name)
        except Exception:
            return raw
    return raw


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    return ""


def _torrent_info(raw: bytes) -> Optional[Dict[Any, Any]]:
    try:
        meta = bdecode(_maybe_decompress(raw))
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    info = meta.get(b"info")
    return info if isinstance(info, dict) else None


def load_torrent_entries(raw: bytes) -> List[Entry]:
    """
    从 .torrent 原始字节提取「文件列表」。

    返回 [(相对路径, 大小)]，多文件种子路径含根目录名（与下载器
    ``torrents_files`` 返回的 name 对齐）。
    """
    info = _torrent_info(raw)
    if not info:
        return []

    root = _text(info.get(b"name")).strip("/")
    files = info.get(b"files")

    entries: List[Entry] = []
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get(b"path")
            length = item.get(b"length")
            if not isinstance(path, list) or length is None:
                continue
            parts = [_text(p) for p in path if isinstance(p, bytes)]
            rel = "/".join(part.strip("/") for part in parts).strip("/")
            if not rel:
                continue
            full = f"{root}/{rel}".strip("/") if root else rel
            entries.append((full, int(length)))
    else:
        length = info.get(b"length")
        if length is not None and root:
            entries.append((root, int(length)))
    return entries


def info_hash(raw: bytes) -> Optional[str]:
    """计算种子 info hash（十六进制小写）。"""
    info = _torrent_info(raw)
    if not info:
        return None
    try:
        return hashlib.sha1(bencode(info)).hexdigest()
    except Exception:
        return None


# ============================================================
# 特征码
# ============================================================

def _normalize(entries: List[Entry]) -> List[Entry]:
    norm = [((p or "").replace("\\", "/").strip("/"), int(s or 0)) for p, s in entries if p]
    norm.sort()
    return norm


def _hash_entries(entries: List[Entry]) -> Optional[str]:
    norm = _normalize(entries)
    if not norm:
        return None
    payload = "\n".join(f"{p}\t{s}" for p, s in norm)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _strip_root(entries: List[Entry]) -> List[Entry]:
    """若所有文件共用一个根目录，去掉这一层（用于跨站根目录名不同的情形）。"""
    norm = _normalize(entries)
    if not norm:
        return norm
    roots = {p.split("/", 1)[0] for p, _ in norm}
    if len(roots) != 1:
        return norm
    root = next(iter(roots))
    # 单文件种子（路径本身就是文件名）不算根目录
    if all(p == root for p, _ in norm):
        return norm
    stripped: List[Entry] = []
    for path, size in norm:
        parts = path.split("/", 1)
        rel = parts[1] if len(parts) > 1 else parts[0]
        stripped.append((rel, size))
    return stripped


def entries_fingerprint(entries: List[Entry]) -> Optional[str]:
    """由「文件列表」计算完整特征码（含根目录名）。"""
    return _hash_entries(entries)


def fingerprint(raw_or_entries: Any) -> Optional[str]:
    """完整特征码：接受 .torrent 字节或 [(path, size)]。"""
    entries = load_torrent_entries(raw_or_entries) if isinstance(raw_or_entries, (bytes, bytearray)) else raw_or_entries
    return _hash_entries(entries or [])


def inner_fingerprint(raw_or_entries: Any) -> Optional[str]:
    """去根目录特征码：忽略最外层目录名，只比内部结构。"""
    entries = load_torrent_entries(raw_or_entries) if isinstance(raw_or_entries, (bytes, bytearray)) else raw_or_entries
    return _hash_entries(_strip_root(entries or []))


def total_size(entries: List[Entry]) -> int:
    return sum(int(s or 0) for _, s in entries or [])
