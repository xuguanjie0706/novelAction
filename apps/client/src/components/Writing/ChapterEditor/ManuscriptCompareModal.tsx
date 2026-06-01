/**
 * @file AI 重写前后正文对照（单按钮唤起，创作端视觉）
 */
import { useMemo } from 'react'
import { GitCompare, X } from 'lucide-react'
import clsx from 'clsx'
import { alignChapterLines } from '../../../utils/chapterLineDiff'

export interface ManuscriptCompareModalProps {
  open: boolean
  chapterTitle: string
  beforePlain: string
  afterPlain: string
  beforeLabel?: string
  afterLabel?: string
  onClose: () => void
}

export function ManuscriptCompareModal({
  open,
  chapterTitle,
  beforePlain,
  afterPlain,
  beforeLabel = '基准版本',
  afterLabel = '对照版本',
  onClose,
}: ManuscriptCompareModalProps) {
  const rows = useMemo(() => alignChapterLines(beforePlain, afterPlain), [beforePlain, afterPlain])
  const displayRows = useMemo(
    () =>
      rows.length > 0
        ? rows
        : [{ left: '（空）', right: '（空）', leftChanged: false, rightChanged: false }],
    [rows],
  )

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-stone-900/35 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        className="fixed inset-4 sm:inset-8 md:inset-12 z-[61] flex flex-col rounded-2xl border border-novel-border bg-novel-card shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal
        aria-labelledby="manuscript-compare-title"
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-novel-border bg-gradient-to-r from-amber-50/90 to-novel-card shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-novel-ink">
              <GitCompare size={18} className="text-amber-600 shrink-0" />
              <h2 id="manuscript-compare-title" className="text-sm font-semibold truncate">
                重写前后对比 · {chapterTitle}
              </h2>
            </div>
            <p className="text-[11px] text-novel-ink-muted mt-1 leading-relaxed">
              左侧：{beforeLabel} · 右侧：{afterLabel}。稿末索引块已隐藏，便于阅读差异。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-novel-ink-faint hover:text-novel-ink hover:bg-stone-100 transition-novel shrink-0"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </header>

        <div className="grid grid-cols-2 gap-0 border-b border-novel-border bg-stone-50/80 text-[11px] shrink-0">
          <div className="px-4 py-2 border-r border-novel-border">
            <span className="font-semibold text-rose-800">左侧</span>
            <span className="text-novel-ink-faint ml-2 truncate">{beforeLabel}</span>
          </div>
          <div className="px-4 py-2">
            <span className="font-semibold text-emerald-800">右侧</span>
            <span className="text-novel-ink-faint ml-2 truncate">{afterLabel}</span>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto bg-white">
          <table className="w-full table-fixed border-collapse">
            <colgroup>
              <col className="w-1/2" />
              <col className="w-1/2" />
            </colgroup>
            <tbody>
              {displayRows.map((row, idx) => (
                <tr key={idx}>
                  <td
                    className={clsx(
                      'align-top px-3 py-1.5 text-[13px] leading-relaxed border-r border-stone-100 border-b border-stone-50 whitespace-pre-wrap break-words',
                      row.leftChanged ? 'bg-rose-50/90' : 'bg-white',
                    )}
                  >
                    {row.left || '\u00a0'}
                  </td>
                  <td
                    className={clsx(
                      'align-top px-3 py-1.5 text-[13px] leading-relaxed border-b border-stone-50 whitespace-pre-wrap break-words',
                      row.rightChanged ? 'bg-emerald-50/90' : 'bg-stone-50/30',
                    )}
                  >
                    {row.right || '\u00a0'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <footer className="px-5 py-3 border-t border-novel-border bg-novel-card shrink-0 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-novel border border-novel-border text-novel-ink hover:bg-stone-50 transition-novel"
          >
            关闭
          </button>
        </footer>
      </div>
    </>
  )
}
