/**
 * types.ts — ChapterEditor 包内共享类型定义
 *
 * 职责：仅包含 interface / type 声明，无运行时代码。
 * 供 index.tsx、DebriefPanel.tsx 及 hooks 共同导入。
 */
import type { Chapter, Character, OutlineNode, StoryLine } from '../../../types'
import type React from 'react'

// ─── 组件 Props ──────────────────────────────────────────────────────────────

/** ChapterEditor 主组件 props */
export interface ChapterEditorProps {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  prevChapter?: Chapter
  onFocusModeChange?: (v: boolean) => void
}

// ─── AI 复盘结构 ─────────────────────────────────────────────────────────────

export type NewCharacterSuggestion = {
  name: string
  role?: string
  gender?: string
  age?: string
  faction?: string
  personality?: string
  motivation?: string
  background?: string
  current_realm?: string
  current_status?: string
  current_location?: string
  arc_scope?: string
  author_notes?: string
}

/** 故事线织网写前预警（SSE storyline_pre_warn） */
export type StorylinePreWarnItem = {
  warn_id: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail?: string
  suggested_action?: string
  storyline_id?: string
  storyline_name?: string
}

/** 写章前程序生成的情节锁定表（先于主编 LLM 预警） */
export type ChapterLockTable = {
  has_prev: boolean
  prev_chapter_number?: number | string | null
  current_chapter_number?: number | string | null
  locked_beats?: string[]
  forbidden_replays?: string[]
  outline_conflicts?: Array<{ field?: string; outline_text?: string; reason?: string }>
  prev_tail_anchor?: string
}

/** 伏笔日程锁定表（core_mysteries + opening_contract，第 1 章起生效） */
export type ForeshadowScheduleLock = {
  has_schedule: boolean
  current_chapter_number?: number | string | null
  forbidden_early_plants?: Array<{
    name?: string
    planned_lay_chapter?: number
    reason?: string
  }>
  allowed_this_chapter?: Array<{ name?: string; op?: string; detail?: string }>
  opening_teases?: Array<{ label?: string; detail?: string }>
  outline_conflicts?: Array<{ field?: string; outline_text?: string; reason?: string }>
}

export type PreWriteWarnResult = {
  ok: boolean
  risk_count: number
  risks: Array<{ type: string; severity: string; description: string; suggested_fix: string }>
  reminders: string[]
  chapter_lock_table?: ChapterLockTable
  foreshadow_schedule_lock?: ForeshadowScheduleLock
  /** 主角状态锁定：境界/位置/可用技能/持有道具/禁止项 */
  protagonist_fact_sheet?: {
    realm: string
    location: string
    key_skills: string[]
    key_items: string[]
    forbidden: string[]
  }
  /** 本章写作简报：开篇策略/冲突节拍/章末钩子/字数节奏 */
  writing_brief?: {
    opening_strategy: string
    conflict_structure: string
    closing_hook: string
    word_rhythm: string
  }
  /** 本章必发事件列表 */
  must_events?: string[]
  /** 幻觉预防清单 */
  hallucination_traps?: string[]
  error?: string
  /** 解析失败时后端附带的原始输出片段 */
  raw?: string
  record_id?: string
  /** 故事线织网预警（门控 SSE storyline_pre_warn 聚合） */
  storyline_pre_warns?: StorylinePreWarnItem[]
}

export type PreWriteWarnHistoryRow = {
  id: string
  created_at: string | null
  model_profile: string
  chapter_plan_summary: string
  result: PreWriteWarnResult
}

export type AutoDebriefResponse = {
  character_updates: Array<{
    character_id: string
    character_name?: string
    current_realm?: string
    current_location?: string
    location_change_reason?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>
  storyline_updates: Array<{
    storyline_id: string
    storyline_name?: string
    status?: string
    beat?: string
    actual_tension?: number
    beat_match_score?: number
    crossover_executed?: boolean
    screen_time_words?: number
  }>
  new_characters?: NewCharacterSuggestion[]
  asset_updates?: Record<string, unknown>
  chapter_index?: {
    story_day?: string
    core_events?: Array<Record<string, unknown> | string>
    first_appearances?: Array<Record<string, unknown>>
    actual_foreshadows_laid?: Array<Record<string, unknown>>
    actual_foreshadows_resolved?: Array<Record<string, unknown>>
    ending_hook?: string
    hook_strength?: number
    continuity_notes?: Array<Record<string, unknown> | string>
  }
  summary?: string
  error?: string
  cached?: boolean
  cache_only_miss?: boolean
  new_reader_promises?: Array<{
    promise_text: string
    promise_type?: string
    expected_within_chapters?: number
    priority?: number
    audience_aware?: number
  }>
  fulfilled_promise_texts?: string[]
  next_chapter_directives?: Array<{
    outline_node_id?: string
    patch?: Record<string, unknown>
    reason?: string
  }>
  speech_kit_updates?: Array<{
    character_id?: string
    character_name?: string
    new_signature_words?: string[]
    new_sample_dialogues?: string[]
    evolution_note?: string
  }>
}

/** 复盘表单：故事线推进 + 织网 actual_beats 四字段 */
export type StorylineBeatFormFields = {
  status?: string
  beat?: string
  actual_tension?: number | ''
  beat_match_score?: number | ''
  crossover_executed?: boolean
  screen_time_words?: number | ''
}

// ─── DebriefPanel Props ───────────────────────────────────────────────────────

export interface DebriefPanelProps {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  characters: Character[]
  storyLines: StoryLine[]
  charUpdates: Record<string, {
    current_realm?: string
    current_location?: string
    location_change_reason?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>
  setCharUpdates: React.Dispatch<React.SetStateAction<DebriefPanelProps['charUpdates']>>
  storylineBeats: Record<string, StorylineBeatFormFields>
  setStorylineBeats: React.Dispatch<React.SetStateAction<DebriefPanelProps['storylineBeats']>>
  debriefNotes: string
  setDebriefNotes: (v: string) => void
  submitting: boolean
  autoDebriefing?: boolean
  /** 打开 Tab 时从服务端缓存恢复建议（非 LLM） */
  cacheHydrating?: boolean
  aiSuggestedCharIds?: Set<string>
  aiSuggestedSlIds?: Set<string>
  aiSuggestedAssetUpdates?: Record<string, unknown> | null
  aiNewCharacters?: NewCharacterSuggestion[]
  aiNewReaderPromises?: Array<{
    promise_text: string
    promise_type?: string
    expected_within_chapters?: number
    priority?: number
    audience_aware?: number
  }>
  aiFulfilledPromiseTexts?: string[]
  aiNextChapterDirectives?: NonNullable<AutoDebriefResponse['next_chapter_directives']>
  aiSpeechKitUpdates?: NonNullable<AutoDebriefResponse['speech_kit_updates']>
  onRemoveNewPromise?: (index: number) => void
  onRemoveFulfilledPromise?: (index: number) => void
  onRemoveNextChapterDirective?: (index: number) => void
  onRemoveSpeechKitUpdate?: (index: number) => void
  aiSummary?: string
  onAutoDebrief?: (forceRefresh?: boolean) => void
  onSubmit: (selectedAssetUpdates?: Record<string, unknown>) => void
  /** 展示内容来自生成队列自动复盘快照（已落库），与手动 AI 分析区分 */
  fromQueueSnapshot?: boolean
  /** 变更时重新拉取本章复盘落库审计列表 */
  debriefHistoryTick?: number
  /** 编辑器或已保存正文是否非空（控制 AI 分析按钮） */
  debriefContentReady?: boolean
}
