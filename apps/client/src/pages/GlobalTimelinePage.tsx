/**
 * @file GlobalTimelinePage.tsx
 * @description 全局时间线横轴甘特：章序为 X 轴，卷/章节/故事线/势力/伏笔/承诺/境界分泳道展示。
 * 数据：GET /outline/story-timeline（只读聚合，无新表）。
 */

import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { GanttChart, Loader2 } from 'lucide-react'
import clsx from 'clsx'

import { outlineApi } from '../api/client'
import type { StoryTimeline, StoryTimelineBar } from '../types'

const LANE_STYLE: Record<string, { bar: string; chip: string }> = {
  volume: { bar: 'bg-blue-500/75', chip: 'bg-blue-100 text-blue-800' },
  chapter: { bar: 'bg-slate-500/70', chip: 'bg-slate-100 text-slate-700' },
  storyline: { bar: 'bg-emerald-500/75', chip: 'bg-emerald-100 text-emerald-800' },
  faction: { bar: 'bg-orange-500/75', chip: 'bg-orange-100 text-orange-800' },
  foreshadow: { bar: 'bg-amber-500/80', chip: 'bg-amber-100 text-amber-800' },
  promise: { bar: 'bg-pink-500/75', chip: 'bg-pink-100 text-pink-800' },
  realm: { bar: 'bg-violet-500/85', chip: 'bg-violet-100 text-violet-800' },
}

const CHAPTER_STATUS_BAR: Record<string, string> = {
  done: 'bg-emerald-500/80',
  reviewed: 'bg-teal-500/80',
  writing: 'bg-amber-500/80',
  draft: 'bg-slate-400/70',
  needs_review: 'bg-red-400/80',
}

const LABEL_W = 168
const ROW_H = 28
const CHAPTER_W = 14

function chapterTicks(max: number): number[] {
  if (max <= 1) return [1]
  const step = max <= 30 ? 1 : max <= 80 ? 5 : 10
  const ticks: number[] = []
  for (let i = 1; i <= max; i += step) ticks.push(i)
  if (ticks[ticks.length - 1] !== max) ticks.push(max)
  return ticks
}

function barStyle(bar: StoryTimelineBar): string {
  if (bar.lane === 'chapter' && bar.status && CHAPTER_STATUS_BAR[bar.status]) {
    return CHAPTER_STATUS_BAR[bar.status]
  }
  return LANE_STYLE[bar.lane]?.bar ?? 'bg-gray-400/70'
}

/** 单条甘特在横轴上的 left/width（百分比）。 */
function barGeom(bar: StoryTimelineBar, maxChapter: number) {
  const span = Math.max(1, maxChapter)
  const start = Math.max(1, Math.min(bar.start_chapter, span))
  const end = Math.max(start, Math.min(bar.end_chapter, span))
  const leftPct = ((start - 1) / span) * 100
  const widthPct = ((end - start + 1) / span) * 100
  return { leftPct, widthPct: Math.max(widthPct, 100 / span) }
}

export default function GlobalTimelinePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [data, setData] = useState<StoryTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hiddenLanes, setHiddenLanes] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    outlineApi
      .storyTimeline(projectId)
      .then(r => setData(r.data))
      .catch(() => setError('加载时间线失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  const visibleBars = useMemo(() => {
    if (!data) return []
    return data.bars.filter(b => !hiddenLanes.has(b.lane))
  }, [data, hiddenLanes])

  const barsByLane = useMemo(() => {
    const map = new Map<string, StoryTimelineBar[]>()
    for (const bar of visibleBars) {
      const list = map.get(bar.lane) ?? []
      list.push(bar)
      map.set(bar.lane, list)
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.start_chapter - b.start_chapter || a.label.localeCompare(b.label))
    }
    return map
  }, [visibleBars])

  const maxChapter = data?.max_chapter ?? 1
  const trackW = maxChapter * CHAPTER_W
  const ticks = chapterTicks(maxChapter)

  const toggleLane = (laneId: string) => {
    setHiddenLanes(prev => {
      const next = new Set(prev)
      if (next.has(laneId)) next.delete(laneId)
      else next.add(laneId)
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-gray-500 text-sm">
        <Loader2 size={18} className="animate-spin" />
        加载全局时间线…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-red-600">
        {error ?? '无数据'}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#FAF8F4]">
      <header className="shrink-0 border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2 text-gray-800 font-semibold text-sm">
          <GanttChart size={18} className="text-[#C4873A]" />
          全局时间线
        </div>
        <p className="text-xs text-gray-500 mt-1">
          横轴第 1–{maxChapter} 章 · 章纲 {data.chapter_plan_count} · 正文 {data.written_chapter_count}
        </p>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {data.lanes.map(lane => {
            const on = !hiddenLanes.has(lane.id)
            const style = LANE_STYLE[lane.id]?.chip ?? 'bg-gray-100 text-gray-700'
            return (
              <button
                key={lane.id}
                type="button"
                title={lane.description ?? undefined}
                onClick={() => toggleLane(lane.id)}
                className={clsx(
                  'text-[10px] px-2 py-0.5 rounded-full border transition-opacity',
                  on ? style : 'bg-gray-50 text-gray-400 border-gray-200 opacity-60',
                )}
              >
                {lane.label}
              </button>
            )
          })}
        </div>
      </header>

      {visibleBars.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
          暂无时间线条目，或已全部隐藏泳道
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-auto p-3">
          <div className="inline-block min-w-full border border-gray-200 rounded-lg bg-white shadow-sm">
            <div className="flex border-b border-gray-100 sticky top-0 z-10 bg-gray-50/95">
              <div
                className="shrink-0 text-[10px] text-gray-400 flex items-end pb-1 pl-2"
                style={{ width: LABEL_W }}
              >
                泳道
              </div>
              <div className="relative h-8" style={{ width: trackW }}>
                {ticks.map(t => (
                  <span
                    key={t}
                    className="absolute bottom-1 text-[9px] text-gray-500 -translate-x-1/2 tabular-nums"
                    style={{ left: (t - 0.5) * CHAPTER_W }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            {data.lanes
              .filter(l => !hiddenLanes.has(l.id) && (barsByLane.get(l.id)?.length ?? 0) > 0)
              .map(lane => (
                <section key={lane.id} className="border-b border-gray-50 last:border-b-0">
                  <div className="text-[10px] font-semibold text-gray-500 px-2 py-1 bg-gray-50/80">
                    {lane.label}
                  </div>
                  {(barsByLane.get(lane.id) ?? []).map(bar => {
                    const { leftPct, widthPct } = barGeom(bar, maxChapter)
                    return (
                      <div
                        key={bar.id}
                        className="flex items-center border-t border-gray-50/80 hover:bg-amber-50/30"
                        style={{ height: ROW_H }}
                        title={[bar.label, bar.detail, bar.status].filter(Boolean).join(' · ')}
                      >
                        <span
                          className="shrink-0 truncate text-[10px] text-gray-700 px-2 border-r border-gray-100"
                          style={{ width: LABEL_W }}
                        >
                          {bar.label}
                        </span>
                        <div className="relative h-full" style={{ width: trackW }}>
                          <div
                            className={clsx(
                              'absolute top-1.5 bottom-1.5 rounded-sm min-w-[4px]',
                              barStyle(bar),
                            )}
                            style={{
                              left: `${leftPct}%`,
                              width: `${widthPct}%`,
                            }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </section>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
