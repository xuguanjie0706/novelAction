/**
 * @file 章纲问题密度热力条（诊脉轨顶栏）
 */
import clsx from 'clsx'
import type { IntuitiveChapterRow } from './intuitiveTypes'

interface Props {
  chapters: IntuitiveChapterRow[]
  activeChapter: number | null
  onChapterClick: (n: number) => void
}

export default function ChapterHeatmap({ chapters, activeChapter, onChapterClick }: Props) {
  if (chapters.length === 0) return null

  return (
    <div className="px-4 py-3 border-b border-slate-800/80">
      <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 font-medium">
        章纲健康度 · 一眼扫卷
      </p>
      <div className="flex gap-0.5 items-end h-8">
        {chapters.map(row => {
          const n = row.issueCount
          const h = n === 0 ? 20 : Math.min(32, 12 + n * 6)
          const color =
            row.hasCritical ? 'bg-red-500' :
            n > 0 ? 'bg-amber-500' :
            'bg-emerald-600/50'
          return (
            <button
              key={row.chapterNumber}
              type="button"
              title={`第${row.chapterNumber}章 · ${n} 项问题`}
              onClick={() => onChapterClick(row.chapterNumber)}
              className={clsx(
                'flex-1 min-w-[3px] max-w-[12px] rounded-sm transition-all hover:opacity-100',
                color,
                activeChapter === row.chapterNumber && 'ring-1 ring-white ring-offset-1 ring-offset-slate-900',
              )}
              style={{ height: h }}
            />
          )
        })}
      </div>
      <div className="flex justify-between mt-1.5 text-[9px] text-slate-600 font-mono tabular-nums">
        <span>01</span>
        <span>{String(chapters.length).padStart(2, '0')}</span>
      </div>
    </div>
  )
}
