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
  /** 开篇章：章纲按开局台账微调（非已写正文冲突）。 */
  setup_alignment?: string[]
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

/** LLM 质检层（衔接/五拍/钩子 + 本章/后续建议）。 */
export interface DabaiLabQualityLlm {
  continuity_score: number
  continuity_issue: string
  beats: Record<string, string>
  beat_issues: string[]
  beat_score: number
  hook_score: number
  hook_issue: string
  /** 本章修改建议（v2 主字段）。 */
  chapter_suggestions?: string[]
  /** 对后续章节的写作提醒。 */
  future_chapter_suggestions?: string[]
  /** 兼容旧报告。 */
  suggestions: string[]
  /** LLM 原始重写指令（score<80 时后端也会合成顶层 rewrite_prompt）。 */
  rewrite_prompt?: string
}

/** 章节质检报告（落库 report 字段）。 */
export interface DabaiLabQualityReport {
  version?: string
  status?: 'ok' | 'warning' | 'blocked' | string
  overall_score?: number
  /** 综合分 <80 时生成的重写提示词（可直接填入写作指令）。 */
  rewrite_prompt?: string
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
  /** 语义检索返回时附带的余弦距离（越小越相关）；列表/精确模式无此字段。 */
  score?: number
}

/** 记忆库检索结果（GET /memory/search）。 */
export interface DabaiLabMemorySearchResult {
  items: DabaiLabMemory[]
  total: number
  /** 请求的模式。 */
  mode: 'semantic' | 'exact'
  /** 实际生效模式：语义不可用/无向量数据时降级为 exact。 */
  effective_mode: 'semantic' | 'exact'
  /** 是否发生降级（语义→精确）。 */
  degraded: boolean
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
  /** 本章新建档的长期角色名（工具人不建档）。 */
  new_characters?: string[]
}

/** 资产台账条目（功法/道具/金手指）。 */
/** 技能/道具详细规格（导演单锁定，防分场/正文乱写）。 */
export interface DabaiAssetSpec {
  usage?: string         // 用法
  cost?: string          // 代价
  progression?: string   // 进阶
  restriction?: string   // 限制
}

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
  spec?: DabaiAssetSpec | null
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

// ── 情节档案（按章聚合：计划五拍 + 复盘实际 + 线索/资产/关系变更）─────────────

/** 本章五拍计划块（章纲值）。 */
export interface DabaiArchivePlan {
  shuang_type: string
  yaqu_setup: string
  emotion_turn: string
  yinbao: string
  shuang_payoff: string
  end_hook: string
  location: string
  realm_rank: number | null
  is_big_beat: boolean
  expected_words: number | null
  witnesses: string[]
  involved_characters: string[]
}

/** 复盘提取的核心事件（实际发生，非摘要记忆）。 */
export interface DabaiArchiveCoreEvent {
  id: string
  mem_type: string
  content: string
  importance: number
  tags: string[]
}

/** 本章埋设的线索。 */
export interface DabaiArchiveCluePlanted {
  id: string
  title: string
  clue_type: string
  description: string | null
  status: string
}

/** 本章回收的线索。 */
export interface DabaiArchiveClueResolved {
  id: string
  title: string
  clue_type: string
}

/** 本章资产变更（获得/消耗/失去）。 */
export interface DabaiArchiveAssetChange {
  name: string
  kind: string
  change: string
}

/** 本章人物态度变更。 */
export interface DabaiArchiveRelationChange {
  from: string
  to: string
  attitude: string | null
  reason: string | null
}

/** 单章情节档案（GET .../archive）。 */
export interface DabaiChapterArchive {
  chapter_id: string
  chapter_number: number
  title: string
  status: string
  word_count: number
  /** 是否已复盘（无复盘时只有计划，无实际事实）。 */
  debriefed: boolean
  plan: DabaiArchivePlan
  summary: string | null
  core_events: DabaiArchiveCoreEvent[]
  clues_planted: DabaiArchiveCluePlanted[]
  clues_resolved: DabaiArchiveClueResolved[]
  asset_changes: DabaiArchiveAssetChange[]
  relation_changes: DabaiArchiveRelationChange[]
  first_appearances: string[]
}
