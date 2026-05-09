/**
 * @file authFetch — 给原生 fetch 自动注入 Bearer Token
 *
 * 资源边界：
 * - 仅用于 SSE/流式调用（bootstrap/stream、ai/draft-assist/stream、ai/chat/stream、
 *   outline/ai-expand、outline/ai-full-generate 等不走 axios 的端点）。
 * - axios 实例（@/api/client）已在请求拦截器里注入 Authorization；不要二次封装。
 *
 * 失败语义：
 * - 401 时清掉 localStorage 的 token 并跳转 /login，与 axios 拦截器行为对齐。
 * - 其他状态码透传给调用方（多数 SSE 端点会自己处理流体异常）。
 */

const TOKEN_KEY = 'novelAction:auth-token'

/** 读取持久化的 JWT token；本地存储不可用（隐私模式等）时返回 null。 */
function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/**
 * 在已有 headers 上叠加 Authorization: Bearer <token>。
 * 不破坏调用方传入的其他 header（如 Content-Type）。
 *
 * @param init RequestInit；可省略。
 * @returns 合并后的 headers，调用方可直接用于 fetch 的 init.headers。
 */
function withAuthHeaders(init?: RequestInit): HeadersInit {
  const base = (init?.headers ?? {}) as Record<string, string>
  const merged: Record<string, string> = { ...base }
  const token = readToken()
  if (token && !('Authorization' in merged) && !('authorization' in merged)) {
    merged['Authorization'] = `Bearer ${token}`
  }
  return merged
}

/**
 * 带 Authorization 头的 fetch 包装。401 时与 axios 一致：清 token + 跳 /login。
 *
 * @param input URL（绝对或相对 /api/v1/...）
 * @param init  fetch RequestInit；headers 会被合并而非覆盖
 * @returns 原始 Response，调用方按 SSE/JSON 业务逻辑继续处理
 */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const merged: RequestInit = { ...init, headers: withAuthHeaders(init) }
  const res = await fetch(input, merged)
  if (res.status === 401) {
    try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
  }
  return res
}

/**
 * 把 token 拼成 query 参数，供原生 WebSocket 鉴权使用。
 *
 * 浏览器 WebSocket 构造函数无法设置自定义 header，常规做法是把 token 放在
 * 查询串里由服务端解析。返回值已 URL 编码，可直接拼到 ws/wss URL 上。
 *
 * @returns 如 "?token=..." 形式的字符串；未登录则返回空串
 */
export function authQueryString(): string {
  const token = readToken()
  return token ? `?token=${encodeURIComponent(token)}` : ''
}
