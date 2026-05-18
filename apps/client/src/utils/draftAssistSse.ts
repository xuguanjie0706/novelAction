/**
 * @file draftAssistSse.ts
 * SSE 行解析工具，服务两类流式端点：
 *   - `/ai/draft-assist/stream`（普通起笔/续写）
 *   - `/ai/gated-draft-stream`（质量门控写作循环）
 *
 * 两者共用相同的 `data: {...}` 格式；门控端点在文本 chunk 之外还推送
 * 结构化事件（event 字段），由 {@link GatedDraftEvent} 描述。
 */

// ─────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────

/** 质量门控循环推送的结构化事件类型 */
export type GatedDraftEventType =
  | 'gate_config'
  | 'attempt_start'
  | 'attempt_done'
  | 'qc_running'
  | 'qc_result'
  | 'gate_passed'
  | 'rewrite_queued'
  | 'gate_failed'

/** 单个维度质检结果 */
export interface QcDimension {
  score: number
  status: string
  comment: string
}

/** `qc_result` 事件的数据字段 */
export interface QcResultEvent {
  event: 'qc_result'
  attempt: number
  overall_score: number
  subscribe_intent: number
  passed: boolean
  dimensions: Record<string, QcDimension>
  suggestions: string[]
  summary: string
}

/** `gate_config` 事件 */
export interface GateConfigEvent {
  event: 'gate_config'
  min_overall_score: number
  min_subscribe_intent: number
  max_rewrite_attempts: number
  auto_quality_gate: boolean
  pre_write_warning_enabled?: boolean
  /** 以下为后端扩展字段（可选） */
  block_on_consistency_issues?: boolean
  consistency_block_severities?: string[]
  block_on_realm_mismatch?: boolean
  enforce_face_slap_payoff_when_hook_required?: boolean
  min_face_slap_payoff_score?: number
  /** 本章是否命中爽点硬约束（结算章/高潮期） */
  hook_mandate_active?: boolean
}

/** `attempt_start` 事件 */
export interface AttemptStartEvent {
  event: 'attempt_start'
  attempt: number
  max_attempts: number
  /** "initial" | "patch" | "full_rewrite" */
  strategy: string
}

/** `attempt_done` 事件 */
export interface AttemptDoneEvent {
  event: 'attempt_done'
  attempt: number
  words: number
}

/** `gate_passed` 事件 */
export interface GatePassedEvent {
  event: 'gate_passed'
  attempt: number
  overall_score: number
  subscribe_intent: number
}

/** `rewrite_queued` 事件 */
export interface RewriteQueuedEvent {
  event: 'rewrite_queued'
  attempt: number
  next_attempt: number
  strategy: string
  failing_dimensions: string[]
  overall_score: number
  subscribe_intent: number
}

/** `gate_failed` 事件 */
export interface GateFailedEvent {
  event: 'gate_failed'
  max_attempts: number
  final_score: number
  final_subscribe_intent: number
  min_overall_score: number
  min_subscribe_intent: number
  message: string
}

/** 联合类型：所有可能的门控事件 */
export type GatedDraftEvent =
  | GateConfigEvent
  | AttemptStartEvent
  | AttemptDoneEvent
  | { event: 'qc_running'; attempt: number }
  | QcResultEvent
  | GatePassedEvent
  | RewriteQueuedEvent
  | GateFailedEvent

/** SSE 行解析结果 */
export interface SseParsed {
  text?: string
  error?: string
  done?: boolean
  event?: GatedDraftEvent
  /** 非正文类事件（rag_context、truncation_warning 等） */
  sideEvent?: Record<string, unknown>
}

// ─────────────────────────────────────────────────────────────
// HTML 工具
// ─────────────────────────────────────────────────────────────

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * 把 AI 输出的纯文本（双换行分段）转成 TipTap 可消费的 HTML。
 * @param s - 纯文本正文（可含 `\n\n` 分段和行内 `\n`）
 */
export function plainTextDraftToHtml(s: string): string {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

// ─────────────────────────────────────────────────────────────
// SSE 行解析
// ─────────────────────────────────────────────────────────────

/**
 * 解析单条 `data: ...` SSE 行。
 *
 * 同时支持普通文本 chunk（`{text}`）和门控结构化事件（`{event, ...}`）。
 *
 * @param line - 原始 SSE 行（含或不含 `data:` 前缀）
 * @returns 解析结果，无法解析时返回 null
 */
export function parseSseDraftDataLine(line: string): SseParsed | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>
    if (typeof obj.event === 'string') {
      const gatedTypes = new Set([
        'gate_config', 'pre_warn_running', 'pre_warn_done',
        'attempt_start', 'attempt_done', 'qc_running', 'qc_result',
        'gate_passed', 'rewrite_queued', 'gate_failed',
      ])
      const parsed: SseParsed = { sideEvent: obj }
      if (gatedTypes.has(obj.event)) {
        parsed.event = obj as unknown as GatedDraftEvent
      }
      return parsed
    }
    return obj as SseParsed
  } catch {
    return null
  }
}

// ─────────────────────────────────────────────────────────────
// 普通流式读取（draft-assist）
// ─────────────────────────────────────────────────────────────

/**
 * 读完普通起笔流式响应，返回模型输出的纯文本。
 * 含可能的索引块，交由 `splitStreamedDraftText` 拆分。
 *
 * @throws 若 HTTP 非 2xx 或流中有 `error` 字段
 */
export type DraftAssistStreamOptions = {
  onSideEvent?: (payload: Record<string, unknown>) => void
}

export async function accumulateDraftAssistStream(
  res: Response,
  options?: DraftAssistStreamOptions,
): Promise<string> {
  if (!res.ok) {
    const errText = (await res.text().catch(() => '')).slice(0, 500)
    throw new Error(errText || `HTTP ${res.status}`)
  }
  if (!res.body) throw new Error('响应无流式内容')
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let accumulated = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const parsed = parseSseDraftDataLine(line)
      if (!parsed) continue
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.sideEvent) options?.onSideEvent?.(parsed.sideEvent)
      if (parsed.text) accumulated += parsed.text
    }
  }
  for (const line of buf.split('\n')) {
    const parsed = parseSseDraftDataLine(line)
    if (parsed?.error) throw new Error(parsed.error)
    if (parsed?.sideEvent) options?.onSideEvent?.(parsed.sideEvent)
    if (parsed?.text) accumulated += parsed.text
  }
  return accumulated
}

// ─────────────────────────────────────────────────────────────
// 门控流读取（gated-draft-stream）
// ─────────────────────────────────────────────────────────────

/** 将 SSE `rag_context` 事件格式化为队列进度文案 */
export function formatRagContextProgressLabel(payload: Record<string, unknown>): string {
  const q = String(payload.query ?? '').slice(0, 48)
  const hits = payload.hits
  const n = typeof payload.hit_count === 'number'
    ? payload.hit_count
    : Array.isArray(hits) ? hits.length : 0
  const status = String(payload.status ?? 'ok')
  return `RAG 记忆检索：「${q || '（空）'}」→ ${n} 条（${status}）`
}

/** 门控流读取的回调接口 */
export interface GatedDraftCallbacks {
  /**
   * 收到文本 chunk 时调用（可能跨多个 attempt）。
   * @param chunk - 文本片段
   * @param attempt - 当前尝试轮次
   */
  onText?: (chunk: string, attempt: number) => void
  /**
   * 收到结构化门控事件时调用。
   * @param ev - 事件对象（见 GatedDraftEvent）
   */
  onEvent?: (ev: GatedDraftEvent) => void
  /** rag_context、truncation_warning 等非门控事件 */
  onSideEvent?: (payload: Record<string, unknown>) => void
  /** 不可恢复错误（含 HTTP 非 2xx 和流中 error 字段） */
  onError?: (err: Error) => void
}

/**
 * 读取门控写作 SSE 流，通过回调分发文本 chunk 和结构化事件。
 *
 * 调用方负责维护 UI 状态（当前轮次、分数、进度条等）。
 * 流结束（[DONE] 或网络中断）时 resolve。
 *
 * @param res - fetch 返回的 Response 对象
 * @param callbacks - 事件回调集合
 * @returns 最终一次成功生成的完整纯文本（最后一轮的正文 chunk 拼接）
 */
export async function consumeGatedDraftStream(
  res: Response,
  callbacks: GatedDraftCallbacks = {},
): Promise<string> {
  if (!res.ok) {
    const errText = (await res.text().catch(() => '')).slice(0, 500)
    const err = new Error(errText || `HTTP ${res.status}`)
    callbacks.onError?.(err)
    throw err
  }
  if (!res.body) {
    const err = new Error('响应无流式内容')
    callbacks.onError?.(err)
    throw err
  }

  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let currentAttempt = 1
  let lastAttemptText = ''  // 记录最后一轮的正文（供调用方拼 HTML）
  let inNewAttempt = false

  const processLine = (line: string) => {
    const parsed = parseSseDraftDataLine(line)
    if (!parsed) return

    if (parsed.error) {
      const err = new Error(parsed.error)
      callbacks.onError?.(err)
      throw err
    }

    if (parsed.done) return

    if (parsed.sideEvent) {
      callbacks.onSideEvent?.(parsed.sideEvent)
    }

    if (parsed.event) {
      const ev = parsed.event
      // 跟踪当前 attempt
      if (ev.event === 'attempt_start') {
        currentAttempt = (ev as AttemptStartEvent).attempt
        lastAttemptText = ''  // 新 attempt 开始，重置累积
        inNewAttempt = true
      }
      callbacks.onEvent?.(ev)
      return
    }

    if (parsed.text) {
      if (inNewAttempt) lastAttemptText += parsed.text
      callbacks.onText?.(parsed.text, currentAttempt)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) processLine(line)
    }
    for (const line of buf.split('\n')) processLine(line)
  } finally {
    reader.releaseLock()
  }

  return lastAttemptText
}
