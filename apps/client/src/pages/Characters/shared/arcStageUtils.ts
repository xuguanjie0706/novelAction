/**
 * @file 弧线阶段拆分：规划（Bootstrap/人工）与复盘实证（completed）
 */

export type ArcStageItem = {
  stage?: string
  realm?: string
  state?: string
  chapter_range?: string
  completed?: boolean
  chapter_number?: number
  chapter_title?: string
  chapter_id?: string
}

export function splitArcStages(stages: unknown[] | null | undefined): {
  planned: ArcStageItem[]
  completed: ArcStageItem[]
} {
  const list = Array.isArray(stages) ? stages : []
  const planned: ArcStageItem[] = []
  const completed: ArcStageItem[] = []
  for (const raw of list) {
    if (!raw || typeof raw !== 'object') continue
    const s = raw as ArcStageItem
    if (s.completed === true) completed.push(s)
    else planned.push(s)
  }
  return { planned, completed }
}

export function mergeArcStages(planned: ArcStageItem[], completed: ArcStageItem[]): ArcStageItem[] {
  return [...planned, ...completed]
}

export const EMPTY_PLANNED_STAGE: ArcStageItem = {
  stage: '',
  realm: '',
  state: '',
  chapter_range: '',
}
