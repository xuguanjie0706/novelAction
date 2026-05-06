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
    <div className="min-h-screen bg-[#0C111C] flex flex-col md:flex-row overflow-hidden">
      {/* Left: Ancient study illustration (CSS scene) */}
      <div className="relative md:w-[55%] h-[200px] md:h-auto bg-[#121B22] flex items-center justify-center overflow-hidden">
        {/* Background layers for depth */}
        <div className="absolute inset-0 bg-[radial-gradient(#3A2F2A_0.8px,transparent_1px)] bg-[length:4px_4px] opacity-30" />

        {/* Wooden desk surface */}
        <div className="absolute bottom-0 left-0 right-0 h-2/5 bg-[#2C2522] shadow-[inset_0_40px_40px_-20px_#1C2526]" />

        {/* Oil lamp with warm glow */}
        <div className="absolute left-1/3 top-1/3 w-16 h-16">
          <div className="absolute inset-0 bg-[#C9A227] rounded-full blur-2xl opacity-40 animate-[pulse_2.5s_ease-in-out_infinite]" />
          <div className="relative w-16 h-16 flex items-end justify-center">
            {/* Lamp base (simplified) */}
            <div className="w-8 h-6 bg-[#5C5240] rounded-full" />
            {/* Flame */}
            <div className="absolute -top-3 w-3 h-5 bg-[#F5E8C7] rounded-full animate-[pulse_1.8s_ease-in-out_infinite] shadow-[0_0_12px_#C9A227]" />
          </div>
        </div>

        {/* Scattered papers */}
        <div className="absolute right-1/4 top-1/4 w-20 h-24 rotate-[-12deg] border border-[#3A2F2A] bg-[#F5E8C7]/10 rounded-sm shadow-inner" />
        <div className="absolute right-1/3 bottom-1/3 w-16 h-20 rotate-[18deg] border border-[#3A2F2A] bg-[#F5E8C7]/10 rounded-sm" />
        {/* Ink lines on paper */}
        <div className="absolute right-[26%] top-[27%] w-12 h-[1px] bg-[#3A2F2A]/40" />
        <div className="absolute right-[26%] top-[32%] w-10 h-[1px] bg-[#3A2F2A]/40" />

        {/* Subtle bamboo curtain hint (right edge) */}
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-[#1C2526]/60 to-transparent" />
      </div>

      {/* Right: Frosted form card */}
      <div className="md:w-[45%] flex items-center justify-center px-6 py-10 md:py-0">
        <div className="w-full max-w-[420px] bg-[#1C2526]/70 backdrop-blur-2xl border border-[#3A2F2A] rounded-2xl shadow-2xl shadow-black/40 p-10">
          {/* Logo / Title */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#C9A227] mb-4 shadow-lg shadow-[#C9A227]/30">
              <span className="text-2xl">📖</span>
            </div>
            <h1 className="text-2xl font-bold text-[#F5E8C7] tracking-wide">NovelAction</h1>
            <p className="text-[#A8B0B8] text-sm mt-1.5">AI 驱动的古典小说创作空间</p>
          </div>

          {/* Tab 切换 */}
          <div className="flex mb-8 bg-[#121B22] rounded-xl p-1 border border-[#3A2F2A]">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null) }}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                mode === 'login'
                  ? 'bg-[#C9A227] text-[#0C111C] shadow'
                  : 'text-[#A8B0B8] hover:text-[#F5E8C7]'
              }`}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(null) }}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                mode === 'register'
                  ? 'bg-[#C9A227] text-[#0C111C] shadow'
                  : 'text-[#A8B0B8] hover:text-[#F5E8C7]'
              }`}
            >
              注册
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
