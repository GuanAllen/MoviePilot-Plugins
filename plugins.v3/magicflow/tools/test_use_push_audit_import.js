#!/usr/bin/env node
// 魔流 · 任务 105 / FE-01 回归测试（node，无依赖）
//
// 验证三件事（任一失败退出码 1）：
//   1. 源码 usePushAudit.js 显式 import 了 unwrapResponse（与全仓惯例同路径）；
//   2. 源码里所有 unwrapResponse 调用都由该 import 解析（不再有裸引用）；
//   3. 构建产物 chunk 里 unwrapResponse 由 import 绑定（可选：用 MF_DIST_CHUNK 指定）。
//
// 用法：
//   node tools/test_use_push_audit_import.js                       # 只测源码
//   MF_DIST_CHUNK=/tmp/out/assets/index-xxxx.js node tools/test_use_push_audit_import.js
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src/views/magicflow/composables/usePushAudit.js');
const IMPORT_RE = /import\s*\{\s*unwrapResponse\s*\}\s*from\s*'\.\.\/\.\.\/\.\.\/utils'/;

let fails = 0;
let cases = 0;
function ok(cond, name, detail = '') {
  cases += 1;
  if (cond) {
    console.log(`  ✅ ${name}`);
  } else {
    fails += 1;
    console.log(`  ❌ ${name}${detail ? ` —— ${detail}` : ''}`);
  }
}

console.log('── FE-01 源码：usePushAudit.js ──');
const src = readFileSync(SRC, 'utf8');
ok(IMPORT_RE.test(src), '显式 import unwrapResponse（../../../utils）');
const calls = (src.match(/\bunwrapResponse\s*\(/g) || []).length;
ok(calls > 0, `存在调用点（${calls} 处）`);
// 唯一 import 在文件头：去掉 import 行后不应再有定义/导入，只剩调用
const importLines = src.split('\n').filter((l) => /\bunwrapResponse\b/.test(l) && /^import\b/.test(l.trim()));
ok(importLines.length === 1, 'unwrapResponse 只由 1 行 import 引入', `实际 ${importLines.length} 行`);
const defined = /\b(?:const|let|var|function)\s+unwrapResponse\b/.test(src);
ok(!defined, '本地没有重复定义 unwrapResponse');

const chunk = process.env.MF_DIST_CHUNK || '';
if (chunk) {
  console.log(`── FE-01 构建产物：${chunk} ──`);
  const js = readFileSync(chunk, 'utf8');
  const bound = /as\s+unwrapResponse\b|\{\s*unwrapResponse\b/.test(js);
  ok(bound, '构建 chunk 的 import 绑定包含 unwrapResponse');
  const bare = (js.match(/(?:^|[^.\w$])unwrapResponse\s*\(/g) || []).length;
  ok(bare > 0, `构建后仍有调用点（${bare} 处，且已绑定）`);
  ok(!/unwrapResponse\$1/.test(js), '没有出现「同名别名」的分裂绑定（$1）');
} else {
  console.log('  · 未指定 MF_DIST_CHUNK，跳过构建产物断言');
}

console.log(`\n${fails ? '❌ FAIL' : '✅ PASS'} —— ${cases - fails}/${cases} 通过`);
process.exit(fails ? 1 : 0);
