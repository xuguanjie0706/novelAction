/**
 * useDabaiWriteActions — 大白文写作页 AI 队列（走后端 dabai 专线）
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { aiApi, chaptersApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../store'
import type { QualityReport } from '../../types'
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

  /** 通用章节质检（/ai/quality-check，与 AIPanel / 队列 rewrite 同源）。 */
  const runConsistencyCheck = async () => {
    if (!chapter || checking) return
    setChecking(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.qualityCheck(projectId, {
        chapter_id: chapter.id,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const data = res.data as QualityReport & { error?: string }
      if (data.error || (data.overall_score === 0 && !Object.keys(data.dimensions || {}).length)) {
        toast.error(data.summary || '质检失败，请稍后重试')
        return
      }
      const chRes = await chaptersApi.get(projectId, chapter.id)
      upsertChapter(chRes.data)
      const score = Number(data.overall_score)
      toast.success(Number.isFinite(score) ? `质检完成：${score.toFixed(1)}/10` : '质检完成')
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : '质检失败')
    } finally {
      setChecking(false)
    }
  }

  return { generateChapter, runConsistencyCheck, chapterBusy, checking }
}
