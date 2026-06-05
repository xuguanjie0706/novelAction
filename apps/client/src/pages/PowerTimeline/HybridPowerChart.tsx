/**
 * 折线 + 卷阶段泳道混合图：主角成长折线、Boss 折线、卷 phase 色带。
 */
import React, { useMemo } from 'react'
import clsx from 'clsx'

import type { PowerTimeline } from '../../types'
import {
  LABEL_W,
  VOL_W,
  HYBRID_H,
  PAD_TOP,
  PAD_BOTTOM,
  chartWidth,
  collectScoreExtent,
  formatPhase,
  phaseBarClass,
  detectPowerTimelineWarnings,
  pathFromPoints,
  realmTicks,
  splitProtagonistPathSegments,
  xSlotOffset,
  xVolumeCenter,
  yToPx,
} from './utils'

interface Props {
  data: PowerTimeline
}

export default function HybridPowerChart({ data }: Props) {
  const n = Math.max(1, data.volume_count || data.rows.length)
  const trackW = chartWidth(n)
  const innerH = HYBRID_H - PAD_TOP - PAD_BOTTOM
  const { min, max } = useMemo(() => collectScoreExtent(data), [data])

  const protagonistSegments = useMemo(
    () => splitProtagonistPathSegments(data.chart.protagonist),
    [data.chart.protagonist],
  )
  const dataWarnings = useMemo(() => detectPowerTimelineWarnings(data.rows), [data.rows])

  const bossPath = useMemo(() => {
    const pts = [...data.chart.boss].sort((a, b) => a.volume_order - b.volume_order)
    return pts
      .map((p, i) => {
        const x = xVolumeCenter(p.volume_order) + xSlotOffset('volume_boss')
        const y = yToPx(p.effective_score ?? p.major_rank, min, max, innerH)
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
      })
      .join(' ')
  }, [data.chart.boss, min, max, innerH])

  const ticks = realmTicks(data.realm_scale)

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-x-auto">
      <div className="px-3 py-2 border-b border-gray-100 text-xs font-semibold text-gray-700">
        折线 + 卷阶段泳道（主角 vs 卷 Boss）
      </div>
      {dataWarnings.length > 0 && (
        <div className="mx-2 mt-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-[10px] text-amber-900">
          <p className="font-semibold mb-1">卷骨架境界数据异常（需在大纲卷导演中修正或重生成卷骨架）</p>
          <ul className="list-disc pl-4 space-y-0.5">
            {dataWarnings.map(w => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="p-2 min-w-max">
        <div className="flex">
          <div style={{ width: LABEL_W }} className="shrink-0" />
          <div style={{ width: trackW }} className="flex border-b border-gray-100 pb-1 mb-1">
            {data.rows.map(row => (
              <div
                key={row.volume_id}
                style={{ width: VOL_W }}
                className={clsx('h-3 rounded-sm shrink-0', phaseBarClass(row.phase))}
                title={`第${row.volume_order}卷 · ${formatPhase(row.phase)}`}
              />
            ))}
          </div>
        </div>

        <div className="flex relative" style={{ height: HYBRID_H }}>
          <div
            className="shrink-0 text-[9px] text-gray-500 pr-2 flex flex-col justify-between py-1"
            style={{ width: LABEL_W, height: HYBRID_H }}
          >
            {[...ticks].reverse().map(t => (
              <span key={t.rank} className="truncate" title={t.name}>
                {t.name}
              </span>
            ))}
          </div>
          <svg width={trackW} height={HYBRID_H} className="overflow-visible">
            {ticks.map(t => {
              const y = yToPx(t.rank, min, max, innerH)
              return (
                <line
                  key={t.rank}
                  x1={0}
                  y1={y}
                  x2={trackW}
                  y2={y}
                  stroke="#e5e7eb"
                  strokeDasharray="4 3"
                />
              )
            })}
            {Array.from({ length: n }, (_, i) => {
              const x = i * VOL_W
              return (
                <line key={i} x1={x} y1={PAD_TOP} x2={x} y2={HYBRID_H - PAD_BOTTOM} stroke="#f3f4f6" />
              )
            })}
            {protagonistSegments.map((seg, si) => {
              const d = pathFromPoints(seg, min, max, innerH)
              if (!d) return null
              return (
                <path
                  key={`p-seg-${si}`}
                  d={d}
                  fill="none"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                />
              )
            })}
            {bossPath && (
              <path
                d={bossPath}
                fill="none"
                stroke="#dc2626"
                strokeWidth={2.5}
                strokeDasharray="6 4"
                strokeLinejoin="round"
              />
            )}
            {data.chart.protagonist.map((p, idx) => {
              const x = xVolumeCenter(p.volume_order) + xSlotOffset(p.point_kind)
              const y = yToPx(p.effective_score ?? p.major_rank, min, max, innerH)
              return (
                <circle
                  key={`p-${idx}`}
                  cx={x}
                  cy={y}
                  r={4}
                  className="fill-blue-600"
                >
                  <title>{`${p.realm_label} (${p.point_kind})`}</title>
                </circle>
              )
            })}
            {data.chart.boss.map((p, idx) => {
              const x = xVolumeCenter(p.volume_order) + xSlotOffset('volume_boss')
              const y = yToPx(p.effective_score ?? p.major_rank, min, max, innerH)
              return (
                <g key={`b-${idx}`}>
                  <circle cx={x} cy={y} r={4} className="fill-red-600">
                    <title>{`${p.boss_name}: ${p.realm_label}`}</title>
                  </circle>
                </g>
              )
            })}
          </svg>
        </div>

        <div className="flex mt-1">
          <div style={{ width: LABEL_W }} />
          <div style={{ width: trackW }} className="flex text-[9px] text-gray-500">
            {data.rows.map(row => (
              <div key={row.volume_id} className="flex-1 text-center truncate px-0.5">
                第{row.volume_order}卷
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-4 mt-2 text-[10px] text-gray-600 px-1">
          <span className="flex items-center gap-1">
            <span className="w-6 h-0.5 bg-blue-600 inline-block" /> 主角
          </span>
          <span className="flex items-center gap-1">
            <span className="w-6 h-0.5 bg-red-600 inline-block border-dashed" style={{ borderTop: '2px dashed' }} />{' '}
            卷 Boss
          </span>
        </div>
      </div>
    </div>
  )
}
