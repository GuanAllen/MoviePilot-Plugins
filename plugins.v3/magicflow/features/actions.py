# -*- coding: utf-8 -*-
"""魔流 · actions —— 一次性人工动作（重挂/校验/改名/迁移等，均幂等）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime


from app.schemas import Response

from ..models import (
    MagicFlowTorrentBatchPayload,
)
from ..persistence import OperationItem


class ActionsMixin:
    """actions 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------
    # API:种子操作
    # ---------------------------------------------------------

    def protect_torrent(self, task_id: str, hash: str) -> Response:
        """手动保留种子。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        if self._store:
            self._store.protect_torrent(task_id, hash)
            self._store.journal.record(
                task_id=task_id,
                kind="protection",
                items=[OperationItem(hash=hash, title="", reason="手动保留")],
            )
        self._invalidate_summary()
        return Response(success=True, message="种子已保留")

    def unprotect_torrent(self, task_id: str, hash: str) -> Response:
        """取消保留种子。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        if self._store:
            self._store.unprotect_torrent(task_id, hash)
            self._store.journal.record(
                task_id=task_id,
                kind="unprotection",
                items=[OperationItem(hash=hash, title="", reason="取消保留")],
            )
        self._invalidate_summary()
        return Response(success=True, message="已取消保留")

    def manual_delete_torrent(self, task_id: str, hash: str) -> Response:
        """手动删除种子。

        ★ MODEL.md §3：**还在欠 H&R 的种不允许手动删**（保种义务未还清）。
        ★ MODEL.md §4：跨站来源份在 H&R 保种期内也拦。
        """
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        # ★ 手动删除前的保护闸门（欠 H&R / 跨站来源份保种期）
        try:
            _h = str(hash or "").strip().lower()
            if _h:
                _src = set()
                try:
                    _src = {str(x).lower() for x in (self._crossseed_source_hashes() or set())}
                except Exception:  # noqa: BLE001
                    _src = set()
                if _h in _src:
                    return Response(success=False,
                                    message="该种是跨站来源份（H&R 保种期内），不能手动删除")
                _t = (self._tag_all_torrents() or {}).get(_h)
                if _t is not None:
                    _rec = (self._tag_state().items() or {}).get(_h) or {}
                    _site = str(_rec.get("site") or "").strip()
                    if not _site:
                        _site = self._torrent_site_name(
                            [str(x) for x in (getattr(_t, "tags", None) or [])], "")
                    if _site:
                        _obl, _need, _seeded, _src2 = self._hr_obligation(_site, _t)
                        if _obl:
                            _left = max(0.0, float(_need or 0.0) - float(_seeded or 0.0))
                            return Response(success=False, message=(
                                f"该种还在欠 H&R（{_site} 还差约 {_left:.1f} 小时），不能手动删除；"
                                "确需强删请在下载器里直接删"))
        except Exception as _hr_err:  # noqa: BLE001
            self._log(f"手动删除前 H&R 校验失败:{_hr_err}", "warning")

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            success_count, error = downloader.delete_torrents(
                hashes=[hash],
                delete_file=task.delete_files,
            )
            if success_count > 0:
                self._note_deleted(task_id, [hash])
                if self._store:
                    self._store.journal.record(
                        task_id=task_id,
                        kind="deletion",
                        items=[OperationItem(hash=hash, title="", reason="手动删除")],
                    )
                self._invalidate_summary()
                return Response(success=True, message="种子已删除")

            return Response(success=False, message=error or "删除失败")

        except Exception as e:
            self._log(f"手动删除种子失败: {e}", "error")
            return Response(success=False, message=str(e))

    def _note_deleted(self, task_id: str, hashes) -> None:
        """★ 7.19.4：手动删除后记「dead」冷却 + 内存速查，避免下一轮刷流把同一颗又拉回来。

        背景：插件自己的清理（无进度/过慢/无上传）都会 `dead.mark`，但**手动删除**
        以前只 `forget_torrents`（忘账），导致同一候选下轮被重新挑中 → 「删了又回来」。
        """
        now = time.time()
        hs = [str(h).lower() for h in (hashes or []) if h]
        if not hs:
            return
        try:
            _mem = getattr(self, "_dead_hashes", None)
            if isinstance(_mem, dict):
                for h in hs:
                    _mem[h] = now
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._store:
                self._store.dead.mark(task_id, [f"hash:{h}" for h in hs], ts=now)
        except Exception as _e:  # noqa: BLE001
            self._log(f"手动删除后记 dead 失败:{_e}", "warning")

    def _control_torrent(self, task_id: str, hash: str, action: str) -> Response:
        """托管种子控制:暂停 / 恢复做种 / 强制校验。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        label = self._TORRENT_CONTROL_ACTIONS.get(action, (action, action))[0]
        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            func = {
                "pause": downloader.pause_torrents,
                "resume": downloader.resume_torrents,
                "recheck": downloader.recheck_torrents,
            }.get(action)
            if not func:
                return Response(success=False, message=f"不支持的操作:{action}")

            success_count, error = func([hash])
            if success_count <= 0:
                return Response(success=False, message=error or f"{label}失败")

            if self._store:
                # 手动暂停/恢复要落盘,避免「自动恢复暂停做种」把人工作废
                if action == "pause":
                    self._store.mark_manual_paused(task_id, [hash])
                elif action == "resume":
                    self._store.clear_manual_paused(task_id, [hash])
                self._store.journal.record(
                    task_id=task_id,
                    kind=action,
                    items=[OperationItem(hash=hash, title="", reason=f"手动{label}")],
                )
            self._invalidate_summary()
            return Response(success=True, message=f"已{label}")

        except Exception as e:
            self._log(f"种子操作({action})失败: {e}", "error")
            return Response(success=False, message=str(e))

    def pause_torrent(self, task_id: str, hash: str) -> Response:
        """暂停一个托管种子(并标记,防止被自动恢复)。"""
        return self._control_torrent(task_id, hash, "pause")

    def resume_torrent(self, task_id: str, hash: str) -> Response:
        """恢复做种。"""
        return self._control_torrent(task_id, hash, "resume")

    def recheck_torrent(self, task_id: str, hash: str) -> Response:
        """强制重新校验。"""
        return self._control_torrent(task_id, hash, "recheck")

    def batch_torrents(self, task_id: str, payload: MagicFlowTorrentBatchPayload) -> Response:
        """批量操作托管种子(保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除)。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        action = (payload.action or "").strip().lower()
        hashes = [h for h in (payload.hashes or []) if h]
        if not hashes:
            return Response(success=False, message="未选择种子")
        label = {
            "protect": "手动保留", "unprotect": "取消保留", "pause": "暂停种子",
            "resume": "恢复运行", "recheck": "强制校验", "delete": "批量删除",
        }.get(action, action)

        try:
            # 1 保护类:仅落盘,不碰下载器
            if action in ("protect", "unprotect"):
                if not self._store:
                    return Response(success=False, message="存储不可用")
                for h in hashes:
                    if action == "protect":
                        self._store.protect_torrent(task_id, h)
                    else:
                        self._store.unprotect_torrent(task_id, h)
                self._store.journal.record(
                    task_id=task_id,
                    kind="protection" if action == "protect" else "unprotection",
                    items=[OperationItem(hash=h, title="", reason=f"批量{label}") for h in hashes],
                )
                self._invalidate_summary()
                return Response(
                    success=True,
                    message=f"已批量{label} {len(hashes)} 个",
                    data={"success_count": len(hashes), "failed": 0, "total": len(hashes)},
                )

            # 2 下载器类
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            if action == "delete":
                ok, error = downloader.delete_torrents(hashes=hashes, delete_file=task.delete_files)
                done = hashes[:max(0, int(ok or 0))]
            else:
                func = {
                    "pause": downloader.pause_torrents,
                    "resume": downloader.resume_torrents,
                    "recheck": downloader.recheck_torrents,
                }.get(action)
                if not func:
                    return Response(success=False, message=f"不支持的操作:{action}")
                ok, error = func(hashes)
                done = hashes[:max(0, int(ok or 0))]

            if self._store and done:
                if action == "pause":
                    self._store.mark_manual_paused(task_id, done)
                elif action == "resume":
                    self._store.clear_manual_paused(task_id, done)
                if action == "delete":
                    self._store.forget_torrents(task_id, done)
            if action == "delete" and done:
                self._note_deleted(task_id, done)
                self._store.journal.record(
                    task_id=task_id,
                    kind=action,
                    items=[OperationItem(hash=h, title="", reason=f"批量{label}") for h in done],
                )
            self._invalidate_summary()

            if not done:
                return Response(success=False, message=error or f"{label}失败")
            msg = f"已批量{label} {len(done)} 个"
            if len(done) < len(hashes):
                msg += f"({len(hashes) - len(done)} 个失败)"
            return Response(
                success=True,
                message=msg,
                data={"success_count": len(done), "failed": len(hashes) - len(done), "total": len(hashes)},
            )

        except Exception as e:
            self._log(f"批量种子操作({action})失败: {e}", "error")
            return Response(success=False, message=str(e))
