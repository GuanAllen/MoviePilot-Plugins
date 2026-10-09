<script setup>
// MagicFlow 前端 · 任务编辑器「高级」面板（P6）
// P6 拆分：自 components/TaskEditorDialog.vue 的
//   <VWindowItem v-if="!simpleMode" value="advanced"> 内层内容 **纯搬家**
//   （template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// VWindowItem 外壳仍留在父（含 v-if="!simpleMode" value="advanced"），内含本组件。

// 逐字段 v-model 下沉（父 localTask.<snake_case> → defineModel('<camelCase>')）
const crossseedEnabled = defineModel('crossseedEnabled')
const crossseedMaxPerRound = defineModel('crossseedMaxPerRound')
const crossseedMaxSizeGb = defineModel('crossseedMaxSizeGb')
const crossseedMaxSites = defineModel('crossseedMaxSites')
const upSpeed = defineModel('upSpeed')
const dlSpeed = defineModel('dlSpeed')

// 只读引用的父级计算值 / 字段 → props（下行；无横线上事件）
defineProps({
  siteName: { type: String, default: '' },
  scheduleText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
  downloader: { type: [String, Number], default: '' },
  activeTimeRange: { type: [String, Number], default: '' },
  goalValue: { type: [String, Number], default: null },
  hasGoal: { type: Boolean, default: false },
})
</script>

<template>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">跨站免费取种</div>
        <div class="text-body-2 text-medium-emphasis">
          本站这颗不免费（下了就烧流量、拉低分享率）→ 去任意他站找「免费且同一 Release」的副本下回来，下完自动辅回本站（零下载纯做种）
        </div>
      </div>
    </header>
    <div class="editor-switches">
      <VSwitch v-model="crossseedEnabled" label="启用跨站免费取种" color="primary" hide-details inset />
    </div>
    <VRow v-if="crossseedEnabled">
      <VCol cols="12" sm="4">
        <VTextField
          v-model.number="crossseedMaxPerRound"
          type="number"
          min="1"
          label="每轮跨站名额"
          hint="每一轮刷流最多发起几个跨站取种"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" sm="4">
        <VTextField
          v-model.number="crossseedMaxSizeGb"
          type="number"
          min="0.1"
          step="0.1"
          label="单种大小上限（GB）"
          hint="超过此体积的种子不做跨站取种"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" sm="4">
        <VTextField
          v-model.number="crossseedMaxSites"
          type="number"
          min="1"
          label="最多探测站点数"
          hint="每个候选最多查几个他站（越大越慢/越耗 PV）"
          persistent-hint
        />
      </VCol>
    </VRow>
  </section>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">单种限速</div>
        <div class="text-body-2 text-medium-emphasis">只作用于当前任务新添加的种子</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="6">
        <VTextField v-model.number="upSpeed" type="number" min="1" label="上传限速（KB/s）" hint="留空 = 用全局档位（设置 · 常规：魔力 / 刷流上传限速）" persistent-hint />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField v-model.number="dlSpeed" type="number" min="1" label="下载限速（KB/s）" hint="留空 = 用任务类型默认（魔力 1024 / 刷流全局档位）" persistent-hint />
      </VCol>
    </VRow>
  </section>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">生效预览</div>
        <div class="text-body-2 text-medium-emphasis">保存后立即写入调度，无需重启插件</div>
      </div>
    </header>
    <dl class="magicflow-facts magicflow-facts--two">
      <div><dt>站点</dt><dd>{{ siteName }}</dd></div>
      <div><dt>下载器</dt><dd>{{ downloader || '未选择' }}</dd></div>
      <div><dt>调度</dt><dd>{{ scheduleText }}</dd></div>
      <div><dt>开启时段</dt><dd>{{ activeTimeRange || '全天' }}</dd></div>
      <div>
        <dt>任务目标</dt>
        <dd>{{ hasGoal ? (isBrush ? `${goalValue} GB 上传量` : `${goalValue} 魔力值`) : '未设置' }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
/* ── 面板专属选择器（自 TaskEditorDialog.vue 第二个 <style scoped> 块整段迁入，父删）。
     .magicflow-facts* 在本弹窗里**仅「高级」面板的「生效预览」使用** → 属面板专属。
     父页删掉后，本组件 scope id 与原父不同 → 须自持一份。── */
.magicflow-facts {
  display: grid;
  gap: 11px;
  margin: 18px 0 0;
}
.magicflow-facts--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.magicflow-facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-inline-size: 0;
}
.magicflow-facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-facts dd {
  margin: 0;
  text-align: end;
  overflow-wrap: anywhere;
}

/* ── 共享选择器（父页其它面板也在用 → 组件内复制一份，TaskEditorDialog.vue 原样保留）。
     子组件 scope id 与父不同 → 父 scoped 够不到本组件渲染的元素，故须自持一份。── */
.editor-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-section + .editor-section {
  margin-block-start: 28px;
  padding-block-start: 24px;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.editor-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.editor-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}
</style>
