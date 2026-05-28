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
import { Eye, EyeOff } from 'lucide-react'
import { authApi } from '../api/auth'

/** 当前模式：登录 or 注册 */
type Mode = 'login' | 'register'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, register } = useAuthStore()

  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [emailCode, setEmailCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const [codeCooldown, setCodeCooldown] = useState(0)
  const [devCodeHint, setDevCodeHint] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  React.useEffect(() => {
    if (codeCooldown <= 0) return
    const timer = window.setTimeout(() => setCodeCooldown(prev => Math.max(prev - 1, 0)), 1000)
    return () => window.clearTimeout(timer)
  }, [codeCooldown])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await register(email, password, username || undefined, emailCode)
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

  const handleSendCode = async () => {
    if (!email) {
      setError('请先输入邮箱后再发送验证码')
      return
    }
    setError(null)
    setDevCodeHint(null)
    setSendingCode(true)
    try {
      const res = await authApi.sendRegisterCode(email)
      setCodeCooldown(60)
      if (res.dev_code) {
        setDevCodeHint(`开发环境验证码：${res.dev_code}`)
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(detail || err.message || '验证码发送失败，请稍后重试')
    } finally {
      setSendingCode(false)
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
              onClick={() => {
                setMode('login')
                setError(null)
                setEmailCode('')
                setDevCodeHint(null)
              }}
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
              onClick={() => {
                setMode('register')
                setError(null)
                setEmailCode('')
                setDevCodeHint(null)
              }}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                mode === 'register'
                  ? 'bg-[#C9A227] text-[#0C111C] shadow'
                  : 'text-[#A8B0B8] hover:text-[#F5E8C7]'
              }`}
            >
              注册
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* 用户名（仅注册） */}
            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
                  用户名 <span className="text-[#5C5240] font-normal">（可选）</span>
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="留空则使用邮箱前缀"
                  className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
                />
              </div>
            )}

            {/* 邮箱 */}
            <div>
              <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
                邮箱
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="your@email.com"
                required
                autoComplete="email"
                className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
              />
            </div>

            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
                  邮箱验证码
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={emailCode}
                    onChange={e => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="6 位数字验证码"
                    required={mode === 'register'}
                    className="flex-1 bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
                  />
                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={sendingCode || codeCooldown > 0}
                    className="px-3 py-2 rounded-xl border border-[#3A2F2A] text-xs text-[#F5E8C7] hover:border-[#C9A227] disabled:text-[#5C5240] disabled:border-[#3A2F2A] disabled:cursor-not-allowed transition-all"
                  >
                    {sendingCode ? '发送中…' : codeCooldown > 0 ? `${codeCooldown}s` : '发送验证码'}
                  </button>
                </div>
                {devCodeHint && (
                  <p className="mt-1.5 text-xs text-[#C9A227]">{devCodeHint}</p>
                )}
              </div>
            )}

            {/* 密码 + visibility toggle (new) */}
            <div>
              <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
                密码 {mode === 'register' && <span className="text-[#5C5240] font-normal">（至少 6 位）</span>}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
                  required
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 pr-12 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[#A8B0B8] hover:text-[#C9A227] transition-colors"
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* 错误提示 */}
            {error && (
              <div className="flex items-start gap-2 bg-[#3A2A2A]/60 border border-[#8B4A4A]/40 rounded-xl px-4 py-3 text-sm text-[#D4A5A5]">
                <span className="mt-0.5">✕</span>
                <p>{error}</p>
              </div>
            )}

            {/* 提交按钮 */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#C9A227] hover:bg-[#D4AF37] active:bg-[#B8971F] disabled:bg-[#5C5240] disabled:text-[#8A7F6A] disabled:cursor-not-allowed text-[#0C111C] font-medium py-3 rounded-xl text-sm transition-all shadow-lg shadow-[#C9A227]/20 mt-2 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="inline-block w-4 h-4 border-2 border-[#0C111C] border-t-transparent rounded-full animate-spin" />
                  {mode === 'login' ? '登录中…' : '注册中…'}
                </>
              ) : (
                mode === 'login' ? '登录' : '注册并登录'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
