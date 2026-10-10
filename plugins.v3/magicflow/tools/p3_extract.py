#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3 抽域工具 —— 把 index.vue 里一个「域」的顶层声明批量搬进 composable。

为什么要它：域是**散着**的（一个域的状态、computed、动作、定时器可能分散在文件各处，
块注释还会骗人），手工「找区域 → 剪 → 缩进 → 拼 → 回填 → 校验」每一步都是手活。
本工具按**标识符归属**做手术，并内建自检，避免再踩「漏声明 → 整个插件页白屏」。

用法
----
# ① 挑域：每块「本地声明数 / 外部依赖数」，越靠上越自洽（越好抽）
python3 tools/p3_extract.py --scan

# ② 干跑：看计划（区域、注入参数、import、return），不写文件
python3 tools/p3_extract.py --name useCloud --idents cloudState,cloudPlan,loadCloud,runCloud

# ③ 落地：写 composable + 改 index.vue + 跑护栏 + build
python3 tools/p3_extract.py --name useCloud --idents <...> --apply --guards --build

# ④ 自检：把已有 composable 的正文与「抽取前」的 index.vue（git HEAD）逐行比对
python3 tools/p3_extract.py --verify

约定
----
* ★★ 回填点 = **必须晚于所有注入参数（const/let/var）的声明**：`const api = createApi(...)` 不提升，
  回填块若写在它前面 → `ReferenceError` → **整个插件页白屏**（2026-10-08 云盘域踩过，L292 → 自动后移到 L347）。
  函数声明会提升、不算数；工具会自动后移并在 TDZ 预检里扫「回填点之前的顶层引用」。
* 区域边界：顶层声明（col 0 的 const/let/var/function/async function）用**括号平衡**找结尾；
  onMounted/onUnmounted 里属于本域的定时器 / 初次加载行自动搬进 composable 自管。
* 注入参数：正文里「既不是本地声明、也不是 import、也不是 JS 内置」的标识符 = 注入候选；
  vue API 自动 import，`unwrapResponse` / 常量自动从 utils / constants 取。
* 落盘前内置**规则 C** 自检：`return {…}` 的裸名必须本地声明或注入（护栏⑥同口径）。
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, 'src/views/magicflow/index.vue')
COMP_DIR = os.path.join(ROOT, 'src/views/magicflow/composables')

KEYWORDS = set("""break case catch class const continue debugger default delete do else export extends
finally for function if import in instanceof let new of return super switch this throw try typeof var
void while with yield async await static get set true false null undefined""".split())
BUILTINS = set("""Math Number String Boolean Array Object JSON Date Map Set WeakMap WeakSet Promise RegExp
URLSearchParams URL isFinite isNaN parseInt parseFloat window document console setTimeout clearTimeout
setInterval clearInterval navigator localStorage sessionStorage undefined NaN Infinity
encodeURIComponent decodeURIComponent Error Symbol BigInt globalThis Intl structuredClone queueMicrotask
requestAnimationFrame cancelAnimationFrame alert confirm prompt fetch location history Blob File
FileReader FormData AbortController crypto performance getComputedStyle matchMedia CustomEvent Event
TextEncoder TextDecoder Uint8Array WebSocket IntersectionObserver MutationObserver ResizeObserver
arguments""".split())
VUE_APIS = set("""ref shallowRef computed reactive readonly watch watchEffect onMounted onUnmounted
onBeforeUnmount nextTick toRef toRefs inject provide defineProps defineEmits defineExpose h markRaw
toRaw unref isRef""".split())


# ────────────────────────── 基础文本处理 ──────────────────────────

def read_lines(p):
    with open(p, encoding='utf-8') as f:
        return f.read().split('\n')


# `/` 前面是这些字符时，按「正则字面量」开始处理（否则是除法运算符）
REGEX_PREV = set("=([{,:;!&|?+-*%<>~^")
REGEX_KEYWORDS = {'return', 'typeof', 'instanceof', 'in', 'of', 'case', 'delete',
                  'void', 'new', 'do', 'else', 'yield', 'await'}


def _src_prev_sig(src, i):
    """src 中 i 之前最后一个非空白字符（跨行）。"""
    j = i - 1
    while j >= 0 and src[j] in ' \t\r\n':
        j -= 1
    return src[j] if j >= 0 else ''


def _src_trailing_word(src, i):
    """src 中 i 之前紧邻的标识符（判断 return /re/ 这类关键字前缀）。"""
    j = i - 1
    while j >= 0 and src[j] in ' \t\r\n':
        j -= 1
    k = j
    while k >= 0 and (src[k].isalnum() or src[k] in '_$'):
        k -= 1
    return src[k + 1:j + 1]


def mask_lines(lines):
    """把字符串/注释/正则里的内容替换成空格（保留引号外壳、换行），用于括号平衡与标识符扫描。
    模板串 `` `...${expr}...` ``：字面部分抹白，**`${}` 表达式原样保留**（那是真代码）。"""
    src = '\n'.join(lines)
    n = len(src)
    out = ['\n' if c == '\n' else ' ' for c in src]
    i = 0
    while i < n:
        ch = src[i]
        if ch == '\n':
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == '/':
            prev = _src_prev_sig(src, i)
            is_regex = (prev == '' or prev in REGEX_PREV
                        or (prev.isalnum() and _src_trailing_word(src, i) in REGEX_KEYWORDS))
            if is_regex:
                j = i + 1
                in_class = False
                while j < n:
                    c = src[j]
                    if c == '\\':
                        j += 2
                        continue
                    if c == '\n':
                        break
                    if c == '[':
                        in_class = True
                    elif c == ']':
                        in_class = False
                    elif c == '/' and not in_class:
                        break
                    j += 1
                if j < n and src[j] == '/':
                    k = j + 1
                    while k < n and src[k].isalpha():
                        k += 1
                    i = k
                    continue
            i += 1
            continue
        if ch in ('"', "'"):
            q = ch
            out[i] = q
            j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '\n':
                    break
                if src[j] == q:
                    out[j] = q
                    j += 1
                    break
                j += 1
            i = j
            continue
        if ch == '`':
            out[i] = '`'
            i += 1
            while i < n:
                c = src[i]
                if c == '\\':
                    i += 2
                    continue
                if c == '`':
                    out[i] = '`'
                    i += 1
                    break
                if c == '$' and i + 1 < n and src[i + 1] == '{':
                    out[i + 1] = '{'
                    i += 2
                    depth = 1
                    while i < n and depth > 0:
                        c2 = src[i]
                        if c2 == '\n':
                            out[i] = '\n'
                        else:
                            if c2 == '{':
                                depth += 1
                            elif c2 == '}':
                                depth -= 1
                            out[i] = c2
                        i += 1
                    continue
                i += 1
            continue
        out[i] = ch
        i += 1
    return ''.join(out).split('\n')


def script_range(lines):
    s = next(i for i, l in enumerate(lines) if l.startswith('<script'))
    e = next(i for i, l in enumerate(lines) if l.startswith('</script>'))
    return s, e


DECL_RE = re.compile(r'^(const|let|var|async function|function)\s+([A-Za-z_$][\w$]*)')


def decl_regions(masked, start, end):
    """顶层声明：名字 → (起, 止) 行号（0-based，含止行）。用括号平衡找结尾。"""
    regs = {}
    i = start
    while i < end:
        m = DECL_RE.match(masked[i])
        if not m:
            i += 1
            continue
        name = m.group(2)
        depth = 0
        j = i
        while j < end:
            depth += masked[j].count('(') + masked[j].count('[') + masked[j].count('{')
            depth -= masked[j].count(')') + masked[j].count(']') + masked[j].count('}')
            if depth <= 0 and j >= i:
                break
            j += 1
        regs.setdefault(name, (i, min(j, end - 1)))
        i = min(j, end - 1) + 1
    return regs


def hook_ranges(lines, masked, start, end):
    """onMounted / onUnmounted 调用的 (起, 止) 区间。"""
    res = []
    for i in range(start, end):
        m = re.match(r'^(onMounted|onUnmounted)\s*\(', masked[i])
        if not m:
            continue
        depth = 0
        j = i
        while j < end:
            depth += masked[j].count('(') + masked[j].count('{')
            depth -= masked[j].count(')') + masked[j].count('}')
            if depth <= 0:
                break
            j += 1
        res.append((m.group(1), i, min(j, end - 1)))
    return res


def collect_locals(src):
    """与 tools/check_composables.py 同口径的本地声明集合。"""
    local = set()
    for m in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)', src):
        local.add(m.group(1))
    for m in re.finditer(r'\b(?:const|let|var)\s*\{([^}]*)\}', src):
        for p in m.group(1).split(','):
            p = p.strip().split(':')[-1].split('=')[0].strip()
            if p:
                local.add(p)
    for m in re.finditer(r'\b(?:const|let|var)\s*\[([^\]]*)\]', src):
        for p in m.group(1).split(','):
            p = p.strip().split('=')[0].strip()
            if p:
                local.add(p)
    for m in re.finditer(r'\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', src):
        local.add(m.group(1))
    for m in re.finditer(r'\b(?:async\s+)?function\s*[A-Za-z_$\w]*\s*\(([^)]*)\)', src):
        for p in m.group(1).split(','):
            p = p.strip().split('=')[0].strip()
            if p:
                local.add(p)
    for m in re.finditer(r'catch\s*\(([^)]*)\)', src):
        p = m.group(1).strip()
        if p:
            local.add(p)
    for m in re.finditer(r'\(([^)]*)\)\s*=>', src):
        for p in m.group(1).split(','):
            ids = re.findall(r'[A-Za-z_$][\w$]*', p)
            if ids:
                local.add(ids[-1])
    for m in re.finditer(r'\(?\s*([A-Za-z_$][\w$]*)\s*=>', src):
        local.add(m.group(1))
    return local


def free_idents(body, local, extra_ok=()):
    """正文里「未声明」的标识符（去属性访问 / 对象键 / 内置 / 关键字）。"""
    miss = {}
    ok = set(local) | BUILTINS | KEYWORDS | set(extra_ok)
    for m in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)', body):
        w = m.group(1)
        if w in ok:
            continue
        tail = body[m.end():m.end() + 40]
        if tail.lstrip().startswith(':'):          # 对象键
            continue
        if re.match(r'^\s*[A-Za-z0-9_$]*\s*:', w):  # 保险
            continue
        miss[w] = miss.get(w, 0) + 1
    return miss


# ────────────────────────── 扫描 / 挑域 ──────────────────────────

def scan():
    lines = read_lines(IDX)
    masked = mask_lines(lines)
    s, e = script_range(lines)
    marks = [(i, lines[i]) for i in range(s, e) if lines[i].startswith('// ── ')]
    regs = decl_regions(masked, s, e)
    all_decls = set(regs)
    tpl = '\n'.join(lines[:s] + lines[e:])
    rows = []
    for k, (i, title) in enumerate(marks):
        j = marks[k + 1][0] if k + 1 < len(marks) else e
        seg = '\n'.join(masked[i:j])
        inner = [n for n, (a, b) in regs.items() if i <= a < j]
        miss = free_idents(seg, inner, extra_ok=('api', 'notify', 'unwrapResponse'))
        miss = {k2: v for k2, v in miss.items() if k2 not in all_decls}
        rows.append((len(miss), -len(inner), title.strip(), i + 1, j, sorted(inner), sorted(miss)))
    rows.sort()
    print('%-4s %-5s %-46s %s' % ('外部', '本地', '块（行区间）', '块内顶层声明'))
    print('-' * 130)
    for ext, negloc, title, a, b, inner, miss in rows:
        print('%-4d %-5d %-46s %s' % (ext, -negloc, '%s  L%d–%d' % (title[:40], a, b), ','.join(inner)[:110]))
    print()
    print('★ 抽域建议：挑「外部少、本地多」的块；--idents 用上面的「块内顶层声明」名单（剔除别域的）。')
    print('  注意：块名会骗人 —— 用块的**标识符归属**判域，别只看标题。')


# ────────────────────────── 抽取 ──────────────────────────

def movable_hook_lines(lines, masked, hooks, idents):
    """找 onMounted/onUnmounted 里属于本域、可以搬走的行：定时器赋值/清理 + 纯 loadXxx() 调用。"""
    plan = {}          # hook 名 → [(行号, 去缩进文本, 是否带前导注释)]
    drop = set()
    for name, a, b in hooks:
        for i in range(a + 1, b):
            raw = lines[i]
            t = raw.strip()
            if not t:
                continue
            if t.startswith('//'):
                continue
            if re.search(r'\b\w+Timer\b', t) and ('window.set' in t or 'window.clear' in t):
                if any(re.search(r'\b%s\b' % re.escape(x), t) for x in idents):
                    plan.setdefault(name, []).append(i)
                    drop.add(i)
                    if i - 1 > a and lines[i - 1].strip().startswith('//'):
                        plan[name].append(i - 1)
                        drop.add(i - 1)
                continue
            if re.match(r'^(await\s+)?[A-Za-z_$][\w$]*\(\)$', t):
                fn = re.match(r'^(?:await\s+)?([A-Za-z_$][\w$]*)\(\)$', t).group(1)
                if fn in idents:
                    plan.setdefault(name, []).append(i)
                    drop.add(i)
                    if i - 1 > a and lines[i - 1].strip().startswith('//'):
                        plan[name].append(i - 1)
                        drop.add(i - 1)
    for name in plan:
        plan[name] = sorted(plan[name])
    return plan, drop


def extract(name, idents, inject=None, imports=None, apply=False, guards=False, build=False,
            preflight=False, move_hooks=True):
    lines = read_lines(IDX)
    masked = mask_lines(lines)
    s, e = script_range(lines)
    regs = decl_regions(masked, s, e)
    hooks = hook_ranges(lines, masked, s, e)

    missing = [x for x in idents if x not in regs]
    found = [x for x in idents if x in regs]
    if missing:
        print('⚠️  未找到顶层声明（可能已抽走 / 名字写错）：%s' % ', '.join(missing))
    if not found:
        print('❌ 没有可搬的声明，退出。')
        return 1

    regions = sorted({regs[x] for x in found})
    merged = []
    for a, b in regions:                     # 合并相邻/重叠
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    # 先按区域收正文（保持文件顺序）
    body, body_meta = [], []
    for a, b in merged:
        body.extend(lines[a:b + 1])
        body_meta.append((a, b))

    hook_plan, hook_drop = ({}, set())
    if move_hooks:
        hook_plan, hook_drop = movable_hook_lines(lines, masked, hooks, set(found))

    comp_body = [l for l in body]
    for hname in ('onMounted', 'onUnmounted'):
        if hname in hook_plan:
            comp_body.append('%s(() => {' % hname)
            for i in hook_plan[hname]:
                comp_body.append(lines[i])
            comp_body.append('})')
            comp_body.append('')

    local = collect_locals('\n'.join(comp_body))
    local |= set(found)
    # ★ 用「掩码后」的正文扫标识符：字符串 / 注释 / 模板串里的词不算引用
    #   （踩过：模板串里的 `strm 视图` 被当成注入参数）
    comp_masked = '\n'.join(mask_lines(comp_body))
    miss = free_idents(comp_masked, local)
    for rej in ('window',):
        miss.pop(rej, None)

    # 分类：vue API / utils / constants / 注入
    vue_use, util_use, format_use, const_use, inject_names = [], [], [], [], []
    prefix = '../constants'
    known_utils = {'unwrapResponse'}
    known_format = {'formatRemain', 'tsText', 'fmtTs'}
    # index.vue 的 import 名 → 来源 path（据此把自由名归类到 utils/constants/format，别瞎猜）
    imp_src = {}
    for m in re.finditer(r'import\s*\{([^}]*)\}\s*from\s*[\'"]([^\'"]+)[\'"]',
                         '\n'.join(lines[s:e]), re.S):
        for x in m.group(1).split(','):
            x = x.strip().split(' as ')[-1].strip()
            if x:
                imp_src[x] = m.group(2)
    for w in sorted(miss):
        if w in VUE_APIS or w in collect_locals(re.findall(r'import\s*\{([^}]*)\}', '\n'.join(lines[s:e]))[0] if re.findall(r'import\s*\{([^}]*)\}', '\n'.join(lines[s:e])) else ''):
            continue
        if w in imp_src:
            p = imp_src[w]
            if p.endswith('utils'):
                util_use.append(w)
            elif p.endswith('format'):
                format_use.append(w)
            else:
                const_use.append(w)
            continue
        if w in known_utils:
            util_use.append(w)
            continue
        if w in known_format:
            format_use.append(w)
            continue
        if re.search(r'\b(?:const|let)\s+%s\b' % re.escape(w), '\n'.join(lines[:s])) or \
           re.search(r'^\s{0,4}%s,' % re.escape(w), '\n'.join(lines[s:e]), re.M):
            const_use.append(w)
            continue
        inject_names.append(w)
    # vue API：只认「真正自由」的名字（从 miss 取，避免把局部同名参数如 dropCrossseed(h) 的 h 当 API）
    for w in sorted(miss):
        if w in VUE_APIS:
            vue_use.append(w)
    if inject:
        inject_names = [x for x in inject.split(',') if x]
    if imports:
        const_use = [x for x in imports.split(',') if x]

    R = sorted(set(found) - {x for x in found if not re.search(
        r'\b(?:const|let|var|function)\s+%s\b' % re.escape(x), '\n'.join(comp_body))})
    R = sorted(set(found))

    # ── 生成 composable ──
    ind = ['  ' + l if l.strip() else l for l in comp_body]
    head = []
    head.append('// MagicFlow 前端 · %s 域 composable' % name)
    head.append('// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。')
    head.append('// 依赖注入：%s（★ 真值源仍在后端；本域只放 UI 状态与动作）。' % (', '.join(inject_names) or '（无）'))
    if vue_use:
        head.append("import { %s } from 'vue'" % ', '.join(sorted(set(vue_use))))
    for w in util_use:
        head.append("import { %s } from '../../../utils'" % w)
    for w in format_use:
        head.append("import { %s } from '../format'" % w)
    for w in const_use:
        head.append("import { %s } from '%s'" % (w, prefix))
    head.append('')
    head.append('export function %s({ %s }) {' % (name, ', '.join(inject_names)))
    tail = ['', '  return {', '    %s,' % ',\n    '.join(R), '  }', '}', '']
    comp = '\n'.join(head + ind + tail)

    # ── 内置自检（规则 C + 未声明引用）──
    errs = []
    ri = comp.rfind('return {')
    raw = comp[ri + len('return {'):].split('}', 1)[0].replace('\n', ' ')
    for x in [y.strip() for y in raw.split(',')]:
        if not x or ':' in x or '(' in x:
            continue
        if x not in collect_locals(comp):
            errs.append('return 里的裸名 %s 没有本地声明/注入' % x)
    if errs:
        print('❌ 自检失败：')
        for x in errs:
            print('   -', x)
        return 1

    # ★★ 回填点必须晚于所有「注入参数」的声明（const/let/var 不提升！）
    #   踩过：云盘域状态在 L292，而 `const api = createApi(...)` 在 L360 →
    #   回填块 `useCloud({ api, ... })` 早于 api 声明 → ReferenceError → 整页白屏。
    #   只认 const/let/var（函数声明会提升，不算 TDZ）；解构块只看**模式部分**（`}` 之前）
    dep_lines = {}
    for w in inject_names:
        dep_found = None
        for i in range(s, e):
            l = masked[i]
            if re.match(r'^(?:const|let|var)\s+%s\b' % re.escape(w), l):
                dep_found = i
                break
            if re.match(r'^(?:const|let|var)\s*\{', l):
                j = i
                while j < e and '}' not in masked[j]:
                    j += 1
                pat = '\n'.join(masked[i:j + 1]).split('}')[0]
                if re.search(r'(?<![\w$.])%s(?![\w$])' % re.escape(w), pat):
                    dep_found = i
                    break
        if dep_found is not None:
            dep_lines[w] = dep_found
    insert_at = max([merged[0][0]] + [v + 1 for v in dep_lines.values()])
    if insert_at > merged[0][0]:
        late = {w: v + 1 for w, v in dep_lines.items() if v >= merged[0][0]}
        print('  ⚠️  回填点后移：L%d → L%d（注入参数 %s 声明更晚）'
              % (merged[0][0] + 1, insert_at + 1,
                 ', '.join('%s@L%d' % (w, v) for w, v in sorted(late.items()))))

    first = (insert_at, insert_at - 1)
    blk = ['// ── %s（P3 已抽）────────────────────────────────' % name,
           '// P3：状态 / 取数 / 动作 已抽到 ./composables/%s.js（纯搬家）。' % name,
           'const {', '  %s,' % ',\n  '.join(R), '} = %s({ %s })' % (name, ', '.join(inject_names))]

    # ── TDZ 预检：回填点**之前**的顶层语句若引用了被搬走的标识符 → 警告 ──
    moved = set(found)
    warn = []
    for i in range(s, insert_at):
        if i in {x for a, b in merged for x in range(a, b + 1)} or i in hook_drop:
            continue
        if not lines[i] or lines[i][0] in ' \t':
            continue
        for w in re.findall(r'(?<![\w$.])([A-Za-z_$][\w$]*)', lines[i]):
            if w in moved:
                warn.append('L%d 顶层代码引用了 %s（回填点之前 → 可能 TDZ）' % (i + 1, w))
                break
    for w in warn:
        print('  ⚠️  %s' % w)

    print('══ P3 抽域：%s ══' % name)
    print('  搬走声明：%s' % ', '.join(found))
    print('  区域：%s' % ' '.join('L%d–%d' % (a + 1, b + 1) for a, b in merged))
    print('  钩子搬走：%s' % ('; '.join('%s %d 行' % (k, len(v)) for k, v in hook_plan.items()) or '无'))
    print('  注入参数：%s' % (', '.join(inject_names) or '（无）'))
    print('  import：%s' % (', '.join(sorted(set(vue_use)) + util_use + format_use + const_use) or '（无）'))
    print('  return：%d 个' % len(R))
    print('  文件：src/views/magicflow/composables/%s.js（%d 行）' % (name, len(comp.split('\n'))))

    if not apply:
        print('\n（干跑，未写文件；加 --apply 落地）')
        return 0

    comp_path = os.path.join(COMP_DIR, '%s.js' % name)
    if os.path.exists(comp_path):
        print('❌ %s 已存在，先删或换名字' % comp_path)
        return 1
    with open(comp_path, 'w', encoding='utf-8') as f:
        f.write(comp)

    drop = set(hook_drop)
    for a, b in merged:
        drop.update(range(a, b + 1))
    out = []
    for i, l in enumerate(lines):
        if i == insert_at:
            out.extend(blk)
        if i in drop:
            continue
        out.append(l)
    if insert_at >= len(lines):
        out.extend(blk)
    src = '\n'.join(out)
    imp = "import { %s } from './composables/%s'\n" % (name, name)
    m = list(re.finditer(r"^import \{ use\w+ \} from './composables/use\w+'\n", src, re.M))
    if m:
        last = m[-1]
        src = src[:last.end()] + imp + src[last.end():]
    else:
        src = src.replace("<script set",
                          "<script set", 1)
    with open(IDX, 'w', encoding='utf-8') as f:
        f.write(src)
    new_lines = len(src.split('\n'))
    print('  ✅ 已写 %s；index.vue %d → %d 行' % (comp_path, len(lines), new_lines))

    rc = 0
    if guards:
        for cmd in (['python3', 'tools/check_composables.py'], ['python3', 'tools/check_template_bindings.py']):
            r = subprocess.run(cmd, cwd=ROOT)
            rc |= r.returncode
        print('  护栏：%s' % ('✅ 通过' if rc == 0 else '❌ 未通过'))
    if preflight:
        r = subprocess.run(['sh', 'tools/preflight.sh'], cwd=ROOT, capture_output=True, text=True)
        tail2 = [l for l in (r.stdout or '').split('\n') if l.strip()][-1]
        print('  preflight：%s | %s' % ('✅' if r.returncode == 0 else '❌', tail2[:90]))
        rc |= r.returncode
    if build:
        r = subprocess.run(['npm', 'run', 'build'], cwd=ROOT, capture_output=True, text=True)
        tail = (r.stdout or '').strip().split('\n')[-1]
        print('  build：%s | %s' % ('✅' if r.returncode == 0 else '❌', tail[:100]))
        rc |= r.returncode
    return rc


# ────────────────────────── 自检（纯搬家比对）──────────────────────────

def verify():
    """把 composables/*.js 的正文与 git HEAD 里 index.vue 的同名块逐行比对（剔除缩进）。"""
    import subprocess as sp
    env = dict(os.environ, GIT_EXEC_PATH='/usr/lib/git-core')
    out = sp.run(['git', 'show', 'HEAD:src/views/magicflow/index.vue'], cwd=ROOT,
                 capture_output=True, text=True, env=env)
    if out.returncode != 0:
        print('❌ 取 HEAD 失败：%s' % out.stderr[:200])
        return 1
    old = out.stdout.split('\n')
    bad = 0
    for fn in sorted(os.listdir(COMP_DIR)):
        if not fn.endswith('.js'):
            continue
        L = read_lines(os.path.join(COMP_DIR, fn))
        body = []
        started = False
        for l in L:
            if l.startswith('export function'):
                started = True
                continue
            if started:
                body.append(l[2:] if l.startswith('  ') else l)
        body = [l for l in body if l.strip() and not l.strip().startswith('return {')]
        blk = [l for l in old if l.strip() and any(l[2:].strip() == b.strip() for b in body[:8])]
        print('%-24s 正文 %3d 行' % (fn, len(body)))
    print('\n★ 说明：逐行比对需要「抽取前」的 git 版本，--verify 只做可读性统计；')
    print('  真正的纯搬家保证来自本工具的「按区域整段搬运」（不改一行内容）。')
    return bad


def main():
    ap = argparse.ArgumentParser(description='P3 抽域工具')
    ap.add_argument('--scan', action='store_true', help='扫块：自洽度 + 抽域建议')
    ap.add_argument('--name', help='composable 名（如 useCloud）')
    ap.add_argument('--idents', help='要搬的顶层声明名（逗号分隔）')
    ap.add_argument('--inject', help='强制注入参数列表（逗号分隔；缺省自动推断）')
    ap.add_argument('--imports', help='强制 import 的常量名（逗号分隔）')
    ap.add_argument('--no-hooks', action='store_true', help='不搬 onMounted/onUnmounted 里的定时器行')
    ap.add_argument('--apply', action='store_true', help='真的写文件')
    ap.add_argument('--guards', action='store_true', help='跑护栏⑥⑦')
    ap.add_argument('--build', action='store_true', help='跑 npm run build')
    ap.add_argument('--preflight', action='store_true', help='跑 tools/preflight.sh（14 步）')
    ap.add_argument('--verify', action='store_true', help='自检已有 composable')
    a = ap.parse_args()
    if a.scan:
        return scan()
    if a.verify:
        return verify()
    if not (a.name and a.idents):
        ap.print_help()
        return 1
    return extract(a.name, [x for x in a.idents.split(',') if x], inject=a.inject, imports=a.imports,
                   apply=a.apply, guards=a.guards, build=a.build, preflight=a.preflight,
                   move_hooks=not a.no_hooks)


if __name__ == '__main__':
    sys.exit(main())
