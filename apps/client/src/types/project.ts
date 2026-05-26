// ── Project ───────────────────────────────────────────
export interface Project {
  id: string
  title: string
  genre?: string
  logline?: string
  premise?: string
  world_overview?: string
  story_core?: Record<string, any>
  status: 'drafting' | 'writing' | 'completed'
  target_words?: number
  cover_url?: string
  created_at: string
  updated_at?: string
  /** JSONB 杂物字段；已知键：positioning / writing_config / opening_contract / consistency_issues */
  extra?: Record<string, any>
}
