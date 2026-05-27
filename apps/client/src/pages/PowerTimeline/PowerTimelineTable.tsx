import React from 'react'
import { TrendingDown, TrendingUp, Minus } from 'lucide-react'

import type { PowerTimeline, PowerTimelineRow } from '../../types'

function trendIcon(trend: string) {
  if (trend === 'up') return <TrendingUp size={14} className="text-emerald-600" />
  if (trend === 'down') return <TrendingDown size={14} className="text-red-600" />
  return <Minus size={14} className="text-gray-400" />
}

function deltaText(delta?: number | null): string {
  if (delta == null) return '—'
  if (delta > 0) return `+${delta}`
  return `${delta}`
}

function rowRisk(row: PowerTimelineRow): { label: string; cls: string } {
  const majorDown = row.boss_vs_prev_major === 'down'
  const effectiveDown = row.boss_vs_prev_effective === 'down'
  if (majorDown) return { label: '高风险', cls: 'bg-red-100 text-red-700' }
  if (effectiveDown) return { label: '需关注', cls: 'bg-amber-100 text-amber-700' }
  return { label: '正常', cls: 'bg-emerald-100 text-emerald-700' }
}

export default function PowerTimelineTable({ data }: { data: PowerTimeline }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-100 text-xs font-semibold text-gray-700">结构化数据表</div>
      <table className="w-full text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="text-left px-3 py-2">卷</th>
            <th className="text-left px-3 py-2">主角起止</th>
            <th className="text-left px-3 py-2">Boss</th>
            <th className="text-left px-3 py-2">Boss境界</th>
            <th className="text-left px-3 py-2">对前卷</th>
            <th className="text-left px-3 py-2">与主角差值</th>
            <th className="text-left px-3 py-2">判定</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map(row => {
            const risk = rowRisk(row)
            return (
              <tr key={row.volume_id} className="border-t border-gray-100">
                <td className="px-3 py-2 align-top">
                  <div className="font-medium text-gray-800">第{row.volume_order}卷</div>
                  <div className="text-gray-500">{row.volume_title}</div>
                </td>
                <td className="px-3 py-2 align-top text-gray-700">
                  <div>{row.protagonist_realm_start || '—'}</div>
                  <div className="text-gray-400">→</div>
                  <div>{row.protagonist_realm_end || '—'}</div>
                </td>
                <td className="px-3 py-2 align-top text-gray-700">
                  <div>{row.boss_name || '—'}</div>
                  <div className="text-gray-500">{row.phase || '未标阶段'}</div>
                </td>
                <td className="px-3 py-2 align-top text-gray-700">
                  <div>{row.boss_realm || '—'}</div>
                  <div className="text-gray-500">
                    大境 {row.boss_major_rank ?? '—'} · 有效分 {row.boss_effective_score ?? '—'}
                  </div>
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="flex items-center gap-1 text-gray-700">
                    {trendIcon(row.boss_vs_prev_major)}
                    大境
                  </div>
                  <div className="flex items-center gap-1 text-gray-700 mt-1">
                    {trendIcon(row.boss_vs_prev_effective)}
                    小境
                  </div>
                </td>
                <td className="px-3 py-2 align-top font-semibold text-gray-700">
                  {deltaText(row.boss_vs_protagonist_end_delta)}
                </td>
                <td className="px-3 py-2 align-top">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] ${risk.cls}`}>{risk.label}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
