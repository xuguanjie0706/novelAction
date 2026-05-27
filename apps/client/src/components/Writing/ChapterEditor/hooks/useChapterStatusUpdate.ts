/**
 * useChapterStatusUpdate — 章节状态下拉更新
 */
import toast from 'react-hot-toast'
import { chaptersApi } from '../../../../api/client'
import type { Chapter } from '../../../../types'
import { STATUS_OPTIONS } from '../constants'

interface UseChapterStatusUpdateOptions {
  projectId: string
  chapterId: string
  upsertChapter: (ch: Chapter) => void
  onAfterDoneOrReviewed: () => Promise<void>
  setStatusOpen: (v: boolean) => void
}

export function useChapterStatusUpdate({
  projectId,
  chapterId,
  upsertChapter,
  onAfterDoneOrReviewed,
  setStatusOpen,
}: UseChapterStatusUpdateOptions) {
  const updateStatus = async (status: Chapter['status']) => {
    setStatusOpen(false)
    try {
      const res = await chaptersApi.update(projectId, chapterId, { status })
      upsertChapter(res.data)
      if (status === 'done' || status === 'reviewed') {
        await onAfterDoneOrReviewed()
      }
      toast.success(`状态 → 「${STATUS_OPTIONS.find(o => o.value === status)?.label}」`)
    } catch {
      toast.error('状态更新失败')
    }
  }

  return { updateStatus }
}
