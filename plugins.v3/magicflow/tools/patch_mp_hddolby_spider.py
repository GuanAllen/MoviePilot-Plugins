# -*- coding: utf-8 -*-
"""MP HDDolby 索引器修补：搜索参数不带 categories（实测可恢复搜索）。

用法（宿主机）：
    docker cp magicflow/tools/patch_mp_hddolby_spider.py moviepilot-v3:/tmp/
    docker exec moviepilot-v3 python3 /tmp/patch_mp_hddolby_spider.py
    docker restart moviepilot-v3

MP 升级后会覆盖 /app/app/modules/indexer/spider/hddolby.py，需重跑本脚本。
"""
import io
import os
import shutil

P = "/app/app/modules/indexer/spider/hddolby.py"
OLD = '            "categories": categories,\n'


def main() -> int:
    if not os.path.exists(P):
        print("not found:", P)
        return 1
    s = io.open(P, encoding="utf-8").read()
    if OLD not in s:
        print("already patched")
        return 0
    shutil.copy(P, P + ".bak-categories")
    s = s.replace(OLD, "", 1)
    io.open(P, "w", encoding="utf-8").write(s)
    import py_compile
    py_compile.compile(P, doraise=True)
    print("patched + compile ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
