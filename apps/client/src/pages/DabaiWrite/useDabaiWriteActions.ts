/**
 * useDabaiWriteActions — 大白文写作页 AI 队列（走后端 dabai 专线）
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { aiApi, chaptersApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, llmProviderIdFromRoute, routeLlmProviderPayload } from '../../store'
import type { Chapter } from '../../types'
import { shouldUseGatedDraft } from '../../utils/writingConfigGate'
import type { WritingConfig } from '../../api/client'

export function useDabaiWriteActions(
  projectId: string,
  chapter: Chapter | undefined,
  writingConfig: WritingConfig | null,
) {
  const addGenTask = useAppStore(s => s.addGenTask)
  const upsertChapter = useAppStore(s => s.upsertChapter)
  const genQueue = useAppStore(s => s.genQueue)

  const chapterBusy = chapter
    ? genQueue.some(
        t =>
          t.projectId === projectId
          && (t.status === 'pending' || t.status === 'running')
          && (
            (t.type === 'rewrite_chapter' && t.params?.chapterId === chapter.id)
            || (t.type === 'gated_rewrite_chapter' && t.params?.chapterId === chapter.id)
          ),
      )
    : false

  const generateChapter = (userPrompt = '') => {
    if (!chapter) return
    const route = useAppStore.getState().aiBackendRoute
    const useGated = shouldUseGatedDraft(writingConfig)
    addGenTask({
      type: useGated ? 'gated_rewrite_chapter' : 'rewrite_chapter',
      projectId,
      label: useGated ? `大白文·门控《${chapter.title}》` : `大白文·生成《${chapter.title}》`,
      params: {
        chapterId: chapter.id,
        userPrompt: userPrompt.trim(),
        modelProfile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      },
    })
    toast.success(
      useGated
        ? '已加入队列：按章节要素五拍写正文 + 设定一致性校验'
        : '已加入队列：按章节要素五拍写正文',
    )
  }

  const [checking, setChecking] = useState(false)

  /** 质检 v2：规则一致性 + LLM 衔接/五拍/钩子（mode=full）。 */
  const runConsistencyCheck = async () => {
    if (!chapter || checking) return
    setChecking(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      await aiApi.dabaiConsistencyCheck(projectId, chapter.id, {
        mode: 'full',
        model_profile: modelProfileFromRoute(route),
        llm_provider_id: llmProviderIdFromRoute(route),
      })
      const chRes = await chaptersApi.get(projectId, chapter.id)
      upsertChapter(chRes.data)
      const report = chRes.data.last_quality_report as { consistency_pass?: boolean; warnings?: unknown[] } | null
      const passed = report?.consistency_pass !== false
      const warnCount = report?.warnings?.length ?? 0
      toast.success(
        !passed ? '发现阻断问题，见上方提示'
        : warnCount > 0 ? `质检完成：${warnCount} 条提醒`
        : '质检通过',
      )
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : '校验失败')
    } finally {
      setChecking(false)
    }
  }

  return { generateChapter, runConsistencyCheck, chapterBusy, checking }
}
