export interface ReviewProject {
  id: string
  title: string
}

export interface ReviewChapter {
  id: string
  title: string
  sort_order: number
  last_quality_score?: number | null
  last_quality_report?: QualityReport | null
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
  selected_chapter_count?: number
  selected_chapter_ids?: string[]
}

export interface CoherenceReportRecord {
  id: string
  name: string
  model_profile: ModelProfile
  selected_chapter_ids: string[]
  result: ChapterCoherenceResult
  created_at: string
}
