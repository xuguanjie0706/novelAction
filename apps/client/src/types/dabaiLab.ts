/**
 * @file types/dabaiLab.ts — dabai 实验书架写作期产物类型（预警/质检/记忆/线索）。
 * 对应后端 dabai_pre_warn_records / dabai_quality_reports / dabai_memories / dabai_clues
 * 与 /api/v1/dabai 下的 lab AI 端点响应。
 */

/** 写前导演单：开笔事实锁定。 */
export interface DabaiFactLock {
  realm?: string
  location?: string
  on_stage?: string[]
  forbidden?: string[]
}

/** 写前导演单完整结果（落库 result 字段）。 */
export interface DabaiPreWarnResult {
  version?: string
  fact_lock?: DabaiFactLock
  conflict_notes?: string[]
  opening_directive?: string
  beat_execution?: Record<string, string>
  bridge_directives?: string[]
  reminders?: string[]
}

/** 落库的导演单记录（GET pre-warn）。 */
export interface DabaiPreWarnRecord {
  version: string
  result: DabaiPreWarnResult
  brief: string
  created_at: string | null
}

/** 分场调度单场结构（落库 scenes[] 元素）。 */
export interface DabaiScenePlanItem {
  order?: number
  name?: string
  location?: string
  characters_on_stage?: string[]
  goal?: string
  event?: string
  dialogue_ammo?: string[]
  sensory_anchor?: string
  end_turn?: string
  word_budget?: number
}

/** 落库的分场调度记录（GET scene-plan）。 */
export interface DabaiScenePlanRecord {
  version: string
  scenes: DabaiScenePlanItem[]
  opening_line: string
  brief: string
  created_at: string | null
}

/** SSE pre_warn_done 事件载荷（写章流内实时推送）。 */
export interface DabaiPreWarnDoneEvent {
  event: 'pre_warn_done'
  dabai_mode: boolean
  ok: boolean
  version?: string
  fact_lock?: DabaiFactLock
  conflict_notes?: string[]
  opening_directive?: string
  brief_injected?: boolean
  error?: string
}

export interface DabaiLabRuleIssue {
  rule_id: string
  message: string
}

/** LLM 质检层（衔接/五拍/钩子）。 */
export interface DabaiLabQualityLlm {
  continuity_score: number
  continuity_issue: string
  beats: Record<string, string>
  beat_issues: string[]
  beat_score: number
  hook_score: number
  hook_issue: string
  suggestions: string[]
}

/** 章节质检报告（落库 report 字段）。 */
export interface DabaiLabQualityReport {
  version?: string
  status?: 'ok' | 'warning' | 'blocked' | string
  overall_score?: number
  llm_status?: 'ok' | 'skipped' | 'error' | 'parse_error' | string
  blockers?: DabaiLabRuleIssue[]
  warnings?: DabaiLabRuleIssue[]
  llm?: DabaiLabQualityLlm
}

/** 复盘记忆条目。 */
export interface DabaiLabMemory {
  id: string
  chapter_id: string
  chapter_number: number
  mem_type: 'summary' | 'fact' | 'event' | 'state' | 'relation' | string
  content: string
  importance: number
  tags: string[]
}

/** 线索台账条目。 */
export interface DabaiLabClue {
  id: string
  title: string
  clue_type: 'hook' | 'foreshadow' | 'promise' | string
  description: string | null
  chapter_planted: number | null
  chapter_resolved: number | null
  status: 'open' | 'resolved' | 'dropped' | string
  source: string
}

/** 复盘端点返回。 */
export interface DabaiLabDebriefResult {
  version: string
  summary: string
  memory_count: number
  new_clues: string[]
  resolved_clues: string[]
  /** 资产变更摘要（如「新获：青冥剑」）。 */
  asset_changes?: string[]
  /** 关系变更摘要（如「张三：敌对→臣服」）。 */
  relation_changes?: string[]
}

/** 资产台账条目（功法/道具/金手指）。 */
export interface DabaiLabAsset {
  id: string
  kind: 'skill' | 'item' | 'golden_finger' | string
  name: string
  owner: string | null
  description: string | null
  acquired_chapter: number | null
  status: 'active' | 'consumed' | 'lost' | string
  status_chapter: number | null
  source: string
}

/** 关系变化轨迹条目（chapter 为 null 表示手动修改）。 */
export interface DabaiRelationHistoryEntry {
  chapter: number | null
  attitude: string
  reason: string
}

/** 人物关系台账条目（主角视角）。 */
export interface DabaiLabRelation {
  id: string
  from_name: string
  to_name: string
  attitude: string | null
  note: string | null
  last_change_chapter: number | null
  history: DabaiRelationHistoryEntry[]
  source: string
}
