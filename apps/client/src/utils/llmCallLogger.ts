const LLM_CALL_LOG_KEY = 'novelAction:llm-call-logs:v1'
const MAX_LOG_COUNT = 200

export interface LlmCallRecord {
  id: string
  at: string
  method: string
  endpoint: string
  status: number | 'network_error'
  duration_ms: number
  context: Record<string, unknown>
  token_usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    estimated: boolean
  }
  error?: string
}

type LlmCallStartInput = {
  method: string
  endpoint: string
  context?: Record<string, unknown>
  requestPayload?: unknown
}

type LlmCallFinishInput = {
  status: number | 'network_error'
  responsePayload?: unknown
  error?: string
  usage?: Partial<{ prompt_tokens: number; completion_tokens: number; total_tokens: number }>
}

type PendingCall = LlmCallStartInput & {
  id: string
  startedAt: number
}

const pendingCalls = new Map<string, PendingCall>()

function normalizeEndpoint(endpoint: string): string {
  if (!endpoint) return endpoint
  try {
    const u = new URL(endpoint, window.location.origin)
    return `${u.pathname}${u.search}`
  } catch {
    return endpoint
  }
}

function estimateTokens(payload: unknown): number {
  if (payload == null) return 0
  const raw = typeof payload === 'string' ? payload : JSON.stringify(payload)
  if (!raw) return 0
  return Math.ceil(raw.length / 4)
}

function readStoredLogs(): LlmCallRecord[] {
  try {
    const raw = localStorage.getItem(LLM_CALL_LOG_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed as LlmCallRecord[] : []
  } catch {
    return []
  }
}

function writeStoredLogs(records: LlmCallRecord[]) {
  try {
    localStorage.setItem(LLM_CALL_LOG_KEY, JSON.stringify(records.slice(0, MAX_LOG_COUNT)))
  } catch {
    // ignore storage failure
  }
}

export function appendLlmCallRecord(record: LlmCallRecord) {
  const prev = readStoredLogs()
  writeStoredLogs([record, ...prev])
}

export function startLlmCall(input: LlmCallStartInput): string {
  const id = `llm-call-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  pendingCalls.set(id, { ...input, id, startedAt: Date.now() })
  return id
}

export function finishLlmCall(id: string, input: LlmCallFinishInput) {
  const pending = pendingCalls.get(id)
  if (!pending) return
  pendingCalls.delete(id)

  const duration = Math.max(1, Date.now() - pending.startedAt)
  const usage = input.usage ?? {}

  const promptTokens = Number.isFinite(usage.prompt_tokens)
    ? Number(usage.prompt_tokens)
    : estimateTokens(pending.requestPayload)
  const completionTokens = Number.isFinite(usage.completion_tokens)
    ? Number(usage.completion_tokens)
    : estimateTokens(input.responsePayload)
  const totalTokens = Number.isFinite(usage.total_tokens)
    ? Number(usage.total_tokens)
    : promptTokens + completionTokens

  appendLlmCallRecord({
    id: pending.id,
    at: new Date(pending.startedAt).toISOString(),
    method: pending.method.toUpperCase(),
    endpoint: normalizeEndpoint(pending.endpoint),
    status: input.status,
    duration_ms: duration,
    context: pending.context ?? {},
    token_usage: {
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      total_tokens: totalTokens,
      estimated: !(Number.isFinite(usage.prompt_tokens) || Number.isFinite(usage.completion_tokens) || Number.isFinite(usage.total_tokens)),
    },
    error: input.error,
  })
}

export function isLlmRelatedEndpoint(endpoint?: string): boolean {
  if (!endpoint) return false
  return [
    '/ai/',
    '/bootstrap/stream',
    '/outline/ai-expand',
    '/outline/ai-full-generate',
  ].some((pattern) => endpoint.includes(pattern))
}

export function extractUsage(payload: unknown): Partial<{ prompt_tokens: number; completion_tokens: number; total_tokens: number }> | undefined {
  if (!payload || typeof payload !== 'object') return undefined
  const data = payload as Record<string, any>
  const usage = data.usage && typeof data.usage === 'object' ? data.usage : null
  if (!usage) return undefined
  return {
    prompt_tokens: typeof usage.prompt_tokens === 'number' ? usage.prompt_tokens : undefined,
    completion_tokens: typeof usage.completion_tokens === 'number' ? usage.completion_tokens : undefined,
    total_tokens: typeof usage.total_tokens === 'number' ? usage.total_tokens : undefined,
  }
}

export function installLlmFetchLogger() {
  const g = globalThis as typeof globalThis & {
    __novelActionLlmFetchPatched?: boolean
    fetch: typeof fetch
  }
  if (typeof g.fetch !== 'function' || g.__novelActionLlmFetchPatched) return
  const originalFetch = g.fetch.bind(g)
  g.__novelActionLlmFetchPatched = true

  g.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const endpoint = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    if (!isLlmRelatedEndpoint(endpoint)) return originalFetch(input, init)

    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const context = { source: 'fetch' }
    const requestPayload = typeof init?.body === 'string' ? init.body : undefined
    const callId = startLlmCall({ method, endpoint, context, requestPayload })

    try {
      const response = await originalFetch(input, init)
      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('text/event-stream')) {
        finishLlmCall(callId, { status: response.status, responsePayload: '[stream]' })
        return response
      }
      let responsePayload: unknown = undefined
      try {
        const cloned = response.clone()
        responsePayload = await cloned.json()
      } catch {
        responsePayload = undefined
      }
      finishLlmCall(callId, {
        status: response.status,
        responsePayload,
        usage: extractUsage(responsePayload),
      })
      return response
    } catch (error: any) {
      finishLlmCall(callId, {
        status: 'network_error',
        error: error?.message || 'network_error',
      })
      throw error
    }
  }
}
