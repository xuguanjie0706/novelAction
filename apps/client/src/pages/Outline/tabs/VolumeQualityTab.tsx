/**
 * @file 单卷大纲质检 Tab
 */
import { Check, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import OutlinePlanQualityView from '../../../components/Outline/OutlinePlanQualityView'
import type { OutlineNode, OutlinePlanQualityReport } from '../../../types'

export interface VolumeQualityTabProps {
  selectedVolumeNode: OutlineNode | null | undefined
  displayedVolumeQuality: OutlinePlanQualityReport | undefined
  volumeQualityRevisions: any[]
  selectedVolumeQualityRevisionId: string | null
  onSelectRevision: (id: string) => void
  onDispatchQuality: (volumeNode: OutlineNode) => void
  onDispatchRepair: (volumeNode: OutlineNode) => void
  onChapterClick: (num: number) => void
}

export default function VolumeQualityTab({
  selectedVolumeNode,
  displayedVolumeQuality,
  volumeQualityRevisions,
  selectedVolumeQualityRevisionId,
  onSelectRevision,
  onDispatchQuality,
  onDispatchRepair,
  onChapterClick,
}: VolumeQualityTabProps) {
  return (
    <div className="p-6 w-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">单卷大纲质检</h3>
          <p className="text-xs text-gray-400 mt-1">
            {selectedVolumeNode
              ? `当前卷：${selectedVolumeNode.title}`
              : '请先在左侧选择一个卷（或该卷下的篇/章）'}
          </p>
        </div>
        <div className="flex max-w-[min(100vw-2rem,52rem)] flex-nowrap items-center justify-end gap-x-1.5 gap-y-0 overflow-x-auto pb-0.5 sm:max-w-none sm:gap-x-2">
          <button
            type="button"
            onClick={() => {
              if (!selectedVolumeNode) {
                toast.error('请先选择一个卷')
                return
              }
              onDispatchRepair(selectedVolumeNode)
            }}
            disabled={!selectedVolumeNode}
            className="flex shrink-0 items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 disabled:opacity-50 disabled:cursor-not-allowed sm:px-3"
          >
            <Sparkles size={12} />
            修复本卷
          </button>
          <button
            type="button"
            onClick={() => {
              if (!selectedVolumeNode) {
                toast.error('请先选择一个卷')
                return
              }
              onDispatchQuality(selectedVolumeNode)
            }}
            disabled={!selectedVolumeNode}
            className="flex shrink-0 items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg text-cyan-700 bg-cyan-50 hover:bg-cyan-100 border border-cyan-200 disabled:opacity-50 disabled:cursor-not-allowed sm:px-3"
          >
            <Check size={12} />
            重新单卷质检
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
        <div className="min-w-0">
          {selectedVolumeNode ? (
            displayedVolumeQuality && typeof displayedVolumeQuality === 'object' ? (
              <OutlinePlanQualityView report={displayedVolumeQuality} onChapterClick={onChapterClick} />
            ) : (
              <div className="border border-dashed border-cyan-200 bg-cyan-50/40 rounded-lg px-4 py-8 text-sm text-cyan-700">
                当前卷还没有质检报告。可点击右上角重新质检。
              </div>
            )
          ) : (
            <div className="border border-dashed border-gray-200 rounded-lg px-4 py-8 text-sm text-gray-500">
              未选中卷：请先在左侧点击一个卷，或点击某卷下的篇/章后再查看本页。
            </div>
          )}
        </div>
        <div className="xl:sticky xl:top-4">
          <div className="rounded-lg border border-gray-100 bg-white">
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-100">
              <h4 className="text-xs font-semibold text-gray-700">单卷质检时间线</h4>
              <span className="text-[11px] text-gray-400">共 {volumeQualityRevisions.length} 条</span>
            </div>
            {selectedVolumeNode ? (
              volumeQualityRevisions.length > 0 ? (
                <div className="max-h-[70vh] overflow-auto divide-y divide-gray-100">
                  {volumeQualityRevisions.slice(0, 24).map(rev => (
                    <button
                      key={rev.id}
                      type="button"
                      onClick={() => onSelectRevision(rev.id)}
                      className={clsx(
                        'w-full text-left px-3 py-2 hover:bg-gray-50',
                        selectedVolumeQualityRevisionId === rev.id && 'bg-cyan-50',
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
                  当前卷还没有质检历史记录。
                </div>
              )
            ) : (
              <div className="px-3 py-4 text-xs text-gray-400">
                选中卷后显示对应时间线。
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
