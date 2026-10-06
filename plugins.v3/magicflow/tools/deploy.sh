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
#   --no-preflight     跳过 preflight 自检
#   --no-market        不同步「监控源」目录
#   --no-container     不更新容器副本（只同步监控源 → 触发 monitor 自动安装）
#   --no-reload        不调用 reload API
#   --no-verify        不校验
#   --dry-run          只打印将要执行的动作
#   --symbols=a,b,c    校验容器内代码含这些符号（grep 命中文件数）
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

DO_PREFLIGHT=1; DO_MARKET=1; DO_CONTAINER=1; DO_RELOAD=1; DO_VERIFY=1; DRY=0
SYMBOLS=""
for a in "$@"; do
  case "$a" in
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

# 1) preflight
if [ "$DO_PREFLIGHT" = 1 ]; then
  echo "── 1) preflight ──"
  if [ "$DRY" = 1 ]; then echo "  (dry-run) sh tools/preflight.sh"; else sh "$DEV/tools/preflight.sh"; fi
fi

# 2) 同步监控源（monitor 会据此自动安装）
if [ "$DO_MARKET" = 1 ]; then
  echo "── 2) 同步监控源 → $MARKET_DIR ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) rsync -a --delete <excl> \"$DEV/\" \"$MARKET_DIR/\""
  else
    rsync -a --delete \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' \
      --exclude='.git' --exclude='docs' --exclude='preview' --exclude='screenshots' \
      --exclude='dist' \
      "$DEV/" "$MARKET_DIR/"
    if [ -d "$DEV/dist" ]; then
      rsync -a --delete "$DEV/dist/" "$MARKET_DIR/dist/"
      echo "  ▸ dist 已同步"
    fi
  fi
fi

# 3) 更新容器副本（tar 流过去，避开逐文件 docker cp）
if [ "$DO_CONTAINER" = 1 ]; then
  echo "── 3) 更新容器副本 → $CONTAINER:$CPATH ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) tar ... | docker exec -i $CONTAINER tar -C $CPATH -xf -"
  else
    tar -C "$DEV" \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' \
      --exclude='.git' --exclude='docs' --exclude='preview' --exclude='screenshots' \
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
  echo "── 4) reload 插件 ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) POST $API/reload/$PLUGIN"
  else
    docker exec "$CONTAINER" sh -c "curl -s -X POST '$API/reload/$PLUGIN?token=$TOK'"; echo
  fi
fi

# 5) 校验：/agent 版本 + 端点计数 + 容器内符号
if [ "$DO_VERIFY" = 1 ] && [ "$DRY" = 0 ]; then
  echo "── 5) 校验 ──"
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

echo "✅ 部署完成（版本 $VER）"
