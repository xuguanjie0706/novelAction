/**
 * 判断 Bootstrap run 是否可从书架/纪要页「继续生成」恢复（避免重头跑浪费 token）。
 */
import type { BootstrapRunHistoryItem } from '../api/bootstrap'

const ACTIVE_STATUSES = new Set(['running', 'awaiting_gate', 'awaiting_retry'])

/** 步骤失败但停在 retry 闸门，或 run 已 failed 却仍保留 gate 上下文（后端 resume 会临时改回 awaiting_gate）。 */
export function isResumableFailedRun(
  run: Pick<BootstrapRunHistoryItem, 'status' | 'gate_data'>,
): boolean {
  if (run.status !== 'failed') return false
  const gd = run.gate_data
  return Boolean(gd && typeof gd === 'object' && (gd as { current_gate?: string }).current_gate)
}

/** 项目下最近一条可恢复的 run：进行中优先，其次 failed+闸门。 */
export function pickResumableBootstrapRun(
  rows: BootstrapRunHistoryItem[],
): BootstrapRunHistoryItem | undefined {
  const active = rows.find(r => ACTIVE_STATUSES.has(r.status))
  if (active) return active
  return rows.find(isResumableFailedRun)
}

export function gateResumeHint(
  gateData: Record<string, unknown> | null | undefined,
): string {
  const kind = String(gateData?.kind || '')
  if (kind === 'volumes') return '卷级骨架已写入，确认后可继续后续步骤'
  if (kind === 'characters') return '人物库已写入，确认后可继续'
  if (kind === 'power_systems') return '境界体系已写入，确认后可继续'
  if (kind === 'positioning') return '立项定位可审阅后继续'
  return '从上次闸门继续，无需重头生成'
}
