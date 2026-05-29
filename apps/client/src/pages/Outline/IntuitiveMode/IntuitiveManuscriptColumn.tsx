/**
 * @file 直观模式 · 左侧连续章纲稿纸列
 */
import { useEffect, useRef } from 'react'
import { BookOpen, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { parseVolumeDirector, PHASE_LABEL } from '../../../utils/volumeBeatsDisplay'
import VolumeExpandButton from '../../../components/Outline/VolumeExpandButton'
import type { ProgressLine, ExpandEndResult } from '../../../components/Outline/VolumeExpandButton'
import type { OutlineNode } from '../../../types'
import ChapterManuscriptCard from './ChapterManuscriptCard'
import type { IntuitiveVolumeBundle } from './intuitiveTypes'

interface Props {
  bundle: IntuitiveVolumeBundle
  projectId: string
  aiBackendRoute: string
  activeChapter: number | null
  onChapterSelect: (n: number) => void
  onOpenWrite: (chapterNumber: number) => void
  onReload: () => void
  scrollToChapter: number | null
  onVolExpandStart?: (v: OutlineNode) => void
  onVolExpandProgress?: (lines: ProgressLine[]) => void
  onVolExpandEnd?: (v: OutlineNode, r: ExpandEndResult) => void
}

export default function IntuitiveManuscriptColumn({
  bundle,
  projectId,
  activeChapter,
  onChapterSelect,
  onOpenWrite,
  scrollToChapter,
  aiBackendRoute,
  onReload,
  onVolExpandStart,
  onVolExpandProgress,
  onVolExpandEnd,
}: Props) {
  const { volume, chapters } = bundle
  const director = parseVolumeDirector(volume)
  const cardRefs = useRef<Map<number, HTMLElement>>(new Map())

  useEffect(() => {
    if (scrollToChapter == null) return
    const el = cardRefs.current.get(scrollToChapter)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [scrollToChapter])

  return (
    <div className="flex flex-col min-h-0 flex-1 bg-gradient-to-b from-[#ebe6dc] via-[#f5f1ea] to-[#faf8f4]">
      <header className="shrink-0 px-6 pt-5 pb-4 border-b border-stone-300/40 bg-[#f5f1ea]/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <BookOpen size={14} className="text-amber-800/70 shrink-0" />
              <span className="text-[10px] uppercase tracking-[0.2em] text-stone-500 font-medium">
                编剧台 · 章纲稿
              </span>
              {volume.phase && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-200/80">
                  {PHASE_LABEL[volume.phase] ?? volume.phase}
                </span>
              )}
            </div>
            <h2 className="text-xl font-semibold text-stone-900 tracking-tight truncate">
              {volume.title}
            </h2>
            {volume.summary && (
              <p className="text-xs text-stone-600 mt-1.5 leading-relaxed line-clamp-2 max-w-2xl">
                {volume.summary}
              </p>
            )}
          </div>
          <VolumeExpandButton
            volumeNode={volume}
            projectId={projectId}
            aiBackendRoute={aiBackendRoute}
            onExpanded={onReload}
            onExpandStart={onVolExpandStart}
            onExpandProgress={onVolExpandProgress}
            onExpandEnd={onVolExpandEnd}
          />
        </div>

        {(director.beatHighlights.length > 0 || director.climaxSummary) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {director.beatHighlights.slice(0, 4).map((b, i) => (
              <span
                key={i}
                className="text-[10px] px-2 py-1 rounded-lg bg-white/70 border border-amber-200/50 text-amber-900/90"
              >
                <Sparkles size={9} className="inline mr-1 -mt-px text-amber-500" />
                {b.description || '燃点'}
              </span>
            ))}
            {director.climaxSummary && (
              <span className="text-[10px] px-2 py-1 rounded-lg bg-red-50/80 border border-red-100 text-red-800">
                卷末 · {director.climaxSummary.slice(0, 36)}
                {director.climaxSummary.length > 36 ? '…' : ''}
              </span>
            )}
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {chapters.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-sm text-stone-500 mb-2">本卷尚无章节计划</p>
            <p className="text-xs text-stone-400">点击右上角「展开章纲」一次性铺完全卷蓝图</p>
          </div>
        ) : (
          <div className={clsx('mx-auto space-y-4', 'max-w-3xl')}>
            {chapters.map(row => (
              <ChapterManuscriptCard
                key={row.node.id}
                ref={el => {
                  if (el) cardRefs.current.set(row.chapterNumber, el)
                  else cardRefs.current.delete(row.chapterNumber)
                }}
                row={row}
                active={activeChapter === row.chapterNumber}
                onSelect={() => onChapterSelect(row.chapterNumber)}
                onOpenWrite={() => onOpenWrite(row.chapterNumber)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
