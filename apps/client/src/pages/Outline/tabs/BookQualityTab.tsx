/**
 * @file 全书大纲质检 Tab
 */
import { Check, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import OutlinePlanQualityView from '../../../components/Outline/OutlinePlanQualityView'
import type { OutlinePlanQualityReport } from '../../../types'

export interface BookQualityTabProps {
  displayedBookQuality: OutlinePlanQualityReport | undefined
  bookQualityRevisions: any[]
  selectedBookQualityRevisionId: string | null
  onSelectRevision: (id: string) => void
  onDispatchQuality: () => void
  onDispatchRepair: () => void
  onChapterClick: (num: number) => void
}

export default function BookQualityTab({
  displayedBookQuality,
  bookQualityRevisions,
  selectedBookQualityRevisionId,
  onSelectRevision,
  onDispatchQuality,
  onDispatchRepair,
  onChapterClick,
}: BookQualityTabProps) {
  return (
    <div className="p-6 w-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">全书大纲质检</h3>
          <p className="text-xs text-gray-400 mt-1">跨卷承接、全书镜像重复、主题兑现和世界观冲突</p>
        </div>
        <button
          type="button"
          onClick={onDispatchQuality}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200"
        >
          <Check size={12} />
          重新全书质检
        </button>
        <button
          type="button"
          onClick={onDispatchRepair}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200"
        >
          <Sparkles size={12} />
          Graph 修复全书
        </button>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
        <div className="min-w-0">
          {displayedBookQuality && typeof displayedBookQuality === 'object' ? (
            <OutlinePlanQualityView report={displayedBookQuality} onChapterClick={onChapterClick} />
          ) : (
            <div className="border border-dashed border-indigo-200 bg-indigo-50/40 rounded-lg px-4 py-8 text-sm text-indigo-700">
              当前还没有全书大纲质检报告。
            </div>
          )}
        </div>
        <div className="xl:sticky xl:top-4">
          <div className="rounded-lg border border-gray-100 bg-white">
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-100">
              <h4 className="text-xs font-semibold text-gray-700">全书质检时间线</h4>
              <span className="text-[11px] text-gray-400">共 {bookQualityRevisions.length} 条</span>
            </div>
            {bookQualityRevisions.length > 0 ? (
              <div className="max-h-[70vh] overflow-auto divide-y divide-gray-100">
                {bookQualityRevisions.slice(0, 24).map(rev => (
                  <button
                    key={rev.id}
                    type="button"
                    onClick={() => onSelectRevision(rev.id)}
                    className={clsx(
                      'w-full text-left px-3 py-2 hover:bg-gray-50',
                      selectedBookQualityRevisionId === rev.id && 'bg-indigo-50',
                    )}
                  >
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <div className="min-w-0">
                        <div className="font-medium text-gray-800 truncate">{rev.label}</div>
                        <div className="text-gray-400 mt-0.5">
                          score {rev.meta?.quality_score ?? '-'} · {rev.meta?.quality_status ?? '-'} · {rev.created_at ? new Date(rev.created_at).toLocaleString() : ''}
                        </div>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                        {String(rev.id).slice(0, 8)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-4 text-xs text-gray-400">
                还没有全书质检历史记录。
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
