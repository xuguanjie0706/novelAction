/**
 * @file 队列任务：单章重写
 */
import type { Chapter, GenTask, GenProgressItem, MemoryChunk } from '../../../../types'
import { aiApi, chaptersApi } from '../../../../api/client'
import { authFetch } from '../../../../api/authFetch'
import { formatApiError } from '../../../../utils/apiError'
import { autoCommitGeneratedChapterDebrief } from '../../../../utils/generatedChapterDebrief'
import { postDraftAssistAccumulatedWithPrewriteRetry } from '../../../../utils/draftPrewriteBlocked'
import { splitStreamedDraftText } from '../../../../utils/draftChapterIndexSplit'
import { useAppStore } from '../../../../store'
import {
  draftAssistSideEventHandler,
  manuscriptSnapshotBeforeRewrite,
  plainTextDraftToHtml,
} from '../utils/sseHelpers'

export async function runRewriteChapter(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
  upsertChapter: (chapter: Chapter) => void,
  setMemories: (memories: MemoryChunk[]) => void,
  markChapterDebriefCommitted: (chapterId: string) => void,
) {
  const { projectId, params } = task
  const chapterId: string | undefined = typeof params.chapterId === 'string' ? params.chapterId : undefined
  const userPrompt: string = typeof params.userPrompt === 'string' ? params.userPrompt : ''
  const modelProfile: 'local' | 'gemini' = params.modelProfile ?? 'local'
  const llmProviderId: string | undefined = params.llm_provider_id

  if (!chapterId) {
    onError('缺少章节 ID')
    return
  }

  pushProgress({ step: 'start', label: '重写任务已开始，正在读取章节…', done: false, error: false })

  let chapter: Chapter
  try {
    const chapterRes = await chaptersApi.get(projectId, chapterId)
    chapter = chapterRes.data
  } catch (e: any) {
    onError(`读取章节失败：${formatApiError(e)}`)
    return
  }

  let accumulated = ''
  try {
    pushProgress({ step: 'draft', label: `正在重写《${chapter.title}》…`, done: false, error: false })
    accumulated = await postDraftAssistAccumulatedWithPrewriteRetry(
      authFetch,
      `/api/v1/projects/${projectId}/ai/draft-assist/stream`,
      {
        chapter_id: chapterId,
        model_profile: modelProfile,
        ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        user_prompt: userPrompt.trim() || null,
        replace_existing: true,
      },
      {
        signal,
        onSideEvent: draftAssistSideEventHandler(pushProgress, phase => phase, chapterId),
      },
    )

    if (!accumulated.trim()) throw new Error('未收到正文内容')

    const { body: draftBody } = splitStreamedDraftText(accumulated.trim())
    if (!draftBody.trim()) throw new Error('未收到叙事正文（可能只有索引块）')

    pushProgress({ step: 'draft', label: `✓ 《${chapter.title}》重写完成，正在保存…`, done: true, error: false })
    try {
      if ((chapter.content || '').trim() && (chapter.word_count ?? 0) > 0) {
        await chaptersApi.snapshot(projectId, chapterId, 'AI重写正文前自动备份', true)
      }
    } catch {
      /* 快照失败不阻断保存 */
    }
    const snapshotBefore = manuscriptSnapshotBeforeRewrite(chapter.content || '')
    const updateRes = await chaptersApi.update(projectId, chapterId, {
      content: plainTextDraftToHtml(draftBody.trim()),
      ...(snapshotBefore ? { manuscript_raw_snapshot: snapshotBefore } : {}),
    })
    upsertChapter(updateRes.data)
    pushProgress({ step: 'save', label: '✓ 已保存叙事正文（稿末见模型调用记录）', done: true, error: false })

    pushProgress({ step: 'quality', label: '正在质检重写后的章节…', done: false, error: false })
    try {
      const qualityRes = await aiApi.qualityCheck(projectId, {
        chapter_id: chapterId,
        model_profile: modelProfile,
        ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
      })
      const score = Number(qualityRes.data?.overall_score)
      pushProgress({
        step: 'quality',
        label: Number.isFinite(score) ? `✓ 质检完成：${score.toFixed(1)}/10` : '✓ 质检完成',
        done: true,
        error: false,
      })
      const refreshedChapter = await chaptersApi.get(projectId, chapterId)
      upsertChapter(refreshedChapter.data)
    } catch (e: any) {
      pushProgress({
        step: 'quality',
        label: `质检失败，可稍后手动检查：${formatApiError(e)}`,
        done: true,
        error: true,
      })
    }

    pushProgress({ step: 'debrief', label: '正在自动复盘并写入线索页（情节档案/伏笔）…', done: false, error: false })
    try {
      useAppStore.getState().resetChapterDebriefQueueState(chapterId)
      const applied = await autoCommitGeneratedChapterDebrief(
        projectId,
        chapterId,
        modelProfile,
        llmProviderId,
        { forceRefresh: true },
      )
      if (applied.debriefPreview && typeof applied.debriefPreview === 'object') {
        useAppStore.getState().setQueueDebriefUiSnapshot(chapterId, applied.debriefPreview as Record<string, unknown>)
      }
      markChapterDebriefCommitted(chapterId)
      const indexLabel = applied.chapterIndexSaved ? '情节档案已写入' : '情节档案未更新'
      pushProgress({
        step: 'debrief',
        label: `✓ 自动复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${indexLabel}`,
        done: true,
        error: false,
      })
    } catch (e: any) {
      pushProgress({
        step: 'debrief',
        label: `自动复盘失败，可稍后在复盘面板手动提交：${formatApiError(e)}`,
        done: true,
        error: true,
      })
    }

    pushProgress({ step: 'memory', label: '正在刷新记忆库…', done: false, error: false })
    try {
      const memoriesRes = await aiApi.listMemory(projectId)
      setMemories(memoriesRes.data)
      pushProgress({ step: 'memory', label: `✓ 记忆库已刷新：${memoriesRes.data.length} 条`, done: true, error: false })
    } catch (e: any) {
      pushProgress({
        step: 'memory',
        label: `记忆库刷新失败：${formatApiError(e)}`,
        done: true,
        error: true,
      })
    }

    onComplete(`《${chapter.title}》已重写并保存`)
  } catch (e: any) {
    if (signal.aborted || e?.name === 'AbortError') {
      onComplete('已取消')
      return
    }
    pushProgress({ step: 'error', label: `重写失败：${formatApiError(e)}`, done: true, error: true })
    onError(`重写失败：${formatApiError(e)}`)
  }
}
