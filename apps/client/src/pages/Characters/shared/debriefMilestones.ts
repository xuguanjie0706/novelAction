/**
 * @file 从 Character.extra.debrief_realm_milestones 解析复盘境界记录（与 list 接口同源）
 */
import type { Character } from '../../../types'

export interface DebriefRealmMilestone {
  chapter_number: number
  chapter_id?: string
  chapter_title?: string
  realm_name: string
  realm_rank?: number | null
  source?: string
}

/** 读取人物 extra 中由 chapter_debrief 写入的境界里程碑（按章号升序） */
export function getDebriefRealmMilestones(char: Character): DebriefRealmMilestone[] {
  const extra = char.extra as Record<string, unknown> | undefined
  const raw = extra?.debrief_realm_milestones
  if (!Array.isArray(raw)) return []
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    .map((x) => ({
      chapter_number: Number(x.chapter_number) || 0,
      chapter_id: typeof x.chapter_id === 'string' ? x.chapter_id : undefined,
      chapter_title: typeof x.chapter_title === 'string' ? x.chapter_title : undefined,
      realm_name: String(x.realm_name ?? '').trim(),
      realm_rank: x.realm_rank != null && x.realm_rank !== '' ? Number(x.realm_rank) : null,
      source: typeof x.source === 'string' ? x.source : undefined,
    }))
    .filter((m) => m.chapter_number > 0 && m.realm_name)
    .sort((a, b) => a.chapter_number - b.chapter_number)
}
