// ── Memory ────────────────────────────────────────────
export interface MemoryChunk {
  id: string
  project_id: string
  chapter_id?: string
  memory_type: 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict'
  title?: string
  content: string
  chapter_number?: number
  tags: string[]
  /** AI 提取时赋值 0.0-1.0；检索时与时效衰减共同加权排序 */
  importance_score: number
  /** 被 RAG 召回的累计次数 */
  access_count: number
  /** 最近一次被召回时间（ISO 格式） */
  last_accessed_at?: string | null
  created_at: string
}

/** 单条记忆冲突描述（与后端 MemoryConflictItem 对齐） */
export interface MemoryConflictItem {
  /** character_state | timeline | attribute | foreshadow */
  conflict_type: string
  /** high | medium | low */
  severity: 'high' | 'medium' | 'low'
  description: string
  chunk_ids: string[]
  chapter_refs: number[]
}

/** 记忆冲突检测报告（与后端 detect_memory_conflicts 返回值对齐） */
export interface MemoryConflictReport {
  total_chunks_scanned: number
  conflicts: MemoryConflictItem[]
  detected_at: string
  error?: string
}

/** 单条 RAG 语义命中（与后端 RagSearchHitOut 对齐） */
export interface RagSearchHit {
  rank: number
  memory_id: string
  score?: number | null
  retrieval_source: 'semantic' | 'recency_anchor' | 'recency_fallback'
  memory_type: string
  title?: string | null
  content: string
  content_preview: string
  chapter_number?: number | null
  tags: string[]
}

/** POST /memory/rag-query 结构化响应 */
export interface RagQueryResponse {
  log_id: string
  query: string
  params: Record<string, unknown>
  status: string
  duration_ms: number
  hits: RagSearchHit[]
  memory_summary: string
  answer_hint: string
}

/** 持久化 RAG 调用日志 */
export interface RagRetrievalLog {
  id: string
  project_id: string
  chapter_id?: string | null
  source: string
  status: string
  duration_ms: number
  input_payload: Record<string, unknown>
  output_payload: Record<string, unknown>
  created_at: string
}
