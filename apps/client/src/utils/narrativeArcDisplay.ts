/**
 * Bootstrap Step 9.5 / 9.8 产物：`Project.extra.emotion_arc` 与 `villain_arc`。
 * 均为按卷 JSON 数组，供纪要页与 Bootstrap 步骤预览复用。
 */

export interface VillainArcEntry {
  vol_index?: number
  vol_title?: string
  villain_name?: string
  vol_goal?: string
  vol_obstacle?: string
  vol_key_choice?: string
  vol_cost?: string
  vol_result?: string
  threat_escalation?: string
  hidden_move?: string
}

export interface EmotionArcEntry {
  vol_index?: number
  vol_title?: string
  phase?: string
  dominant_emotion?: string
  emotional_deposit?: string
  emotional_cost?: string
  net_balance?: string
  arc_note?: string
}

/** 从 project.extra 取出并规范为按 vol_index 排序的数组。 */
export function normalizeArcList<T extends { vol_index?: number }>(
  raw: unknown,
): T[] {
  if (!Array.isArray(raw)) return []
  return [...(raw as T[])].sort(
    (a, b) => (a.vol_index ?? 0) - (b.vol_index ?? 0),
  )
}

export function resolveVillainArc(
  projectExtra?: Record<string, unknown> | null,
): VillainArcEntry[] {
  return normalizeArcList<VillainArcEntry>(projectExtra?.villain_arc)
}

export function resolveEmotionArc(
  projectExtra?: Record<string, unknown> | null,
): EmotionArcEntry[] {
  return normalizeArcList<EmotionArcEntry>(projectExtra?.emotion_arc)
}

const VILLAIN_RESULT_LABEL: Record<string, string> = {
  win: '反派占优',
  lose: '反派受挫',
  stalemate: '僵持',
}

const VILLAIN_RESULT_COLOR: Record<string, string> = {
  win: '#ef4444',
  lose: '#22c55e',
  stalemate: '#f59e0b',
}

export function villainResultLabel(result?: string): string {
  if (!result) return '—'
  return VILLAIN_RESULT_LABEL[result.toLowerCase()] ?? result
}

export function villainResultColor(result?: string): string {
  if (!result) return '#6b7280'
  return VILLAIN_RESULT_COLOR[result.toLowerCase()] ?? '#6b7280'
}

const NET_BALANCE_LABEL: Record<string, string> = {
  positive: '情绪净收益',
  neutral: '情绪持平',
  negative: '情绪净消耗',
}

const NET_BALANCE_COLOR: Record<string, string> = {
  positive: '#22c55e',
  neutral: '#6b7280',
  negative: '#f97316',
}

export function netBalanceLabel(balance?: string): string {
  if (!balance) return '—'
  return NET_BALANCE_LABEL[balance.toLowerCase()] ?? balance
}

export function netBalanceColor(balance?: string): string {
  if (!balance) return '#6b7280'
  return NET_BALANCE_COLOR[balance.toLowerCase()] ?? '#6b7280'
}
