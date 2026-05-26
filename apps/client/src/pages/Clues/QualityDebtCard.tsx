/**
 * QualityDebtCard — 质量债务单条卡片（状态切换、备注、AI 修复、跳转写作页）
 */
import React, { useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle, Circle, ExternalLink,
  Loader2, Save, Wand2, XCircle,
} from 'lucide-react'
import clsx from 'clsx'
import type { QualityDebt } from '../../types'
import {
  QUALITY_DEBT_STATUS_LABEL, QUALITY_DEBT_STATUS_COLOR, QUALITY_DEBT_SEVERITY_COLOR,
} from './constants'

export interface QualityDebtCardProps {
  debt: QualityDebt
  chapterTitle?: string
  isAiFixing: boolean
  onStatusChange: (status: QualityDebt['status']) => void
  onSaveAuthorNotes: (id: string, notes: string) => Promise<void>
  onAiFix: (debt: QualityDebt, mode: 'micro' | 'rewrite' | 'continue') => Promise<void>
  onOpenWrite: (debt: QualityDebt) => void
}

export default function QualityDebtCard({
  debt, chapterTitle, isAiFixing,
  onStatusChange, onSaveAuthorNotes, onAiFix, onOpenWrite,
}: QualityDebtCardProps) {
  const [notesDraft, setNotesDraft] = useState(debt.author_notes ?? '')
  const [savingNotes, setSavingNotes] = useState(false)
  const [fixMode, setFixMode] = useState<'micro' | 'rewrite' | 'continue'>('micro')

  useEffect(() => {
    setNotesDraft(debt.author_notes ?? '')
  }, [debt.id, debt.author_notes])

  const saveNotes = async () => {
    setSavingNotes(true)
    try {
      await onSaveAuthorNotes(debt.id, notesDraft)
    } finally {
      setSavingNotes(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-mono text-red-600 bg-red-50 px-1.5 py-0.5 rounded">
              Ch.{debt.source_chapter_number.toString().padStart(3, '0')}
            </span>
            <span className={clsx(
              'text-[10px] px-1.5 py-0.5 rounded font-medium',
              QUALITY_DEBT_SEVERITY_COLOR[debt.severity] || QUALITY_DEBT_SEVERITY_COLOR.medium,
            )}>
              {debt.severity}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
              {debt.issue_type}
            </span>
            <span className={clsx(
              'text-[10px] px-1.5 py-0.5 rounded border',
              QUALITY_DEBT_STATUS_COLOR[debt.status],
            )}>
              {QUALITY_DEBT_STATUS_LABEL[debt.status]}
            </span>
          </div>
          <div className="text-sm font-medium text-gray-800">
            {chapterTitle || `第 ${debt.source_chapter_number} 章`}
          </div>
        </div>
        {debt.status === 'pending' && (
          <AlertTriangle size={16} className="text-red-400 shrink-0 mt-1" />
        )}
      </div>

      <p className="text-sm text-gray-700 leading-6">{debt.summary}</p>
      {debt.suggested_fix && (
        <p className="text-xs text-gray-500 leading-5 bg-gray-50 rounded-lg px-2 py-1.5">
          修正方向：{debt.suggested_fix}
        </p>
      )}

      <div className="space-y-1.5 rounded-lg border border-amber-100 bg-amber-50/40 px-2 py-2">
        <div className="text-[10px] font-medium text-amber-800">手动修复</div>
        <textarea
          value={notesDraft}
          onChange={e => setNotesDraft(e.target.value)}
          placeholder="记录你打算怎么改、改了哪里（可选，会一并交给定向 AI 修复）"
          rows={2}
          className="w-full text-xs border border-amber-100 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-amber-300 bg-white"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void saveNotes()}
            disabled={savingNotes}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-amber-200 text-amber-900 hover:bg-amber-100/80 disabled:opacity-50"
          >
            {savingNotes ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            保存备注
          </button>
          <button
            type="button"
            onClick={() => onOpenWrite(debt)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-200 text-gray-700 hover:bg-white"
          >
            <ExternalLink size={12} />去写作页改稿
          </button>
        </div>
      </div>

      {debt.status === 'pending' && (
        <div className="space-y-1.5 rounded-lg border border-violet-100 bg-violet-50/30 px-2 py-2">
          <div className="text-[10px] font-medium text-violet-800">AI 修复（定向注入本条债务）</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={fixMode}
              onChange={e => setFixMode(e.target.value as 'micro' | 'rewrite' | 'continue')}
              className="text-xs border border-violet-100 rounded-lg px-2 py-1 bg-white max-w-[220px]"
            >
              <option value="micro">局部微调（摘录替换，改动最小）</option>
              <option value="rewrite">整章重写</option>
              <option value="continue">续写追加（文末补改）</option>
            </select>
            <button
              type="button"
              onClick={() => void onAiFix(debt, fixMode)}
              disabled={isAiFixing}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
            >
              {isAiFixing ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
              {isAiFixing ? '生成中…' : 'AI 修复本章'}
            </button>
          </div>
          <p className="text-[10px] text-violet-700/90 leading-relaxed">
            「局部微调」由模型标出一段原文并替换，适合句式/事实级问题；若提示无法唯一定位或失败，请改选整章重写。流式模式会尝试解析稿末索引。
          </p>
        </div>
      )}

      <div className="flex items-center gap-2 pt-1 flex-wrap">
        <button
          type="button"
          onClick={() => onStatusChange('resolved')}
          disabled={debt.status === 'resolved'}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-green-100 text-green-700 hover:bg-green-50 disabled:opacity-50"
        >
          <CheckCircle size={12} />已修复
        </button>
        <button
          type="button"
          onClick={() => onStatusChange('dismissed')}
          disabled={debt.status === 'dismissed'}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-100 text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          <XCircle size={12} />忽略
        </button>
        {debt.status !== 'pending' && (
          <button
            type="button"
            onClick={() => onStatusChange('pending')}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-red-100 text-red-600 hover:bg-red-50"
          >
            <Circle size={12} />重开
          </button>
        )}
      </div>
    </div>
  )
}
