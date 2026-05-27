/**
 * useChapterSideData — 章节关联侧数据（开放伏笔、ChapterIndex）
 */
import { useEffect, useState } from 'react'
import { foreshadowsApi, chapterIndexesApi } from '../../../../api/client'
import type { ChapterIndex, Foreshadow } from '../../../../types'

export function useChapterSideData(projectId: string, chapterId: string) {
  const [bottomPanelOpen, setBottomPanelOpen] = useState(false)
  const [openForeshadows, setOpenForeshadows] = useState<Foreshadow[]>([])
  const [currentChIndex, setCurrentChIndex] = useState<ChapterIndex | null>(null)

  useEffect(() => {
    if (!projectId) return
    foreshadowsApi.list(projectId, 'open').then(r => setOpenForeshadows(r.data)).catch(() => {})
    chapterIndexesApi.getByChapter(projectId, chapterId)
      .then(r => setCurrentChIndex(r.data))
      .catch(() => setCurrentChIndex(null))
  }, [projectId, chapterId])

  return {
    bottomPanelOpen,
    setBottomPanelOpen,
    openForeshadows,
    setOpenForeshadows,
    currentChIndex,
    setCurrentChIndex,
  }
}
