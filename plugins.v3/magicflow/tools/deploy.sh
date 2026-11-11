#!/bin/sh
# 魔流 · 部署脚手架
# 把 dev 源码同步到「监控源 + 容器副本」，reload 插件，并校验版本/端点/符号。
#
# ── 用法（本机 trim.openclaw 的附加组不刷新，docker 必须走 sg）──
#   sg docker -c "sh tools/deploy.sh"
#   sg docker -c "sh tools/deploy.sh --symbols=_silent_pause_gate,__hr_host__"
#   sg docker -c "sh tools/deploy.sh --dry-run"
#
# ── 选项 ──
#   --no-build        不重建前端（默认会 npm run build）
#   --no-preflight    跳过 preflight 自检（preflight 前会自动重生成 MODULES-REGISTRY.md）
#   --no-market       不同步「监控源」目录
#   --no-container    不更新容器副本（只同步监控源 → 触发 monitor 自动安装）
#   --no-reload       不调用 reload API
#   --no-verify       不校验
#   --dry-run         只打印将要执行的动作
#   --symbols=a,b,c   校验容器内代码含这些符号（grep 命中文件数）
#   --prune-dist      真删 dist 里的旧哈希构建产物（默认只报告，见 tools/prune_dist_orphans.py）
#   --no-prune-dist   跳过这项检查
#
# ── 三个部署点（与 TOOLS.md 一致）──
#   ① 监控源（改这里 monitor 会自动装）: $MARKET_DIR
#   ② 本地市场索引（发版才动，本脚本不动）: $MARKET_INDEX
#   ③ 容器内副本（非挂载，需 docker cp/tar）: $CONTAINER:$CPATH
set -eu

DEV="$(cd "$(dirname "$0")/.." && pwd)"
MARKET_DIR="/vol1/1000/moviepilot/core/local-plugins/plugins.v3/magicflow"
MARKET_INDEX="/vol1/1000/moviepilot/core/local-plugins/package.v3.json"
CONTAINER="moviepilot-v3"
CPATH="/app/app/plugins/magicflow"
PLUGIN="MagicFlow"
API="http://127.0.0.1:3000/api/v1/plugin"

DO_BUILD=1; DO_PREFLIGHT=1; DO_MARKET=1; DO_CONTAINER=1; DO_RELOAD=1; DO_VERIFY=1; DRY=0
DO_PRUNE=1   # 1=只报告  2=真删  0=跳过
SYMBOLS=""
for a in "$@"; do
  case "$a" in
    --prune-dist) DO_PRUNE=2;;
    --no-prune-dist) DO_PRUNE=0;;
    --no-build) DO_BUILD=0;;
    --no-preflight) DO_PREFLIGHT=0;;
    --no-market) DO_MARKET=0;;
    --no-container) DO_CONTAINER=0;;
    --no-reload) DO_RELOAD=0;;
    --no-verify) DO_VERIFY=0;;
    --dry-run) DRY=1;;
    --symbols=*) SYMBOLS="${a#--symbols=}";;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) echo "未知参数: $a" >&2; exit 2;;
  esac
done

VER="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$DEV/common.py" | head -1)"
echo "══ 魔流部署 ══ 版本=$VER  dry_run=$DRY"

# 0) docker 可用性（提前失败，别改一半）
if [ "$DO_CONTAINER" = 1 ] && [ "$DRY" = 0 ]; then
  if ! docker info >/dev/null 2>&1; then
    echo "✖ 无法访问 docker —— 请用: sg docker -c \"sh tools/deploy.sh\"" >&2
    exit 3
  fi
fi

# 1) 前端构建（★ 2026-10-06：dist 之前从不重建 → 部署的 UI 是旧的）
#    源码 src/ 改动必须 vite build 才会进 dist/，而 dist/ 才是真正部署的产物。
if [ "$DO_BUILD" = 1 ]; then
  echo "── 1) 前端构建（vite build）──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) npm run build"
  elif [ ! -d "$DEV/node_modules" ]; then
    # ★ 护栏：无 node_modules 时 vite 必然启动失败，但 vite 会在启动阶段先清空 dist/。
    #   直接跑等于「先删 UI 再报错」，所以这里必须先拦住。
    if [ -f "$DEV/dist/index.html" ]; then
      echo "  ⚠ 无 node_modules，跳过构建，沿用现有 dist"
    else
      echo "  ✖ 无 node_modules 且无 dist —— 前端资源无从产生，中止部署" >&2
      exit 4
    fi
  else
    ( cd "$DEV" && npm run build 2>&1 | tail -3 )
    if [ ! -f "$DEV/dist/index.html" ]; then
      echo "  ✖ 前端构建失败：$DEV/dist/index.html 不存在，中止部署" >&2
      exit 4
    fi
    echo "  ▸ dist 已重建"
  fi
fi

# 2) preflight（★ 先自动重生成模块登记，避免手忘导致 preflight --check 失败）
if [ "$DO_PREFLIGHT" = 1 ]; then
  echo "── 2) preflight ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) python3 tools/gen_modules.py"
    echo "  (dry-run) python3 tools/gen_modules.py --check"
    echo "  (dry-run) sh tools/preflight.sh"
  else
    # ★ 发布路径保留严格口径（任务 110）：开发态 preflight 用 --check-modules
    #   （允许行数/职责漂移），但发布前必须先重生成，再逐字节 --check。
    ( cd "$DEV" && python3 tools/gen_modules.py >/dev/null ) \
      && ( cd "$DEV" && python3 tools/gen_modules.py --check >/dev/null ) \
      && echo "  ▸ 模块登记 已重生成（严格校验通过）" \
      && sh "$DEV/tools/preflight.sh"
  fi
fi

# 2) 同步监控源（monitor 会据此自动安装）
#    ★ 2026-11-09：排除 _dev_live —— 它是开发期审计/证据目录（含 root 属主文件），
#      一并 rsync 会让部署在非 root 用户下因 Permission denied 直接 rc=23 中止；
#      且它本就不属于插件产物。--delete 仍会清掉监控源里历史残留的同名目录。
if [ "$DO_MARKET" = 1 ]; then
  echo "── 3) 同步监控源 → $MARKET_DIR ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) rsync -a --delete <excl> \"$DEV/\" \"$MARKET_DIR/\""
  else
    rsync -a --delete \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' \
      --exclude='.git' --exclude='docs' --exclude='preview' --exclude='screenshots' \
      --exclude='.worktrees' --exclude='_dev_live' \
      --exclude='dist' --exclude='backups' \
      "$DEV/" "$MARKET_DIR/"
    if [ -f "$DEV/dist/index.html" ]; then
      rsync -a --delete "$DEV/dist/" "$MARKET_DIR/dist/"
      echo "  ▸ dist 已同步"
    else
      echo "  ⚠ 源 dist 缺失（$DEV/dist/index.html），跳过 dist 同步"
    fi
  fi
fi

# 3) 更新容器副本
#    ★ 2026-10-27 关键修正：本环境的 $CPATH 与 $DEV 是同一个 bind mount
#      （/vol1/1000/moviepilot/plugins-local/magicflow → /app/app/plugins/magicflow）。
#      旧写法 "docker exec rm -rf $CPATH/dist" 删掉的其实是宿主的 $DEV/dist，
#      紧接着 "tar -C $DEV ." 打包时 dist 已不存在 → 每部署一次必丢一次前端，页面白屏。
#      现在先探测挂载：已挂载则源码即容器副本，整个同步步骤跳过。
if [ "$DO_CONTAINER" = 1 ]; then
  echo "── 4) 更新容器副本 → $CONTAINER:$CPATH ──"
  MOUNTED=0
  if [ "$DRY" = 0 ]; then
    if docker inspect -f '{{range .Mounts}}{{.Source}}=>{{.Destination}}{{"\n"}}{{end}}' "$CONTAINER" 2>/dev/null \
         | tr -d '\r' | grep -qx "$DEV=>$CPATH"; then
      MOUNTED=1
    fi
  fi
  if [ "$MOUNTED" = 1 ]; then
    echo "  ▸ 已绑定挂载（$DEV => $CPATH）"
    echo "  ▸ 源码即容器副本，跳过同步（同步会自删 dist）"
  elif [ "$DRY" = 1 ]; then
    echo "  (dry-run) tar ... | docker exec -i $CONTAINER tar -C $CPATH -xf -"
  else
    # 非挂载场景：容器内是独立副本，才需要先清 dist 再整目录覆盖。
    if [ -f "$DEV/dist/index.html" ]; then
      docker exec "$CONTAINER" sh -c "rm -rf $CPATH/dist" >/dev/null 2>&1 || true
    else
      echo "  ⚠ 源 dist 缺失，保留容器内旧 dist"
    fi
    tar -C "$DEV" \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' \
      --exclude='.git' --exclude='docs' --exclude='preview' --exclude='screenshots' \
      --exclude='.worktrees' --exclude='backups' --exclude='_dev_live' \
      -cf - . | docker exec -i "$CONTAINER" tar -C "$CPATH" -xf -
    echo "  ▸ 容器副本已更新"
  fi
fi

# 4) reload（token 取自容器 /config/app.env 的 API_TOKEN）
TOK=""
if [ "$DO_RELOAD" = 1 ] && [ "$DRY" = 0 ]; then
  TOK="$(docker exec "$CONTAINER" sh -c 'grep -aE "^API_TOKEN" /config/app.env | head -1 | cut -d= -f2-' \
        | tr -d '\r\n' | sed "s/^[\"']//; s/[\"']\$//")"
fi
if [ "$DO_RELOAD" = 1 ]; then
  echo "── 5) reload 插件 ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) POST $API/reload/$PLUGIN"
  else
    docker exec "$CONTAINER" sh -c "curl -s -X POST '$API/reload/$PLUGIN?token=$TOK'"; echo
  fi
fi

# 5) 校验：/agent 版本 + 端点计数 + 容器内符号
if [ "$DO_VERIFY" = 1 ] && [ "$DRY" = 0 ]; then
  echo "── 6) 校验 ──"
  sleep 2
  docker exec "$CONTAINER" sh -c "curl -s '$API/$PLUGIN/agent?token=$TOK'" > /tmp/mf_agent.json 2>/dev/null || true
  VER="$VER" python3 - <<'PY'
import json, os, sys
want = os.environ.get("VER", "")
try:
    d = json.load(open("/tmp/mf_agent.json"))
except Exception as e:
    print("  ⚠ /agent 解析失败:", e); sys.exit(0)
data = d.get("data", d) if isinstance(d, dict) else {}
got = data.get("plugin_version") or data.get("version")
eps = data.get("endpoints")
print("  端点清单 plugin_version=%s endpoints=%s" % (got, len(eps) if isinstance(eps, list) else eps))
if want and got and got != want:
    print("  ✖ 版本不符：期望 %s，实际 %s" % (want, got)); sys.exit(1)
if got == want:
    print("  ✅ 版本匹配 %s" % want)
PY
  for sym in $(echo "$SYMBOLS" | tr ',' ' '); do
    [ -z "$sym" ] && continue
    n="$(docker exec "$CONTAINER" sh -c "grep -rl -- '$sym' $CPATH --include='*.py' 2>/dev/null | wc -l" | tr -d ' ')"
    echo "  ▸ 符号 $sym → $n 个文件命中"
  done
  rm -f /tmp/mf_agent.json
fi

# 7) dist 旧构建残留（vite 每次构建都出新哈希文件名，旧的不自动消失）
#    --no-market 时 dist 不同步，这项就没意义，直接跳过。
if [ "$DO_PRUNE" != 0 ] && [ "$DO_MARKET" = 1 ] && [ "$DRY" = 0 ] && [ -d "$MARKET_DIR/dist" ]; then
  echo "── 7) dist 旧构建残留 ──"
  PRUNE_ARG=""
  [ "$DO_PRUNE" = 2 ] && PRUNE_ARG="--prune"
  # 非致命：清不掉不该让整次部署判失败
  python3 "$DEV/tools/prune_dist_orphans.py" --local \
    --dest "$MARKET_DIR/dist" --local-src "$DEV/dist" $PRUNE_ARG || true
fi

echo "✅ 部署完成（版本 $VER）"
