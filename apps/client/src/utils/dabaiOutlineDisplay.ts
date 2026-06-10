/**
 * @file 大白文章纲展示：从 OutlineNode / DabaiChapter 解析爽点节拍字段。
 */
import type { OutlineNode } from '../types'
import type { DabaiChapter } from '../types/dabai'

/** 爽点类型 → Tailwind 徽章样式（与 DabaiResult 对齐） */
export const DABAI_SHUANG_BADGE: Record<string, string> = {
  打脸: 'bg-rose-100 text-rose-700',
  升级: 'bg-amber-100 text-amber-700',
  获宝: 'bg-emerald-100 text-emerald-700',
  扮猪吃虎: 'bg-violet-100 text-violet-700',
  装逼: 'bg-sky-100 text-sky-700',
  群嘲反转: 'bg-pink-100 text-pink-700',
  收小弟: 'bg-teal-100 text-teal-700',
  救场: 'bg-orange-100 text-orange-700',
  扬名: 'bg-indigo-100 text-indigo-700',
}

export interface DabaiBeatDisplay {
  chapterNumber: number
  titleText: string
  shuangType: string
  yaquSetup: string
  emotionTurn: string
  yinbao: string
  shuangPayoff: string
  endHook: string
  realmRank: number | null
  realmLabel: string
  locationName: string
  isBigBeat: boolean
  expectedWords: number | null
}

export function isDabaiProject(extra?: Record<string, unknown> | null): boolean {
  const e = extra ?? {}
  const pos = e.positioning as Record<string, unknown> | undefined
  return (
    e.bootstrap_mode === 'dabai'
    || pos?.bootstrap_mode === 'dabai'
    || Boolean(e.dabai_positioning)
  )
}

export function isDabaiOutlineNode(node: OutlineNode): boolean {
  const extra = node.extra ?? {}
  return extra.bootstrap_mode === 'dabai' || Boolean(extra.dabai)
}

/** 去掉「第N章：」前缀，只留章名正文。 */
export function chapterTitleText(fullTitle: string, chapterNumber: number): string {
  const raw = (fullTitle || '').trim()
  const m = raw.match(/^第\s*0*(\d+)\s*章\s*[:：]?\s*(.*)$/s)
  if (m) {
    const text = (m[2] || '').trim()
    return text || '未命名'
  }
  if (raw) return raw
  return `第 ${chapterNumber} 章`
}

export function realmNameFromLevels(
  rank: number | null | undefined,
  levels: Array<{ rank?: number; name?: string }> | undefined,
): string {
  if (!rank) return ''
  const lv = levels?.find(l => l.rank === rank)
  return lv?.name ? String(lv.name) : `第${rank}档`
}

export function dabaiBeatFromOutlineNode(
  node: OutlineNode,
  chapterNumber: number,
  opts?: { realmLevels?: Array<{ rank?: number; name?: string }> },
): DabaiBeatDisplay | null {
  if (!isDabaiOutlineNode(node)) return null
  const extra = node.extra ?? {}
  const dabai = (extra.dabai as Record<string, unknown> | undefined) ?? {}
  const realmRank = typeof extra.realm_rank === 'number' ? extra.realm_rank : null
  return {
    chapterNumber,
    titleText: chapterTitleText(node.title ?? '', chapterNumber),
    shuangType: String(dabai.shuang_type ?? ''),
    yaquSetup: String(dabai.yaqu_setup ?? ''),
    emotionTurn: String(dabai.emotion_turn ?? ''),
    yinbao: String(dabai.yinbao ?? ''),
    shuangPayoff: String(dabai.shuang_payoff ?? node.summary ?? ''),
    endHook: String(node.highlight ?? node.hook ?? dabai.end_hook ?? ''),
    realmRank,
    realmLabel: realmNameFromLevels(realmRank, opts?.realmLevels),
    locationName: String(extra.location_name ?? ''),
    isBigBeat: Boolean(dabai.is_big_beat),
    expectedWords: node.expected_words ?? null,
  }
}

export function dabaiBeatFromChapter(ch: DabaiChapter, realmName?: (r?: number | null) => string): DabaiBeatDisplay {
  return {
    chapterNumber: ch.chapter_number,
    titleText: chapterTitleText(ch.title, ch.chapter_number),
    shuangType: ch.shuang_type,
    yaquSetup: ch.yaqu_setup,
    emotionTurn: ch.emotion_turn ?? '',
    yinbao: ch.yinbao,
    shuangPayoff: ch.shuang_payoff,
    endHook: ch.end_hook,
    realmRank: ch.realm_rank ?? null,
    realmLabel: realmName?.(ch.realm_rank) ?? (ch.realm_rank ? `第${ch.realm_rank}档` : ''),
    locationName: '',
    isBigBeat: ch.is_big_beat,
    expectedWords: ch.expected_words ?? null,
  }
}
