# -*- coding: utf-8 -*-
"""魔流 · deck —— 满魔套牌存档（表 ``mf_deck``，MODEL.md §5.2）。

一套牌 = 同 ``deck_id`` 的所有行；**单位是「种子」(hash)**（站内一资源一种子，
resource_id 只在「跨站找同资源」时用）。

生命周期：
  打磨期  表在动（换种增删行）→ :meth:`_deck_sync` 每轮把当前在岗套牌全量写回；
  满魔期  连续 N 轮套牌不变（= 无补种 / 无清理 / 无换种）→ 打 ``frozen`` 标（冻结）；
  复用期  开任务读表 → :meth:`_deck_apply` 把存档 hash 在本机同站种上重新纳管（零下载、零重排）。

``deck_id`` 约定：``d<site_id>-<task_type>`` —— 同站同类型共用一套牌（任务改名不影响）。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from .. import db as mfdb
from ..downloader_ops import QB_PAUSED_STATES
from ..persistence import OperationItem
from ..tags import STATE_BONUS, STATE_BRUSH

from app.schemas import Response


class DeckMixin:
    """满魔套牌（``mf_deck``）读写与生命周期。"""

    _DECK_STUCK_ROUNDS = 3   # 连续 N 轮套牌不变 → 冻存（满魔）

    # ------------------------------------------------------------------ 基础

    def _deck_id(self, task: Any) -> str:
        """套牌标识：同站同类型共用一套牌（任务改名不影响）。"""
        sid = int(getattr(task, "site_id", 0) or 0)
        tt = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() or "bonus"
        return f"d{sid}-{tt}"

    def _deck_session(self):
        return self.get_database().session()

    def _deck_rows(
        self,
        *,
        deck_id: str = "",
        site_id: Optional[int] = None,
        task_type: str = "",
        frozen: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """读套牌行（不传 ``deck_id`` 则按 site / task_type 过滤；全空 = 全部）。"""
        out: List[Dict[str, Any]] = []
        try:
            with self._deck_session() as sess:
                stmt = select(mfdb.DeckRow)
                if deck_id:
                    stmt = stmt.where(mfdb.DeckRow.deck_id == str(deck_id))
                if site_id is not None:
                    stmt = stmt.where(mfdb.DeckRow.site_id == int(site_id))
                if task_type:
                    stmt = stmt.where(mfdb.DeckRow.task_type_id == str(task_type))
                if frozen is not None:
                    stmt = stmt.where(mfdb.DeckRow.frozen == bool(frozen))
                for r in sess.execute(stmt).scalars().all():
                    out.append({
                        "deck_id": r.deck_id,
                        "seed_id": str(r.seed_id or ""),
                        "site_id": r.site_id,
                        "task_type_id": r.task_type_id,
                        "task_id": r.task_id,
                        "a_contrib": float(r.a_contrib or 0.0),
                        "size_gb": float(r.size_gb or 0.0),
                        "frozen": bool(r.frozen),
                        "frozen_at": float(r.frozen_at or 0.0),
                        "created": float(r.created or 0.0),
                        "updated": float(r.updated or 0.0),
                    })
        except Exception as e:  # noqa: BLE001
            self._log(f"魔流 套牌读取失败: {e}", "warning")
        return out

    def _deck_save(
        self, task: Any, entries: List[Dict[str, Any]], *, frozen: bool = False
    ) -> Dict[str, int]:
        """全量替换该套牌的行（打磨期增删 / 满魔期冻结都走这里）。

        ``entries``：``[{"hash": h, "a": 贡献A, "size_gb": 体积}]``。
        """
        deck_id = self._deck_id(task)
        now = time.time()
        keep = {str(e.get("hash") or "").lower() for e in entries if e.get("hash")}
        old: set = set()
        added = removed = 0
        try:
            with self._deck_session() as sess:
                old = {
                    str(r.seed_id or "")
                    for r in sess.execute(
                        select(mfdb.DeckRow).where(mfdb.DeckRow.deck_id == deck_id)
                    ).scalars().all()
                }
                for e in entries:
                    h = str(e.get("hash") or "").lower()
                    if not h:
                        continue
                    sess.merge(mfdb.DeckRow(
                        deck_id=deck_id,
                        seed_id=h,
                        site_id=int(getattr(task, "site_id", 0) or 0) or None,
                        task_type_id=str(getattr(task, "task_type", "") or "") or None,
                        task_id=str(getattr(task, "id", "") or "") or None,
                        a_contrib=float(e.get("a") or 0.0),
                        size_gb=float(e.get("size_gb") or 0.0),
                        frozen=bool(frozen),
                        frozen_at=(now if frozen else None),
                        created=now,
                        updated=now,
                    ))
                gone = old - keep
                if gone:
                    sess.execute(
                        delete(mfdb.DeckRow).where(
                            mfdb.DeckRow.deck_id == deck_id,
                            mfdb.DeckRow.seed_id.in_(list(gone)),
                        )
                    )
                sess.commit()
            added = len(keep - old)
            removed = len(gone)
        except Exception as e:  # noqa: BLE001
            self._log(f"魔流 套牌落盘失败: {e}", "warning")
            return {"deck_id": deck_id, "total": 0, "added": 0, "removed": 0, "error": str(e)}
        return {"deck_id": deck_id, "total": len(keep), "added": added, "removed": removed,
                "frozen": bool(frozen)}

    def _deck_delete(self, deck_id: str) -> Dict[str, int]:
        n = 0
        try:
            with self._deck_session() as sess:
                res = sess.execute(delete(mfdb.DeckRow).where(mfdb.DeckRow.deck_id == str(deck_id)))
                sess.commit()
                n = int(getattr(res, "rowcount", 0) or 0)
        except Exception as e:  # noqa: BLE001
            self._log(f"魔流 套牌删除失败: {e}", "warning")
        return {"deck_id": deck_id, "deleted": n}

    # -------------------------------------------------------------- 在岗套牌

    def _deck_active(self, task: Any) -> List[Any]:
        """当前「在岗」的种（同站 × 职务，且真正在做种、不是暂停/未下完）。"""
        try:
            managed = self._task_managed_torrents(task)
        except Exception:  # noqa: BLE001
            return []
        out: List[Any] = []
        for t in managed or []:
            h = str(getattr(t, "hash", "") or "").lower()
            if not h:
                continue
            try:
                if str(getattr(t, "state", "") or "").lower() in QB_PAUSED_STATES:
                    continue
                if float(getattr(t, "progress", 1.0) or 0.0) < 0.999:
                    continue
            except Exception:  # noqa: BLE001
                pass
            out.append(t)
        return out

    def _deck_sync(self, task: Any) -> Dict[str, Any]:
        """打磨/满魔判定：套牌变过 → 更新存档；连续 N 轮不变 → 冻结（满魔）。"""
        act = self._deck_active(task)
        hashes = frozenset(str(getattr(t, "hash", "") or "").lower() for t in act)
        if not hashes:
            return {"skipped": "无在岗种"}
        bag = getattr(self, "_deck_seen", None)
        if bag is None:
            bag = self._deck_seen = {}
        key = self._deck_id(task)
        prev, stuck = bag.get(key, (None, 0))
        stuck = (stuck + 1) if hashes == prev else 0
        bag[key] = (hashes, stuck)
        entries = [
            {
                "hash": str(getattr(t, "hash", "") or "").lower(),
                "a": float(getattr(t, "bonus_score", 0.0) or 0.0),
                "size_gb": float(getattr(t, "size_gb", 0) or 0.0),
            }
            for t in act
        ]
        frozen = stuck >= int(self._DECK_STUCK_ROUNDS)
        out = self._deck_save(task, entries, frozen=frozen)
        out["stuck"] = stuck
        out["frozen"] = bool(frozen)
        if out.get("added") or out.get("removed") or frozen:
            self._log(
                f"魔流 [{task.name}] 套牌 {out['deck_id']}：{out['total']} 张"
                f"（+{out.get('added', 0)} / −{out.get('removed', 0)}）"
                + ("　★ 满魔冻结" if frozen else "")
            )
        return out

    # -------------------------------------------------------------- 复用期

    def _deck_apply(self, task: Any, *, apply: bool = True) -> Dict[str, Any]:
        """复用期：把存档套牌里「本机仍在做种」的 hash 重新纳管（标职务，零下载）。"""
        deck_id = self._deck_id(task)
        rows = self._deck_rows(deck_id=deck_id)
        if not rows:
            return {"ok": False, "reason": "该站该类型还没有套牌存档", "deck_id": deck_id}
        want = {r["seed_id"] for r in rows if r.get("seed_id")}
        present = self._tag_all_torrents() or {}
        live = [h for h in want if str(h).lower() in present]
        try:
            on_duty = {
                str(getattr(t, "hash", "") or "").lower()
                for t in (self._task_managed_torrents(task) or [])
            }
        except Exception:  # noqa: BLE001
            on_duty = set()
        todo = [h for h in live if h not in on_duty]
        tt = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower()
        state = STATE_BRUSH if tt == "brush" else STATE_BONUS
        site = str(getattr(task, "site_name", "") or getattr(task, "site_domain", "") or "")
        adopted = 0
        if apply and self._store:
            for h in todo:
                try:
                    ok, _why = self._store.claim(h, task.id, state=state, site=site)
                    if ok:
                        adopted += 1
                except Exception:  # noqa: BLE001
                    pass
            if adopted:
                try:
                    self._store.journal.record(
                        task_id=task.id, kind="tag",
                        items=[OperationItem(
                            hash="", title=f"套牌复用：纳管 {adopted} 个",
                            reason=f"读存档 {deck_id}", source="deck",
                        )],
                    )
                except Exception:  # noqa: BLE001
                    pass
        return {
            "ok": True, "deck_id": deck_id, "archived": len(want), "live": len(live),
            "on_duty": len(on_duty), "todo": len(todo), "adopted": adopted,
            "frozen": bool(rows[0].get("frozen")),
        }

    # -------------------------------------------------------------- 观测

    def _deck_info(self, site_id: Optional[int] = None) -> Dict[str, Any]:
        """给 API / 前端：按套牌汇总。"""
        rows = self._deck_rows(site_id=site_id)
        decks: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            d = decks.setdefault(r["deck_id"], {
                "deck_id": r["deck_id"], "site_id": r["site_id"],
                "task_type_id": r["task_type_id"], "task_id": r["task_id"],
                "frozen": bool(r["frozen"]), "frozen_at": float(r["frozen_at"] or 0.0),
                "updated": float(r["updated"] or 0.0), "count": 0, "size_gb": 0.0,
            })
            d["count"] = int(d["count"]) + 1
            d["size_gb"] = round(float(d["size_gb"]) + float(r["size_gb"] or 0.0), 2)
            d["updated"] = max(float(d["updated"] or 0.0), float(r["updated"] or 0.0))
            d["frozen"] = bool(d["frozen"]) and bool(r["frozen"])
        return {
            "total": len(rows),
            "decks": sorted(decks.values(), key=lambda x: str(x["deck_id"])),
        }

    # -------------------------------------------------------------- API 端点

    def deck_info(self, site_id: Optional[int] = None) -> Any:
        """GET /deck：满魔套牌存档（按 site_id 可过滤）。"""
        try:
            return Response(success=True, data=self._deck_info(site_id))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"读取套牌失败: {e}")

    def deck_sync(self, task_id: str = "") -> Any:
        """POST /deck/sync：把某任务当前在岗套牌写回存档（不传 task_id = 全部 bonus 任务）。"""
        rows = []
        try:
            if task_id:
                task = self._get_task_config(task_id)
                rows.append(self._deck_sync(task) if task else {"error": "任务不存在"})
            else:
                for t in list(self._task_configs.values()):
                    if str(getattr(t, "task_type", "") or "").strip().lower() == "bonus":
                        rows.append(self._deck_sync(t))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"套牌同步失败: {e}")
        return Response(success=True, message=f"已同步 {len(rows)} 个任务", data={"rows": rows})

    def deck_apply(self, task_id: str, apply: bool = True) -> Any:
        """POST /deck/apply：复用期——按存档把本机在种的牌重新纳管（零下载）。"""
        task = self._get_task_config(task_id or "")
        if not task:
            return Response(success=False, message="任务不存在")
        try:
            return Response(success=True, data=self._deck_apply(task, apply=bool(apply)))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"套牌复用失败: {e}")

    def deck_delete(self, deck_id: str) -> Any:
        """POST /deck/delete：删掉一套牌存档。"""
        if not deck_id:
            return Response(success=False, message="缺少 deck_id")
        return Response(success=True, data=self._deck_delete(deck_id))
