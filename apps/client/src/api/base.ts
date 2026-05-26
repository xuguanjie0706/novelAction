/**
 * axios 实例与请求/响应拦截器。
 * 所有业务 API 模块从这里导入 `api` 实例，不直接 import axios。
 */
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  extractUsage,
  finishLlmCall,
  installLlmFetchLogger,
  isLlmRelatedEndpoint,
  startLlmCall,
} from '../utils/llmCallLogger'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

/** 复盘类接口会调用 thinking 模型，单次可能超过 2 分钟；避免 axios 默认无超时却被代理/浏览器提前断开。 */
export const DEBRIEF_REQUEST_TIMEOUT_MS = 600_000

installLlmFetchLogger()

/**
 * 请求拦截器：
 * 1. 注入 Authorization: Bearer <token>（若 authStore 有 token）
 * 2. 记录 LLM 相关请求的调用 ID（用于耗时统计）
 */
api.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('novelAction:auth-token')
    if (token) {
      config.headers = config.headers ?? {}
      config.headers['Authorization'] = `Bearer ${token}`
    }
  } catch { /* ignore */ }

  const endpoint = config.url || ''
  if (isLlmRelatedEndpoint(endpoint)) {
    const callId = startLlmCall({
      method: config.method || 'GET',
      endpoint,
      context: { source: 'axios' },
      requestPayload: config.data,
    })
    ;(config as any).__llmCallId = callId
  }
  return config
})

api.interceptors.response.use(
  (res) => {
    const callId = (res.config as any).__llmCallId as string | undefined
    if (callId) {
      finishLlmCall(callId, {
        status: res.status,
        responsePayload: res.data,
        usage: extractUsage(res.data),
      })
    }
    return res
  },
  (err) => {
    const callId = (err.config as any)?.__llmCallId as string | undefined
    if (callId) {
      finishLlmCall(callId, {
        status: err.response?.status ?? 'network_error',
        responsePayload: err.response?.data,
        usage: extractUsage(err.response?.data),
        error: err.response?.data?.detail || err.message || '请求失败',
      })
    }

    // 401 未授权：清除 token 并跳转登录页（避免静默失效）
    if (err.response?.status === 401) {
      try {
        localStorage.removeItem('novelAction:auth-token')
      } catch { /* ignore */ }
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
      return Promise.reject(err)
    }

    const msg = err.response?.data?.detail || err.message || '请求失败'
    toast.error(msg)
    return Promise.reject(err)
  }
)

export default api
