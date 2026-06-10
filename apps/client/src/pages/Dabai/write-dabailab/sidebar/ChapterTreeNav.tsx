import type { MutableRefObject, ReactNode } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import type { DabaiChapter } from '../../../../types/dabai'
import { chapterTitleText } from '../../../../utils/dabaiOutlineDisplay'
import type { VolumeGroup } from '../groupByVolume'
import { hasContent } from '../useWriteDabailab'

interface Props {
  groups: VolumeGroup[]
  activeId: string | null
  activeVolumeKey: string | null
  collapsed: Set<string>
  visibleChapters: (g: VolumeGroup) => DabaiChapter[]
  volumeKey: (g: VolumeGroup) => string
  activeRowRef: MutableRefObject<HTMLButtonElement | null>
  onToggleVolume: (key: string) => void
  onSelect: (ch: DabaiChapter) => void
  /** 卷头右侧动作（如「展开章纲」入口）；返回 null/undefined 则不渲染。 */
  volumeAction?: (g: VolumeGroup) => ReactNode
}

export default function ChapterTreeNav({
  groups,
  activeId,
  activeVolumeKey,
  collapsed,
  visibleChapters,
  volumeKey,
  activeRowRef,
  onToggleVolume,
  onSelect,
  volumeAction,
}: Props) {
  return (
    <>
      {groups.map(group => {
        const key = volumeKey(group)
        const open = !collapsed.has(key)
        const writtenCount = group.chapters.filter(hasContent).length
        const chapters = visibleChapters(group)
        return (
          <div key={key} className="mb-0.5">
            <div className={clsx(
              'flex w-full items-center rounded-lg transition-colors hover:bg-gray-50',
              key === activeVolumeKey && 'bg-gray-50',
            )}>
              <button
                type="button"
                onClick={() => onToggleVolume(key)}
                className="flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left"
              >
                {open ? <ChevronDown size={11} className="shrink-0 text-gray-400" /> : <ChevronRight size={11} className="shrink-0 text-gray-400" />}
                <span className="shrink-0 rounded bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-700">卷</span>
                <span className="min-w-0 flex-1 truncate text-xs font-medium text-gray-700">{group.volume.title}</span>
                <span className="shrink-0 text-[10px] tabular-nums text-gray-400">{writtenCount}/{group.chapters.length}</span>
              </button>
              {volumeAction?.(group)}
            </div>
            {open && (
              <div className="mt-0.5 space-y-0.5 pl-2">
                {chapters.length === 0 ? (
                  <p className="px-2 py-2 text-[11px] text-gray-300">无匹配章节</p>
                ) : (
                  chapters.map(ch => {
                    const active = ch.id === activeId
                    const title = chapterTitleText(ch.title, ch.chapter_number)
                    return (
                      <button
                        key={ch.id ?? ch.chapter_number}
                        ref={active ? activeRowRef : undefined}
                        type="button"
                        onClick={() => onSelect(ch)}
                        className={clsx(
                          'mb-0.5 flex w-full items-center gap-2 rounded-lg border py-1.5 pl-2 pr-2 text-left transition-colors',
                          active
                            ? 'border-amber-200 border-l-2 border-l-amber-500 bg-amber-50'
                            : 'border-transparent hover:bg-gray-50',
                        )}
                      >
                        <FileText size={11} className={clsx('shrink-0', active ? 'text-amber-500' : 'text-gray-300')} />
                        <span className={clsx(
                          'min-w-0 flex-1 truncate text-xs',
                          active ? 'font-medium text-amber-800' : hasContent(ch) ? 'text-gray-800' : 'text-gray-400',
                        )}>
                          {ch.chapter_number}. {title}
                        </span>
                        <span className="shrink-0 text-[10px] tabular-nums text-gray-400">
                          {hasContent(ch) ? `${ch.content!.length}字` : '待写'}
                        </span>
                      </button>
                    )
                  })
                )}
              </div>
            )}
          </div>
        )
      })}
    </>
  )
}
