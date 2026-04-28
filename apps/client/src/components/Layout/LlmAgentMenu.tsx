import React, { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown } from 'lucide-react'
import clsx from 'clsx'
import { llmApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { LlmOverview } from '../../types'

/**
 * 顶部栏右上角：后端登记的「智能体」详情下拉（与「本地 / Gemini」选择联动）。
 */
export default function LlmAgentMenu() {
  const aiModelProfile = useAppStore(s => s.aiModelProfile)
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<LlmOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    llmApi
      .overview()
      .then(res => {
        if (!cancelled) {
          setData(res.data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const useRemote = aiModelProfile === 'gemini'
  let summary = ''
  let warn = false
  if (loading) summary = '加载中…'
  else if (!data) {
    summary = '无法连接后端'
    warn = true
  } else if (useRemote) {
    if (!data.remote_ready) {
      summary = '未配置'
      warn = true
    } else {
      const label = data.remote_agent?.name ?? (data.remote_source === 'env' ? '环境变量' : '远程')
      summary = `${label}`
    }
  } else {
    summary = data.local_model_name
  }

  return (
    <div className="relative shrink-0" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className={clsx(
          'flex items-center gap-1 rounded-lg border px-2 py-1 text-xs transition-colors',
          warn
            ? 'border-amber-200 bg-amber-50 text-amber-800'
            : 'border-gray-200 bg-gray-50/80 text-gray-700 hover:bg-gray-100'
        )}
        aria-expanded={open}
        aria-haspopup="true"
        title="查看后端登记的大模型 / 智能体"
      >
        <Bot size={14} className="shrink-0 text-gray-500" aria-hidden />
        <span className="hidden sm:inline max-w-[7rem] truncate">智能体</span>
        <span className="max-w-[5rem] sm:max-w-[6rem] truncate text-[11px] text-gray-500">· {summary}</span>
        <ChevronDown size={12} className={clsx('shrink-0 text-gray-400 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-1 w-64 rounded-xl border border-gray-200 bg-white py-2.5 px-3 shadow-lg"
          role="menu"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-2">大模型 / 智能体</div>
          <p className="text-[11px] text-gray-500 mb-2">
            与右侧「本地 / Gemini」一致：选 Gemini 时走下方远程线路；选本地则用本地模型。
          </p>
          <div className="rounded-lg bg-stone-50 px-2.5 py-2 text-xs space-y-1.5 border border-stone-100">
            <div className="flex justify-between gap-2">
              <span className="text-gray-500 shrink-0">当前模式</span>
              <span className="font-medium text-gray-800 text-right">{useRemote ? '远程' : '本地'}</span>
            </div>
            {loading && <p className="text-gray-400">正在拉取后端配置…</p>}
            {!loading && !data && <p className="text-amber-700">无法连接后端，请检查服务与代理。</p>}
            {!loading && data && (
              <>
                <div className="flex justify-between gap-2">
                  <span className="text-gray-500 shrink-0">本地模型</span>
                  <span className="text-gray-800 text-right break-all">{data.local_model_name}</span>
                </div>
                <div className="border-t border-stone-200 pt-1.5 mt-1.5">
                  <div className="text-gray-500 mb-0.5">远程线路</div>
                  {!data.remote_ready ? (
                    <p className="text-amber-700 text-[11px] leading-snug">
                      未配置。请在管理后台「大模型」中添加并设为默认，或配置环境变量 GEMINI_*。
                    </p>
                  ) : (
                    <div className="text-[11px] text-gray-800 space-y-0.5">
                      <p>
                        <span className="text-gray-500">名称：</span>
                        {data.remote_agent?.name ?? (data.remote_source === 'env' ? '环境变量 (.env)' : '—')}
                      </p>
                      <p className="break-all">
                        <span className="text-gray-500">模型 ID：</span>
                        {data.effective_remote_model ?? data.remote_agent?.model_name ?? '—'}
                      </p>
                      {data.remote_source === 'database' && (
                        <p className="text-[10px] text-gray-400">来源：管理后台持久化</p>
                      )}
                      {data.remote_source === 'env' && (
                        <p className="text-[10px] text-gray-400">来源：环境变量（未入库）</p>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
