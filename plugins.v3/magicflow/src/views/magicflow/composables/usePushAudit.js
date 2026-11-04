// MagicFlow 前端 · 推送审计域 composable（★ 19.11.22）
// 由线上 dist 还原（源文件在 11-03 之后丢失）：dist 关闭了 minify，保留了完整实现与注释。
import * as __vue from 'vue'

// MagicFlow 前端 · 推送审计（★ 19.11.22）
// 定位：⑤「推送审计」的**看**那一半。后端每次「加种」落一条（成功也记、失败更记），
//       这里只读 `/pushes`：列表 + 成败计数 + **钩子自检**（`hook_ready`）。
// 为什么要有钩子自检：钩子是模块级全局，热重载偶发绑丢，此时接口照常返回空列表 ——
//       不把「没在记」和「真没加过种」分开，人就会被空表骗。
// 依赖注入：api, notify（真值源在后端；本域只放 UI 状态与动作）。
const {computed: computed$h,ref: ref$i} = __vue;

function usePushAudit({ api, notify }) {
  const pushAuditOpen = ref$i(false);
  const pushAuditLoading = ref$i(false);
  const pushAuditFilter = ref$i(''); // '' 全部 / 'false' 仅失败 / 'true' 仅成功
  const pushAuditTaskId = ref$i('');
  const pushAuditTaskName = ref$i('');
  const pushAudit = ref$i({
    items: [],
    count: 0,
    kept: 0,
    ok_count: 0,
    failed_count: 0,
    keep_limit: 300,
    hook_ready: true,
  });

  const pushAuditItems = computed$h(() => pushAudit.value.items || []);
  const pushAuditHookReady = computed$h(() => pushAudit.value.hook_ready !== false);
  // 任务上下文（从运行诊断进来时带 task_id，弹窗顶部显示并支持清除）
  const pushAuditScopeText = computed$h(
    () => (pushAuditTaskId.value ? (pushAuditTaskName.value || pushAuditTaskId.value) : ''),
  );
  const pushAuditFailed = computed$h(() => Number(pushAudit.value.failed_count || 0));

  async function loadPushAudit() {
    pushAuditLoading.value = true;
    try {
      const qs = ['limit=200'];
      if (pushAuditFilter.value) qs.push(`ok=${pushAuditFilter.value}`);
      if (pushAuditTaskId.value) qs.push(`task_id=${encodeURIComponent(pushAuditTaskId.value)}`);
      const data = unwrapResponse(await api.push.pushes(qs.join('&'))) || {};
      pushAudit.value = { ...pushAudit.value, ...data };
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '读取推送审计失败', 'error');
    } finally {
      pushAuditLoading.value = false;
    }
  }

  /** 打开审计弹窗。`payload` 可带 `{ taskId, taskName }` 做任务维度过滤。 */
  function openPushAudit(payload) {
    const p = payload && typeof payload === 'object' ? payload : {};
    pushAuditTaskId.value = String(p.taskId || '');
    pushAuditTaskName.value = String(p.taskName || '');
    pushAuditOpen.value = true;
    loadPushAudit();
  }

  function setPushAuditFilter(value) {
    pushAuditFilter.value = String(value ?? '');
    loadPushAudit();
  }

  function clearPushAuditTask() {
    pushAuditTaskId.value = '';
    pushAuditTaskName.value = '';
    loadPushAudit();
  }

  return {
    pushAuditOpen,
    pushAuditLoading,
    pushAuditFilter,
    pushAuditTaskId,
    pushAuditTaskName,
    pushAudit,
    pushAuditItems,
    pushAuditHookReady,
    pushAuditScopeText,
    pushAuditFailed,
    loadPushAudit,
    openPushAudit,
    setPushAuditFilter,
    clearPushAuditTask,
  }
}

export { usePushAudit }

