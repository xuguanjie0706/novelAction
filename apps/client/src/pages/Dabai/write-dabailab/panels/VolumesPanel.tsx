import clsx from 'clsx'
import type { DabaiChapter, DabaiProjectDetail } from '../../../../types/dabai'
import type { VolumeGroup } from '../groupByVolume'
import { makeRealmLabel } from '../realmLabel'
import { hasContent } from '../useWriteDabailab'

interface Props {
  detail: DabaiProjectDetail
  groups: VolumeGroup[]
  activeId: string | null
  onSelectChapter: (ch: DabaiChapter) => void
}

function ChapterBeatRow({
  ch, active, realmName, onSelect,
}: {
  ch: DabaiChapter
  active: boolean
  realmName: (r?: number | null) => string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors',
        active ? 'border-rose-200 bg-rose-50' : 'border-gray-100 hover:border-rose-100',
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-gray-400">{ch.chapter_number}</span>
        <span className="min-w-0 flex-1 truncate font-medium text-gray-800">{ch.title}</span>
        {ch.shuang_type ? (
          <span className="shrink-0 rounded bg-rose-50 px-1.5 text-[10px] text-rose-600">{ch.shuang_type}</span>
        ) : null}
        <span className="shrink-0 text-[10px] text-gray-400">
          {hasContent(ch) ? `${ch.content!.length}字` : '待写'}
        </span>
      </div>
      {ch.yaqu_setup ? (
        <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-gray-500">{ch.yaqu_setup}</p>
      ) : null}
      {ch.realm_rank ? (
        <p className="mt-0.5 text-[10px] text-indigo-500">境界 {realmName(ch.realm_rank)}</p>
      ) : null}
    </button>
  )
}

export default function VolumesPanel({ detail, groups, activeId, onSelectChapter }: Props) {
  const realmName = makeRealmLabel(detail)

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4">
      {groups.map(g => {
        const v = g.volume
        return (
          <section key={v.id ?? v.volume_number} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start gap-2">
              <h3 className="text-base font-bold text-gray-900">{v.title}</h3>
              <span className="rounded bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">{v.phase}</span>
              <span className="text-xs text-gray-400">{v.planned_chapters} 章</span>
              {v.realm_start_rank ? (
                <span className="rounded bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-600">
                  {realmName(v.realm_start_rank)} → {realmName(v.realm_end_rank)}
                </span>
              ) : null}
            </div>
            {v.volume_climax ? (
              <p className="mt-2 text-sm text-gray-600"><span className="text-gray-400">卷高潮 · </span>{v.volume_climax}</p>
            ) : null}
            {v.end_hook ? (
              <p className="mt-1 text-sm text-gray-600"><span className="text-gray-400">卷末钩子 · </span>{v.end_hook}</p>
            ) : null}
            {v.big_beats?.length ? (
              <ul className="mt-3 space-y-1 text-xs text-gray-600">
                {v.big_beats.map((b, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-rose-400">▸</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="mt-4 space-y-2 border-t border-gray-50 pt-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">章纲节拍</div>
              {g.chapters.map(ch => (
                <ChapterBeatRow
                  key={ch.id ?? ch.chapter_number}
                  ch={ch}
                  active={ch.id === activeId}
                  realmName={realmName}
                  onSelect={() => onSelectChapter(ch)}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
