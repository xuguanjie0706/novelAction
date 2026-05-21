/**
 * @file 大纲历史快照 Tab
 */
import { BookOpen } from 'lucide-react'
import clsx from 'clsx'
import { outlineApi } from '../../../api/client'
import toast from 'react-hot-toast'

export interface RevisionsTabProps {
  projectId: string
  selectedVolumeId: string | null
  visibleRevisions: any[]
  compareBaseRevisionId: string | null
  isComparing: boolean
  onCompareLatestTwo: () => void
  onSelectCompareBase: (id: string) => void
  onCompareWithBase: (id: string) => void
  onReloadRevisions: () => void
}

export default function RevisionsTab({
  projectId,
  selectedVolumeId,
  visibleRevisions,
  compareBaseRevisionId,
  isComparing,
  onCompareLatestTwo,
  onSelectCompareBase,
  onCompareWithBase,
  onReloadRevisions,
}: RevisionsTabProps) {
  const handleCreateManualSnapshot = async () => {
    try {
      await outlineApi.createRevision(projectId, {
        label: '手动大纲快照',
        source: 'manual',
        scope: 'book',
      })
      toast.success('已保存当前大纲快照')
      onReloadRevisions()
    } catch {
      toast.error('保存快照失败')
    }
  }

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">大纲历史快照</h3>
          <p className="text-xs text-gray-400 mt-1">保存版本、设置 A/B 基线并快速对比结构化变化</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCompareLatestTwo}
            disabled={visibleRevisions.length < 2 || isComparing}
            className="text-[11px] px-2 py-1 rounded border border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            最近两版对比
          </button>
          <button
            type="button"
            onClick={handleCreateManualSnapshot}
            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200"
          >
            <BookOpen size={12} />
            保存快照
          </button>
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <h4 className="text-xs font-semibold text-gray-700">大纲历史快照</h4>
          <span className="text-[11px] text-gray-400">
            {selectedVolumeId ? '当前卷' : '全书'} · 共 {visibleRevisions.length} 条
          </span>
        </div>
        {visibleRevisions.length > 0 ? (
          <div className="border border-gray-100 rounded-lg divide-y divide-gray-100 overflow-hidden">
            {visibleRevisions.slice(0, 12).map(rev => (
              <div key={rev.id} className="px-3 py-2 flex items-center justify-between gap-3 text-xs">
                <div className="min-w-0">
                  <div className="font-medium text-gray-800 truncate">{rev.label}</div>
                  <div className="text-gray-400 mt-0.5">
                    {rev.source} · {rev.scope} · {rev.node_count ?? 0} 节点 · {rev.created_at ? new Date(rev.created_at).toLocaleString() : ''}
                  </div>
                </div>
                <div className="shrink-0 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onSelectCompareBase(rev.id)}
                    className={clsx(
                      'text-[10px] px-1.5 py-0.5 rounded border',
                      compareBaseRevisionId === rev.id
                        ? 'bg-indigo-100 text-indigo-700 border-indigo-200'
                        : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50',
                    )}
                  >
                    设 A
                  </button>
                  <button
                    type="button"
                    onClick={() => onCompareWithBase(rev.id)}
                    disabled={!compareBaseRevisionId || compareBaseRevisionId === rev.id || isComparing}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    与 A 对比
                  </button>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                    {String(rev.id).slice(0, 8)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="border border-dashed border-gray-200 rounded-lg px-4 py-5 text-xs text-gray-400">
            暂无快照。Graph 修复会自动保存修复前/后快照。
          </div>
        )}
      </div>
    </div>
  )
}
