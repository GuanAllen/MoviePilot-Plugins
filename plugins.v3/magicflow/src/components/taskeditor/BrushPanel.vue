<script setup>
// P6：从 TaskEditorDialog.vue 的「刷流运维」VWindowItem 内层整块抽出（纯搬家，零行为/样式改动）。
// 契约：props 下 / emit 上；v-model 用 defineModel。

const props = defineProps({
  uploadRateOptions: { type: Array, default: () => [] },
})

const brushSeedDays = defineModel('brushSeedDays')
const brushMinLeechers = defineModel('brushMinLeechers')
const rotateUploadGb = defineModel('rotateUploadGb')
const rotateRatio = defineModel('rotateRatio')
const exceptSubscribe = defineModel('exceptSubscribe')
const uploadMinKbps = defineModel('uploadMinKbps')
const uploadIdleMinutes = defineModel('uploadIdleMinutes')
const brushGraceMinutes = defineModel('brushGraceMinutes')
const maxAddPerRun = defineModel('maxAddPerRun')
const maxDownloadConcurrent = defineModel('maxDownloadConcurrent')
const topN = defineModel('topN')
const browsePages = defineModel('browsePages')
const refillWhenEmpty = defineModel('refillWhenEmpty')
const cleanupNoProgress = defineModel('cleanupNoProgress')
const cleanupSlowProgress = defineModel('cleanupSlowProgress')
const purgeUnfreeIncomplete = defineModel('purgeUnfreeIncomplete')
const autoResumePaused = defineModel('autoResumePaused')
const deleteFiles = defineModel('deleteFiles')
const deleteExceptTags = defineModel('deleteExceptTags')
const noProgressMinutes = defineModel('noProgressMinutes')
const seenCooldownHours = defineModel('seenCooldownHours')
const slowProgressGraceMinutes = defineModel('slowProgressGraceMinutes')
const slowProgressMaxHours = defineModel('slowProgressMaxHours')
</script>

<template>
  <VAlert type="info" variant="tonal" density="compact" class="mb-2" icon="mdi-upload-network-outline">
    刷流模式：<strong>按「上传潜力」运行，有自己的选种标准</strong> —— 只挑<strong>免费（含 2X免费）且有下载者</strong>的种，
    不设做种人数上限、体积/年龄不限（热门大种才是上传主力）；定期检查每个种子，
    <strong>做种满设定天数即清理换新的</strong>（默认 2 天）；没下完也算（只要在上传）。
  </VAlert>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">刷流轮换</div>
        <div class="text-body-2 text-medium-emphasis">做种满设定天数即清理换新（默认 2 天）</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="brushSeedDays"
          type="number"
          min="0"
          max="365"
          label="保种天数"
          hint="做种满该天数后清理换新；0 = 不按天数，改回「无上传」判定"
          suffix="天"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="brushMinLeechers"
          type="number"
          min="0"
          label="最小下载人数"
          hint="只挑下载人数≥该值的种（有下载需求才值得下）"
          persistent-hint
        />
      </VCol>
    </VRow>
    <VRow>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="rotateUploadGb"
          type="number"
          min="0"
          label="产出换新：单种上传量"
          hint="单种已上传达到该 GB 即清理换新；留空 = 不看上传量"
          suffix="GB"
          clearable
          persistent-hint
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="rotateRatio"
          type="number"
          min="0"
          step="0.1"
          label="产出换新：单种分享率"
          hint="单种分享率达到该值即清理换新；留空 = 不看分享率"
          clearable
          persistent-hint
        />
      </VCol>
    </VRow>
    <div class="editor-switches">
      <VSwitch v-model="exceptSubscribe" label="选种排除订阅命中（不抢主人要看的片）" color="primary" hide-details inset />
    </div>
  </section>

  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">无上传判定（保种天数 = 0 时启用）</div>
        <div class="text-body-2 text-medium-emphasis">保种天数填 0 时不按天数轮换，而是以「平均上传速率」为准清理换新</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="6">
        <VSelect
          v-model.number="uploadMinKbps"
          label="上传速率门槛"
          :items="uploadRateOptions"
          hint="窗口内平均上传速率低于该值 → 判「无上传」（连续若干次后删除）"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="uploadIdleMinutes"
          type="number"
          min="0"
          max="1440"
          label="清理时间（无上传判定时长）"
          hint="连续多少分钟低于速率门槛就清理（0 = 自动：约 2×检查间隔）"
          suffix="分钟"
          persistent-hint
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="brushGraceMinutes"
          type="number"
          min="0"
          max="1440"
          label="宽容时间（起步宽限）"
          hint="新种加入后多少分钟内不判「无上传」"
          suffix="分钟"
          persistent-hint
        />
      </VCol>
    </VRow>
  </section>

  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">抓取与并发</div>
        <div class="text-body-2 text-medium-emphasis">刷流只看最新页（免费热种在最新页），不深翻</div>
      </div>
    </header>
    <VRow>
      <VCol cols="12" md="6"><VTextField v-model.number="maxAddPerRun" type="number" min="1" label="单轮最多新增" placeholder="默认 10" suffix="个/轮" clearable /></VCol>
      <VCol cols="12" md="6"><VTextField v-model.number="maxDownloadConcurrent" type="number" min="1" label="同时下载上限" placeholder="默认 10" suffix="个" clearable /></VCol>
      <VCol cols="12" md="6"><VTextField v-model.number="topN" type="number" min="1" label="每轮参评候选数" placeholder="默认 30" suffix="个" clearable /></VCol>
      <VCol cols="12" md="6"><VTextField v-model.number="browsePages" type="number" min="1" max="60" label="每轮翻页数" placeholder="默认 3" suffix="页" clearable /></VCol>
    </VRow>
  </section>

  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">清理</div>
        <div class="text-body-2 text-medium-emphasis">做种满天数 / 促销失效 / 停滞的种子清理</div>
      </div>
    </header>
    <div class="editor-switches">
      <VSwitch v-model="refillWhenEmpty" label="清理后主动补种" color="primary" hide-details inset />
      <VSwitch v-model="cleanupNoProgress" label="清理无进度种子（停滞/出错且进度为 0）" color="primary" hide-details inset />
      <VSwitch v-model="cleanupSlowProgress" label="清理下载过慢的种子（长期下不完腾名额）" color="primary" hide-details inset />
      <VSwitch v-model="purgeUnfreeIncomplete" label="清理「已不再免费且未下完」的种子" color="primary" hide-details inset />
      <VSwitch v-model="autoResumePaused" label="自动恢复被暂停的已完成种子" color="primary" hide-details inset />
      <VSwitch v-model="deleteFiles" label="删种同时删除文件" color="primary" hide-details inset />
    </div>
    <VRow>
      <VCol cols="12">
        <VTextField
          v-model="deleteExceptTags"
          label="永不删除的标签（可选，逗号分隔）"
          hint="叠加在「已整理 / 辅种」之上：带这些标签的种子删种时永不删除"
          persistent-hint
          clearable
        />
      </VCol>
    </VRow>
    <VRow v-if="cleanupNoProgress">
      <VCol cols="12" md="6"><VTextField v-model.number="noProgressMinutes" type="number" min="1" label="无进度判定时长（分钟）" persistent-hint /></VCol>
      <VCol cols="12" md="6"><VTextField v-model.number="seenCooldownHours" type="number" min="0" label="已处理去重窗口（小时）" hint="同一候选在该时长内不重复拉取，0 = 不跳过" persistent-hint /></VCol>
    </VRow>
    <VRow v-if="cleanupSlowProgress">
      <VCol cols="12" md="6"><VTextField v-model.number="slowProgressGraceMinutes" type="number" min="1" label="慢种宽限（分钟）" persistent-hint /></VCol>
      <VCol cols="12" md="6"><VTextField v-model.number="slowProgressMaxHours" type="number" min="1" label="预计下完上限（小时）" persistent-hint /></VCol>
    </VRow>
  </section>
</template>

<style scoped>
/* 共享选择器（父保留一份）：搬进子作用域，保证 .editor-section 的间距/头部/开关排布不变。 */
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
