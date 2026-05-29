/**
 * @file 直观模式 · 单章稿纸卡片（左侧连续阅读）
 */
import { forwardRef } from 'react'
import { Clock, Flame, Zap, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { IntuitiveChapterRow } from './intuitiveTypes'

const PACING_LABEL: Record<string, string> = {
  climax: '高潮',
  fast: '快',
  slow: '慢',
  normal: '常',
}

interface Props {
  row: IntuitiveChapterRow
  active: boolean
  onSelect: () => void
  onOpenWrite: () => void
}

const ChapterManuscriptCard = forwardRef<HTMLElement, Props>(function ChapterManuscriptCard(
  { row, active, onSelect, onOpenWrite },
  ref,
) {
  const { node, chapterNumber, issueCount, hasCritical } = row
  const extra = node.extra ?? {}
  const pacing = (extra.pacing as string) || node.pacing
  const hasFaceSlap = Boolean(extra.has_face_slap)
  const choiceCost = (extra.choice_cost as string) || ''
  const coreEvent = (extra.core_event as string) || ''
  const obstacle = (extra.obstacle as string) || node.conflict || ''
  const hookEnd = node.hook || (extra.chapter_end_hook as string) || ''

  const accent =
    hasCritical ? 'border-l-red-500' :
    issueCount > 0 ? 'border-l-amber-400' :
    'border-l-emerald-400/60'

  return (
    <article
      ref={ref}
      id={`intuitive-ch-${chapterNumber}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onDoubleClick={e => { e.stopPropagation(); onOpenWrite() }}
      onKeyDown={e => { if (e.key === 'Enter') onSelect() }}
      className={clsx(
        'group relative rounded-xl border border-stone-200/80 bg-[#fffcf7] shadow-sm transition-all duration-200',
        'border-l-[3px] pl-0 overflow-hidden cursor-pointer',
        accent,
        active
          ? 'ring-2 ring-amber-400/50 shadow-md scale-[1.01] z-10'
          : 'hover:shadow-md hover:border-stone-300',
      )}
    >
      <div className="px-5 py-4">
        <header className="flex items-start gap-3 mb-3">
          <span
            className={clsx(
              'shrink-0 font-mono text-2xl font-light tabular-nums leading-none pt-0.5',
              active ? 'text-amber-800' : 'text-stone-400',
            )}
          >
            {String(chapterNumber).padStart(2, '0')}
          </span>
          <div className="flex-1 min-w-0">
            <h3 className="text-[15px] font-semibold text-stone-900 leading-snug tracking-tight">
              {node.title || `第 ${chapterNumber} 章`}
            </h3>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              {pacing && pacing !== 'normal' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-stone-100 text-stone-600 border border-stone-200/80">
                  {PACING_LABEL[pacing] ?? pacing}
                </span>
              )}
              {node.emotional_tone && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-700 border border-violet-100">
                  {node.emotional_tone}
                </span>
              )}
              {hasFaceSlap && (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-100">
                  <Zap size={9} /> 爽点
                </span>
              )}
              {node.expected_words != null && node.expected_words > 0 && (
                <span className="inline-flex items-center gap-0.5 text-[10px] text-stone-400 tabular-nums">
                  <Clock size={9} />
                  {node.expected_words} 字
                </span>
              )}
              {issueCount > 0 && (
                <span
                  className={clsx(
                    'inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-md border font-medium',
                    hasCritical
                      ? 'bg-red-50 text-red-700 border-red-100'
                      : 'bg-amber-50 text-amber-800 border-amber-100',
                  )}
                >
                  <AlertTriangle size={9} />
                  {issueCount} 项待察
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={e => { e.stopPropagation(); onOpenWrite() }}
            className="opacity-0 group-hover:opacity-100 shrink-0 text-[10px] px-2 py-1 rounded-lg border border-stone-200 text-stone-500 hover:bg-stone-900 hover:text-white hover:border-stone-900 transition-all"
          >
            写作
          </button>
        </header>

        {node.summary && (
          <p className="text-[13px] text-stone-600 leading-relaxed mb-3 font-[system-ui]">
            {node.summary}
          </p>
        )}

        <div className="grid gap-2 sm:grid-cols-2 text-[11px]">
          {obstacle && (
            <div className="rounded-lg bg-stone-50/90 border border-stone-100 px-2.5 py-2">
              <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wide">障碍</span>
              <p className="text-stone-700 mt-0.5 leading-snug line-clamp-3">{obstacle}</p>
            </div>
          )}
          {coreEvent && (
            <div className="rounded-lg bg-stone-50/90 border border-stone-100 px-2.5 py-2">
              <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wide">核心事件</span>
              <p className="text-stone-700 mt-0.5 leading-snug line-clamp-3">{coreEvent}</p>
            </div>
          )}
        </div>

        {choiceCost && (
          <p className="mt-2.5 text-[11px] text-indigo-700/90 leading-snug flex items-start gap-1">
            <Flame size={11} className="shrink-0 mt-0.5 text-indigo-400" />
            <span>代价 · {choiceCost}</span>
          </p>
        )}

        {hookEnd && (
          <p className="mt-2.5 text-[12px] italic text-amber-900/80 border-t border-dashed border-amber-200/60 pt-2.5 leading-relaxed">
            「{hookEnd}」
          </p>
        )}

        {node.power_milestone && (
          <p className="mt-2 text-[10px] text-cyan-800 bg-cyan-50/80 inline-block px-2 py-0.5 rounded border border-cyan-100">
            境界 · {node.power_milestone}
          </p>
        )}
      </div>
    </article>
  )
})

export default ChapterManuscriptCard
