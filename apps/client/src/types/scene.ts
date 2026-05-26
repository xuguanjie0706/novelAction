// ── Scene（三层调度：章纲 → 分场 → 正文） ──────────────────

/** 节奏标记 */
export type ScenePacing = 'fast' | 'mid' | 'slow'

/** 分场状态 */
export type SceneStatus = 'planned' | 'written' | 'reviewed'

// ── 场景投料约束类型 ──────────────────────────────────────
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

/**
 * 分场（Scene）——章节的子结构单元。
 * 对应后端 SceneRead schema；由 Bootstrap Step 13 或手动生成。
 * outline_node_id 指向所属 chapter_plan 大纲节点。
 */
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
