/**
 * @file BootstrapStepGatePanel — 非 Step0 的根设定确认面板（境界 / 人物 / 卷骨架）
 *
 * 数据来源：SSE ``gate_pending`` 的 ``step`` / ``message`` / ``gate_preview``。
 */
import React from 'react'
import { CheckCircle, Loader, RefreshCw } from 'lucide-react'

export type RootGateStep = 'power_systems' | 'characters' | 'volumes'

const TITLES: Record<RootGateStep, string> = {
  power_systems: '境界体系已生成',
  characters: '人物库已生成',
  volumes: '卷级骨架已生成',
}

interface Props {
  step: RootGateStep
  message: string
  preview: Record<string, unknown> | null
  loading?: boolean
  onApprove: () => void
  onRegenerate: () => void
}

export default function BootstrapStepGatePanel({
  step, message, preview, loading, onApprove, onRegenerate,
}: Props) {
  const title = TITLES[step]
  const count =
    preview?.power_systems_count ?? preview?.characters_count ?? preview?.volumes_count

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="px-6 pt-5 pb-3 shrink-0 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-1">
          <CheckCircle size={16} className="text-green-500" />
          <span className="font-semibold text-gray-800 text-sm">{title}，请确认后继续</span>
        </div>
        <p className="text-xs text-gray-500 leading-relaxed">{message}</p>
        {count != null && (
          <p className="text-xs text-gray-400 mt-2">当前条目数：<span className="font-mono text-gray-600">{String(count)}</span></p>
        )}
      </div>
      <div className="flex-1 min-h-[80px]" />
      <div className="px-6 pb-6 pt-3 shrink-0 space-y-2">
        <button
          type="button"
          onClick={onApprove}
          disabled={loading}
          className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? <Loader size={15} className="animate-spin" /> : <CheckCircle size={15} />}
          确认继续生成
        </button>
        <button
          type="button"
          onClick={onRegenerate}
          disabled={loading}
          className="w-full py-2.5 border border-gray-200 rounded-xl text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          <RefreshCw size={15} />
          重新生成本步
        </button>
      </div>
    </div>
  )
}
