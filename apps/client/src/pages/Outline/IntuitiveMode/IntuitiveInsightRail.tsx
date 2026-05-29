/**
 * @file 直观模式 · 右侧连续诊脉轨（问题 / 分析 / 修复入口）
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, Check, ShieldOff, Wrench } from 'lucide-react'
import clsx from 'clsx'
import VolumeLinterPanel from '../../../components/Outline/VolumeLinterPanel'
import ChapterHeatmap from './ChapterHeatmap'
import InsightTimelineEntryCard from './InsightTimelineEntry'
import type { InsightTimelineEntry, IntuitiveVolumeBundle } from './intuitiveTypes'

interface Props {
  bundle: IntuitiveVolumeBundle
  projectId: string
  activeChapter: number | null
  activeInsightId: string | null
  scrollToInsightId: string | null
  onChapterSelect: (n: number) => void
  onInsightSelect: (entry: InsightTimelineEntry) => void
  onQualityCheck: () => void
  onRelintDone?: () => void
  onRequestRepair?: (mustFixChapters: number[]) => void
  onForceAccept?: () => void
}

export default function IntuitiveInsightRail({
  bundle,
  projectId,
  activeChapter,
  activeInsightId,
  scrollToInsightId,
  onChapterSelect,
  onInsightSelect,
  onQualityCheck,
  onRelintDone,
  onRequestRepair,
  onForceAccept,
}: Props) {
  const { volume, chapters, timeline, stats } = bundle
  const [showFixBench, setShowFixBench] = useState(false)
  const entryRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  const filteredTimeline = useMemo(() => {
    if (activeChapter == null) return timeline
    return timeline.filter(
      e => e.chapterNumber === activeChapter || e.chapterNumber === null,
    )
  }, [timeline, activeChapter])

  useEffect(() => {
    if (!scrollToInsightId) return
    entryRefs.current.get(scrollToInsightId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [scrollToInsightId])

  const statusTone =
    stats.linterStatus === 'ok' ? 'text-emerald-400' :
    stats.linterStatus === 'warn' ? 'text-amber-400' : 'text-red-400'

  return (
    <aside className="w-[min(420px,38vw)] shrink-0 flex flex-col min-h-0 bg-[#0c1017] text-slate-200 border-l border-slate-800">
      <header className="shrink-0 px-4 pt-4 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2 mb-2">
          <Activity size={14} className="text-cyan-400" />
          <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500 font-medium">
            诊脉轨
          </span>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          <span className={clsx('font-semibold', statusTone)}>
            Linter · {stats.linterStatus === 'ok' ? '通过' : stats.linterStatus}
          </span>
          {stats.issueCount > 0 && (
            <span className="text-slate-400">
              {stats.issueCount} 项
              {stats.criticalCount > 0 && (
                <span className="text-red-400 ml-1">严重 {stats.criticalCount}</span>
              )}
            </span>
          )}
          {stats.qualityScore != null && (
            <span className="text-indigo-300">AI {stats.qualityScore} 分</span>
          )}
          {stats.draftBlocked && (
            <span className="text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded">
              草稿待确认
            </span>
          )}
        </div>
      </header>

      <ChapterHeatmap
        chapters={chapters}
        activeChapter={activeChapter}
        onChapterClick={onChapterSelect}
      />

      <div className="flex-1 overflow-y-auto px-2 py-2 min-h-0">
        {filteredTimeline.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-sm text-slate-500">暂无诊断记录</p>
            <p className="text-[11px] text-slate-600 mt-2">展开章纲后将自动运行规则检测</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {filteredTimeline.map(entry => (
              <InsightTimelineEntryCard
                key={entry.id}
                ref={el => {
                  if (el) entryRefs.current.set(entry.id, el)
                  else entryRefs.current.delete(entry.id)
                }}
                entry={entry}
                active={activeInsightId === entry.id}
                onSelect={() => onInsightSelect(entry)}
              />
            ))}
          </div>
        )}
      </div>

      <footer className="shrink-0 border-t border-slate-800 bg-slate-900/80 p-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={onQualityCheck}
            className="flex-1 min-w-[100px] flex items-center justify-center gap-1 text-[11px] px-2 py-2 rounded-lg bg-indigo-600/90 hover:bg-indigo-500 text-white font-medium"
          >
            <Check size={12} />
            AI 深度质检
          </button>
          <button
            type="button"
            onClick={() => setShowFixBench(v => !v)}
            className="flex items-center gap-1 text-[11px] px-2.5 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800"
          >
            <Wrench size={12} />
            {showFixBench ? '收起' : '修复台'}
          </button>
        </div>

        {showFixBench && (
          <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-700 bg-slate-950/50 p-2">
            <VolumeLinterPanel
              volumeNode={volume}
              projectId={projectId}
              onRelintDone={onRelintDone}
              onRequestRepair={onRequestRepair}
              onForceAccept={onForceAccept}
            />
          </div>
        )}

        {stats.draftBlocked && onForceAccept && (
          <button
            type="button"
            onClick={onForceAccept}
            className="w-full flex items-center justify-center gap-1 text-[10px] py-1.5 text-amber-400 hover:text-amber-300"
          >
            <ShieldOff size={11} />
            强制采用草稿
          </button>
        )}
      </footer>
    </aside>
  )
}
