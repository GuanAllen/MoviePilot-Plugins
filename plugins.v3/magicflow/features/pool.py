# -*- coding: utf-8 -*-
"""魔流 · pool —— 池盘空间（**一个目录 = 一个池**，绝不跨目录求和）。

为什么单开一个模块：MP 仪表板的「本地存储」是把**多个下载/媒体目录的容量加起来**的
（例如 /movie 7.25 TiB + /media 0.91 TiB = 8.16 TiB），拿它算「80% 阈值」是错的——
任务只能写在自己那个池里，用不到别的池的空间。

所以这里按 **目录→挂载卷** 逐个 statvfs：
  * 前端把任务的保存目录（qB 视角，如 ``/vol6/1000/movie/刷流``）传进来；
  * 这里用 MP 目录配置里的下载目录（容器视角，如 ``/movie``）按**路径名匹配**回池；
  * 返回该池的 总量/已用/剩余 + 「80% 阈值」下本任务还能占多少（``budget_gb``）。
"""

import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import Response

# ★ 池盘阈值：任务占用的体积上限 = （池总量 × 阈值 − 池已用），保证池不过 80%
POOL_THRESHOLD = 0.8


class PoolMixin:
    """池盘空间（按目录分池）。"""

    # ------------------------------------------------------------------ 目录发现
    def _pool_dirs(self) -> List[Tuple[str, str]]:
        """MP 目录配置里的下载目录 → [(显示名, 容器内路径)]（读不到时退回常见挂载点）。"""
        out: List[Tuple[str, str]] = []
        try:
            from app.application.directory import DirectoryHelper  # type: ignore  # noqa: WPS433

            for item in DirectoryHelper().get_download_dirs() or []:
                path = str(getattr(item, "download_path", "") or "").strip().strip("/")
                if not path:
                    continue
                container = "/" + path
                name = str(getattr(item, "name", "") or "") or container
                if container not in [x[1] for x in out]:
                    out.append((name, container))
        except Exception:  # noqa: BLE001
            out = []
        # 兜底：容器里实际存在的常见挂载点（保证至少能给个数字）
        for guess in ("/movie", "/media", "/movie1", "/downloads"):
            if os.path.isdir(guess) and guess not in [x[1] for x in out]:
                out.append((guess, guess))
        return out

    @staticmethod
    def _match_pool(save_path: str, dirs: List[Tuple[str, str]]) -> Tuple[str, str]:
        """把保存目录（qB 视角）匹配到某个池（容器视角）。

        规则：容器目录的最后一段（如 ``movie``）出现在保存路径的分段里 → 命中；
        多个命中时取**最靠后**（最具体）的那个。
        """
        parts = [seg for seg in str(save_path or "").split("/") if seg]
        best: Optional[Tuple[Tuple[int, int], str, str]] = None
        for name, container in dirs:
            base = container.rstrip("/").split("/")[-1]
            if not base or base not in parts:
                continue
            idx = len(parts) - 1 - parts[::-1].index(base)
            score = (idx, len(base))
            if best is None or score > best[0]:
                best = (score, name, container)
        if best:
            return best[1], best[2]
        return (dirs[0][0], dirs[0][1]) if dirs else ("", "")

    @staticmethod
    def _usage(container: str) -> Dict[str, Any]:
        """单个池的用量（读不到返回空）。"""
        try:
            usage = shutil.disk_usage(container)
        except Exception:  # noqa: BLE001
            return {}
        total = float(usage.total or 0)
        used = float(usage.used or 0)
        return {
            "total": total,
            "used": used,
            "free": float(usage.free or 0),
            "pct": round(used / total * 100, 1) if total else 0.0,
        }

    # ------------------------------------------------------------------ 端点
    def pool_info(self, path: str = "") -> Response:
        """池盘空间：``GET /pool?path=<任务保存目录>``（按目录分池，不做跨目录求和）。"""
        dirs = self._pool_dirs()
        name, container = self._match_pool(path, dirs)
        if not container:
            return Response(success=False, message="未找到可用的下载目录（请检查 MP 目录设置）")
        usage = self._usage(container)
        if not usage:
            return Response(success=False, message=f"读不到池盘空间：{container}")
        total = float(usage.get("total") or 0)
        used = float(usage.get("used") or 0)
        budget = max(total * POOL_THRESHOLD - used, 0.0)
        pools = []
        for pool_name, pool_path in dirs:
            info = self._usage(pool_path)
            if not info:
                continue
            pools.append({
                "name": pool_name,
                "path": pool_path,
                "total": info["total"],
                "used": info["used"],
                "free": info["free"],
                "pct": info["pct"],
                "matched": pool_path == container,
            })
        return Response(success=True, data={
            "name": name,
            "path": container,
            "source_path": str(path or ""),
            "total": total,
            "used": used,
            "free": float(usage.get("free") or 0),
            "pct": float(usage.get("pct") or 0.0),
            "threshold": POOL_THRESHOLD,
            "budget_gb": round(budget / 1024 ** 3, 1),
            "pools": pools,
        })
