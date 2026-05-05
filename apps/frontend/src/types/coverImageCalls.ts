/** GET /api/v1/admin/cover-image-calls/ 单条记录 */
export interface CoverImageCallRecord {
  id: string
  created_at: string
  project_id: string
  llm_provider_id: string
  provider_name: string
  model_name: string
  prompt: string
  size: string
  quality: string
  store_compressed: boolean
  status: string
  http_status: number | null
  error_message: string | null
  duration_ms: number
  response_kind: string
  gateway_url: string
  debug_bundle_rel_path: string | null
  /** 成功时站内路径或外链，管理端预览用 */
  result_cover_url: string | null
}
