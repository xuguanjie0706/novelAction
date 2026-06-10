import type { DabaiProjectDetail } from '../../../../types/dabai'
import { fmtVal } from '../detailFormat'

interface Props {
  detail: DabaiProjectDetail
}

const CHAR_FIELDS: { key: string; label: string }[] = [
  { key: 'role', label: '角色' },
  { key: 'tier', label: '层级' },
  { key: 'start_realm', label: '起始境界' },
  { key: 'persona', label: '人设' },
  { key: 'function', label: '功能' },
]

export default function CharactersPanel({ detail }: Props) {
  if (!detail.characters.length) {
    return <p className="p-8 text-center text-sm text-gray-400">暂无人物</p>
  }

  return (
    <div className="mx-auto grid max-w-4xl gap-3 p-4 sm:grid-cols-2">
      {detail.characters.map((c, i) => (
        <article key={i} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <h3 className="text-base font-bold text-gray-900">{fmtVal(c.name) || '未命名'}</h3>
          <dl className="mt-2 space-y-1.5 text-sm">
            {CHAR_FIELDS.map(f => {
              const v = fmtVal(c[f.key])
              if (!v) return null
              return (
                <div key={f.key} className="flex gap-2">
                  <dt className="w-16 shrink-0 text-gray-400">{f.label}</dt>
                  <dd className="text-gray-700">{v}</dd>
                </div>
              )
            })}
          </dl>
        </article>
      ))}
    </div>
  )
}
