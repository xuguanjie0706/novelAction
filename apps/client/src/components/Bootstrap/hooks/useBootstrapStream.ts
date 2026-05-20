/**
 * @file useBootstrapStream — Bootstrap SSE 业务逻辑 Hook
 *
 * 职责：
 * - 管理生成流程状态（phase / steps / gate / projectId）
 * - 新版串行：POST /runs → GET /events；支持刷新后 ``reconnectToRun`` 回放事件并重连 SSE（事件带 ``ts`` 时还原步耗时）
 * - single_shot：POST /stream
 * - 会话内 ``sessionStorage`` 记录 run_id（见 ``utils/bootstrapActiveRun``），便于书架/首页提示「继续生成」
 * - ``abortSse``：仅断开当前 fetch/SSE；``cancelRun``：调用 ``POST .../cancel`` 终止后端任务并清理本地状态
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { authFetch } from '../../../api/authFetch'
import {
  clearActiveBootstrapRun,
  saveActiveBootstrapRun,
} from '../../../utils/bootstrapActiveRun'

// ── 类型导出 ──────────────────────────────────────────────────

export type Phase = 'input' | 'generating' | 'gate' | 'done'
/** 与后端 ``gate_pending.step`` 对齐的根闸门步骤 */
export type GatePendingStep = 'positioning' | 'power_systems' | 'characters' | 'volumes'

const GATE_PENDING_STEPS: readonly GatePendingStep[] = [
  'positioning', 'power_systems', 'characters', 'volumes',
]

function isGatePendingStep(s: unknown): s is GatePendingStep {
  return typeof s === 'string' && (GATE_PENDING_STEPS as readonly string[]).includes(s)
}
export type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'blocked'
/** 时间轴分组阶段标识 */
export type StepPhase = 'foundation' | 'world' | 'characters' | 'narrative' | 'blueprint' | 'qa'

export type StepKey =
  | 'positioning' | 'project'
  | 'power_systems' | 'factions' | 'storylines' | 'characters'
  | 'skills' | 'items' | 'settings'
  | 'volumes' | 'memory' | 'relations'
  | 'opening_contract' | 'vol1_chapters' | 'ch1_scenes' | 'consistency'
  // 番茄专属步骤
  | 'contrast_design' | 'golden_finger' | 'face_slap_map'
  | 'power_ladder' | 'opening_5chapters' | 'rhythm_map' | 'signal_audit'
  | 'all' | 'saving'

/** SSE linter_issues_top 单项（章纲阻断时附带） */
export interface LinterIssuePreview {
  rule_id: string
  severity: string
  message: string
  suggestion?: string
  chapter_number_in_volume?: number | null
}

export interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  /** @deprecated 仅保留旧代码引用兼容，新逻辑用 count + preview */
  detail?: string
  inflight: number
  icon: string
  stepColor: string
  phase: StepPhase
  stepNum: string
  desc: string
  startedAt?: number
  completedAt?: number
  count?: number
  preview?: string
  /** vol1_chapters 等步骤 linter 阻断时的 Top 问题列表 */
  linterIssues?: LinterIssuePreview[]
  linterBlockingRules?: string[]
}

export interface StartParams {
  logline: string
  mode: 'sequential' | 'single_shot' | 'fanqie'
  targetWords: number
  modelProfile: string
  llmProviderId?: string | null
}

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
  all:              { icon: '✨', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'SINGLE',    desc: 'AI 单次全量生成世界蓝图（大上下文模式）' },
  saving:           { icon: '💾', stepColor: '#06b6d4', phase: 'foundation', stepNum: 'SAVE',      desc: '将生成结果批量写入数据库' },
  // 番茄专属步骤
  contrast_design:   { icon: '📉', stepColor: '#f97316', phase: 'foundation', stepNum: 'FQ-1',  desc: '设计主角落差（初始状态→触发事件），触发点锁定800字内' },
  golden_finger:     { icon: '✋', stepColor: '#eab308', phase: 'foundation', stepNum: 'FQ-2',  desc: '设计金手指工程（类型/可视化/成长路线图），核心爽感引擎' },
  face_slap_map:     { icon: '👋', stepColor: '#ef4444', phase: 'world',      stepNum: 'FQ-3',  desc: '规划打脸地图（5个对象，首次打脸≤第5章，类型多样性）' },
  power_ladder:      { icon: '🪜', stepColor: '#06b6d4', phase: 'world',      stepNum: 'FQ-4',  desc: '构建权力阶梯（5阶社会结构），最小化世界观设计' },
  opening_5chapters: { icon: '🚀', stepColor: '#f59e0b', phase: 'blueprint',  stepNum: 'FQ-5',  desc: '开局五章工程（算法生死线）：Ch1完读率>60%精确结构规划' },
  rhythm_map:        { icon: '🎵', stepColor: '#8b5cf6', phase: 'blueprint',  stepNum: 'FQ-6',  desc: '爽点节奏图（前50章打标）+ 剧情储量池（3-5个备用支线弧）' },
  signal_audit:      { icon: '✅', stepColor: '#22c55e', phase: 'qa',         stepNum: 'FQ-7',  desc: '番茄算法双校验：类型信号强度 + 爽感密度审计' },
}

const SEQ_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'power_systems', 'factions', 'storylines', 'characters',
  'skills', 'items', 'settings',
  'volumes', 'memory', 'relations',
  'opening_contract', 'vol1_chapters', 'ch1_scenes', 'consistency',
]

/** 番茄专属 Bootstrap 步骤列表（9阶段）*/
const FANQIE_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'contrast_design', 'golden_finger', 'face_slap_map',
  'power_ladder', 'characters',
  'opening_5chapters', 'rhythm_map', 'signal_audit',
]

function getStepKeys(mode: StartParams['mode']): StepKey[] {
  if (mode === 'fanqie') return FANQIE_STEP_KEYS
  return SEQ_STEP_KEYS
}

const STEP_ALIAS: Partial<Record<string, StepKey>> = {
  outline: 'volumes',
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

/** 某步失败后，后续未开始的步骤标记为 blocked，避免 UI 显示仍在继续。 */
function blockStepsAfter(steps: StepState[], failedKey: StepKey): StepState[] {
  const idx = steps.findIndex(s => s.key === failedKey)
  if (idx < 0) return steps
  return steps.map((s, i) => {
    if (i <= idx) return s
    if (s.status === 'pending' || s.status === 'running') {
      return {
        ...s,
        status: 'blocked',
        inflight: 0,
        detail: '等待前序步骤成功',
        completedAt: Date.now(),
      }
    }
    return s
  })
}

/** 用户点击重试：从失败步起重置为 pending，清除 blocked。 */
function resetStepsFromRetry(steps: StepState[], retryKey: StepKey): StepState[] {
  const idx = steps.findIndex(s => s.key === retryKey)
  if (idx < 0) return steps
  return steps.map((s, i) => {
    const fresh = makeStep(s.key)
    if (s.key === retryKey) {
      return { ...fresh, label: s.label }
    }
    if (i > idx && (s.status === 'blocked' || s.status === 'error')) {
      return { ...fresh, label: s.label }
    }
    return s
  })
}

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
  const [gateStep, setGateStep]           = useState<GatePendingStep | null>(null)
  const [gateMessage, setGateMessage]     = useState('')
  const [gatePreview, setGatePreview]     = useState<Record<string, unknown> | null>(null)
  const [haltedStep, setHaltedStep]       = useState<StepKey | null>(null)
  const [retryLoading, setRetryLoading]   = useState(false)
  const [generationStartMs, setGenStartMs] = useState<number | null>(null)
  const [activeLogline, setActiveLogline]   = useState('')

  const abortRef          = useRef<AbortController | null>(null)
  const isSubmittingRef   = useRef(false)
  const streamCompleteRef = useRef(false)
  /** 供 ``cancel()`` 读取最新 run_id，避免闭包陈旧 */
  const runIdRef          = useRef<string | null>(null)
  /** 当前运行模式；供 cancel / reconnect 等回调读取，避免闭包陈旧 */
  const currentModeRef    = useRef<StartParams['mode']>('sequential')

  useEffect(() => {
    runIdRef.current = runId
  }, [runId])

  const patchGateFromSnapshot = useCallback((gateData: Record<string, any> | null | undefined) => {
    if (!gateData || typeof gateData !== 'object') return
    const kind = (gateData as { kind?: string }).kind || 'positioning'
    if (kind === 'positioning' && (gateData as { positioning?: unknown }).positioning) {
      setGateStep('positioning')
      setPositioning((gateData as { positioning: Record<string, any> }).positioning)
      setGateMessage('请确认或修改立项定位后继续生成')
      setGatePreview(null)
      setPhase('gate')
      return
    }
    if (kind === 'power_systems') {
      setGateStep('power_systems')
      setGateMessage('请确认境界体系后继续')
      setGatePreview({ power_systems_count: (gateData as { count?: number }).count ?? 0 })
      setPhase('gate')
      return
    }
    if (kind === 'characters') {
      const gd = gateData as Record<string, unknown>
      const count =
        typeof gd.characters_count === 'number'
          ? gd.characters_count
          : typeof gd.count === 'number'
            ? gd.count
            : 0
      setGateStep('characters')
      setGateMessage('请确认人物库后继续')
      setGatePreview({
        characters_count: count,
        ...(Array.isArray(gd.characters_preview) ? { characters_preview: gd.characters_preview } : {}),
        ...(typeof gd.characters_preview_truncated === 'boolean'
          ? { characters_preview_truncated: gd.characters_preview_truncated }
          : {}),
        ...(typeof gd.relations_count === 'number' ? { relations_count: gd.relations_count } : {}),
        ...(Array.isArray(gd.relations_sample) ? { relations_sample: gd.relations_sample } : {}),
      })
      setPhase('gate')
      return
    }
    if (kind === 'volumes') {
      setGateStep('volumes')
      setGateMessage('请确认卷级骨架后继续')
      setGatePreview({ volumes_count: (gateData as { count?: number }).count ?? 0 })
      setPhase('gate')
    }
  }, [])

  /** 番茄图末步完成后拉取 run 快照收尾（兼容未 emit complete 的旧后端） */
  const tryFinalizeFanqieRun = useCallback(async () => {
    if (streamCompleteRef.current || currentModeRef.current !== 'fanqie') return
    const rid = runIdRef.current
    if (!rid) return
    try {
      const res = await authFetch(`/api/v1/bootstrap/runs/${rid}`)
      if (!res.ok) return
      const run = (await res.json()) as { project_id?: string | null; status?: string }
      if (!run.project_id) return
      streamCompleteRef.current = true
      setProjectId(run.project_id)
      setPhase('done')
      clearActiveBootstrapRun()
    } catch {
      /* 忽略；用户仍可书架进入项目 */
    }
  }, [])

  const handleEvent = useCallback((evt: Record<string, any>) => {
    const { event, step, label, count, preview, message, project_id, positioning, gate_preview } = evt
    const key = toKey(step)
    /** 优先用后端 ``emit`` 写入的 ``ts``（毫秒），重连 replay 时才能还原真实步间耗时 */
    const now =
      typeof evt.ts === 'number' && Number.isFinite(evt.ts) ? (evt.ts as number) : Date.now()

    if (event === 'step_start' && key) {
      setHaltedStep(prev => (prev === key ? null : prev))
      setSteps(prev => prev.map(s =>
        s.key === key
          ? { ...s, status: 'running', inflight: s.inflight + 1,
              label: label ?? s.label, startedAt: s.startedAt ?? now,
              detail: undefined, completedAt: undefined }
          : s
      ))
    } else if (event === 'step_done' && key) {
      const linterBlocked = Boolean(evt.linter_blocked)
      const linterMsg =
        typeof evt.linter_message === 'string' ? evt.linter_message.trim() : ''
      const linterIssuesTop = Array.isArray(evt.linter_issues_top)
        ? (evt.linter_issues_top as LinterIssuePreview[])
        : undefined
      const linterBlockingRules = Array.isArray(evt.linter_blocking_rules)
        ? (evt.linter_blocking_rules as string[])
        : undefined
      let detail = [count != null ? `${count} 条` : '', preview ?? ''].filter(Boolean).join(' · ')
      if (linterBlocked) {
        detail = preview ?? linterMsg ?? '章纲质量门控未通过'
      }
      setSteps(prev => prev.map(s => {
        if (s.key !== key) return s
        const next = Math.max(0, s.inflight - 1)
        const doneStatus = linterBlocked
          ? 'error'
          : (next === 0 ? 'done' : 'running')
        return {
          ...s, inflight: next,
          status: doneStatus,
          detail: detail || s.detail,
          completedAt: now,
          count: count ?? s.count,
          preview: preview ?? s.preview,
          linterIssues: linterBlocked ? linterIssuesTop : undefined,
          linterBlockingRules: linterBlocked ? linterBlockingRules : undefined,
        }
      }))
      if (linterBlocked && (linterMsg || preview)) {
        setErrorMsg(linterMsg || String(preview))
      }
      if (key === 'signal_audit' && currentModeRef.current === 'fanqie') {
        void tryFinalizeFanqieRun()
      }
    } else if (event === 'error' || event === 'step_halted') {
      const msg = (typeof message === 'string' && message.trim()) ? message : '生成失败'
      if (key) {
        setHaltedStep(key)
        setSteps(prev => blockStepsAfter(
          prev.map(s =>
            s.key === key
              ? { ...s, status: 'error', inflight: 0, detail: msg, completedAt: now }
              : s
          ),
          key,
        ))
      }
      setErrorMsg(`${key ? `[${key}] ` : ''}${msg}`)
    } else if (event === 'gate_pending') {
      const gst = isGatePendingStep(step) ? step : 'positioning'
      setGateStep(gst)
      setGateMessage(typeof message === 'string' ? message : '')
      setGatePreview(
        gate_preview && typeof gate_preview === 'object'
          ? (gate_preview as Record<string, unknown>)
          : null,
      )
      if (positioning && typeof positioning === 'object') setPositioning(positioning)
      setPhase('gate')
    } else if (event === 'gate_passed') {
      setPhase('generating')
    } else if (event === 'cancelled') {
      streamCompleteRef.current = true
      clearActiveBootstrapRun()
      setRunId(null)
      setGateStep(null)
      setGateMessage('')
      setGatePreview(null)
      setPhase('input')
      setProjectId(null)
      setPositioning(null)
      setGenStartMs(null)
      setSteps(getStepKeys(currentModeRef.current).map(k => makeStep(k)))
      setErrorMsg('')
    } else if (event === 'complete') {
      streamCompleteRef.current = true
      setProjectId(project_id)
      setPhase('done')
      clearActiveBootstrapRun()
    }
  }, [tryFinalizeFanqieRun])

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

  async function startGenerate(params: StartParams) {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    streamCompleteRef.current = false
    currentModeRef.current = params.mode
    const startMs = Date.now()
    setErrorMsg('')
    setGenStartMs(startMs)
    setActiveLogline(params.logline)
    setPhase('generating')

    if (params.mode === 'single_shot') {
      setSteps([makeStep('all', 'AI 全量生成（单次调用）'), makeStep('saving', '写入数据库')])
    } else {
      setSteps(getStepKeys(params.mode).map(k => makeStep(k)))
      setGateStep(null)
      setGateMessage('')
      setGatePreview(null)
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
        // sequential 和 fanqie 均走 /runs 新协议
        const apiMode = params.mode === 'fanqie' ? 'fanqie' : 'sequential'
        const runRes = await authFetch('/api/v1/bootstrap/runs', {
          method: 'POST', signal: abort.signal,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, mode: apiMode }),
        })
        if (!runRes.ok) throw new Error(await runRes.text().catch(() => `创建失败 (${runRes.status})`))
        const { run_id } = await runRes.json()
        setRunId(run_id)
        saveActiveBootstrapRun({
          runId: run_id,
          logline: params.logline,
          projectId: null,
        })
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
   * 刷新或从书架入口恢复：拉取 run 快照、回放已持久化事件、再订阅 SSE。
   */
  async function reconnectToRun(
    rid: string,
    params: Pick<StartParams, 'modelProfile' | 'llmProviderId'>,
    opts?: { loglineHint?: string },
  ) {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    streamCompleteRef.current = false
    setErrorMsg('')
    setRunId(rid)
    setGateStep(null)
    setGateMessage('')
    setGatePreview(null)
    setPhase('generating')

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const snapRes = await authFetch(`/api/v1/bootstrap/runs/${rid}`, {
        method: 'GET',
        signal: abort.signal,
      })
      if (!snapRes.ok) throw new Error(await snapRes.text().catch(() => `无法恢复 run (${snapRes.status})`))
      const run = await snapRes.json() as {
        status: string
        mode?: string | null
        events?: Array<Record<string, any>>
        gate_data?: Record<string, any> | null
        project_id?: string | null
        error_message?: string | null
        logline?: string | null
        created_at?: string | null
      }

      // 根据快照中的 mode 还原步骤列表与 ref
      const runMode: StartParams['mode'] =
        run.mode === 'fanqie' ? 'fanqie'
        : run.mode === 'single_shot' ? 'single_shot'
        : 'sequential'
      currentModeRef.current = runMode
      setSteps(getStepKeys(runMode).map(k => makeStep(k)))
      setActiveLogline((run.logline || opts?.loglineHint || '').trim())

      if (run.project_id) {
        saveActiveBootstrapRun({
          runId: rid,
          logline: (run.logline || opts?.loglineHint || '').trim() || undefined,
          projectId: run.project_id,
        })
      }

      const anchorMs =
        run.created_at && !Number.isNaN(Date.parse(run.created_at))
          ? Date.parse(run.created_at)
          : Date.now()
      setGenStartMs(anchorMs)

      const evs = run.events || []
      let legacyTsCursor = anchorMs
      for (const ev of evs) {
        const evRec = ev as Record<string, unknown>
        const hasTs = typeof evRec.ts === 'number' && Number.isFinite(evRec.ts as number)
        const evToApply = hasTs
          ? ev
          : { ...evRec, ts: (legacyTsCursor += 200) }
        handleEvent(evToApply as Record<string, any>)
      }

      const hasGatePending = evs.some(e => e.event === 'gate_pending')
      if (run.status === 'awaiting_gate' && !hasGatePending) {
        patchGateFromSnapshot(run.gate_data ?? undefined)
      }

      if (run.status === 'awaiting_retry') {
        const gd = run.gate_data as { step?: string; message?: string } | null | undefined
        const failed = toKey(gd?.step)
        const haltMsg = typeof gd?.message === 'string' ? gd.message : '步骤失败，请重试'
        if (failed) {
          setHaltedStep(failed)
          setErrorMsg(haltMsg)
          setSteps(prev => blockStepsAfter(prev, failed))
        }
      }

      if (run.status === 'done') {
        streamCompleteRef.current = true
        if (run.project_id) setProjectId(run.project_id)
        setPhase('done')
        clearActiveBootstrapRun()
        return
      }
      if (run.status === 'failed' || run.status === 'cancelled') {
        setErrorMsg(run.error_message || `生成已${run.status === 'failed' ? '失败' : '取消'}`)
        setPhase('input')
        clearActiveBootstrapRun()
        return
      }

      const evtRes = await authFetch(`/api/v1/bootstrap/runs/${rid}/events`, { signal: abort.signal })
      if (!evtRes.ok) throw new Error(`SSE 重连失败 (${evtRes.status})`)
      await readSse(evtRes)
      if (!streamCompleteRef.current && !abort.signal.aborted) {
        setErrorMsg(prev => prev || '连接已结束但未完成生成，请重试或从书架继续。')
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') setErrorMsg(err.message || '恢复失败')
    } finally {
      isSubmittingRef.current = false
    }
  }

  async function retryFailedStep(
    step: StepKey,
    params: Pick<StartParams, 'modelProfile' | 'llmProviderId'>,
  ) {
    const rid = runIdRef.current ?? runId
    if (!rid) return
    setRetryLoading(true)
    try {
      const res = await authFetch(`/api/v1/bootstrap/runs/${rid}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'retry_step',
          step,
          model_profile: params.modelProfile,
          llm_provider_id: params.llmProviderId ?? null,
        }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `重试失败 (${res.status})`)
      }
      setHaltedStep(null)
      setErrorMsg('')
      setSteps(prev => resetStepsFromRetry(prev, step))
      setPhase('generating')
      if (streamCompleteRef.current) {
        streamCompleteRef.current = false
        abortRef.current?.abort()
        const abort = new AbortController()
        abortRef.current = abort
        const evtRes = await authFetch(`/api/v1/bootstrap/runs/${rid}/events`, {
          signal: abort.signal,
        })
        if (evtRes.ok) void readSse(evtRes)
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : '重试失败')
    } finally {
      setRetryLoading(false)
    }
  }

  async function handleResume(
    payload: { action: 'approve' | 'regenerate', positioning?: Record<string, unknown> | null },
    params: Pick<StartParams, 'modelProfile' | 'llmProviderId'>,
  ) {
    const rid = runIdRef.current ?? runId
    if (!rid) return
    try {
      const body: Record<string, unknown> = {
        action: payload.action,
        model_profile: params.modelProfile,
        llm_provider_id: params.llmProviderId ?? null,
      }
      if (payload.positioning != null) body.positioning = payload.positioning
      const res = await authFetch(`/api/v1/bootstrap/runs/${rid}/resume`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        let detail = text || `resume 失败 (${res.status})`
        try {
          const parsed = JSON.parse(text) as { detail?: unknown }
          if (typeof parsed.detail === 'string') detail = parsed.detail
          else if (parsed.detail != null) detail = JSON.stringify(parsed.detail)
        } catch { /* 非 JSON 则沿用原文 */ }
        throw new Error(detail)
      }
      setErrorMsg('')
      setPhase('generating')
    } catch (err: any) {
      setErrorMsg(err.message || 'resume 失败')
      setPhase('gate')
    }
  }

  function abortSse() {
    abortRef.current?.abort()
  }

  /**
   * 请求后端取消 LangGraph run，并复位前端状态（与顶条「终止」一致）。
   * @returns 是否已成功收到成功响应（无 run_id 时视为已清理本地状态）
   */
  async function cancelRun(): Promise<boolean> {
    abortSse()
    streamCompleteRef.current = true
    const rid = runIdRef.current
    isSubmittingRef.current = false

    if (rid) {
      try {
        const res = await authFetch(`/api/v1/bootstrap/runs/${rid}/cancel`, { method: 'POST' })
        if (!res.ok) {
          const t = await res.text().catch(() => '')
          setErrorMsg(t.trim() || `终止失败（${res.status}）`)
          streamCompleteRef.current = false
          return false
        }
        clearActiveBootstrapRun()
        setRunId(null)
        setGateStep(null)
        setGateMessage('')
        setGatePreview(null)
        setPhase('input')
        setProjectId(null)
        setPositioning(null)
        setGenStartMs(null)
        setSteps(getStepKeys(currentModeRef.current).map(k => makeStep(k)))
        setErrorMsg('')
        return true
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : '终止请求失败'
        setErrorMsg(msg)
        streamCompleteRef.current = false
        return false
      }
    }

    clearActiveBootstrapRun()
    setPhase('input')
    setGateStep(null)
    setGateMessage('')
    setGatePreview(null)
    setProjectId(null)
    setPositioning(null)
    setGenStartMs(null)
    setSteps(getStepKeys(currentModeRef.current).map(k => makeStep(k)))
    return true
  }

  return {
    phase, steps, errorMsg, projectId, positioningData, runId, generationStartMs,
    gateStep, gateMessage, gatePreview, activeLogline,
    haltedStep, retryLoading,
    startGenerate, reconnectToRun, handleResume, retryFailedStep, abortSse, cancelRun,
  }
}
