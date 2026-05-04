export interface ReviewProject {
  id: string
  title: string
  /** 含 outline_quality 等（GET /projects/:id） */
  story_core?: Record<string, unknown> | null
}

/** 大纲 AI 质检（与章节正文 QualityReport 不同） */
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

export interface ReviewChapter {
  id: string
  project_id?: string
  outline_node_id?: string | null
  title: string
  content: string
  sort_order: number
  word_count?: number
  status?: string
  updated_at?: string | null
  last_quality_score?: number | null
  last_quality_report?: QualityReport | null
}

export interface ReviewMemoryChunk {
  id: string
  chapter_id?: string | null
  /** 与章节 sort_order+1 或业务章号一致，便于排序展示 */
  chapter_number?: number | null
  memory_type: 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict' | string
  title?: string
  content: string
  tags?: string[]
  created_at?: string
}

export interface ReviewChapterIndex {
  id: string
  chapter_id: string
  chapter_number: number
  story_day?: string
  core_events: Array<Record<string, unknown> | string>
  first_appearances: Array<Record<string, unknown>>
  actual_foreshadows_laid: Array<Record<string, unknown>>
  actual_foreshadows_resolved: Array<Record<string, unknown>>
  ending_hook?: string
  hook_strength?: number
  continuity_notes: Array<Record<string, unknown> | string>
  updated_at?: string
}

export interface ReviewForeshadow {
  id: string
  title: string
  description?: string
  status: 'open' | 'resolved' | 'dropped' | string
  laid_chapter_id?: string | null
  resolved_chapter_id?: string | null
  priority?: number
}

export type ModelProfile = 'local' | 'gemini'

export interface QualityDimensionResult {
  score: number
  status: 'excellent' | 'pass' | 'warning' | 'fail' | string
  comment: string
}

export interface QualityIssue {
  type: string
  description: string
}

export interface QualityReport {
  overall_score: number
  dimensions: Record<string, QualityDimensionResult>
  issues: QualityIssue[]
  suggestions: string[]
  summary: string
  error?: string
  raw_response?: string
}

export interface ChapterCoherenceResult {
  title_match_score: number
  continuity_score: number
  overall_score: number
  chapter_evaluations: Array<{
    chapter_id: string
    chapter_title: string
    title_match_score: number
    title_match_comment: string
    risk_level: string
  }>
  cross_chapter_issues: Array<{
    type: string
    severity: string
    description: string
  }>
  suggestions: string[]
  summary: string
  error?: string
  raw_response?: string
  selected_chapter_count?: number
  selected_chapter_ids?: string[]
}

/** 单次「根据评测改正文」写入结果中的一章 */
export interface CoherenceApplyChapterResult {
  chapter_id: string
  skipped: boolean
  word_count?: number
  reason?: string
}

/** 一次写入数据库产生的改正文记录（可多次，对应多次预览提交） */
export interface CoherenceApplyEventRecord {
  applied_at: string
  applied: CoherenceApplyChapterResult[]
}

export interface CoherenceReportRecord {
  id: string
  name: string
  model_profile: ModelProfile
  selected_chapter_ids: string[]
  result: ChapterCoherenceResult
  /** 本评测报告关联的改正文写入历史 */
  apply_events?: CoherenceApplyEventRecord[]
  created_at: string
}

export interface CoherenceApplyRevisionPreview {
  chapter_id: string
  chapter_title: string
  unchanged: boolean
  change_note: string
  revised_content: string
  previous_plain_preview: string
  revised_plain_preview: string
}

export interface CoherenceApplyPreviewResponse {
  report_id: string
  revisions: CoherenceApplyRevisionPreview[]
}
