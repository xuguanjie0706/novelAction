/**
 * 人物面板 — 人物卡 + 伴随台账（该人物持有的功法/道具 + 对主角的态度）。
 * 资产/关系来自 dabai_assets / dabai_relations（按 owner / to_name 人名匹配）。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../types/dabaiLab'
import type { DabaiProjectDetail } from '../../../../types/dabai'
import { fmtVal } from '../detailFormat'

interface Props {
  detail: DabaiProjectDetail
  projectId: string
}

const CHAR_FIELDS: { key: string; label: string }[] = [
  { key: 'role', label: '角色' },
  { key: 'tier', label: '层级' },
  { key: 'start_realm', label: '起始境界' },
  { key: 'persona', label: '人设' },
  { key: 'function', label: '功能' },
]

const KIND_BADGE: Record<string, string> = {
  golden_finger: 'bg-amber-50 text-amber-700',
  skill: 'bg-sky-50 text-sky-600',
  item: 'bg-emerald-50 text-emerald-700',
}
const KIND_LABELS: Record<string, string> = {
  golden_finger: '金手指', skill: '功法', item: '道具',
}

function attitudeColor(attitude: string): string {
  if (attitude === '敌对') return 'bg-rose-50 text-rose-600'
  if (['臣服', '效忠', '盟友'].includes(attitude)) return 'bg-emerald-50 text-emerald-700'
  if (attitude === '暧昧') return 'bg-pink-50 text-pink-600'
  return 'bg-gray-100 text-gray-500'
}

export default function CharactersPanel({ detail, projectId }: Props) {
  const [assets, setAssets] = useState<DabaiLabAsset[]>([])
  const [relations, setRelations] = useState<DabaiLabRelation[]>([])

  useEffect(() => {
    let cancelled = false
    Promise.all([dabaiLabApi.listAssets(projectId), dabaiLabApi.listRelations(projectId)])
      .then(([a, r]) => {
        if (cancelled) return
        setAssets(a.data.items)
        setRelations(r.data.items)
      })
      .catch(() => { /* 台账缺失不影响人物卡 */ })
    return () => { cancelled = true }
  }, [projectId])

  if (!detail.characters.length) {
    return <p className="p-8 text-center text-sm text-gray-400">暂无人物</p>
  }

  return (
    <div className="mx-auto grid max-w-4xl gap-3 p-4 sm:grid-cols-2">
      {detail.characters.map((c, i) => {
        const name = fmtVal(c.name) || '未命名'
        const owned = assets.filter(a => a.owner === c.name)
        const rel = relations.find(r => r.to_name === c.name)
        return (
          <article key={i} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <h3 className="min-w-0 flex-1 truncate text-base font-bold text-gray-900">{name}</h3>
              {rel?.attitude ? (
                <span
                  className={clsx('rounded-full px-2 py-0.5 text-[10px]', attitudeColor(rel.attitude))}
                  title={rel.note ?? undefined}
                >
                  对{rel.from_name}·{rel.attitude}
                </span>
              ) : null}
            </div>
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
            {owned.length > 0 && (
              <div className="mt-3 border-t border-gray-50 pt-2">
                <p className="mb-1 text-[11px] font-semibold text-gray-400">持有功法 / 道具</p>
                <ul className="space-y-1">
                  {owned.map(a => (
                    <li key={a.id} className="flex items-start gap-1.5 text-xs">
                      <span className={clsx('shrink-0 rounded px-1.5 py-0.5 text-[10px]', KIND_BADGE[a.kind] ?? 'bg-gray-100 text-gray-500')}>
                        {KIND_LABELS[a.kind] ?? a.kind}
                      </span>
                      <span className={clsx(a.status === 'active' ? 'text-gray-700' : 'text-gray-400 line-through')}>
                        {a.name}
                        {a.description ? <span className="text-gray-400">　{a.description}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {rel?.note ? (
              <p className="mt-2 text-[11px] text-gray-400">张力：{rel.note}</p>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
