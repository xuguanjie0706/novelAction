import type { DabaiChapter } from '../../../types/dabai'

/** 首写本章时若上一章无正文则阻断；已有正文的重写不受限。 */
export function dabaiChapterGenerateBlockReason(
  chapter: DabaiChapter,
  chapters: DabaiChapter[],
): string | null {
  if ((chapter.content ?? '').trim()) return null
  const num = chapter.chapter_number
  if (num <= 1) return null
  const prev = chapters.find(c => c.chapter_number === num - 1)
  if (!prev) return `第 ${num - 1} 章不存在，请先展开章纲`
  if (!(prev.content ?? '').trim()) {
    const title = prev.title?.trim()
    return title
      ? `请先生成第 ${num - 1} 章《${title}》正文`
      : `请先生成第 ${num - 1} 章正文`
  }
  return null
}
