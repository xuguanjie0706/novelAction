/**
 * 管理后台 token 工具：与创作端 storage key 严格隔离，避免跨 SPA 误读。
 *
 * - localStorage key: `novelAction:admin-token`
 * - 单一来源：所有需要鉴权的网络请求只通过 ``http`` axios 实例（拦截器自动注入）
 *   或本文件提供的 helper；禁止散落在组件里手写 Authorization 头。
 */
const TOKEN_KEY = 'novelAction:admin-token'
const USERNAME_KEY = 'novelAction:admin-username'

export function getAdminToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAdminAuth(token: string, username: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USERNAME_KEY, username)
  } catch {
    /* ignore quota/disabled storage */
  }
}

export function getAdminUsername(): string | null {
  try {
    return localStorage.getItem(USERNAME_KEY)
  } catch {
    return null
  }
}

export function clearAdminAuth(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USERNAME_KEY)
  } catch {
    /* ignore */
  }
}
