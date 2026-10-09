#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""护栏⑧：.vue <script> 使用了 Vue API 但未 `import {...} from 'vue'`。

背景（2026-10-09 白屏事故）：本项目 **未配置 auto-import**（见 vite.config.*，无
unplugin-auto-import / unplugin-vue-components），故所有 Vue API 必须显式 import。
P4 前端拆分「纯搬家」时，把 `computed(...)` 的**用法**搬进了 MobileHome.vue，却把
`import { computed } from 'vue'` 留在了父页 → 构建成功（Vite 对未定义全局不报错）→
运行时 `computed is not defined`（ReferenceError）被 Vue errorHandler 吞掉 → 组件渲染
成注释节点 → 手机首页白屏。既有护栏（语法/名字/绑定）都抓不到这种「跨文件搬运丢 import」。

本脚本静态扫描 src 下每个 .vue，比对「用到的 Vue API」与「从 vue 导入的名字」，求差集。
定义宏（defineProps/defineEmits/defineExpose/defineModel/defineOptions/defineSlots/
withDefaults）由编译器处理，无需 import，白名单放行。
"""
import re
import sys
from pathlib import Path

# 需要显式 import 的运行时 API（仅收集「会被调用」的名称，要求后面跟 "("）。
VUE_APIS = [
    "computed", "ref", "reactive", "readonly", "watch", "watchEffect", "watchPostEffect",
    "watchSyncEffect", "onMounted", "onUnmounted", "onBeforeMount", "onBeforeUnmount",
    "onUpdated", "onBeforeUpdate", "onActivated", "onDeactivated", "onErrorCaptured",
    "nextTick", "toRef", "toRefs", "toValue", "unref", "isRef", "shallowRef", "triggerRef",
    "markRaw", "toRaw", "shallowReactive", "shallowReadonly", "effectScope",
    "getCurrentInstance", "provide", "inject", "h", "defineComponent", "defineAsyncComponent",
    "useCssModule", "useId", "useAttrs", "useSlots", "createApp", "mergeProps", "cloneVNode",
]
# 编译器宏：无需 import。
MACROS = {
    "defineProps", "defineEmits", "defineExpose", "defineModel", "defineOptions",
    "defineSlots", "withDefaults", "useTemplateRef",
}

VERBOSE = "--verbose" in sys.argv


def strip_noise(code: str) -> str:
    code = re.sub(r"//[^\n]*", "", code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return code


def scan_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", text, re.S)
    if not scripts:
        return None
    code = strip_noise("\n".join(scripts))

    imported = set()
    for im in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"][^'\"]*vue['\"]", code):
        for part in im.group(1).split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                imported.add(name)
    # 形如  import * as vue from 'vue' / import Vue from 'vue' → 视为全量，直接放行。
    if re.search(r"import\s*\*\s*as\s+\w+\s*from\s*['\"][^'\"]*vue['\"]", code) or \
       re.search(r"import\s+[A-Za-z_$][\w$]*\s+from\s*['\"][^'\"]*vue['\"]", code):
        return []

    used = set()
    for api in VUE_APIS:
        if api in imported or api in MACROS:
            continue
        # 调用式：前面不是标识符字符 / 点号（排除 obj.computed( ），后面跟 ( 。
        if re.search(r"(?<![\w.$])" + re.escape(api) + r"\s*\(", code):
            used.add(api)
    return sorted(used - imported - MACROS)


def main() -> int:
    root = Path("src")
    if not root.is_dir():
        print("❌ 未找到 src/ 目录（请在插件仓库根运行）")
        return 1
    files = sorted(root.rglob("*.vue"))
    bad = []
    for f in files:
        miss = scan_file(f)
        if miss:
            bad.append((f, miss))
    if bad:
        print(f"❌ Vue API 未导入（护栏⑧）：{len(bad)} 个文件（项目无 auto-import，须显式 import）")
        for f, miss in bad:
            print(f"   {f}: 缺 {', '.join(miss)}  ← 补 `import {{ {', '.join(miss)} }} from 'vue'`")
        return 1
    print(f"✅ Vue API 导入护栏通过（扫描 {len(files)} 个 .vue，无未导入的 Vue API）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
