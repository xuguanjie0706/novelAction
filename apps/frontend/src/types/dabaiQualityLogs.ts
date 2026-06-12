export interface DabaiQualityLogRecord {
  id: string
  project_id: string
  chapter_id: string
  chapter_number?: number | null
  source: string
  status?: string | null
  overall_score?: number | null
  content_word_count?: number | null
  content_head_preview?: string
  continuity_score?: number | null
  continuity_issue?: string
  opening_continues_prev_tail?: boolean | null
  location_bridge_needed?: boolean | null
  prev_outline_location?: string | null
  curr_outline_location?: string | null
  created_at: string
  report?: Record<string, unknown>
  project_title?: string
  chapter_title?: string
}
