/** 卷章纲展开按钮：计划章数与补全态（与后端 planned_chapters 15–80 对齐） */
import type { OutlineNode } from '../../types'

export function normalizePlannedChapters(raw: unknown, isFanqie: boolean): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 15) return isFanqie ? 50 : 30
  if (n > 80) return 80
  return Math.floor(n)
}

export function isFanqieOutlineProject(projectExtra?: Record<string, unknown>): boolean {
  const pos = projectExtra?.positioning as Record<string, unknown> | undefined
  if (pos?.pace_type === 'fast') return true
  return Boolean(projectExtra?.fanqie_positioning)
}

export function volumeExpandUiState(volumeNode: OutlineNode, projectExtra?: Record<string, unknown>) {
  const chapterPlanCount = (volumeNode.children ?? []).filter(c => c.node_type === 'chapter_plan').length
  const fanqie = isFanqieOutlineProject(projectExtra)
  const planned = normalizePlannedChapters(volumeNode.extra?.planned_chapters, fanqie)
  const isEmpty = chapterPlanCount === 0
  const isComplete = chapterPlanCount >= planned
  const isPartial = chapterPlanCount > 0 && !isComplete
  return { chapterPlanCount, planned, isEmpty, isComplete, isPartial, fanqie }
}
