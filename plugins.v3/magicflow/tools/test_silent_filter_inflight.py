# -*- coding: utf-8 -*-
"""test_silent_filter_inflight · 15.8.3

★ 点播下完之前（inflight）不被静默闸补暂停。
下完之后走 _ondemand_settle → 转资源 → 资源账本接管 → 回到正常静默闸管辖。

校验：
  1) 源码有 `_od_inflight` 过滤变量定义
  2) 主循环有 `if hh in _od_inflight: continue`
  3) tag_only 对账循环也有 `if _hh3 in _od_inflight: continue`
  4) 注释里写清 Master 口径和时序
  5) ★ 15.8.11 同版补丁：音乐线「下载中」（progress<1）同点播 inflight 待遇 ——
     主循环 / tag_only 对账 / 暂停闸三处都跳过（Master 口径原文 `下载中不会被静默池暂停`）

运行：python3 tools/test_silent_filter_inflight.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SILENT_PY = os.path.join(ROOT, "features", "silent.py")


class SilentFilterInflightTest(unittest.TestCase):
    """★ 15.8.3：点播 inflight 不进静默闸"""

    def test_01_source_has_filter(self):
        with open(SILENT_PY) as f:
            src = f.read()
        self.assertIn("_od_inflight", src, "源码应包含 _od_inflight 过滤变量")
        self.assertIn("_od_inflight = set()", src, "源码应包含 _od_inflight 默认空集合")

    def test_02_main_loop_skips_inflight(self):
        with open(SILENT_PY) as f:
            src = f.read()
        self.assertIn("if hh in _od_inflight or hh in _music_inflight:", src,
                      "源码应包含主循环 inflight 跳过（15.8.11 起含音乐线）")

    def test_03_tag_only_loop_skips_inflight(self):
        with open(SILENT_PY) as f:
            src = f.read()
        self.assertIn("if _hh3 in _od_inflight or _hh3 in _music_inflight:", src,
                      "源码应包含 tag_only 对账 inflight 跳过（15.8.11 起含音乐线）")

    def test_04_doc_marker(self):
        with open(SILENT_PY) as f:
            src = f.read()
        self.assertIn("15.8.3", src, "源码应标 15.8.3 注释锚点")
        # 口径关键词
        self.assertIn("下完之前", src,
                      "源码应说明「下完之前」不暂停口径")
        self.assertIn("ondemand_pending", src,
                      "源码应说明真值源 = ondemand_pending slot")

    def test_05_ondemand_api_unchanged(self):
        """on-demand API 端点没新增/删除"""
        with open(os.path.join(ROOT, "features", "api.py")) as f:
            api = f.read()
        # /ondemand 三件套：ondemand / ondemand_items / ondemand_act
        self.assertIn('"path": "/ondemand"', api)
        self.assertIn('"path": "/ondemand/items"', api)
        self.assertIn('"path": "/ondemand/act"', api)

    # ★ 15.8.11 同版补丁：音乐线「下载中」同点播 inflight 待遇
    def test_06_music_inflight_source_guard(self):
        with open(SILENT_PY) as f:
            src = f.read()
        self.assertIn("_music_inflight", src, "源码应包含 _music_inflight 过滤变量")
        self.assertIn('rep["skipped_music_inflight"]', src,
                      "暂停闸应记录被豁免的音乐线 inflight 数")
        self.assertIn("下载中不会被静默池暂停", src, "源码应写 Master 口径原文")


if __name__ == "__main__":
    unittest.main(verbosity=2)