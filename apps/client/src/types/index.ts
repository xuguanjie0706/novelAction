// ── Project ──────────────────────────────────────────
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
  alias: string[]
  role: 'protagonist' | 'supporting' | 'antagonist' | 'neutral'
  gender?: string
  age?: string
  avatar_url?: string
  // 归属
  faction?: string
  faction_id?: string
  faction_rank?: string
  birthplace?: string
  // 外貌
  appearance?: string
  clothing_style?: string
  // 能力
  current_realm?: string
  power_system_id?: string
  realm_rank?: number
  // 性格
  personality?: string
  speech_style?: string
  values?: string
  // 背景
  background?: string
  secrets?: string
  trauma?: string
  // 动机成长
  motivation?: string
  fear?: string
  arc?: string
  arc_stages: any[]
  // 能力标签
  strengths: string[]
  weaknesses: string[]
  special_traits: string[]
  // 技能道具
  known_skills: any[]
  owned_items: any[]
  // 状态
  current_status: 'alive' | 'dead' | 'missing' | 'sealed' | 'transformed'
  current_location?: string
  author_notes?: string
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
  is_dynamic: string
  evolution_note?: string
}

// ── StoryLine ─────────────────────────────────────────
export interface StoryLine {
  id: string
  project_id: string
  name: string
  line_type: 'main' | 'sub' | 'romance' | 'growth' | 'mystery' | 'faction' | 'antagonist'
  description?: string
  status: 'planned' | 'active' | 'climax' | 'resolved' | 'dropped'
  start_chapter?: number
  end_chapter?: number
  related_character_ids: string[]
  key_beats: any[]
  core_conflict?: string
  resolution_direction?: string
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── PowerSystem ───────────────────────────────────────
export interface PowerLevel {
  rank: number
  name: string
  description?: string
  requirements?: string
  abilities?: string[]
  approximate_chapter?: string
  sub_level_count?: number   // 细分星级数，默认 9
}

export interface PowerSystem {
  id: string
  project_id: string
  name: string
  system_type: 'cultivation' | 'magic' | 'ability' | 'tech' | 'hybrid'
  description?: string
  levels: PowerLevel[]
  cultivation_method?: string
  breakthrough_condition?: string
  special_rules?: string
  protagonist_current_rank?: number
  protagonist_end_rank?: number
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Skill ─────────────────────────────────────────────
export interface Skill {
  id: string
  project_id: string
  power_system_id?: string
  name: string
  skill_type: 'combat' | 'defense' | 'movement' | 'support' | 'bloodline' | 'special'
  grade: 'mortal' | 'earth' | 'sky' | 'profound' | 'saint' | 'divine' | 'supreme'
  source?: string
  level_required?: string
  prerequisites?: string
  description?: string
  effects?: string
  limitations?: string
  mastery_stages: any[]
  mastered_by_character_ids: string[]
  first_appearance_chapter?: number
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Item ──────────────────────────────────────────────
export interface Item {
  id: string
  project_id: string
  name: string
  item_type: 'weapon' | 'armor' | 'pill' | 'artifact' | 'material' | 'scroll' | 'beast' | 'other'
  rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary' | 'mythic' | 'unique'
  description?: string
  origin?: string
  effects?: string
  limitations?: string
  current_owner_id?: string
  ownership_history: any[]
  story_significance?: string
  first_appearance_chapter?: number
  status: 'intact' | 'damaged' | 'destroyed' | 'lost' | 'unknown'
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
}

// ── Faction ───────────────────────────────────────────
export interface Faction {
  id: string
  project_id: string
  parent_faction_id?: string
  name: string
  faction_type: 'sect' | 'kingdom' | 'family' | 'guild' | 'evil' | 'race' | 'other'
  alignment: 'protagonist' | 'neutral' | 'antagonist' | 'unknown'
  description?: string
  territory?: string
  strength_level?: string
  member_count?: string
  top_power?: string
  leader_character_id?: string
  key_members: any[]
  goals?: string
  resources?: string
  rivals: string[]
  allies: string[]
  attitude_to_protagonist: string
  history?: string
  secrets?: string
  sort_order: number
  extra: Record<string, any>
  created_at: string
  updated_at?: string
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
export type GenTaskStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'
export type GenTaskType = 'full_generate' | 'batch_expand' | 'outline_quality' | 'outline_repair' | 'continue_chapters' | 'rewrite_chapter'

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
   *  outline_repair: { scope: all|volume|book, volume_node_id?, model_profile, llm_provider_id }
   *  continue_chapters: { chapterIds: string[], userPrompt, modelProfile, llm_provider_id }（单章时 chapterIds 可为 1 个）
   *  rewrite_chapter: { chapterId, userPrompt, modelProfile, llm_provider_id } */
  params: Record<string, any>
  createdAt: number
}

// ── Foreshadow ────────────────────────────────────────
export interface Foreshadow {
  id: string
  project_id: string
  code?: string
  title: string
  description?: string
  laid_chapter_id?: string
  laid_chapter_number?: number
  resolved_chapter_id?: string
  resolved_chapter_number?: number
  planned_resolve_chapter?: number
  planned_action?: 'resolve' | 'develop'
  status: 'open' | 'resolved' | 'dropped'
  priority: number   // 1–5
  created_at: string
  updated_at?: string
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
  chapter_id: string
  source_chapter_number: number
  issue_type: string
  severity: 'critical' | 'high' | 'medium' | 'low' | string
  status: 'pending' | 'resolved' | 'dismissed'
  summary: string
  suggested_fix?: string
  created_at: string
  updated_at?: string
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

export interface AiChatMessage {
  id: string
  project_id: string
  chapter_id?: string | null
  context_type: 'outline' | 'writing' | 'general'
  role: 'user' | 'assistant'
  content: string
  created_at: string
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
