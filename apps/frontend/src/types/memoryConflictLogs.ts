export interface MemoryConflictDetectLogRecord {
  id: string
  project_id: string
  chapter_id: string | null
  trigger: string
  status: string
  duration_ms: number
  total_chunks_scanned: number
  conflict_count: number
  llm_call_log_id: string | null
  error: string | null
  output_payload: Record<string, unknown>
  created_at: string
}
