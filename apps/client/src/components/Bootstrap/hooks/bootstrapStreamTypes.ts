/**
 * @file bootstrapStreamTypes — Bootstrap SSE 流程的类型、常量与纯工具函数
 *
 * 含：Phase / StepKey 等所有枚举类型、STEP_META 元数据表、
 * SEQ_STEP_KEYS / FANQIE_STEP_KEYS 步骤列表、makeStep / toKey 等辅助函数，
 * 以及 blockStepsAfter / resetStepsFromRetry / applyGateSnapshot 等纯状态更新函数。
 *
 * 本文件无 React 依赖，可独立于渲染上下文测试。
 */

// ── Types ──────────────────────────────────────────────────────
export type Phase = 'input' | 'generating' | 'gate' | 'done'
/** 与后端 ``gate_pending.step`` 对齐的根闸门步骤 */
export type GatePendingStep = 'positioning' | 'power_systems' | 'characters' | 'volumes'

export const GATE_PENDING_STEPS: readonly GatePendingStep[] = [
  'positioning', 'power_systems', 'characters', 'volumes',
]

export function isGatePendingStep(s: unknown): s is GatePendingStep {
  return typeof s === 'string' && (GATE_PENDING_STEPS as readonly string[]).includes(s)
}

export type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'blocked'
/** 时间轴分组阶段标识 */
export type StepPhase = 'foundation' | 'world' | 'characters' | 'narrative' | 'blueprint' | 'qa'

export type StepKey =
  | 'positioning' | 'project'
  | 'power_systems' | 'factions' | 'storylines' | 'antagonist_ladder' | 'characters'
  | 'skills' | 'items' | 'settings'
  | 'volumes' | 'emotion_arc' | 'villain_arc' | 'memory' | 'relations'
  | 'core_mysteries' | 'opening_contract' | 'consistency'
  /** 时间轴汇总 / 落库中（仅 UI 图标，非 graph 步骤） */
  | 'all' | 'saving'
  // 番茄专属步骤
  | 'contrast_design' | 'golden_finger' | 'face_slap_map'
  | 'power_ladder' | 'rhythm_map' | 'signal_audit'
  // 同人·番茄专属
  | 'canon_pack' | 'deviation_contract' | 'entry_hook'
  | 'canon_power' | 'canon_characters' | 'canon_audit'

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
  /** linter 阻断时的 Top 问题列表 */
  linterIssues?: LinterIssuePreview[]
  linterBlockingRules?: string[]
}

export interface FanficStartMeta {
  source_work_title: string
  canon_synopsis: string
  fanfic_trope: 'transmigration' | 'rebirth' | 'au'
  focal_characters?: string
}

export interface StartParams {
  logline: string
  mode: 'sequential' | 'fanqie' | 'fanfic' | 'xianxia'
  targetWords: number
  modelProfile: string
  llmProviderId?: string | null
  /** 为 true 时自动通过闸门；步骤失败不自动重试 */
  autoMode?: boolean
  writingStyle?: 'plain' | 'standard' | 'dense'
  fanficMeta?: FanficStartMeta
}

// ── Constants ──────────────────────────────────────────────────
export const STEP_META: Record<StepKey, {
  icon: string; stepColor: string; phase: StepPhase; stepNum: string; desc: string
}> = {
  positioning:       { icon: '🎯', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'STEP 0',  desc: '从一句话创意推导全局约束，是后续所有步骤的基准锚点' },
  project:           { icon: '📚', stepColor: '#f59e0b', phase: 'foundation', stepNum: 'STEP 1',  desc: '创建项目基础记录，写入书名、题材与立项定位' },
  power_systems:     { icon: '⚡', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 2',  desc: '构建力量进阶体系，决定主角成长曲线与境界门槛' },
  factions:          { icon: '🏰', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 3',  desc: '构建世界权力版图，设计主角需要面对的势力格局' },
  storylines:        { icon: '🔮', stepColor: '#8b5cf6', phase: 'characters', stepNum: 'STEP 4',  desc: '规划贯穿全书的叙事主轴，明确追读动力来源' },
  antagonist_ladder:   { icon: '👹', stepColor: '#dc2626', phase: 'characters', stepNum: 'STEP 4.5', desc: '登记每卷核心对立面（Boss 名+境界），作为人物与卷骨架的唯一来源' },
  characters:        { icon: '👤', stepColor: '#22c55e', phase: 'characters', stepNum: 'STEP 5',  desc: '创建核心人物档案，包含背景、性格、弧线与关系' },
  skills:            { icon: '⚔️', stepColor: '#ef4444', phase: 'characters', stepNum: 'STEP 6',  desc: '生成核心技能功法，分配给对应角色' },
  items:             { icon: '💎', stepColor: '#eab308', phase: 'characters', stepNum: 'STEP 7',  desc: '生成关键道具与法宝，埋下伏笔与稀缺资源节点' },
  settings:          { icon: '🌍', stepColor: '#06b6d4', phase: 'world',      stepNum: 'STEP 8',  desc: '生成世界底层规则、地理格局、历史传说等叙事性设定卡' },
  volumes:           { icon: '📖', stepColor: '#a78bfa', phase: 'narrative',  stepNum: 'STEP 9',  desc: '规划全书卷级骨架，为每卷分配叙事阶段标记' },
  emotion_arc:       { icon: '🎭', stepColor: '#ec4899', phase: 'narrative',  stepNum: 'STEP 9.5', desc: '规划全书情绪节律图，标记每卷情绪收支' },
  villain_arc:       { icon: '😈', stepColor: '#dc2626', phase: 'narrative',  stepNum: 'STEP 9.8', desc: '生成反派独立行动线，与主角成长轴对位' },
  memory:            { icon: '🧠', stepColor: '#ec4899', phase: 'narrative',  stepNum: 'STEP 10', desc: '注入长篇记忆系统的初始知识种子，供后续章节检索' },
  relations:         { icon: '🕸️', stepColor: '#22c55e', phase: 'characters', stepNum: 'STEP 11', desc: '建立人物关系网络，明确情感张力与社会结构' },
  core_mysteries:    { icon: '🔮', stepColor: '#8b5cf6', phase: 'narrative',  stepNum: 'STEP 11.5', desc: '预分配全书跨卷核心谜题，埋下追更伏笔' },
  opening_contract:  { icon: '🤝', stepColor: '#22c55e', phase: 'narrative',  stepNum: 'STEP 12', desc: '明确前10章对读者的追读承诺，防止开局流失' },
  consistency:       { icon: '🔍', stepColor: '#ef4444', phase: 'qa',         stepNum: 'STEP 13', desc: '交叉核验所有生成物，标出矛盾与需要确认的问题' },
  all:               { icon: '📋', stepColor: '#94a3b8', phase: 'qa',         stepNum: '—',       desc: '全部步骤汇总视图' },
  saving:            { icon: '💾', stepColor: '#94a3b8', phase: 'qa',         stepNum: '—',       desc: '正在写入数据库' },
  // 番茄专属
  contrast_design:   { icon: '📉', stepColor: '#f97316', phase: 'foundation', stepNum: 'FQ-1', desc: '设计主角落差（初始状态→触发事件），触发点锁定800字内' },
  golden_finger:     { icon: '✋', stepColor: '#eab308', phase: 'foundation', stepNum: 'FQ-2', desc: '设计金手指工程（类型/可视化/成长路线图），核心爽感引擎' },
  face_slap_map:     { icon: '👋', stepColor: '#ef4444', phase: 'world',      stepNum: 'FQ-3', desc: '规划打脸地图（5个对象，首次打脸≤第5章，类型多样性）' },
  power_ladder:      { icon: '🪜', stepColor: '#06b6d4', phase: 'world',      stepNum: 'FQ-4', desc: '构建权力阶梯（5阶社会结构），最小化世界观设计' },
  rhythm_map:        { icon: '🎵', stepColor: '#8b5cf6', phase: 'blueprint',  stepNum: 'FQ-5', desc: '爽点节奏图（前50章打标）+ 剧情储量池（3-5个备用支线弧）' },
  signal_audit:      { icon: '✅', stepColor: '#22c55e', phase: 'qa',         stepNum: 'FQ-6', desc: '番茄算法双校验：类型信号强度 + 爽感密度审计' },
  canon_pack:        { icon: '📜', stepColor: '#6366f1', phase: 'foundation', stepNum: 'FF-1', desc: '将作者填写的原著梗概结构化为世界观/人物/不可改事实' },
  deviation_contract:{ icon: '⚖️', stepColor: '#8b5cf6', phase: 'foundation', stepNum: 'FF-2', desc: '明确魔改边界：允许改动、禁止改动、CP/主线承诺' },
  entry_hook:        { icon: '🪝', stepColor: '#f97316', phase: 'foundation', stepNum: 'FF-3', desc: '穿书/重生/AU 切入点与开局落差（800字内触发）' },
  canon_power:       { icon: '🪜', stepColor: '#06b6d4', phase: 'world',      stepNum: 'FF-4', desc: '从原著提炼权力阶梯，不另造世界观' },
  canon_characters:  { icon: '👥', stepColor: '#22c55e', phase: 'characters', stepNum: 'FF-5', desc: '原著人物建档并标注 canon/oc' },
  canon_audit:       { icon: '✅', stepColor: '#22c55e', phase: 'qa',         stepNum: 'FF-6', desc: '原著贴合 + 番茄爽感双校验' },
}

export const SEQ_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'power_systems', 'factions', 'storylines', 'antagonist_ladder', 'characters',
  'skills', 'items', 'settings',
  'volumes', 'emotion_arc', 'villain_arc',
  'memory', 'relations', 'core_mysteries',
  'opening_contract', 'consistency',
]

/** 番茄专属 Bootstrap 步骤列表（与通用线对齐，补全全部步骤）*/
export const FANQIE_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  // Phase B：番茄创意设计
  'contrast_design', 'golden_finger', 'face_slap_map', 'power_ladder',
  // Phase C：世界构建（复用通用）
  'factions', 'storylines', 'antagonist_ladder', 'characters',
  'skills', 'items', 'settings',
  // Phase D：卷骨架
  'volumes',
  // Phase E：节奏 + 情绪
  'emotion_arc', 'villain_arc', 'rhythm_map',
  // Phase F：记忆 / 伏笔 / 承诺
  'memory', 'relations', 'core_mysteries', 'opening_contract',
  // Phase G：校验
  'consistency', 'signal_audit',
]

export const FANFIC_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'canon_pack', 'deviation_contract', 'entry_hook',
  'golden_finger', 'face_slap_map', 'canon_power',
  'canon_characters', 'volumes', 'rhythm_map', 'canon_audit',
]

// 玄幻修仙直白（原生）：通用串行序列，power_systems→power_ladder（境界主轴+契约），并插入 golden_finger。
export const XIANXIA_STEP_KEYS: StepKey[] = [
  'positioning', 'project',
  'power_ladder', 'golden_finger',
  'factions', 'storylines', 'antagonist_ladder', 'characters',
  'skills', 'items', 'settings',
  'volumes', 'emotion_arc', 'villain_arc',
  'memory', 'relations', 'core_mysteries',
  'opening_contract', 'consistency',
]

export function getStepKeys(mode: StartParams['mode']): StepKey[] {
  if (mode === 'xianxia') return XIANXIA_STEP_KEYS
  if (mode === 'fanqie') return FANQIE_STEP_KEYS
  if (mode === 'fanfic') return FANFIC_STEP_KEYS
  return SEQ_STEP_KEYS
}

export const STEP_ALIAS: Partial<Record<string, StepKey>> = {
  outline: 'volumes',
}

export function makeStep(key: StepKey, overrideLabel?: string): StepState {
  const meta = STEP_META[key]
  return {
    key, label: overrideLabel ?? meta.stepNum,
    status: 'pending', inflight: 0,
    ...meta,
  }
}

export function toKey(step: unknown): StepKey | null {
  if (typeof step !== 'string') return null
  if (step in STEP_META) return step as StepKey
  return STEP_ALIAS[step] ?? null
}

/** 从已持久化 SSE 事件推断最近失败步骤（failed run 重连恢复用）。 */
export function inferFailedStepFromEvents(
  events: Array<{ event?: string; step?: string }> | null | undefined,
): StepKey | null {
  if (!events?.length) return null
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i]
    if (!ev || (ev.event !== 'error' && ev.event !== 'step_halted')) continue
    const key = toKey(ev.step)
    if (key) return key
  }
  return null
}

// ── Pure state helpers ─────────────────────────────────────────

/** 某步失败后，后续未开始的步骤标记为 blocked，避免 UI 显示仍在继续。 */
export function blockStepsAfter(steps: StepState[], failedKey: StepKey): StepState[] {
  const idx = steps.findIndex(s => s.key === failedKey)
  if (idx < 0) return steps
  return steps.map((s, i) => {
    if (i <= idx) return s
    if (s.status === 'pending' || s.status === 'running') {
      return { ...s, status: 'blocked', inflight: 0, detail: '等待前序步骤成功', completedAt: Date.now() }
    }
    return s
  })
}

/** 用户点击重试：从失败步起重置为 pending，清除 blocked。 */
export function resetStepsFromRetry(steps: StepState[], retryKey: StepKey): StepState[] {
  const idx = steps.findIndex(s => s.key === retryKey)
  if (idx < 0) return steps
  return steps.map((s, i) => {
    const fresh = makeStep(s.key)
    if (s.key === retryKey) return { ...fresh, label: s.label }
    if (i > idx && (s.status === 'blocked' || s.status === 'error')) return { ...fresh, label: s.label }
    return s
  })
}

/** 从 ``gate_data.kind`` 推断 GatePendingStep 类型。 */
export function gateStepFromGateData(gd: Record<string, unknown> | null | undefined): GatePendingStep | null {
  if (!gd) return null
  const kind = String(gd.kind || '')
  if (kind === 'positioning') return 'positioning'
  if (kind === 'power_systems') return 'power_systems'
  if (kind === 'characters') return 'characters'
  if (kind === 'volumes') return 'volumes'
  return null
}

/**
 * 将 ``gate_data`` 快照中的闸门信息写入 React 状态（重连恢复时使用）。
 *
 * 设计为纯工具函数（无 React 依赖），供 ``useBootstrapStream.reconnectToRun`` 调用。
 *
 * @param gateData  后端 run 快照的 `gate_data` 字段
 * @param setters   对应的 React state 更新函数
 */
export function applyGateSnapshot(
  gateData: Record<string, any> | null | undefined,
  setters: {
    setGateStep: (v: GatePendingStep | null) => void
    setPositioning: (v: Record<string, any> | null) => void
    setGateMessage: (v: string) => void
    setGatePreview: (v: Record<string, unknown> | null) => void
    setPhase: (v: Phase) => void
  },
): void {
  if (!gateData || typeof gateData !== 'object') return
  const { setGateStep, setPositioning, setGateMessage, setGatePreview, setPhase } = setters
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
      typeof gd.characters_count === 'number' ? gd.characters_count
      : typeof gd.count === 'number' ? gd.count : 0
    setGateStep('characters')
    setGateMessage('请确认人物库后继续')
    setGatePreview({
      characters_count: count,
      ...(Array.isArray(gd.characters_preview) ? { characters_preview: gd.characters_preview } : {}),
      ...(typeof gd.characters_preview_truncated === 'boolean'
        ? { characters_preview_truncated: gd.characters_preview_truncated } : {}),
      ...(typeof gd.relations_count === 'number' ? { relations_count: gd.relations_count } : {}),
      ...(Array.isArray(gd.relations_sample) ? { relations_sample: gd.relations_sample } : {}),
    })
    setPhase('gate')
    return
  }
  if (kind === 'volumes') {
    const gd = gateData as Record<string, unknown>
    setGateStep('volumes')
    setGateMessage(
      typeof gd.has_realm_warnings === 'boolean' && gd.has_realm_warnings
        ? '⚠️ 检测到卷级 BOSS 境界曲线异常，建议重新生成此步后再继续'
        : '请确认卷级骨架后继续',
    )
    setGatePreview({
      volumes_count: (gateData as { count?: number }).count ?? (gd.volumes_count as number | undefined) ?? 0,
      ...(Array.isArray(gd.volumes_preview) ? { volumes_preview: gd.volumes_preview } : {}),
      ...(Array.isArray(gd.volume_realm_warnings) ? { volume_realm_warnings: gd.volume_realm_warnings } : {}),
      ...(typeof gd.has_realm_warnings === 'boolean' ? { has_realm_warnings: gd.has_realm_warnings } : {}),
    })
    setPhase('gate')
  }
}
