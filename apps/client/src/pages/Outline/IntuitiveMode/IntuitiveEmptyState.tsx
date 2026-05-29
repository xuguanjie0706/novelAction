/**
 * @file 直观模式未选卷时的卷选择引导
 */
import { Layers } from 'lucide-react'
import clsx from 'clsx'
import type { OutlineNode } from '../../../types'

interface Props {
  volumes: OutlineNode[]
  onSelectVolume: (v: OutlineNode) => void
}

export default function IntuitiveEmptyState({ volumes, onSelectVolume }: Props) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-gradient-to-br from-[#ebe6dc] to-[#0c1017] p-8">
      <div className="max-w-lg w-full rounded-2xl border border-stone-300/30 bg-[#fffcf7]/95 shadow-xl p-8 text-center">
        <Layers className="mx-auto text-amber-700/80 mb-4" size={32} />
        <h2 className="text-lg font-semibold text-stone-900 mb-2">编剧台 · 直观模式</h2>
        <p className="text-sm text-stone-600 mb-6 leading-relaxed">
          左侧连续阅读全卷章纲，右侧诊脉轨同步展示规则检测与 AI 分析。
          请先选择一卷进入工作台。
        </p>
        {volumes.length === 0 ? (
          <p className="text-xs text-stone-400">暂无卷节点，请先在左侧树中创建或通过 Bootstrap 生成。</p>
        ) : (
          <div className="flex flex-col gap-2 text-left">
            {volumes.map((v, i) => {
              const chCount = (v.children ?? []).filter(c => c.node_type === 'chapter_plan').length
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => onSelectVolume(v)}
                  className={clsx(
                    'w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl',
                    'border border-stone-200 bg-white hover:border-amber-300 hover:bg-amber-50/50 transition-colors',
                  )}
                >
                  <span className="text-sm font-medium text-stone-800 truncate">
                    {v.title || `第 ${i + 1} 卷`}
                  </span>
                  <span className="text-[10px] text-stone-400 shrink-0 tabular-nums">
                    {chCount > 0 ? `${chCount} 章` : '未展开'}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
