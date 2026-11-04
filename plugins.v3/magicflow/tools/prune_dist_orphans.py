#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署后清理 ``dist`` 里的旧构建残留：**默认只报告，加 ``--prune`` 才真删**。

**为什么需要**：vite 每次构建都生成新的内容哈希文件名（``index-<hash>.js`` /
``__federation_expose_AppPage-<hash>.js``），旧哈希不会自动消失。走
``tools/deploy.sh`` 的 ``rsync -a --delete`` 会自动清，但**直传（SFTP/paramiko）
部署没有这一步**——实测 5 次部署堆了 30 个文件 9.26 MB。它们有两个害处：
① 排查时 ``grep`` 到的是旧包，"改了没生效"的误判源头；
② ``dist`` 有多大/哪一版在跑，肉眼数不出来。

**事故防线（本脚本的核心，不是可选项）**：孤儿集 = 远端 − 本地。这个算法的前提是
「远端跑的就是本地这一版」。若部署只成功了一半（新 py 上去了、dist 没同步或同步失败），
远端 ``index.html`` 仍是旧版，那么**上一版构建就会被算成"孤儿"而删掉** —— 正是
2026-10-30「删了旧哈希、``remoteEntry.js`` 还指向它 → 插件页整页打不开」那类事故。
所以删之前必须比对远端 ``index.html`` + ``assets/remoteEntry.js`` 与本地**逐字节一致**；
不一致就中止（这两份是入口，``remoteEntry.js`` 无哈希名、最容易被漏传）。

用法::

    python3 tools/prune_dist_orphans.py                    # 只报告（默认）
    python3 tools/prune_dist_orphans.py --prune            # 真删
    python3 tools/prune_dist_orphans.py --local           # 在 NAS 本机上跑（文件系统直读）
    python3 tools/prune_dist_orphans.py --dest /path/dist --local-src /path/src/dist

退出码：0 = 正常（含"无可清理"）；1 = 防线拦下或删除后校验失败。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time

DEFAULT_HOST = "192.168.0.61"
DEFAULT_USER = "guan"
DEFAULT_PASS = "raltszz5310"
DEFAULT_DEST = "/vol1/1000/moviepilot/plugins-local/magicflow/dist"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOCAL_SRC = os.path.join(os.path.dirname(HERE), "dist")
# 入口文件：必须与本地逐字节一致，否则说明远端跑的不是本地这一版
ENTRIES = ("index.html", "assets/remoteEntry.js")


# ── 传输层：本地文件系统 / SFTP 各一套，上层只认 rel → (size, mtime) ──

class LocalFS:
    """把本地目录包成与 SFTP 同形的接口（便于在 NAS 本机直跑）。"""

    def __init__(self, root: str) -> None:
        self.root = root

    def walk(self) -> dict:
        """递归列出 ``{rel: (size, mtime)}``，rel 用 POSIX 分隔符。"""
        out: dict = {}
        for cur, _dirs, files in os.walk(self.root):
            for f in files:
                p = os.path.join(cur, f)
                rel = os.path.relpath(p, self.root).replace("\\", "/")
                st = os.stat(p)
                out[rel] = (st.st_size, int(st.st_mtime))
        return out

    def md5(self, rel: str) -> str:
        """算整个文件的 md5（入口文件防线性比对）。"""
        h = hashlib.md5()
        with open(os.path.join(self.root, rel), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def remove(self, rel: str) -> None:
        """删一个文件（只删文件，不碰目录）。"""
        os.remove(os.path.join(self.root, rel))


class SftpFS:
    """paramiko SFTP 包装；连接延迟建立，只有真要跑时才连。"""

    def __init__(self, host: str, user: str, password: str, root: str) -> None:
        self.root = root
        self._cli = None
        try:
            import paramiko  # noqa: WPS433 —— 仅本工具需要，不进插件依赖
        except ImportError:
            sys.exit("✖ 需要 paramiko（pip install paramiko），或用 --local 在 NAS 本机跑")
        self._cli = paramiko.SSHClient()
        self._cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._cli.connect(host, 22, username=user, password=password,
                          timeout=15, allow_agent=False, look_for_keys=False)
        self._sftp = self._cli.open_sftp()

    def walk(self) -> dict:
        """递归列出 ``{rel: (size, mtime)}``。"""
        import stat as _stat

        out: dict = {}

        def rec(path: str, prefix: str) -> None:
            for a in self._sftp.listdir_attr(path):
                p = path + "/" + a.filename
                rel = (prefix + "/" + a.filename) if prefix else a.filename
                if _stat.S_ISDIR(a.st_mode):
                    rec(p, rel)
                else:
                    out[rel] = (a.st_size, int(a.st_mtime))

        rec(self.root, "")
        return out

    def md5(self, rel: str) -> str:
        """整文件 md5：分块读，避免一次性把 1.6MB chunk 拉进内存多份。"""
        h = hashlib.md5()
        with self._sftp.file(self.root + "/" + rel, "rb") as fh:
            fh.prefetch()
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def remove(self, rel: str) -> None:
        """删一个文件。"""
        self._sftp.remove(self.root + "/" + rel)

    def close(self) -> None:
        """关连接（失败不致命）。"""
        try:
            self._sftp.close()
            self._cli.close()
        except Exception:  # noqa: BLE001
            pass


def _entry_guard(fs, local_files: dict, local_src: str) -> None:
    """删前防线：远端入口文件必须与本地逐字节一致，否则中止。"""
    for rel in ENTRIES:
        if rel not in local_files:
            sys.exit(f"✖ 本地缺入口文件 {rel} —— dist 不完整，中止")
        far = fs.md5(rel)
        near = hashlib.md5(open(os.path.join(local_src, rel.replace("/", os.sep)), "rb").read()).hexdigest()
        flag = "✅" if far == near else "✖"
        print(f"  {flag} {rel:26s} md5 {far}{'' if far == near else ' ≠ ' + near}")
        if far != near:
            sys.exit(
                "✖ 远端入口与本地不一致 —— 说明远端跑的不是本地这一版。\n"
                "  此时「远端 − 本地」算出来的不是残留，而是**线上正在用的旧构建**。\n"
                "  拒绝删除。请先完成部署同步，再重跑本脚本。"
            )


def main() -> int:
    """列残留 → 过防线 → （可选）删除 → 复核。"""
    ap = argparse.ArgumentParser(description="清理 dist 旧构建残留（默认只报告）")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="远端 dist 目录")
    ap.add_argument("--local-src", default=DEFAULT_LOCAL_SRC, help="本地 dist 目录（真值）")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--local", action="store_true", help="在 NAS 本机直读文件系统（不用 SFTP）")
    ap.add_argument("--prune", action="store_true", help="真的删（缺省只报告）")
    args = ap.parse_args()

    if not os.path.isdir(args.local_src):
        sys.exit(f"✖ 本地 dist 不存在：{args.local_src}")

    fs = (LocalFS(args.dest) if args.local
          else SftpFS(args.host, args.user, args.password, args.dest))
    try:
        local_files = LocalFS(args.local_src).walk()
        remote = fs.walk()
        print(f"本地 {len(local_files)} 个文件 / 远端 {len(remote)} 个")

        print("── 入口一致性（防删掉线上那版）──")
        _entry_guard(fs, local_files, args.local_src)

        orphans = {k: v for k, v in remote.items() if k not in local_files}
        missing = [k for k in local_files if k not in remote]
        if missing:
            print(f"\n⚠ 本地有、远端没有 {len(missing)} 个（部署不完整，先补同步）：")
            for k in sorted(missing):
                print("   ", k)

        if not orphans:
            print("\n✅ 无可清理，dist 已经是当前构建的干净态")
            return 0

        # 按 mtime 归「构建批次」看堆了几版。★ 不能直接拿 mtime 当键：同一次构建里
        # 文件是逐个写出的，13 个文件能横跨 2~3 秒（实测一次构建被切成 3 组）。按 5 分钟
        # 粒度归并才等于"一次部署"。
        batch_sec = 300
        batches: dict = {}
        for k, (_sz, mt) in orphans.items():
            batches.setdefault(mt // batch_sec * batch_sec, []).append(k)
        total = sum(v[0] for v in orphans.values())
        print(f"\n── 旧构建残留 {len(orphans)} 个 / {total / 1048576.0:.2f} MB"
              f"（{len(batches)} 个批次）──")
        for mt in sorted(batches, reverse=True):
            names = sorted(batches[mt])
            sz = sum(orphans[n][0] for n in names)
            print(f"  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))}"
                  f"  {len(names):2d} 个  {sz / 1048576.0:.2f} MB")
            for n in names:
                print(f"        {n:56s} {orphans[n][0]:>9d} B")

        if not args.prune:
            print("\n（只报告。加 --prune 真删）")
            return 0

        print("\n── 删除 ──")
        bad = 0
        for k in sorted(orphans):
            try:
                fs.remove(k)
                print(f"  ✓ {k}")
            except Exception as e:  # noqa: BLE001
                bad += 1
                print(f"  ✖ {k} —— {e}")

        after = fs.walk()
        left = sorted(set(after) - set(local_files))
        print(f"\n复核：远端剩 {len(after)} 个文件，非当前构建残留 {len(left)} 个")
        for k in left:
            print("   仍存在:", k)
        if bad or left:
            return 1
        print("✅ 清理完成，dist 只剩当前构建")
        return 0
    finally:
        if hasattr(fs, "close"):
            fs.close()


if __name__ == "__main__":
    sys.exit(main())
