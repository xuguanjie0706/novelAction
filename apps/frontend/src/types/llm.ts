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
  has_api_key: boolean
  api_key_hint: string | null
  enabled: boolean
  is_default: boolean
  sort_order: number
  created_at?: string
  updated_at?: string
}
