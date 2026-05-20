/**
 * 顶部轻条：与书架/小说详情互补——**不自动打开向导**；用户点「继续」后由父级挂载 ``GenerateWizard`` 并传入 ``recoverRunId``。
 * 新建一键生成请走各页「AI 生成」入口（无未结束 run 时）。
 */
import React from 'react'
import { ChevronRight, Loader2, OctagonX, Sparkles } from 'lucide-react'
import type { BootstrapResumeSnapshot } from '../../hooks/useBootstrapResumeBanner'

interface Props {
  snapshot: BootstrapResumeSnapshot | null
  hidden: boolean
  onContinue: () => void
  onHide: () => void
  /** 调用后端 ``POST /bootstrap/runs/:id/cancel``，终止进行中的串行生成 */
  onCancelRun?: () => void | Promise<void>
  /** 终止请求进行中 */
  cancelLoading?: boolean
}

export default function ActiveBootstrapResumeBar({
  snapshot,
  hidden,
  onContinue,
  onHide,
  onCancelRun,
  cancelLoading,
}: Props) {
  if (hidden || !snapshot) return null
  const sub =
    snapshot.status === 'awaiting_gate'
      ? '等待你确认根设定'
      : snapshot.status === 'awaiting_retry'
        ? '某步骤失败，等待重试'
        : '生成正在进行中'

  return (
    <div
      className="mb-5 flex flex-col gap-3 rounded-2xl border border-amber-100 bg-amber-50/90 px-4 py-3.5 shadow-[0_12px_32px_rgba(245,158,11,0.1)] sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-amber-500 shadow-sm ring-1 ring-amber-100">
          <Sparkles size={18} strokeWidth={2.2} />
        </div>
        <div className="min-w-0 pt-0.5">
          <p className="text-sm font-semibold text-gray-950">{sub}</p>
          <p className="mt-0.5 truncate text-xs leading-relaxed text-gray-600">
            {snapshot.logline || '（无创意摘要）'}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 sm:pl-4">
        <button
          type="button"
          onClick={onHide}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-600 shadow-sm transition-colors hover:border-amber-200 hover:bg-amber-50/50 hover:text-gray-900"
        >
          本页不再提示
        </button>
        {onCancelRun && (
          <button
            type="button"
            onClick={() => void onCancelRun()}
            disabled={cancelLoading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 shadow-sm transition-colors hover:bg-red-50 disabled:opacity-50"
          >
            {cancelLoading ? <Loader2 size={14} className="animate-spin" /> : <OctagonX size={14} />}
            终止生成
          </button>
        )}
        <button
          type="button"
          onClick={onContinue}
          className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-colors hover:bg-amber-600"
        >
          继续
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}
