import axios from 'axios'
import toast from 'react-hot-toast'
import type { AiChatMessage, Chapter, ChapterAnalysisResult, ChapterAnalysisStats, DashboardHome, HookCheckResult, Location, LlmOverview, ReaderPromise, ReaderSimulationResult, Scene, StorylineGapsResult, WorldSetting } from '../types'
import {
  extractUsage,
  finishLlmCall,
  installLlmFetchLogger,
  isLlmRelatedEndpoint,
  startLlmCall,
} from '../utils/llmCallLogger'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

installLlmFetchLogger()

/**
 * 请求拦截器：
 * 1. 注入 Authorization: Bearer <token>（若 authStore 有 token）
 * 2. 记录 LLM 相关请求的调用 ID（用于耗时统计）
 */
api.interceptors.request.use((config) => {
  // 注入 JWT token（从 localStorage 直接读，避免循环依赖 authStore）
  try {
    const token = localStorage.getItem('novelAction:auth-token')
    if (token) {
      config.headers = config.headers ?? {}
      config.headers['Authorization'] = `Bearer ${token}`
    }
  } catch { /* ignore */ }

  const endpoint = config.url || ''
  if (isLlmRelatedEndpoint(endpoint)) {
    const callId = startLlmCall({
      method: config.method || 'GET',
      endpoint,
      context: { source: 'axios' },
      requestPayload: config.data,
    })
    ;(config as any).__llmCallId = callId
  }
  return config
})

api.interceptors.response.use(
  (res) => {
    const callId = (res.config as any).__llmCallId as string | undefined
    if (callId) {
      finishLlmCall(callId, {
        status: res.status,
        responsePayload: res.data,
        usage: extractUsage(res.data),
      })
    }
    return res
  },
  (err) => {
    const callId = (err.config as any)?.__llmCallId as string | undefined
    if (callId) {
      finishLlmCall(callId, {
        status: err.response?.status ?? 'network_error',
        responsePayload: err.response?.data,
        usage: extractUsage(err.response?.data),
        error: err.response?.data?.detail || err.message || '请求失败',
      })
    }

    // 401 未授权：清除 token 并跳转登录页（避免静默失效）
    if (err.response?.status === 401) {
      try {
        localStorage.removeItem('novelAction:auth-token')
      } catch { /* ignore */ }
      // 非登录页才跳转，避免死循环
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
      return Promise.reject(err)
    }

    const msg = err.response?.data?.detail || err.message || '请求失败'
    toast.error(msg)
    return Promise.reject(err)
  }
)

export default api

// ── Projects ──────────────────────────────────────────
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
}

// ── Dashboard 首页聚合（跨项目）───────────────────────
export const dashboardApi = {
  /** GET /api/v1/dashboard/home：首页所需的全量数据（写作统计 + 最近章节 + 问候语） */
  home: () => api.get<DashboardHome>('/dashboard/home'),
}

// ── Cover Generation ──────────────────────────────────
export const coverApi = {
  /** 获取所有已启用的图片类提供者（provider_type='image'） */
  imageProviders: () => api.get('/cover/image-providers'),
  /** 调用图片模型生成封面；默认返回压缩落盘的 cover_url */
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
  getChangelog: (pid: string, cid: string) => api.get(`/projects/${pid}/characters/${cid}/changelog`),
  deleteChangelogEntry: (pid: string, cid: string, logId: string) => api.delete(`/projects/${pid}/characters/${cid}/changelog/${logId}`),
  clearChangelog: (pid: string, cid: string) => api.delete(`/projects/${pid}/characters/${cid}/changelog`),
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

// ── ReaderPromise（读者承诺台账） ─────────────────────────

/**
 * 读者承诺 CRUD。
 * 后端路由前缀：/api/v1/projects/{pid}/reader_promises/
 */
export const readerPromisesApi = {
  /**
   * 列出项目所有承诺，可按 status 过滤（open/fulfilled/broken）。
   * @param pid - 项目 ID
   * @param status - 可选状态过滤
   */
  list: (pid: string, status?: string) =>
    api.get<ReaderPromise[]>(`/projects/${pid}/reader_promises/`, {
      params: status ? { status } : undefined,
    }),

  /**
   * 创建新承诺。
   * @param pid - 项目 ID
   * @param data - 承诺内容，promise_text 必填
   */
  create: (pid: string, data: Partial<ReaderPromise>) =>
    api.post<ReaderPromise>(`/projects/${pid}/reader_promises/`, data),

  /**
   * 更新承诺字段（部分更新）——常用于标记 status=fulfilled/broken。
   * @param pid - 项目 ID
   * @param id - 承诺 ID
   * @param data - 要更新的字段
   */
  update: (pid: string, id: string, data: Partial<ReaderPromise>) =>
    api.patch<ReaderPromise>(`/projects/${pid}/reader_promises/${id}`, data),

  /** 删除承诺（谨慎使用，一般用 status=broken 代替）。 */
  delete: (pid: string, id: string) =>
    api.delete(`/projects/${pid}/reader_promises/${id}`),
}

// ── Locations（空间连续性机制） ───────────────────────────────

/**
 * 地点（Location）CRUD。
 * 后端路由前缀：/api/v1/projects/{pid}/locations
 *
 * sensory_signature 是核心字段：写章时注入 prompt 防止感知漂移。
 * 依赖：Character.current_location（文本）在复盘后自动更新，无需本接口维护。
 */
export const locationsApi = {
  /**
   * 列出项目所有地点，按 sort_order + name 升序。
   * @param pid - 项目 ID
   */
  list: (pid: string) =>
    api.get<Location[]>(`/projects/${pid}/locations`),

  /**
   * 创建地点。
   * @param pid - 项目 ID
   * @param data - 地点数据，name 必填
   */
  create: (pid: string, data: Omit<Partial<Location>, 'id' | 'project_id' | 'created_at' | 'updated_at'>) =>
    api.post<Location>(`/projects/${pid}/locations`, data),

  /**
   * 更新地点字段（部分更新）。
   * @param pid - 项目 ID
   * @param id - 地点 ID
   * @param data - 要更新的字段
   */
  update: (pid: string, id: string, data: Partial<Location>) =>
    api.patch<Location>(`/projects/${pid}/locations/${id}`, data),

  /** 删除地点（解除关联后再删）。 */
  delete: (pid: string, id: string) =>
    api.delete(`/projects/${pid}/locations/${id}`),
}

// ── Scenes（三层调度：分场） ───────────────────────────────

/**
 * 分场 API——读取某 OutlineNode 或 Chapter 的场景蓝图。
 * 后端路由：GET /api/v1/projects/{pid}/scenes/
 */
export const scenesApi = {
  /**
   * 列出某 outline_node_id（chapter_plan）或 chapter_id 下的所有场景，按 order 升序。
   * @param pid - 项目 ID
   * @param params - 过滤条件，至少传 outline_node_id 或 chapter_id 其一
   */
  list: (pid: string, params: { outline_node_id?: string; chapter_id?: string }) =>
    api.get<Scene[]>(`/projects/${pid}/scenes/`, { params }),

  /**
   * 批量创建分场——AI 生成计划后调用，replace_existing=true 会先清空旧记录。
   * @param pid - 项目 ID
   * @param outline_node_id - 批次归属节点 ID（同时用于清空旧场景）
   * @param scenes - AI 返回的场景列表（字段与 SceneCreate 对齐）
   */
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
}

// ── Outline ───────────────────────────────────────────
export const outlineApi = {
  getTree: (pid: string) => api.get(`/projects/${pid}/outline/`),
  /** 只读：从大纲章节计划「人物变化」聚合主角境界新高节点 */
  protagonistRealmTimeline: (pid: string) =>
    api.get(`/projects/${pid}/outline/protagonist-realm-timeline`),
  create: (pid: string, data: any) => api.post(`/projects/${pid}/outline/`, data),
  update: (pid: string, id: string, data: any) => api.patch(`/projects/${pid}/outline/${id}`, data),
  delete: (pid: string, id: string) => api.delete(`/projects/${pid}/outline/${id}`),
  /** 删除全部章节计划节点（保留卷/篇）；写作章节仅解除绑定 */
  clearChapterPlans: (pid: string) =>
    api.delete<{ deleted: number }>(`/projects/${pid}/outline/chapter-plans`),
  // AI 展开大纲 — SSE，使用原生 fetch（见 OutlineAIPanel.tsx）
  aiExpandUrl: (pid: string) => `/api/v1/projects/${pid}/outline/ai-expand`,
  // 确认写入大纲树
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
  /** 本章历次复盘落库审计（含完整 payload，可追溯） */
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

// ── Bootstrap（一句话生成）────────────────────────────
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
  cancel: (runId: string) => api.post<{ ok: boolean; run_id: string; status: string }>(`/bootstrap/runs/${runId}/cancel`),
}

// ── AI ────────────────────────────────────────────────
// ── LLM / 智能体（只读）────────────────────────────────────
export const llmApi = {
  overview: () => api.get<LlmOverview>('/llm/overview'),
}

export const aiApi = {
  qualityCheck: (pid: string, data: any) => api.post(`/projects/${pid}/ai/quality-check`, data),
  /**
   * 已有项目：AI 生成世界观设定卡（整套覆盖 / 仅补蓝图缺失 / 追加自拟标题卡）。
   * 线路由 ``model_profile`` 与 ``llm_provider_id`` 决定，与 Bootstrap 一致。
   *
   * @param pid 项目 id
   * @param data.mode ``blueprint_replace`` 会先删光本项目设定卡再按标准蓝图重建
   */
  generateWorldSettings: (
    pid: string,
    data: {
      mode: 'blueprint_replace' | 'blueprint_fill_missing' | 'append'
      user_hint?: string
      append_count?: number
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    },
  ) =>
    api.post<{
      mode: string
      created_count: number
      message?: string | null
      settings: WorldSetting[]
    }>(`/projects/${pid}/ai/world-settings/generate`, data),
  /**
   * 质量门控写作流 URL（原生 fetch + SSE，不走 axios）。
   * 对应后端 POST /ai/gated-draft-stream，事件协议见 draftAssistSse.ts。
   */
  gatedDraftStreamUrl: (pid: string) => `/api/v1/projects/${pid}/ai/gated-draft-stream`,
  /** 质量债务：模型给出原文摘录→替换文，服务端唯一匹配后写回（微调，非整章流式） */
  qualityDebtMicroFix: (
    pid: string,
    data: {
      quality_debt_id: string
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    },
  ) => api.post<{
    chapter: Chapter
    rationale?: string
    original_excerpt?: string
    replacement_excerpt?: string
  }>(`/projects/${pid}/ai/quality-debt-micro-fix`, data),
  listChatMessages: (
    pid: string,
    params: { context_type: 'outline' | 'writing' | 'general'; chapter_id?: string },
  ) => {
    const q = new URLSearchParams({ context_type: params.context_type })
    if (params.chapter_id) q.set('chapter_id', params.chapter_id)
    return api.get<AiChatMessage[]>(`/projects/${pid}/ai/chat/messages?${q.toString()}`)
  },
  chatStreamUrl: (pid: string) => `/api/v1/projects/${pid}/ai/chat/stream`,
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
    llm_provider_id?: string
    force_refresh?: boolean
    /** 仅读服务端复盘缓存，不调用 LLM */
    cache_only?: boolean
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
      storyline_name?: string
      status?: string
      append_beat?: string
    }>
    memory_updates?: Array<{
      memory_type?: 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict'
      title?: string
      content: string
      tags?: string[]
    }>
    asset_updates?: Record<string, unknown>
    new_characters?: Array<{
      name: string
      role?: string
      gender?: string
      age?: string
      faction?: string
      personality?: string
      motivation?: string
      background?: string
      current_realm?: string
      current_status?: string
      current_location?: string
      arc_scope?: string
      author_notes?: string
    }>
    chapter_index?: {
      story_day?: string
      core_events?: Array<Record<string, unknown> | string>
      first_appearances?: Array<Record<string, unknown>>
      actual_foreshadows_laid?: Array<Record<string, unknown>>
      actual_foreshadows_resolved?: Array<Record<string, unknown>>
      ending_hook?: string
      hook_strength?: number
      continuity_notes?: Array<Record<string, unknown> | string>
    }
    notes?: string
    apply_source?: 'queue_auto' | 'manual_tab'
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

  chapterCoherenceApplyPreview: (
    pid: string,
    data: {
      report_id: string
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-apply/preview`, data),

  chapterCoherenceApplyCommit: (
    pid: string,
    data: {
      report_id: string
      revisions: Array<{ chapter_id: string; revised_content: string }>
    }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-apply/commit`, data),

  /** 写前预警：传入本章计划，对照记忆/连续性/伏笔台账，输出矛盾风险 */
  preWriteWarning: (
    pid: string,
    data: {
      chapter_id: string
      chapter_plan_summary: string
      chapter_number?: number
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    },
  ) => api.post<{
    ok: boolean
    risk_count: number
    risks: Array<{ type: string; severity: string; description: string; suggested_fix: string }>
    reminders: string[]
    error?: string
    record_id?: string
  }>(`/projects/${pid}/ai/pre-write-warning`, data),

  preWriteWarningHistory: (pid: string, chapterId: string, limit = 30) =>
    api.get<
      Array<{
        id: string
        chapter_id: string
        chapter_number: number
        chapter_plan_summary: string
        model_profile: string
        result: {
          ok: boolean
          risk_count: number
          risks: Array<{ type: string; severity: string; description: string; suggested_fix: string }>
          reminders: string[]
          error?: string
        }
        created_at: string | null
      }>
    >(`/projects/${pid}/ai/pre-write-warning/history`, {
      params: { chapter_id: chapterId, limit },
    }),

  /**
   * 章节综合分析（推荐入口）：单次 LLM 调用，结果写入 DB，返回该章历次均值统计。
   * 每次调用都会新增一条历史记录，多跑几次可获得更稳定的 avg_score。
   * @param pid - 项目 ID
   * @param chapterId - 章节 ID
   * @param modelProfile - 模型线路
   * @param llmProviderId - 可选远程线路 provider ID
   */
  chapterAnalysis: (
    pid: string,
    chapterId: string,
    modelProfile: 'local' | 'gemini' = 'local',
    llmProviderId?: string,
  ) => api.post<ChapterAnalysisStats>(`/projects/${pid}/ai/chapter-analysis`, {
    chapter_id: chapterId,
    model_profile: modelProfile,
    ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
  }),

  /**
   * 批量读取项目所有章节的分析均值统计（无 AI 调用）。
   * 供节奏地图页面加载时恢复历史数据。
   * @param pid - 项目 ID
   */
  chapterAnalysisStats: (pid: string) =>
    api.get<ChapterAnalysisStats[]>(`/projects/${pid}/ai/chapter-analysis-stats`),

  /**
   * 故事线悬空检测：无 AI，纯逻辑，找出 N 章以上未出现的活跃故事线。
   * @param pid - 项目 ID
   * @param gapThreshold - 悬空阈值章数，默认 8
   */
  storylineGaps: (pid: string, gapThreshold = 8) =>
    api.get<StorylineGapsResult>(`/projects/${pid}/ai/storyline-gaps`, {
      params: { gap_threshold: gapThreshold },
    }),

  // ── 独立端点（保留，供其他场景单独调用） ──────────────────────────────────

  /** @internal 仅追读模拟（推荐用 chapterAnalysis） */
  readerSimulation: (
    pid: string,
    chapterId: string,
    modelProfile: 'local' | 'gemini' = 'local',
    llmProviderId?: string,
  ) => api.post<ReaderSimulationResult>(`/projects/${pid}/ai/reader-simulation`, {
    chapter_id: chapterId,
    model_profile: modelProfile,
    ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
  }),

  /** @internal 仅钩子检测（推荐用 chapterAnalysis） */
  hookCheck: (
    pid: string,
    chapterId: string,
    modelProfile: 'local' | 'gemini' = 'local',
    llmProviderId?: string,
  ) => api.post<HookCheckResult>(`/projects/${pid}/ai/hook-check`, {
    chapter_id: chapterId,
    model_profile: modelProfile,
    ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
  }),

  /**
   * 章纲 → 分场计划（AI 生成，不自动入库）。
   * 调用方负责将返回的 scenes 批量写入 scenesApi.batchCreate。
   *
   * @param pid - 项目 ID
   * @param outlineNodeId - chapter_plan 节点 ID（用于读取 prev_directives）
   * @param chapterTitle - 章节标题，传入 OutlineNode.title
   * @param chapterSummary - 章节摘要，传入 OutlineNode.summary
   * @param modelProfile - 模型线路
   * @param llmProviderId - 远程线路 provider ID（可选）
   */
  scenePlan: (
    pid: string,
    outlineNodeId: string,
    chapterTitle: string,
    chapterSummary: string,
    modelProfile: 'local' | 'gemini' = 'local',
    llmProviderId?: string,
  ) => api.post<{ scenes: Array<Record<string, unknown>>; total_word_budget: number; notes?: string }>(
    `/projects/${pid}/ai/scene-plan`,
    {
      outline_node_id: outlineNodeId,
      chapter_title: chapterTitle,
      chapter_summary: chapterSummary,
      model_profile: modelProfile,
      ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
    },
  ),
}
