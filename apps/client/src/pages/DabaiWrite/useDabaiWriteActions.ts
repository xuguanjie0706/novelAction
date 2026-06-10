/**
 * useDabaiWriteActions — 大白文写作页 AI 队列（走后端 dabai 专线）
 */
import toast from 'react-hot-toast'
import { aiApi, chaptersApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../store'
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

  const runConsistencyCheck = async () => {
    if (!chapter) return
    try {
      await aiApi.dabaiConsistencyCheck(projectId, chapter.id)
      const chRes = await chaptersApi.get(projectId, chapter.id)
      upsertChapter(chRes.data)
      const passed = chRes.data.last_quality_report?.consistency_pass !== false
      toast.success(passed ? '设定一致性通过' : '发现一致性问题，见上方提示')
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : '校验失败')
    }
  }

  return { generateChapter, runConsistencyCheck, chapterBusy }
}
