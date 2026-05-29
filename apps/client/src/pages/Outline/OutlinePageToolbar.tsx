/**
 * @file 大纲页顶栏：经典/编剧台切换 + 经典模式子 Tab
 */
import type { ReactNode } from 'react'
import { LayoutGrid, ListTree } from 'lucide-react'
import clsx from 'clsx'

type ContentTab = 'node' | 'bookQuality' | 'volumeQuality' | 'revisions'
type ViewMode = 'classic' | 'intuitive'

interface Props {
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  contentTab: ContentTab
  onContentTabChange: (tab: ContentTab) => void
}

export default function OutlinePageToolbar({
  viewMode,
  onViewModeChange,
  contentTab,
  onContentTabChange,
}: Props) {
  return (
    <div className="shrink-0 border-b border-gray-100 bg-white px-6 pt-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center rounded-lg border border-gray-200 p-0.5 bg-gray-50 mr-1">
          <button
            type="button"
            title="经典模式：树 + 节点详情"
            onClick={() => onViewModeChange('classic')}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md transition-colors',
              viewMode === 'classic'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-800',
            )}
          >
            <ListTree size={13} />
            经典
          </button>
          <button
            type="button"
            title="直观模式：编剧台双栏"
            onClick={() => onViewModeChange('intuitive')}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md transition-colors',
              viewMode === 'intuitive'
                ? 'bg-amber-100 text-amber-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-800',
            )}
          >
            <LayoutGrid size={13} />
            编剧台
          </button>
        </div>
        {viewMode === 'classic' && (
          <>
            <TabBtn active={contentTab === 'node'} onClick={() => onContentTabChange('node')} accent="amber">
              当前节点
            </TabBtn>
            <TabBtn active={contentTab === 'bookQuality'} onClick={() => onContentTabChange('bookQuality')} accent="indigo">
              全书质检
            </TabBtn>
            <TabBtn active={contentTab === 'volumeQuality'} onClick={() => onContentTabChange('volumeQuality')} accent="cyan">
              单卷质检
            </TabBtn>
            <TabBtn active={contentTab === 'revisions'} onClick={() => onContentTabChange('revisions')} accent="slate">
              大纲快照
            </TabBtn>
          </>
        )}
      </div>
    </div>
  )
}

function TabBtn({
  active, onClick, accent, children,
}: {
  active: boolean
  onClick: () => void
  accent: 'amber' | 'indigo' | 'cyan' | 'slate'
  children: ReactNode
}) {
  const activeCls = {
    amber: 'border-amber-500 text-amber-700',
    indigo: 'border-indigo-500 text-indigo-700',
    cyan: 'border-cyan-500 text-cyan-700',
    slate: 'border-slate-500 text-slate-700',
  }[accent]
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors',
        active ? activeCls : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
      )}
    >
      {children}
    </button>
  )
}
