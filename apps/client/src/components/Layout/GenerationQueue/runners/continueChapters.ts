/**
 * @file 队列任务：多章续写
 */
import type { Chapter, GenTask, GenProgressItem, MemoryChunk } from '../../../../types'
import { aiApi, chaptersApi } from '../../../../api/client'
import { authFetch } from '../../../../api/authFetch'
import { formatApiError } from '../../../../utils/apiError'
import { autoCommitGeneratedChapterDebrief } from '../../../../utils/generatedChapterDebrief'
import { postDraftAssistAccumulatedWithPrewriteRetry } from '../../../../utils/draftPrewriteBlocked'
import {
  splitStreamedDraftText,
  parseChapterIndexMarkdown,
  fallbackChapterIndexFromRawMarkdown,
} from '../../../../utils/draftChapterIndexSplit'
import { useAppStore } from '../../../../store'
import {
  draftAssistSideEventHandler,
  manuscriptRawSnapshotForContinue,
  plainTextDraftToHtml,
} from '../utils/sseHelpers'

export async function runContinueChapters(
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
  const chapterIds: string[] = Array.isArray(params.chapterIds) ? params.chapterIds : []
  const userPrompt: string = typeof params.userPrompt === 'string' ? params.userPrompt : ''
  const modelProfile: 'local' | 'gemini' = params.modelProfile ?? 'local'
  const llmProviderId: string | undefined = params.llm_provider_id

  let successCount = 0
  for (let i = 0; i < chapterIds.length; i++) {
    if (signal.aborted) {
      onComplete(`已取消（已完成 ${successCount}/${chapterIds.length} 章）`)
      return
    }

    const chapterId = chapterIds[i]
    let chapter: Chapter
    try {
      const chapterRes = await chaptersApi.get(projectId, chapterId)
      chapter = chapterRes.data
    } catch (e: any) {
      pushProgress({ step: i + 1, label: `读取第 ${i + 1} 章失败：${formatApiError(e)}`, done: true, error: true })
      onError(`读取章节失败，已完成 ${successCount}/${chapterIds.length} 章`)
      return
    }

    const stepLabel = `${chapter.title}（${i + 1}/${chapterIds.length}）`
    const phaseStep = (phase: string) => `${i + 1}-${phase}`
    pushProgress({ step: phaseStep('draft'), label: `正在生成正文 ${stepLabel}…`, done: false, error: false })

    let accumulated = ''
    try {
      accumulated = await postDraftAssistAccumulatedWithPrewriteRetry(
        authFetch,
        `/api/v1/projects/${projectId}/ai/draft-assist/stream`,
        {
          chapter_id: chapterId,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
          user_prompt: userPrompt.trim() || null,
          replace_existing: false,
        },
        {
          signal,
          onSideEvent: draftAssistSideEventHandler(pushProgress, phaseStep, chapterId),
        },
      )

      if (!accumulated.trim()) throw new Error('未收到正文内容')

      const { body: draftBody, indexMarkdown } = splitStreamedDraftText(accumulated.trim())
      if (!draftBody.trim()) throw new Error('未收到叙事正文（可能只有索引块）')

      pushProgress({ step: phaseStep('draft'), label: `✓ 正文生成完成 ${stepLabel}`, done: true, error: false })
      pushProgress({ step: phaseStep('save'), label: `正在保存叙事正文 ${stepLabel}…`, done: false, error: false })

      try {
        if ((chapter.content || '').trim()) {
          await chaptersApi.snapshot(projectId, chapterId, 'AI续写追加前自动备份', true)
        }
      } catch {
        /* 快照失败不阻断保存 */
      }

      const appendedHtml = plainTextDraftToHtml(draftBody.trim())
      const nextContent = `${chapter.content || ''}${chapter.content ? '\n' : ''}${appendedHtml}`
      const manuscript_raw_snapshot = manuscriptRawSnapshotForContinue(chapter.content, accumulated.trim())
      const updateRes = await chaptersApi.update(projectId, chapterId, {
        content: nextContent,
        manuscript_raw_snapshot,
      })
      upsertChapter(updateRes.data)
      pushProgress({ step: phaseStep('save'), label: `✓ ${stepLabel} 已保存（仅叙事；稿末见模型调用记录）`, done: true, error: false })

      // 读取项目质量门槛（writing_config.min_overall_score，默认 0 即始终入库）
      const minOverallScore = (() => {
        const ex = (useAppStore.getState().currentProject as any)?.extra
        const cfg = (ex && typeof ex === 'object') ? (ex as Record<string, any>).writing_config : null
        return typeof cfg?.min_overall_score === 'number' ? cfg.min_overall_score : 0
      })()
      let indexPersistedFromDraft = false

      pushProgress({ step: phaseStep('quality'), label: `正在质检 ${stepLabel}…`, done: false, error: false })
      try {
        const qualityRes = await aiApi.qualityCheck(projectId, {
          chapter_id: chapterId,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        })
        const score = Number(qualityRes.data?.overall_score)
        pushProgress({
          step: phaseStep('quality'),
          label: Number.isFinite(score) ? `✓ 质检完成：${score.toFixed(1)}/10` : '✓ 质检完成',
          done: true,
          error: false,
        })
        const refreshedChapter = await chaptersApi.get(projectId, chapterId)
        upsertChapter(refreshedChapter.data)

        // 质检通过阈值后才解析稿末索引入库，避免低分稿污染 ChapterIndex
        if (indexMarkdown && Number.isFinite(score) && score >= minOverallScore) {
          pushProgress({ step: phaseStep('index'), label: `正在写入 ChapterIndex ${stepLabel}…`, done: false, error: false })
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
            pushProgress({ step: phaseStep('index'), label: `✓ 索引已从流式稿末解析入库（质检 ${score.toFixed(1)} ≥ ${minOverallScore}）`, done: true, error: false })
          } catch (e: any) {
            pushProgress({
              step: phaseStep('index'),
              label: `索引解析入库失败：${formatApiError(e)}`,
              done: true,
              error: true,
            })
          }
        } else if (indexMarkdown && Number.isFinite(score) && score < minOverallScore) {
          pushProgress({
            step: phaseStep('index'),
            label: `跳过索引入库（质检 ${score.toFixed(1)} < 阈值 ${minOverallScore}，重写通过后再入库）`,
            done: true,
            error: false,
          })
        }
      } catch (e: any) {
        pushProgress({
          step: phaseStep('quality'),
          label: `质检失败，可稍后手动检查：${formatApiError(e)}`,
          done: true,
          error: true,
        })
      }

      pushProgress({ step: phaseStep('debrief'), label: `正在复盘并写入 ChapterIndex ${stepLabel}…`, done: false, error: false })
      try {
        const applied = await autoCommitGeneratedChapterDebrief(
          projectId,
          chapterId,
          modelProfile,
          llmProviderId,
          { omitChapterIndex: indexPersistedFromDraft },
        )
        if (applied.debriefPreview && typeof applied.debriefPreview === 'object') {
          useAppStore.getState().setQueueDebriefUiSnapshot(chapterId, applied.debriefPreview as Record<string, unknown>)
        }
        markChapterDebriefCommitted(chapterId)
        const indexLabel =
          applied.chapterIndexSaved || indexPersistedFromDraft ? 'ChapterIndex 已写入' : 'ChapterIndex 未更新'
        pushProgress({
          step: phaseStep('debrief'),
          label: `✓ 复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${indexLabel}`,
          done: true,
          error: false,
        })
      } catch (e: any) {
        pushProgress({
          step: phaseStep('debrief'),
          label: `自动复盘失败，已中止连续续写（避免下一章在旧状态下生成）：${formatApiError(e)}`,
          done: true,
          error: true,
        })
        onError(`复盘失败，已中止续写链：${stepLabel}。${formatApiError(e)}`)
        return
      }

      pushProgress({ step: phaseStep('memory'), label: '正在刷新记忆库…', done: false, error: false })
      try {
        const memoriesRes = await aiApi.listMemory(projectId)
        setMemories(memoriesRes.data)
        pushProgress({ step: phaseStep('memory'), label: `✓ 记忆库已刷新：${memoriesRes.data.length} 条`, done: true, error: false })
      } catch (e: any) {
        pushProgress({
          step: phaseStep('memory'),
          label: `记忆库刷新失败：${formatApiError(e)}`,
          done: true,
          error: true,
        })
      }

      pushProgress({ step: phaseStep('done'), label: `✓ ${stepLabel} 流程完成`, done: true, error: false })
      successCount++
    } catch (e: any) {
      if (signal.aborted || e?.name === 'AbortError') {
        onComplete(`已取消（已完成 ${successCount}/${chapterIds.length} 章）`)
        return
      }
      pushProgress({ step: i + 1, label: `✗ ${stepLabel} 失败：${formatApiError(e)}`, done: true, error: true })
      onError(`续写中断：${stepLabel} 失败，已完成 ${successCount}/${chapterIds.length} 章`)
      return
    }
  }

  onComplete(`多章续写完成：${successCount}/${chapterIds.length} 章已保存`)
}

