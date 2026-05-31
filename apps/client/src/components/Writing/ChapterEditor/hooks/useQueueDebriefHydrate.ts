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
  /** 防止复盘 Tab effect 因 chapterContent 更新反复触发 loadDebriefTabCache */
  const debriefTabCacheFetchedRef = useRef<string | null>(null)

  const resetQueueHydrateRefs = () => {
    queueSnapHydratedChapterRef.current = null
    debriefTabCacheFetchedRef.current = null
  }

  useEffect(() => {
    if (!contextOpen || contextTab !== 'debrief') return
    if (!hasHtmlTextContent(chapterContent)) return
    if (autoDebriefing || debriefSubmitting) return
    if (debriefTabCacheFetchedRef.current === chapterId) return
    debriefTabCacheFetchedRef.current = chapterId

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
      if (!snapHasUi) {
        void loadDebriefTabCache()
      }
      return
    }

    void loadDebriefTabCache()
    // 仅在本章首次打开复盘 Tab 时拉缓存；勿把 chapterContent / loadDebriefTabCache 放进 deps 以免刷屏
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debriefTabCacheFetchedRef 按 chapterId 去重
  }, [
    contextOpen,
    contextTab,
    chapterId,
    autoDebriefing,
    debriefSubmitting,
    queueCommittedDebriefIds,
    queueDebriefSnapshot,
  ])

  return { resetQueueHydrateRefs, clearDebriefToastKeys: () => queueDebriefToastShownRef.current.clear() }
}
