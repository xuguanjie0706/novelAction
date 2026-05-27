/**
 * useChapterManuscript — 原文/正文视图切换与预览 HTML
 */
import { useEffect, useMemo, useState } from 'react'
import type { Editor } from '@tiptap/react'
import type { Chapter } from '../../../../types'
import {
  splitStreamedDraftText,
  htmlToPlainForSplit,
  plainTextBlocksToHtml,
} from '../../../../utils/draftChapterIndexSplit'

export function useChapterManuscript(chapter: Chapter, editor: Editor | null, editorHtmlTick: number) {
  const [manuscriptView, setManuscriptView] = useState<'source' | 'prose'>('source')

  const hasManuscriptRawSnapshot = useMemo(
    () => Boolean((chapter.manuscript_raw_snapshot || '').trim()),
    [chapter.manuscript_raw_snapshot],
  )

  const rawSnapshotPreviewHtml = useMemo(() => {
    const s = (chapter.manuscript_raw_snapshot || '').trim()
    if (!s) return ''
    return plainTextBlocksToHtml(s)
  }, [chapter.manuscript_raw_snapshot])

  const prosePreviewHtml = useMemo(() => {
    if (!editor || manuscriptView !== 'prose') return ''
    const plain = htmlToPlainForSplit(editor.getHTML())
    const { body } = splitStreamedDraftText(plain.trim())
    return plainTextBlocksToHtml(body.trim())
  }, [editor, editorHtmlTick, manuscriptView, chapter.id])

  const resetManuscriptViewForChapter = () => {
    setManuscriptView((chapter.manuscript_raw_snapshot || '').trim() ? 'prose' : 'source')
  }

  useEffect(() => {
    const s = (chapter.manuscript_raw_snapshot || '').trim()
    if (!s) return
    setManuscriptView('prose')
  }, [chapter.manuscript_raw_snapshot])

  return {
    manuscriptView,
    setManuscriptView,
    hasManuscriptRawSnapshot,
    rawSnapshotPreviewHtml,
    prosePreviewHtml,
    resetManuscriptViewForChapter,
  }
}
