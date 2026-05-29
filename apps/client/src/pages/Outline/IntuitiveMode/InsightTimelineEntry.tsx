/**
 * @file 直观模式 · 诊脉轨单条时间轴节点
 */
import { forwardRef } from 'react'
import { Bot, CheckCircle2, Layers, ShieldAlert } from 'lucide-react'
import clsx from 'clsx'
import type { InsightTimelineEntry as Entry } from './intuitiveTypes'

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.5)]',
  high: 'bg-orange-500',
  medium: 'bg-amber-400',
  low: 'bg-slate-500',
  info: 'bg-emerald-500/70',
}

const SEV_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-amber-400',
  low: 'border-l-slate-500',
  info: 'border-l-emerald-500/70',
}

const KIND_ICON = {
  linter: ShieldAlert,
  quality: Bot,
  strength: CheckCircle2,
  volume_meta: Layers,
} as const

interface Props {
  entry: Entry
  active: boolean
  onSelect: () => void
}

const InsightTimelineEntryCard = forwardRef<HTMLDivElement, Props>(function InsightTimelineEntryCard(
  { entry, active, onSelect },
  ref,
) {
  const Icon = KIND_ICON[entry.kind] ?? ShieldAlert
  const chLabel = entry.chapterNumber != null
    ? `第 ${entry.chapterNumber} 章`
    : '全卷'

  return (
    <div
      ref={ref}
      id={`intuitive-insight-${entry.id}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={e => { if (e.key === 'Enter') onSelect() }}
      className={clsx(
        'relative flex gap-3 pl-1 pr-2 py-2 rounded-lg transition-colors cursor-pointer',
        active ? 'bg-white/10' : 'hover:bg-white/5',
      )}
    >
      <div className="flex flex-col items-center shrink-0 w-3 pt-1.5">
        <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', SEV_DOT[entry.severity] ?? SEV_DOT.low)} />
        <span className="flex-1 w-px bg-gradient-to-b from-slate-600/80 to-transparent min-h-[8px] mt-1" />
      </div>

      <div
        className={clsx(
          'relative flex-1 min-w-0 rounded-lg border-l-[3px] px-3 py-2.5 transition-all',
          SEV_BORDER[entry.severity] ?? SEV_BORDER.low,
          active
            ? 'border-amber-400/40 border-t border-r border-b bg-slate-800/90 shadow-lg shadow-amber-900/10'
            : 'border-t border-r border-b border-slate-700/60 bg-slate-800/40',
        )}
      >
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <Icon size={12} className={clsx(
            entry.kind === 'strength' ? 'text-emerald-400' :
            entry.kind === 'quality' ? 'text-indigo-400' : 'text-amber-400',
          )} />
          <span className="text-[10px] font-mono text-slate-500 tabular-nums">{chLabel}</span>
          <span className="text-[11px] font-medium text-slate-200 leading-tight">{entry.title}</span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed">{entry.message}</p>
        {entry.suggestion && (
          <p className="text-[10px] text-indigo-300/90 mt-1.5 leading-snug border-t border-slate-700/50 pt-1.5">
            ↳ {entry.suggestion}
          </p>
        )}
      </div>
    </div>
  )
})

export default InsightTimelineEntryCard
