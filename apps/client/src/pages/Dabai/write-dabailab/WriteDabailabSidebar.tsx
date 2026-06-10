/**
 * 写作侧栏 — 默认章节树（标题导航）；节拍卡片为可选增强视图。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import { LayoutGrid, ListTree } from 'lucide-react'
import type { DabaiChapter } from '../../../types/dabai'
import type { VolumeGroup } from './groupByVolume'
import { hasContent } from './useWriteDabailab'
import ChapterTreeNav from './sidebar/ChapterTreeNav'
import BeatCardNav from './sidebar/BeatCardNav'
import VolumeExpandButton from './sidebar/VolumeExpandButton'
import { useVolumeExpand } from './sidebar/useVolumeExpand'

type NavView = 'tree' | 'cards'
type StatusFilter = 'all' | 'todo' | 'done'

const FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'todo', label: '待写' },
  { key: 'done', label: '已写' },
]

const VIEW_KEY = 'dabai-write-nav-view'

interface Props {
  groups: VolumeGroup[]
  activeId: string | null
  realmName: (r?: number | null) => string
  onSelect: (ch: DabaiChapter) => void
  projectId: string
  /** 卷章纲展开完成后回调（重拉项目详情）。 */
  onExpanded: () => void
}

export default function WriteDabailabSidebar({
  groups, activeId, realmName, onSelect, projectId, onExpanded,
}: Props) {
  const expandState = useVolumeExpand(projectId, onExpanded)
  /** 仅未满卷（已有章数 < planned）渲染「展开/补全章纲」入口。 */
  const volumeAction = (g: VolumeGroup) =>
    g.volume.id && g.chapters.length < g.volume.planned_chapters ? (
      <VolumeExpandButton
        volume={g.volume}
        existingCount={g.chapters.length}
        state={expandState}
      />
    ) : null
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [view, setView] = useState<NavView>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === 'cards' ? 'cards' : 'tree'
    } catch {
      return 'tree'
    }
  })
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const activeTreeRef = useRef<HTMLButtonElement | null>(null)
  const activeCardRef = useRef<HTMLDivElement | null>(null)

  const volumeKey = (g: VolumeGroup) => g.volume.id ?? `v${g.volume.volume_number}`

  const activeVolumeKey = useMemo(() => {
    for (const g of groups) {
      if (g.chapters.some(c => c.id === activeId)) return volumeKey(g)
    }
    return null
  }, [groups, activeId])

  const visibleChapters = (group: VolumeGroup) =>
    group.chapters.filter(ch => {
      const done = hasContent(ch)
      if (filter === 'todo') return !done
      if (filter === 'done') return done
      return true
    })

  useEffect(() => {
    if (!activeVolumeKey) return
    setCollapsed(prev => {
      if (!prev.has(activeVolumeKey)) return prev
      const next = new Set(prev)
      next.delete(activeVolumeKey)
      return next
    })
    const t = window.setTimeout(() => {
      const el = view === 'tree' ? activeTreeRef.current : activeCardRef.current
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 120)
    return () => window.clearTimeout(t)
  }, [activeId, activeVolumeKey, view])

  const toggleVolume = (key: string) =>
    setCollapsed(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const switchView = (next: NavView) => {
    setView(next)
    try { localStorage.setItem(VIEW_KEY, next) } catch { /* ignore */ }
  }

  const isTree = view === 'tree'

  return (
    <div className={clsx(
      'flex h-full shrink-0 flex-col border-r bg-white transition-[width] duration-200',
      isTree ? 'w-56 border-gray-100' : 'w-72 border-rose-100 bg-gradient-to-b from-rose-50/30 to-white',
    )}>
      <div className="space-y-2 border-b border-gray-100 px-3 py-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">写作</span>
          <div className="flex items-center gap-0.5 rounded-lg border border-gray-100 p-0.5">
            <button
              type="button"
              title="章节树"
              onClick={() => switchView('tree')}
              className={clsx(
                'rounded p-1 transition-colors',
                isTree ? 'bg-amber-100 text-amber-700' : 'text-gray-400 hover:text-gray-600',
              )}
            >
              <ListTree size={14} />
            </button>
            <button
              type="button"
              title="节拍卡片（增强）"
              onClick={() => switchView('cards')}
              className={clsx(
                'rounded p-1 transition-colors',
                !isTree ? 'bg-rose-100 text-rose-700' : 'text-gray-400 hover:text-gray-600',
              )}
            >
              <LayoutGrid size={14} />
            </button>
          </div>
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
                  ? isTree ? 'bg-amber-500 text-white' : 'bg-rose-500 text-white'
                  : 'border border-gray-200 bg-white text-gray-600 hover:bg-gray-50',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-1.5 py-1.5">
        {groups.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-gray-400">暂无章纲</p>
        ) : isTree ? (
          <ChapterTreeNav
            groups={groups}
            activeId={activeId}
            activeVolumeKey={activeVolumeKey}
            collapsed={collapsed}
            visibleChapters={visibleChapters}
            volumeKey={volumeKey}
            activeRowRef={activeTreeRef}
            onToggleVolume={toggleVolume}
            onSelect={onSelect}
            volumeAction={volumeAction}
          />
        ) : (
          <BeatCardNav
            groups={groups}
            activeId={activeId}
            activeVolumeKey={activeVolumeKey}
            collapsed={collapsed}
            visibleChapters={visibleChapters}
            volumeKey={volumeKey}
            realmName={realmName}
            activeRowRef={activeCardRef}
            onToggleVolume={toggleVolume}
            onSelect={onSelect}
            volumeAction={volumeAction}
          />
        )}
      </div>
    </div>
  )
}
