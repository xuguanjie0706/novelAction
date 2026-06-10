/**
 * @file components/Dabai/DabaiResult.tsx — 大白文产物只读展示。
 * 渲染：定位 / 金手指 / 境界 / 势力 / 人物 / 故事线 / 卷骨架 / 章纲爽点节拍 / linter。
 * 数据来源：props.detail（由 useDabaiGenerate 提供）。无编辑能力（生成+展示+质检）。
 */
import type { ReactNode } from 'react'
import { Flame, Sparkles, ShieldAlert, Users, GitBranch, Layers, Zap, BookMarked } from 'lucide-react'
import type { DabaiProjectDetail, DabaiChapter, DabaiLinterReport, DabaiBenchmark } from '../../types/dabai'
import DabaiBeatMap from './DabaiBeatMap'
import DabaiChapterBeatCard from './DabaiChapterBeatCard'
import { dabaiBeatFromChapter } from '../../utils/dabaiOutlineDisplay'

function Card({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-gray-900">
        {icon}{title}
      </div>
      {children}
    </section>
  )
}

function KV({ data, labels }: { data: Record<string, unknown>; labels: Record<string, string> }) {
  const entries = Object.entries(labels).filter(([k]) => data?.[k] != null && data[k] !== '')
  return (
    <dl className="space-y-2 text-sm">
      {entries.map(([k, label]) => (
        <div key={k} className="flex gap-2">
          <dt className="w-24 shrink-0 text-gray-400">{label}</dt>
          <dd className="text-gray-700">{fmt(data[k])}</dd>
        </div>
      ))}
    </dl>
  )
}

function fmt(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('、')
  if (typeof v === 'object' && v) return JSON.stringify(v)
  return String(v)
}

function LinterBadge({ report }: { report: DabaiLinterReport }) {
  const status = report?.status ?? 'ok'
  const map = {
    ok: 'bg-emerald-100 text-emerald-700', warning: 'bg-amber-100 text-amber-700',
    blocked: 'bg-rose-100 text-rose-700',
  } as const
  const label = { ok: '通过', warning: '有警告', blocked: '被阻断' }[status] ?? status
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${map[status as keyof typeof map] ?? map.ok}`}>
      质检 {label} · {report?.score ?? 100} 分
    </span>
  )
}

function ChapterRow(
  { ch, onWrite, realmName }:
  { ch: DabaiChapter; onWrite?: (ch: DabaiChapter) => void; realmName?: (r?: number | null) => string },
) {
  const written = ch.status === 'written'
  return (
    <DabaiChapterBeatCard
      beat={dabaiBeatFromChapter(ch, realmName)}
      onWrite={onWrite ? () => onWrite(ch) : undefined}
      writeLabel={written ? '看/改正文' : '写正文'}
    />
  )
}

const STYLE_LABELS: Record<string, string> = {
  sentence_style: '句式', pacing: '节奏', dialogue_density: '对话密度',
  shuang_cadence: '爽点节奏', narration_voice: '腔调',
}

function BenchmarkCard({ bm }: { bm: DabaiBenchmark }) {
  if (!bm || !(bm.reference_books?.length || bm.style_profile)) return null
  const sp = bm.style_profile ?? {}
  return (
    <Card icon={<BookMarked size={15} className="text-amber-500" />}
          title={`对标分析${bm.topic ? ` · ${bm.topic}` : ''}`}>
      {bm.reference_books?.length ? (
        <div className="mb-3 space-y-1.5">
          {bm.reference_books.map((b, i) => (
            <div key={i} className="text-sm">
              <span className="font-semibold text-gray-800">{b.title}</span>
              {b.core_appeal && <span className="text-gray-500"> · {b.core_appeal}</span>}
              {b.style_note && <span className="text-xs text-gray-400"> ｜文笔：{b.style_note}</span>}
            </div>
          ))}
        </div>
      ) : null}
      {Object.keys(sp).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(STYLE_LABELS).filter(([k]) => sp[k]).map(([k, label]) => (
            <span key={k} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700">
              {label}：{sp[k]}
            </span>
          ))}
        </div>
      )}
      {bm.pitfalls_to_avoid?.length ? (
        <div className="mt-3 text-xs text-rose-500">避坑：{bm.pitfalls_to_avoid.join('、')}</div>
      ) : null}
      <p className="mt-2 text-[11px] text-gray-300">仅借鉴题材特征，不复制任何作品原文</p>
    </Card>
  )
}

export default function DabaiResult(
  { detail, onWrite }: { detail: DabaiProjectDetail; onWrite?: (ch: DabaiChapter) => void },
) {
  const levels = detail.power_ladder?.levels ?? []
  const report = detail.linter_report ?? {}
  const realmName = (r?: number | null) => {
    if (!r) return ''
    const lv = levels.find((l) => l.rank === r)
    return lv ? `${lv.name}` : `境界${r}档`
  }
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-amber-100 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Flame size={18} className="text-amber-500" />
          <h2 className="text-lg font-bold text-gray-900">{detail.title || detail.logline}</h2>
          {detail.mock && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">离线 mock</span>}
          <span className="ml-auto"><LinterBadge report={report} /></span>
        </div>
        <p className="mt-2 text-sm text-gray-500">一句话创意：{detail.logline}</p>
        {detail.failed_steps?.length > 0 && (
          <p className="mt-2 text-xs text-rose-500">⚠ 失败步骤：{detail.failed_steps.join('、')}</p>
        )}
      </section>

      <BenchmarkCard bm={detail.benchmark} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card icon={<Sparkles size={15} className="text-amber-500" />} title="立项定位">
          <KV data={detail.positioning} labels={{
            target_audience: '目标读者', shuang_pool: '爽点池', face_slap_frequency: '打脸频率',
            golden_three_strategy: '黄金三章', pace_type: '节奏', emotional_arc: '情绪闭环',
            taboo_lines: '禁忌',
          }} />
        </Card>
        <Card icon={<Zap size={15} className="text-amber-500" />} title="金手指（爽点引擎）">
          <KV data={detail.golden_finger} labels={{
            name: '名称', type: '类型', core_ability: '核心能力', upgrade_mechanism: '升级机制',
            shuang_engine: '爽点引擎', restriction: '限制',
          }} />
        </Card>
      </div>

      <Card icon={<Layers size={15} className="text-amber-500" />} title={`境界阶梯 · ${detail.power_ladder?.name ?? ''}`}>
        <div className="flex flex-wrap gap-2">
          {levels.map((l) => (
            <span key={l.rank} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-sm text-gray-700">
              <b className="text-amber-600">{l.rank}</b> {l.name}
            </span>
          ))}
        </div>
      </Card>

      <DabaiBeatMap detail={detail} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card icon={<ShieldAlert size={15} className="text-amber-500" />} title={`势力 ${detail.factions.length}`}>
          <ul className="space-y-2 text-sm text-gray-700">
            {detail.factions.map((f, i) => (
              <li key={i}><b>{fmt(f.name)}</b> <span className="text-xs text-gray-400">{fmt(f.stance)}</span></li>
            ))}
          </ul>
        </Card>
        <Card icon={<Users size={15} className="text-amber-500" />} title={`人物 ${detail.characters.length}`}>
          <ul className="space-y-2 text-sm text-gray-700">
            {detail.characters.map((c, i) => (
              <li key={i}><b>{fmt(c.name)}</b> <span className="text-xs text-gray-400">{fmt(c.role)}</span></li>
            ))}
          </ul>
        </Card>
        <Card icon={<GitBranch size={15} className="text-amber-500" />} title={`故事线 ${detail.storylines.length}`}>
          <ul className="space-y-2 text-sm text-gray-700">
            {detail.storylines.map((s, i) => (
              <li key={i}><b>{fmt(s.name)}</b> <span className="text-xs text-gray-400">{fmt(s.type)}</span></li>
            ))}
          </ul>
        </Card>
      </div>

      <Card icon={<Layers size={15} className="text-amber-500" />} title={`卷骨架 ${detail.volumes.length} 卷`}>
        <div className="grid gap-2 sm:grid-cols-2">
          {detail.volumes.map((v) => (
            <div key={v.volume_number} className="rounded-xl border border-gray-100 p-3 text-sm">
              <div className="font-semibold text-gray-900">{v.title}
                <span className="ml-2 rounded bg-gray-100 px-1.5 text-xs text-gray-500">{v.phase}</span>
                {v.realm_start_rank ? (
                  <span className="ml-2 rounded bg-indigo-50 px-1.5 text-xs text-indigo-600">
                    境界 {realmName(v.realm_start_rank)}→{realmName(v.realm_end_rank)}
                  </span>
                ) : null}
              </div>
              <div className="mt-1 text-xs text-gray-500">高潮：{v.volume_climax}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card icon={<Flame size={15} className="text-rose-500" />}
            title={`章纲 · 爽点节拍器（${detail.chapter_outlines.length} 章，无 choice_cost）`}>
        <div className="space-y-2">
          {detail.chapter_outlines.map((ch) => (
            <ChapterRow key={ch.chapter_number} ch={ch} onWrite={onWrite} realmName={realmName} />
          ))}
        </div>
      </Card>

      {(report.issues?.length ?? 0) > 0 && (
        <Card icon={<ShieldAlert size={15} className="text-rose-500" />} title="大白文 linter 问题">
          <ul className="space-y-1 text-sm">
            {report.issues!.map((it, i) => (
              <li key={i} className="text-gray-600">
                <span className="font-mono text-xs text-rose-500">[{it.severity}] {it.rule_id}</span>{' '}
                {it.chapter ? `第${it.chapter}章` : '卷级'}：{it.message}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
