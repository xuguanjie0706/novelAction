/**
 * 将章节 HTML 转为对照用叙事纯文本（去索引块）。
 */
import { htmlToPlainForSplit, splitStreamedDraftText } from '../../../utils/draftChapterIndexSplit'

export function chapterHtmlToComparePlain(html: string): string {
  const plain = htmlToPlainForSplit(html || '').trim()
  if (!plain) return ''
  return splitStreamedDraftText(plain).body.trim() || plain
}
