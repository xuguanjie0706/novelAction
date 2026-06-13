/**
 * @file VolumeExpandButton — 卷头「展开/补全/重做章纲」入口。
 * 未满卷显示补全；已有章纲时可强制重做（删旧按节拍表重生成）。
 */
import clsx from 'clsx'
import { Loader2, RotateCcw, Wand2 } from 'lucide-react'
import type { DabaiVolume } from '../../../../types/dabai'
import type { VolumeExpandState } from './useVolumeExpand'

interface Props {
  volume: DabaiVolume
  /** 卷内已有章数（增量补全时按钮提示用）。 */
  existingCount: number
  state: VolumeExpandState
}

export default function VolumeExpandButton({ volume, existingCount, state }: Props) {
  const running = state.expandingId === volume.id
  const busyOther = state.expandingId !== null && !running
  const planned = volume.planned_chapters
  const incomplete = existingCount < planned
  const expandTimes = Math.max(1, Math.ceil(planned / 15))
  const doneTimes = Math.ceil(existingCount / 15) || 0
  const label = existingCount > 0 ? '补全章纲' : '展开章纲'

  const btnClass = (variant: 'primary' | 'ghost') => clsx(
    'flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium transition-colors',
    running && variant === 'primary'
      ? 'bg-amber-100 text-amber-700'
      : busyOther
        ? 'cursor-not-allowed text-gray-300'
        : variant === 'primary'
          ? 'text-amber-600 hover:bg-amber-50 hover:text-amber-700'
          : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600',
  )

  return (
    <div className="flex shrink-0 items-center gap-0.5">
      {incomplete && (
        <button
          type="button"
          disabled={busyOther || running}
          title={running ? `生成中…${state.progress}` : `${label}（${existingCount}/${planned}，${expandTimes}次×15章，已完成${doneTimes}次）`}
          onClick={e => {
            e.stopPropagation()
            state.expand(volume, false)
          }}
          className={btnClass('primary')}
        >
          {running ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
          {running ? (state.progress || '生成中') : label}
        </button>
      )}
      {existingCount > 0 && (
        <button
          type="button"
          disabled={busyOther || running}
          title="删旧章纲，按节拍表整卷重生成（章数不对或质量差时用）"
          onClick={e => {
            e.stopPropagation()
            if (window.confirm(`确定重做第 ${volume.volume_number} 卷章纲？将删除现有 ${existingCount} 章章纲。`)) {
              state.expand(volume, true)
            }
          }}
          className={btnClass('ghost')}
        >
          <RotateCcw size={11} />
          重做
        </button>
      )}
    </div>
  )
}
