import type { WorldSetting } from '../types'

export interface PremiseCore {
  core_concept: string
  genre_position: string
  protagonist_drive: string
  core_conflict: string
  reader_hook: string
  emotional_tone: string
  boundaries: string
  ending_direction: string
}

export interface SettingFocus {
  summary: string
  story_function: string
  conflict_seed: string
  cost_or_risk: string
  affected_people: string
  exception_or_loophole: string
  visual_anchor: string
}

type SettingLike = Pick<WorldSetting, 'title' | 'content' | 'extra'>

const PREMISE_KEYS: Array<keyof PremiseCore> = [
  'core_concept',
  'genre_position',
  'protagonist_drive',
  'core_conflict',
  'reader_hook',
  'emotional_tone',
  'boundaries',
  'ending_direction',
]

const FOCUS_KEYS: Array<keyof SettingFocus> = [
  'summary',
  'story_function',
  'conflict_seed',
  'cost_or_risk',
  'affected_people',
  'exception_or_loophole',
  'visual_anchor',
]

function readString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function compact(text: string, limit: number): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit)}...`
}

export function getPremiseCoreFromExtra(extra: Record<string, any> | undefined): PremiseCore {
  const raw = extra?.core && typeof extra.core === 'object' ? extra.core : {}
  return PREMISE_KEYS.reduce((core, key) => ({ ...core, [key]: readString(raw[key]) }), {} as PremiseCore)
}

export function getSettingFocusFromExtra(extra: Record<string, any> | undefined): SettingFocus {
  const raw = extra?.focus && typeof extra.focus === 'object' ? extra.focus : {}
  return FOCUS_KEYS.reduce((focus, key) => ({ ...focus, [key]: readString(raw[key]) }), {} as SettingFocus)
}

export function hasPremiseCore(core: PremiseCore): boolean {
  return PREMISE_KEYS.some(key => core[key].trim().length > 0)
}

export function hasSettingFocus(focus: SettingFocus): boolean {
  return FOCUS_KEYS.some(key => focus[key].trim().length > 0)
}

export function getSettingPreview(setting: SettingLike, limit = 42): string {
  const core = getPremiseCoreFromExtra(setting.extra)
  if (core.core_concept.trim()) return compact(core.core_concept, limit)
  if (core.core_conflict.trim()) return compact(core.core_conflict, limit)

  const focus = getSettingFocusFromExtra(setting.extra)
  if (focus.summary.trim()) return compact(focus.summary, limit)
  if (focus.story_function.trim()) return compact(focus.story_function, limit)

  return compact(setting.content ?? '', limit)
}
