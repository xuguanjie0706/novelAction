import { api } from './base'

/** 卷章纲 linter 报告（与后端 LinterReport.to_dict 对齐） */
export interface LinterVolumeReport {
  linter_version: string
  status: 'ok' | 'warn' | 'failed'
  critical_count: number
  high_count: number
  issue_count: number
  issues: Array<{
    rule_id: string
    severity: string
    scope: string
    message: string
    suggestion?: string
    field?: string
    chapter_number_in_volume?: number | null
  }>
}

export interface LinterRepairSeed {
  must_fix_chapter_numbers: number[]
  issues_by_chapter: Record<string, Array<{ rule_id: string; message: string; field: string; suggestion: string }>>
  critical_count: number
  high_count: number
  summary: string
}

// ── Outline ───────────────────────────────────────────
export const outlineApi = {
  getTree: (pid: string) => api.get(`/projects/${pid}/outline/`),
  /** 只读：从大纲章节计划「人物变化」聚合主角境界新高节点 */
  protagonistRealmTimeline: (pid: string) =>
    api.get(`/projects/${pid}/outline/protagonist-realm-timeline`),
  /** 全书章序横轴 + 卷/故事线/势力/伏笔/承诺/境界甘特条 */
  storyTimeline: (pid: string) =>
    api.get(`/projects/${pid}/outline/story-timeline`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/outline/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/outline/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/outline/${id}`),
  clearChapterPlans: (pid: string) =>
    api.delete<{ deleted: number }>(`/projects/${pid}/outline/chapter-plans`),
  aiExpandUrl: (pid: string) => `/api/v1/projects/${pid}/outline/ai-expand`,
  expandVolChaptersUrl: (pid: string, volumeNodeId: string) =>
    `/api/v1/projects/${pid}/outline/volumes/${volumeNodeId}/expand-chapters`,
  /** 卷章纲 linter（落库 volume.extra.linter_*） */
  lintVolume: (pid: string, volumeNodeId: string, persist = true) =>
    api
      .post<LinterVolumeReport>(
        `/projects/${pid}/outline/volumes/${volumeNodeId}/lint`,
        undefined,
        { params: { persist } },
      )
      .then((r) => r.data),
  lintVolumeRepairSeed: (pid: string, volumeNodeId: string, persist = true) =>
    api
      .post<LinterVolumeReport & { repair_seed: LinterRepairSeed }>(
        `/projects/${pid}/outline/volumes/${volumeNodeId}/lint/repair-seed`,
        undefined,
        { params: { persist } },
      )
      .then((r) => r.data),
  commitExpand: (pid: string, data: { parent_node_id: string; chapters: any[] }) =>
    api.post(`/projects/${pid}/outline/ai-expand/commit`, data),
  qualityCheck: (pid: string, data: any) =>
    api.post(`/projects/${pid}/outline/ai-quality-check`, data),
  startQualityCheckWorkflow: (pid: string, data: any) =>
    api.post<{ run_id: string }>(`/projects/${pid}/outline/ai-quality-check/workflow`, data),
  startRepairWorkflow: (pid: string, data: any) =>
    api.post<{ run_id: string }>(`/projects/${pid}/outline/ai-repair/workflow`, data),
  qualityCheckWorkflowWsUrl: (pid: string, runId: string) =>
    `/api/v1/projects/${pid}/outline/workflows/${runId}/ws`,
  listRevisions: (pid: string) => api.get(`/projects/${pid}/outline/revisions`),
  createRevision: (pid: string, data: any) => api.post(`/projects/${pid}/outline/revisions`, data),
  getRevision: (pid: string, id: string) => api.get(`/projects/${pid}/outline/revisions/${id}`),
}
