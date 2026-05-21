/**
 * @file 队列任务：大纲 Graph 修复（含连续卷修复）
 */
import type { GenTask, GenProgressItem, OutlinePlanQualityReport } from '../../../../types'
import { outlineApi } from '../../../../api/client'
import { formatApiError } from '../../../../utils/apiError'
import { toWsUrl } from '../utils/sseHelpers'

const DEFAULT_VOLUME_CONTINUOUS_REPAIR_ROUNDS = 5

/** 连续修复提前结束：pass，或综合分不低于阈值（与 UI continuous_min_score 一致） */
function volumeOutlineRepairShouldStop(
  report: OutlinePlanQualityReport | undefined,
  minScore: number | undefined,
): 'pass' | 'score' | null {
  if (!report) return null
  if (report.status === 'pass') return 'pass'
  if (minScore != null && report.overall_score != null) {
    const s = Number(report.overall_score)
    if (Number.isFinite(s) && s >= minScore) return 'score'
  }
  return null
}

/** 与大纲质检 overall_score / 时间线 quality_score 一致，0–100 */
function parseContinuousMinScore(params: Record<string, unknown>): number | undefined {
  const v = params.continuous_min_score
  if (v === undefined || v === null || v === '') return undefined
  const n = Number(v)
  if (!Number.isFinite(n)) return undefined
  return Math.min(100, Math.max(0, n))
}

type OutlineRepairRoundMeta = { round: number; maxRounds: number }

/** 执行单轮大纲 Graph 修复工作流，返回是否成功及 workflow 最终质检结果 */
export async function runSingleOutlineRepairRound(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  signal: AbortSignal,
  roundMeta?: OutlineRepairRoundMeta,
): Promise<{ ok: boolean; report?: OutlinePlanQualityReport }> {
  if (signal.aborted) return { ok: false }
  const { projectId, params } = task
  const roundHint =
    roundMeta && roundMeta.maxRounds > 1
      ? `（第 ${roundMeta.round}/${roundMeta.maxRounds} 轮）`
      : ''
  pushProgress({
    step: 'outline-repair',
    progressKey: 'outline-repair-launch',
    label: `正在启动大纲 Graph 修复${roundHint}…`,
    done: false,
    error: false,
  })
  try {
    const res = await outlineApi.startRepairWorkflow(projectId, {
      model_profile: params.model_profile ?? 'gemini',
      llm_provider_id: params.llm_provider_id,
      theme_statement: params.theme_statement,
      scope: params.scope ?? 'all',
      volume_node_id: params.volume_node_id,
      use_linter_seed: params.use_linter_seed ?? true,
      linter_must_fix_chapter_numbers: params.linter_must_fix_chapter_numbers,
    })
    const runId = res.data.run_id
    if (!runId) throw new Error('后端未返回 workflow run_id')
    pushProgress({
      step: 'outline-repair',
      progressKey: 'outline-repair-launch',
      label: `大纲 Graph 修复已启动${roundHint}：${runId.slice(0, 8)}`,
      done: true,
      error: false,
    })

    return await new Promise<{ ok: boolean; report?: OutlinePlanQualityReport }>((resolve) => {
      let settled = false
      const ws = new WebSocket(toWsUrl(outlineApi.qualityCheckWorkflowWsUrl(projectId, runId)))
      const finish = (ok: boolean, report?: OutlinePlanQualityReport) => {
        if (settled) return
        settled = true
        signal.removeEventListener('abort', onAbort)
        try { ws.close() } catch { /* ignore */ }
        resolve({ ok, report })
      }
      const onAbort = () => finish(false)
      signal.addEventListener('abort', onAbort)

      ws.onmessage = (event) => {
        if (settled) return
        let evt: {
          event?: string
          label?: string
          step?: number | string
          done?: boolean
          error?: boolean
          message?: string
          node_key?: string
          progress_key?: string
          outline_quality_report?: unknown
          outline_quality_scope?: 'volume' | 'book'
          result?: { summary?: string; status?: string; overall_score?: number; [key: string]: unknown }
          details?: string[]
        }
        try {
          evt = JSON.parse(event.data)
        } catch {
          return
        }

        if (evt.event === 'truncation_warning') {
          pushProgress({
            step: 'outline-repair-truncation',
            progressKey: `outline-repair-truncation-${Date.now()}`,
            label: evt.label ?? '⚠️ 部分上下文被截断，修复质量可能受影响',
            done: true,
            error: false,
            warning: true,
            warningDetails: evt.details,
          })
          return
        }

        if (evt.event === 'node_start' || evt.event === 'node_done') {
          const done = evt.event === 'node_done'
          pushProgress({
            step: evt.node_key || 'outline-repair-node',
            progressKey: `outline-repair-node-${evt.node_key}`,
            label: evt.label ? `Graph 节点${done ? '完成' : '开始'}：${evt.label}` : `Graph 节点${done ? '完成' : '开始'}`,
            done,
            error: false,
          })
          return
        }

        if (evt.event === 'progress') {
          const rep = evt.outline_quality_report as OutlinePlanQualityReport | undefined
          pushProgress({
            step: evt.step ?? 'outline-repair',
            progressKey: evt.progress_key ?? `outline-repair-${evt.step ?? Date.now()}`,
            label: evt.label ?? '',
            done: !!evt.done,
            error: !!evt.error,
            outlineQualityReport: rep,
            outlineQualityScope: evt.outline_quality_scope,
          })
          return
        }

        if (evt.event === 'workflow_done') {
          const rep = evt.result as OutlinePlanQualityReport | undefined
          const failed = evt.result?.status === 'error'
          pushProgress({
            step: 'outline-repair',
            progressKey: 'outline-repair-complete',
            label: evt.result?.summary
              ? `${roundHint ? `${roundHint.trim()} ` : ''}${evt.result.summary}`
              : `大纲 Graph 修复完成${roundHint}`,
            done: true,
            error: failed,
            outlineQualityReport: rep,
          })
          finish(!failed, rep)
          return
        }

        if (evt.event === 'workflow_error') {
          pushProgress({
            step: 'outline-repair',
            progressKey: 'outline-repair-error',
            label: `大纲 Graph 修复失败：${evt.message || '未知错误'}`,
            done: true,
            error: true,
          })
          finish(false)
        }
      }

      ws.onerror = () => {
        pushProgress({
          step: 'outline-repair',
          progressKey: 'outline-repair-ws-error',
          label: '大纲 Graph 修复进度连接失败',
          done: true,
          error: true,
        })
        finish(false)
      }

      ws.onclose = () => {
        if (!settled && !signal.aborted) {
          pushProgress({
            step: 'outline-repair',
            progressKey: 'outline-repair-ws-closed',
            label: '大纲 Graph 修复连接已关闭，未收到完成事件',
            done: true,
            error: true,
          })
          finish(false)
        }
      }
    })
  } catch (e: any) {
    if (signal.aborted) return { ok: false }
    pushProgress({
      step: 'outline-repair',
      progressKey: 'outline-repair-error',
      label: `大纲修复失败：${formatApiError(e)}`,
      done: true,
      error: true,
    })
    return { ok: false }
  }
}

export async function runOutlineRepair(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  signal: AbortSignal,
): Promise<boolean> {
  const { params } = task
  const scope = params.scope ?? 'all'
  const continuous =
    params.continuous_repair !== false
    && scope === 'volume'
    && Boolean(params.volume_node_id)

  const rawMax = Number(params.continuous_max_rounds)
  const maxRounds = continuous
    ? Math.min(20, Math.max(1, Number.isFinite(rawMax) && rawMax > 0 ? rawMax : DEFAULT_VOLUME_CONTINUOUS_REPAIR_ROUNDS))
    : 1
  const minScore = continuous ? parseContinuousMinScore(params as Record<string, unknown>) : undefined

  if (!continuous || maxRounds === 1) {
    const { ok } = await runSingleOutlineRepairRound(task, pushProgress, signal)
    return ok
  }

  let lastOk = false
  let lastReport: OutlinePlanQualityReport | undefined
  for (let round = 1; round <= maxRounds; round++) {
    if (signal.aborted) return false
    const meta: OutlineRepairRoundMeta = { round, maxRounds }
    const { ok, report } = await runSingleOutlineRepairRound(task, pushProgress, signal, meta)
    lastOk = ok
    lastReport = report
    if (!ok) return false
    const stopWhy = volumeOutlineRepairShouldStop(report, minScore)
    if (stopWhy) {
      const scoreLabel = report?.overall_score ?? '-'
      const label =
        stopWhy === 'pass'
          ? `第 ${round}/${maxRounds} 轮后质检已通过（status pass · score ${scoreLabel}），停止连续修复`
          : `第 ${round}/${maxRounds} 轮后总分已达阈值（≥${minScore ?? '?'}，当前 ${scoreLabel}），停止连续修复`
      pushProgress({
        step: 'outline-repair',
        progressKey: stopWhy === 'pass' ? 'outline-repair-pass' : 'outline-repair-score',
        label,
        done: true,
        error: false,
        outlineQualityReport: report,
      })
      return true
    }
    if (round < maxRounds) {
      pushProgress({
        step: 'outline-repair',
        progressKey: `outline-repair-between-${round}`,
        label: `第 ${round}/${maxRounds} 轮后仍未达标（${report?.status ?? '?'} · score ${report?.overall_score ?? '-'}），自动开始下一轮…`,
        done: true,
        error: false,
        outlineQualityReport: report,
      })
    }
  }

  pushProgress({
    step: 'outline-repair',
    progressKey: 'outline-repair-max-rounds',
    label: `已连续修复 ${maxRounds} 轮；最新质检 ${lastReport?.status ?? '?'} · score ${lastReport?.overall_score ?? '-'}`,
    done: true,
    error: false,
    outlineQualityReport: lastReport,
  })
  return lastOk
}
