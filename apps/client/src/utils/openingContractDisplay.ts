/**
 * Bootstrap Step 12 `opening_contract` 的展示与计数工具。
 * 后端落库为扁平 JSON 字段，非 `promises[]` 数组。
 */

export const OPENING_CONTRACT_FIELDS: ReadonlyArray<{
  key: string
  label: string
  priority: number
}> = [
  { key: 'first_200_words_test', label: '第1章前200字核验', priority: 2 },
  { key: 'chapter1_hook', label: '第1章末钩子', priority: 5 },
  { key: 'chapter3_payoff', label: '第3章小爽点', priority: 4 },
  { key: 'chapter5_foreshadow', label: '第5章长线伏笔', priority: 3 },
  { key: 'chapter10_subscribe_reason', label: '第10章订阅钩', priority: 5 },
  { key: 'chapter_rhythm', label: '前10章节奏设计', priority: 2 },
]

export function resolveOpeningContract(
  insights?: { opening_contract?: Record<string, unknown> } | null,
  projectExtra?: Record<string, unknown> | null,
): Record<string, unknown> {
  const candidates = [insights?.opening_contract, projectExtra?.opening_contract]
  for (const raw of candidates) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
    const oc = raw as Record<string, unknown>
    if (countOpeningContractEntries(oc) > 0) return oc
  }
  return {}
}

export function hasContractValue(v: unknown): boolean {
  if (v == null) return false
  if (typeof v === 'string') return v.trim().length > 0
  if (Array.isArray(v)) return v.some(hasContractValue)
  if (typeof v === 'object') return Object.keys(v as object).length > 0
  return true
}

/** 将任意 AI 产物安全转为可渲染纯文本（避免 React 子节点类型错误）。 */
export function formatContractDisplayValue(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) {
    return v
      .map(item => formatContractDisplayValue(item))
      .filter(Boolean)
      .join('；')
  }
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>
    const inner = o.text ?? o.content ?? o.description ?? o.hook ?? o.value
    if (inner != null) return formatContractDisplayValue(inner)
    try {
      return JSON.stringify(o)
    } catch {
      return String(o)
    }
  }
  return String(v)
}

export function countOpeningContractEntries(oc: Record<string, unknown>): number {
  if (!oc || typeof oc !== 'object') return 0
  const legacy = oc.promises ?? oc.contracts ?? oc.items
  if (Array.isArray(legacy)) return legacy.length

  let n = OPENING_CONTRACT_FIELDS.filter(f => hasContractValue(oc[f.key])).length
  const traps = oc.opening_traps_to_avoid
  if (Array.isArray(traps) && traps.some(hasContractValue)) n += 1
  return n
}

export function priorityColor(priority: number): string {
  if (priority >= 5) return '#ef4444'
  if (priority >= 3) return '#f97316'
  return '#22c55e'
}
