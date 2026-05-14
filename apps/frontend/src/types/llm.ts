/** POST .../test-connection 响应 */
export interface LlmTestConnectionResult {
  ok: boolean
  message: string
  latency_ms?: number | null
  http_status?: number | null
}

export interface LlmProvider {
  id: string
  name: string
  base_url: string
  model_name: string
  /** 'text' = 文本生成（默认）；'image' = 图片生成（/v1/images/generations） */
  provider_type: 'text' | 'image'
  /**
   * 计费档位，由管理员显式指定：
   * - 'heavy'    高端大模型（GPT-4、Claude Opus 等），扣费最多
   * - 'standard' 中端模型（默认），按标准费率扣费
   * - 'light'    本地/免费模型，不扣积分
   */
  tier: 'heavy' | 'standard' | 'light'
  has_api_key: boolean
  api_key_hint: string | null
  enabled: boolean
  is_default: boolean
  sort_order: number
  created_at?: string
  updated_at?: string
}

export interface RemoteProviderBrief {
  id: string
  name: string
  model_name: string
  is_default: boolean
}

export interface LlmOverview {
  local_model_name: string
  remote_ready: boolean
  effective_remote_model: string | null
  remote_agent: RemoteProviderBrief | null
  remote_source: 'database' | 'env' | 'none'
  remote_providers: RemoteProviderBrief[]
}

export interface LlmCallTokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated: boolean
}

export interface LlmCallRecord {
  id: string
  created_at: string
  mode: string
  model: string
  llm_endpoint: string
  status: 'ok' | 'error'
  duration_ms: number
  context: Record<string, unknown>
  token_usage: LlmCallTokenUsage
  error?: string | null
  input_payload?: unknown
  output_payload?: unknown
}
