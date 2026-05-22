/**
 * @file 队列任务：单章重写
 */
import type { Chapter, GenTask, GenProgressItem, MemoryChunk } from '../../../../types'
import { aiApi, chaptersApi } from '../../../../api/client'
import { authFetch } from '../../../../api/authFetch'
import { formatApiError } from '../../../../utils/apiError'
import { autoCommitGeneratedChapterDebrief } from '../../../../utils/generatedChapterDebrief'
import { postDraftAssistAccumulatedWithPrewriteRetry } from '../../../../utils/draftPrewriteBlocked'
import { splitStreamedDraftText, parseChapterIndexMarkdown, fallbackChapterIndexFromRawMarkdown } from '../../../../utils/draftChapterIndexSplit'
import { useAppStore } from '../../../../store'
import { ragContextSideEventHandler, plainTextDraftToHtml } from '../utils/sseHelpers'

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
        onSideEvent: ragContextSideEventHandler(pushProgress, 'rag_context'),
      },
    )

    if (!accumulated.trim()) throw new Error('未收到正文内容')

    const { body: draftBody, indexMarkdown } = splitStreamedDraftText(accumulated.trim())
    if (!draftBody.trim()) throw new Error('未收到叙事正文（可能只有索引块）')

    pushProgress({ step: 'draft', label: `✓ 《${chapter.title}》重写完成，正在保存…`, done: true, error: false })
    try {
      if ((chapter.content || '').trim()) {
        await chaptersApi.snapshot(projectId, chapterId, 'AI重写正文前自动备份', true)
      }
    } catch {
      /* 快照失败不阻断保存 */
    }
    const updateRes = await chaptersApi.update(projectId, chapterId, {
      content: plainTextDraftToHtml(draftBody.trim()),
      manuscript_raw_snapshot: accumulated.trim(),
    })
    upsertChapter(updateRes.data)
    pushProgress({ step: 'save', label: '✓ 已保存叙事正文（稿末见模型调用记录）', done: true, error: false })

    // 读取项目质量门槛（writing_config.min_overall_score，默认 0 即始终入库）
    const minOverallScore = (() => {
      const ex = (useAppStore.getState().currentProject as any)?.extra
      const cfg = (ex && typeof ex === 'object') ? (ex as Record<string, any>).writing_config : null
      return typeof cfg?.min_overall_score === 'number' ? cfg.min_overall_score : 0
    })()
    let indexPersistedFromDraft = false

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

      // 质检通过阈值后才解析稿末索引入库，避免低分稿污染 ChapterIndex
      if (indexMarkdown && Number.isFinite(score) && score >= minOverallScore) {
        pushProgress({ step: 'index', label: '正在写入 ChapterIndex…', done: false, error: false })
        try {
          const parsed = parseChapterIndexMarkdown(indexMarkdown)
          const chapter_index = parsed ?? fallbackChapterIndexFromRawMarkdown(indexMarkdown)
          await aiApi.chapterDebrief(projectId, {
            chapter_id: chapterId,
            chapter_index,
            apply_source: 'queue_auto',
            model_profile: modelProfile,
            ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
          })
          indexPersistedFromDraft = true
          pushProgress({ step: 'index', label: `✓ 索引已从流式稿末解析入库（质检 ${score.toFixed(1)} ≥ ${minOverallScore}）`, done: true, error: false })
        } catch (e: any) {
          pushProgress({
            step: 'index',
            label: `索引解析入库失败：${formatApiError(e)}`,
            done: true,
            error: true,
          })
        }
      } else if (indexMarkdown && Number.isFinite(score) && score < minOverallScore) {
        pushProgress({
          step: 'index',
          label: `跳过索引入库（质检 ${score.toFixed(1)} < 阈值 ${minOverallScore}，重写通过后再入库）`,
          done: true,
          error: false,
        })
      }
    } catch (e: any) {
      pushProgress({
        step: 'quality',
        label: `质检失败，可稍后手动检查：${formatApiError(e)}`,
        done: true,
        error: true,
      })
    }

    pushProgress({ step: 'debrief', label: '正在自动复盘人物、故事线、记忆和 ChapterIndex…', done: false, error: false })
    try {
      useAppStore.getState().resetChapterDebriefQueueState(chapterId)
      const applied = await autoCommitGeneratedChapterDebrief(
        projectId,
        chapterId,
        modelProfile,
        llmProviderId,
        { omitChapterIndex: indexPersistedFromDraft, forceRefresh: true },
      )
      if (applied.debriefPreview && typeof applied.debriefPreview === 'object') {
        useAppStore.getState().setQueueDebriefUiSnapshot(chapterId, applied.debriefPreview as Record<string, unknown>)
      }
      markChapterDebriefCommitted(chapterId)
      pushProgress({
        step: 'debrief',
        label: `✓ 自动复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${
          applied.chapterIndexSaved || indexPersistedFromDraft ? 'ChapterIndex 已写入' : 'ChapterIndex 未更新'
        }`,
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
