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
