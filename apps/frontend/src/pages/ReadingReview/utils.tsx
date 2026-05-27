import { Tag } from 'antd'
import type { CoherenceApplyChapterResult, ReviewChapter } from '../../types/review'
import { SCORE_COLORS } from './constants'

export function scoreTag(score: number | undefined) {
  if (score == null) return <Tag>未评测</Tag>
  const matched = SCORE_COLORS.find((item) => score >= item.min) ?? SCORE_COLORS[SCORE_COLORS.length - 1]
  return (
    <Tag color={matched.color}>
      {matched.text} {score}
    </Tag>
  )
}

export function formatApplyChapterLine(chapterList: ReviewChapter[], a: CoherenceApplyChapterResult) {
  const c = chapterList.find((x) => x.id === a.chapter_id)
  const label = c ? `第${c.sort_order + 1}章 · ${c.title || '未命名'}` : `章节 ${a.chapter_id.slice(0, 8)}…`
  if (a.skipped) return `${label}（未写入${a.reason ? `：${a.reason}` : ''}）`
  return `${label}（${a.word_count ?? '-'} 字）`
}

export function snapshotSourceTag(note: string | null | undefined, isAuto: boolean) {
  if (note?.includes('连贯性评测')) return { color: 'blue' as const, text: '连贯性改正前' }
  if (isAuto) return { color: 'orange' as const, text: '自动快照' }
  return { color: 'default' as const, text: '手动快照' }
}

export function stripHtmlToPlain(html: string, maxLen: number) {
  const t = (html || '').replace(/<[^>]+>/g, '\n').replace(/\n+/g, '\n').trim()
  if (t.length <= maxLen) return t
  return `${t.slice(0, maxLen)}…`
}

export function clipLabel(s: string, maxLen: number) {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  if (t.length <= maxLen) return t
  return `${t.slice(0, maxLen)}…`
}
