import type { MutableRefObject, ReactNode } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronRight } from 'lucide-react'
import DabaiChapterBeatCard from '../../../../components/Dabai/DabaiChapterBeatCard'
import type { DabaiChapter } from '../../../../types/dabai'
import { dabaiBeatFromChapter } from '../../../../utils/dabaiOutlineDisplay'
import type { VolumeGroup } from '../groupByVolume'
import { hasContent } from '../useWriteDabailab'

interface Props {
  groups: VolumeGroup[]
  activeId: string | null
  activeVolumeKey: string | null
  collapsed: Set<string>
  visibleChapters: (g: VolumeGroup) => DabaiChapter[]
  volumeKey: (g: VolumeGroup) => string
  realmName: (r?: number | null) => string
  activeRowRef: MutableRefObject<HTMLDivElement | null>
  onToggleVolume: (key: string) => void
  onSelect: (ch: DabaiChapter) => void
  /** 卷头右侧动作（如「展开章纲」入口）；返回 null/undefined 则不渲染。 */
  volumeAction?: (g: VolumeGroup) => ReactNode
}

export default function BeatCardNav({
  groups,
  activeId,
  activeVolumeKey,
  collapsed,
  visibleChapters,
  volumeKey,
  realmName,
  activeRowRef,
  onToggleVolume,
  onSelect,
  volumeAction,
}: Props) {
  return (
    <>
      {groups.map(group => {
        const key = volumeKey(group)
        const isCollapsed = collapsed.has(key)
        const writtenCount = group.chapters.filter(hasContent).length
        const chapters = visibleChapters(group)
        return (
          <div key={key}>
            <div className={clsx(
              'flex w-full items-center rounded-lg text-xs font-semibold',
              key === activeVolumeKey ? 'bg-rose-100/70 text-rose-900' : 'text-gray-700 hover:bg-rose-50',
            )}>
              <button
                type="button"
                onClick={() => onToggleVolume(key)}
                className="flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left"
              >
                {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                <span className="min-w-0 flex-1 truncate">{group.volume.title}</span>
                <span className="shrink-0 text-[10px] font-normal tabular-nums text-gray-400">
                  {writtenCount}/{group.chapters.length}
                </span>
              </button>
              {volumeAction?.(group)}
            </div>
            {!isCollapsed && (
              <div className="mt-1 space-y-1.5 pl-1.5">
                {chapters.length === 0 ? (
                  <p className="px-2 py-2 text-[11px] text-gray-300">无匹配章节</p>
                ) : (
                  chapters.map(ch => {
                    const active = ch.id === activeId
                    const beat = dabaiBeatFromChapter(ch, realmName)
                    return (
                      <div key={ch.id ?? ch.chapter_number} ref={active ? activeRowRef : undefined}>
                        <DabaiChapterBeatCard
                          beat={beat}
                          active={active}
                          onClick={() => onSelect(ch)}
                          trailing={
                            <span className={clsx(
                              'shrink-0 text-[10px] tabular-nums',
                              active ? 'text-amber-700' : 'text-gray-400',
                            )}>
                              {hasContent(ch) ? `${ch.content!.length}字` : '待写'}
                            </span>
                          }
                        />
                      </div>
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
