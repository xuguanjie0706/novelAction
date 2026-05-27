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
] as const

export const CHECK_LABELS: Record<string, string> = {
  plot: '情节推进',
  character: '人物一致',
  setting_consistency: '设定一致',
  pacing: '节奏控制',
  hooks: '悬念钩子',
  outline_alignment: '大纲匹配度',
  face_slap_payoff: '打脸兑现',
  emotional_resonance: '情感共鸣',
  subscribe_intent: '追读意愿',
}

export const SCORE_COLORS = [
  { min: 85, color: 'green', text: '优秀' },
  { min: 70, color: 'blue', text: '通过' },
  { min: 50, color: 'orange', text: '警告' },
  { min: 0, color: 'red', text: '高风险' },
] as const
