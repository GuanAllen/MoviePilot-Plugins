// MagicFlow 前端 · 站点货币名（19.10.48）
//
// 各 PT 站对「魔力」有各自的叫法：NexusPHP 默认「魔力值」、财神「金元宝」、
// 蟹黄堡「蟹币值」、野马PT「积分」。这些是**互不通兑**的独立经济系统，
// 界面上统一写「魔力」会让人误以为能横向比较/相加。
//
// 后端 `sites/formula_fetch.py::detect_currency_name` 从站点页面原文里认出自称，
// 随 `/status` 的 `currency` 字段下发（空串 = 没认出来）。
// 这里只做取值 + 兜底，不做猜名。
//
// ⚠ 仅用于「数值 + 单位」的展示（当前 1167 积分 / 131.4 蟹币值/时）。
//   功能名（刷魔力 / 魔力门槛 / 魔力规则 / 魔力趋势）保持「魔力」不动 ——
//   那是这个产品的功能名，不是某站的计量单位。

const DEFAULT_CURRENCY = '魔力值';


/**
 * 取站点货币名。
 * @param {object|string|null} source 任务对象（带 currency）或直接的货币名字符串
 * @returns {string} 认不出时返回默认「魔力值」
 */
function currencyOf(source) {
  const raw = source && typeof source === 'object' ? source.currency : source;
  const name = String(raw == null ? '' : raw).trim();
  return name || DEFAULT_CURRENCY
}

/**
 * 多站汇总场景：各站货币不同，**不能相加**。
 * 只有所有站点货币一致时才用那个名字，否则退回中性说法。
 * @param {Array} tasks 任务列表
 * @returns {string} 统一货币名，或默认「魔力值」
 */
function currencyOfMany(tasks) {
  const names = new Set(
    (tasks || []).map((t) => String((t && t.currency) || '').trim()).filter(Boolean),
  );
  if (names.size === 1) return [...names][0]
  return DEFAULT_CURRENCY
}

export { DEFAULT_CURRENCY, currencyOf, currencyOfMany }
