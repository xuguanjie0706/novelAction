/**
 * useChapterManuscript — AI 重写快照与「前后对比」文稿
 */
import { useMemo } from 'react'
import type { Editor } from '@tiptap/react'
import type { Chapter } from '../../../../types'
import {
  splitStreamedDraftText,
  htmlToPlainForSplit,
} from '../../../../utils/draftChapterIndexSplit'

export type ManuscriptComparePlain = {
  before: string
  after: string
}

export function useChapterManuscript(
  chapter: Chapter,
  editor: Editor | null,
  editorHtmlTick: number,
) {
  const hasManuscriptRawSnapshot = useMemo(
    () => Boolean((chapter.manuscript_raw_snapshot || '').trim()),
    [chapter.manuscript_raw_snapshot],
  )

  const comparePlainTexts = useMemo((): ManuscriptComparePlain | null => {
    const snap = (chapter.manuscript_raw_snapshot || '').trim()
    if (!snap) return null
    const before = splitStreamedDraftText(snap).body
    let afterPlain = ''
    if (editor) {
      afterPlain = htmlToPlainForSplit(editor.getHTML())
    } else {
      afterPlain = htmlToPlainForSplit(chapter.content || '')
    }
    const after = splitStreamedDraftText(afterPlain.trim()).body
    return { before, after }
  }, [chapter.manuscript_raw_snapshot, chapter.content, editor, editorHtmlTick])

  return {
    hasManuscriptRawSnapshot,
    comparePlainTexts,
  }
}
