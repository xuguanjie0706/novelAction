import { ChevronRight, Loader2, Trash2 } from 'lucide-react'
import type { DabaiProjectSummary } from '../../types/dabai'
import { DABAI_SHELF_GRADIENT } from './shelfCardGradient'

function timeAgo(dateStr?: string | null) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

interface Props {
  item: DabaiProjectSummary
  onOpen: () => void
  onDelete: () => void
  deleting?: boolean
}

export default function DabaiShelfCard({ item, onOpen, onDelete, deleting }: Props) {
  const g = DABAI_SHELF_GRADIENT
  const title = item.title || item.logline

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-gray-100 bg-white text-left shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg"
    >
      <div
        className="relative flex h-48 flex-col items-center justify-center px-4 text-center"
        style={{ background: `linear-gradient(145deg, ${g.from}, ${g.to})` }}
      >
        <span className="line-clamp-3 text-lg font-bold leading-snug" style={{ color: g.accent }}>
          {title}
        </span>
        <span className="mt-2 text-xs opacity-80" style={{ color: g.accent }}>
          {item.volume_count} 卷 · {item.chapter_count} 章
        </span>
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/20 group-hover:opacity-100">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 shadow-lg">
            <ChevronRight size={20} className="text-gray-800" />
          </div>
        </div>
        {item.linter_score != null && (
          <span className="absolute right-2 top-2 rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-semibold text-rose-700">
            质检 {item.linter_score}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1 px-4 py-3">
        <p className="line-clamp-2 text-[12px] text-gray-500">{item.logline}</p>
        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-[11px] text-gray-400">{timeAgo(item.created_at)}{item.mock ? ' · mock' : ''}</span>
          <button
            type="button"
            title="删除"
            disabled={deleting}
            onClick={e => {
              e.stopPropagation()
              onDelete()
            }}
            className="rounded p-1 text-gray-400 opacity-100 hover:bg-red-50 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100"
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        </div>
      </div>
    </div>
  )
}
