#!/bin/sh
# 魔流发布 worker：宿主轮询 .publish-request -> 跑 tools/deploy.sh -> 写 .publish-result
# 由 crontab 每 30 秒调用一次。
set -u
REPO=/vol1/@apphome/trim.openclaw/data/workspace/magicflow
REQ="$REPO/.publish-request"
RES="$REPO/.publish-result"
LOCK=/tmp/mf_publish.lock

[ -f "$REQ" ] || exit 0

# 防止上一轮还在跑
if ! mkdir "$LOCK" 2>/dev/null; then exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

NOTE=$(cat "$REQ")
# 先改名再处理，避免同一请求被重复消费
PROC="$REPO/.publish-processing"
mv "$REQ" "$PROC" 2>/dev/null || exit 0

START=$(date +%s)
bash -c "cd $REPO && PYTHONPYCACHEPREFIX=/tmp/pyc sh tools/deploy.sh --no-build" > /tmp/mf_publish_run.log 2>&1
RC=$?
END=$(date +%s)

# 取部署后容器内版本
VER=$(docker exec moviepilot-v3 grep -m1 __version__ /app/app/plugins/magicflow/common.py 2>/dev/null | sed 's/.*= *"//; s/".*//')

python3 - "$PROC" "$RES" "$RC" "$START" "$END" "$VER" <<PYEOF
import json, sys, time
proc, res, rc, start, end, ver = sys.argv[1:7]
try:
    req = json.load(open(proc, encoding="utf-8"))
except Exception:
    req = {}
log = ""
try:
    log = open("/tmp/mf_publish_run.log", encoding="utf-8", errors="ignore").read()[-3000:]
except Exception:
    pass
ok = (rc == "0")
out = {"ok": ok, "rc": int(rc), "request": req, "version": ver or None,
       "seconds": int(end) - int(start), "finished_at": time.time(),
       "log_tail": log}
json.dump(out, open(res, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(0 if ok else 1)
PYEOF

rm -f "$PROC"
