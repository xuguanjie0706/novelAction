/**
 * @file useBootstrapStepRegen — 单步重新生成 Hook
 *
 * 调用 POST /bootstrap/projects/{pid}/steps/{step}/regenerate，
 * 读取 SSE 流并通过回调 onEvent 把 step_start / step_done / error 回传给父组件，
 * 父组件（BootstrapPage/useBootstrapStream）再用 handleEvent 更新步骤状态，
 * 与主流程事件处理共用同一套逻辑，不需要维护独立状态。
 *
 * 依赖：
 *   - projectId（从 useBootstrapStream 取）
 *   - onEvent(evt)（传入 useBootstrapStream 的 handleEvent）
 */
import { useCallback, useRef, useState } from 'react'
import { authFetch } from '../../../api/authFetch'
import type { StepKey } from './useBootstrapStream'

export interface RegenParams {
  modelProfile: string
  llmProviderId?: string | null
}

export interface UseBootstrapStepRegenReturn {
  /** 正在重跑的步骤 key，null 表示无重跑进行中 */
  regenStep: StepKey | null
  /** 最近一次重跑的错误信息 */
  regenError: string | null
  /** 发起单步重跑 */
  triggerRegen: (step: StepKey, projectId: string, params: RegenParams) => Promise<void>
  /** 清除错误 */
  clearRegenError: () => void
}

export function useBootstrapStepRegen(
  onEvent: (evt: Record<string, any>) => void,
): UseBootstrapStepRegenReturn {
  const [regenStep, setRegenStep] = useState<StepKey | null>(null)
  const [regenError, setRegenError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const triggerRegen = useCallback(
    async (step: StepKey, projectId: string, params: RegenParams) => {
      // 同时只允许一个步骤重跑
      if (regenStep) return

      abortRef.current?.abort()
      const abort = new AbortController()
      abortRef.current = abort

      setRegenStep(step)
      setRegenError(null)

      try {
        const res = await authFetch(
          `/api/v1/bootstrap/projects/${projectId}/steps/${step}/regenerate`,
          {
            method: 'POST',
            signal: abort.signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model_profile: params.modelProfile,
              llm_provider_id: params.llmProviderId ?? null,
            }),
          },
        )
        if (!res.ok) {
          const text = await res.text().catch(() => '')
          let detail = text || `重新生成请求失败 (${res.status})`
          try {
            const parsed = JSON.parse(text) as { detail?: unknown }
            if (typeof parsed.detail === 'string') detail = parsed.detail
          } catch { /* 非 JSON 则沿用原文 */ }
          throw new Error(detail)
        }

        // 读取 SSE 流，直接把事件透传给 handleEvent
        if (!res.body) throw new Error('响应无流式正文')
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (!raw || raw === '[DONE]') continue
            try {
              const evt = JSON.parse(raw) as Record<string, any>
              if (evt.event === '__stream_end__') break
              onEvent(evt)
            } catch { /* ignore malformed */ }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return
        const msg = err instanceof Error ? err.message : '重新生成失败'
        setRegenError(msg)
        // 推送 error 事件让步骤状态回到 error 态
        onEvent({ event: 'error', step, message: msg, ts: Date.now() })
      } finally {
        setRegenStep(null)
      }
    },
    [regenStep, onEvent],
  )

  const clearRegenError = useCallback(() => setRegenError(null), [])

  return { regenStep, regenError, triggerRegen, clearRegenError }
}
