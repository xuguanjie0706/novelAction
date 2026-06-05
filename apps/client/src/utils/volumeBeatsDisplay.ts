/**
 * 卷级导演单（Step 9 beat_highlights / volume_climax）展示与解析。
 */
import type { OutlineNode } from '../types'
import {
  chapterStartForVolume,
  formatVolumeChapterLabel,
  shiftPacingSkeletonDisplay,
} from './volumeChapterStarts'

export interface VolumeBeatHighlight {
  chapter_hint: number
  chapter_span?: string
  beat_type: string
  description: string
  payoff_of?: string
}

export interface VolumeClimaxBeat {
  chapter_hint?: number
  description?: string
}

export interface VolumeTurningPoint {
  chapter_hint?: number
  description?: string
}

export interface VolumeDirectorData {
  phase?: string
  plannedChapters?: number
  /** 本卷初主角境界（extra.protagonist_realm_start） */
  protagonistRealmStart?: string
  /** 本卷末主角境界（extra.protagonist_realm_end） */
  protagonistRealmEnd?: string
  /** 展示用区间，如「凝气境 → 筑基境」 */
  protagonistRealmRange: string
  volumeBoss?: string
  volumeBossRealm?: string
  beatHighlights: VolumeBeatHighlight[]
  volumeClimax?: VolumeClimaxBeat
  emotionalTurningPoint?: VolumeTurningPoint
  mustPayoffs: string[]
  pacingSkeleton: string
  /** 本卷末高潮摘要（highlight 列或 volume_climax.description） */
  climaxSummary: string
  /** 留给下一卷的悬念种子（hook 列） */
  nextVolumeHook: string
  /** 旧版数据：无 director 节拍时 hook 曾用作本卷追读悬念 */
  legacyReaderHook: string
  hasDirectorBeats: boolean
  /** 本卷第 1 章对应的全书章号（extra.chapter_start_global 或由全书卷列表推算） */
  chapterStartGlobal: number
  /** 节奏骨架展示文案（已换算全书章号，非编辑用原文） */
  pacingSkeletonDisplay: string
}

export function formatBeatChapterHint(local: number, chapterStartGlobal: number): string {
  return formatVolumeChapterLabel(local, chapterStartGlobal)
}

export const PHASE_LABEL: Record<string, string> = {
  opening: '开局期',
  rising: '起飞期',
  turning: '转折期',
  dark_hour: '至暗期',
  climax: '高潮期',
  ending: '收束期',
}

export const BEAT_TYPE_LABEL: Record<string, string> = {
  face_slap: '打脸/爽点',
  reveal: '揭秘',
  power_up: '实力跃迁',
  relationship_turn: '关系逆转',
  betrayal: '背叛/决裂',
  sacrifice: '牺牲/至暗',
  victory: '阶段性胜利',
  emotional_peak: '情感高点',
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
}

function asBeatList(raw: unknown): VolumeBeatHighlight[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((b): b is Record<string, unknown> => !!b && typeof b === 'object')
    .map(b => ({
      chapter_hint: Number(b.chapter_hint) || 0,
      chapter_span: b.chapter_span ? String(b.chapter_span) : undefined,
      beat_type: String(b.beat_type || 'face_slap'),
      description: String(b.description || ''),
      payoff_of: b.payoff_of ? String(b.payoff_of) : undefined,
    }))
    .filter(b => b.description.trim())
}

/** 主角本卷境界起止（与后端 format_volume_realm_anchor_line 语义一致）。 */
export function formatProtagonistRealmRange(start?: string, end?: string): string {
  const s = (start || '').trim()
  const e = (end || '').trim()
  if (s && e) return s === e ? s : `${s} → ${e}`
  if (e) return e
  if (s) return s
  return ''
}

/** 从 OutlineNode 解析卷级导演单展示数据。 */
export function parseVolumeDirector(
  vol: OutlineNode,
  options?: { allVolumes?: OutlineNode[] },
): VolumeDirectorData {
  const extra = vol.extra ?? {}
  const chapterStartGlobal = chapterStartForVolume(vol, options?.allVolumes)
  const beatHighlights = asBeatList(extra.beat_highlights)
  const volumeClimax = asRecord(extra.volume_climax) as VolumeClimaxBeat
  const climaxDesc = (
    (vol.highlight || '').trim()
    || String(volumeClimax.description || '').trim()
  )
  if (climaxDesc && !volumeClimax.description) {
    volumeClimax.description = climaxDesc
  }
  const turning = asRecord(extra.emotional_turning_point) as VolumeTurningPoint
  const mustPayoffs = Array.isArray(extra.must_payoff_before_vol_end)
    ? extra.must_payoff_before_vol_end.map(String).filter(s => s.trim())
    : []
  const pacingSkeleton = String(extra.pacing_skeleton || '').trim()
  const hasDirectorBeats = beatHighlights.length > 0
    || Boolean(climaxDesc)
    || Boolean(pacingSkeleton)

  const hook = (vol.hook || '').trim()
  const legacyReaderHook = !hasDirectorBeats && hook ? hook : ''

  const protagonistRealmStart = String(extra.protagonist_realm_start || '').trim() || undefined
  const protagonistRealmEnd = String(extra.protagonist_realm_end || '').trim() || undefined

  return {
    phase: (vol as OutlineNode & { phase?: string }).phase ?? extra.phase,
    plannedChapters: extra.planned_chapters,
    protagonistRealmStart,
    protagonistRealmEnd,
    protagonistRealmRange: formatProtagonistRealmRange(protagonistRealmStart, protagonistRealmEnd),
    volumeBoss: extra.volume_boss,
    volumeBossRealm: extra.volume_boss_realm,
    beatHighlights,
    volumeClimax: volumeClimax.description ? volumeClimax : undefined,
    emotionalTurningPoint: turning.description ? turning : undefined,
    mustPayoffs,
    pacingSkeleton,
    climaxSummary: climaxDesc,
    nextVolumeHook: hasDirectorBeats ? hook : '',
    legacyReaderHook,
    hasDirectorBeats,
    chapterStartGlobal,
    pacingSkeletonDisplay: shiftPacingSkeletonDisplay(pacingSkeleton, chapterStartGlobal),
  }
}

export function beatTypeLabel(type: string): string {
  return BEAT_TYPE_LABEL[type] ?? type
}
