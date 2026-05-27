/**
 * 写作侧栏：已同步番茄的章节角标（紧凑火焰标）。
 */
import { Flame } from 'lucide-react'
import clsx from 'clsx'

export interface FanqieSyncedBadgeProps {
  /** 悬停说明，可含同步标题 */
  title?: string
  className?: string
  /** 极窄侧栏用仅图标；默认带「番」字 */
  compact?: boolean
}

export default function FanqieSyncedBadge({
  title = '已同步到番茄作家后台',
  className,
  compact = false,
}: FanqieSyncedBadgeProps) {
  return (
    <span
      title={title}
      aria-label={title}
      className={clsx(
        'inline-flex items-center justify-center shrink-0',
        'rounded-full',
        'bg-gradient-to-br from-rose-50 via-orange-50 to-amber-50',
        'ring-1 ring-rose-200/70 shadow-[0_1px_2px_rgba(244,63,94,0.12)]',
        compact ? 'h-3.5 w-3.5' : 'h-[18px] min-w-[18px] px-0.5 gap-px',
        className,
      )}
    >
      <Flame
        size={compact ? 8 : 9}
        className="text-rose-500"
        fill="currentColor"
        strokeWidth={2.25}
      />
      {!compact && (
        <span className="text-[8px] font-bold leading-none text-rose-600 pr-0.5 select-none">
          番
        </span>
      )}
    </span>
  )
}
