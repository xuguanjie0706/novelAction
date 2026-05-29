/**
 * @file 直观模式（编剧台）编排壳：左稿纸 + 右诊脉，双向联动滚动
 */
import { useMemo, useState, useCallback, useEffect } from 'react'
import type { OutlineNode } from '../../../types'
import VolExpandProgressPanel from '../../../components/Outline/VolExpandProgressPanel'
import type { VolExpandState } from '../../../components/Outline/VolExpandProgressPanel'
import type { ProgressLine, ExpandEndResult } from '../../../components/Outline/VolumeExpandButton'
import { buildIntuitiveBundle } from './buildIntuitiveBundle'
import IntuitiveManuscriptColumn from './IntuitiveManuscriptColumn'
import IntuitiveInsightRail from './IntuitiveInsightRail'
import type { InsightTimelineEntry } from './intuitiveTypes'

interface Props {
  volume: OutlineNode
  projectId: string
  aiBackendRoute: string
  onReload: () => void
  volExpandState: VolExpandState | null
  onDismissExpand: () => void
  onViewLinter: () => void
  onForceAcceptDraft?: () => void
  onOpenWrite: (chapterNumber: number) => void
  onQualityCheck: () => void
  onRelintDone?: () => void
  onRequestRepair?: (mustFixChapters: number[]) => void
  onVolExpandStart?: (v: OutlineNode) => void
  onVolExpandProgress?: (lines: ProgressLine[]) => void
  onVolExpandEnd?: (v: OutlineNode, r: ExpandEndResult) => void
}

export default function IntuitiveModeShell({
  volume,
  projectId,
  aiBackendRoute,
  onReload,
  volExpandState,
  onDismissExpand,
  onViewLinter,
  onForceAcceptDraft,
  onOpenWrite,
  onQualityCheck,
  onRelintDone,
  onRequestRepair,
  onVolExpandStart,
  onVolExpandProgress,
  onVolExpandEnd,
}: Props) {
  const bundle = useMemo(() => buildIntuitiveBundle(volume), [volume])
  const [activeChapter, setActiveChapter] = useState<number | null>(
    bundle.chapters.length > 0 ? 1 : null,
  )
  const [activeInsightId, setActiveInsightId] = useState<string | null>(null)
  const [scrollToChapter, setScrollToChapter] = useState<number | null>(null)
  const [scrollToInsightId, setScrollToInsightId] = useState<string | null>(null)

  useEffect(() => {
    setActiveChapter(bundle.chapters.length > 0 ? 1 : null)
    setActiveInsightId(null)
    setScrollToChapter(null)
    setScrollToInsightId(null)
  }, [volume.id, bundle.chapters.length])

  const handleChapterSelect = useCallback((n: number) => {
    setActiveChapter(n)
    setScrollToChapter(n)
    const first = bundle.timeline.find(e => e.chapterNumber === n)
    if (first) {
      setActiveInsightId(first.id)
      setScrollToInsightId(first.id)
    }
  }, [bundle.timeline])

  const handleInsightSelect = useCallback((entry: InsightTimelineEntry) => {
    setActiveInsightId(entry.id)
    setScrollToInsightId(entry.id)
    if (entry.chapterNumber != null) {
      setActiveChapter(entry.chapterNumber)
      setScrollToChapter(entry.chapterNumber)
    }
  }, [])

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      {volExpandState && volExpandState.volumeTitle && (
        <VolExpandProgressPanel
          state={volExpandState}
          onDismiss={onDismissExpand}
          onViewLinter={onViewLinter}
          onForceAccept={onForceAcceptDraft}
        />
      )}
      <div className="flex flex-1 min-h-0">
        <IntuitiveManuscriptColumn
          bundle={bundle}
          projectId={projectId}
          aiBackendRoute={aiBackendRoute}
          onReload={onReload}
          activeChapter={activeChapter}
          onChapterSelect={handleChapterSelect}
          onOpenWrite={onOpenWrite}
          scrollToChapter={scrollToChapter}
          onVolExpandStart={onVolExpandStart}
          onVolExpandProgress={onVolExpandProgress}
          onVolExpandEnd={onVolExpandEnd}
        />
        <IntuitiveInsightRail
          bundle={bundle}
          projectId={projectId}
          activeChapter={activeChapter}
          activeInsightId={activeInsightId}
          scrollToInsightId={scrollToInsightId}
          onChapterSelect={handleChapterSelect}
          onInsightSelect={handleInsightSelect}
          onQualityCheck={onQualityCheck}
          onRelintDone={onRelintDone}
          onRequestRepair={onRequestRepair}
          onForceAccept={onForceAcceptDraft}
        />
      </div>
    </div>
  )
}
