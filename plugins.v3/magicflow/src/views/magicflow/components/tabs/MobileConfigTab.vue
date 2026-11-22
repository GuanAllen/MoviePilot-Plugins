<script setup>
// MagicFlow 前端 · 手机端任务配置 Tab（★ 19.15.0 视觉层重写，对齐 task-detail-design.html viewConfig）
// 手机端（≤959px）专用精简版：六格核心参数 + 站点卡 + 三操作按钮。
// 数据向下（props）、事件向上（emit）。只读派生值由父页 composable 计算后传入，不重复计算。
// （字段口径与桌面 TaskConfigTab 同源，此处只挑设计稿六格 + 站点 + 操作。）
defineProps({
  task: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  runMode: { type: Object, default: () => ({ text: '' }) },
  goalText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
  brushSeedDays: { type: Number, default: 0 },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'edit', 'delete'])
</script>

<template>
  <div class="magicflow-page">
    <div class="mob-cfg">
      <div class="mob-cfg__ttl">
        <h3>任务配置</h3>
        <small>当前服务端生效值</small>
      </div>

      <div class="cfg-grid">
        <div class="cfg">
          <span class="cfg__k">任务模式</span>
          <span class="cfg__v">{{ isBrush ? '刷流' : '刷魔力' }}</span>
        </div>
        <div class="cfg">
          <span class="cfg__k">{{ isBrush ? '轮转周期' : '最低魔力' }}</span>
          <span class="cfg__v">
            {{ isBrush
              ? (brushSeedDays > 0 ? `满 ${brushSeedDays} 天清` : '按无上传')
              : (config.min_bonus_per_hour == null ? '自动' : `${Number(config.min_bonus_per_hour).toFixed(1)}/h`) }}
          </span>
        </div>
        <div class="cfg">
          <span class="cfg__k">完美种保护</span>
          <span class="cfg__v">{{ config.protect_perfect === false ? '关' : '开' }}</span>
        </div>
        <div class="cfg">
          <span class="cfg__k">清理策略</span>
          <span class="cfg__v">{{ isBrush ? '做种满天数' : '满 30 天 · 低效淘汰' }}</span>
        </div>
        <div class="cfg">
          <span class="cfg__k">接管保护</span>
          <span class="cfg__v">{{ task.protected_count ? `${task.protected_count} 个` : '无' }}</span>
        </div>
        <div class="cfg">
          <span class="cfg__k">运行状态</span>
          <span class="cfg__v cfg__v--ac">{{ runMode.text || '—' }}</span>
        </div>
      </div>

      <div class="panelbox">
        <div class="ph"><b>站点</b><span>{{ task.site_name || task.site_domain || '未设置' }}</span></div>
        <div class="row"><span>任务目标</span><b>{{ goalText || '—' }}</b></div>
        <div class="row"><span>标签</span><b>{{ task.brush_tag || '未设置' }}</b></div>
        <div class="row">
          <span>绑定</span>
          <b>
            <span v-if="task.site_missing" class="pill">站点已删除</span>
            <span v-else class="ok">正常</span>
          </b>
        </div>
      </div>

      <div class="cfg-act">
        <button type="button" :disabled="saving" @click="emit('run')">
          <VIcon icon="mdi-sync" size="14" />立即执行
        </button>
        <button type="button" @click="emit('edit')">
          <VIcon icon="mdi-pencil-outline" size="14" />编辑任务
        </button>
        <button type="button" class="del" @click="emit('delete')">
          <VIcon icon="mdi-delete-outline" size="14" />删除任务
        </button>
      </div>

      <p class="cfg-note">
        任务按间隔自动运行；「立即执行」只是在下个间隔到来前插队跑一轮。存在活跃种子时后端会拒绝删除，避免失管任务。
      </p>
    </div>
  </div>
</template>

<style scoped>
/* ══════════════════════════════════════════════════════════════════════════════
   手机端任务配置（★ 19.15.0，视觉层按设计稿 viewConfig 整体重写）。
   设计稿口径：2 列 × 3 行参数格（9.5/12.5px 两级），站点事实表，三按钮同行等权。
   ══════════════════════════════════════════════════════════════════════════════ */
.mob-cfg {
  --line: rgba(255, 255, 255, 0.07);
  --dim: #6f7488;
  --sub: #8b90a3;
  --purple: #8b7cf6;
  --green: #3ddc97;
  --red: #ff6b7a;
  display: flex;
  flex-direction: column;
}

.mob-cfg__ttl { display: flex; align-items: baseline; justify-content: space-between; margin: 2px 0 10px; }
.mob-cfg__ttl h3 { font-size: 13px; font-weight: 700; }
.mob-cfg__ttl small { font-size: 10px; color: var(--dim); }

/* ── 参数六格：2 列（设计稿 cfggrid）── */
.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.cfg {
  min-width: 0;
  padding: 10px 11px;
  border-radius: 11px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
}
.cfg__k { display: block; font-size: 9.5px; color: var(--dim); }
.cfg__v { display: block; margin-top: 4px; font-size: 12.5px; font-weight: 700; color: #e8e9f0; line-height: 1.35; word-break: break-word; }
.cfg__v--ac { color: #cfc6ff; }

/* ── 事实表（设计稿 panelbox + row）── */
.panelbox {
  padding: 13px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  margin-bottom: 12px;
}
.ph { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.ph b { font-size: 12.5px; font-weight: 700; }
.ph span { font-size: 9.5px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  font-size: 11px; padding: 7px 0; color: #b9bdcf;
  border-top: 1px solid var(--line);
}
.row:first-of-type { border-top: 0; }
.row b { color: #e8e9f0; font-weight: 650; text-align: right; word-break: break-word; }
.ok { color: var(--green); }
.pill {
  display: inline-block; font-size: 9.5px; padding: 3px 8px; border-radius: 20px;
  background: rgba(255, 107, 122, 0.14); color: #ff9aa5;
  border: 1px solid rgba(255, 107, 122, 0.28);
}

/* ── 三按钮：同行等权，删除只靠颜色区分（设计稿 cfgact；无主按钮）── */
.cfg-act { display: flex; gap: 8px; margin-top: 4px; }
.cfg-act button {
  flex: 1;
  min-width: 0;
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  padding: 10px 4px;
  font-size: 11px; font-weight: 600;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.05);
  color: #c3c7d8;
  white-space: nowrap;
}
.cfg-act button:disabled { opacity: 0.55; }
.cfg-act button.del { color: #ff9aa5; border-color: rgba(255, 107, 122, 0.3); }

.cfg-note { margin-top: 10px; font-size: 9.5px; line-height: 1.6; color: var(--dim); }
</style>
