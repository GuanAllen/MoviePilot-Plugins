# -*- coding: utf-8 -*-
"""魔流 · transfer —— **整理执行的公共层**（影视 / 音乐 / 库内资产整理共用一个执行体）。

★ 19.12.95（Master 2026-11-20：「我觉得整理这块是不是要改成一个公共层」）

为什么要有这一层
----------------
「调 MP 整理」这件事原来有两份实现，各自长起来，于是同一类坑被各踩一遍：

* ``features/recommend.py:_recommend_import``    —— 推荐确认 / 点播 / 库内资产整理（影视）
* ``features/musicgrab.py:_music_transfer_now``  —— 音乐下载线 / 库内资产整理（音乐）

三次实证，都是「同一个参数两边只有一边记得传」：

1. ``transfer_type`` 漏传（19.12.94）：MP 在 ``None`` 时一路落到 ``checkpoint.py``
   的 ``... or "copy"``，音乐入库一直在**复制** —— 实测 521 个独立副本 / 18.87 GB。
2. ``skip_success`` 与 ``reorganize`` 互斥（19.12.93）：MP 里前者优先，同时传等于
   没重整；而「落点丢失」恰恰是「记录在、文件没了」，不清记录永远补不回来。
3. ``_transfer_already_done`` 把「重建失败」兜成假成功（19.12.93 音乐侧发现）：
   redo 模式下若还回「已整理过」，说明重整没生效，此时兜成成功只是把问题藏起来。

两边各记一遍参数语义，第三处调用（库内资产整理）一出现就必然写错 —— 这就是抽
公共层的理由，不是为了少写几行。

抽什么、不抽什么
----------------
**只抽「执行」**：把参数拼成 MP ``TransferChain().manual_transfer(**kwargs)``、
调用、把异常折成 ``(False, msg)``、判「已整理过」。

**不抽**三件事 —— 它们各自带业务语义，混进来只会让公共层变成第二个大杂烩：

* 身份获取：影视 ``recognize(title)`` / 点播下载期 ``media_hint`` / 音乐交给 MP
  按音频标签自己认。三种来源、三种失败口径，不该在底层纠缠。
* 台账与状态：入库账本、qB 标签、``taken_by``、库记、元数据兜底。``_asset_organize``
  对外承诺「只整理代表种，其余成员状态一律不改」，靠的就是这些留在上层。
* 播报：每个调用方的日志口径不同（推荐记「推荐整理」、音乐记「MP 整理」）。

三个参数维度都对应真实场景，不是预留
------------------------------------
``kind``
    ``"video"`` → ``mtype`` 由 ``identity`` 给，无 ``music_type``
    ``"music"`` → ``mtype=MediaType.MUSIC`` + ``music_type="album"``，忽略 ``identity``

``target``
    ``""``       → 不传，吃 MP 系统默认（推荐 / 点播的既有行为，本次不动）
    ``"link"``   → 显式锁硬链接。**库内资产整理与音乐线必须传**：一份资源常是
                   十余颗种共用同一个 ``content_path``，系统默认若被改回 move 会
                   搬走源文件、整组坏种；音乐库与下载区同文件系统，link 零额外占用。

``mode``
    ``"default"`` → 什么都不传（推荐 / 点播的既有行为）
    ``"fresh"``   → ``skip_success=True``：MP 侧已整理过的直接跳过，省一次重跑
    ``"redo"``    → ``reorganize=True``：**清掉旧成功记录再整**，落点丢失的唯一解
"""

import os
import re
from typing import Any, Dict, Optional, Tuple


TRANSFER_KINDS = ("video", "music")
TRANSFER_MODES = ("default", "fresh", "redo")
_TRANSFER_TARGETS = ("", "link", "copy", "move")


class TransferMixin:
    """整理执行公共层（影视 / 音乐 / 库内资产整理共用）。"""

    @staticmethod
    def _transfer_already_done(msg: Any) -> bool:
        """★ 识别「MP 整理返回的错误其实只是『已整理过』」。

        MP 的 ``TransferChain.manual_transfer`` 对**已经整理过**的文件返回
        ``ok=False`` + ``msg="<文件> 已整理过（成功记录 #N…）、…，等N个文件错误！"``，
        但文件其实早在库里（硬链接都在）→ 应当视作**成功**。

        规则：消息里出现「已整理过」，且拆开后**没有**其它实质错误（忽略
        「等N个文件错误！」这种汇总）。

        注意这是**判据**不是**决定**：``redo`` 模式下即使判出「已整理过」也不该当
        成功（那说明重整没生效），这个取舍在 ``_transfer_execute`` 里做。
        """
        s = str(msg or "").strip()
        if not s or "已整理过" not in s:
            return False
        for _p in re.split(r"[、,，;；]", s):
            _p = _p.strip()
            if not _p or "已整理过" in _p:
                continue
            if re.fullmatch(r"等\s*\d+\s*个文件错误[!！]?", _p):
                continue
            return False
        return True

    def _transfer_execute(self, seed_hash: str, *, path: str,
                          identity: Optional[Dict[str, Any]] = None,
                          kind: str = "video", target: str = "",
                          mode: str = "default") -> Tuple[bool, str, bool]:
        """**调一次 MP 整理**，返回 ``(ok, msg, already_done)``。

        ``seed_hash``
            种子 hash（大小写不敏感，内部转小写）。MP 靠它回写整理历史、广播
            ``TransferComplete``，传错就只是白整一遍。

        ``path``
            **已映射成 MP（容器内）可访问**的源路径。宿主机路径要先过
            ``downloader.normalize_path()`` —— 这不是本层的事，传进来的必需是对的值。

        ``identity``
            ``{media_id, media_source, media_type}``，影视专用。``media_type`` 必须是
            ``MediaType`` **成员**（普通 Enum，值就是中文）：直接传 ``"电视剧"`` 字符串
            会让 MP 内部判等失败，剧集被当电影建目录。

        ``kind`` / ``target`` / ``mode``
            见模块 docstring 的三维表。``mode="redo"`` 时**不兜**「已整理过」。

        返回的 ``already_done`` 告诉调用方「这个成功是靠兜底判出来的」—— MP 对
        「已整理过」不广播 ``TransferComplete``，需要补库记的调用方（推荐线）得知道。
        """
        key = str(seed_hash or "").strip().lower()
        src = str(path or "").strip().rstrip("/")
        _kind = str(kind or "video").strip().lower()
        _mode = str(mode or "default").strip().lower()
        _target = str(target or "").strip().lower()
        if not key:
            return False, "缺少 hash", False
        if not src:
            return False, "缺少整理路径", False
        if _kind not in TRANSFER_KINDS:
            return False, "不认识的整理类型:%s" % kind, False
        if _mode not in TRANSFER_MODES:
            return False, "不认识的整理模式:%s" % mode, False
        if _target not in _TRANSFER_TARGETS:
            return False, "不认识的整理方式:%s" % target, False

        try:
            from app.chain.transfer import TransferChain  # noqa: WPS433
            from app.schemas.file import FileItem  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return False, "MoviePilot 整理接口不可用:%s" % err, False

        try:
            is_dir = os.path.isdir(src)
        except OSError:
            is_dir = False
        fileitem = FileItem(
            path=src, storage="local", type="dir" if is_dir else "file",
            name=os.path.basename(src) or os.path.basename(src + "/"),
        )

        kwargs: Dict[str, Any] = {
            "fileitem": fileitem,
            "downloader": "qbittorrent",
            "download_hash": key,
        }
        if _kind == "music":
            try:
                from app.schemas.types import MediaType  # noqa: WPS433
            except Exception as err:  # noqa: BLE001
                return False, "MoviePilot 媒体类型不可用:%s" % err, False
            # 音乐没有 TMDB 身份，交给 MP 按音频标签自己认；``album`` 让它按整张建目录
            kwargs["mtype"] = MediaType.MUSIC
            kwargs["music_type"] = "album"
        else:
            _id = identity or {}
            # 三个都照传（含 None）—— 与改造前的调用完全一致，MP 自己会退化到按名称识别
            kwargs["media_source"] = _id.get("media_source")
            kwargs["media_id"] = _id.get("media_id")
            kwargs["mtype"] = _id.get("media_type")
        if _target:
            # 空串 = 不传 = 吃 MP 系统默认（推荐 / 点播的历史行为，别顺手改成 link）
            kwargs["transfer_type"] = _target
        if _mode == "fresh":
            kwargs["skip_success"] = True
        elif _mode == "redo":
            # 注意：MP 里 skip_success **优先于** reorganize，同时传等于没重整
            kwargs["reorganize"] = True

        try:
            ok, msg = TransferChain().manual_transfer(**kwargs)
        except Exception as err:  # noqa: BLE001
            return False, "整理异常:%s" % err, False

        msg = str(msg or "")
        if ok or _mode == "redo" or not self._transfer_already_done(msg):
            return bool(ok), msg, False
        # 「已整理过」在 MP 里走的是**错误**返回，但文件早在库 → 等价成功。
        # redo 模式例外：那时本来就是「记录在、落点没了」，再回「已整理过」说明
        # 重整没生效，兜成成功只会把「落点还是没回来」藏起来（19.12.93 实证）。
        return True, msg, True
