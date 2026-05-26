// ── AI / LLM ──────────────────────────────────────────
export interface AiChatMessage {
  id: string
  project_id: string
  chapter_id?: string | null
  context_type: 'outline' | 'writing' | 'general'
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

/** GET /api/v1/llm/overview — 启用的远程线路列表（不含密钥） */
export interface RemoteProviderBrief {
  id: string
  name: string
  model_name: string
  is_default: boolean
}

/** GET /api/v1/cover/image-providers — 图片生成提供者 */
export interface ImageProviderBrief {
  id: string
  name: string
  model_name: string
}

/** POST /api/v1/projects/{id}/cover/generate 请求 */
export interface CoverGenerateIn {
  llm_provider_id: string
  prompt: string
  size?: string
  quality?: string
  /** 默认 true：服务端压缩 WebP 落盘并返回 cover_url */
  store_compressed?: boolean
}

/** POST /api/v1/projects/{id}/cover/generate 响应 */
export interface CoverGenerateOut {
  /** 压缩落盘后的站内路径（默认 store_compressed=true） */
  cover_url?: string
  data_url?: string
  image_url?: string
}

/** GET /api/v1/llm/overview — 后端登记的远程智能体 / 本地模型摘要 */
export interface LlmOverview {
  local_model_name: string
  remote_ready: boolean
  effective_remote_model: string | null
  remote_agent: {
    id: string
    name: string
    model_name: string
    is_default?: boolean
  } | null
  remote_source: 'database' | 'env' | 'none'
  remote_providers: RemoteProviderBrief[]
}
