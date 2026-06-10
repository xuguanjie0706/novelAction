/**
 * DabaiWriteSidebar — 章纲五拍列表 + 同步入口
 */
import clsx from 'clsx'
import { Loader2, RefreshCw, Zap } from 'lucide-react'
import DabaiChapterBeatCard from '../../components/Dabai/DabaiChapterBeatCard'
import type { Chapter, OutlineNode } from '../../types'
import type { DabaiBeatDisplay } from '../../utils/dabaiOutlineDisplay'

interface PlanRow {
  plan: OutlineNode
  chapter?: Chapter
  beat: DabaiBeatDisplay | null
}

interface Props {
  planRows: PlanRow[]
  activeChapterId?: string | null
  unsyncedCount: number
  syncing: boolean
  onSelect: (plan: OutlineNode) => void
  onSyncAll: () => void
}

export default function DabaiWriteSidebar({
  planRows,
  activeChapterId,
  unsyncedCount,
  syncing,
  onSelect,
  onSyncAll,
}: Props) {
  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-rose-100 bg-gradient-to-b from-rose-50/40 to-white">
      <div className="border-b border-rose-100 px-3 py-3 space-y-2">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-rose-500" />
          <span className="text-xs font-semibold text-rose-800">大白文 · 爽点写作</span>
        </div>
        <p className="text-[11px] leading-relaxed text-rose-700/80">
          按章节要素五拍写正文；写后只做设定一致性校验，不走通用质检循环。
        </p>
        {unsyncedCount > 0 && (
          <button
            type="button"
            onClick={onSyncAll}
            disabled={syncing}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-200 bg-white py-1.5 text-[11px] font-medium text-rose-700 hover:bg-rose-50"
          >
            <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
            同步 {unsyncedCount} 章写作入口
          </button>
        )}
      </div>

      <div className="flex-1 overflow-auto p-2 space-y-2">
        {planRows.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-gray-400">
            请先到「大纲」展开卷章纲
          </p>
        ) : (
          planRows.map(({ plan, chapter, beat }) => {
            if (!beat) return null
            const active = chapter?.id === activeChapterId
            return (
              <DabaiChapterBeatCard
                key={plan.id}
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
            )
          })
        )}
      </div>
    </div>
  )
}
