/**
 * @file VolumeExpandButton — 卷头「展开章纲」入口。
 * 仅当卷章纲未满（已有章数 < planned_chapters）时由父级渲染；
 * 运行中显示 spinner + 已落库章数，其他卷的按钮同时禁用（后端单卷串行）。
 */
import clsx from 'clsx'
import { Loader2, Wand2 } from 'lucide-react'
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
  const label = existingCount > 0 ? '补全章纲' : '展开章纲'
  return (
    <button
      type="button"
      disabled={busyOther || running}
      title={running ? `生成中…${state.progress}` : `${label}（${existingCount}/${volume.planned_chapters}）`}
      onClick={e => {
        e.stopPropagation()
        state.expand(volume)
      }}
      className={clsx(
        'flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium transition-colors',
        running
          ? 'bg-amber-100 text-amber-700'
          : busyOther
            ? 'cursor-not-allowed text-gray-300'
            : 'text-amber-600 hover:bg-amber-50 hover:text-amber-700',
      )}
    >
      {running ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
      {running ? (state.progress || '生成中') : label}
    </button>
  )
}
