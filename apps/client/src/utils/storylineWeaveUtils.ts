/**
 * 故事线织网：前端读取 extra.volume_beats 等辅助函数
 */
import type { StoryLine } from '../types'

export type VolumeBeatRow = {
  vol_index?: number
  beat?: string
  tension?: number
  is_active?: boolean
  chapter_hint_start?: number
  chapter_hint_peak?: number
}

export function hasStorylineWeave(sl: StoryLine): boolean {
  const beats = sl.extra?.volume_beats
  return Array.isArray(beats) && beats.length > 0
}

/** 按全书章序号粗算卷索引（与后端 weave_engine 一致：每卷默认 60 章）。 */
export function volIndexForChapter(chapterNumber: number, plannedPerVol = 60): number {
  if (chapterNumber <= 0) return 0
  return Math.floor((chapterNumber - 1) / plannedPerVol)
}

export function plannedBeatForChapter(
  sl: StoryLine,
  chapterNumber: number,
  plannedPerVol = 60,
): VolumeBeatRow | null {
  const beats = sl.extra?.volume_beats as VolumeBeatRow[] | undefined
  if (!beats?.length) return null
  const vi = volIndexForChapter(chapterNumber, plannedPerVol)
  return beats.find(b => Number(b.vol_index) === vi) ?? null
}

export function formatPlannedBeatHint(sl: StoryLine, chapterNumber: number): string {
  const row = plannedBeatForChapter(sl, chapterNumber)
  if (!row || row.is_active === false) return ''
  const parts: string[] = []
  if (row.beat) parts.push(`计划：${row.beat}`)
  if (row.tension != null) parts.push(`张力 ${row.tension}`)
  if (row.chapter_hint_peak) parts.push(`高潮约第 ${row.chapter_hint_peak} 章`)
  return parts.join(' · ')
}
