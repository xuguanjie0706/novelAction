import type { WritingConfig } from '../api/client'

/**
 * 是否应走 `/ai/gated-draft-stream`（写前预警 + 质检循环重写）。
 * 与 ChapterEditor、GenerationQueuePanel 路由判断保持一致。
 */
export function shouldUseGatedDraft(cfg: WritingConfig | null | undefined): boolean {
  if (!cfg) return false
  if (cfg.pre_write_warning_enabled) return true
  return (
    cfg.auto_quality_gate === true &&
    (cfg.min_overall_score > 0 || cfg.min_subscribe_intent > 0)
  )
}

/** 章节是否已有可识别的叙事正文（去掉 HTML 标签后非空）。 */
export function chapterHasNarrativeBody(content: string | null | undefined): boolean {
  if (!content?.trim()) return false
  const text = content.replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ').trim()
  return text.length > 0
}
