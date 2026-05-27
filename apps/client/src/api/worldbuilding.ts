import { api } from './base'

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
  get: (pid: string, id: string) => api.get(`/projects/${pid}/characters/${id}`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/characters/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/characters/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/characters/${id}`),
  listRelationships: (pid: string) => api.get(`/projects/${pid}/characters/relationships/all`),
  createRelationship: (pid: string, data: any) => api.post(`/projects/${pid}/characters/relationships`, data),
  getChangelog: (pid: string, cid: string) => api.get(`/projects/${pid}/characters/${cid}/changelog`),
  growthTimeline: (pid: string, cid: string) =>
    api.get(`/projects/${pid}/characters/${cid}/growth-timeline`),
  deleteChangelogEntry: (pid: string, cid: string, logId: string) =>
    api.delete(`/projects/${pid}/characters/${cid}/changelog/${logId}`),
  clearChangelog: (pid: string, cid: string) =>
    api.delete(`/projects/${pid}/characters/${cid}/changelog`),
  generatePortrait: (
    pid: string,
    cid: string,
    data: { llm_provider_id: string; prompt_override?: string; style_hint?: string; size?: string; quality?: string },
  ) => api.post(`/projects/${pid}/characters/${cid}/portrait/generate`, data),
  generatePortraitsBatch: (
    pid: string,
    data: {
      llm_provider_id: string
      character_ids: string[]
      style_hint?: string
      size?: string
      quality?: string
      skip_existing?: boolean
    },
  ) => api.post(`/projects/${pid}/characters/portraits/generate-batch`, data),
}

// ── StoryLines ────────────────────────────────────────
export const storylinesApi = {
  weaveMatrix: (pid: string) => api.get(`/projects/${pid}/storylines/weave-matrix`),
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
