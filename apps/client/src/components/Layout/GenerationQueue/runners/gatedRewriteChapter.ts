/**
 * @file 队列任务：质量门控写作
 */
import type { Chapter, GenTask, GenProgressItem, MemoryChunk } from '../../../../types'
import { aiApi, chaptersApi } from '../../../../api/client'
import { authFetch } from '../../../../api/authFetch'
import { formatApiError } from '../../../../utils/apiError'
import { autoCommitGeneratedChapterDebrief } from '../../../../utils/generatedChapterDebrief'
import { authFetchGatedDraftStreamWithPrewriteRetry } from '../../../../utils/draftPrewriteBlocked'
import { formatRagContextProgressLabel } from '../../../../utils/draftAssistSse'
import { useAppStore } from '../../../../store'

export async function runGatedRewriteChapter(
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

  pushProgress({ step: 'start', label: '质量门控写作已开始…', done: false, error: false })

  const strategyLabel: Record<string, string> = {
    initial: '初稿',
    patch: '定点修复',
    full_rewrite: '全量重写',
  }

  let lastOverall = 0
  let lastSubscribe = 0
  let gateOutcome: 'passed' | 'failed' | null = null

  try {
    const res = await authFetchGatedDraftStreamWithPrewriteRetry(
      authFetch,
      aiApi.gatedDraftStreamUrl(projectId),
      {
        chapter_id: chapterId,
        model_profile: modelProfile,
        ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        user_prompt: userPrompt.trim() || null,
        replace_existing: true,
      },
      { signal },
    )

    if (!res.body) throw new Error('响应无流式内容')

    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let currentAttempt = 1
    let draftAccumulated = ''     // 当前轮次文字累积（显示字数用）

    const processLine = (line: string) => {
      const t = line.trim()
      if (!t.startsWith('data:')) return
      const raw = t.slice(5).trimStart()
      if (raw === '[DONE]') return

      let obj: Record<string, unknown>
      try { obj = JSON.parse(raw) } catch { return }

      if (obj.error) throw new Error(obj.error as string)

      const ev = obj.event as string | undefined

      if (ev === 'rag_context') {
        pushProgress({
          step: 'rag_context',
          label: formatRagContextProgressLabel(obj),
          done: true,
          error: false,
        })
        return
      }

      // 结构化事件处理
      if (ev === 'gate_config') {
        const warnEnabled = obj.pre_write_warning_enabled === true
        const hookOn = obj.hook_mandate_active === true
        const fsEn = obj.enforce_face_slap_payoff_when_hook_required === true
        const blk = obj.block_on_consistency_issues === true || obj.block_on_realm_mismatch === true
        const extras: string[] = []
        if (warnEnabled) extras.push('写前预警已开启')
        if (hookOn && fsEn) extras.push('爽点结算章将卡 face_slap_payoff')
        if (blk) extras.push('写前硬门已开启')
        const extraStr = extras.length ? ` · ${extras.join(' · ')}` : ''
        pushProgress({
          step: 'gate_config',
          label: `门控配置：综合分≥${obj.min_overall_score} / 订阅意愿≥${obj.min_subscribe_intent}，最多${obj.max_rewrite_attempts}次${extraStr ? `${extraStr}` : ''}`,
          done: true,
          error: false,
        })
        return
      }

      if (ev === 'pre_warn_running') {
        pushProgress({
          step: 'pre_warn',
          label: '写前预警：30年主编正在审稿（主角状态/幻觉预防/写法简报）…',
          done: false,
          error: false,
        })
        return
      }

      if (ev === 'pre_warn_done') {
        const ok = obj.ok !== false
        const riskCount = typeof obj.risk_count === 'number' ? obj.risk_count : 0
        const errMsg = typeof obj.error === 'string' ? obj.error : null
        const ragLogId = typeof obj.rag_retrieval_log_id === 'string' ? obj.rag_retrieval_log_id : null
        const reused = obj.reused === true
        pushProgress({
          step: 'pre_warn',
          label: errMsg
            ? `写前预警：${errMsg}`
            : reused
              ? `写前预警：复用本章已有记录（${riskCount} 处风险，已跳过主编审稿；简报已注入 prompt）`
              : ok
                ? `写前预警完成（发现 ${riskCount} 处风险，简报已注入 prompt${ragLogId ? `；RAG log ${ragLogId.slice(0, 8)}` : ''}）`
                : `写前预警：发现 ${riskCount} 处风险需注意，简报已注入 prompt`,
          done: true,
          error: !!errMsg,
        })
        return
      }

      if (ev === 'attempt_start') {
        currentAttempt = obj.attempt as number
        draftAccumulated = ''
        const strategy = strategyLabel[obj.strategy as string] ?? (obj.strategy as string)
        pushProgress({
          step: `attempt_${currentAttempt}_draft`,
          label: `第 ${currentAttempt}/${obj.max_attempts} 轮 · ${strategy} · 正在起笔…`,
          done: false,
          error: false,
        })
        return
      }

      if (ev === 'attempt_done') {
        pushProgress({
          step: `attempt_${currentAttempt}_draft`,
          label: `✓ 第 ${currentAttempt} 轮正文完成（${obj.words}字）`,
          done: true,
          error: false,
        })
        return
      }

      if (ev === 'qc_running') {
        pushProgress({
          step: `attempt_${currentAttempt}_qc`,
          label: `第 ${currentAttempt} 轮质检中…`,
          done: false,
          error: false,
        })
        return
      }

      if (ev === 'qc_result') {
        lastOverall = obj.overall_score as number
        lastSubscribe = obj.subscribe_intent as number
        const scoreLabel = `综合 ${(lastOverall).toFixed(1)} / 订阅 ${(lastSubscribe).toFixed(1)}`
        pushProgress({
          step: `attempt_${currentAttempt}_qc`,
          label: `✓ 质检完成：${scoreLabel}`,
          done: true,
          error: false,
        })
        return
      }

      if (ev === 'gate_passed') {
        gateOutcome = 'passed'
        pushProgress({
          step: 'gate_result',
          label: `✅ 质量达标（第 ${obj.attempt} 轮）— 综合 ${(obj.overall_score as number).toFixed(1)} / 订阅 ${(obj.subscribe_intent as number).toFixed(1)}`,
          done: true,
          error: false,
        })
        return
      }

      if (ev === 'rewrite_queued') {
        const nextStrategy = strategyLabel[obj.strategy as string] ?? (obj.strategy as string)
        pushProgress({
          step: `rewrite_queued_${obj.next_attempt}`,
          label: `△ 未达标（综合 ${(obj.overall_score as number).toFixed(1)} / 订阅 ${(obj.subscribe_intent as number).toFixed(1)}），准备第 ${obj.next_attempt} 轮 · ${nextStrategy}`,
          done: true,
          error: false,
        })
        return
      }

      if (ev === 'gate_failed') {
        gateOutcome = 'failed'
        pushProgress({
          step: 'gate_result',
          label: `⏸ 达到最大次数仍未达标 — 综合 ${(obj.final_score as number).toFixed(1)} / 订阅 ${(obj.final_subscribe_intent as number).toFixed(1)}，章节已标记「待审阅」`,
          done: true,
          error: false,
        })
        return
      }

      // 普通文字 chunk — 追加字数显示
      if (typeof obj.text === 'string') {
        draftAccumulated += obj.text
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) processLine(line)
    }
    for (const line of buf.split('\n')) processLine(line)

    // 流结束后刷新章节
    try {
      const refreshed = await chaptersApi.get(projectId, chapterId)
      upsertChapter(refreshed.data)
    } catch { /* ignore */ }

    // 起草阶段已不再输出稿末 ### ch_ 索引；情节档案/伏笔同步改由 auto-debrief → chapter-debrief 写入
    if (gateOutcome === 'passed') {
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
          label: `✓ 复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${indexLabel}`,
          done: true,
          error: false,
        })
      } catch (e: any) {
        pushProgress({
          step: 'debrief',
          label: `自动复盘失败，线索页可能为空，请在写作页手动「AI 复盘」：${formatApiError(e)}`,
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
    }

    if (gateOutcome === 'passed') {
      onComplete(`质量门控写作完成（综合 ${lastOverall.toFixed(1)} / 订阅 ${lastSubscribe.toFixed(1)}）`)
    } else if (gateOutcome === 'failed') {
      onComplete(`写作已暂停，章节标记为「待审阅」（综合 ${lastOverall.toFixed(1)} / 订阅 ${lastSubscribe.toFixed(1)}）`)
    } else {
      onComplete('质量门控写作流程结束')
    }
  } catch (e: any) {
    if (signal.aborted) return
    pushProgress({ step: 'error', label: `门控写作失败：${formatApiError(e)}`, done: true, error: true })
    onError(`门控写作失败：${formatApiError(e)}`)
  }
}
