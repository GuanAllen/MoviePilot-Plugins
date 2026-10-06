#!/bin/sh
# 12.6.0 一次性收尾：plugindata 里「缓存 / 日志」类旧键已全部搬进热层（TierCache），
# 这里把残留的 kv 行删掉，让 kv 只剩「设置 / 凭证」。
#
# ★ 数据安全（Master 16:07 红线）：默认干跑；--apply 才真删；删前把命中行**原样**备份成 0600。
# 用法： sg docker -c "sh tools/cleanup_kv_cache_1260.sh"          # 干跑
#        sg docker -c "sh tools/cleanup_kv_cache_1260.sh --apply"  # 真删（先自动备份）
set -e

APPLY=0
[ "$1" = "--apply" ] && APPLY=1

KEYS="'collect_day','crossseed_pending','douban_rating_cache','eventlog_v1','fallback_report','iyuu_cache','live_samples','reseed_cloud','reseed_day','trend_v1'"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/config/plugins/MagicFlow/legacy_kv_cache_backup_${STAMP}.json"

psql_t() {  # psql_t "<sql>"  → 单列纯文本
  sg docker -c "docker exec moviepilot-postgres psql -U moviepilot -d moviepilot -tAc \"$1\""
}

echo "── 命中行（plugin_id=MagicFlow）──"
psql_t "select key || ' = ' || length(value::text) || 'B' from plugindata where plugin_id='MagicFlow' and key in ($KEYS) order by key"

if [ "$APPLY" != "1" ]; then
  echo "(dry-run) 未删任何东西；加 --apply 执行（备份将写 $OUT）"
  exit 0
fi

echo "── 备份 → $OUT (0600) ──"
JSON=$(psql_t "select coalesce(json_object_agg(key, value)::text,'{}') from plugindata where plugin_id='MagicFlow' and key in ($KEYS)")
printf '%s' "$JSON" | sg docker -c "docker exec -i moviepilot-v3 sh -lc 'umask 077; cat > \"$OUT\"; chmod 600 \"$OUT\"; wc -c < \"$OUT\"'"

echo "── 删除 ──"
psql_t "delete from plugindata where plugin_id='MagicFlow' and key in ($KEYS)"
echo "── 剩余 kv 键 ──"
psql_t "select key from plugindata where plugin_id='MagicFlow' order by key"
