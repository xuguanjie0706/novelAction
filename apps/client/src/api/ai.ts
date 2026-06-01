import type {
  AiChatMessage,
  Chapter,
  ChapterAnalysisStats,
  HookCheckResult,
  LlmOverview,
  RagQueryResponse,
  RagRetrievalLog,
  ReaderSimulationResult,
  StorylineGapsResult,
  WorldSetting,
} from '../types'
import { api, DEBRIEF_REQUEST_TIMEOUT_MS } from './base'

// ── LLM ──────────────────────────────────────────────
export const llmApi = {
  overview: () => api.get<LlmOverview>('/llm/overview'),
}

// ── AI ────────────────────────────────────────────────
export const aiApi = {
  qualityCheck: (pid: string, data: any) => api.post(`/projects/${pid}/ai/quality-check`, data),
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
  gatedDraftStreamUrl: (pid: string) => `/api/v1/projects/${pid}/ai/gated-draft-stream`,
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
  qualityCheckMicroFix: (
    pid: string,
    data: {
      chapter_id: string
      suggestions?: string[]
      issues?: string[]
      focus_suggestion_index?: number
      author_notes?: string
      model_profile?: 'local' | 'gemini'
      llm_provider_id?: string
    },
  ) => api.post<{
    chapter: Chapter
    rationale?: string
    original_excerpt?: string
    replacement_excerpt?: string
  }>(`/projects/${pid}/ai/quality-check-micro-fix`, data),
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
  listMemory: (pid: string, params?: { type?: string; sort_by?: string }) => {
    const q = new URLSearchParams()
    if (params?.type) q.set('memory_type', params.type)
    if (params?.sort_by) q.set('sort_by', params.sort_by)
    const qs = q.toString()
    return api.get(`/projects/${pid}/ai/memory${qs ? `?${qs}` : ''}`)
  },
  detectConflicts: (pid: string, params?: { model_profile?: 'local' | 'gemini'; llm_provider_id?: string }) => {
    const q = new URLSearchParams()
    q.set('model_profile', params?.model_profile ?? 'gemini')
    if (params?.llm_provider_id) q.set('llm_provider_id', params.llm_provider_id)
    return api.post<import('../types').MemoryConflictReport>(
      `/projects/${pid}/ai/memory/detect-conflicts?${q.toString()}`,
    )
  },
  ragQuery: (
    pid: string,
    data: {
      q: string
      top_k?: number
      max_chapter?: number
      types?: string
      chapter_id?: string
      include_injected_summary?: boolean
    },
  ) => api.post<RagQueryResponse>(`/projects/${pid}/ai/memory/rag-query`, data),
  listRagLogs: (
    pid: string,
    params?: { chapter_id?: string; source?: string; limit?: number },
  ) => {
    const q = new URLSearchParams()
    if (params?.chapter_id) q.set('chapter_id', params.chapter_id)
    if (params?.source) q.set('source', params.source)
    if (params?.limit != null) q.set('limit', String(params.limit))
    const qs = q.toString()
    return api.get<RagRetrievalLog[]>(`/projects/${pid}/ai/memory/rag-logs${qs ? `?${qs}` : ''}`)
  },
  getRagLog: (pid: string, logId: string) =>
    api.get<RagRetrievalLog>(`/projects/${pid}/ai/memory/rag-logs/${logId}`),
  autoDebrief: (pid: string, data: {
    chapter_id: string
    model_profile?: 'local' | 'gemini'
    llm_provider_id?: string
    force_refresh?: boolean
    cache_only?: boolean
  }) => api.post(`/projects/${pid}/ai/auto-debrief`, data, { timeout: DEBRIEF_REQUEST_TIMEOUT_MS }),
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
      actual_tension?: number
      beat_match_score?: number
      crossover_executed?: boolean
      screen_time_words?: number
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
    new_reader_promises?: Array<{
      promise_text: string
      promise_type?: string
      expected_within_chapters?: number
      priority?: number
      audience_aware?: number
    }>
    fulfilled_promise_texts?: string[]
    fulfilled_promise_ids?: string[]
    next_chapter_directives?: Array<{
      outline_node_id?: string
      patch?: Record<string, unknown>
      reason?: string
    }>
    speech_kit_updates?: Array<{
      character_id?: string
      character_name?: string
      new_signature_words?: string[]
      new_sample_dialogues?: string[]
      evolution_note?: string
    }>
    model_profile?: 'local' | 'gemini'
    llm_provider_id?: string
  }) => api.post(`/projects/${pid}/ai/chapter-debrief`, data, { timeout: DEBRIEF_REQUEST_TIMEOUT_MS }),
  chapterCoherenceCheck: (
    pid: string,
    data: { chapter_ids: string[]; model_profile?: 'local' | 'gemini'; llm_provider_id?: string }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-check`, data),
  saveChapterCoherenceReport: (
    pid: string,
    data: { name?: string; model_profile?: 'local' | 'gemini'; selected_chapter_ids: string[]; result: Record<string, any> }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-reports`, data),
  listChapterCoherenceReports: (pid: string, limit = 20) =>
    api.get(`/projects/${pid}/ai/chapter-coherence-reports?limit=${limit}`),
  chapterCoherenceApplyPreview: (
    pid: string,
    data: { report_id: string; model_profile?: 'local' | 'gemini'; llm_provider_id?: string }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-apply/preview`, data),
  chapterCoherenceApplyCommit: (
    pid: string,
    data: { report_id: string; revisions: Array<{ chapter_id: string; revised_content: string }> }
  ) => api.post(`/projects/${pid}/ai/chapter-coherence-apply/commit`, data),
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
    >(`/projects/${pid}/ai/pre-write-warning/history`, { params: { chapter_id: chapterId, limit } }),
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
  chapterAnalysisStats: (pid: string) =>
    api.get<ChapterAnalysisStats[]>(`/projects/${pid}/ai/chapter-analysis-stats`),
  storylineGaps: (pid: string, gapThreshold = 8) =>
    api.get<StorylineGapsResult>(`/projects/${pid}/ai/storyline-gaps`, {
      params: { gap_threshold: gapThreshold },
    }),
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
