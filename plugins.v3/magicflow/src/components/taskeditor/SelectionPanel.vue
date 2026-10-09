<script setup>
// MagicFlow 前端 · 任务编辑器「选种规则」面板（P6）
// P6 拆分：自 components/TaskEditorDialog.vue 的
//   <VWindowItem v-if="!simpleMode" value="selection"> 内层内容 **纯搬家**
//   （template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// VWindowItem 外壳仍留在父（含 v-if="!simpleMode" value="selection"），内含本组件。

// 逐字段 v-model 下沉（父 localTask.<snake_case> → defineModel('<camelCase>')）
const freeleech = defineModel('freeleech')
const hr = defineModel('hr')
const size = defineModel('size')
const seeder = defineModel('seeder')
const pubtime = defineModel('pubtime')
const include = defineModel('include')
const exclude = defineModel('exclude')
const excludeZeroBonus = defineModel('excludeZeroBonus')

// 只读引用的父级计算值 → props
defineProps({
  isBrush: { type: Boolean, default: false },
})
</script>

<template>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">来源与促销</div>
        <div class="text-body-2 text-medium-emphasis">{{ isBrush ? '刷流只看站点最新页（免费热种在最新页），不做游标深翻' : '沿用站点列表页或 RSS 获取链路' }}</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="6">
        <VSelect
          v-if="isBrush"
          :model-value="'free'"
          label="促销"
          :items="[{ title: '免费（含 2X 免费）', value: 'free' }]"
          disabled
          hint="刷流固定只抓免费种（下载不计量），保障分享率"
          persistent-hint
        />
        <VSelect
          v-else
          v-model="freeleech"
          label="促销"
          :items="[
            { title: '免费', value: 'free' },
            { title: '2X 免费', value: '2xfree' },
          ]"
          hint="系统硬规则：只下免费种（非免费不碰）。「免费」含 2X 免费；选「2X 免费」= 只要双倍免费"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" md="6">
        <VSelect
          v-model="hr"
          label="排除 H&R"
          :items="[
            { title: '是', value: 'yes' },
            { title: '否', value: 'no' },
          ]"
        />
      </VCol>
    </VRow>
  </section>

  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">候选过滤</div>
        <div class="text-body-2 text-medium-emphasis">{{ isBrush ? '刷流默认不限人数 / 体积 / 年龄（留空即为不限），如需收敛再填；范围支持单值或「最小值-最大值」' : '范围字段支持单值或「最小值-最大值」' }}</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="4">
        <VTextField v-model="size" label="种子大小（GB）" placeholder="10-80" />
      </VCol>
      <VCol cols="12" md="4">
        <VTextField v-model="seeder" label="做种人数" placeholder="1-10" />
      </VCol>
      <VCol cols="12" md="4">
        <VTextField v-model="pubtime" label="发布时间（分钟）" placeholder="5-120" />
      </VCol>
      <VCol cols="12">
        <VTextField v-model="include" label="包含规则" placeholder="支持正则表达式" />
      </VCol>
      <VCol cols="12">
        <VTextField v-model="exclude" label="排除规则" placeholder="支持正则表达式" />
      </VCol>
    </VRow>
    <div class="editor-switches">
      <VSwitch
        v-if="!isBrush"
        v-model="excludeZeroBonus"
        label="不选零魔种子（Wi=0.2）"
        color="primary"
        hide-details
        inset
      />
    </div>
  </section>
</template>

<style scoped>
/* ── 面板专属选择器：无（本面板仅复用共享的 .editor-section / .editor-section__head / .editor-switches）。
     `.editor-section`、`.editor-section + .editor-section`、`.editor-section__head`、`.editor-switches`
     为**共享**选择器（父页其它面板也在用）→ 组件内复制一份，TaskEditorDialog.vue 原样保留。
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
