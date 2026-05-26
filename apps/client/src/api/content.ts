import type { Location, ReaderPromise, Scene } from '../types'
import { api } from './base'

// ── Chapters ──────────────────────────────────────────
export const chaptersApi = {
  list: (pid: string) => api.get(`/projects/${pid}/chapters/`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/chapters/`, data),
  get: (pid: string, id: string) => api.get(`/projects/${pid}/chapters/${id}`),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/chapters/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/chapters/${id}`),
  snapshot: (pid: string, id: string, note = '', isAuto = false) => {
    const q = new URLSearchParams()
    if (note) q.set('note', note)
    if (isAuto) q.set('is_auto', 'true')
    const qs = q.toString()
    return api.post(`/projects/${pid}/chapters/${id}/snapshot${qs ? `?${qs}` : ''}`)
  },
  listVersions: (pid: string, id: string) => api.get(`/projects/${pid}/chapters/${id}/versions`),
  getVersion: (pid: string, chapterId: string, versionId: string) =>
    api.get(`/projects/${pid}/chapters/${chapterId}/versions/${versionId}`),
  listDebriefApplyRecords: (pid: string, chapterId: string, limit = 40) =>
    api.get<
      Array<{
        id: string
        apply_source: string
        content_hash: string | null
        payload: Record<string, unknown>
        result_message: string | null
        created_at: string | null
      }>
    >(`/projects/${pid}/chapters/${chapterId}/debrief-apply-records?limit=${limit}`),
}

// ── Foreshadows ───────────────────────────────────────
export const foreshadowsApi = {
  list: (pid: string, status?: string) =>
    api.get(`/projects/${pid}/foreshadows/${status ? `?status=${status}` : ''}`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/foreshadows/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/foreshadows/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/foreshadows/${id}`),
}

// ── Chapter Indexes ───────────────────────────────────
export const chapterIndexesApi = {
  list: (pid: string) => api.get(`/projects/${pid}/chapter-indexes/`),
  getByChapter: (pid: string, chapterId: string) =>
    api.get(`/projects/${pid}/chapter-indexes/chapter/${chapterId}`),
  upsert: (pid: string, data: any) => api.post(`/projects/${pid}/chapter-indexes/`, data),
  update: (pid: string, chapterId: string, data: any) =>
    api.patch(`/projects/${pid}/chapter-indexes/chapter/${chapterId}`, data),
}

// ── Quality Debts ─────────────────────────────────────
export const qualityDebtsApi = {
  list: (pid: string, status?: string) =>
    api.get(`/projects/${pid}/quality-debts/${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  update: (pid: string, id: string, data: any) =>
    api.patch(`/projects/${pid}/quality-debts/${id}`, data),
}

// ── ReaderPromises ────────────────────────────────────
export const readerPromisesApi = {
  list: (pid: string, status?: string) =>
    api.get<ReaderPromise[]>(`/projects/${pid}/reader_promises/`, {
      params: status ? { status } : undefined,
    }),
  create: (pid: string, data: Partial<ReaderPromise>) =>
    api.post<ReaderPromise>(`/projects/${pid}/reader_promises/`, data),
  update: (pid: string, id: string, data: Partial<ReaderPromise>) =>
    api.patch<ReaderPromise>(`/projects/${pid}/reader_promises/${id}`, data),
  delete: (pid: string, id: string) =>
    api.delete(`/projects/${pid}/reader_promises/${id}`),
}

// ── Locations ─────────────────────────────────────────
export const locationsApi = {
  list: (pid: string) =>
    api.get<Location[]>(`/projects/${pid}/locations`),
  create: (pid: string, data: Omit<Partial<Location>, 'id' | 'project_id' | 'created_at' | 'updated_at'>) =>
    api.post<Location>(`/projects/${pid}/locations`, data),
  update: (pid: string, id: string, data: Partial<Location>) =>
    api.patch<Location>(`/projects/${pid}/locations/${id}`, data),
  delete: (pid: string, id: string) =>
    api.delete(`/projects/${pid}/locations/${id}`),
}

// ── Scenes（三层调度：分场） ──────────────────────────────
export const scenesApi = {
  list: (pid: string, params: { outline_node_id?: string; chapter_id?: string }) =>
    api.get<Scene[]>(`/projects/${pid}/scenes/`, { params }),
  batchCreate: (
    pid: string,
    outline_node_id: string,
    scenes: Array<Record<string, unknown>>,
  ) =>
    api.post<Scene[]>(`/projects/${pid}/scenes/batch`, {
      outline_node_id,
      scenes,
      replace_existing: true,
    }),
  patch: (pid: string, sceneId: string, data: Record<string, unknown>) =>
    api.patch<Scene>(`/projects/${pid}/scenes/${sceneId}`, data),
}
