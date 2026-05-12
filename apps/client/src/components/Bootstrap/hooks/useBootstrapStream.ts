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
 */
import { useRef, useState } from 'react'
import { authFetch } from '../../../api/authFetch'

// ── 类型导出 ──────────────────────────────────────────────────

export type Phase = 'input' | 'generating' | 'gate' | 'done'
export type StepStatus = 'pending' | 'running' | 'done' | 'error'
/** 时间轴分组阶段标识 */
export type StepPhase = 'foundation' | 'world' | 'characters' | 'narrative' | 'blueprint' | 'qa'

export type StepKey =
  | 'positioning' | 'project'
  | 'power_systems' | 'factions' | 'storylines' | 'characters'
  | 'skills' | 'items' | 'settings'
  | 'volumes' | 'memory' | 'relations'
  | 'opening_contract' | 'vol1_chapters' | 'ch1_scenes' | 'consistency'
  | 'all' | 'saving'

export interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  /** @deprecated 仅保留旧代码引用兼容，新逻辑用 count + preview */
  detail?: string
  inflight: number
  // ── 静态元数据（初始化时写入，不随事件变化）────────────────
  icon: string
  stepColor: string
  phase: StepPhase
  stepNum: string
  desc: string
  // ── 时序数据（由 step_start / step_done 事件填充）──────────
  /** Date.now() when step_start received; null = not started yet */
  startedAt?: number
  /** Date.now() when step_done received */
  completedAt?: number
  /** 条目数量，来自 SSE step_done.count */
  count?: number
  /** 预览文本，来自 SSE step_done.preview */
  preview?: string
}

export interface StartParams {
  logline: string
  mode: 'sequential' | 'single_shot'
  targetWords: number
  modelProfile: string
  llmProviderId?: string | null
}

// ── 步骤元数据 ────────────────────────────────────────────────

/** 每个步骤的静态展示元数据，供时间轴与详情面板使用 */
export const STEP_META: Record<StepKey, {
  icon: string; stepColor: string; phase: StepPhase; stepNum: string; desc: string
}> = {
  positioning:      { icon: '🎯', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'STEP 0',    desc: '从一句话创意推导全局约束，是后续所有步骤的基准锚点' },
  project:          { icon: '📚', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'STEP 1',    desc: '创建项目基础记录，写入书名、题材与立项定位' },
  power_systems:    { icon: '⚡', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 2',    desc: '构建力量进阶体系，决定主角成长曲线与境界门槛' },
  factions:         { icon: '🏰', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 3',    desc: '构建世界权力版图，设计主角需要面对的势力格局' },
  storylines:       { icon: '🔮', stepColor: '#8b5cf6', phase: 'characters', stepNum: 'STEP 4',    desc: '规划贯穿全书的叙事主轴，明确追读动力来源' },
  characters:       { icon: '👤', stepColor: '#22c55e', phase: 'characters', stepNum: 'STEP 5',    desc: '创建核心人物档案，包含背景、性格、弧线与关系' },
  skills:           { icon: '⚔️', stepColor: '#ef4444', phase: 'characters', stepNum: 'STEP 6',    desc: '生成核心技能功法，分配给对应角色' },
  items:            { icon: '💎', stepColor: '#eab308', phase: 'characters', stepNum: 'STEP 7',    desc: '生成关键道具与法宝，埋下伏笔与稀缺资源节点' },
  settings:         { icon: '🌍', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 8',    desc: '生成世界底层规则、地理格局、历史传说等叙事性设定卡' },
  volumes:          { icon: '📖', stepColor: '#a78bfa', phase: 'narrative',  stepNum: 'STEP 9',    desc: '规划全书卷级骨架，为每卷分配叙事阶段标记' },
  memory:           { icon: '🧠', stepColor: '#ec4899', phase: 'narrative',  stepNum: 'STEP 10',   desc: '注入长篇记忆系统的初始知识种子，供后续章节检索' },
  relations:        { icon: '🕸️', stepColor: '#22c55e', phase: 'characters', stepNum: 'STEP 11',   desc: '建立人物关系网络，明确情感张力与社会结构' },
  opening_contract: { icon: '🤝', stepColor: '#22c55e', phase: 'narrative',  stepNum: 'STEP 12',   desc: '明确前10章对读者的追读承诺，防止开局流失' },
  vol1_chapters:    { icon: '📋', stepColor: '#f97316', phase: 'blueprint',  stepNum: 'STEP 12.5', desc: '将第一卷骨架拆解为可执行的章节级写作计划' },
  ch1_scenes:       { icon: '🎬', stepColor: '#f97316', phase: 'blueprint',  stepNum: 'STEP 13',   desc: '将第1章章纲拆解为可直接执行的逐场写作蓝图' },
  consistency:      { icon: '🔍', stepColor: '#ef4444', phase: 'qa',         stepNum: 'STEP 14',   desc: '交叉核验所有生成物，标出矛盾与需要确认的问题' },
  // single_shot 专用
  all:              { icon: '✨', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'SINGLE',    desc: 'AI 单次全量生成世界蓝图（大上下文模式）' },
  saving:           { icon: '💾', stepColor: '#06b6d4', phase: 'foundation', stepNum: 'SAVE',      desc: '将生成结果批量写入数据库' },
}

/** sequential 模式下按 SSE 推进顺序排列的步骤 key 列表 */
const SEQ_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'power_systems', 'factions', 'storylines', 'characters',
  'skills', 'items', 'settings',
  'volumes', 'memory', 'relations',
  'opening_contract', 'vol1_chapters', 'ch1_scenes', 'consistency',
]

/** 后端 SSE step 字段 → 前端 StepKey 映射（仅需覆盖不一致的别名） */
const STEP_ALIAS: Partial<Record<string, StepKey>> = {
  outline: 'volumes',  // 旧后端版本兼容
}

function makeStep(key: StepKey, overrideLabel?: string): StepState {
  const meta = STEP_META[key]
  return {
    key, label: overrideLabel ?? meta.stepNum,
    status: 'pending', inflight: 0,
    ...meta,
  }
}

function toKey(step: unknown): StepKey | null {
  if (typeof step !== 'string') return null
  if (step in STEP_META) return step as StepKey
  return STEP_ALIAS[step] ?? null
}

// ── Hook ──────────────────────────────────────────────────────

/** @returns Bootstrap 生成流程的全部状态与操作 */
export function useBootstrapStream() {
  const [phase, setPhase]                 = useState<Phase>('input')
  const [steps, setSteps]                 = useState<StepState[]>(
    SEQ_STEP_KEYS.map(k => makeStep(k))
  )
  const [errorMsg, setErrorMsg]           = useState('')
  const [projectId, setProjectId]         = useState<string | null>(null)
  const [positioningData, setPositioning] = useState<Record<string, any> | null>(null)
  const [runId, setRunId]                 = useState<string | null>(null)
  /** 生成开始的时间戳（ms），用于计算各步骤的时间偏移 */
  const [generationStartMs, setGenStartMs] = useState<number | null>(null)

  const abortRef          = useRef<AbortController | null>(null)
  const isSubmittingRef   = useRef(false)
  const streamCompleteRef = useRef(false)

  // ── 事件处理 ──────────────────────────────────────────────

  function handleEvent(evt: Record<string, any>) {
    const { event, step, label, count, preview, message, project_id, positioning } = evt
    const key = toKey(step)
    const now = Date.now()

    if (event === 'step_start' && key) {
      setSteps(prev => prev.map(s =>
        s.key === key
          ? { ...s, status: 'running', inflight: s.inflight + 1,
              label: label ?? s.label, startedAt: s.startedAt ?? now }
          : s
      ))
    } else if (event === 'step_done' && key) {
      const detail = [count != null ? `${count} 条` : '', preview ?? ''].filter(Boolean).join(' · ')
      setSteps(prev => prev.map(s => {
        if (s.key !== key) return s
        const next = Math.max(0, s.inflight - 1)
        return {
          ...s, inflight: next,
          status: next === 0 ? 'done' : 'running',
          detail: detail || s.detail,
          completedAt: now,
          count: count ?? s.count,
          preview: preview ?? s.preview,
        }
      }))
    } else if (event === 'error') {
      const msg = (typeof message === 'string' && message.trim()) ? message : '生成失败'
      if (key) {
        setSteps(prev => prev.map(s =>
          s.key === key
            ? { ...s, status: 'error', inflight: Math.max(0, s.inflight - 1),
                detail: msg, completedAt: now }
            : s
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

  // ── SSE 读取循环 ───────────────────────────────────────────

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
   * sequential 模式走新的两阶段流；single_shot 走旧 /stream 端点。
   */
  async function startGenerate(params: StartParams) {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    streamCompleteRef.current = false
    const startMs = Date.now()
    setErrorMsg('')
    setGenStartMs(startMs)
    setPhase('generating')

    if (params.mode === 'single_shot') {
      setSteps([makeStep('all', 'AI 全量生成（单次调用）'), makeStep('saving', '写入数据库')])
    } else {
      setSteps(SEQ_STEP_KEYS.map(k => makeStep(k)))
    }

    const abort = new AbortController()
    abortRef.current = abort
    const body = {
      logline: params.logline, target_words: params.targetWords,
      model_profile: params.modelProfile, llm_provider_id: params.llmProviderId ?? null,
    }

    try {
      if (params.mode === 'single_shot') {
        const res = await authFetch('/api/v1/bootstrap/stream', {
          method: 'POST', signal: abort.signal,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, mode: 'single_shot' }),
        })
        if (!res.ok) throw new Error(await res.text().catch(() => `请求失败 (${res.status})`))
        await readSse(res)
      } else {
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
  async function handleResume(
    positioning: Record<string, any>,
    params: Pick<StartParams, 'modelProfile' | 'llmProviderId'>,
  ) {
    if (!runId) return
    try {
      const res = await authFetch(`/api/v1/bootstrap/runs/${runId}/resume`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          positioning,
          model_profile: params.modelProfile,
          llm_provider_id: params.llmProviderId ?? null,
        }),
      })
      if (!res.ok) throw new Error(await res.text().catch(() => `resume 失败 (${res.status})`))
    } catch (err: any) {
      setErrorMsg(err.message || 'resume 失败')
      setPhase('gate')
    }
  }

  function cancel() { abortRef.current?.abort() }

  return {
    phase, steps, errorMsg, projectId, positioningData, runId, generationStartMs,
    startGenerate, handleResume, cancel,
  }
}
