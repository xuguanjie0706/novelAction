/**
 * 全员境界泳道：横轴=卷序，纵轴=境界有效分，每人一行。
 */
import React, { useMemo, useState } from 'react'
import clsx from 'clsx'

import type { CharacterRealmLane, PowerTimeline } from '../../types'
import {
  LABEL_W,
  VOL_W,
  LANE_ROW_H,
  PAD_TOP,
  PAD_BOTTOM,
  chartWidth,
  collectScoreExtent,
  realmTicks,
  roleFill,
  xSlotOffset,
  xVolumeCenter,
  yToPx,
} from './utils'

interface Props {
  data: PowerTimeline
}

const TIER_FILTER = [
  { id: 'all', label: '全部' },
  { id: 'core', label: '核心' },
  { id: 'arc', label: '弧线' },
  { id: 'plot', label: '剧情' },
  { id: 'background', label: '背景' },
] as const

function laneHeight(laneCount: number): number {
  return PAD_TOP + PAD_BOTTOM + laneCount * LANE_ROW_H
}

export default function CharacterRealmLanesChart({ data }: Props) {
  const [tierFilter, setTierFilter] = useState<string>('all')
  const [hideEmpty, setHideEmpty] = useState(true)

  const lanes = useMemo(() => {
    let list = data.character_lanes
    if (tierFilter !== 'all') {
      list = list.filter(l => l.character_tier === tierFilter)
    }
    if (hideEmpty) {
      list = list.filter(l => l.segments.length > 0)
    }
    return list
  }, [data.character_lanes, tierFilter, hideEmpty])

  const n = Math.max(1, data.volume_count || data.rows.length)
  const trackW = chartWidth(n)
  const chartH = laneHeight(lanes.length)
  const innerH = chartH - PAD_TOP - PAD_BOTTOM
  const { min, max } = useMemo(() => collectScoreExtent(data), [data])
  const ticks = realmTicks(data.realm_scale)

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-x-auto">
      <div className="px-3 py-2 border-b border-gray-100 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-gray-700">全员境界泳道</span>
        <div className="flex flex-wrap gap-1">
          {TIER_FILTER.map(f => (
            <button
              key={f.id}
              type="button"
              onClick={() => setTierFilter(f.id)}
              className={clsx(
                'text-[10px] px-2 py-0.5 rounded-full border',
                tierFilter === f.id
                  ? 'bg-[#C4873A] text-white border-[#C4873A]'
                  : 'bg-gray-50 text-gray-600 border-gray-200',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="text-[10px] text-gray-500 flex items-center gap-1 ml-auto">
          <input type="checkbox" checked={hideEmpty} onChange={e => setHideEmpty(e.target.checked)} />
          仅显示有锚点
        </label>
      </div>

      {lanes.length === 0 ? (
        <div className="p-8 text-center text-sm text-gray-500">暂无人物境界锚点数据</div>
      ) : (
        <div className="p-2 min-w-max">
          <div className="flex relative" style={{ height: chartH }}>
            <div className="shrink-0" style={{ width: LABEL_W }}>
              <div style={{ height: PAD_TOP }} />
              {lanes.map(lane => (
                <LaneLabel key={laneKey(lane)} lane={lane} />
              ))}
              <div style={{ height: PAD_BOTTOM }} />
            </div>
            <svg width={trackW} height={chartH}>
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
              {Array.from({ length: n + 1 }, (_, i) => (
                <line
                  key={i}
                  x1={i * VOL_W}
                  y1={PAD_TOP}
                  x2={i * VOL_W}
                  y2={chartH - PAD_BOTTOM}
                  stroke="#f3f4f6"
                />
              ))}
              {lanes.map((lane, rowIdx) => (
                <LaneRow
                  key={laneKey(lane)}
                  lane={lane}
                  rowIdx={rowIdx}
                  min={min}
                  max={max}
                  innerH={innerH}
                />
              ))}
            </svg>
          </div>
          <div className="flex mt-1">
            <div style={{ width: LABEL_W }} />
            <div style={{ width: trackW }} className="flex text-[9px] text-gray-500">
              {data.rows.map(row => (
                <div key={row.volume_id} className="flex-1 text-center">
                  第{row.volume_order}卷
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function laneKey(lane: CharacterRealmLane): string {
  return lane.character_id ?? `name:${lane.display_name}`
}

function LaneLabel({ lane }: { lane: CharacterRealmLane }) {
  return (
    <div
      className="truncate text-[10px] text-gray-700 pr-2 flex items-center border-t border-gray-50"
      style={{ height: LANE_ROW_H }}
      title={`${lane.display_name} · ${lane.role} · ${lane.character_tier}`}
    >
      {lane.display_name}
    </div>
  )
}

function LaneRow({
  lane,
  rowIdx,
  min,
  max,
  innerH,
}: {
  lane: CharacterRealmLane
  rowIdx: number
  min: number
  max: number
  innerH: number
}) {
  const cy = PAD_TOP + rowIdx * LANE_ROW_H + LANE_ROW_H / 2
  const fill = roleFill(lane.role)

  return (
    <g>
      {lane.segments.map((seg, i) => {
        const x = xVolumeCenter(seg.volume_order) + xSlotOffset(seg.slot)
        const y = yToPx(seg.effective_score, min, max, innerH)
        const w = Math.min(VOL_W * 0.55, 48)
        const h = 10
        return (
          <g key={`${seg.volume_order}-${seg.slot}-${i}`}>
            <title>{`${lane.display_name} · 第${seg.volume_order}卷 · ${seg.realm_label} (${seg.slot})`}</title>
            <line x1={x} y1={cy} x2={x} y2={y} stroke="#d1d5db" strokeWidth={1} strokeDasharray="2 2" />
            <rect
              x={x - w / 2}
              y={y - h / 2}
              width={w}
              height={h}
              rx={3}
              fill={fill}
              opacity={0.88}
            />
            <text x={x} y={y - h / 2 - 2} textAnchor="middle" className="fill-gray-600 text-[7px]">
              {seg.realm_label.length > 8 ? `${seg.realm_label.slice(0, 7)}…` : seg.realm_label}
            </text>
          </g>
        )
      })}
    </g>
  )
}
