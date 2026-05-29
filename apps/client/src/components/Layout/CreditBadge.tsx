/**
 * CreditBadge — 顶栏积分余额展示组件。
 *
 * 数据来源：`/api/v1/credits/me`（轮询间隔 60s，交互后立即刷新）。
 * 展示逻辑：
 *   - 余额 > 1000：绿色，正常显示。
 *   - 余额 100–999：橙色警告。
 *   - 余额 < 100：红色，附「积分不足」提示 chip。
 * 点击：展开简单的流水弹层（最近 10 条）。
 *
 * @param className 可选的额外 CSS class，用于定位调整。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Coins, ExternalLink, TrendingDown, TrendingUp, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { fetchMyCredits, fetchMyTransactions, type CreditBalance, type CreditTransaction } from '../../api/credits'

// ── 阈值常量 ─────────────────────────────────────────────────
const LOW_CREDIT_THRESHOLD = 100
const WARN_CREDIT_THRESHOLD = 1000
const POLL_INTERVAL_MS = 60_000

// ── ref_type 中文映射 ─────────────────────────────────────────
const REF_TYPE_LABEL: Record<string, string> = {
  registration_bonus: '注册赠送',
  llm_call: 'AI 调用',
  image_generation: '图片生成',
  admin_topup: '管理员充值',
  admin_adjust: '管理员调整',
  redeem_code: '兑换码',
}

interface Props {
  className?: string
}

export default function CreditBadge({ className }: Props) {
  const [credit, setCredit] = useState<CreditBalance | null>(null)
  const [transactions, setTransactions] = useState<CreditTransaction[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // ── 余额色调 ───────────────────────────────────────────────
  const colorClass = credit === null
    ? 'text-gray-400'
    : credit.balance <= 0
      ? 'text-red-600'
      : credit.balance < LOW_CREDIT_THRESHOLD
        ? 'text-red-500'
        : credit.balance < WARN_CREDIT_THRESHOLD
          ? 'text-amber-500'
          : 'text-emerald-600'

  // ── 数据拉取 ───────────────────────────────────────────────
  const refresh = useCallback(async () => {
    try {
      const data = await fetchMyCredits()
      setCredit(data)
    } catch {
      // 静默失败（例如未登录时）
    }
  }, [])

  useEffect(() => {
    refresh()
    const tid = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(tid)
  }, [refresh])

  // ── 点击展开流水 ───────────────────────────────────────────
  const handleOpen = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    setLoading(true)
    try {
      const txns = await fetchMyTransactions(10, 0)
      setTransactions(txns)
    } catch {
      setTransactions([])
    } finally {
      setLoading(false)
    }
  }

  // ── 点击面板外关闭 ─────────────────────────────────────────
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (credit === null) return null

  return (
    <div ref={panelRef} className={clsx('relative select-none', className)}>
      {/* ── 余额徽标 ─────────────────────────────────────────── */}
      <button
        onClick={handleOpen}
        className={clsx(
          'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium',
          'bg-white/80 border transition-colors hover:bg-white',
          credit.balance <= 0
            ? 'border-red-400 hover:border-red-500'
            : credit.balance < LOW_CREDIT_THRESHOLD
              ? 'border-red-300 hover:border-red-400'
              : credit.balance < WARN_CREDIT_THRESHOLD
                ? 'border-amber-300 hover:border-amber-400'
                : 'border-gray-200 hover:border-gray-300',
        )}
        title="查看积分详情"
      >
        <Coins size={14} className={colorClass} />
        <span className={clsx('tabular-nums', colorClass)}>
          {credit.balance.toLocaleString()}
        </span>
        {credit.balance <= 0 && (
          <span className="text-[10px] text-red-600 font-semibold">
            {credit.balance < 0 ? '欠款' : '已用完'}
          </span>
        )}
        {credit.balance > 0 && credit.balance < LOW_CREDIT_THRESHOLD && (
          <span className="text-[10px] text-red-500 font-semibold">积分不足</span>
        )}
      </button>

      {/* ── 流水弹层 ─────────────────────────────────────────── */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl shadow-xl border border-gray-100 z-50 overflow-hidden">
          {/* 头部 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <div>
              <p className="text-xs text-gray-500">当前积分</p>
              <p className={clsx('text-xl font-bold tabular-nums', colorClass)}>
                {credit.balance.toLocaleString()}
              </p>
            </div>
            <div className="flex flex-col items-end gap-0.5 text-xs text-gray-400">
              <span>累计消耗 {credit.total_consumed.toLocaleString()}</span>
              <span>累计充值 {credit.total_topped_up.toLocaleString()}</span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded hover:bg-gray-100 text-gray-400 ml-2"
            >
              <X size={14} />
            </button>
          </div>

          {/* 流水列表 */}
          <div className="max-h-72 overflow-y-auto">
            {loading ? (
              <p className="text-center text-gray-400 text-xs py-6">加载中…</p>
            ) : transactions.length === 0 ? (
              <p className="text-center text-gray-400 text-xs py-6">暂无流水记录</p>
            ) : (
              <ul className="divide-y divide-gray-50">
                {transactions.map(txn => (
                  <li key={txn.id} className="flex items-start gap-2 px-4 py-2.5">
                    <div className="mt-0.5 shrink-0">
                      {txn.delta > 0
                        ? <TrendingUp size={14} className="text-emerald-500" />
                        : <TrendingDown size={14} className="text-red-400" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-700 flex items-center justify-between">
                        <span>{REF_TYPE_LABEL[txn.ref_type] ?? txn.ref_type}</span>
                        <span className={clsx(
                          'font-semibold tabular-nums',
                          txn.delta > 0 ? 'text-emerald-600' : 'text-red-500',
                        )}>
                          {txn.delta > 0 ? '+' : ''}{txn.delta}
                        </span>
                      </p>
                      {txn.model && (
                        <p className="text-[10px] text-gray-400 truncate mt-0.5">
                          {txn.model}
                          {txn.prompt_tokens != null && (
                            <> · in {txn.prompt_tokens.toLocaleString()} / out {(txn.completion_tokens ?? 0).toLocaleString()} tok</>
                          )}
                        </p>
                      )}
                      {txn.note && (
                        <p className="text-[10px] text-gray-400 truncate">{txn.note}</p>
                      )}
                      <p className="text-[10px] text-gray-300 mt-0.5">
                        余额 {txn.balance_after.toLocaleString()} · {new Date(txn.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 底部：费率提示 + 钱包入口 */}
          <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100 flex items-center justify-between gap-2">
            <p className="text-[10px] text-gray-400 leading-relaxed">
              费率（每千 token）：重型 5/15 · 标准 1/3
            </p>
            <Link
              to="/wallet"
              onClick={() => setOpen(false)}
              className="shrink-0 flex items-center gap-1 text-[10px] text-amber-600 hover:text-amber-700 font-medium transition-colors"
            >
              钱包 <ExternalLink size={10} />
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
