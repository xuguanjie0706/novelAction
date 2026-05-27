/**
 * useQueueDebriefHydrate — 复盘 Tab 打开时：队列快照或服务端缓存预填
 */
import { useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import type { AutoDebriefResponse } from '../types'
import { hasHtmlTextContent } from '../utils'

interface UseQueueDebriefHydrateOptions {
  contextOpen: boolean
  contextTab: string
  chapterId: string
  chapterContent: string
  chapterUpdatedAt: string
  autoDebriefing: boolean
  debriefSubmitting: boolean
  queueCommittedDebriefIds: Set<string>
  queueDebriefSnapshot: AutoDebriefResponse | undefined
  applyAutoDebriefData: (
    data: AutoDebriefResponse,
    source: 'cache' | 'llm',
    opts?: { silent?: boolean },
  ) => void
  setDebriefFromQueueSnapshot: (v: boolean) => void
  loadDebriefTabCache: () => Promise<void>
}

export function useQueueDebriefHydrate({
  contextOpen,
  contextTab,
  chapterId,
  chapterContent,
  chapterUpdatedAt,
  autoDebriefing,
  debriefSubmitting,
  queueCommittedDebriefIds,
  queueDebriefSnapshot,
  applyAutoDebriefData,
  setDebriefFromQueueSnapshot,
  loadDebriefTabCache,
}: UseQueueDebriefHydrateOptions) {
  const queueDebriefToastShownRef = useRef<Set<string>>(new Set())
  const queueSnapHydratedChapterRef = useRef<string | null>(null)

  const resetQueueHydrateRefs = () => {
    queueSnapHydratedChapterRef.current = null
  }

  useEffect(() => {
    if (!contextOpen || contextTab !== 'debrief') return
    if (!hasHtmlTextContent(chapterContent)) return
    if (autoDebriefing || debriefSubmitting) return

    if (queueCommittedDebriefIds.has(chapterId)) {
      const snap = queueDebriefSnapshot
      const snapHasUi = snap && (
        (snap.character_updates?.length ?? 0) > 0
        || (snap.storyline_updates?.length ?? 0) > 0
        || (snap.new_characters?.length ?? 0) > 0
        || (snap.asset_updates && Object.keys(snap.asset_updates).length > 0)
        || (typeof snap.summary === 'string' && snap.summary.trim().length > 0)
        || !!snap.chapter_index
      )

      if (snapHasUi && queueSnapHydratedChapterRef.current !== chapterId) {
        queueSnapHydratedChapterRef.current = chapterId
        applyAutoDebriefData(snap, 'cache', { silent: true })
        setDebriefFromQueueSnapshot(true)
      }

      if (!queueDebriefToastShownRef.current.has(chapterId)) {
        queueDebriefToastShownRef.current.add(chapterId)
        toast('此章复盘已由队列自动完成', { icon: '✅' })
      }
      return
    }

    void loadDebriefTabCache()
  }, [
    contextOpen,
    contextTab,
    chapterId,
    chapterUpdatedAt,
    chapterContent,
    autoDebriefing,
    debriefSubmitting,
    queueCommittedDebriefIds,
    queueDebriefSnapshot,
    loadDebriefTabCache,
    applyAutoDebriefData,
    setDebriefFromQueueSnapshot,
  ])

  return { resetQueueHydrateRefs, clearDebriefToastKeys: () => queueDebriefToastShownRef.current.clear() }
}
