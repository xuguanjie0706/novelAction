/**
 * @file 大白文章纲 · 爽点节拍卡片（憋屈→转折→爽点→钩子）。
 * 用于 /dabai 独立页、大纲编剧台、卷详情章节清单。
 */
import type { ReactNode } from 'react'
import { Star, PenLine, Clock } from 'lucide-react'
import clsx from 'clsx'
import type { DabaiBeatDisplay } from '../../utils/dabaiOutlineDisplay'
import { DABAI_SHUANG_BADGE } from '../../utils/dabaiOutlineDisplay'

interface BeatRowProps {
  label: string
  value: string
  labelClass?: string
  valueClass?: string
}

function BeatRow({ label, value, labelClass = 'text-gray-400', valueClass = 'text-gray-600' }: BeatRowProps) {
  if (!value.trim()) return null
  return (
    <div className="grid gap-x-3 gap-y-0.5 text-xs sm:grid-cols-[3rem_1fr]">
      <span className={clsx('font-medium shrink-0', labelClass)}>{label}</span>
      <span className={clsx('leading-relaxed', valueClass)}>{value}</span>
    </div>
  )
}

export interface DabaiChapterBeatCardProps {
  beat: DabaiBeatDisplay
  /** embedded：编剧台稿纸内嵌；card：独立带边框卡片 */
  variant?: 'card' | 'embedded'
  active?: boolean
  className?: string
  onClick?: () => void
  onWrite?: () => void
  writeLabel?: string
  /** 右侧附加操作（如 linter 徽章） */
  trailing?: ReactNode
}

export default function DabaiChapterBeatCard({
  beat,
  variant = 'card',
  active,
  className,
  onClick,
  onWrite,
  writeLabel = '写正文',
  trailing,
}: DabaiChapterBeatCardProps) {
  const shuangCls = DABAI_SHUANG_BADGE[beat.shuangType] ?? 'bg-gray-100 text-gray-600'
  const payoff = beat.shuangPayoff.trim()
  const showYinbao = beat.yinbao.trim() && beat.yinbao.trim() !== payoff

  const shellCls = clsx(
    variant === 'card' && 'rounded-xl border border-gray-100 bg-white p-3 hover:border-amber-200 transition-colors',
    variant === 'embedded' && 'mt-2 pt-3 border-t border-dashed border-stone-200/80',
    active && variant === 'card' && 'border-amber-300 ring-1 ring-amber-200/80',
    onClick && 'cursor-pointer',
    className,
  )

  return (
    <div
      className={shellCls}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? e => { if (e.key === 'Enter') onClick() } : undefined}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-gray-900 tabular-nums">
          第{beat.chapterNumber}章
        </span>
        <span className="text-sm text-gray-700">{beat.titleText}</span>
        {beat.shuangType && (
          <span className={clsx('rounded-full px-2 py-0.5 text-xs font-medium', shuangCls)}>
            {beat.shuangType}
          </span>
        )}
        {beat.isBigBeat && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-600">
            <Star size={11} fill="currentColor" />大爆点
          </span>
        )}
        {beat.realmLabel && (
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">
            {beat.realmLabel}
          </span>
        )}
        {beat.locationName && (
          <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs text-sky-600">
            {beat.locationName}
          </span>
        )}
        {beat.expectedWords != null && beat.expectedWords > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-gray-400 tabular-nums ml-auto">
            <Clock size={10} />
            {beat.expectedWords}字
          </span>
        )}
        {onWrite && (
          <button
            type="button"
            onClick={e => { e.stopPropagation(); onWrite() }}
            className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-amber-600 hover:bg-amber-50"
          >
            <PenLine size={12} />{writeLabel}
          </button>
        )}
        {trailing}
      </div>

      <div className="mt-2.5 space-y-1.5">
        <BeatRow label="憋屈" value={beat.yaquSetup} />
        <BeatRow label="转折" value={beat.emotionTurn} labelClass="text-violet-400" />
        {showYinbao && (
          <BeatRow label="引爆" value={beat.yinbao} labelClass="text-amber-500" />
        )}
        <BeatRow label="爽点" value={payoff} labelClass="text-rose-400" valueClass="text-gray-800" />
        <BeatRow label="钩子" value={beat.endHook} />
      </div>
    </div>
  )
}
