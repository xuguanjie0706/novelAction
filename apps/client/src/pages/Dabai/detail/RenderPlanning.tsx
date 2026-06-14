/**
 * @file pages/Dabai/detail/RenderPlanning.tsx
 * 详情页「规划层」分区渲染：立项概览 / 对标 / 金手指 / 境界 / 反派阶梯 /
 * 势力 / 人物 / 故事线 / 谜题排程。数据全部来自 DabaiProjectDetail（只读）。
 */
import { BookOpen } from 'lucide-react'
import type { DabaiProjectDetail } from '../../../types/dabai'
import { resolveDabaiIntensity } from '../../../types/dabai'
import { Card, FieldList, Pill, Empty, SectionEmpty, fmtVal, pickFields } from './blocks'
import { antagonistLadder, mysteries } from './sections'
import IntensityControl from './IntensityControl'

function asStr(v: unknown): string {
  return v == null ? '' : String(v)
}

/** 立项概览：创意 / 简介 / 立项定位 / 叙事烈度档。 */
export function OverviewSection({ d, projectId }: { d: DabaiProjectDetail; projectId: string }) {
  const extra = d.extra ?? {}
  const blurb = (extra.title_blurb ?? {}) as Record<string, unknown>
  const candidates = Array.isArray(blurb.candidates) ? (blurb.candidates as unknown[]) : []
  return (
    <div className="space-y-4">
      <Card title="一句话创意">
        <p className="text-sm leading-relaxed text-gray-700">{d.logline}</p>
        {asStr(blurb.blurb || blurb.tagline) ? (
          <p className="mt-3 rounded-lg bg-rose-50/60 p-3 text-sm leading-relaxed text-gray-600">
            {asStr(blurb.blurb || blurb.tagline)}
          </p>
        ) : null}
        {d.failed_steps?.length ? (
          <p className="mt-3 text-xs text-rose-500">⚠️ 失败步骤：{d.failed_steps.join('、')}</p>
        ) : null}
      </Card>

      <Card title="叙事烈度（写正文用）" hint="降调克制 / 默认 / 够炸">
        <IntensityControl projectId={projectId} value={resolveDabaiIntensity(d)} />
      </Card>

      <Card title="立项定位">
        <FieldList
          rows={pickFields(d.positioning, {
            target_audience: '目标读者',
            shuang_pool: '爽点池',
            face_slap_frequency: '打脸频率',
            golden_three_strategy: '黄金三章',
            pace_type: '节奏',
            emotional_arc: '情绪闭环',
            writing_style: '写作风格',
            taboo_lines: '禁忌线',
          })}
        />
      </Card>

      {candidates.length ? (
        <Card title="书名候选" count={candidates.length}>
          <div className="flex flex-wrap gap-2">
            {candidates.slice(0, 16).map((c, i) => {
              const name = typeof c === 'object' && c !== null
                ? asStr((c as Record<string, unknown>).title || (c as Record<string, unknown>).name)
                : asStr(c)
              const chosen = name && name === d.title
              return name ? (
                <Pill key={i} tone={chosen ? 'rose' : 'gray'}>
                  {chosen ? '★ ' : ''}{name}
                </Pill>
              ) : null
            })}
          </div>
        </Card>
      ) : null}
    </div>
  )
}

/** 对标分析。 */
export function BenchmarkSection({ d }: { d: DabaiProjectDetail }) {
  const bm = d.benchmark ?? {}
  const books = bm.reference_books ?? []
  if (!books.length && !bm.tropes_to_use?.length) {
    return <SectionEmpty icon={<BookOpen size={28} />} text="暂无对标分析" />
  }
  return (
    <div className="space-y-4">
      {bm.topic ? (
        <Card title="题材定位"><p className="text-sm text-gray-700">{bm.topic}</p></Card>
      ) : null}

      {books.length ? (
        <Card title="对标作品" count={books.length}>
          <div className="grid gap-3 sm:grid-cols-2">
            {books.map((b, i) => (
              <div key={i} className="rounded-xl border border-gray-100 bg-gray-50/60 p-3">
                <div className="text-sm font-bold text-gray-900">{b.title}</div>
                {b.core_appeal ? <p className="mt-1 text-xs text-gray-600">核心爽感 · {b.core_appeal}</p> : null}
                {b.setting_motif ? <p className="mt-0.5 text-xs text-gray-500">设定母题 · {b.setting_motif}</p> : null}
                {b.style_note ? <p className="mt-0.5 text-xs text-gray-400">{b.style_note}</p> : null}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {(bm.tropes_to_use?.length || bm.pitfalls_to_avoid?.length) ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="可用套路">
            <div className="flex flex-wrap gap-1.5">
              {(bm.tropes_to_use ?? []).map((t, i) => <Pill key={i} tone="emerald">{t}</Pill>)}
              {!bm.tropes_to_use?.length ? <Empty /> : null}
            </div>
          </Card>
          <Card title="规避雷区">
            <div className="flex flex-wrap gap-1.5">
              {(bm.pitfalls_to_avoid ?? []).map((t, i) => <Pill key={i} tone="rose">{t}</Pill>)}
              {!bm.pitfalls_to_avoid?.length ? <Empty /> : null}
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  )
}

/** 金手指。 */
export function GoldenSection({ d }: { d: DabaiProjectDetail }) {
  const gf = d.golden_finger ?? {}
  const firstShuang = Array.isArray(gf.first_10_shuang) ? (gf.first_10_shuang as unknown[]) : []
  const milestones = Array.isArray(gf.realm_milestones) ? (gf.realm_milestones as unknown[]) : []
  if (!Object.keys(gf).length) {
    return <SectionEmpty icon={<BookOpen size={28} />} text="暂无金手指设定" />
  }
  return (
    <div className="space-y-4">
      <Card title="金手指核心">
        <FieldList
          rows={pickFields(gf, {
            name: '名称',
            type: '类型',
            core_ability: '核心能力',
            upgrade_mechanism: '升级机制',
            shuang_engine: '爽点引擎',
            manifestation_style: '呈现方式',
            blood_price: '代价',
            restriction: '限制',
          })}
        />
      </Card>

      {firstShuang.length ? (
        <Card title="前 10 章爽点弹药" count={firstShuang.length}>
          <ul className="space-y-1.5 text-sm text-gray-700">
            {firstShuang.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="font-mono text-xs text-rose-400">{i + 1}</span>
                <span>{fmtVal(s)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {milestones.length ? (
        <Card title="境界 × 金手指里程碑" count={milestones.length}>
          <ul className="space-y-1.5 text-sm text-gray-700">
            {milestones.map((m, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-rose-400">▸</span>
                <span>{fmtVal(m)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  )
}

/** 境界阶梯。 */
export function PowerSection({ d }: { d: DabaiProjectDetail }) {
  const levels = d.power_ladder?.levels ?? []
  if (!levels.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无境界体系" />
  return (
    <Card title={`境界阶梯 · ${d.power_ladder?.name ?? ''}`} count={levels.length}>
      <ol className="space-y-2">
        {levels.map(l => (
          <li key={l.rank} className="flex items-start gap-3 rounded-lg border border-gray-100 bg-gray-50/60 px-3 py-2">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-100 text-xs font-bold text-cyan-700">
              {l.rank}
            </span>
            <div>
              <div className="text-sm font-semibold text-gray-900">{l.name}</div>
              {l.desc ? <div className="text-xs text-gray-500">{l.desc}</div> : null}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

/** 反派阶梯（卷级 Boss roster）。 */
export function AntagonistSection({ d }: { d: DabaiProjectDetail }) {
  const ladder = antagonistLadder(d) as Record<string, unknown>[]
  if (!ladder.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无反派阶梯" />
  return (
    <div className="space-y-3">
      {ladder.map((b, i) => (
        <div key={i} className="flex items-start gap-3 rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rose-100 text-sm font-bold text-rose-700">
            {asStr(b.volume_number) || i + 1}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold text-gray-900">{asStr(b.boss_name) || '（待定）'}</span>
              {asStr(b.boss_realm) ? <Pill tone="indigo">{asStr(b.boss_realm)}</Pill> : null}
              {asStr(b.faction) ? <Pill>{asStr(b.faction)}</Pill> : null}
            </div>
            {asStr(b.face_slap_hook) ? (
              <p className="mt-1.5 text-xs leading-relaxed text-gray-600">
                <span className="text-rose-400">打脸钩子 · </span>{asStr(b.face_slap_hook)}
              </p>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}

/** 势力。 */
export function FactionsSection({ d }: { d: DabaiProjectDetail }) {
  if (!d.factions.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无势力" />
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {d.factions.map((f, i) => (
        <div key={i} className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900">{asStr(f.name)}</span>
            {asStr(f.stance) ? <Pill tone="rose">{asStr(f.stance)}</Pill> : null}
            {asStr(f.power_tier) ? <Pill tone="indigo">{asStr(f.power_tier)}</Pill> : null}
          </div>
          {asStr(f.role) ? <p className="mt-1.5 text-xs text-gray-600">{asStr(f.role)}</p> : null}
          {asStr(f.note) ? <p className="mt-1 text-xs text-gray-400">{asStr(f.note)}</p> : null}
        </div>
      ))}
    </div>
  )
}

/** 人物。 */
export function CharactersSection({ d }: { d: DabaiProjectDetail }) {
  if (!d.characters.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无人物" />
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {d.characters.map((c, i) => (
        <div key={i} className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900">{asStr(c.name)}</span>
            {asStr(c.role) ? <Pill tone="emerald">{asStr(c.role)}</Pill> : null}
            {asStr(c.start_realm) ? <Pill tone="indigo">{asStr(c.start_realm)}</Pill> : null}
          </div>
          {asStr(c.persona) ? <p className="mt-1.5 text-xs text-gray-600">人设 · {asStr(c.persona)}</p> : null}
          {asStr(c.function) ? <p className="mt-1 text-xs text-gray-500">爽点功能 · {asStr(c.function)}</p> : null}
          {asStr(c.name_meaning) ? <p className="mt-1 text-xs text-gray-400">{asStr(c.name_meaning)}</p> : null}
        </div>
      ))}
    </div>
  )
}

/** 故事线。 */
export function StorylinesSection({ d }: { d: DabaiProjectDetail }) {
  if (!d.storylines.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无故事线" />
  return (
    <div className="space-y-3">
      {d.storylines.map((s, i) => (
        <div key={i} className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900">{asStr(s.name)}</span>
            {asStr(s.type) ? <Pill tone="indigo">{asStr(s.type)}</Pill> : null}
          </div>
          {asStr(s.summary) ? <p className="mt-1.5 text-xs text-gray-600">{asStr(s.summary)}</p> : null}
        </div>
      ))}
    </div>
  )
}

/** 谜题排程。 */
export function MysterySection({ d }: { d: DabaiProjectDetail }) {
  const list = mysteries(d) as Record<string, unknown>[]
  if (!list.length) return <SectionEmpty icon={<BookOpen size={28} />} text="暂无谜题排程" />
  return (
    <div className="space-y-3">
      {list.map((m, i) => (
        <div key={i} className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900">{asStr(m.name) || `谜题 ${i + 1}`}</span>
            {asStr(m.final_reveal_volume) ? (
              <Pill tone="amber">第 {asStr(m.final_reveal_volume)} 卷揭底</Pill>
            ) : null}
          </div>
          {asStr(m.hook_question) ? (
            <p className="mt-1.5 text-xs text-gray-600"><span className="text-sky-500">钩子 · </span>{asStr(m.hook_question)}</p>
          ) : null}
          {asStr(m.essence) ? (
            <p className="mt-1 text-xs text-gray-400"><span className="text-gray-300">真相 · </span>{asStr(m.essence)}</p>
          ) : null}
        </div>
      ))}
    </div>
  )
}
