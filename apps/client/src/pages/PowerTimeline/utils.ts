/** 战力时间轴图表布局与配色工具。 */
import type { PowerTimeline, RealmScaleLevel } from '../../types'

export const LABEL_W = 132
export const VOL_W = 72
export const HYBRID_H = 300
export const LANE_ROW_H = 30
export const PAD_TOP = 28
export const PAD_BOTTOM = 36

const PHASE_COLOR: Record<string, string> = {
  opening: 'bg-sky-400/70',
  rising: 'bg-emerald-400/70',
  turning: 'bg-amber-400/70',
  dark_hour: 'bg-indigo-400/55',
  climax: 'bg-red-400/75',
  ending: 'bg-violet-400/65',
}

const ROLE_FILL: Record<string, string> = {
  protagonist: '#3b82f6',
  antagonist: '#ef4444',
  supporting: '#94a3b8',
  neutral: '#9ca3af',
}

export function phaseBarClass(phase: string): string {
  return PHASE_COLOR[phase] ?? 'bg-gray-300/70'
}

export function roleFill(role: string): string {
  return ROLE_FILL[role] ?? ROLE_FILL.supporting
}

export function chartWidth(volumeCount: number): number {
  return Math.max(1, volumeCount) * VOL_W
}

export function collectScoreExtent(data: PowerTimeline): { min: number; max: number } {
  const scores: number[] = []
  for (const lvl of data.realm_scale) {
    scores.push(lvl.rank)
  }
  const push = (v?: number | null) => {
    if (v != null && !Number.isNaN(v)) scores.push(v)
  }
  for (const p of [...data.chart.protagonist, ...data.chart.boss]) {
    push(p.effective_score ?? p.major_rank)
  }
  for (const lane of data.character_lanes) {
    for (const s of lane.segments) {
      push(s.effective_score)
    }
  }
  if (!scores.length) return { min: 0, max: 5 }
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  return { min: Math.max(0, min - 0.35), max: max + 0.35 }
}

export function yToPx(score: number, min: number, max: number, innerH: number): number {
  const span = Math.max(0.01, max - min)
  const t = (score - min) / span
  return PAD_TOP + (1 - t) * innerH
}

export function xVolumeCenter(vol: number): number {
  return (vol - 0.5) * VOL_W
}

/** 同卷内按 slot 水平偏移，避免点重叠。 */
export function xSlotOffset(slot: string): number {
  if (slot.includes('start') || slot === 'debut') return -VOL_W * 0.22
  if (slot.includes('end') || slot === 'climax' || slot === 'volume_boss' || slot === 'peak') return VOL_W * 0.22
  return 0
}

export function formatPhase(phase: string): string {
  const map: Record<string, string> = {
    opening: '开局',
    rising: '起飞',
    turning: '转折',
    dark_hour: '至暗',
    climax: '高潮',
    ending: '收束',
  }
  return map[phase] ?? phase || '—'
}

export function realmTicks(scale: RealmScaleLevel[]): RealmScaleLevel[] {
  return [...scale].sort((a, b) => a.rank - b.rank)
}
