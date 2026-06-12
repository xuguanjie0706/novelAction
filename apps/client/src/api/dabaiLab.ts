/**
 * @file api/dabaiLab.ts — dabai 实验书架写作期 AI 端点客户端（质检/复盘/记忆/线索/预警）。
 * 复用全局 axios 实例（携带 Bearer token），调用 /api/v1/dabai。
 * 质检与复盘走真实 LLM，单独放宽超时。
 */
import { api } from './base'
import type {
  DabaiLabAsset,
  DabaiLabClue,
  DabaiLabDebriefResult,
  DabaiLabMemory,
  DabaiLabQualityReport,
  DabaiLabRelation,
  DabaiPreWarnRecord,
  DabaiScenePlanRecord,
} from '../types/dabaiLab'

/** LLM 端点最长 3 分钟。 */
const LAB_AI_TIMEOUT_MS = 180_000

/** 质检/复盘通用请求体（模型线路沿用写章约定）。 */
export interface DabaiLabAiRequest {
  model_profile?: 'local' | 'gemini'
  llm_provider_id?: string
  /** 仅质检用：rules=只跑规则层（快速、零 LLM 成本）。 */
  mode?: 'rules' | 'full'
}

export const dabaiLabApi = {
  /** 跑一次章节质检（规则+LLM），报告落库并返回。 */
  qualityCheck(projectId: string, chapterId: string, payload: DabaiLabAiRequest) {
    return api.post<DabaiLabQualityReport>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/quality-check`,
      payload, { timeout: LAB_AI_TIMEOUT_MS },
    )
  },

  /** 本章最新落库质检报告。 */
  getQualityReport(projectId: string, chapterId: string) {
    return api.get<{ report: DabaiLabQualityReport | null; created_at: string | null }>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/quality-report`,
    )
  },

  /** 章末复盘：提取记忆与线索并落库（幂等可重跑）。 */
  debrief(projectId: string, chapterId: string, payload: DabaiLabAiRequest) {
    return api.post<DabaiLabDebriefResult>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/debrief`,
      payload, { timeout: LAB_AI_TIMEOUT_MS },
    )
  },

  /** 记忆条目列表（可按章过滤）。 */
  listMemory(projectId: string, chapterId?: string) {
    return api.get<{ items: DabaiLabMemory[]; total: number }>(
      `/dabai/projects/${projectId}/memory`,
      { params: chapterId ? { chapter_id: chapterId } : {} },
    )
  },

  /** 线索台账列表（可按状态过滤）。 */
  listClues(projectId: string, status?: 'open' | 'resolved' | 'dropped') {
    return api.get<{ items: DabaiLabClue[]; total: number }>(
      `/dabai/projects/${projectId}/clues`,
      { params: status ? { status } : {} },
    )
  },

  /** 手动改线索状态（误判纠偏）。 */
  patchClue(
    projectId: string, clueId: string,
    body: { status: 'open' | 'resolved' | 'dropped'; chapter_resolved?: number },
  ) {
    return api.patch<{ ok: boolean; id: string; status: string }>(
      `/dabai/projects/${projectId}/clues/${clueId}`, body,
    )
  },

  /** 手动生成/重跑写前导演单（落库并返回）。 */
  runPreWarn(projectId: string, chapterId: string, payload: DabaiLabAiRequest) {
    return api.post<{
      record: DabaiPreWarnRecord | null
      ok: boolean
      brief_injected?: boolean
      error?: string
    }>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/pre-warn`,
      payload, { timeout: LAB_AI_TIMEOUT_MS },
    )
  },

  /** 本章最新落库导演单。 */
  getPreWarn(projectId: string, chapterId: string) {
    return api.get<{ record: DabaiPreWarnRecord | null }>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/pre-warn`,
    )
  },

  /** 手动生成/重跑分场调度单（落库并返回；须先有导演单）。 */
  runScenePlan(projectId: string, chapterId: string, payload: DabaiLabAiRequest) {
    return api.post<{
      record: DabaiScenePlanRecord | null
      ok: boolean
      scene_count?: number
      scene_names?: string[]
      error?: string
    }>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/scene-plan`,
      payload, { timeout: LAB_AI_TIMEOUT_MS },
    )
  },

  /** 本章最新落库分场调度单。 */
  getScenePlan(projectId: string, chapterId: string) {
    return api.get<{ record: DabaiScenePlanRecord | null }>(
      `/dabai/projects/${projectId}/chapters/${chapterId}/scene-plan`,
    )
  },

  /** 资产台账列表（可按状态/类型过滤）。 */
  listAssets(projectId: string, params?: { status?: string; kind?: string }) {
    return api.get<{ items: DabaiLabAsset[]; total: number }>(
      `/dabai/projects/${projectId}/assets`, { params: params ?? {} },
    )
  },

  /** 手动改资产状态。 */
  patchAsset(projectId: string, assetId: string, status: 'active' | 'consumed' | 'lost') {
    return api.patch<{ ok: boolean; id: string; status: string }>(
      `/dabai/projects/${projectId}/assets/${assetId}`, { status },
    )
  },

  /** 人物关系台账列表。 */
  listRelations(projectId: string) {
    return api.get<{ items: DabaiLabRelation[]; total: number }>(
      `/dabai/projects/${projectId}/relations`,
    )
  },

  /** 手动改人物态度（追加轨迹）。 */
  patchRelation(projectId: string, relationId: string, attitude: string, reason?: string) {
    return api.patch<{ ok: boolean; id: string; attitude: string }>(
      `/dabai/projects/${projectId}/relations/${relationId}`, { attitude, reason },
    )
  },
}
