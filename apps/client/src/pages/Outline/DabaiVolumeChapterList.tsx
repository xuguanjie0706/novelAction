/**
 * @file 大白文卷 · 章节清单（四段式爽点节拍，替代通用章纲列表）
 */
import { useState } from 'react'
import DabaiChapterBeatCard from '../../components/Dabai/DabaiChapterBeatCard'
import {
  ChapterLinterBadgeTrigger,
  ChapterLinterIssuePanel,
} from '../../components/Outline/ChapterLinterBadge'
import type { LinterIssueRow } from '../../components/Outline/VolumeLinterPanel'
import type { OutlineNode } from '../../types'
import { dabaiBeatFromOutlineNode } from '../../utils/dabaiOutlineDisplay'

interface Props {
  chapters: OutlineNode[]
  linterIssuesByChapter: Map<number, LinterIssueRow[]>
  realmLevels?: Array<{ rank?: number; name?: string }>
  onJumpToChapterPlan: (chapterNumber: number) => void
}

export default function DabaiVolumeChapterList({
  chapters,
  linterIssuesByChapter,
  realmLevels,
  onJumpToChapterPlan,
}: Props) {
  const [expandedLintChapter, setExpandedLintChapter] = useState<number | null>(null)

  return (
    <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-0.5">
      {chapters.map((ch, idx) => {
        const chNum = idx + 1
        const beat = dabaiBeatFromOutlineNode(ch, chNum, { realmLevels })
        if (!beat) return null
        const chapterLintIssues = linterIssuesByChapter.get(chNum) ?? []
        const lintExpanded = expandedLintChapter === chNum
        return (
          <div key={ch.id} className="space-y-1">
            <DabaiChapterBeatCard
              beat={beat}
              onClick={() => onJumpToChapterPlan(chNum)}
              trailing={chapterLintIssues.length > 0 ? (
                <ChapterLinterBadgeTrigger
                  issues={chapterLintIssues}
                  expanded={lintExpanded}
                  onToggle={() => setExpandedLintChapter(lintExpanded ? null : chNum)}
                />
              ) : undefined}
            />
            {lintExpanded && chapterLintIssues.length > 0 && (
              <ChapterLinterIssuePanel issues={chapterLintIssues} />
            )}
          </div>
        )
      })}
    </div>
  )
}
