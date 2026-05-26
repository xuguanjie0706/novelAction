import { api } from './base'

// ── Bootstrap（一句话生成）─────────────────────────────
// 注意：bootstrap 使用原生 fetch + SSE，不走 axios
// 用法见 GenerateWizard.tsx
export const bootstrapApi = {
  streamUrl: '/api/v1/bootstrap/stream',
}

export interface BootstrapRunHistoryItem {
  run_id: string
  status: string
  project_id: string | null
  gate_data?: Record<string, any> | null
  events: Array<Record<string, any>>
  error_message?: string | null
  logline?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** GET /bootstrap/runs/{id} 与列表项字段对齐，便于恢复 UI */
export type BootstrapRunDetail = BootstrapRunHistoryItem

export const bootstrapRunsApi = {
  listByProject: (projectId: string) =>
    api.get<BootstrapRunHistoryItem[]>(`/bootstrap/projects/${projectId}/runs`),
  get: (runId: string) => api.get<BootstrapRunDetail>(`/bootstrap/runs/${runId}`),
  cancel: (runId: string) =>
    api.post<{ ok: boolean; run_id: string; status: string }>(`/bootstrap/runs/${runId}/cancel`),
}
