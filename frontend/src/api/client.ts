import axios from 'axios'
import toast from 'react-hot-toast'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    toast.error(msg)
    return Promise.reject(err)
  }
)

export default api

// ── Projects ──────────────────────────────────────────
export const projectsApi = {
  list: () => api.get('/projects/'),
  create: (data: any) => api.post('/projects/', data),
  get: (id: string) => api.get(`/projects/${id}`),
  update: (id: string, data: any) => api.patch(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
}

// ── World Settings ────────────────────────────────────
export const settingsApi = {
  list: (pid: string) => api.get(`/projects/${pid}/settings/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/settings/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/settings/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/settings/${id}`),
}

// ── Characters ────────────────────────────────────────
export const charactersApi = {
  list: (pid: string) => api.get(`/projects/${pid}/characters/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/characters/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/characters/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/characters/${id}`),
  listRelationships: (pid: string) => api.get(`/projects/${pid}/characters/relationships/all`),
  createRelationship: (pid: string, data: any) => api.post(`/projects/${pid}/characters/relationships`, data),
}

// ── Outline ───────────────────────────────────────────
export const outlineApi = {
  getTree: (pid: string) => api.get(`/projects/${pid}/outline/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/outline/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/outline/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/outline/${id}`),
  // AI 展开大纲 — SSE，使用原生 fetch（见 OutlineAIPanel.tsx）
  aiExpandUrl: (pid: string) => `/api/v1/projects/${pid}/outline/ai-expand`,
  // 确认写入大纲树
  commitExpand: (pid: string, data: { parent_node_id: string; chapters: any[] }) =>
    api.post(`/projects/${pid}/outline/ai-expand/commit`, data),
}

// ── Chapters ──────────────────────────────────────────
export const chaptersApi = {
  list: (pid: string) => api.get(`/projects/${pid}/chapters/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/chapters/`, data),
  get: (pid: string, id: string) => api.get(`/projects/${pid}/chapters/${id}`),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/chapters/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/chapters/${id}`),
  snapshot: (pid: string, id: string, note = '') => api.post(`/projects/${pid}/chapters/${id}/snapshot?note=${note}`),
  listVersions: (pid: string, id: string) => api.get(`/projects/${pid}/chapters/${id}/versions`),
}

// ── Bootstrap（一句话生成）────────────────────────────
// 注意：bootstrap 使用原生 fetch + SSE，不走 axios
// 用法见 GenerateWizard.tsx
export const bootstrapApi = {
  streamUrl: '/api/v1/bootstrap/stream',
}

// ── AI ────────────────────────────────────────────────
export const aiApi = {
  qualityCheck: (pid: string, data: any) => api.post(`/projects/${pid}/ai/quality-check`, data),
  extractMemory: (pid: string, chapterId: string, modelProfile: 'local' | 'gemini' = 'local') =>
    api.post(`/projects/${pid}/ai/extract-memory?chapter_id=${chapterId}&model_profile=${modelProfile}`),
  listMemory: (pid: string, type?: string) =>
    api.get(`/projects/${pid}/ai/memory${type ? `?memory_type=${type}` : ''}`),
}
