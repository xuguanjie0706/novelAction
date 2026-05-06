/**
 * @file 登录 / 注册页面
 *
 * 数据来源：useAuthStore（login / register action）
 * 关键副作用：
 *   - 登录/注册成功后 store 更新 token + user，页面跳转至 /（由 PrivateRoute 放行）
 *   - 错误消息从 AxiosError.response.data.detail 读取并本地展示，不触发全局 toast
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

/** 当前模式：登录 or 注册 */
type Mode = 'login' | 'register'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, register } = useAuthStore()

  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await register(email, password, username || undefined)
      }
      navigate('/', { replace: true })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (Array.isArray(detail)) {
        // Pydantic 422 校验错误格式：detail 是数组
        setError(detail.map((d: any) => d.msg).join('；'))
      } else {
        setError(detail || err.message || '操作失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-indigo-900/20 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-purple-900/20 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Logo / 标题 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-indigo-600 mb-4 shadow-lg shadow-indigo-900/50">
            <span className="text-2xl">📖</span>
          </div>
          <h1 className="text-2xl font-bold text-white">NovelAction</h1>
          <p className="text-gray-400 text-sm mt-1">AI 驱动的网络小说创作系统</p>
        </div>

        {/* 卡片 */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl p-8">
          {/* Tab 切换 */}
          <div className="flex mb-6 bg-gray-800 rounded-xl p-1">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null) }}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                mode === 'login'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(null) }}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                mode === 'register'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              注册
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 用户名（仅注册） */}
            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  用户名 <span className="text-gray-500 font-normal">（可选）</span>
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="留空则使用邮箱前缀"
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
                />
              </div>
            )}

            {/* 邮箱 */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                邮箱
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="your@email.com"
                required
                autoComplete="email"
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
              />
            </div>

            {/* 密码 */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                密码 {mode === 'register' && <span className="text-gray-500 font-normal">（至少 6 位）</span>}
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
              />
            </div>

            {/* 错误提示 */}
            {error && (
              <div className="flex items-start gap-2 bg-red-900/30 border border-red-700/50 rounded-xl px-4 py-3">
                <span className="text-red-400 text-sm flex-shrink-0 mt-0.5">✕</span>
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}

            {/* 提交按钮 */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-xl text-sm transition-colors shadow-lg shadow-indigo-900/30 mt-2"
            >
              {loading
                ? (mode === 'login' ? '登录中…' : '注册中…')
                : (mode === 'login' ? '登录' : '注册并登录')
              }
            </button>
          </form>

          {/* 底部切换提示 */}
          <p className="text-center text-gray-500 text-xs mt-6">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <button
              type="button"
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}
              className="text-indigo-400 hover:text-indigo-300 ml-1 transition-colors"
            >
              {mode === 'login' ? '立即注册' : '去登录'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
