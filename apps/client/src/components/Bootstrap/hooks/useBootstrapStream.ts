/**
 * @file useBootstrapStream — Bootstrap SSE 业务逻辑 Hook
 *
 * 职责：
 * - 管理生成流程状态（phase / steps / errors / projectId / positioningData）
 * - 封装新版两阶段 SSE 流（POST /runs → GET /runs/{id}/events）
 * - 封装旧版单次 SSE 流（POST /stream，single_shot 模式专用）
 * - 暴露 startGenerate / handleResume / cancel 给 GenerateWizard 调用
 *
 * 设计约束：
 * - phase / steps 等状态完全由本 hook 管理，GenerateWizard 只做渲染
 * - gate_pending 事件触发 phase → 'gate'，前端展示确认面板
 * - gate 期间 SSE 连接保持活跃（后端不推 __stream_end__）
 * - 本文件 < 200 行
 */
import { useRef, useState } from 'react'
import { authFetch } from '../../../api/authFetch'

// ── 类型导出（GenerateWizard 也要用）──────────────────────────
export type Phase = 'input' | 'generating' | 'gate' | 'done'
export type StepStatus = 'pending' | 'running' | 'done' | 'error'
export type StepKey =
  | 'project' | 'settings' | 'characters' | 'outline' | 'memory' | 'relations'
  | 'opening_contract' | 'vol1_chapters' | 'ch1_scenes' | 'consistency'
  | 'all' | 'saving'

export interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  detail?: string
  inflight: number
}

export interface StartParams {
  logline: string
  mode: 'sequential' | 'single_shot'
  targetWords: number
  modelProfile: string
  llmProviderId?: string | null
}

// ── Step 定义（与 GenerateWizard 的 STEP_DEFS 对齐）────────────
const STEP_DEFS: { key: StepKey; label: string }[] = [
  { key: 'project',          label: '项目基础信息' },
  { key: 'settings',         label: '世界观设定卡' },
  { key: 'characters',       label: '人物库' },
  { key: 'outline',          label: '卷级结构规划' },
  { key: 'memory',           label: '记忆库种子' },
  { key: 'relations',        label: '人物关系' },
  { key: 'opening_contract', label: '开局追读承诺' },
  { key: 'vol1_chapters',    label: '第一卷章级大纲' },
  { key: 'ch1_scenes',       label: '第1章场景蓝图' },
  { key: 'consistency',      label: '全局一致性扫描' },
]

const STEP_ALIAS: Record<string, StepKey> = {
  positioning: 'project', power_systems: 'settings', factions: 'settings',
  storylines: 'settings', skills: 'settings', items: 'settings',
  settings: 'settings', volumes: 'outline',
  opening_contract: 'opening_contract', vol1_chapters: 'vol1_chapters',
  ch1_scenes: 'ch1_scenes', consistency: 'consistency',
}

function toKey(step: unknown): StepKey | null {
  if (typeof step !== 'string') return null
  if (STEP_DEFS.some(s => s.key === step)) return step as StepKey
  return STEP_ALIAS[step] ?? null
}

// ── Hook ──────────────────────────────────────────────────────

/** @returns Bootstrap 生成流程的全部状态与操作 */
export function useBootstrapStream() {
  const [phase, setPhase]               = useState<Phase>('input')
  const [steps, setSteps]               = useState<StepState[]>(
    STEP_DEFS.map(s => ({ ...s, status: 'pending', inflight: 0 }))
  )
  const [errorMsg, setErrorMsg]         = useState('')
  const [projectId, setProjectId]       = useState<string | null>(null)
  const [positioningData, setPositioning] = useState<Record<string, any> | null>(null)
  const [runId, setRunId]               = useState<string | null>(null)

  const abortRef            = useRef<AbortController | null>(null)
  const isSubmittingRef     = useRef(false)
  const streamCompleteRef   = useRef(false)

  // ── 事件处理 ──────────────────────────────────────────────

  function handleEvent(evt: Record<string, any>) {
    const { event, step, label, count, preview, message, project_id, positioning } = evt
    const key = toKey(step)

    if (event === 'step_start' && key) {
      setSteps(prev => prev.map(s =>
        s.key === key ? { ...s, status: 'running', inflight: s.inflight + 1, label: label ?? s.label } : s
      ))
    } else if (event === 'step_done' && key) {
      const detail = [count != null ? `${count} 条` : '', preview ?? ''].filter(Boolean).join(' · ')
      setSteps(prev => prev.map(s => {
        if (s.key !== key) return s
        const next = Math.max(0, s.inflight - 1)
        return { ...s, inflight: next, status: next === 0 ? 'done' : 'running', detail: detail || s.detail }
      }))
    } else if (event === 'error') {
      const msg = (typeof message === 'string' && message.trim()) ? message : '生成失败'
      if (key) {
        setSteps(prev => prev.map(s =>
          s.key === key ? { ...s, status: 'error', inflight: Math.max(0, s.inflight - 1), detail: msg } : s
        ))
      }
      setErrorMsg(`${key ? `[${key}] ` : ''}${msg}`)
    } else if (event === 'gate_pending') {
      setPositioning(positioning || {})
      setPhase('gate')
    } else if (event === 'gate_passed') {
      setPhase('generating')
    } else if (event === 'complete') {
      streamCompleteRef.current = true
      setProjectId(project_id)
      setPhase('done')
    }
  }

  // ── SSE 读取循环（供 startGenerate / handleResume 复用）──────

  async function readSse(res: Response) {
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
        try { handleEvent(JSON.parse(raw)) } catch { /* ignore malformed */ }
      }
    }
  }

  // ── 主入口 ────────────────────────────────────────────────

  /**
   * 启动 Bootstrap 生成。
   * sequential 模式走新的 LangGraph 两阶段流；single_shot 走旧 /stream 端点。
   */
  async function startGenerate(params: StartParams) {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    streamCompleteRef.current = false
    setErrorMsg('')
    setPhase('generating')
    if (params.mode === 'single_shot') {
      setSteps([
        { key: 'all',    label: 'AI 全量生成（单次调用）', status: 'running',  inflight: 1 },
        { key: 'saving', label: '写入数据库',               status: 'pending',  inflight: 0 },
      ])
    } else {
      // 顺序模式完全以 SSE 的 step_start/step_done 驱动状态，避免预置 inflight 导致计数失衡。
      setSteps(STEP_DEFS.map((s) => ({ ...s, status: 'pending', inflight: 0 })))
    }

    const abort = new AbortController()
    abortRef.current = abort
    const body = { logline: params.logline, target_words: params.targetWords,
                   model_profile: params.modelProfile, llm_provider_id: params.llmProviderId ?? null }

    try {
      if (params.mode === 'single_shot') {
        // 旧端点：SSE 直连
        const res = await authFetch('/api/v1/bootstrap/stream', {
          method: 'POST', signal: abort.signal,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, mode: 'single_shot' }),
        })
        if (!res.ok) throw new Error(await res.text().catch(() => `请求失败 (${res.status})`))
        await readSse(res)
      } else {
        // 新端点：POST /runs → GET /runs/{id}/events
        const runRes = await authFetch('/api/v1/bootstrap/runs', {
          method: 'POST', signal: abort.signal,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, mode: 'sequential' }),
        })
        if (!runRes.ok) throw new Error(await runRes.text().catch(() => `创建失败 (${runRes.status})`))
        const { run_id } = await runRes.json()
        setRunId(run_id)
        const evtRes = await authFetch(`/api/v1/bootstrap/runs/${run_id}/events`, { signal: abort.signal })
        if (!evtRes.ok) throw new Error(`SSE 连接失败 (${evtRes.status})`)
        await readSse(evtRes)
      }
      if (!streamCompleteRef.current && !abort.signal.aborted) {
        setErrorMsg(prev => prev || '连接已结束但未完成生成，请查看后端日志后重试。')
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') setErrorMsg(err.message || '网络错误')
    } finally {
      isSubmittingRef.current = false
    }
  }

  /**
   * 用户在 gate 面板确认立项定位后调用，向后端提交 resume。
   * SSE 连接仍活跃，事件将继续流入 readSse 循环。
   */
  async function handleResume(positioning: Record<string, any>, params: Pick<StartParams, 'modelProfile' | 'llmProviderId'>) {
    if (!runId) return
    try {
      const res = await authFetch(`/api/v1/bootstrap/runs/${runId}/resume`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positioning, model_profile: params.modelProfile, llm_provider_id: params.llmProviderId ?? null }),
      })
      if (!res.ok) throw new Error(await res.text().catch(() => `resume 失败 (${res.status})`))
    } catch (err: any) {
      setErrorMsg(err.message || 'resume 失败')
      setPhase('gate')  // 回退到 gate 让用户重试
    }
  }

  function cancel() {
    abortRef.current?.abort()
  }

  return { phase, steps, errorMsg, projectId, positioningData, runId,
           startGenerate, handleResume, cancel }
}
