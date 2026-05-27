/**
 * @file 战力时间轴页：折线+卷泳道混合图、全员境界泳道、结构化表。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Sword } from 'lucide-react'
import clsx from 'clsx'

import { outlineApi } from '../../api/client'
import type { PowerTimeline } from '../../types'
import HybridPowerChart from './HybridPowerChart'
import CharacterRealmLanesChart from './CharacterRealmLanesChart'
import PowerTimelineTable from './PowerTimelineTable'

type ViewTab = 'hybrid' | 'lanes' | 'table'

const TABS: { id: ViewTab; label: string }[] = [
  { id: 'hybrid', label: '折线+卷泳道' },
  { id: 'lanes', label: '全员泳道' },
  { id: 'table', label: '数据表' },
]

export default function PowerTimelinePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [data, setData] = useState<PowerTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<ViewTab>('hybrid')

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    outlineApi
      .powerTimeline(projectId, true)
      .then(r => {
        const payload = r.data
        setData({
          ...payload,
          realm_scale: payload.realm_scale ?? [],
          chart: payload.chart ?? { protagonist: [], boss: [] },
          character_lanes: payload.character_lanes ?? [],
          volume_count: payload.volume_count ?? payload.rows?.length ?? 0,
        })
      })
      .catch(() => setError('加载战力时间轴失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  const laneCount = useMemo(() => data?.character_lanes?.length ?? 0, [data])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-gray-500 text-sm">
        <Loader2 size={18} className="animate-spin" />
        加载战力轴…
      </div>
    )
  }
  if (error || !data) {
    return <div className="flex h-full items-center justify-center text-sm text-red-600">{error ?? '无数据'}</div>
  }

  return (
    <div className="h-full min-h-0 flex flex-col bg-[#FAF8F4]">
      <header className="shrink-0 border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2 text-gray-800 font-semibold text-sm">
          <Sword size={16} className="text-[#C4873A]" />
          战力时间轴
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {data.volume_count} 卷 · {laneCount} 人泳道
          {data.updated_at ? ` · 更新 ${new Date(data.updated_at).toLocaleString()}` : ''}
        </p>
        <div className="flex gap-1 mt-2">
          {TABS.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={clsx(
                'text-[11px] px-2.5 py-1 rounded-md border transition-colors',
                tab === t.id
                  ? 'bg-[#C4873A] text-white border-[#C4873A]'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 min-h-0 overflow-auto p-3 space-y-3">
        {tab === 'hybrid' && <HybridPowerChart data={data} />}
        {tab === 'lanes' && <CharacterRealmLanesChart data={data} />}
        {tab === 'table' && <PowerTimelineTable data={data} />}
      </div>
    </div>
  )
}
