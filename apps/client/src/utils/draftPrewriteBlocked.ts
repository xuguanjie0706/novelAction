/**
 * @file 写前硬门（HTTP 409、`detail.error === draft_prewrite_blocked`）解析与带指纹重试。
 *
 * 与后端 `prewrite_gate_violation` 返回的 FastAPI `HTTPException.detail` 对齐；
 * 供 `draft-assist/stream`、`gated-draft-stream` 在开启 `writing_config.block_on_*` 时使用。
 */

import { accumulateDraftAssistStream } from './draftAssistSse'

/** 单条待确认的一致性矛盾（含稳定 fingerprint） */
export interface DraftPrewriteIssueRow {
  fingerprint: string
  severity?: string
  type?: string
  description?: string
  suggestion?: string
}

/** 后端 `detail` 主体（不含 FastAPI 外层 `detail` 键） */
export interface DraftPrewriteBlockedPayload {
  error: 'draft_prewrite_blocked'
  reason: 'consistency_issues' | 'realm_mismatch'
  message?: string
  issues?: DraftPrewriteIssueRow[]
  realm_violations?: string[]
}

/** 写前硬门拦截：携带结构化 `payload` 供 UI 展示或重试时回传 `consistency_issue_ack` */
export class DraftPrewriteBlockedError extends Error {
  readonly payload: DraftPrewriteBlockedPayload

  constructor(payload: DraftPrewriteBlockedPayload) {
    super((payload.message ?? '').trim() || '写前校验未通过，已阻止起笔')
    this.name = 'DraftPrewriteBlockedError'
    this.payload = payload
  }
}

/** 类型守卫：便于 `catch` 分支分支处理 */
export function isDraftPrewriteBlockedError(e: unknown): e is DraftPrewriteBlockedError {
  return e instanceof DraftPrewriteBlockedError
}

/**
 * 从 409 响应体解析写前硬门错误；非该形态时返回 `null`。
 *
 * @param status - HTTP 状态码
 * @param bodyText - `await res.text()` 的原文
 */
export function parseDraftPrewriteBlockedError(
  status: number,
  bodyText: string,
): DraftPrewriteBlockedError | null {
  if (status !== 409 || !bodyText?.trim()) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(bodyText) as { detail?: unknown }
  } catch {
    return null
  }
  const raw = (parsed as { detail?: unknown }).detail
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const d = raw as Record<string, unknown>
  if (d.error !== 'draft_prewrite_blocked') return null
  return new DraftPrewriteBlockedError(d as unknown as DraftPrewriteBlockedPayload)
}

function issueLines(payload: DraftPrewriteBlockedPayload): string {
  if (payload.reason === 'realm_mismatch') {
    return (payload.realm_violations ?? []).join('\n')
  }
  return (payload.issues ?? [])
    .map(i => `• ${(i.description || i.type || '?').trim()}`)
    .join('\n')
}

function issueFingerprints(payload: DraftPrewriteBlockedPayload): string[] {
  return (payload.issues ?? []).map(i => i.fingerprint).filter(Boolean)
}

/**
 * 浏览器默认策略：`realm_mismatch` 仅 `alert`；一致性矛盾 `confirm` 后返回全部 fingerprint。
 *
 * @returns 可写入请求体 `consistency_issue_ack` 的指纹列表；用户取消或无法处理时返回 `null`
 */
export async function defaultResolveDraftPrewriteAck(
  err: DraftPrewriteBlockedError,
): Promise<string[] | null> {
  if (typeof window === 'undefined') return null
  const { payload } = err
  if (payload.reason === 'realm_mismatch') {
    const lines = issueLines(payload) || err.message
    window.alert(`境界字段与体系不一致，请先修正人物卡后再试：\n\n${lines}`)
    return null
  }
  const lines = issueLines(payload)
  const ok = window.confirm(
    `写前全局一致性校验：存在未处理条目。请阅读下列说明；若仍要在当前数据下强制生成，请点击「确定」表示已知悉风险。\n\n${lines || '（无描述）'}`,
  )
  if (!ok) return null
  const fps = issueFingerprints(payload)
  return fps.length ? fps : null
}

export type AuthFetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

/**
 * 调用普通起草 SSE，在遇到 409 时经 `resolveAck` 取得指纹后自动重试一次或多次。
 *
 * @param authFetch - 通常为 {@link authFetch}
 * @param url - 完整 URL
 * @param baseBody - 与后端 `DraftAssistRequest` 对齐的 JSON 字段（不含 `consistency_issue_ack`）
 */
export async function postDraftAssistAccumulatedWithPrewriteRetry(
  authFetch: AuthFetchFn,
  url: string,
  baseBody: Record<string, unknown>,
  options?: {
    signal?: AbortSignal
    resolveAck?: (err: DraftPrewriteBlockedError) => Promise<string[] | null>
  },
): Promise<string> {
  let ack: string[] | undefined
  const resolveAck = options?.resolveAck ?? defaultResolveDraftPrewriteAck
  for (;;) {
    const body: Record<string, unknown> = { ...baseBody }
    if (ack?.length) body.consistency_issue_ack = ack
    const res = await authFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options?.signal,
    })
    if (res.status === 409) {
      const txt = await res.text().catch(() => '')
      const blocked = parseDraftPrewriteBlockedError(409, txt)
      if (!blocked) throw new Error(txt.slice(0, 500) || 'HTTP 409')
      const next = await resolveAck(blocked)
      if (!next?.length) throw blocked
      ack = next
      continue
    }
    return accumulateDraftAssistStream(res)
  }
}

/**
 * 请求门控写作 SSE，409 时解析并经 `resolveAck` 带指纹重试，成功时返回 `ok` 的 `Response`（body 未读）。
 */
export async function authFetchGatedDraftStreamWithPrewriteRetry(
  authFetch: AuthFetchFn,
  url: string,
  baseBody: Record<string, unknown>,
  options?: {
    signal?: AbortSignal
    resolveAck?: (err: DraftPrewriteBlockedError) => Promise<string[] | null>
  },
): Promise<Response> {
  let ack: string[] | undefined
  const resolveAck = options?.resolveAck ?? defaultResolveDraftPrewriteAck
  for (;;) {
    const body: Record<string, unknown> = { ...baseBody }
    if (ack?.length) body.consistency_issue_ack = ack
    const res = await authFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options?.signal,
    })
    if (res.status === 409) {
      const txt = await res.text().catch(() => '')
      const blocked = parseDraftPrewriteBlockedError(409, txt)
      if (!blocked) throw new Error(txt.slice(0, 500) || 'HTTP 409')
      const next = await resolveAck(blocked)
      if (!next?.length) throw blocked
      ack = next
      continue
    }
    if (!res.ok) {
      const txt = (await res.text().catch(() => '')).slice(0, 500)
      throw new Error(txt || `HTTP ${res.status}`)
    }
    return res
  }
}
