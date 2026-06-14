/**
 * 详情页「功法·道具」— 写作期台账（dabai_assets）+ 建书规划（extra.story_assets）。
 */
import { Link } from 'react-router-dom'
import { Package, PenLine } from 'lucide-react'
import type { DabaiProjectDetail } from '../../../types/dabai'
import LedgerPanel from '../write-dabailab/panels/LedgerPanel'
import { Card, Pill } from './blocks'

const KIND_LABELS: Record<string, string> = {
  skill: '功法', item: '道具', golden_finger: '金手指',
}

interface PlotAsset {
  kind?: string
  name?: string
  plot_role?: string
  owner?: string
  debut?: string
  planned_volume?: number
  description?: string
}

function PlannedAssets({ d }: { d: DabaiProjectDetail }) {
  const sa = (d.extra ?? {}).story_assets as { plot_assets?: PlotAsset[] } | undefined
  const items = (sa?.plot_assets ?? []).filter(a => (a.name ?? '').trim())
  if (items.length === 0) return null

  return (
    <Card title="建书规划资产" count={items.length}>
      <p className="mb-3 text-xs text-gray-500">
        Bootstrap「剧情资产」步产出；未获得前可能在「线索」而非下方台账。写章复盘后会同步进实际持有列表。
      </p>
      <ul className="space-y-2">
        {items.map((a, i) => (
          <li key={i} className="rounded-lg border border-gray-100 bg-gray-50/80 px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={a.kind === 'skill' ? 'indigo' : 'emerald'}>
                {KIND_LABELS[a.kind ?? ''] ?? '道具'}
              </Pill>
              <span className="font-medium text-gray-900">{a.name}</span>
              {a.plot_role ? <span className="text-xs text-gray-400">{a.plot_role}</span> : null}
              {a.owner ? <span className="text-xs text-gray-400">· {a.owner}</span> : null}
              {a.debut === 'later' ? (
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">剧情获得</span>
              ) : (
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">开局自带</span>
              )}
            </div>
            {a.description ? <p className="mt-1 text-xs text-gray-600">{a.description}</p> : null}
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default function LedgerSection({
  projectId, d,
}: { projectId: string; d: DabaiProjectDetail }) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-100 bg-amber-50/50 px-4 py-3">
        <Package size={18} className="shrink-0 text-amber-600" />
        <p className="min-w-0 flex-1 text-xs leading-relaxed text-gray-600">
          实际持有（功法 / 道具 / 金手指）由写章复盘写入台账，写前导演单会锁定规格并注入正文。
        </p>
        <Link
          to={`/dabai/${projectId}/write-dabailab?tab=ledger`}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-50"
        >
          <PenLine size={13} />
          写作台台账
        </Link>
      </div>
      <LedgerPanel projectId={projectId} embedded />
      <PlannedAssets d={d} />
    </div>
  )
}
