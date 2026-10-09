<script setup>
// MagicFlow 前端 · 任务编辑器「魔力托管」面板（P6 拆分）
// 自 components/TaskEditorDialog.vue 的 <VWindowItem value="magic"> **纯搬家**
//（内层 template + 面板专属样式，零行为/样式变更）。
// 数据向下（defineModel）、事件向上：面板内不引用父级计算值，也不调父级动作 → 无 props / 无 emit。
const minBonusPerHour = defineModel('minBonusPerHour')
const diskSizeGb = defineModel('diskSizeGb')
const maxKeepTorrents = defineModel('maxKeepTorrents')
const maxAddPerRun = defineModel('maxAddPerRun')
const maxDownloadConcurrent = defineModel('maxDownloadConcurrent')
const topN = defineModel('topN')
const browsePages = defineModel('browsePages')
const bonusProtectThreshold = defineModel('bonusProtectThreshold')
const minBonusToKeep = defineModel('minBonusToKeep')
const refillWhenEmpty = defineModel('refillWhenEmpty')
const cleanupNoProgress = defineModel('cleanupNoProgress')
const cleanupSlowProgress = defineModel('cleanupSlowProgress')
const purgeUnfreeIncomplete = defineModel('purgeUnfreeIncomplete')
const autoResumePaused = defineModel('autoResumePaused')
const tiSource = defineModel('tiSource')
const noProgressMinutes = defineModel('noProgressMinutes')
const seenCooldownHours = defineModel('seenCooldownHours')
const slowProgressGraceMinutes = defineModel('slowProgressGraceMinutes')
const slowProgressMaxHours = defineModel('slowProgressMaxHours')
const minSeedTime = defineModel('minSeedTime')
const minRatio = defineModel('minRatio')
const deleteFiles = defineModel('deleteFiles')
const deleteExceptTags = defineModel('deleteExceptTags')
const protectPerfect = defineModel('protectPerfect')
const perfectMaxSeeders = defineModel('perfectMaxSeeders')
const perfectMinWeeks = defineModel('perfectMinWeeks')
</script>

<template>
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">魔力门槛（留空 = 自动）</div>
                    <div class="text-body-2 text-medium-emphasis">留空由公式与实时数据自动推算，手填即覆盖</div>
                  </div>
                  <VChip size="small" color="primary" variant="tonal">可自动</VChip>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="minBonusPerHour"
                      type="number"
                      min="0"
                      step="0.01"
                      label="每小时最低魔力"
                      placeholder="留空 = 种子魔力中位数 × 0.5"
                      suffix="/h"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="diskSizeGb"
                      type="number"
                      min="0"
                      step="10"
                      label="保种体积上限"
                      placeholder="留空 = 不限"
                      suffix="GB"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="maxKeepTorrents"
                      type="number"
                      min="1"
                      label="最多保留种子数（覆盖站点上限）"
                      placeholder="留空 = 按站点上限 → 保种体积 ÷ 平均种子大小"
                      hint="站点上限来自「设置 · 站点规则」；此处只覆盖当前任务"
                      persistent-hint
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="maxAddPerRun"
                      type="number"
                      min="1"
                      label="单轮最多新增"
                      placeholder="默认 10"
                      suffix="个/轮"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="maxDownloadConcurrent"
                      type="number"
                      min="1"
                      label="同时下载上限"
                      placeholder="默认 10"
                      suffix="个"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="topN"
                      type="number"
                      min="1"
                      label="每轮参评候选数"
                      placeholder="默认 30"
                      suffix="个"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="browsePages"
                      type="number"
                      min="1"
                      max="60"
                      label="每轮翻页数"
                      placeholder="默认 3"
                      suffix="页"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="bonusProtectThreshold"
                      type="number"
                      min="0"
                      label="魔力保护阈值"
                      placeholder="留空 = 站点当前魔力"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="minBonusToKeep"
                      type="number"
                      min="0"
                      label="最低魔力保底值"
                      placeholder="留空 = 0（不设保底）"
                      clearable
                      :rules="[
                        value =>
                          Number(value || 0) < Number(bonusProtectThreshold || 999999999) ||
                          '最低魔力保底值应小于魔力保护阈值',
                      ]"
                    />
                  </VCol>
                </VRow>
                <div class="editor-switches">
                  <VSwitch v-model="refillWhenEmpty" label="清理后主动补种" color="primary" hide-details inset />
                  <VSwitch
                    v-model="cleanupNoProgress"
                    label="每次运行清理无进度种子（停滞/出错且进度为 0）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="cleanupSlowProgress"
                    label="清理下载过慢的种子（速度÷体积算 ETA，长期下不完的腾名额）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="purgeUnfreeIncomplete"
                    label="检查时清理「已不再免费且未下完」的种子（回站点核对促销）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="autoResumePaused"
                    label="自动恢复被暂停的已完成种子（重新做种）"
                    color="primary"
                    hide-details
                    inset
                  />
                </div>
                <VRow>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="tiSource"
                      :items="[
                        { title: '发布时长（站点公式口径，推荐）', value: 'publish' },
                        { title: '做种时长（qB 统计）', value: 'seed_time' },
                      ]"
                      label="Ti 口径（做种时间因子）"
                      hint="候选排序与做种汇总使用同一口径；取不到发布时间时自动回落做种时长"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
                <VRow v-if="cleanupNoProgress">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="noProgressMinutes"
                      type="number"
                      min="1"
                      label="无进度判定时长（分钟）"
                      hint="加入下载器超过该时长仍无进度才清理"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="seenCooldownHours"
                      type="number"
                      min="0"
                      label="已处理去重窗口（小时）"
                      hint="同一候选在该时长内不重复拉取，0 = 不跳过"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
                <VRow v-if="cleanupSlowProgress">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="slowProgressGraceMinutes"
                      type="number"
                      min="1"
                      label="慢种宽限（分钟）"
                      hint="种子加入后该时长内不判「慢」，给新种起步时间"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="slowProgressMaxHours"
                      type="number"
                      min="1"
                      label="预计下完上限（小时）"
                      hint="按当前速度（速度÷体积）预计还要超过该小时数才下完 → 清理"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">删种保护</div>
                    <div class="text-body-2 text-medium-emphasis">保护期内、受保护与 H&R 种子永不删除</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="minSeedTime"
                      type="number"
                      min="0"
                      label="最短做种时间（小时）"
                      placeholder="0 = 不设保护期"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="minRatio"
                      type="number"
                      min="0"
                      step="0.01"
                      label="最低分享率"
                      placeholder="0 = 不限"
                    />
                  </VCol>
                </VRow>
                <div class="editor-switches">
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
              </section>
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">完美种保护</div>
                    <div class="text-body-2 text-medium-emphasis">优质老种（非零魔 · 做种人数少 · 挂得够老）永久保留，不参与任何清理——魔力靠「养」，越老越肥</div>
                  </div>
                </header>
                <div class="editor-switches">
                  <VSwitch v-model="protectPerfect" label="启用完美种保护（满足条件的种子永不清理）" color="primary" hide-details inset />
                </div>
                <VRow v-if="protectPerfect">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="perfectMaxSeeders"
                      type="number"
                      min="0"
                      label="完美种：做种人数上限"
                      hint="站内做种人数 ≤ 该值才算完美（0 = 不限制）"
                      suffix="人"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="perfectMinWeeks"
                      type="number"
                      min="0"
                      step="0.5"
                      label="完美种：做种周数下限"
                      hint="做种周数 ≥ 该值才算完美（0 = 不限制）"
                      suffix="周"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>

</template>

<style scoped>
/* 面板专属 scoped 选择器（自 TaskEditorDialog.vue 复制；
   .editor-* 是跨面板共享类，父组件保留同名规则） */
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
