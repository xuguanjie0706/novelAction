/**
 * useChapterHistory — 正文版本历史弹窗
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import type { Editor } from '@tiptap/react'
import { chaptersApi } from '../../../../api/client'
import type { Chapter, ChapterVersion, ChapterVersionDetail } from '../../../../types'
import { filterVersionsForUserCompare } from '../versionCompareFilter'

interface UseChapterHistoryOptions {
  projectId: string
  chapter: Chapter
  editor: Editor | null
  upsertChapter: (ch: Chapter) => void
}

export function useChapterHistory({
  projectId,
  chapter,
  editor,
  upsertChapter,
}: UseChapterHistoryOptions) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const [versionsList, setVersionsList] = useState<ChapterVersion[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [historyPreview, setHistoryPreview] = useState<ChapterVersionDetail | null>(null)
  const [historyPreviewLoading, setHistoryPreviewLoading] = useState(false)

  const resetHistoryUi = () => {
    setHistoryOpen(false)
    setVersionsList([])
    setHistoryPreview(null)
  }

  const openChapterHistory = async () => {
    setHistoryOpen(true)
    setVersionsLoading(true)
    setHistoryPreview(null)
    try {
      const r = await chaptersApi.listVersions(projectId, chapter.id)
      setVersionsList(filterVersionsForUserCompare(r.data as ChapterVersion[]))
    } catch {
      setVersionsList([])
      toast.error('无法加载版本列表')
    } finally {
      setVersionsLoading(false)
    }
  }

  const loadHistoryPreview = async (versionId: string) => {
    setHistoryPreviewLoading(true)
    try {
      const r = await chaptersApi.getVersion(projectId, chapter.id, versionId)
      setHistoryPreview(r.data as ChapterVersionDetail)
    } catch {
      toast.error('加载该版本正文失败')
    } finally {
      setHistoryPreviewLoading(false)
    }
  }

  const restoreHistoryVersion = async () => {
    if (!historyPreview || !editor) return
    if (!window.confirm('将用此历史版本替换当前正文（会先自动备份当前稿）。确定？')) return
    try {
      const plain = (chapter.content || '').replace(/<[^>]+>/g, '').trim()
      if (plain.length >= 1) {
        await chaptersApi.snapshot(projectId, chapter.id, '恢复历史版本前备份', true)
      }
      const res = await chaptersApi.update(projectId, chapter.id, {
        content: historyPreview.content,
        manuscript_raw_snapshot: null,
      })
      upsertChapter(res.data)
      editor.commands.setContent(historyPreview.content)
      toast.success('已恢复为所选历史版本')
      setHistoryOpen(false)
      setHistoryPreview(null)
    } catch {
      toast.error('恢复失败')
    }
  }

  return {
    historyOpen,
    setHistoryOpen,
    versionsList,
    versionsLoading,
    historyPreview,
    historyPreviewLoading,
    openChapterHistory,
    loadHistoryPreview,
    restoreHistoryVersion,
    resetHistoryUi,
  }
}
