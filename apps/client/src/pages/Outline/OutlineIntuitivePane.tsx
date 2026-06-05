/**
 * @file 大纲页 · 编剧台（直观模式）主区域
 */
import toast from 'react-hot-toast'
import type { OutlineNode } from '../../types'
import type { VolExpandState } from '../../components/Outline/VolExpandProgressPanel'
import type { ProgressLine, ExpandEndResult } from '../../components/Outline/VolumeExpandButton'
import IntuitiveModeShell from './IntuitiveMode/IntuitiveModeShell'
import IntuitiveEmptyState from './IntuitiveMode/IntuitiveEmptyState'

interface Props {
  projectId: string | undefined
  intuitiveVolume: OutlineNode | null
  volumeNodes: OutlineNode[]
  aiBackendRoute: string
  projectExtra?: Record<string, unknown>
  volExpandState: VolExpandState | null
  onReload: () => void
  onSelectVolume: (v: OutlineNode) => void
  onDismissExpand: () => void
  onViewLinter: () => void
  forceAccept: (node: OutlineNode, reload: () => void) => Promise<void>
  onOpenWrite: (chapterNumber: number) => void
  onQualityCheck: (volume: OutlineNode) => void
  onRequestRepair: (volume: OutlineNode, chapters: number[]) => void
  sidebarCallbacks: {
    onVolExpandStart?: (v: OutlineNode) => void
    onVolExpandProgress?: (lines: ProgressLine[]) => void
    onVolExpandEnd?: (v: OutlineNode, r: ExpandEndResult) => void
  }
}

export default function OutlineIntuitivePane({
  projectId,
  intuitiveVolume,
  volumeNodes,
  aiBackendRoute,
  projectExtra,
  volExpandState,
  onReload,
  onSelectVolume,
  onDismissExpand,
  onViewLinter,
  forceAccept,
  onOpenWrite,
  onQualityCheck,
  onRequestRepair,
  sidebarCallbacks,
}: Props) {
  if (!intuitiveVolume || !projectId) {
    return (
      <IntuitiveEmptyState
        volumes={volumeNodes}
        onSelectVolume={onSelectVolume}
      />
    )
  }

  return (
    <IntuitiveModeShell
      volume={intuitiveVolume}
      allVolumes={volumeNodes}
      projectId={projectId}
      projectExtra={projectExtra}
      aiBackendRoute={aiBackendRoute}
      onReload={onReload}
      volExpandState={volExpandState}
      onDismissExpand={onDismissExpand}
      onViewLinter={onViewLinter}
      onForceAcceptDraft={
        Boolean(intuitiveVolume.extra?.linter_blocked)
          ? () => forceAccept(intuitiveVolume, onReload).catch(() => toast.error('强制采用失败'))
          : undefined
      }
      onOpenWrite={onOpenWrite}
      onQualityCheck={() => onQualityCheck(intuitiveVolume)}
      onRelintDone={onReload}
      onRequestRepair={chapters => onRequestRepair(intuitiveVolume, chapters)}
      {...sidebarCallbacks}
    />
  )
}
