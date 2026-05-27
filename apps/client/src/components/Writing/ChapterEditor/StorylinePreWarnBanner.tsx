/**
 * 编辑区顶部：故事线织网写前预警（可折叠）
 */
import { useState } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronUp, GitBranch } from 'lucide-react'
import type { StorylinePreWarnItem } from './types'

export default function StorylinePreWarnBanner({
  items,
  onOpenWarnTab,
}: {
  items: StorylinePreWarnItem[]
  onOpenWarnTab?: () => void
}) {
  const [open, setOpen] = useState(true)
  if (items.length === 0) return null

  const sorted = [...items].sort((a, b) => {
    const rank = { critical: 0, warning: 1, info: 2 }
    return (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9)
  })

  return (
    <div className="border-b border-indigo-200/80 bg-indigo-50/90 shrink-0">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-2 text-left"
        onClick={() => setOpen(v => !v)}
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-indigo-900">
          <GitBranch size={14} />
          故事线织网预警（{items.length}）
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1.5 max-h-40 overflow-y-auto">
          {sorted.map((w, i) => (
            <div
              key={w.warn_id || i}
              className={clsx(
                'text-xs rounded-md px-2.5 py-1.5 border',
                w.severity === 'critical' && 'bg-rose-50 border-rose-200 text-rose-900',
                w.severity === 'warning' && 'bg-amber-50 border-amber-200 text-amber-900',
                w.severity === 'info' && 'bg-sky-50 border-sky-200 text-sky-900',
              )}
            >
              <span className="font-medium">{w.title}</span>
              {w.detail && <p className="mt-0.5 opacity-90">{w.detail}</p>}
            </div>
          ))}
          {onOpenWarnTab && (
            <button
              type="button"
              onClick={onOpenWarnTab}
              className="text-[10px] text-indigo-700 underline mt-1"
            >
              在「预警」Tab 查看详情
            </button>
          )}
        </div>
      )}
    </div>
  )
}
