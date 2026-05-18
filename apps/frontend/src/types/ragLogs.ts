/** GET /api/v1/admin/rag-logs/ 单条记录（与后端 RagRetrievalLogOut 对齐） */
export interface RagRetrievalLogRecord {
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
