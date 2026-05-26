import type { DashboardHome, WorldSetting } from '../types'
import { api } from './base'

/** 写作质量门控配置 */
export interface WritingConfig {
  /** 是否启用质量门控循环（默认 true，但阈值极低不影响日常写作） */
  auto_quality_gate: boolean
  /** 综合质检分下限（0-10 scale，默认 6.0） */
  min_overall_score: number
  /** 章末订阅意愿分下限（独立门槛，默认 6.0） */
  min_subscribe_intent: number
  /** 最大重写次数（含首次，默认 3） */
  max_rewrite_attempts: number
  /**
   * 写前预警：开启后每次门控写作前先以「三十年主编」视角生成简报，
   * 包含主角状态锁定、本章写法指导、必发事件和幻觉预防清单，注入正文 prompt。
   * 默认 false（关闭）。
   */
  pre_write_warning_enabled: boolean
}

// ── Projects ──────────────────────────────────────────
export const projectsApi = {
  list: () => api.get('/projects/'),
  create: (data: any) => api.post('/projects/', data),
  get: (id: string) => api.get(`/projects/${id}`),
  update: (id: string, data: any) => api.patch(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
  resetWriting: (id: string) => api.post(`/projects/${id}/reset-writing`),
  /** Bootstrap 后写入 Project.extra 的编辑洞察：consistency_issues / opening_contract / positioning */
  getInsights: (id: string) => api.get<{
    project_id: string
    consistency_issues: Array<{ severity?: string; description?: string; issue?: string; category?: string }>
    opening_contract: Record<string, any>
    positioning: Record<string, any>
  }>(`/projects/${id}/insights`),
  /** 读取项目级写作质量门控配置（含系统默认值兜底） */
  getWritingConfig: (id: string) =>
    api.get<{ writing_config: WritingConfig }>(`/projects/${id}/writing-config`),
  /** 部分更新写作质量门控配置（只传改变的字段） */
  updateWritingConfig: (id: string, data: Partial<WritingConfig>) =>
    api.patch<{ writing_config: WritingConfig }>(`/projects/${id}/writing-config`, data),
  fixConsistencyIssues: (
    id: string,
    data: {
      selected_indices: number[]
      user_prompt: string
      model_profile: 'local' | 'gemini'
      llm_provider_id: string | null
    },
  ) => api.post<{
    applied: Array<{
      issue_index: number
      entity_type: string
      entity_name: string
      field: string
      old_value: string | null
      new_value: string
      applied: boolean
      reason: string
    }>
    skipped: Array<{ issue_index: number; reason: string; suggestion: string }>
    message: string
  }>(`/projects/${id}/consistency/fix`, data),
  rescanConsistency: (
    id: string,
    data: {
      model_profile: 'local' | 'gemini'
      llm_provider_id: string | null
    },
  ) => api.post<{
    issues: Array<{ severity?: string; description?: string; type?: string; suggestion?: string; status?: string }>
    count: number
    message: string
  }>(`/projects/${id}/consistency/rescan`, data),
}

// ── Dashboard ─────────────────────────────────────────
export const dashboardApi = {
  home: () => api.get<DashboardHome>('/dashboard/home'),
}

// ── Cover Generation ──────────────────────────────────
export const coverApi = {
  imageProviders: () => api.get('/cover/image-providers'),
  generate: (projectId: string, data: {
    llm_provider_id: string
    prompt: string
    size?: string
    quality?: string
    store_compressed?: boolean
  }) => api.post(`/projects/${projectId}/cover/generate`, data),
  /** multipart：字段名 file，服务端压缩为 WebP 落盘 */
  upload: (projectId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/projects/${projectId}/cover/upload`, fd, {
      transformRequest: [
        (data, headers) => {
          const h = headers as Record<string, unknown> | undefined
          if (h && typeof h === 'object') delete h['Content-Type']
          return data
        },
      ],
    })
  },
}
