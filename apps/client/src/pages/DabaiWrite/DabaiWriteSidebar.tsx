/**
 * DabaiWriteSidebar — 分卷折叠章纲导航：
 * 卷头（已写/总数）折叠展开 + 待写/已写筛选 + 自动定位当前章。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronRight, Loader2, RefreshCw, Zap } from 'lucide-react'
import DabaiChapterBeatCard from '../../components/Dabai/DabaiChapterBeatCard'
import type { Chapter, OutlineNode } from '../../types'
import type { DabaiBeatDisplay } from '../../utils/dabaiOutlineDisplay'

interface PlanRow {
  plan: OutlineNode
  chapter?: Chapter
  beat: DabaiBeatDisplay | null
}

interface VolumeGroupRow {
  volume: OutlineNode | null
  rows: PlanRow[]
}

type StatusFilter = 'all' | 'todo' | 'done'

const FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'todo', label: '待写' },
  { key: 'done', label: '已写' },
]

interface Props {
  volumeGroups: VolumeGroupRow[]
  activeChapterId?: string | null
  unsyncedCount: number
  syncing: boolean
  onSelect: (plan: OutlineNode) => void
  onSyncAll: () => void
}

function rowWritten(row: PlanRow): boolean {
  return (row.chapter?.word_count ?? 0) > 0
}

export default function DabaiWriteSidebar({
  volumeGroups,
  activeChapterId,
  unsyncedCount,
  syncing,
  onSelect,
  onSyncAll,
}: Props) {
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const activeCardRef = useRef<HTMLDivElement | null>(null)

  const volumeKey = (g: VolumeGroupRow) => g.volume?.id ?? '__orphan__'

  /** 当前章所在卷：切章时自动展开并滚动定位 */
  const activeVolumeKey = useMemo(() => {
    for (const g of volumeGroups) {
      if (g.rows.some(r => r.chapter?.id === activeChapterId)) return volumeKey(g)
    }
    return null
  }, [volumeGroups, activeChapterId])

  useEffect(() => {
    if (!activeVolumeKey) return
    setCollapsed(prev => {
      if (!prev.has(activeVolumeKey)) return prev
      const next = new Set(prev)
      next.delete(activeVolumeKey)
      return next
    })
    // 等折叠状态生效后再滚动
    const t = window.setTimeout(() => {
      activeCardRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 120)
    return () => window.clearTimeout(t)
  }, [activeChapterId, activeVolumeKey])

  const toggleVolume = (key: string) =>
    setCollapsed(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-rose-100 bg-gradient-to-b from-rose-50/40 to-white">
      <div className="border-b border-rose-100 px-3 py-3 space-y-2">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-rose-500" />
          <span className="text-xs font-semibold text-rose-800">大白文 · 爽点写作</span>
        </div>
        <div className="flex gap-1">
          {FILTERS.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={clsx(
                'flex-1 rounded-md py-1 text-[11px] font-medium transition-colors',
                filter === f.key
                  ? 'bg-rose-500 text-white'
                  : 'bg-white text-rose-700 border border-rose-200 hover:bg-rose-50',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        {unsyncedCount > 0 && (
          <button
            type="button"
            onClick={onSyncAll}
            disabled={syncing}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-200 bg-white py-1.5 text-[11px] font-medium text-rose-700 hover:bg-rose-50"
          >
            <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
            {syncing ? <Loader2 size={11} className="animate-spin" /> : null}
            同步 {unsyncedCount} 章写作入口
          </button>
        )}
      </div>

      <div className="flex-1 overflow-auto p-2 space-y-1.5">
        {volumeGroups.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-gray-400">
            请先到「大纲」展开卷章纲
          </p>
        ) : (
          volumeGroups.map(group => {
            const key = volumeKey(group)
            const isCollapsed = collapsed.has(key)
            const writtenCount = group.rows.filter(rowWritten).length
            const visibleRows = group.rows.filter(row => {
              if (filter === 'todo') return !rowWritten(row)
              if (filter === 'done') return rowWritten(row)
              return true
            })
            return (
              <div key={key}>
                <button
                  type="button"
                  onClick={() => toggleVolume(key)}
                  className={clsx(
                    'flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-xs font-semibold',
                    key === activeVolumeKey ? 'bg-rose-100/70 text-rose-900' : 'text-gray-700 hover:bg-rose-50',
                  )}
                >
                  {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                  <span className="min-w-0 flex-1 truncate">
                    {group.volume ? group.volume.title : '未分卷章节'}
                  </span>
                  <span className="shrink-0 tabular-nums text-[10px] font-normal text-gray-400">
                    {writtenCount}/{group.rows.length}
                  </span>
                </button>
                {!isCollapsed && (
                  <div className="mt-1 space-y-1.5 pl-1.5">
                    {visibleRows.length === 0 ? (
                      <p className="px-2 py-2 text-[11px] text-gray-300">
                        {filter === 'todo' ? '本卷已全部写完' : filter === 'done' ? '本卷暂无已写章节' : '无章节'}
                      </p>
                    ) : (
                      visibleRows.map(({ plan, chapter, beat }) => {
                        if (!beat) return null
                        const active = !!chapter && chapter.id === activeChapterId
                        return (
                          <div key={plan.id} ref={active ? activeCardRef : undefined}>
                            <DabaiChapterBeatCard
                              beat={beat}
                              active={active}
                              onClick={() => onSelect(plan)}
                              trailing={
                                chapter ? (
                                  <span className={clsx(
                                    'text-[10px] tabular-nums shrink-0',
                                    active ? 'text-amber-700' : 'text-gray-400',
                                  )}>
                                    {chapter.word_count > 0 ? `${chapter.word_count}字` : '待写'}
                                  </span>
                                ) : (
                                  <span className="text-[10px] text-gray-300 shrink-0">待同步</span>
                                )
                              }
                            />
                          </div>
                        )
                      })
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
