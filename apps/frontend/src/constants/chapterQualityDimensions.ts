/** 章节正文质检维度键名 → 中文展示（与后端 quality.py / 创作端 AIPanel 对齐） */
export const CHAPTER_QUALITY_DIMENSION_LABELS: Record<string, string> = {
  plot: '情节推进',
  character: '人物一致',
  setting_consistency: '设定一致',
  pacing: '节奏控制',
  hooks: '悬念钩子',
  outline_alignment: '大纲匹配度',
  face_slap_payoff: '打脸兑现',
  emotional_resonance: '情感共鸣',
  subscribe_intent: '追读意愿',
  craft_discipline: '反AI味',
  realm_check: '境界体系',
  readability: '可读性',
  storyline_progress: '故事线推进',
  storyline_beat_match: '节拍兑现',
  storyline_tension_fit: '张力曲线',
  storyline_screen_balance: '戏份均衡',
}

export function qualityDimensionLabel(key: string): string {
  return CHAPTER_QUALITY_DIMENSION_LABELS[key] ?? key
}
