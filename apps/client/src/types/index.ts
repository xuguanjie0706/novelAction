// ── Project ──────────────────────────────────────────
export interface Project {
  id: string
  title: string
  genre?: string
  logline?: string
  world_overview?: string
  story_core?: Record<string, any>
  status: 'drafting' | 'writing' | 'completed'
  target_words?: string
  cover_url?: string
  created_at: string
  updated_at?: string
}

// ── World Setting ─────────────────────────────────────
export interface WorldSetting {
  id: string
  project_id: string
  category_id?: string
  title: string
  content?: string
  tags: string[]
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Character ─────────────────────────────────────────
export interface Character {
  id: string
  project_id: string
  name: string
  role: 'protagonist' | 'supporting' | 'antagonist'
  gender?: string
  age?: string
  faction?: string
  avatar_url?: string
  personality?: string
  background?: string
  motivation?: string
  arc?: string
  strengths: string[]
  weaknesses: string[]
  special_traits: string[]
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface CharacterRelationship {
  id: string
  project_id: string
  from_character_id: string
  to_character_id: string
  relation_type: string
  description?: string
  intensity: number
}

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
}

// ── Chapter ───────────────────────────────────────────
export interface Chapter {
  id: string
  project_id: string
  outline_node_id?: string
  title: string
  content: string
  word_count: number
  sort_order: number
  status: 'draft' | 'writing' | 'done' | 'reviewed'
  last_quality_score?: number
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

// ── Memory ────────────────────────────────────────────
export interface MemoryChunk {
  id: string
  project_id: string
  chapter_id?: string
  memory_type: 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict'
  title?: string
  content: string
  chapter_number?: number
  tags: string[]
  created_at: string
}

// ── Generation Queue ──────────────────────────────────
export type GenTaskStatus = 'pending' | 'running' | 'done' | 'error'
export type GenTaskType = 'full_generate' | 'batch_expand'

export interface GenProgressItem {
  step: number | string
  label: string
  done: boolean
  error: boolean
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
  /** full_generate: { scale_hint, model_profile, clear_existing }
   *  batch_expand:  { nodes: [{id,title}], chapterCount, modelProfile } */
  params: Record<string, any>
  createdAt: number
}

// ── AI ────────────────────────────────────────────────
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

/** GET /api/v1/llm/overview — 启用的远程线路列表（不含密钥） */
export interface RemoteProviderBrief {
  id: string
  name: string
  model_name: string
  is_default: boolean
}

/** GET /api/v1/llm/overview — 后端登记的远程智能体 / 本地模型摘要 */
export interface LlmOverview {
  local_model_name: string
  remote_ready: boolean
  effective_remote_model: string | null
  remote_agent: {
    id: string
    name: string
    model_name: string
    is_default?: boolean
  } | null
  remote_source: 'database' | 'env' | 'none'
  remote_providers: RemoteProviderBrief[]
}
