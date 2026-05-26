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
  priority: number
  created_at: string
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
  priority: number
  audience_aware: number
  status: PromiseStatus
  fulfilled_chapter_id: string | null
  fulfilled_chapter_number: number | null
  created_at: string
  updated_at: string
}

// ── Location（空间连续性机制） ────────────────────────────
export type LocationDangerLevel = 'safe' | 'neutral' | 'dangerous' | 'forbidden'

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

export type LocationStatus = 'active' | 'destroyed' | 'occupied' | 'abandoned' | 'sealed'

/**
 * 地点（Location）— 空间连续性管理的核心单元。
 *
 * sensory_signature 是防漂移的核心字段：固定感官描述（1-3句），
 * 写章时注入 prompt 作为硬约束，防止 AI 在同一地点产生矛盾感官描写。
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
  sensory_signature?: string | null
  description?: string | null
  status?: LocationStatus
  sort_order?: number
  extra?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}
