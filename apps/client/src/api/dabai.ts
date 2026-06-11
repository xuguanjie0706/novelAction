/**
 * @file api/dabai.ts — 大白文独立分支 API 客户端。
 * 复用全局 axios 实例（携带 Bearer token），调用 /api/v1/dabai。
 * 生成可能较慢（真实 LLM 8 步），单独放宽超时。
 */
import { api } from './base'
import type {
  DabaiGenerateRequest,
  DabaiProjectDetail,
  DabaiProjectSummary,
  DabaiStreamEvent,
} from '../types/dabai'

/** 生成请求最长 10 分钟（真实 LLM 多步）。 */
const DABAI_GENERATE_TIMEOUT_MS = 600_000

const AUTH_TOKEN_KEY = 'novelAction:auth-token'

/** 通用：POST 一个 SSE 端点并逐条回调 data: 行。 */
async function streamSse<T>(
  url: string,
  body: unknown,
  onEvent: (ev: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = (() => { try { return localStorage.getItem(AUTH_TOKEN_KEY) } catch { return null } })()
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`请求失败（HTTP ${res.status}）`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      try { onEvent(JSON.parse(line.slice(5).trim()) as T) } catch { /* 跳过半包 */ }
    }
  }
}

/** SSE 流式生成 bootstrap：边生成边推 8 步进度。 */
export function dabaiGenerateStream(
  payload: DabaiGenerateRequest,
  onEvent: (ev: DabaiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse('/api/v1/dabai/projects/stream', payload, onEvent, signal)
}

/** 按卷展开章纲请求体（线路默认 gemini）。 */
export interface DabaiExpandRequest {
  model_profile?: 'local' | 'gemini'
  llm_provider_id?: string
  /** 满卷删旧重做（未满卷为增量补全，无需此参数）。 */
  force?: boolean
}

/** 按卷展开章纲 SSE 事件。 */
export type DabaiExpandEvent =
  | { event: 'expand_start'; volume_number: number; chapter_from: number; chapter_to: number; mode: 'full' | 'incremental' | 'force' }
  | { event: 'chapter_batch'; batch_start: number; batch_end: number; total: number }
  | { event: 'linter_done'; status?: string; score?: number | null; issue_count?: number; critical_count?: number }
  | { event: 'done'; volume_number: number; created: number }
  | { event: 'error'; message: string; code?: string }

/**
 * SSE 流式按卷展开章纲（写作期懒展开：卷2+ 全量 / 未满卷增量补全）。
 * 后端边生成边落库，中断不丢已生成批次；done 后调用方需重拉项目详情。
 */
export function dabaiExpandVolumeStream(
  projectId: string,
  volumeId: string,
  payload: DabaiExpandRequest,
  onEvent: (ev: DabaiExpandEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse(
    `/api/v1/dabai/projects/${projectId}/volumes/${volumeId}/expand-chapters`,
    payload, onEvent, signal,
  )
}

/** 章节正文写作请求体。 */
export interface DabaiDraftRequest {
  model_profile?: 'local' | 'gemini'
  llm_provider_id?: string
}

/** SSE 流式事件：写前导演单（预警）→ 正文逐段 → 写后自动质检/复盘。 */
export type DabaiDraftEvent =
  | { event: 'chunk'; delta: string }
  | { event: 'done'; chapter_id: string; word_count: number }
  | { event: 'error'; message: string }
  | { event: 'pre_warn_running'; dabai_mode: boolean }
  | import('../types/dabaiLab').DabaiPreWarnDoneEvent
  | { event: 'quality_running'; dabai_mode: boolean }
  | {
      event: 'quality_done'; ok: boolean; status?: string
      overall_score?: number; llm_status?: string; error?: string
    }
  | { event: 'debrief_running'; dabai_mode: boolean }
  | {
      event: 'debrief_done'; ok: boolean; summary?: string; memory_count?: number
      new_clues?: string[]; resolved_clues?: string[]
      asset_changes?: string[]; relation_changes?: string[]; error?: string
    }

/** 流式写一章正文。 */
export function dabaiDraftStream(
  projectId: string,
  chapterId: string,
  payload: DabaiDraftRequest,
  onEvent: (ev: DabaiDraftEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse(
    `/api/v1/dabai/projects/${projectId}/chapters/${chapterId}/draft/stream`,
    payload, onEvent, signal,
  )
}

export const dabaiApi = {
  /** 一句话 → 生成 + 落库，返回完整详情。 */
  generate(payload: DabaiGenerateRequest) {
    return api.post<DabaiProjectDetail>('/dabai/projects', payload, {
      timeout: DABAI_GENERATE_TIMEOUT_MS,
    })
  },

  /** 当前用户的大白文项目列表（摘要）。 */
  list() {
    return api.get<{ items: DabaiProjectSummary[]; total: number }>('/dabai/projects')
  },

  /** 单个项目完整详情。 */
  get(id: string) {
    return api.get<DabaiProjectDetail>(`/dabai/projects/${id}`)
  },

  /** 删除项目。 */
  remove(id: string) {
    return api.delete<{ ok: boolean; deleted: string }>(`/dabai/projects/${id}`)
  },

  /** 全书章纲 linter 重跑（读库最新章纲，写回 linter_report）。 */
  relintOutline(id: string) {
    return api.post<{ linter_report: DabaiProjectDetail['linter_report'] }>(
      `/dabai/projects/${id}/relint-outline`,
    )
  },
}
