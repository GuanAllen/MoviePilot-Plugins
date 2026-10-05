# -*- coding: utf-8 -*-
"""魔流 · protection —— 保护裁决（唯一判定『这个种能不能动』）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


from ..downloader_ops import (
    TorrentInfo,
)


class ProtectionMixin:
    """protection 功能集（原 MagicFlow 方法原样搬入）。"""

    def _protection_sets(
        self,
        task: Any,
        bonus_list: Optional[List[Any]] = None,
        managed: Optional[List[Any]] = None,
        snap: Any = None,
    ) -> Dict[str, Any]:
        """★ 保护裁决的**唯一真值源**（docs/MODULES.md X3）：判定哪些种「不能动」。

        - ``hard``（永不删、永不换出）：手动保留 / 跨站来源份（H&R 保种期内）/ 欠 H&R / 未下完
        - ``soft``（可换出但不可删）：库内资产（已整理 / 下载历史命中）/ 同站纳管的自有种
          —— 换出只是「暂停做种、不删种」，不具破坏性，故不列入硬保护。
        - ``incomplete``（★ 8.0.2）：**仅因「未下完」**而进 ``hard`` 的子集。单独给出，是为了让
          「促销失效且未下完 → 删」那条清理能**只剔除这一条理由**放行：促销一结束还没下完的种
          本来就该清（否则白拉流量）；而手动保留 / 跨站 / 欠 H&R / 库内资产照旧硬拦。

        消费方（清理 / 换种 / 站点监控 / 静默池）**只读**本函数结果，不得自行增删保护集合；
        要新增一类保护 → 只改这里。返回 ``{"hard": set, "soft": set, "why": {hash: 理由},
        "incomplete": set}``。
        """
        hard: set = set()
        soft: set = set()
        why: Dict[str, str] = {}
        adopted: set = set()
        incomplete: set = set()   # ★ 8.0.2：单独记「仅因未下完」→ 供促销清理放行
        if self._store:
            try:
                hard |= set(self._store.get_protected_torrents(getattr(task, "id", "")) or set())
            except Exception:  # noqa: BLE001
                pass
            try:
                adopted |= set(self._store.get_adopted(getattr(task, "id", "")) or set())
            except Exception:  # noqa: BLE001
                pass
        for h in hard:
            why.setdefault(h, "手动保留")
        # 同站纳管（adopted）当初为「不删种」而记入保留集合；换出只是暂停做种，
        # 不具破坏性 → 从硬保护里剥离，归入软保护。
        hard -= adopted
        for h in adopted:
            if h:
                why.pop(h, None)
                why.setdefault(h, "同站纳管自有种")
        soft |= adopted
        try:
            _assets = set(self._media_asset_hashes(list(managed or []), task) or set())
        except Exception:  # noqa: BLE001
            _assets = set()
        for h in _assets:
            why.setdefault(h, "库内资产（已整理/下载历史）")
        soft |= _assets
        try:
            _cs = set(self._crossseed_source_hashes() or set())
        except Exception:  # noqa: BLE001
            _cs = set()
        for h in _cs:
            why.setdefault(h, "跨站来源份（H&R 保种期）")
        hard |= _cs
        # ★ 认领（claim）= 保种承诺：已认领的种进硬保护、永不删
        #   （否则「认领了又被自己删掉 → 站点判不达标 → 扣魔力」，7.14.0）
        try:
            _claim = set(self._claim_protected_hashes(getattr(task, "site_id", None)) or set())
        except Exception:  # noqa: BLE001
            _claim = set()
        for h in _claim:
            why.setdefault(h, "已认领（保种承诺）")
        hard |= _claim
        # 未下完 → 硬保护（用 TorrentInfo，才有真实的 progress/state）
        for t in (managed or []):
            _h = (getattr(t, "hash", "") or "").lower()
            if not _h:
                continue
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except Exception:  # noqa: BLE001
                prog = 1.0
            if prog < 0.999:
                hard.add(_h)
                incomplete.add(_h)
                why.setdefault(_h, "尚未下载完成")
        site_name = getattr(task, "site_name", "") or getattr(task, "site_domain", "")
        for b in (bonus_list or []):
            _h = getattr(b, "hash", "") or ""
            if not _h:
                continue
            try:
                owed, _hh, _sh, _src = self._hr_obligation(site_name, b, snap=snap)
            except Exception:  # noqa: BLE001
                owed = False
            if owed:
                hard.add(_h)
                why.setdefault(_h, "欠 H&R 义务")
        for h in hard:
            why.setdefault(h, "硬保护")
        return {"hard": hard, "soft": soft, "why": why, "incomplete": incomplete}
