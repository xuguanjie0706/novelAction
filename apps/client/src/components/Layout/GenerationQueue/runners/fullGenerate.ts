/**
 * @file 队列任务：全书大纲生成
 */
import type { GenTask, GenProgressItem, OutlinePlanQualityReport } from '../../../../types'
import { authFetch } from '../../../../api/authFetch'
import { formatApiError } from '../../../../utils/apiError'
import { parseSseDataLine } from '../utils/sseHelpers'

export async function runFullGenerate(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
): Promise<boolean> {
  const { projectId, params } = task
  let res: Response
  try {
    res = await authFetch(`/api/v1/projects/${projectId}/outline/ai-full-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
      signal,
    })
  } catch (e: any) {
    if (e?.name === 'AbortError') return false
    onError(formatApiError(e) || '网络请求失败')
    return false
  }

  if (!res.ok) {
    onError(`HTTP ${res.status}`)
    return false
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let settled = false
  const wrapComplete = (msg: string) => {
    if (settled) return
    settled = true
    onComplete(msg)
  }
  const wrapError = (msg: string) => {
    if (settled) return
    settled = true
    onError(msg)
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue
        let evt: {
          event?: string
          label?: string
          step?: number
          done?: boolean
          error?: boolean
          message?: string
          progress_key?: string
          outline_quality_report?: unknown
          outline_quality_scope?: 'volume' | 'book'
        }
        try {
          evt = JSON.parse(raw)
        } catch {
          continue
        }
        if (evt.event === 'progress') {
          const rep = evt.outline_quality_report as OutlinePlanQualityReport | undefined
          pushProgress({
            step: evt.step ?? 0,
            progressKey: evt.progress_key,
            label: evt.label ?? '',
            done: !!evt.done,
            error: !!evt.error,
            outlineQualityReport: rep as OutlinePlanQualityReport | undefined,
            outlineQualityScope: evt.outline_quality_scope,
          })
        } else if (evt.event === 'complete') {
          wrapComplete(evt.message || '生成完成')
          return true
        } else if (evt.event === 'error') {
          wrapError(evt.message || '生成失败')
          return false
        }
      }
    }
    if (!settled && !signal.aborted) {
      wrapError('连接已结束，未收到生成完成事件（可能网络中断或后端异常）')
    }
    return false
  } catch (e: any) {
    if (e?.name === 'AbortError') return false
    wrapError(formatApiError(e) || '流读取异常')
    return false
  }
}
