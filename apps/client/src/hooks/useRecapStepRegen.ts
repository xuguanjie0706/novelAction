/**
 * 纪要页单步补跑：调用 Bootstrap step regenerate SSE，不依赖 GenerateWizard 时间轴。
 */
import { useCallback, useRef, useState } from 'react'
import { authFetch } from '../api/authFetch'
import {
  llmProviderIdFromRoute,
  modelProfileFromRoute,
  useAppStore,
} from '../store'

/** 纪要页支持补跑的 Bootstrap 步骤（与后端 _SUPPORTED_STEPS 子集对齐） */
export type RecapRegenStep = 'emotion_arc' | 'villain_arc' | 'opening_contract' | 'volumes'

export interface RecapRegenResult {
  count: number
  preview?: string
}

export function useRecapStepRegen() {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [loadingStep, setLoadingStep] = useState<RecapRegenStep | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const runRegen = useCallback(
    async (projectId: string, step: RecapRegenStep): Promise<RecapRegenResult> => {
      if (loadingStep) {
        throw new Error('已有步骤正在生成，请稍候')
      }

      abortRef.current?.abort()
      const abort = new AbortController()
      abortRef.current = abort
      setLoadingStep(step)

      try {
        const res = await authFetch(
          `/api/v1/bootstrap/projects/${projectId}/steps/${step}/regenerate`,
          {
            method: 'POST',
            signal: abort.signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model_profile: modelProfileFromRoute(aiBackendRoute),
              llm_provider_id: llmProviderIdFromRoute(aiBackendRoute),
            }),
          },
        )
        if (!res.ok) {
          const text = await res.text().catch(() => '')
          let detail = text || `重新生成失败 (${res.status})`
          try {
            const parsed = JSON.parse(text) as { detail?: unknown }
            if (typeof parsed.detail === 'string') detail = parsed.detail
          } catch { /* ignore */ }
          throw new Error(detail)
        }
        if (!res.body) throw new Error('响应无流式正文')

        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        let lastDone: RecapRegenResult = { count: 0 }
        let lastError: string | null = null

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
              const evt = JSON.parse(raw) as Record<string, unknown>
              if (evt.event === '__stream_end__') break
              if (evt.event === 'step_done' && evt.step === step) {
                lastDone = {
                  count: typeof evt.count === 'number' ? evt.count : 0,
                  preview: typeof evt.preview === 'string' ? evt.preview : undefined,
                }
              }
              if (evt.event === 'error') {
                lastError = typeof evt.message === 'string'
                  ? evt.message
                  : '生成失败'
              }
            } catch { /* ignore malformed */ }
          }
        }

        if (lastError) throw new Error(lastError)
        return lastDone
      } finally {
        setLoadingStep(null)
      }
    },
    [aiBackendRoute, loadingStep],
  )

  const cancelRegen = useCallback(() => {
    abortRef.current?.abort()
    setLoadingStep(null)
  }, [])

  return { loadingStep, runRegen, cancelRegen }
}
