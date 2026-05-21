/**
 * @file 大纲快照对比抽屉
 */
import { X } from 'lucide-react'
import clsx from 'clsx'
import { FIELD_LABEL, type OutlineDiffItem, type OutlineDiffResult } from './diffUtils'

export interface OutlineCompareDrawerProps {
  open: boolean
  compareResult: OutlineDiffResult | null
  compareFilter: 'all' | 'high' | 'structure' | 'content'
  onFilterChange: (f: OutlineCompareDrawerProps['compareFilter']) => void
  onClose: () => void
  compareBaseRevisionId: string | null
  compareTargetRevisionId: string | null
  compareBaseRevision?: { label?: string }
  compareTargetRevision?: { label?: string }
  filteredChanges: OutlineDiffItem[]
}

export default function OutlineCompareDrawer({
  open,
  compareResult,
  compareFilter,
  onFilterChange,
  onClose,
  compareBaseRevisionId,
  compareTargetRevisionId,
  compareBaseRevision,
  compareTargetRevision,
  filteredChanges,
}: OutlineCompareDrawerProps) {
  if (!open || !compareResult) return null

  return (
    <>
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />
      <div className="fixed top-0 right-0 h-full w-full max-w-xl bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-100 flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-gray-900">快照快速比对</h4>
            <p className="text-[11px] text-gray-500 mt-1">
              A：{compareBaseRevision?.label || String(compareBaseRevisionId).slice(0, 8)} · B：{compareTargetRevision?.label || String(compareTargetRevisionId).slice(0, 8)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-4 py-3 border-b border-gray-100 grid grid-cols-4 gap-2 text-xs">
          <div className="rounded border border-green-100 bg-green-50 px-2 py-1.5">
            <div className="text-green-700 font-semibold">{compareResult.summary.added}</div>
            <div className="text-green-600/90">新增</div>
          </div>
          <div className="rounded border border-red-100 bg-red-50 px-2 py-1.5">
            <div className="text-red-700 font-semibold">{compareResult.summary.removed}</div>
            <div className="text-red-600/90">删除</div>
          </div>
          <div className="rounded border border-amber-100 bg-amber-50 px-2 py-1.5">
            <div className="text-amber-700 font-semibold">{compareResult.summary.updated}</div>
            <div className="text-amber-600/90">修改</div>
          </div>
          <div className="rounded border border-indigo-100 bg-indigo-50 px-2 py-1.5">
            <div className="text-indigo-700 font-semibold">{compareResult.summary.high}</div>
            <div className="text-indigo-600/90">高风险</div>
          </div>
        </div>

        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1 text-xs">
          {([
            ['high', '仅高风险'],
            ['structure', '结构变更'],
            ['content', '内容修改'],
            ['all', '全部'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => onFilterChange(key)}
              className={clsx(
                'px-2 py-1 rounded border',
                compareFilter === key
                  ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto px-4 py-3 space-y-2">
          {filteredChanges.length === 0 ? (
            <div className="text-xs text-gray-400 border border-dashed border-gray-200 rounded-lg p-4 text-center">
              当前筛选下没有变化。
            </div>
          ) : (
            filteredChanges.map(change => (
              <div key={`${change.changeType}-${change.nodeId}`} className="border border-gray-100 rounded-lg p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-gray-800 truncate">{change.title}</div>
                    <div className="text-[11px] text-gray-400 truncate mt-0.5">{change.path}</div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className={clsx(
                      'text-[10px] px-1.5 py-0.5 rounded',
                      change.changeType === 'added'
                        ? 'bg-green-100 text-green-700'
                        : change.changeType === 'removed'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-amber-100 text-amber-700',
                    )}>
                      {change.changeType === 'added' ? '新增' : change.changeType === 'removed' ? '删除' : '修改'}
                    </span>
                    <span className={clsx(
                      'text-[10px] px-1.5 py-0.5 rounded',
                      change.severity === 'high'
                        ? 'bg-rose-100 text-rose-700'
                        : change.severity === 'medium'
                          ? 'bg-orange-100 text-orange-700'
                          : 'bg-gray-100 text-gray-600',
                    )}>
                      {change.severity}
                    </span>
                  </div>
                </div>
                {change.fields && change.fields.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {change.fields.slice(0, 4).map(field => (
                      <div key={field.field} className="text-[11px] rounded bg-gray-50 border border-gray-100 p-2">
                        <div className="text-gray-500">{FIELD_LABEL[field.field] || field.field}</div>
                        <div className="text-red-500 mt-0.5 line-clamp-2">- {field.before}</div>
                        <div className="text-green-600 mt-0.5 line-clamp-2">+ {field.after}</div>
                      </div>
                    ))}
                    {change.fields.length > 4 && (
                      <div className="text-[10px] text-gray-400">
                        还有 {change.fields.length - 4} 项字段变化...
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </>
  )
}
