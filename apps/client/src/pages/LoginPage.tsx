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
import { BarChart3, BookOpen, Eye, EyeOff, Lightbulb } from 'lucide-react'
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
    <div className="min-h-screen bg-[#f7f5f2] text-slate-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1400px] flex-col lg:flex-row">
        <section
          className="relative hidden lg:flex lg:w-[66%] flex-col overflow-hidden border-r border-slate-200/70 px-12 py-10"
          style={{
            backgroundImage: "url('/assets/bg.png')",
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 6% center',
            backgroundSize: '48% auto',
          }}
        >
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(247,245,242,0.97)_0%,rgba(247,245,242,0.95)_46%,rgba(247,245,242,0.72)_66%,rgba(247,245,242,0.42)_100%)]" />

          <div className="relative z-10">
            <div className="mb-1 flex items-center gap-3">
              <img
                src="/assets/icon.png"
                alt="书之幻境"
                className="h-10 w-10 rounded-xl shadow-sm"
              />
              <div>
                <p className="text-xl font-semibold tracking-tight">书之幻境</p>
                <p className="text-sm text-slate-500">AI 驱动的古典小说创作空间</p>
              </div>
            </div>
          </div>

          <div className="relative z-10 mt-20 max-w-xl">
            <h2 className="text-5xl font-semibold leading-tight tracking-tight text-slate-900">
              让每一个故事
              <br />
              都有温度与力量
            </h2>
            <p className="mt-6 text-lg leading-8 text-slate-500">
              AI 驱动的古典小说创作空间，激发灵感，沉浸创作，让你的文字闪耀独特光芒。
            </p>

            <div className="mt-10 space-y-4">
              <div className="flex items-center gap-4 px-1 py-1">
                <span className="rounded-xl bg-amber-50 p-2 text-amber-500">
                  <BookOpen size={20} />
                </span>
                <div>
                  <p className="font-medium">智能创作</p>
                  <p className="text-sm text-slate-500">AI 辅助构思，激发创作灵感</p>
                </div>
              </div>
              <div className="flex items-center gap-4 px-1 py-1">
                <span className="rounded-xl bg-amber-50 p-2 text-amber-500">
                  <Lightbulb size={20} />
                </span>
                <div>
                  <p className="font-medium">沉浸体验</p>
                  <p className="text-sm text-slate-500">专注创作，打造沉浸式写作环境</p>
                </div>
              </div>
              <div className="flex items-center gap-4 px-1 py-1">
                <span className="rounded-xl bg-amber-50 p-2 text-amber-500">
                  <BarChart3 size={20} />
                </span>
                <div>
                  <p className="font-medium">数据统计</p>
                  <p className="text-sm text-slate-500">多维度数据分析，见证成长轨迹</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="flex w-full items-center justify-center bg-slate-50/60 px-4 py-8 sm:px-8 lg:w-[34%] lg:px-10">
          <div className="w-full max-w-[420px] rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-xl shadow-slate-200/50 backdrop-blur sm:p-8">
            <div className="mb-8 text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 mb-4">
              <img
                src="/assets/icon.png"
                alt="书之幻境"
                  className="w-16 h-16 rounded-2xl shadow-md"
              />
            </div>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{mode === 'login' ? '欢迎回来' : '创建账号'}</h1>
              <p className="mt-1.5 text-sm text-slate-500">{mode === 'login' ? '登录继续创作之旅' : '注册后即可进入你的创作空间'}</p>
            </div>

            <div className="mb-6 flex rounded-2xl bg-slate-100 p-1 ring-1 ring-slate-200">
              <button
                type="button"
                onClick={() => {
                  setMode('login')
                  setError(null)
                  setEmailCode('')
                  setDevCodeHint(null)
                }}
                className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition ${
                  mode === 'login'
                    ? 'bg-white text-amber-600 shadow-sm ring-1 ring-amber-200/60'
                    : 'text-slate-500 hover:text-slate-700'
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
                className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition ${
                  mode === 'register'
                    ? 'bg-white text-amber-600 shadow-sm ring-1 ring-amber-200/60'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                注册
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === 'register' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    用户名 <span className="font-normal text-slate-400">（可选）</span>
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    placeholder="留空则使用邮箱前缀"
                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
                  />
                </div>
              )}

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  邮箱
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  autoComplete="email"
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
                />
              </div>

              {mode === 'register' && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    邮箱验证码
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={emailCode}
                      onChange={e => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="6 位数字验证码"
                      required={mode === 'register'}
                      className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
                    />
                    <button
                      type="button"
                      onClick={handleSendCode}
                      disabled={sendingCode || codeCooldown > 0}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-amber-300 hover:text-amber-600 disabled:cursor-not-allowed disabled:text-slate-400"
                    >
                      {sendingCode ? '发送中…' : codeCooldown > 0 ? `${codeCooldown}s` : '发送验证码'}
                    </button>
                  </div>
                  {devCodeHint && (
                    <p className="mt-1.5 text-xs text-amber-600">{devCodeHint}</p>
                  )}
                </div>
              )}

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  密码 {mode === 'register' && <span className="font-normal text-slate-400">（至少 6 位）</span>}
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
                    required
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 pr-12 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-amber-600"
                    aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  <p>{error}</p>
                  {error.includes('已被注册') && mode === 'register' && (
                    <button
                      type="button"
                      onClick={() => {
                        setMode('login')
                        setError(null)
                        setEmailCode('')
                        setDevCodeHint(null)
                      }}
                      className="mt-2 font-medium text-amber-700 underline underline-offset-2 hover:text-amber-800"
                    >
                      切换到登录
                    </button>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-amber-500 py-3 text-sm font-semibold text-white shadow-md shadow-amber-200 transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
              >
                {loading ? (
                  <>
                    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    {mode === 'login' ? '登录中…' : '注册中…'}
                  </>
                ) : (
                  mode === 'login' ? '登录' : '注册并登录'
                )}
              </button>

              <div className="pt-2 text-center text-xs text-slate-400">
                继续即表示你同意相关服务条款与隐私政策
              </div>
            </form>
          </div>
        </section>
      </div>
    </div>
  )
}
