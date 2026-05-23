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
  /** JSONB 杂物字段；已知键：positioning / writing_config / opening_contract / consistency_issues */
  extra?: Record<string, any>
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
  /** 叙事层级：core=核心长线 / arc=弧线支柱 / plot=剧情推手 / background=背景填充 */
  character_tier: 'core' | 'arc' | 'plot' | 'background'
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
  /** 结构化语风指纹（P2 新增） */
  speech_kit?: {
    signature_words?: string[]
    sentence_length_pref?: string
    taboo_words?: string[]
    sample_dialogues?: string[]
    inner_monologue_style?: string
    recent_evolution_notes?: Array<{ chapter_id: string; chapter_title: string; note: string }>
  }
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
  // P2 三层调度新增
  character_screen_time?: Record<string, number>   // { character_id: 百分比 }
  pov_character_id?: string
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
  /** AI 提取时赋值 0.0-1.0；检索时与时效衰减共同加权排序 */
  importance_score: number
  /** 被 RAG 召回的累计次数 */
  access_count: number
  /** 最近一次被召回时间（ISO 格式） */
  last_accessed_at?: string | null
  created_at: string
}

/** 单条记忆冲突描述（与后端 MemoryConflictItem 对齐） */
export interface MemoryConflictItem {
  /** character_state | timeline | attribute | foreshadow */
  conflict_type: string
  /** high | medium | low */
  severity: 'high' | 'medium' | 'low'
  description: string
  chunk_ids: string[]
  chapter_refs: number[]
}

/** 记忆冲突检测报告（与后端 detect_memory_conflicts 返回值对齐） */
export interface MemoryConflictReport {
  total_chunks_scanned: number
  conflicts: MemoryConflictItem[]
  detected_at: string
  error?: string
}

/** 单条 RAG 语义命中（与后端 RagSearchHitOut 对齐） */
export interface RagSearchHit {
  rank: number
  memory_id: string
  score?: number | null
  retrieval_source: 'semantic' | 'recency_anchor' | 'recency_fallback'
  memory_type: string
  title?: string | null
  content: string
  content_preview: string
  chapter_number?: number | null
  tags: string[]
}

/** POST /memory/rag-query 结构化响应 */
export interface RagQueryResponse {
  log_id: string
  query: string
  params: Record<string, unknown>
  status: string
  duration_ms: number
  hits: RagSearchHit[]
  memory_summary: string
  answer_hint: string
}

/** 持久化 RAG 调用日志 */
export interface RagRetrievalLog {
  id: string
  project_id: string
  chapter_id?: string | null
  source: string
  status: string
  duration_ms: number
  input_payload: Record<string, unknown>
  output_payload: Record<string, unknown>
  created_at: string
}

// ── Generation Queue ──────────────────────────────────
export type GenTaskStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'
export type GenTaskType = 'full_generate' | 'batch_expand' | 'outline_quality' | 'outline_repair' | 'continue_chapters' | 'rewrite_chapter' | 'gated_rewrite_chapter'

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

/** GET /api/v1/cover/image-providers — 图片生成提供者 */
export interface ImageProviderBrief {
  id: string
  name: string
  model_name: string
}

/** POST /api/v1/projects/{id}/cover/generate 请求 */
export interface CoverGenerateIn {
  llm_provider_id: string
  prompt: string
  size?: string
  quality?: string
  /** 默认 true：服务端压缩 WebP 落盘并返回 cover_url */
  store_compressed?: boolean
}

/** POST /api/v1/projects/{id}/cover/generate 响应 */
export interface CoverGenerateOut {
  /** 压缩落盘后的站内路径（默认 store_compressed=true） */
  cover_url?: string
  data_url?: string   // data:image/png;base64,…
  image_url?: string  // 部分 provider 直接返回外链
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

// ── 全局时间线甘特 ───────────────────────────────────────────

export interface StoryTimelineLane {
  id: string
  label: string
  description?: string | null
}

export interface StoryTimelineBar {
  id: string
  lane: string
  label: string
  start_chapter: number
  end_chapter: number
  status?: string | null
  detail?: string | null
}

export interface StoryTimeline {
  max_chapter: number
  chapter_plan_count: number
  written_chapter_count: number
  lanes: StoryTimelineLane[]
  bars: StoryTimelineBar[]
}

// ── 节奏地图：追读模拟 / 钩子检测 / 故事线悬空 ──────────────
export interface ReaderSimulationResult {
  chapter_id: string
  chapter_title: string
  chapter_number: number
  will_continue: boolean
  /** 追读意愿分 1-10 */
  score: number
  drop_risk: 'low' | 'medium' | 'high'
  what_hooked: string
  what_repelled: string
  verdict: string
  hook_tail: string
}

export interface HookMatchedPromise {
  promise_id: string
  promise_text: string
  promise_type: string
  status: string
}

export interface HookCheckResult {
  chapter_id: string
  chapter_title: string
  hook_text: string
  hook_type: 'cliffhanger' | 'curiosity' | 'promise' | 'emotional' | 'revelation' | 'weak' | 'none'
  hook_strength: number
  matched_promises: HookMatchedPromise[]
  analysis: string
  suggestions: string[]
}

export interface StorylineGapItem {
  storyline_id: string
  storyline_name: string
  line_type: string
  status: string
  last_seen_chapter_number: number | null
  current_max_chapter: number
  gap_size: number
  severity: 'warning' | 'critical'
}

export interface StorylineGapsResult {
  gaps: StorylineGapItem[]
  total_chapters: number
  checked_storylines: number
}

/** 章节综合分析结果（单次 AI 调用，内部用于写库，不直接展示给用户）*/
export interface ChapterAnalysisResult {
  simulation: ReaderSimulationResult
  hook: HookCheckResult
}

// ── Dashboard 首页聚合 ─────────────────────────────────
/** 七天柱状图单项 */
export interface DashboardWeekDay {
  /** YYYY-MM-DD（服务器时区） */
  date: string
  /** 周一 = 一，周日 = 日 */
  weekday_label: string
  /** 该日 ChapterVersion 增量字数总和 */
  words: number
  /** 柱高（像素，4-78），最大值映射到 78 */
  height: number
}

/** 「最近编辑」单项；项目对象用于跳转 */
export interface DashboardRecentChapter {
  id: string
  title: string
  word_count: number
  sort_order: number
  /** 「第 N 章 标题」展示串 */
  chapter_label: string
  /** ISO 时间字符串 */
  updated_at: string | null
  project: Project
}

/** GET /api/v1/dashboard/home 返回结构 */
export interface DashboardHome {
  /** 问候语姓名（username 优先，回退邮箱前缀，再回退「写作者」） */
  greeting_name: string
  /** 跨项目章节字数总和 */
  total_words: number
  today_words: number
  streak_days: number
  /** 最近 7 天里有写作的天数 */
  writing_days: number
  /** 最近 7 天总字数 / writing_days，向下取整 */
  average_words: number
  /** 7 项，从 7 天前到今天 */
  week: DashboardWeekDay[]
  /** 最近编辑的章节，最多 5 条 */
  recent_chapters: DashboardRecentChapter[]
}

/**
 * 章节分析均值统计——汇总该章所有历史分析记录的结果。
 *
 * 由 POST /ai/chapter-analysis（每次分析后）和
 * GET /ai/chapter-analysis-stats（页面加载批量拉取）返回。
 *
 * avg_score / avg_hook_strength 为浮点数，展示时保留一位小数。
 * 定性字段（verdict、what_hooked 等）取最近一次分析。
 */
// ── Scene（三层调度：章纲 → 分场 → 正文） ──────────────────

/** 节奏标记 */
export type ScenePacing = 'fast' | 'mid' | 'slow'

/** 分场状态 */
export type SceneStatus = 'planned' | 'written' | 'reviewed'

/**
 * 分场（Scene）——章节的子结构单元。
 * 对应后端 SceneRead schema；由 Bootstrap Step 13 或手动生成。
 * outline_node_id 指向所属 chapter_plan 大纲节点。
 */
// ── 场景投料约束类型（chapter_ingredients 服务生成，分场规划时写入）────

export interface SceneStorylineMove {
  storyline_id: string
  name: string
  line_type: string
  must_advance: boolean
  gap_chapters: number
  suggested_beat?: string
}

export interface SceneDebtFlag {
  debt_type: 'payoff' | 'storyline_gap' | 'promise_due' | 'emotion_debt' | string
  description: string
  severity: 'critical' | 'warning' | 'info'
  overdue_chapters: number
  related_id?: string
}

export interface SceneForeshadowOp {
  foreshadow_id: string
  title: string
  op: 'lay' | 'hint' | 'resolve'
  priority: number
  suggested_method: string
  is_overdue: boolean
}

export interface SceneFactionColor {
  faction_id: string
  name: string
  faction_type: string
  alignment: string
  atmosphere: string
  npc_default_attitude: string
}

export interface SceneAssetCard {
  asset_type: 'skill' | 'item'
  asset_id: string
  name: string
  description: string
  key_effect: string
  cost_or_rarity?: string
}

export interface SceneStructuralWarning {
  code: string
  level: 'warn' | 'info'
  msg: string
}

export interface SceneChecklistResult {
  storyline_ok: boolean
  foreshadow_ok: boolean
  debt_cleared: boolean
  score: number
  notes: string
}

export interface Scene {
  id: string
  project_id: string
  outline_node_id: string | null
  chapter_id: string | null
  order: number
  title: string | null
  time: string | null
  story_day: string | null
  /** 关联 Location 库记录的 UUID；存在时写章会注入感官基准约束块 */
  location_id: string | null
  location_name: string | null
  pov_character_id: string | null
  /** 在场人物 ID 列表 */
  characters_on_stage: string[]
  goal: string | null
  conflict: string | null
  turn: string | null
  hook: string | null
  hook_strength: number
  word_budget: number
  /** 实际已写字数（后端 scene_draft/stream 写完后更新） */
  actual_word_count: number
  pacing: ScenePacing
  sensory_focus: string
  status: SceneStatus
  content: string | null
  extra: Record<string, unknown>
  // ── 投料约束字段（分场规划时由 chapter_ingredients 服务写入）────
  storyline_moves: SceneStorylineMove[] | null
  debt_flags: SceneDebtFlag[] | null
  foreshadow_ops: SceneForeshadowOp[] | null
  faction_color: SceneFactionColor | null
  asset_spotlight: SceneAssetCard[] | null
  structural_warnings: SceneStructuralWarning[] | null
  /** 写后核验结果（stitch 后异步回填） */
  checklist_result: SceneChecklistResult | null
}

export interface ChapterAnalysisStats {
  chapter_id: string
  run_count: number
  /** 追读意愿均值（1-10，float） */
  avg_score: number
  /** 钩子强度均值（1-5，float） */
  avg_hook_strength: number
  /** 由 avg_score 推导：>=7 low / >=5 medium / else high */
  drop_risk: 'low' | 'medium' | 'high'
  will_continue: boolean
  // ── 最新一次分析的定性字段 ──
  what_hooked: string
  what_repelled: string
  verdict: string
  hook_type: 'cliffhanger' | 'curiosity' | 'promise' | 'emotional' | 'revelation' | 'weak' | 'none'
  hook_analysis: string
  hook_suggestions: string[]
  matched_promises: HookMatchedPromise[]
  hook_tail: string
  /** 最近一次分析的 ISO 时间戳 */
  latest_at: string
}

// ── Location（空间连续性机制） ────────────────────────────

/** 危险等级 */
export type LocationDangerLevel = 'safe' | 'neutral' | 'dangerous' | 'forbidden'

/** 地点类型 */
export type LocationType =
  | 'indoor'
  | 'outdoor'
  | 'ruins'
  | 'battlefield'
  | 'wilderness'
  | 'sacred_ground'
  | 'city'
  | 'dungeon'
  | 'void'

/** 地点状态 */
export type LocationStatus = 'active' | 'destroyed' | 'occupied' | 'abandoned' | 'sealed'

/**
 * 地点（Location）— 空间连续性管理的核心单元。
 *
 * sensory_signature 是防漂移的核心字段：固定感官描述（1-3句），
 * 写章时注入 prompt 作为硬约束，防止 AI 在同一地点产生矛盾感官描写。
 *
 * 与 Character.current_location（文本）和 Scene.location_id（UUID FK）双向关联。
 */
export interface Location {
  id: string
  project_id: string
  name: string
  aliases?: string[]
  location_type?: LocationType
  parent_location_id?: string | null
  danger_level?: LocationDangerLevel
  controller?: string | null
  /** 固定感官基准（1-3句），写章时注入硬约束防止感知漂移 */
  sensory_signature?: string | null
  description?: string | null
  status?: LocationStatus
  sort_order?: number
  extra?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

// ── ReaderPromise（读者承诺台账） ────────────────────────

/** 承诺类型：章末悬念 / 卷末钩子 / 名字暗示 / 章评共识 / 主角宣言 */
export type PromiseType =
  | 'chapter_ending'
  | 'volume_ending'
  | 'name_implication'
  | 'chapter_comment_consensus'
  | 'protagonist_claim'

/** 兑现状态 */
export type PromiseStatus = 'open' | 'fulfilled' | 'broken'

/**
 * 读者承诺——章末/卷末对读者的显式或隐式承诺记录。
 * Bootstrap Step 12 自动生成种子；后续可手动创建/维护。
 * status 随写章进展由 open → fulfilled / broken 更新。
 */
export interface ReaderPromise {
  id: string
  project_id: string
  promise_text: string
  promise_type: PromiseType
  source_chapter_id: string | null
  source_chapter_number: number | null
  expected_chapter_window: number | null
  expected_volume: number | null
  /** 优先级 1-5，核心承诺权重高 */
  priority: number
  /** 读者感知度 0-5，0=隐性埋伏 5=明显承诺 */
  audience_aware: number
  status: PromiseStatus
  fulfilled_chapter_id: string | null
  fulfilled_chapter_number: number | null
  created_at: string
  updated_at: string
}
