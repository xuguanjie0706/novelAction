/**
 * @file 单条生成任务卡片（进度 + 质检展开）
 */
import { useState } from 'react'
import {
  Loader2, CheckCircle2, AlertCircle, AlertTriangle, X,
} from 'lucide-react'
import clsx from 'clsx'
import type { GenTask, GenProgressItem } from '../../../types'
import OutlinePlanQualityView from '../../Outline/OutlinePlanQualityView'

export function progressRowKey(p: GenProgressItem, idx: number) {
  return p.progressKey ?? `p-${String(p.step)}-${idx}`
}

export function isTaskInterruptedByReload(task: GenTask): boolean {
  return task.status === 'error' && (
    !!task.errorMsg?.includes('页面刷新') ||
    !!task.errorMsg?.includes('页面重载') ||
    task.progress.some(p => p.step === 'resume')
  )
}

export function TaskCard({
  task,
  onRemove,
  onCancel,
  onRetry,
}: {
  task: GenTask
  onRemove: () => void
  onCancel: () => void
  onRetry: () => void
}) {
  const [expandedPk, setExpandedPk] = useState<string | null>(null)
  const isRunning = task.status === 'running'
  const isPending = task.status === 'pending'
  const isDone = task.status === 'done'
  const isError = task.status === 'error'
  const isCancelled = task.status === 'cancelled'

  const statusIcon = isRunning ? (
    <Loader2 size={13} className="text-amber-500 animate-spin shrink-0" />
  ) : isDone ? (
    <CheckCircle2 size={13} className="text-green-500 shrink-0" />
  ) : isError ? (
    <AlertCircle size={13} className="text-red-500 shrink-0" />
  ) : isCancelled ? (
    <X size={13} className="text-gray-500 shrink-0" />
  ) : (
    <span className="w-3 h-3 rounded-full bg-gray-300 shrink-0" />
  )

  return (
    <div className={clsx(
      'rounded-xl border px-3 py-2.5 text-xs transition-colors',
      isDone ? 'bg-green-50 border-green-200' :
      isError ? 'bg-red-50 border-red-200' :
      isCancelled ? 'bg-gray-50 border-gray-200' :
      isRunning ? 'bg-amber-50 border-amber-200' :
      'bg-gray-50 border-gray-200'
    )}>
      {/* 任务标题行 */}
      <div className="flex items-center gap-1.5 mb-1.5">
        {statusIcon}
        <span className={clsx(
          'flex-1 font-medium truncate',
          isDone ? 'text-green-800' :
          isError ? 'text-red-700' :
          isCancelled ? 'text-gray-500' :
          isRunning ? 'text-amber-800' :
          'text-gray-600'
        )}>
          {task.label}
        </span>
        {(isRunning || isPending) && (
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-red-500 p-0.5 rounded"
            title="取消任务"
          >
            <X size={11} />
          </button>
        )}
        {(isDone || isError || isCancelled) && (
          <button
            onClick={onRemove}
            className="text-gray-400 hover:text-gray-600 p-0.5 rounded"
            title="移除"
          >
            <X size={11} />
          </button>
        )}
      </div>

      {/* 进度条目（含大纲质检可展开详情） */}
      {task.progress.length > 0 && (
        <div className={clsx(
          'space-y-1 overflow-y-auto pr-0.5',
          task.progress.some(x => x.outlineQualityReport) ? 'max-h-56' : 'max-h-32',
        )}>
          {task.progress.map((p, idx) => {
            const pk = progressRowKey(p, idx)
            const expandable = !!p.outlineQualityReport || !!(p.warning && p.warningDetails?.length)
            const open = expandedPk === pk
            return (
              <div key={pk} className={clsx(
                'rounded px-2 py-1',
                p.error   ? 'bg-red-100 text-red-700' :
                p.warning ? 'bg-yellow-50 text-yellow-800' :
                p.done    ? 'bg-green-100 text-green-700' :
                'bg-white text-gray-600'
              )}>
                <div
                  className={clsx('flex items-start gap-1.5', expandable && 'cursor-pointer select-none')}
                  onClick={() => expandable && setExpandedPk(open ? null : pk)}
                >
                  {p.error ? (
                    <AlertCircle size={10} className="shrink-0 mt-0.5" />
                  ) : p.warning ? (
                    <AlertTriangle size={10} className="shrink-0 mt-0.5 text-yellow-600" />
                  ) : p.done ? (
                    <CheckCircle2 size={10} className="shrink-0 mt-0.5" />
                  ) : (
                    <Loader2 size={10} className="shrink-0 mt-0.5 animate-spin" />
                  )}
                  <span className="text-[11px] leading-relaxed flex-1">
                    {p.label}
                    {expandable && (
                      <span className="text-[10px] text-gray-500 ml-1">
                        {open ? '（收起）' : '（展开）'}
                      </span>
                    )}
                  </span>
                </div>
                {open && p.outlineQualityReport && (
                  <div className="mt-1.5 pl-4 border-l border-green-200">
                    <OutlinePlanQualityView report={p.outlineQualityReport} variant="minimal" />
                  </div>
                )}
                {open && p.warning && p.warningDetails && p.warningDetails.length > 0 && (
                  <div className="mt-1.5 pl-4 border-l border-yellow-300 space-y-0.5">
                    {p.warningDetails.map((d, i) => (
                      <p key={i} className="text-[10px] text-yellow-700">{d}</p>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 完成/错误消息 */}
      {task.completedMsg && (
        <p className="text-[11px] text-green-700 mt-1.5 font-medium">{task.completedMsg}</p>
      )}
      {task.errorMsg && (
        <p className="text-[11px] text-red-700 mt-1.5">{task.errorMsg}</p>
      )}
      {isError && isTaskInterruptedByReload(task) && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 w-full rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-[11px] font-medium text-amber-900 hover:bg-amber-100"
        >
          重新排队（从中断处重跑整任务）
        </button>
      )}
      {isCancelled && (
        <p className="text-[11px] text-gray-500 mt-1.5">已取消</p>
      )}
    </div>
  )
}
