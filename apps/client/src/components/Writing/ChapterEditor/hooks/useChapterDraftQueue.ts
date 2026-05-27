/**
 * useChapterDraftQueue — AI 草稿/续写/选区改写与生成门控派生值
 */
import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import type { Editor } from '@tiptap/react'
import { chaptersApi } from '../../../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../../../store'
import type { Chapter, OutlineNode } from '../../../../types'
import type { WritingConfig } from '../../../../api/client'
import { chapterHasNarrativeBody, shouldUseGatedDraft } from '../../../../utils/writingConfigGate'
import { INLINE_ACTIONS } from '../constants'
import { hasHtmlTextContent, isBookFirstChapterTitle } from '../utils'

interface UseChapterDraftQueueOptions {
  projectId: string
  chapter: Chapter
  chapters: Chapter[]
  outlineNode?: OutlineNode
  editor: Editor | null
  writingConfig: WritingConfig | null
  upsertChapter: (ch: Chapter) => void
  genQueue: ReturnType<typeof useAppStore.getState>['genQueue']
}

export function useChapterDraftQueue({
  projectId,
  chapter,
  chapters,
  outlineNode,
  editor,
  writingConfig,
  upsertChapter,
  genQueue,
}: UseChapterDraftQueueOptions) {
  const addGenTask = useAppStore(s => s.addGenTask)

  const [aiExtraPrompt, setAiExtraPrompt] = useState('')
  const [continueChapterCount, setContinueChapterCount] = useState(1)

  const orderedChapters = useMemo(
    () => [...chapters].sort((a, b) => a.sort_order - b.sort_order),
    [chapters],
  )
  const currentChapterIndex = orderedChapters.findIndex(c => c.id === chapter.id)
  const previousChapter = currentChapterIndex > 0 ? orderedChapters[currentChapterIndex - 1] : null
  const previousChapterGenerated =
    !previousChapter
    || hasHtmlTextContent(previousChapter.content)
    || (
      isBookFirstChapterTitle(chapter, outlineNode)
      && !!previousChapter
      && !hasHtmlTextContent(previousChapter.content)
    )
  const generateBlockedReason = previousChapterGenerated
    ? null
    : `请先生成上一章《${previousChapter?.title ?? '未命名章节'}》`

  const chapterGenBusy = useMemo(
    () =>
      genQueue.some(
        t =>
          t.projectId === projectId
          && (t.status === 'pending' || t.status === 'running')
          && (
            (t.type === 'continue_chapters'
              && Array.isArray(t.params?.chapterIds)
              && t.params.chapterIds.includes(chapter.id))
            || (t.type === 'rewrite_chapter' && t.params?.chapterId === chapter.id)
            || (t.type === 'gated_rewrite_chapter' && t.params?.chapterId === chapter.id)
          ),
      ),
    [genQueue, projectId, chapter.id],
  )

  const generateDisabled = chapterGenBusy || !previousChapterGenerated
  const remainingChapterCount = currentChapterIndex >= 0
    ? Math.max(1, orderedChapters.length - currentChapterIndex)
    : 1
  const normalizedContinueCount = Math.min(
    Math.max(1, continueChapterCount || 1),
    remainingChapterCount,
  )

  const flushEditorContent = async (): Promise<boolean> => {
    if (!editor) return true
    try {
      const currentContent = editor.getHTML()
      if (currentContent !== chapter.content) {
        const res = await chaptersApi.update(projectId, chapter.id, { content: currentContent })
        upsertChapter(res.data)
      }
      return true
    } catch {
      toast.error('当前章节保存失败，请稍后重试')
      return false
    }
  }

  const generateDraft = (opts?: { replaceExisting?: boolean; overridePrompt?: string }) => {
    if (!previousChapterGenerated) {
      toast.error(generateBlockedReason ?? '请先生成上一章')
      return
    }
    if (opts?.replaceExisting) {
      if (!window.confirm('「重新生成本章」将按大纲替换当前正文；若有旧稿会在保存前自动留版本快照。确定继续？')) return
      const route = useAppStore.getState().aiBackendRoute
      const wc = writingConfig as {
        pre_write_warning_enabled?: boolean
        auto_quality_gate?: boolean
        min_overall_score?: number
        min_subscribe_intent?: number
      } | null
      const useGated = shouldUseGatedDraft(writingConfig)
      const gatedLabel = (() => {
        const hasWarn = wc?.pre_write_warning_enabled === true
        const hasGate = wc?.auto_quality_gate === true
          && ((wc?.min_overall_score ?? 0) > 0 || (wc?.min_subscribe_intent ?? 0) > 0)
        if (hasWarn && hasGate) return `预警+门控重写《${chapter.title}》`
        if (hasWarn) return `写前预警重写《${chapter.title}》`
        return `门控重写《${chapter.title}》`
      })()
      addGenTask({
        type: useGated ? 'gated_rewrite_chapter' : 'rewrite_chapter',
        projectId,
        label: useGated ? gatedLabel : `重写《${chapter.title}》`,
        params: {
          chapterId: chapter.id,
          userPrompt: opts.overridePrompt ?? aiExtraPrompt.trim(),
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      const toastMsg = (() => {
        const hasWarn = wc?.pre_write_warning_enabled === true
        const warnReuseHint = hasWarn ? '（本章若已有预警记录将自动复用，跳过重复审稿）' : ''
        if (!useGated) return `已加入 AI 队列：开始重写本章${warnReuseHint}`
        const hasGate = wc?.auto_quality_gate === true
        if (hasWarn && hasGate) return `已加入 AI 队列：写前预警 + 质量门控写作${warnReuseHint}`
        if (hasWarn) return `已加入 AI 队列：写前预警写作（质检仅参考）${warnReuseHint}`
        return '已加入 AI 队列：质量门控写作（自动质检+重写）'
      })()
      toast.success(toastMsg)
      setAiExtraPrompt('')
      return
    }
    void (async () => {
      if (!(await flushEditorContent())) return
      const route = useAppStore.getState().aiBackendRoute
      const userPrompt =
        opts?.overridePrompt !== undefined ? String(opts.overridePrompt) : aiExtraPrompt.trim()
      addGenTask({
        type: 'continue_chapters',
        projectId,
        label: `生成《${chapter.title}》正文`,
        params: {
          chapterIds: [chapter.id],
          userPrompt,
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      toast.success('已加入 AI 队列：生成本章正文')
      setAiExtraPrompt('')
    })()
  }

  const runPromptAction = (action: 'rewrite' | 'expand', setShowSelectionBar: (v: boolean) => void, selectionText: string) => {
    if (!selectionText.trim()) {
      toast.error('请先选中需要处理的正文')
      return
    }
    const actionConfig = INLINE_ACTIONS.find(item => item.key === action)
    if (!actionConfig) return
    const actionPrompt = actionConfig.buildPrompt(selectionText.slice(0, 400))
    void (async () => {
      if (!(await flushEditorContent())) return
      const route = useAppStore.getState().aiBackendRoute
      addGenTask({
        type: 'continue_chapters',
        projectId,
        label: `生成《${chapter.title}》正文（选区）`,
        params: {
          chapterIds: [chapter.id],
          userPrompt: actionPrompt,
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      toast.success('已加入 AI 队列')
    })()
    setShowSelectionBar(false)
  }

  const enqueueContinueChapters = async () => {
    if (!previousChapterGenerated) {
      toast.error(generateBlockedReason ?? '请先生成上一章')
      return
    }
    const startIndex = orderedChapters.findIndex(c => c.id === chapter.id)
    if (startIndex < 0) {
      toast.error('未找到当前章节顺序，请刷新后重试')
      return
    }
    const remaining = Math.max(1, orderedChapters.length - startIndex)
    const count = Math.min(Math.max(1, continueChapterCount || 1), remaining)
    const targetChapters = orderedChapters.slice(startIndex, startIndex + count)

    if (!(await flushEditorContent())) return

    const route = useAppStore.getState().aiBackendRoute
    const userPrompt = aiExtraPrompt.trim()
    const modelProfile = modelProfileFromRoute(route)
    const llmPayload = routeLlmProviderPayload(route)

    if (
      targetChapters.length === 1
      && shouldUseGatedDraft(writingConfig)
      && !chapterHasNarrativeBody(targetChapters[0].content)
    ) {
      const sole = targetChapters[0]
      addGenTask({
        type: 'gated_rewrite_chapter',
        projectId,
        label: `门控生成《${sole.title}》`,
        params: {
          chapterId: sole.id,
          userPrompt,
          modelProfile,
          ...llmPayload,
        },
      })
      toast.success('已加入 AI 队列：质量门控写作（自动质检+重写）')
      setAiExtraPrompt('')
      return
    }

    addGenTask({
      type: 'continue_chapters',
      projectId,
      label: `从《${chapter.title}》起续写 ${targetChapters.length} 章`,
      params: {
        chapterIds: targetChapters.map(c => c.id),
        userPrompt,
        modelProfile,
        ...llmPayload,
      },
    })
    toast.success(`已加入 AI 队列：连续续写 ${targetChapters.length} 章`)
    setAiExtraPrompt('')
  }

  return {
    aiExtraPrompt,
    setAiExtraPrompt,
    continueChapterCount,
    setContinueChapterCount,
    generateDraft,
    runPromptAction,
    enqueueContinueChapters,
    chapterGenBusy,
    generateDisabled,
    generateBlockedReason,
    remainingChapterCount,
    normalizedContinueCount,
  }
}
