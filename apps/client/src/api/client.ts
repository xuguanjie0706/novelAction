import axios from 'axios'
import toast from 'react-hot-toast'
import type { LlmOverview } from '../types'

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

// ── StoryLines ────────────────────────────────────────
export const storylinesApi = {
  list: (pid: string) => api.get(`/projects/${pid}/storylines/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/storylines/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/storylines/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/storylines/${id}`),
}

// ── PowerSystems ──────────────────────────────────────
export const powerSystemsApi = {
  list: (pid: string) => api.get(`/projects/${pid}/power-systems/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/power-systems/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/power-systems/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/power-systems/${id}`),
}

// ── Skills ────────────────────────────────────────────
export const skillsApi = {
  list: (pid: string) => api.get(`/projects/${pid}/skills/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/skills/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/skills/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/skills/${id}`),
}

// ── Items ─────────────────────────────────────────────
export const itemsApi = {
  list: (pid: string) => api.get(`/projects/${pid}/items/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/items/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/items/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/items/${id}`),
}

// ── Factions ──────────────────────────────────────────
export const factionsApi = {
  list: (pid: string) => api.get(`/projects/${pid}/factions/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/factions/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/factions/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/factions/${id}`),
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
// ── LLM / 智能体（只读）────────────────────────────────────
export const llmApi = {
  overview: () => api.get<LlmOverview>('/llm/overview'),
}

export const aiApi = {
  qualityCheck: (pid: string, data: any) => api.post(`/projects/${pid}/ai/quality-check`, data),
  extractMemory: (
    pid: string,
    chapterId: string,
    modelProfile: 'local' | 'gemini' = 'local',
    llmProviderId?: string,
  ) => {
    const q = new URLSearchParams({ chapter_id: chapterId, model_profile: modelProfile })
    if (llmProviderId) q.set('llm_provider_id', llmProviderId)
    return api.post(`/projects/${pid}/ai/extract-memory?${q.toString()}`)
  },
  listMemory: (pid: string, type?: string) =>
    api.get(`/projects/${pid}/ai/memory${type ? `?memory_type=${type}` : ''}`),
  /** AI 自动分析章节，提取人物/故事线变化建议（不写库，只返回建议） */
  autoDebrief: (pid: string, data: {
    chapter_id: string
    model_profile?: 'local' | 'gemini'
  }) => api.post(`/projects/${pid}/ai/auto-debrief`, data),

  /** 章节写完后批量提交状态更新 */
  chapterDebrief: (pid: string, data: {
    chapter_id: string
    character_updates?: Array<{
      character_id: string
      current_realm?: string
      realm_rank?: number
      current_location?: string
      current_status?: string
      add_skill?: { skill_id?: string; skill_name: string; mastery?: string }
      add_item?: { item_id?: string; item_name: string; acquired_chapter?: number }
      remove_item_id?: string
    }>
    storyline_updates?: Array<{
      storyline_id: string
      status?: string
      append_beat?: string
    }>
    notes?: string
  }) => api.post(`/projects/${pid}/ai/chapter-debrief`, data),

  chapterCoherenceCheck: (
    pid: string,
    data: {
      chapter_ids: string[]
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-check`, data),

  saveChapterCoherenceReport: (
    pid: string,
    data: {
      name?: string
      model_profile?: 'local' | 'gemini'
      selected_chapter_ids: string[]
      result: Record<string, any>
    }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-reports`, data),

  listChapterCoherenceReports: (pid: string, limit = 20) =>
    api.get(`/projects/${pid}/ai/chapter-coherence-reports?limit=${limit}`),
}
