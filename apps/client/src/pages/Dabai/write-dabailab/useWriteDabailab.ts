import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { dabaiApi } from '../../../api/dabai'
import type { DabaiChapter, DabaiProjectDetail } from '../../../types/dabai'
import { groupByVolume } from './groupByVolume'

export function useWriteDabailab(projectId: string | undefined) {
  const [detail, setDetail] = useState<DabaiProjectDetail | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [activeId, setActiveId] = useState<string | null>(null)

  const reload = useCallback(() => {
    if (!projectId) return
    setLoadState('loading')
    dabaiApi.get(projectId)
      .then(res => {
        setDetail(res.data)
        const chs = [...(res.data.chapter_outlines ?? [])].sort((a, b) => a.chapter_number - b.chapter_number)
        const blank = [...chs].reverse().find(c => !c.content?.trim())
        setActiveId((blank ?? chs[0])?.id ?? null)
        setLoadState('ready')
      })
      .catch(() => {
        setLoadState('error')
        toast.error('加载失败')
      })
  }, [projectId])

  useEffect(() => { reload() }, [reload])

  const groups = useMemo(
    () => groupByVolume(detail?.volumes ?? [], detail?.chapter_outlines ?? []),
    [detail],
  )

  const activeChapter = useMemo(
    () => detail?.chapter_outlines.find(c => c.id === activeId) ?? null,
    [detail, activeId],
  )

  const afterSave = useCallback(async (chapterId: string) => {
    if (!projectId) return
    const res = await dabaiApi.get(projectId)
    setDetail(res.data)
    setActiveId(chapterId)
  }, [projectId])

  return { loadState, detail, groups, activeChapter, activeId, setActiveId, reload, afterSave }
}

export function hasContent(ch: DabaiChapter): boolean {
  return (ch.content?.trim().length ?? 0) > 0
}
