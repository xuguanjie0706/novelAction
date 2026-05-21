/**
 * @file 队列任务：大纲 Graph 质检
 */
import type { GenTask, GenProgressItem, OutlinePlanQualityReport } from '../../../../types'
import { outlineApi } from '../../../../api/client'
import { formatApiError } from '../../../../utils/apiError'
import { toWsUrl } from '../utils/sseHelpers'

export async function runOutlineQualityCheck(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  signal: AbortSignal,
): Promise<boolean> {
  if (signal.aborted) return false
  const { projectId, params } = task
  pushProgress({
    step: 'outline-quality',
    progressKey: 'outline-quality-launch',
    label: '正在启动大纲 Graph 质检…',
    done: false,
    error: false,
  })
  try {
    const res = await outlineApi.startQualityCheckWorkflow(projectId, {
      model_profile: params.model_profile ?? 'gemini',
      llm_provider_id: params.llm_provider_id,
      theme_statement: params.theme_statement,
      scope: params.scope ?? 'all',
      volume_node_id: params.volume_node_id,
    })
    const runId = res.data.run_id
    if (!runId) throw new Error('后端未返回 workflow run_id')
    pushProgress({
      step: 'outline-quality',
      progressKey: 'outline-quality-launch',
      label: `大纲 Graph 质检已启动：${runId.slice(0, 8)}`,
      done: true,
      error: false,
    })

    return await new Promise<boolean>((resolve) => {
      let settled = false
      const ws = new WebSocket(toWsUrl(outlineApi.qualityCheckWorkflowWsUrl(projectId, runId)))
      const MAX_WORKFLOW_MS = 20 * 60 * 1000
      const MAX_IDLE_MS = 3 * 60 * 1000
      let idleTimer: number | null = null
      const maxTimer = window.setTimeout(() => {
        pushProgress({
          step: 'outline-quality',
          progressKey: 'outline-quality-timeout',
          label: '大纲 Graph 质检超时（20分钟），任务已自动停止',
          done: true,
          error: true,
          outlineQualityScope: 'book',
        })
        finish(false)
      }, MAX_WORKFLOW_MS)
      const refreshIdleTimer = () => {
        if (idleTimer != null) window.clearTimeout(idleTimer)
        idleTimer = window.setTimeout(() => {
          pushProgress({
            step: 'outline-quality',
            progressKey: 'outline-quality-idle-timeout',
            label: '大纲 Graph 质检长时间无进展（3分钟），连接已中断',
            done: true,
            error: true,
            outlineQualityScope: 'book',
          })
          finish(false)
        }, MAX_IDLE_MS)
      }
      const finish = (ok: boolean) => {
        if (settled) return
        settled = true
        signal.removeEventListener('abort', onAbort)
        if (idleTimer != null) {
          window.clearTimeout(idleTimer)
          idleTimer = null
        }
        window.clearTimeout(maxTimer)
        try { ws.close() } catch { /* ignore */ }
        resolve(ok)
      }
      const onAbort = () => finish(false)
      signal.addEventListener('abort', onAbort)
      refreshIdleTimer()

      ws.onmessage = (event) => {
        if (settled) return
        refreshIdleTimer()
        let evt: {
          event?: string
          label?: string
          step?: number | string
          total?: number | string
          done?: boolean
          error?: boolean
          message?: string
          node_key?: string
          progress_key?: string
          outline_quality_report?: unknown
          outline_quality_scope?: 'volume' | 'book'
          result?: OutlinePlanQualityReport & { volume_reports?: unknown[] }
          details?: string[]
        }
        try {
          evt = JSON.parse(event.data)
        } catch {
          return
        }

        if (evt.event === 'truncation_warning') {
          pushProgress({
            step: 'outline-quality-truncation',
            progressKey: `outline-quality-truncation-${Date.now()}`,
            label: evt.label ?? '⚠️ 部分上下文被截断，质检结果可能不完整',
            done: true,
            error: false,
            warning: true,
            warningDetails: evt.details,
          })
          return
        }

        if (evt.event === 'node_start') {
          pushProgress({
            step: evt.node_key || 'outline-quality-node',
            progressKey: `outline-quality-node-${evt.node_key}`,
            label: evt.label ? `Graph 节点开始：${evt.label}` : 'Graph 节点开始',
            done: false,
            error: false,
          })
          return
        }

        if (evt.event === 'node_done') {
          pushProgress({
            step: evt.node_key || 'outline-quality-node',
            progressKey: `outline-quality-node-${evt.node_key}`,
            label: evt.label ? `Graph 节点完成：${evt.label}` : 'Graph 节点完成',
            done: true,
            error: false,
          })
          return
        }

        if (evt.event === 'progress') {
          const rep = evt.outline_quality_report as OutlinePlanQualityReport | undefined
          pushProgress({
            step: evt.step ?? 'outline-quality',
            progressKey: evt.progress_key,
            label: evt.label ?? '',
            done: !!evt.done,
            error: !!evt.error,
            outlineQualityReport: rep,
            outlineQualityScope: evt.outline_quality_scope,
          })
          return
        }

        if (evt.event === 'workflow_started') {
          pushProgress({
            step: 'outline-quality',
            progressKey: 'outline-quality-running',
            label: '大纲 Graph 质检运行中…',
            done: false,
            error: false,
          })
          return
        }

        if (evt.event === 'workflow_done') {
          const report = evt.result as OutlinePlanQualityReport | undefined
          const score = report?.overall_score
          const resultScope = (params.scope === 'volume' ? 'volume' : 'book') as 'volume' | 'book'
          pushProgress({
            step: 'outline-quality',
            progressKey: 'outline-quality-complete',
            label: typeof score === 'number' ? `大纲 Graph 质检完成：${score}分 / ${report?.status || '-'}` : '大纲 Graph 质检完成',
            done: true,
            error: !!report?.error,
            outlineQualityReport: report,
            outlineQualityScope: resultScope,
          })
          finish(!report?.error)
          return
        }

        if (evt.event === 'workflow_error') {
          pushProgress({
            step: 'outline-quality',
            progressKey: 'outline-quality-error',
            label: `大纲 Graph 质检失败：${evt.message || '未知错误'}`,
            done: true,
            error: true,
            outlineQualityScope: 'book',
          })
          finish(false)
        }
      }

      ws.onerror = () => {
        pushProgress({
          step: 'outline-quality',
          progressKey: 'outline-quality-ws-error',
          label: '大纲 Graph 质检进度连接失败',
          done: true,
          error: true,
          outlineQualityScope: 'book',
        })
        finish(false)
      }

      ws.onclose = () => {
        if (!settled && !signal.aborted) {
          pushProgress({
            step: 'outline-quality',
            progressKey: 'outline-quality-ws-closed',
            label: '大纲 Graph 质检连接已关闭，未收到完成事件',
            done: true,
            error: true,
            outlineQualityScope: 'book',
          })
          finish(false)
        }
      }
    })
  } catch (e: any) {
    if (signal.aborted) return false
    pushProgress({
      step: 'outline-quality',
      progressKey: 'outline-quality-book',
      label: `全书大纲质检失败，可稍后重试：${formatApiError(e)}`,
      done: true,
      error: true,
      outlineQualityScope: 'book',
    })
    return false
  }
}
