/**
 * @file pages/Dabai/detail/RenderBeats.tsx
 * 详情页「结构层」分区渲染：卷骨架 / 爽点节拍（章纲）/ 卷纲质检。
 * 章纲按卷分组展示，凸显大白文一等公民——爽点类型 / 憋屈 / 引爆 / 见证者 / 钩子。
 */
import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Flame, ShieldCheck } from 'lucide-react'
import type { DabaiChapter, DabaiProjectDetail, DabaiVolume } from '../../../types/dabai'
import { makeRealmLabel } from '../write-dabailab/realmLabel'
import { Card, Pill, SectionEmpty } from './blocks'

function asStr(v: unknown): string {
  return v == null ? '' : String(v)
}

/** 卷骨架：每卷 phase / 境界区间 / Boss / 大爆点 / 卷末高潮。 */
export function VolumesSection({ d }: { d: DabaiProjectDetail }) {
  const realm = makeRealmLabel(d)
  if (!d.volumes.length) return <SectionEmpty icon={<Flame size={28} />} text="暂无卷骨架" />
  return (
    <div className="space-y-4">
      {d.volumes.map(v => {
        const extra = (v.extra ?? {}) as Record<string, unknown>
        const boss = asStr(extra.volume_boss || extra.boss)
        return (
          <div key={v.id ?? v.volume_number} className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-orange-100 text-sm font-bold text-orange-700">
                {v.volume_number}
              </span>
              <h3 className="text-base font-bold text-gray-900">{v.title}</h3>
              {v.phase ? <Pill>{v.phase}</Pill> : null}
              <span className="text-xs text-gray-400">{v.planned_chapters} 章</span>
              {v.realm_start_rank ? (
                <Pill tone="indigo">{realm(v.realm_start_rank)} → {realm(v.realm_end_rank)}</Pill>
              ) : null}
              {boss ? <Pill tone="rose">Boss · {boss}</Pill> : null}
            </div>
            {v.volume_climax ? (
              <p className="mt-2.5 text-sm text-gray-600"><span className="text-gray-400">卷高潮 · </span>{v.volume_climax}</p>
            ) : null}
            {v.end_hook ? (
              <p className="mt-1 text-sm text-gray-600"><span className="text-gray-400">卷末钩子 · </span>{v.end_hook}</p>
            ) : null}
            {v.big_beats?.length ? (
              <ul className="mt-3 space-y-1 text-xs text-gray-600">
                {v.big_beats.map((b, i) => (
                  <li key={i} className="flex gap-2"><span className="text-orange-400">▸</span><span>{b}</span></li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function BeatChapterRow({ ch, realm }: { ch: DabaiChapter; realm: (r?: number | null) => string }) {
  const written = !!(ch.content && ch.content.length)
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-gray-400">{ch.chapter_number}</span>
        <span className="text-sm font-semibold text-gray-800">{ch.title}</span>
        {ch.shuang_type ? <Pill tone="rose">{ch.shuang_type}</Pill> : null}
        {ch.is_big_beat ? <Pill tone="amber">大爆点</Pill> : null}
        {ch.realm_rank ? <Pill tone="indigo">{realm(ch.realm_rank)}</Pill> : null}
        <span className="ml-auto text-[10px] text-gray-400">{written ? `${ch.content!.length} 字` : '待写'}</span>
      </div>
      <div className="mt-2 grid gap-1.5 text-xs leading-relaxed text-gray-600 sm:grid-cols-2">
        {ch.yaqu_setup ? <p><span className="text-gray-400">憋屈 · </span>{ch.yaqu_setup}</p> : null}
        {ch.yinbao ? <p><span className="text-gray-400">引爆 · </span>{ch.yinbao}</p> : null}
        {ch.shuang_payoff ? <p><span className="text-rose-400">爽感 · </span>{ch.shuang_payoff}</p> : null}
        {ch.end_hook ? <p><span className="text-gray-400">钩子 · </span>{ch.end_hook}</p> : null}
      </div>
      {ch.witnesses?.length ? (
        <p className="mt-1.5 text-[11px] text-gray-400">见证者：{ch.witnesses.join('、')}</p>
      ) : null}
    </div>
  )
}

/** 爽点节拍：章纲按卷折叠分组。 */
export function BeatsSection({ d }: { d: DabaiProjectDetail }) {
  const realm = makeRealmLabel(d)
  const groups = useMemo(() => {
    const byVol = new Map<number, DabaiChapter[]>()
    for (const ch of d.chapter_outlines) {
      // 章号区间归卷：按卷 planned_chapters 累加边界。
      let acc = 0
      let volNo = d.volumes[0]?.volume_number ?? 1
      for (const v of d.volumes) {
        if (ch.chapter_number <= acc + (v.planned_chapters || 0)) { volNo = v.volume_number; break }
        acc += v.planned_chapters || 0
        volNo = v.volume_number
      }
      const list = byVol.get(volNo) ?? []
      list.push(ch)
      byVol.set(volNo, list)
    }
    return d.volumes
      .map(v => ({ v, chapters: (byVol.get(v.volume_number) ?? []).sort((a, b) => a.chapter_number - b.chapter_number) }))
      .filter(g => g.chapters.length)
  }, [d])

  if (!d.chapter_outlines.length) {
    return <SectionEmpty icon={<Flame size={28} />} text="章纲尚未展开 · 进入写作台按卷展开" />
  }

  return (
    <div className="space-y-3">
      {groups.map(g => (
        <VolumeBeatGroup key={g.v.volume_number} v={g.v} chapters={g.chapters} realm={realm} />
      ))}
    </div>
  )
}

function VolumeBeatGroup({
  v, chapters, realm,
}: {
  v: DabaiVolume
  chapters: DabaiChapter[]
  realm: (r?: number | null) => string
}) {
  const [open, setOpen] = useState(v.volume_number <= 1)
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-5 py-3 text-left hover:bg-gray-50"
      >
        {open ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
        <span className="text-sm font-bold text-gray-900">第 {v.volume_number} 卷 · {v.title}</span>
        <span className="ml-auto text-xs text-gray-400">{chapters.length} 章</span>
      </button>
      {open ? (
        <div className="space-y-2 border-t border-gray-50 p-4">
          {chapters.map(ch => <BeatChapterRow key={ch.id ?? ch.chapter_number} ch={ch} realm={realm} />)}
        </div>
      ) : null}
    </div>
  )
}

/** 卷纲质检报告。 */
export function QualitySection({ d, onRelint, relinting }: {
  d: DabaiProjectDetail
  onRelint: () => void
  relinting: boolean
}) {
  const r = d.linter_report ?? {}
  const issues = r.issues ?? []
  const sevTone: Record<string, 'rose' | 'amber' | 'gray'> = {
    critical: 'rose', high: 'amber', medium: 'gray',
  }
  return (
    <div className="space-y-4">
      <Card title="质检概览">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold text-emerald-600">{r.score ?? '—'}</span>
            <span className="text-xs text-gray-400">/ 100</span>
          </div>
          <div className="flex flex-col gap-1 text-xs text-gray-500">
            <span>状态：{r.status ?? '未检测'}</span>
            <span>问题 {r.issue_count ?? 0} 条 · 严重 {r.critical_count ?? 0} 条</span>
            {r.chapter_count != null ? <span>覆盖 {r.chapter_count} 章</span> : null}
            {r.linted_at ? <span>检测于 {new Date(r.linted_at).toLocaleString('zh-CN')}</span> : null}
          </div>
          <button
            type="button"
            onClick={onRelint}
            disabled={relinting}
            className="ml-auto rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-600 disabled:opacity-60"
          >
            {relinting ? '检测中…' : '重新检测'}
          </button>
        </div>
      </Card>

      {issues.length ? (
        <Card title="问题清单" count={issues.length}>
          <ul className="space-y-2">
            {issues.map((iss, i) => (
              <li key={i} className="rounded-lg border border-gray-100 bg-gray-50/60 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={sevTone[iss.severity] ?? 'gray'}>{iss.severity}</Pill>
                  <span className="font-mono text-[11px] text-gray-400">{iss.rule_id}</span>
                  {iss.chapter != null ? <span className="text-[11px] text-gray-400">第 {iss.chapter} 章</span> : null}
                </div>
                <p className="mt-1.5 text-sm text-gray-700">{iss.message}</p>
                {iss.suggestion ? <p className="mt-1 text-xs text-gray-500">建议 · {iss.suggestion}</p> : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/40 py-12">
          <ShieldCheck size={28} className="text-emerald-400" />
          <p className="text-sm text-emerald-700">
            {r.status === 'pending' || r.score == null ? '尚未检测' : '未发现问题'}
          </p>
        </div>
      )}
    </div>
  )
}
