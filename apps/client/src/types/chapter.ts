// ── Outline ───────────────────────────────────────────
export interface OutlineNode {
  id: string
  project_id: string
  parent_id?: string
  node_type: 'volume' | 'arc' | 'chapter_plan'
  title: string
  summary?: string
  hook?: string
  highlight?: string
  conflict?: string
  sort_order: number
  expected_words?: number
  reader_hook_score?: number
  extra: Record<string, any>
  children: OutlineNode[]
  created_at: string
  updated_at?: string
  // v2 新增字段
  storyline_ids?: string[]
  involved_character_ids?: string[]
  key_item_ids?: string[]
  key_skill_ids?: string[]
  emotional_tone?: string
  pacing?: string
  power_milestone?: string
  foreshadows_laid?: Array<{ id?: string; description: string }>
  foreshadows_resolved?: Array<{ id?: string; description: string }>
  phase?: string
  // P2 三层调度新增
  character_screen_time?: Record<string, number>
  pov_character_id?: string
}

// ── Quality ───────────────────────────────────────────
export interface QualityReport {
  overall_score: number
  dimensions: Record<string, {
    score: number
    status: 'excellent' | 'pass' | 'warning' | 'fail'
    comment: string
  }>
  issues: Array<{ type: string; description: string }>
  suggestions: string[]
  summary: string
}

// ── Chapter ───────────────────────────────────────────
export interface Chapter {
  id: string
  project_id: string
  outline_node_id?: string
  title: string
  content: string
  /** 最近一次 AI 返回的完整纯文本（含稿末索引），与 content 分离，用于「原文」对照 */
  manuscript_raw_snapshot?: string | null
  word_count: number
  sort_order: number
  status: 'draft' | 'writing' | 'done' | 'reviewed'
  last_quality_score?: number
  last_quality_report?: QualityReport
  quality_checked_at?: string
  created_at: string
  updated_at?: string
}

export interface ChapterVersion {
  id: string
  chapter_id: string
  word_count?: number
  note?: string
  is_auto: boolean
  created_at: string
}

export interface ChapterVersionDetail extends ChapterVersion {
  content: string
}

// ── ChapterIndex ──────────────────────────────────────
export interface ChapterIndex {
  id: string
  project_id: string
  chapter_id: string
  chapter_number: number
  story_day?: string
  core_events: Array<Record<string, unknown> | string>
  first_appearances: Array<Record<string, unknown>>
  actual_foreshadows_laid: Array<Record<string, unknown>>
  actual_foreshadows_resolved: Array<Record<string, unknown>>
  ending_hook?: string
  hook_strength: number
  continuity_notes: Array<Record<string, unknown> | string>
  created_at: string
  updated_at?: string
}

// ── Quality Debt ──────────────────────────────────────
export interface QualityDebt {
  id: string
  project_id: string
  /** 删章或归档后可能为空，仍可用 source_chapter_number 定位 */
  chapter_id?: string | null
  source_chapter_number: number
  issue_type: string
  severity: 'critical' | 'high' | 'medium' | 'low' | string
  status: 'pending' | 'resolved' | 'dismissed'
  summary: string
  suggested_fix?: string
  /** 作者手动记录的修复说明，会一并注入定向 AI 修复提示词 */
  author_notes?: string
  created_at: string
  updated_at?: string
}

// ── CharacterChangeLog ────────────────────────────────
export interface ChangeItem {
  field:  string
  label:  string
  before: string | null
  after:  string | null
}

export interface CharacterChangeLog {
  id:             string
  project_id:     string
  character_id:   string
  character_name: string
  chapter_id:     string | null
  chapter_number: string | null
  chapter_title:  string | null
  source:         'debrief' | 'manual' | 'bootstrap'
  summary:        string | null
  changes:        ChangeItem[]
  created_at:     string
}
