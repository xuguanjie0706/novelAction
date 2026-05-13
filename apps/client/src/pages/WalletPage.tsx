/**
 * WalletPage — 用户积分钱包页。
 *
 * 数据来源：
 *   - 余额：`GET /api/v1/credits/me`
 *   - 流水：`GET /api/v1/credits/me/transactions`
 *   - 兑换：`POST /api/v1/credits/redeem`
 *
 * 布局：
 *   - 左侧 HomeSidebar（复用首页侧边栏）
 *   - 主区：余额英雄区 → 兑换码卡 → 流水历史
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Clock,
  Coins,
  Gift,
  Loader2,
  LogOut,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import {
  fetchMyCredits,
  fetchMyTransactions,
  redeemCode,
  type CreditBalance,
  type CreditTransaction,
} from '../api/credits'
import { useAuthStore } from '../store/authStore'

// ─────────────────────────────────────────────────────────
//  Constants
// ─────────────────────────────────────────────────────────

const PAGE_SIZE = 20

/** ref_type → 中文标签 + 图标 */
const REF_META: Record<string, { label: string; color: string; bg: string }> = {
  registration_bonus: { label: '注册赠送', color: 'text-violet-600', bg: 'bg-violet-50' },
  llm_call:           { label: 'AI 调用',   color: 'text-blue-600',   bg: 'bg-blue-50'   },
  admin_topup:        { label: '管理员充值', color: 'text-emerald-600', bg: 'bg-emerald-50' },
  admin_adjust:       { label: '管理员调账', color: 'text-amber-600',   bg: 'bg-amber-50'  },
  redeem_code:        { label: '兑换码',     color: 'text-rose-600',    bg: 'bg-rose-50'   },
}

function refMeta(type: string) {
  return REF_META[type] ?? { label: type, color: 'text-gray-500', bg: 'bg-gray-50' }
}

// ─────────────────────────────────────────────────────────
//  Sub-components
// ─────────────────────────────────────────────────────────

/**
 * 余额英雄区：大数字展示 + 统计行。
 *
 * @param credit 积分账户信息；null 时显示加载骨架。
 */
function BalanceHero({ credit }: { credit: CreditBalance | null }) {
  const balanceColor =
    credit === null
      ? 'text-gray-300'
      : credit.balance < 100
        ? 'text-red-500'
        : credit.balance < 1000
          ? 'text-amber-500'
          : 'text-gray-900'

  return (
    <div className="relative overflow-hidden rounded-2xl bg-white border border-gray-100 shadow-sm px-8 py-8">
      {/* 右上角装饰光晕 */}
      <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-amber-100/60 blur-3xl" />
      <div className="pointer-events-none absolute -right-4 -top-4 h-24 w-24 rounded-full bg-amber-200/40 blur-2xl" />

      <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        {/* 左列：余额 */}
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-gray-400 mb-2">
            <Coins size={15} className="text-amber-500" />
            当前可用积分
          </div>
          {credit === null ? (
            <div className="h-14 w-48 animate-pulse rounded-xl bg-gray-100" />
          ) : (
            <div className={clsx('text-6xl font-bold tabular-nums tracking-tight leading-none', balanceColor)}>
              {credit.balance.toLocaleString()}
            </div>
          )}
          {credit && credit.balance < 100 && (
            <p className="mt-2 text-xs text-red-500 font-medium flex items-center gap-1">
              <Zap size={12} />
              余额不足，请及时充值
            </p>
          )}
        </div>

        {/* 右列：统计 */}
        <div className="flex gap-6 sm:gap-8">
          <div className="flex flex-col items-center sm:items-end">
            <span className="text-xs text-gray-400 mb-1">累计消耗</span>
            {credit === null ? (
              <div className="h-6 w-20 animate-pulse rounded bg-gray-100" />
            ) : (
              <span className="text-lg font-semibold text-gray-700 tabular-nums">
                {credit.total_consumed.toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex flex-col items-center sm:items-end">
            <span className="text-xs text-gray-400 mb-1">累计充值</span>
            {credit === null ? (
              <div className="h-6 w-20 animate-pulse rounded bg-gray-100" />
            ) : (
              <span className="text-lg font-semibold text-emerald-600 tabular-nums">
                {credit.total_topped_up.toLocaleString()}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 费率说明条 */}
      <div className="relative mt-6 flex flex-wrap gap-3">
        {[
          { tier: '重型模型', desc: 'GPT-4 / Opus', cost: '5 / 15 积分 / 千 token' },
          { tier: '标准模型', desc: 'Sonnet / Flash', cost: '1 / 3 积分 / 千 token' },
        ].map(({ tier, desc, cost }) => (
          <div
            key={tier}
            className="flex items-center gap-2 rounded-full bg-gray-50 border border-gray-100 px-3 py-1.5 text-xs text-gray-500"
          >
            <span className="font-medium text-gray-700">{tier}</span>
            <span className="text-gray-300">·</span>
            <span>{desc}</span>
            <span className="text-gray-300">·</span>
            <span className="text-amber-600 font-medium">{cost}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────

/**
 * 兑换码输入卡。
 *
 * @param onSuccess 兑换成功后回调（触发余额刷新）
 */
function RedeemCard({ onSuccess }: { onSuccess: (credits: number) => void }) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState<{ credits: number; balance: number } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  /** 格式化输入：自动插入连字符、大写 */
  const handleInput = (raw: string) => {
    const clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, '')
    const parts: string[] = []
    for (let i = 0; i < Math.min(clean.length, 16); i += 4) {
      parts.push(clean.slice(i, i + 4))
    }
    setCode(parts.join('-'))
    setSuccess(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = code.trim()
    if (!trimmed) return
    setLoading(true)
    try {
      const result = await redeemCode(trimmed)
      setSuccess({ credits: result.credits, balance: result.balance_after })
      onSuccess(result.credits)
      toast.success(`🎉 成功兑换 ${result.credits.toLocaleString()} 积分！`)
      setCode('')
    } catch (err: any) {
      toast.error(err?.message ?? '兑换失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const isComplete = code.replace(/-/g, '').length === 16

  return (
    <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
      {/* 卡头 */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-50">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50">
          <Gift size={18} className="text-amber-500" />
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-800">兑换码充值</p>
          <p className="text-xs text-gray-400 mt-0.5">输入有效兑换码，积分立即到账</p>
        </div>
      </div>

      {/* 输入区 */}
      <form onSubmit={handleSubmit} className="px-6 py-6">
        <div className="relative">
          {/* 装饰边框光效（激活时） */}
          <div
            className={clsx(
              'absolute inset-0 rounded-xl transition-opacity duration-300',
              isComplete ? 'opacity-100' : 'opacity-0',
              'bg-gradient-to-r from-amber-200/40 via-amber-100/20 to-amber-200/40 blur-sm',
            )}
          />
          <input
            ref={inputRef}
            type="text"
            value={code}
            onChange={e => handleInput(e.target.value)}
            placeholder="XXXX-XXXX-XXXX-XXXX"
            maxLength={19}
            spellCheck={false}
            autoComplete="off"
            className={clsx(
              'relative w-full rounded-xl border bg-gray-50 px-5 py-4 text-center',
              'font-mono text-xl tracking-[0.3em] text-gray-800 placeholder:text-gray-300',
              'focus:outline-none focus:ring-2 transition-all',
              isComplete
                ? 'border-amber-300 bg-amber-50/40 focus:ring-amber-200'
                : 'border-gray-200 focus:ring-amber-100',
            )}
          />
          {isComplete && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <CheckCircle2 size={18} className="text-amber-500" />
            </div>
          )}
        </div>

        {/* 成功提示 */}
        {success && (
          <div className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3">
            <Sparkles size={15} className="text-emerald-500 shrink-0" />
            <p className="text-sm text-emerald-700">
              已到账 <span className="font-bold">{success.credits.toLocaleString()}</span> 积分，
              当前余额 <span className="font-bold">{success.balance.toLocaleString()}</span>
            </p>
          </div>
        )}

        <button
          type="submit"
          disabled={!isComplete || loading}
          className={clsx(
            'mt-4 w-full flex items-center justify-center gap-2 rounded-xl py-3.5 text-sm font-semibold transition-all',
            isComplete && !loading
              ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-sm hover:shadow-md hover:-translate-y-px active:translate-y-0'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed',
          )}
        >
          {loading ? (
            <><Loader2 size={15} className="animate-spin" /> 兑换中…</>
          ) : (
            <><Gift size={15} /> 立即兑换</>
          )}
        </button>
      </form>
    </div>
  )
}

// ─────────────────────────────────────────────────────────

/**
 * 流水历史列表，支持分页加载。
 *
 * @param refreshKey 变化时触发重新拉取（兑换成功后递增）
 */
function TransactionHistory({ refreshKey }: { refreshKey: number }) {
  const [txns, setTxns] = useState<CreditTransaction[]>([])
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)

  const load = useCallback(async (off: number, reset: boolean) => {
    setLoading(true)
    try {
      const data = await fetchMyTransactions(PAGE_SIZE, off)
      setTxns(prev => reset ? data : [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
      setOffset(off + data.length)
    } catch {
      toast.error('流水加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 初次加载 / 兑换后刷新
  useEffect(() => {
    setOffset(0)
    setHasMore(true)
    load(0, true)
  }, [refreshKey, load])

  const loadMore = () => load(offset, false)

  if (!loading && txns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <Wallet size={36} className="mb-3 opacity-30" />
        <p className="text-sm">暂无积分记录</p>
        <p className="text-xs mt-1 text-gray-300">AI 调用或兑换码充值后将在此显示</p>
      </div>
    )
  }

  return (
    <div>
      <ul className="divide-y divide-gray-50">
        {txns.map(txn => {
          const meta = refMeta(txn.ref_type)
          const isIncome = txn.delta > 0
          return (
            <li key={txn.id} className="flex items-start gap-4 py-4 hover:bg-gray-50/60 transition-colors rounded-xl px-2">
              {/* 图标 */}
              <div className={clsx('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', meta.bg)}>
                {isIncome
                  ? <TrendingUp size={15} className={meta.color} />
                  : <TrendingDown size={15} className={meta.color} />
                }
              </div>

              {/* 主内容 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full', meta.bg, meta.color)}>
                    {meta.label}
                  </span>
                  <span className={clsx(
                    'text-sm font-bold tabular-nums',
                    isIncome ? 'text-emerald-600' : 'text-gray-600',
                  )}>
                    {isIncome ? '+' : ''}{txn.delta.toLocaleString()}
                  </span>
                </div>

                {txn.model && (
                  <p className="mt-1 text-xs text-gray-400 truncate">
                    {txn.model}
                    {txn.prompt_tokens != null && (
                      <> · in {txn.prompt_tokens.toLocaleString()} / out {(txn.completion_tokens ?? 0).toLocaleString()} tok</>
                    )}
                    {txn.task && <> · {txn.task}</>}
                  </p>
                )}

                {txn.note && (
                  <p className="mt-0.5 text-xs text-gray-400 truncate">{txn.note}</p>
                )}

                <div className="mt-1 flex items-center gap-3 text-[11px] text-gray-300">
                  <span className="flex items-center gap-1">
                    <Clock size={10} />
                    {new Date(txn.created_at).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </span>
                  <span>余额 {txn.balance_after.toLocaleString()}</span>
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {/* 加载更多 */}
      {(hasMore || loading) && (
        <button
          onClick={loadMore}
          disabled={loading}
          className="mt-2 w-full flex items-center justify-center gap-2 py-3 text-sm text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
        >
          {loading
            ? <><Loader2 size={14} className="animate-spin" /> 加载中…</>
            : <><ChevronDown size={14} /> 加载更多</>
          }
        </button>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  Main Page
// ─────────────────────────────────────────────────────────

/**
 * WalletPage — 积分钱包主页。
 *
 * 布局：固定顶栏 + 滚动主区（两栏：左侧余额+兑换码，右侧流水）。
 */
export default function WalletPage() {
  const { logout, user } = useAuthStore()
  const navigate = useNavigate()
  const [credit, setCredit] = useState<CreditBalance | null>(null)
  const [redeemKey, setRedeemKey] = useState(0)

  const refreshCredit = useCallback(async () => {
    try {
      const data = await fetchMyCredits()
      setCredit(data)
    } catch {
      // 静默失败
    }
  }, [])

  useEffect(() => {
    refreshCredit()
  }, [refreshCredit])

  const handleRedeemSuccess = (credits: number) => {
    refreshCredit()
    setRedeemKey(k => k + 1)
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const avatarLetter = user
    ? (user.username?.[0] ?? user.email?.[0] ?? '写').toUpperCase()
    : '写'

  return (
    <div className="flex min-h-screen flex-col bg-[#FAF8F4]">
      {/* ── 顶栏 ─────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-gray-100 bg-white/90 px-6 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-100"
          >
            <ArrowLeft size={12} />
            返回首页
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-50">
              <Wallet size={13} className="text-amber-500" />
            </div>
            <span className="text-sm font-semibold text-gray-800">我的钱包</span>
          </div>
        </div>

        {/* 用户 + 登出 */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-100 text-xs font-bold text-amber-700">
              {avatarLetter}
            </div>
            <span className="hidden text-xs text-gray-500 sm:block">
              {user?.username || user?.email}
            </span>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-gray-400 transition-colors hover:bg-red-50 hover:text-red-500"
          >
            <LogOut size={13} />
            <span className="hidden sm:inline">退出</span>
          </button>
        </div>
      </header>

      {/* ── 主内容区 ─────────────────────────────────────── */}
      <main className="flex-1 mx-auto w-full max-w-5xl px-4 sm:px-6 py-8">
        {/* 页标题 */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">积分钱包</h1>
          <p className="text-sm text-gray-400 mt-1">查看余额、兑换码充值、查看消耗明细</p>
        </div>

        {/* 两栏布局 */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          {/* 左栏：余额英雄区 + 兑换码 */}
          <div className="flex flex-col gap-6 lg:col-span-2">
            <BalanceHero credit={credit} />
            <RedeemCard onSuccess={handleRedeemSuccess} />
          </div>

          {/* 右栏：流水历史 */}
          <div className="lg:col-span-3">
            <div className="rounded-2xl bg-white border border-gray-100 shadow-sm overflow-hidden">
              {/* 卡头 */}
              <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-50">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gray-50">
                  <Clock size={17} className="text-gray-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">积分明细</p>
                  <p className="text-xs text-gray-400 mt-0.5">全部充值与消耗记录</p>
                </div>
              </div>

              <div className="px-4 py-2">
                <TransactionHistory refreshKey={redeemKey} />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
