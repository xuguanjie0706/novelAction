/**
 * @file 批量展开章节计划配置弹窗
 */
import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'

export default function BatchExpandConfigModal({
  targetCount,
  onClose,
  onDispatch,
}: {
  targetCount: number
  onClose: () => void
  onDispatch: (chapterCount: number) => void
}) {
  const [chapterCount, setChapterCount] = useState(60)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Sparkles size={16} className="text-amber-500" />
          <h3 className="font-semibold text-gray-800 flex-1">批量展开章节计划</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-gray-500 leading-relaxed">
            将对 <span className="font-semibold text-gray-700">{targetCount} 个</span>尚未有章节计划的卷依次展开。
          </p>
          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-500 whitespace-nowrap">每处生成</label>
            <input
              type="number"
              min={1}
              max={200}
              value={chapterCount}
              onChange={e => {
                const v = parseInt(e.target.value, 10)
                if (!isNaN(v) && v >= 1) setChapterCount(v)
              }}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 w-24 focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
            <span className="text-xs text-gray-400">章</span>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-500 border border-gray-200 rounded-lg bg-white">
            取消
          </button>
          <button
            type="button"
            onClick={() => { onDispatch(chapterCount); onClose() }}
            className="flex items-center gap-2 px-4 py-1.5 text-sm font-medium bg-amber-500 text-white rounded-lg"
          >
            <Sparkles size={14} />
            加入队列
          </button>
        </div>
      </div>
    </div>
  )
}
