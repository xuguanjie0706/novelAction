/**
 * @file 用户认证 API 客户端
 *
 * 职责：封装 /api/v1/auth/* 的三个端点，返回类型与后端 schema 一一对应。
 * 依赖：使用独立的 axios 实例（不带自动 toast），避免登录失败时触发全局错误提示。
 *
 * @see 后端 apps/backend/app/routers/auth.py
 */

import axios from 'axios'
import type { AuthUser } from '../store/authStore'

/** 后端 TokenResponse schema */
export interface TokenResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

/** 专用 axios 实例：不挂全局错误拦截，让调用方自己处理 error.response.data.detail */
const authHttp = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

export const authApi = {
  /**
   * 注册新账号。
   *
   * @param email 注册邮箱
   * @param password 明文密码（后端哈希，不落库原文）
   * @param username 可选显示名；留空则后端回退到邮箱前缀
   * @returns TokenResponse，包含 access_token 与用户信息
   * @throws AxiosError - 400 邮箱已注册 | 422 字段校验失败
   */
  register: async (email: string, password: string, username?: string): Promise<TokenResponse> => {
    const res = await authHttp.post<TokenResponse>('/auth/register', { email, password, username })
    return res.data
  },

  /**
   * 账号密码登录。
   *
   * @param email 注册邮箱
   * @param password 明文密码
   * @returns TokenResponse，包含 access_token 与用户信息
   * @throws AxiosError - 401 邮箱或密码错误
   */
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const res = await authHttp.post<TokenResponse>('/auth/login', { email, password })
    return res.data
  },

  /**
   * 用 token 获取当前登录用户信息（用于应用初始化时校验 token 有效性）。
   *
   * @param token 已存储的 JWT Bearer Token
   * @returns 当前用户公开信息（AuthUser）
   * @throws AxiosError - 401 token 无效或过期
   */
  me: async (token: string): Promise<AuthUser> => {
    const res = await authHttp.get<AuthUser>('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return res.data
  },
}
