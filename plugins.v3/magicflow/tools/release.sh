#!/bin/sh
# 魔流 · 发版脚手架
# 一次做完：版本一致性 → 本地市场索引 → 公共市场仓 → 私有备份仓 → 留痕检查。
#
# ── 用法 ──
#   sh tools/release.sh --note="11.11.0：静默池重设计（全 paused 硬不变量 + H&R 宿主拆分）"
#   sh tools/release.sh --version=11.11.0 --note="..." [--no-push]
#   sh tools/release.sh --dry-run --note="..."
#
# ── 选项 ──
#   --version X      指定版本（默认读 package.json）；会把 common.py/package.json/市场索引强制同步到 X
#   --note=...     history / commit 说明（缺省会告警并写占位；★ 必须带 =，空格形式会报「未知参数」）
#   --no-push        只提交不推送
#   --skip-public    跳过公共市场仓
#   --skip-private   跳过私有备份仓
#   --dry-run        只打印，不改任何东西
#
# ── 三个发版点 ──
#   ① 本地市场索引（最容易漏）: $INDEX
#   ② 公共市场仓: $PUB  （plugins.v3/magicflow + package.v3.json）
#   ③ 私有备份仓: $DEV   （dev 目录本身是 git 仓）
set -eu

DEV="$(cd "$(dirname "$0")/.." && pwd)"
INDEX="/vol1/1000/moviepilot/core/local-plugins/package.v3.json"
PUB="/vol1/@apphome/trim.openclaw/data/workspace/moviepilot-plugins-git"
GE="/usr/lib/git-core"
GITC="git -C"

VER=""; NOTE=""; DO_PUSH=1; DO_PUB=1; DO_PRIV=1; DRY=0
for a in "$@"; do
  case "$a" in
    --version=*) VER="${a#--version=}";;
    --note=*) NOTE="${a#--note=}";;
    --no-push) DO_PUSH=0;;
    --skip-public) DO_PUB=0;;
    --skip-private) DO_PRIV=0;;
    --dry-run) DRY=1;;
    -h|--help) sed -n '2,24p' "$0"; exit 0;;
    *) echo "未知参数: $a" >&2; exit 2;;
  esac
done

[ -z "$VER" ] && VER="$(python3 -c "import json;print(json.load(open('$DEV/package.json'))['version'])")"
[ -z "$NOTE" ] && { NOTE="$VER 发版"; echo "⚠ 未给 --note，使用占位：$NOTE"; }

echo "══ 魔流发版 ══ 版本=$VER  push=$DO_PUSH  公共仓=$DO_PUB  私有仓=$DO_PRIV  dry_run=$DRY"
echo "   note: $NOTE"

# 环境刷 docker 组（保证 ssh/git 正常）
unset GIT_DIR GIT_WORK_TREE 2>/dev/null || true

# ── 0) 版本一致性：common.py + package.json 强制 = VER ──
sync_version() {
  f="$DEV/common.py"; cur="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$f" | head -1)"
  if [ "$cur" != "$VER" ]; then
    echo "  ▸ common.py __version__ $cur → $VER"
    [ "$DRY" = 1 ] || sed -i "s/^__version__ *= *\".*\"/__version__ = \"$VER\"/" "$f"
  fi
  pv="$(python3 -c "import json;print(json.load(open('$DEV/package.json'))['version'])")"
  if [ "$pv" != "$VER" ]; then
    echo "  ▸ package.json version $pv → $VER"
    [ "$DRY" = 1 ] || python3 - "$DEV/package.json" "$VER" <<'PY'
import json,sys
p,v=sys.argv[1],sys.argv[2]
d=json.load(open(p)); d["version"]=v
json.dump(d,open(p,"w"),ensure_ascii=False,indent=4); open(p,'a').write("\n")
PY
  fi
}
echo "── 1) 版本一致性 ──"; sync_version

# ── 2) 本地市场索引 ──
echo "── 2) 本地市场索引 → $INDEX ──"
if [ "$DRY" = 1 ]; then
  echo "  (dry-run) MagicFlow.version=$VER, history[$VER]=note, 顶层 version=$VER"
else
  VER="$VER" NOTE="$NOTE" INDEX="$INDEX" python3 - <<'PY'
import json,os
p=os.environ["INDEX"]; ver=os.environ["VER"]; note=os.environ["NOTE"]
d=json.load(open(p))
mf=d.setdefault("MagicFlow",{})
old=mf.get("version")
mf["version"]=ver
mf.setdefault("history",{})[ver]=note
d["version"]=ver
json.dump(d,open(p,"w"),ensure_ascii=False,indent=4); open(p,'a').write("\n")
print("  ▸ MagicFlow.version %s → %s（history 新增，现 %d 条）" % (old, ver, len(mf["history"])))
PY
fi

# ── 3) 公共市场仓 ──
if [ "$DO_PUB" = 1 ]; then
  echo "── 3) 公共市场仓 → $PUB ──"
  if [ ! -d "$PUB/.git" ]; then echo "✖ 公共仓克隆不存在: $PUB" >&2; exit 4; fi
  base="$(GIT_EXEC_PATH=$GE git -C "$PUB" rev-parse HEAD)"
  remote="$(GIT_EXEC_PATH=$GE git -C "$PUB" ls-remote origin refs/heads/main 2>/dev/null | cut -f1)"
  if [ -n "$remote" ] && [ "$remote" != "$base" ]; then
    echo "✖ 公共仓远程 HEAD($remote) ≠ 本地 HEAD($base)：可能分叉，拒绝推送（请手工处理）" >&2; exit 5
  fi
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) cp 索引→仓 package.v3.json；rsync dev/ → plugins.v3/magicflow/；commit+push"
  else
    cp "$INDEX" "$PUB/package.v3.json"
    rsync -a --delete \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' \
      --exclude='.git' --exclude='docs' --exclude='preview' --exclude='screenshots' \
      "$DEV/" "$PUB/plugins.v3/magicflow/"
    GIT_EXEC_PATH=$GE git -C "$PUB" -c user.name=IronOx -c user.email=guanallen@users.noreply.github.com add -A
    GIT_EXEC_PATH=$GE git -C "$PUB" -c user.name=IronOx -c user.email=guanallen@users.noreply.github.com commit -q -m "magicflow $VER: $NOTE" || echo "  (公共仓无改动)"
    if [ "$DO_PUSH" = 1 ]; then
      GIT_EXEC_PATH=$GE git -C "$PUB" push -q origin main && echo "  ▸ 公共仓已推送 $(GIT_EXEC_PATH=$GE git -C "$PUB" rev-parse --short HEAD)"
    fi
  fi
fi

# ── 4) 私有备份仓（dev）──
if [ "$DO_PRIV" = 1 ]; then
  echo "── 4) 私有备份仓 → $DEV ──"
  if [ "$DRY" = 1 ]; then
    echo "  (dry-run) git add -A；commit -m \"$VER ...\"；push origin main"
  else
    GIT_EXEC_PATH=$GE git -C "$DEV" -c user.name=IronOx -c user.email=guanallen@users.noreply.github.com add -A
    GIT_EXEC_PATH=$GE git -C "$DEV" -c user.name=IronOx -c user.email=guanallen@users.noreply.github.com commit -q -m "$VER: $NOTE" || echo "  (私有仓无改动)"
    if [ "$DO_PUSH" = 1 ]; then
      GIT_EXEC_PATH=$GE git -C "$DEV" push -q origin main && echo "  ▸ 私有仓已推送 $(GIT_EXEC_PATH=$GE git -C "$DEV" rev-parse --short HEAD)"
    fi
  fi
fi

# ── 5) 留痕检查 ──
echo "── 5) 留痕检查 ──"
if grep -q "$VER" "$DEV/docs/DESIGN-CURRENT.md" 2>/dev/null; then
  echo "  ✅ docs/DESIGN-CURRENT.md 已含 $VER"
else
  echo "  ⚠ docs/DESIGN-CURRENT.md §8 未含 $VER —— 记得补发版留痕"
fi

echo "✅ 发版完成（$VER）"
