/** 与后端 `app.utils.chapter_numbering.display_chapter_number` 对齐 */

const CHAPTER_NUM_PREFIX = /^\s*第\s*0*(\d+)\s*章/

export function displayChapterNumber(title: string | undefined, sortOrder: number | undefined): number {
  const raw = (title || '').trim()
  const m = CHAPTER_NUM_PREFIX.exec(raw)
  if (m) return Math.max(1, parseInt(m[1], 10))
  const so = sortOrder == null ? 0 : Number(sortOrder)
  return Math.max(1, so + 1)
}
