#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""护栏：前端 composables 依赖闭环检查（P3 拆分专用）

背景（2026-10-08 血泪）：把 index.vue 的域抽成 composables 时，最容易出的两类
**静默**错误（构建不报错、控制台不报错，只在打开对应页面时弹窗空白）：

  1. **漏 import 常量**：composable 里用了 `SIGNIN_STATUS_TEXT`（本来在 index.vue 顶部
     从 constants.js 导入），搬家时没一起 import → 运行到那行 ReferenceError →
     Vue 渲染中断 → VDialog 只剩一个 `<!---->`（空弹窗）。
  2. **漏注入 / 漏解构**：composable 返回了 X 但 index.vue 没解构（或反过来），
     模板里 X 未定义。

本工具做两件事：
  A. 依赖闭环：对每个 composables/*.js，找出「引用了、但既没本地声明、也没 import、
     也没从工厂函数参数注入」的标识符，且该标识符在 index.vue 作用域里存在
     → 说明它本该 import 或注入 → 报错。
  B. 解构↔return 对齐：index.vue 里 `const { ... } = useXxx({...})` 的名字集合
     必须与 composables/useXxx.js 的 `return { ... }` 名字集合**完全一致**。

用法：python3 tools/check_composables.py
退出码 0 = 通过。
"""
import os
import re
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS = os.path.join(ROOT, 'src', 'views', 'magicflow')
INDEX = os.path.join(VIEWS, 'index.vue')
COMPOSABLES = os.path.join(VIEWS, 'composables')

KEYWORDS = set("""const let var function return if else for while switch case break continue
try catch finally new typeof instanceof await async of in do throw delete void yield this
true false null undefined import export default class extends super static get set""".split())

BUILTINS = set("""Math Number String Boolean Array Object JSON Date Map Set WeakMap WeakSet
Promise RegExp URLSearchParams URL isFinite isNaN parseInt parseFloat window document console
setTimeout clearTimeout setInterval clearInterval navigator localStorage sessionStorage
undefined NaN Infinity encodeURIComponent decodeURIComponent Error Symbol BigInt globalThis Intl
structuredClone queueMicrotask requestAnimationFrame cancelAnimationFrame alert confirm prompt
fetch location history Blob File FileReader FormData Headers Request Response AbortController
crypto performance getComputedStyle matchMedia CustomEvent Event Node Element HTMLElement
TextEncoder TextDecoder Uint8Array Float64Array WebSocket IntersectionObserver
MutationObserver ResizeObserver""".split())


def strip_literals(s):
    """抹白字符串 / 注释 / 正则；模板串只抹**字面部分**，`` `${expr}` `` 里的表达式原样保留
    （否则会漏扫模板串里的引用 —— 正是 2026-10-08 「白屏」那一类）。"""
    out = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '/' and i + 1 < n and s[i + 1] == '/':
            j = s.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch == '/' and i + 1 < n and s[i + 1] == '*':
            j = s.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in ('"', "'"):
            j = i + 1
            while j < n:
                if s[j] == '\\':
                    j += 2
                    continue
                if s[j] == '\n':
                    break
                if s[j] == ch:
                    j += 1
                    break
                j += 1
            out.append(' ' * (j - i))
            i = j
            continue
        if ch == '`':
            i += 1
            while i < n:
                c = s[i]
                if c == '\\':
                    i += 2
                    continue
                if c == '`':
                    i += 1
                    break
                if c == '$' and i + 1 < n and s[i + 1] == '{':
                    out.append(' ')          # 抹掉 $
                    out.append('{')          # 保留花括号
                    i += 2
                    depth = 1
                    while i < n and depth > 0:
                        c2 = s[i]
                        if c2 == '{':
                            depth += 1
                        elif c2 == '}':
                            depth -= 1
                        out.append(c2 if depth > 0 else '}')
                        i += 1
                    continue
                out.append(' ')              # 字面部分抹白
                i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out).replace('${', ' {')   # 收尾消掉嵌套模板串漏出的 $


def collect_locals(src):
    """本地声明：const/let/var、function 名、import 名、箭头/函数参数、解构参数。"""
    local = set()
    for m in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)', src):
        local.add(m.group(1))
    for m in re.finditer(r'\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', src):
        local.add(m.group(1))
    for m in re.finditer(r'\b(?:const|let|var)\s*\{([^}]*)\}', src):
        for p in m.group(1).split(','):
            p = p.strip().split(':')[-1].split('=')[0].strip()
            if p:
                local.add(p)
    for m in re.finditer(r'import\s*\{([^}]*)\}', src, re.S):
        for x in m.group(1).split(','):
            x = x.strip().split(' as ')[-1].strip()
            if x:
                local.add(x)
    for m in re.finditer(r'^\s*import\s+([A-Za-z_$][\w$]*)\s', src, re.M):
        local.add(m.group(1))
    for m in re.finditer(r'\(([^)]*)\)\s*=>', src):
        for p in m.group(1).split(','):
            ids = re.findall(r'[A-Za-z_$][\w$]*', p)
            if ids:
                local.add(ids[-1])
    for m in re.finditer(r'([A-Za-z_$][\w$]*)\s*=>', src):
        local.add(m.group(1))
    for m in re.finditer(r'\bfunction\s*[A-Za-z_$\w]*\s*\(([^)]*)\)', src):
        for p in m.group(1).split(','):
            p = p.strip().split('=')[0].strip()
            if p:
                local.add(p)
    for m in re.finditer(r'\bcatch\s*\(([^)]*)\)', src):
        p = m.group(1).strip()
        if p:
            local.add(p)
    for m in re.finditer(r'\b(?:const|let|var)\s*\[([^\]]*)\]', src):
        for p in m.group(1).split(','):
            p = p.strip().split('=')[0].strip()
            if p:
                local.add(p)
    # 箭头函数的对象解构参数 ({ a, b }) => ...
    for m in re.finditer(r'\(\s*\{([^}]*)\}\s*\)\s*=>', src):
        for p in m.group(1).split(','):
            p = p.strip().split(':')[-1].split('=')[0].strip()
            if p:
                local.add(p)
    return local


def index_globals():
    """index.vue 的 <script> 作用域里的名字（可 import / 可注入的来源）。"""
    src = open(INDEX, encoding='utf-8').read()
    lines = src.split('\n')
    end = next(i for i, l in enumerate(lines) if l.startswith('</script>'))
    head = '\n'.join(lines[:end])
    names = set()
    for l in lines[:end]:
        m = re.match(r'^(?:const|let|var|async function|function)\s+([A-Za-z_$][\w$]*)', l)
        if m:
            names.add(m.group(1))
    for m in re.finditer(r'import\s*\{([^}]*)\}', head, re.S):
        for x in m.group(1).split(','):
            x = x.strip().split(' as ')[-1].strip()
            if x:
                names.add(x)
    return names


def factory_params(src):
    """导出工厂函数的解构参数（= 注入依赖名）。"""
    m = re.search(r'export\s+function\s+use[A-Za-z0-9_$]*\s*\(\s*\{([^}]*)\}', src)
    if not m:
        return set()
    out = set()
    for p in m.group(1).split(','):
        p = p.strip().split(':')[-1].split('=')[0].strip()
        if p:
            out.add(p)
    return out


def return_names(src):
    i = src.rfind('return {')
    if i < 0:
        return None
    body = src[i + len('return {'):]
    body = body.split('}', 1)[0]
    return [x.strip() for x in body.replace('\n', ' ').split(',') if x.strip()]


def declared_imports(src):
    out = set()
    for m in re.finditer(r'import\s*\{([^}]*)\}', src, re.S):
        for x in m.group(1).split(','):
            x = x.strip().split(' as ')[-1].strip()
            if x:
                out.add(x)
    return out


def module_exports(path):
    """目标模块的真实导出名集合（找不到模块返回 None）。"""
    for cand in (path, path + '.js', path + '.vue', os.path.join(path, 'index.js')):
        if os.path.isfile(cand):
            t = open(cand, encoding='utf-8').read()
            out = set()
            for m in re.finditer(r'export\s+(?:const|let|var|function|async function|class)\s+([A-Za-z_$][\w$]*)', t):
                out.add(m.group(1))
            for m in re.finditer(r'export\s*\{([^}]*)\}', t):
                for x in m.group(1).split(','):
                    x = x.strip().split(' as ')[-1].strip()
                    if x:
                        out.add(x)
            return out
    return None


def main():
    fails = []
    G = index_globals()
    idx_src = open(INDEX, encoding='utf-8').read()

    files = sorted(glob.glob(os.path.join(COMPOSABLES, '*.js')))
    files += [p for p in (os.path.join(VIEWS, 'format.js'),) if os.path.exists(p)]

    for path in files:
        name = os.path.basename(path)
        src = open(path, encoding='utf-8').read()
        local = collect_locals(src)
        injected = factory_params(src)
        imports = declared_imports(src)
        body = strip_literals(src)

        # ---- D. import 名必须在目标模块真实导出（防「误从 constants 导入」一类）----
        for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"](\.[^'\"]+)['\"]", src):
            nms = [x.strip().split(' as ')[-1].strip() for x in m.group(1).split(',') if x.strip()]
            tgt = os.path.normpath(os.path.join(os.path.dirname(path), m.group(2)))
            exp = module_exports(tgt)
            if exp is None:
                fails.append('%s：import 目标模块不存在 → %s' % (name, m.group(2)))
                continue
            miss = [x for x in nms if x not in exp]
            if miss:
                fails.append('%s：import 了目标模块（%s）未导出的名字 → %s'
                             % (name, m.group(2), ', '.join(miss)))

        # ---- A. 依赖闭环 ----
        missing = set()
        for m in re.finditer(r'\b([A-Za-z_$][\w$]*)\b', body):
            w = m.group(1)
            if w in local or w in injected or w in KEYWORDS or w in BUILTINS:
                continue
            if re.search(r'\.\s*%s\b' % re.escape(w), body):   # 属性访问
                continue
            # 对象字面量的键（如 { tasks: … }）——只认「{ 或 , 开头」的键；三元 `? x : y` 不算
            if re.search(r'(?:^|[{,])\s*%s\s*:' % re.escape(w), body, re.M):
                continue
            if w in G and w not in imports:
                missing.add(w)
        if missing:
            fails.append('%s：引用了但既没 import、也没注入 → %s'
                         % (name, ', '.join(sorted(missing))))

        # ---- B. 解构 ↔ return 对齐 ----
        if name.startswith('use'):
            fn = name[:-3]
            m = re.search(r'const\s*\{([^}]*)\}\s*=\s*%s\s*\(' % re.escape(fn), idx_src, re.S)
            if not m:
                fails.append('%s：index.vue 里找不到 `const { ... } = %s(...)` 解构' % (name, fn))
                continue
            used = [x.strip() for x in m.group(1).replace('\n', ' ').split(',') if x.strip()]
            defined = return_names(src)
            if defined is None:
                fails.append('%s：找不到 return { ... }' % name)
                continue
            # ★ 规则 C（2026-10-08 血泪）：return 里的**裸名**必须本地声明或注入。
            #   踩过：useTagModel 的 state 切片少切一行 → `return { tagInfo }` 引用未定义
            #   变量 → 工厂函数一调用就 ReferenceError → 整个插件页白屏（构建/控制台都不报）。
            i = src.rfind('return {')
            raw = src[i + len('return {'):].split('}', 1)[0].replace('\n', ' ')
            for e in raw.split(','):
                e = e.strip()
                if not e or e.startswith('...') or ':' in e or '(' in e:
                    continue
                if e not in local and e not in injected:
                    fails.append('%s：return 里的裸名 %s **没有本地声明、也不是注入参数**（会 ReferenceError）'
                                 % (name, e))
            miss = [x for x in used if x not in defined]
            extra = [x for x in defined if x not in used]
            if miss:
                fails.append('%s：index.vue 解构了但 composable 没返回 → %s' % (name, ', '.join(miss)))
            if extra:
                fails.append('%s：composable 返回了但 index.vue 没解构 → %s' % (name, ', '.join(extra)))

    if fails:
        print('❌ 前端 composables 依赖/对齐检查未通过：')
        for f in fails:
            print('   - ' + f)
        return 1
    n = len([f for f in files if os.path.basename(f).startswith('use')])
    print('✅ 前端 composables 依赖闭环 + 解构对齐全通过（%d 个 use* + 共享模块）' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
