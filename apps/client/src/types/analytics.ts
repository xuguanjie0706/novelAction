import type { Project } from './project'

// ── 全局时间线甘特 ────────────────────────────────────
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

export interface PowerTimelineRow {
  volume_order: number
  volume_id: string
  volume_title: string
  phase: string
  protagonist_realm_start?: string | null
  protagonist_rank_start?: number | null
  protagonist_realm_end?: string | null
  protagonist_rank_end?: number | null
  boss_name?: string | null
  boss_character_id?: string | null
  boss_realm?: string | null
  boss_major_rank?: number | null
  boss_effective_score?: number | null
  boss_vs_prev_major: 'first' | 'up' | 'equal' | 'down' | string
  boss_vs_prev_effective: 'first' | 'up' | 'equal' | 'down' | string
  boss_vs_protagonist_end_delta?: number | null
}

export interface RealmScaleLevel {
  rank: number
  name: string
}

export interface PowerTimelinePoint {
  volume_order: number
  realm_label: string
  major_rank: number
  effective_score?: number | null
  point_kind: string
  phase?: string
  boss_name?: string | null
}

export interface PowerTimelineChart {
  protagonist: PowerTimelinePoint[]
  boss: PowerTimelinePoint[]
}

export interface CharacterRealmSegment {
  volume_order: number
  realm_label: string
  major_rank: number
  effective_score: number
  slot: string
}

export interface CharacterRealmLane {
  character_id?: string | null
  display_name: string
  role: string
  character_tier: string
  segments: CharacterRealmSegment[]
}

export interface PowerTimeline {
  updated_at?: string | null
  rows: PowerTimelineRow[]
  realm_scale: RealmScaleLevel[]
  chart: PowerTimelineChart
  character_lanes: CharacterRealmLane[]
  volume_count: number
}

// ── 节奏地图：追读模拟 / 钩子检测 / 故事线悬空 ──────────
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

/**
 * 章节分析均值统计——汇总该章所有历史分析记录的结果。
 *
 * 由 POST /ai/chapter-analysis（每次分析后）和
 * GET /ai/chapter-analysis-stats（页面加载批量拉取）返回。
 *
 * avg_score / avg_hook_strength 为浮点数，展示时保留一位小数。
 * 定性字段（verdict、what_hooked 等）取最近一次分析。
 */
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

// ── Dashboard 首页聚合 ─────────────────────────────────
/** 七天柱状图单项 */
export interface DashboardWeekDay {
  /** YYYY-MM-DD（服务器时区） */
  date: string
  weekday_label: string
  words: number
  height: number
}

/** 「最近编辑」单项；项目对象用于跳转 */
export interface DashboardRecentChapter {
  id: string
  title: string
  word_count: number
  sort_order: number
  chapter_label: string
  updated_at: string | null
  project: Project
}

/** GET /api/v1/dashboard/home 返回结构 */
export interface DashboardHome {
  greeting_name: string
  total_words: number
  today_words: number
  streak_days: number
  writing_days: number
  average_words: number
  week: DashboardWeekDay[]
  recent_chapters: DashboardRecentChapter[]
}
