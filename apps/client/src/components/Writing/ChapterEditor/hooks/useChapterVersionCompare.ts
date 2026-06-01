/**
 * useChapterVersionCompare — 先选版本历史，再打开左右对照
 */
import { useCallback, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import type { Editor } from '@tiptap/react'
import { chaptersApi } from '../../../../api/client'
import type { Chapter, ChapterVersion } from '../../../../types'
import { chapterHtmlToComparePlain } from '../comparePlain'
import { filterVersionsForUserCompare } from '../versionCompareFilter'

export const CURRENT_SIDE_ID = '__current__'

const CURRENT_LABEL = '当前正文（服务器最新入库稿）'

export function useChapterVersionCompare({
  projectId,
  chapter,
  editor,
  upsertChapter,
  saveTimerRef,
  syncEditorContent,
}: {
  projectId: string
  chapter: Chapter
  editor: Editor | null
  upsertChapter: (ch: Chapter) => void
  saveTimerRef?: React.MutableRefObject<ReturnType<typeof setTimeout> | undefined>
  syncEditorContent: (html: string) => void
}) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [versionsList, setVersionsList] = useState<ChapterVersion[]>([])
  const [baseId, setBaseId] = useState<string>(CURRENT_SIDE_ID)
  const [targetId, setTargetId] = useState<string>(CURRENT_SIDE_ID)
  const [beforePlain, setBeforePlain] = useState('')
  const [afterPlain, setAfterPlain] = useState('')
  const [beforeLabel, setBeforeLabel] = useState('')
  const [afterLabel, setAfterLabel] = useState('')
  const [runningCompare, setRunningCompare] = useState(false)
  const [currentWordCount, setCurrentWordCount] = useState<number | null>(null)
  /** 打开对照前从 API 拉取的最新 HTML，避免编辑器/Store 滞后 */
  const latestContentRef = useRef('')

  const formatVersionLabel = (v: ChapterVersion) => {
    const when = new Date(v.created_at).toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
    const tag = v.is_auto ? '自动' : '手动'
    const note = v.note ? ` · ${v.note}` : ''
    return `${when}（${tag}${note}）`
  }

  const refreshLatestChapter = useCallback(async () => {
    const r = await chaptersApi.get(projectId, chapter.id)
    const fresh = r.data as Chapter
    upsertChapter(fresh)
    const html = fresh.content ?? ''
    latestContentRef.current = html
    setCurrentWordCount(typeof fresh.word_count === 'number' ? fresh.word_count : null)
    if (saveTimerRef?.current) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = undefined
    }
    syncEditorContent(html)
    return fresh
  }, [chapter.id, projectId, saveTimerRef, syncEditorContent, upsertChapter])

  const resolvePlain = useCallback(
    async (sideId: string): Promise<{ plain: string; label: string }> => {
      if (sideId === CURRENT_SIDE_ID) {
        let html = latestContentRef.current
        if (!html.trim()) {
          const fresh = await refreshLatestChapter()
          html = fresh.content ?? ''
        }
        return { plain: chapterHtmlToComparePlain(html), label: CURRENT_LABEL }
      }
      const r = await chaptersApi.getVersion(projectId, chapter.id, sideId)
      const v = r.data
      return {
        plain: chapterHtmlToComparePlain(v.content || ''),
        label: formatVersionLabel(v),
      }
    },
    [chapter.id, projectId, refreshLatestChapter],
  )

  const openComparePicker = useCallback(async () => {
    setPickerOpen(true)
    setVersionsLoading(true)
    setVersionsList([])
    try {
      const [, versionsRes] = await Promise.all([
        refreshLatestChapter(),
        chaptersApi.listVersions(projectId, chapter.id),
      ])
      const list = filterVersionsForUserCompare(
        (versionsRes.data as ChapterVersion[]).filter(v => (v.word_count ?? 0) > 0),
      )
      setVersionsList(list)
      if (list.length >= 1) {
        setBaseId(list[0].id)
        setTargetId(CURRENT_SIDE_ID)
      } else {
        setBaseId(CURRENT_SIDE_ID)
        setTargetId(CURRENT_SIDE_ID)
      }
    } catch {
      toast.error('无法加载版本历史')
      setPickerOpen(false)
    } finally {
      setVersionsLoading(false)
    }
  }, [chapter.id, projectId, refreshLatestChapter])

  const runCompare = useCallback(async () => {
    if (baseId === targetId) {
      toast.error('请选择两个不同的版本进行对照')
      return
    }
    setRunningCompare(true)
    try {
      await refreshLatestChapter()
      const left = await resolvePlain(baseId)
      const right = await resolvePlain(targetId)
      setBeforePlain(left.plain)
      setAfterPlain(right.plain)
      setBeforeLabel(left.label)
      setAfterLabel(right.label)
      setPickerOpen(false)
      setCompareOpen(true)
    } catch {
      toast.error('加载对照正文失败')
    } finally {
      setRunningCompare(false)
    }
  }, [baseId, targetId, refreshLatestChapter, resolvePlain])

  const resetCompareUi = () => {
    setPickerOpen(false)
    setCompareOpen(false)
    setVersionsList([])
    latestContentRef.current = ''
  }

  /** 设为左侧，若该版本当前是右侧则自动互换 */
  const assignBase = useCallback((id: string) => {
    setBaseId(id)
    if (id === targetId) setTargetId(baseId)
  }, [baseId, targetId])

  /** 设为右侧，若该版本当前是左侧则自动互换 */
  const assignTarget = useCallback((id: string) => {
    setTargetId(id)
    if (id === baseId) setBaseId(targetId)
  }, [baseId, targetId])

  const canCompare = baseId !== targetId
  const showCompareEntry =
    (chapter.word_count ?? 0) > 0
    || Boolean((chapter.manuscript_raw_snapshot || '').trim())

  return {
    showCompareEntry,
    pickerOpen,
    setPickerOpen,
    compareOpen,
    setCompareOpen,
    versionsLoading,
    versionsList,
    baseId,
    setBaseId,
    assignBase,
    targetId,
    setTargetId,
    assignTarget,
    beforePlain,
    afterPlain,
    beforeLabel,
    afterLabel,
    runningCompare,
    openComparePicker,
    runCompare,
    resetCompareUi,
    canCompare,
    currentSideId: CURRENT_SIDE_ID,
    formatVersionLabel,
    currentWordCount,
  }
}
