import { CHAPTER_QUALITY_DIMENSION_LABELS } from '../../constants/chapterQualityDimensions'

/** 单章 / 连贯性评测维度键名 */
export const CHECK_TYPES = [
  'plot',
  'character',
  'setting_consistency',
  'pacing',
  'hooks',
  'outline_alignment',
  'face_slap_payoff',
  'emotional_resonance',
  'subscribe_intent',
  'craft_discipline',
  'realm_check',
  'readability',
] as const

export const CHECK_LABELS: Record<string, string> = {
  ...CHAPTER_QUALITY_DIMENSION_LABELS,
  craft_discipline: '反AI味(视角/铺垫/设定)',
}

export const SCORE_COLORS = [
  { min: 85, color: 'green', text: '优秀' },
  { min: 70, color: 'blue', text: '通过' },
  { min: 50, color: 'orange', text: '警告' },
  { min: 0, color: 'red', text: '高风险' },
] as const
