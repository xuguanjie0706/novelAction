// ── Generation Queue ──────────────────────────────────
export type GenTaskStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'
export type GenTaskType =
  | 'full_generate'
  | 'batch_expand'
  | 'outline_quality'
  | 'outline_repair'
  | 'continue_chapters'
  | 'rewrite_chapter'
  | 'gated_rewrite_chapter'

/** 大纲 AI 质检（与章节正文质检 QualityReport 结构不同） */
export interface OutlinePlanQualityIssue {
  severity?: string
  type?: string
  chapter_numbers?: number[]
  description?: string
  suggested_patch?: {
    chapter_number?: number
    field?: string
    replacement?: string
  }
}

export interface OutlinePlanQualityReport {
  scope?: string
  overall_score?: number
  status?: string
  summary?: string
  issues?: OutlinePlanQualityIssue[]
  must_fix_chapter_numbers?: number[]
  strengths?: string[]
  error?: string
}

export interface GenProgressItem {
  step: number | string
  label: string
  done: boolean
  error: boolean
  /** 上下文截断等非致命警告 */
  warning?: boolean
  /** 截断详情列表，warning=true 时可能存在 */
  warningDetails?: string[]
  /** 与 step 组合区分同日进度行（如大纲质检 vs 展开进度） */
  progressKey?: string
  outlineQualityReport?: OutlinePlanQualityReport | null
  outlineQualityScope?: 'volume' | 'book'
}

export interface GenTask {
  id: string
  type: GenTaskType
  projectId: string
  label: string
  status: GenTaskStatus
  progress: GenProgressItem[]
  completedMsg?: string
  errorMsg?: string
  /** full_generate: { scale_hint: micro|auto|short|medium|long|epic, model_profile, clear_existing }
   *  batch_expand:  { nodes: [{id,title}], chapterCount, modelProfile }
   *  outline_quality: { scope: all|volume|book, volume_node_id?, model_profile, llm_provider_id }
   *  outline_repair: { scope, volume_node_id?, model_profile, llm_provider_id,
   *    continuous_repair?, continuous_max_rounds?, continuous_min_score?（0–100，与质检总分同刻度） }
   *  continue_chapters: { chapterIds: string[], userPrompt, modelProfile, llm_provider_id }（单章时 chapterIds 可为 1 个）
   *  rewrite_chapter: { chapterId, userPrompt, modelProfile, llm_provider_id } */
  params: Record<string, any>
  createdAt: number
}
