/**
 * ChapterVersionComparePicker — 版本列表 + 左右侧指定，再开始对照
 */
import clsx from 'clsx'
import { GitCompare, Loader2, X } from 'lucide-react'
import type { ChapterVersion } from '../../../types'
import { CURRENT_SIDE_ID } from './hooks/useChapterVersionCompare'

export default function ChapterVersionComparePicker({
  open,
  onClose,
  versionsLoading,
  versionsList,
  baseId,
  targetId,
  onAssignBase,
  onAssignTarget,
  onRunCompare,
  runningCompare,
  canCompare,
  formatVersionLabel,
  currentWordCount,
}: {
  open: boolean
  onClose: () => void
  versionsLoading: boolean
  versionsList: ChapterVersion[]
  baseId: string
  targetId: string
  onAssignBase: (id: string) => void
  onAssignTarget: (id: string) => void
  onRunCompare: () => void | Promise<void>
  runningCompare: boolean
  canCompare: boolean
  formatVersionLabel: (v: ChapterVersion) => string
  currentWordCount: number | null
}) {
  if (!open) return null

  type Row = { id: string; title: string; meta: string }

  const rows: Row[] = [
    {
      id: CURRENT_SIDE_ID,
      title: '当前正文',
      meta: currentWordCount != null ? `服务器最新 · ${currentWordCount.toLocaleString()} 字` : '服务器最新入库稿',
    },
    ...versionsList.map(v => ({
      id: v.id,
      title: formatVersionLabel(v),
      meta: typeof v.word_count === 'number' ? `${v.word_count.toLocaleString()} 字` : '历史快照',
    })),
  ]

  const sideBadge = (id: string) => {
    const tags: string[] = []
    if (id === baseId) tags.push('左')
    if (id === targetId) tags.push('右')
    return tags
  }

  return (
    <div
      className="fixed inset-0 z-[130] flex items-center justify-center p-4 bg-black/50 backdrop-blur-[2px]"
      role="dialog"
      aria-modal
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-xl max-h-[min(85vh,640px)] flex flex-col rounded-2xl border border-novel-border bg-white shadow-2xl overflow-hidden"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-novel-border shrink-0 bg-white">
          <div className="flex items-center gap-2 text-sm font-semibold text-novel-ink">
            <GitCompare size={16} className="text-amber-600 shrink-0" />
            选择对照版本
          </div>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:bg-stone-100 text-novel-ink-faint">
            <X size={16} />
          </button>
        </div>

        <p className="text-[11px] text-novel-ink-faint px-4 py-2 border-b border-stone-100 bg-stone-50 shrink-0 leading-relaxed">
          在列表中为每一侧指定版本：左侧通常为改写前备份，右侧建议选「当前正文」。门控写作内部的第 2/3 轮中间稿已自动隐藏。
        </p>

        <div className="flex-1 min-h-0 overflow-auto px-3 py-3 space-y-2 bg-white">
          {versionsLoading ? (
            <p className="text-xs text-novel-ink-faint flex items-center gap-2 px-1 py-4">
              <Loader2 size={14} className="animate-spin shrink-0" />
              正在加载版本历史并同步最新正文…
            </p>
          ) : rows.length === 0 ? (
            <p className="text-xs text-novel-ink-faint px-1 py-4 leading-relaxed">
              暂无历史版本。保存本章或经 AI 重写后会自动生成备份。
            </p>
          ) : (
            rows.map(row => {
              const tags = sideBadge(row.id)
              return (
                <div
                  key={row.id}
                  className={clsx(
                    'rounded-xl border px-3 py-2.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between',
                    tags.length > 0 ? 'border-amber-200 bg-amber-50/50' : 'border-novel-border bg-white',
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-medium text-novel-ink truncate">{row.title}</span>
                      {tags.map(t => (
                        <span
                          key={t}
                          className={clsx(
                            'text-[10px] font-bold px-1.5 py-0.5 rounded',
                            t === '左' ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800',
                          )}
                        >
                          {t === '左' ? '左侧' : '右侧'}
                        </span>
                      ))}
                    </div>
                    <p className="text-[10px] text-novel-ink-faint mt-0.5 truncate">{row.meta}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => onAssignBase(row.id)}
                      className={clsx(
                        'text-[10px] font-medium px-2.5 py-1.5 rounded-lg border transition-colors',
                        row.id === baseId
                          ? 'border-rose-300 bg-rose-50 text-rose-800'
                          : 'border-novel-border text-novel-ink-muted hover:bg-stone-50',
                      )}
                    >
                      设为左侧
                    </button>
                    <button
                      type="button"
                      onClick={() => onAssignTarget(row.id)}
                      className={clsx(
                        'text-[10px] font-medium px-2.5 py-1.5 rounded-lg border transition-colors',
                        row.id === targetId
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                          : 'border-novel-border text-novel-ink-muted hover:bg-stone-50',
                      )}
                    >
                      设为右侧
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </div>

        <div className="px-4 py-3 border-t border-stone-100 flex items-center justify-between gap-3 bg-stone-50 shrink-0">
          <p className="text-[10px] text-novel-ink-faint hidden sm:block">
            {canCompare ? '两侧已选不同版本，可以开始对照' : '请为左右两侧选择不同版本'}
          </p>
          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 text-xs rounded-lg border border-novel-border text-novel-ink hover:bg-white"
            >
              取消
            </button>
            <button
              type="button"
              disabled={versionsLoading || runningCompare || !canCompare}
              onClick={() => void onRunCompare()}
              className={clsx(
                'px-4 py-2 text-xs font-medium rounded-lg text-white',
                canCompare && !versionsLoading ? 'bg-amber-600 hover:bg-amber-500' : 'bg-stone-300 cursor-not-allowed',
              )}
            >
              {runningCompare ? '加载中…' : '开始对照'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
