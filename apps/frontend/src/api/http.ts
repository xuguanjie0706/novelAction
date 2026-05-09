import axios from 'axios'

import { clearAdminAuth, getAdminToken } from './auth'

/** 列表/轻量接口 */
export const DEFAULT_HTTP_TIMEOUT_MS = 60_000

/**
 * 与后端 `LLM_HTTP_READ_TIMEOUT`（默认 900s）对齐；连贯性评测/改正文等请求勿用 60s 默认超时。
 */
export const LONG_RUNNING_HTTP_TIMEOUT_MS = 900_000

export const http = axios.create({
  baseURL: '',
  timeout: DEFAULT_HTTP_TIMEOUT_MS,
})

// 请求拦截器：自动注入管理员 Bearer token（来自 localStorage）。
http.interceptors.request.use((config) => {
  const token = getAdminToken()
  if (token) {
    config.headers = config.headers ?? {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 → 清空 token 并跳转登录页（仅一次性跳转，避免循环）。
// 登录端点本身的 401 由 LoginPage 自行展示错误，此处通过 URL 排除避免误清。
http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    const isLoginCall = url.includes('/admin/auth/login')
    if (status === 401 && !isLoginCall) {
      clearAdminAuth()
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  },
)
