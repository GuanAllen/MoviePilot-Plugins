/**
 * 计划审批域接口（★ 15.17.0）。
 * 「AI 出计划 → 人复核 → 执行」：`plan` 只算不删（返回 plan_id = 内容哈希），
 * `apply` 带 plan_id（重新生成比对哈希，过期即拒绝）执行。
 * 全部返回**原始响应**（调用点自行 unwrap）。
 */
function qs(params = {}) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  return p.toString()
}

export function makePlan(c) {
  return {
    /** 生成计划（只算不删）：action=cleanup|optimize，task_id，budget_gb（仅 optimize） */
    plan: (params = {}) => c.get(`agent/plan?${qs(params)}`),
    /** 执行已批准的计划：plan_id 必填；confirm=1 才真执行（缺省干跑）。
     *  ★ agent 端 POST 参数走 **query**（与同族端点一致：FastAPI 标量 = query 参数）。 */
    apply: (params = {}) => c.post(`agent/plan/apply?${qs(params)}`, {}),
  }
}
