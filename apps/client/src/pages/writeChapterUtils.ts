/**
 * 写作页章节侧栏：同一大纲节点可能有多条 Chapter 记录时的择优规则。
 */
import type { Chapter } from '../types'

/** 同 outline_node_id 保留字数最多的一条；并列时取 updated_at 较新者 */
export function buildChapterByNodeId(chapters: Chapter[]): Map<string, Chapter> {
  const m = new Map<string, Chapter>()
  for (const ch of chapters) {
    if (!ch.outline_node_id) continue
    const prev = m.get(ch.outline_node_id)
    if (!prev) {
      m.set(ch.outline_node_id, ch)
      continue
    }
    const wc = ch.word_count ?? 0
    const prevWc = prev.word_count ?? 0
    if (wc > prevWc) {
      m.set(ch.outline_node_id, ch)
      continue
    }
    if (wc < prevWc) continue
    const chTs = ch.updated_at ? Date.parse(ch.updated_at) : 0
    const prevTs = prev.updated_at ? Date.parse(prev.updated_at) : 0
    if (chTs >= prevTs) m.set(ch.outline_node_id, ch)
  }
  return m
}

/** activeChapterId 若指向空壳重复章，改指向同大纲下有正文的那条 */
export function resolveActiveChapterId(
  chapters: Chapter[],
  activeChapterId: string | null,
): string | null {
  if (!activeChapterId) return null
  const current = chapters.find(c => c.id === activeChapterId)
  if (!current?.outline_node_id || (current.word_count ?? 0) > 0) return activeChapterId

  const siblings = chapters.filter(
    c => c.outline_node_id === current.outline_node_id && c.id !== current.id,
  )
  const best = siblings.sort((a, b) => (b.word_count ?? 0) - (a.word_count ?? 0))[0]
  return best && (best.word_count ?? 0) > 0 ? best.id : activeChapterId
}
