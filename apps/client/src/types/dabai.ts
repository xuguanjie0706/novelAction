/**
 * @file types/dabai.ts — 大白文（爽点节拍器）独立分支类型。
 * 与精品文类型完全隔离，对应后端 dabai_* 表与 /api/v1/dabai 响应。
 */

/** 章纲：爽点节拍器（注意——没有 choice_cost）。 */
export interface DabaiChapter {
  id?: string
  chapter_number: number
  title: string
  shuang_type: string          // 一等公民：本章爽点类型
  yaqu_setup: string           // 憋屈势能
  yinbao: string               // 引爆
  shuang_payoff: string        // 爽感量化（须有观众）
  witnesses: string[]          // 见证者/被打脸者
  end_hook: string             // 章末强钩子
  new_info_count: number       // 信息密度
  involved_characters: string[]
  is_big_beat: boolean         // 大爆点
  expected_words: number
  content?: string | null      // 正文（写作期填充）
  status?: string              // planned / written
}

export interface DabaiVolume {
  id?: string
  volume_number: number
  title: string
  phase: string
  planned_chapters: number
  big_beats: string[]
  volume_climax: string
  end_hook: string
}

export interface DabaiLinterIssue {
  rule_id: string
  severity: 'critical' | 'high' | 'medium'
  chapter: number | null
  message: string
  suggestion?: string
}

export interface DabaiLinterReport {
  status?: 'ok' | 'warning' | 'blocked'
  score?: number
  issue_count?: number
  critical_count?: number
  issues?: DabaiLinterIssue[]
}

export interface DabaiProjectDetail {
  id: string
  logline: string
  title: string | null
  status: string
  mock: boolean
  positioning: Record<string, unknown>
  golden_finger: Record<string, unknown>
  power_ladder: { name?: string; levels?: Array<{ rank: number; name: string; desc: string }> }
  factions: Array<Record<string, unknown>>
  characters: Array<Record<string, unknown>>
  storylines: Array<Record<string, unknown>>
  linter_report: DabaiLinterReport
  meta: Record<string, unknown>
  failed_steps: string[]
  created_at: string | null
  volumes: DabaiVolume[]
  chapter_outlines: DabaiChapter[]
}

export interface DabaiProjectSummary {
  id: string
  logline: string
  title: string | null
  status: string
  mock: boolean
  linter_status?: string
  linter_score?: number
  volume_count: number
  chapter_count: number
  created_at: string | null
}

export interface DabaiGenerateRequest {
  logline: string
  mock: boolean
  /** 模型/线路：沿用通用分支选择（local 走 .env，gemini 走 llm_providers/env）。 */
  model_profile?: 'local' | 'gemini'
  llm_provider_id?: string
  volume_count: number
  volume_chapters: number
  big_beat_every: number
  chapter_batch_size?: number
}

/** SSE 流式生成事件（与后端 /dabai/projects/stream 对齐）。 */
export type DabaiStreamEvent =
  | { event: 'project_created'; project_id: string; steps: string[] }
  | { event: 'step_start'; step: string }
  | { event: 'step_done'; step: string; count: number }
  | { event: 'chapter_batch'; batch_start: number; batch_end: number; total: number }
  | { event: 'step_error'; step: string; message: string }
  | { event: 'linter_done'; status: string; score: number; issue_count: number }
  | { event: 'done'; project_id: string }
  | { event: 'error'; message: string }

/** 8 步中文标签（进度展示）。 */
export const DABAI_STEP_LABELS: Record<string, string> = {
  positioning: '立项定位',
  golden_finger: '金手指',
  power_ladder: '境界阶梯',
  factions: '势力',
  characters: '人物',
  storylines: '故事线',
  volumes: '卷骨架',
  chapter_outlines: '章纲·爽点节拍',
}

