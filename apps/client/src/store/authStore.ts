/**
 * @file 用户认证全局状态（Auth Store）
 *
 * 职责：管理 JWT token、当前登录用户信息、登录/注册/登出操作。
 * 数据来源：token 持久化在 localStorage；user 信息在内存（登录后填充）。
 *
 * 副作用：
 * - login / register 成功后写 localStorage，并刷新 axios 拦截器的 Authorization 头
 * - logout 清除 localStorage token，重置 user 为 null
 */

import { create } from 'zustand'
import { authApi } from '../api/auth'

const TOKEN_KEY = 'novelAction:auth-token'

/** 用户公开信息，与后端 UserOut schema 对齐 */
export interface AuthUser {
  id: string
  email: string
  username: string | null
  is_active: boolean
  created_at: string
}

interface AuthState {
  /** JWT Bearer Token，null 表示未登录 */
  token: string | null
  /** 当前登录用户，null 表示未登录或尚未初始化 */
  user: AuthUser | null
  /** 是否正在校验 token（首次加载时的 /auth/me 请求） */
  initializing: boolean

  // ── Actions ──────────────────────────────────────────────────────────────

  /**
   * 登录：调用 POST /auth/login，成功后存 token + user。
   * @param email 注册邮箱
   * @param password 明文密码
   * @throws 登录失败时抛出 AxiosError（由调用方 catch 展示错误）
   */
  login: (email: string, password: string) => Promise<void>

  /**
   * 注册：调用 POST /auth/register，成功后存 token + user（自动登录）。
   * @param email 邮箱
   * @param password 明文密码
   * @param username 可选显示名
   * @throws 注册失败时抛出 AxiosError
   */
  register: (email: string, password: string, username?: string) => Promise<void>

  /**
   * 登出：清除 token 与 user，重定向由调用方处理。
   */
  logout: () => void

  /**
   * 应用初始化时调用：若 localStorage 有 token，验证有效性并填充 user。
   * 无论成功失败都将 initializing 置为 false。
   */
  initialize: () => Promise<void>
}

/** 从 localStorage 读取存储的 token（启动时） */
function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** 将 token 写入 localStorage */
function saveToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch { /* ignore */ }
}

/** 清除 localStorage 中的 token */
function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch { /* ignore */ }
}

export const useAuthStore = create<AuthState>((set) => ({
  token: readToken(),
  user: null,
  initializing: true,

  login: async (email, password) => {
    const res = await authApi.login(email, password)
    saveToken(res.access_token)
    set({ token: res.access_token, user: res.user })
  },

  register: async (email, password, username) => {
    const res = await authApi.register(email, password, username)
    saveToken(res.access_token)
    set({ token: res.access_token, user: res.user })
  },

  logout: () => {
    clearToken()
    set({ token: null, user: null })
  },

  initialize: async () => {
    const token = readToken()
    if (!token) {
      set({ initializing: false })
      return
    }
    try {
      const user = await authApi.me(token)
      set({ token, user, initializing: false })
    } catch {
      // token 过期或无效，清除
      clearToken()
      set({ token: null, user: null, initializing: false })
    }
  },
}))
