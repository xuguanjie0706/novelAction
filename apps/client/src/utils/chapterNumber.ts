/** 与后端 display_chapter_number 一致：标题以「第N章」开头时用 N，否则 sort_order+1 */

const CHAPTER_NUM_PREFIX = /^\s*第\s*0*(\d+)\s*章/u

export function displayChapterNumber(title: string | undefined, sortOrder: number | undefined): number {
  const raw = (title ?? '').trim()
  const m = raw.match(CHAPTER_NUM_PREFIX)
  if (m) return Math.max(1, parseInt(m[1], 10))
  const so = sortOrder == null || Number.isNaN(Number(sortOrder)) ? 0 : Number(sortOrder)
  return Math.max(1, so + 1)
}

export function memoryDisplayChapter(
  m: { chapter_id?: string; chapter_number?: number },
  chapterById: Map<string, { title: string; sort_order: number }>,
): number {
  if (m.chapter_id && chapterById.has(m.chapter_id)) {
    const ch = chapterById.get(m.chapter_id)!
    return displayChapterNumber(ch.title, ch.sort_order)
  }
  return m.chapter_number ?? 0
}
