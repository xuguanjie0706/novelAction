import type { DabaiProjectDetail } from '../../../../types/dabai'
import { pickFields } from '../detailFormat'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-bold text-gray-900">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function FieldList({ rows }: { rows: { label: string; value: string }[] }) {
  if (!rows.length) return <p className="text-xs text-gray-400">暂无</p>
  return (
    <dl className="space-y-2 text-sm">
      {rows.map(r => (
        <div key={r.label} className="flex gap-2">
          <dt className="w-24 shrink-0 text-gray-400">{r.label}</dt>
          <dd className="text-gray-700">{r.value}</dd>
        </div>
      ))}
    </dl>
  )
}

interface Props {
  detail: DabaiProjectDetail
}

export default function WorldPanel({ detail }: Props) {
  const bm = detail.benchmark
  const levels = detail.power_ladder?.levels ?? []

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4">
      <Section title="一句话创意">
        <p className="text-sm text-gray-700">{detail.logline}</p>
        {detail.failed_steps?.length > 0 && (
          <p className="mt-2 text-xs text-rose-500">失败步骤：{detail.failed_steps.join('、')}</p>
        )}
      </Section>

      {bm?.reference_books?.length ? (
        <Section title="对标分析">
          <ul className="space-y-2 text-sm text-gray-700">
            {bm.reference_books.map((b, i) => (
              <li key={i}>
                <span className="font-semibold">{b.title}</span>
                {b.core_appeal ? <span className="text-gray-500"> · {b.core_appeal}</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="立项定位">
          <FieldList rows={pickFields(detail.positioning, {
            target_audience: '目标读者',
            shuang_pool: '爽点池',
            face_slap_frequency: '打脸频率',
            golden_three_strategy: '黄金三章',
            pace_type: '节奏',
            emotional_arc: '情绪闭环',
            taboo_lines: '禁忌',
          })} />
        </Section>
        <Section title="金手指">
          <FieldList rows={pickFields(detail.golden_finger, {
            name: '名称',
            type: '类型',
            core_ability: '核心能力',
            upgrade_mechanism: '升级机制',
            shuang_engine: '爽点引擎',
            restriction: '限制',
          })} />
        </Section>
      </div>

      <Section title={`境界阶梯 · ${detail.power_ladder?.name ?? ''}`}>
        <div className="flex flex-wrap gap-2">
          {levels.map(l => (
            <span key={l.rank} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-sm">
              <b className="text-rose-600">{l.rank}</b> {l.name}
              {l.desc ? <span className="ml-1 text-xs text-gray-400">— {l.desc}</span> : null}
            </span>
          ))}
        </div>
      </Section>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title={`势力（${detail.factions.length}）`}>
          <ul className="space-y-2 text-sm">
            {detail.factions.map((f, i) => (
              <li key={i} className="text-gray-700">
                <b>{String(f.name ?? '')}</b>
                {f.stance ? <span className="text-xs text-gray-400"> · {String(f.stance)}</span> : null}
                {f.note ? <p className="mt-0.5 text-xs text-gray-500">{String(f.note)}</p> : null}
              </li>
            ))}
          </ul>
        </Section>
        <Section title={`故事线（${detail.storylines.length}）`}>
          <ul className="space-y-2 text-sm">
            {detail.storylines.map((s, i) => (
              <li key={i} className="text-gray-700">
                <b>{String(s.name ?? '')}</b>
                {s.type ? <span className="text-xs text-gray-400"> · {String(s.type)}</span> : null}
                {s.summary ? <p className="mt-0.5 text-xs text-gray-500">{String(s.summary)}</p> : null}
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  )
}
