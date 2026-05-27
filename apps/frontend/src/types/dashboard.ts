/** 管理后台控制台聚合数据类型定义。 */

export interface ContentStats {
  total_projects: number
  projects_by_status: Record<string, number>
  total_chapters: number
  total_words: number
}

export interface UserStats {
  total_users: number
  active_users: number
}

export interface BootstrapStats {
  bootstrap_total: number
  bootstrap_today: number
  bootstrap_by_status: Record<string, number>
}

export interface TopTask {
  task: string
  tokens: number
}

export interface LlmStats {
  llm_calls_today: number
  llm_ok_today: number
  llm_error_today: number
  token_today: number
  prompt_tokens_today: number
  completion_tokens_today: number
  avg_duration_ms_today: number
  success_rate_today: number
  truncated_today: number
  limit_exceeded_today: number
  llm_calls_total: number
  success_rate_total: number
  token_total: number
  prompt_tokens_total: number
  completion_tokens_total: number
  top_tasks_by_token: TopTask[]
}

export interface TokenTrendItem {
  date: string
  tokens: number
  calls: number
  errors: number
}

export interface RagStats {
  rag_total: number
  rag_semantic_ok: number
  rag_fallback: number
  rag_semantic_rate: number
  rag_avg_duration_ms: number
  rag_today: number
  rag_by_status: Record<string, number>
}

export interface QualityStats {
  conflict_detections_today: number
  total_conflicts_found: number
  quality_debt_pending: number
  quality_debt_by_status: Record<string, number>
  quality_debt_by_severity: Record<string, number>
}

export interface CreditStats {
  credits_consumed_today: number
  credits_topup_today: number
  credits_consumed_total: number
  credits_topup_total: number
}

export interface RecentBootstrap {
  id: string
  status: string
  logline: string
  mode: string
  created_at: string | null
}

export interface RecentLlmError {
  id: string
  model: string
  error: string
  duration_ms: number
  created_at: string | null
  context: { operation?: string }
}

export interface RecentConflict {
  id: string
  project_id: string
  conflict_count: number
  trigger: string
  created_at: string | null
}

export interface ActivityData {
  recent_bootstraps: RecentBootstrap[]
  recent_llm_errors: RecentLlmError[]
  recent_memory_conflicts: RecentConflict[]
}

export interface DashboardStats {
  generated_at: string
  content: ContentStats
  users: UserStats
  bootstrap: BootstrapStats
  llm: LlmStats
  token_trend: TokenTrendItem[]
  rag: RagStats
  quality: QualityStats
  credits: CreditStats
  activity: ActivityData
}
