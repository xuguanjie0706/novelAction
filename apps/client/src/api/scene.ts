/**
 * @file scene.ts — 三层调度 Scene Pipeline 的前端 HTTP 封装。
 *
 * 不混入 client.ts，保持领域隔离，由 useScenePipeline hook 调用。
 * SSE 解析遵循项目既有 draftAssistSse 模式（fetch + ReadableStream）。
 */

import type { Scene } from '../types'

const BASE = '/api/v1'

/** 从 localStorage 读取 JWT 并构造通用请求头。 */
function authHeaders(): HeadersInit {
  try {
    const token = localStorage.getItem('novelAction:auth-token')
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  } catch {
    return { 'Content-Type': 'application/json' }
  }
}

// ── 1. 查询分场列表 ──────────────────────────────────────────

/**
 * 查询某 outline_node 下的所有分场，按 order 升序。
 *
 * @param pid       项目 ID
 * @param nodeId    chapter_plan OutlineNode ID
 * @returns         Scene 列表（空数组表示尚未生成分场）
 */
export async function fetchScenes(pid: string, nodeId: string): Promise<Scene[]> {
  const res = await fetch(
    `${BASE}/projects/${pid}/scenes/?outline_node_id=${nodeId}`,
    { headers: authHeaders() },
  )
  if (!res.ok) throw new Error(`fetchScenes failed: ${res.status}`)
  return res.json()
}

// ── 2. 章纲 → 分场（生成 + 持久化）────────────────────────

export interface ScenePlanSaveRequest {
  outline_node_id: string
  chapter_id?: string | null
  word_target?: number
  model_profile?: string
  llm_provider_id?: string | null
}

/**
 * 调用 /ai/scene-plan-save：AI 生成分场计划并持久化到 scenes 表。
 * 旧分场会被替换（服务端保证幂等）。
 *
 * @returns 新生成的 scenes 列表
 */
export async function planAndSave(
  pid: string,
  req: ScenePlanSaveRequest,
): Promise<Scene[]> {
  const res = await fetch(`${BASE}/projects/${pid}/ai/scene-plan-save`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => '')
    throw new Error(msg || `scene-plan-save failed: ${res.status}`)
  }
  const data = await res.json()
  return data.scenes ?? []
}

// ── 3. 逐场起草（SSE）───────────────────────────────────────

export interface SceneDraftCallbacks {
  /** 每个文本 token 到达时调用 */
  onChunk: (text: string) => void
  /** 流结束且后端已写库时调用 */
  onSaved: (sceneId: string, wordCount: number) => void
  /** 发生错误时调用 */
  onError: (err: string) => void
}

/**
 * 向 /ai/scene-draft/stream 发起 SSE 请求，流式起草单个 Scene。
 * 后端在流结束时自动将正文写回 scene.content 并更新 status=written。
 *
 * @param pid           项目 ID
 * @param sceneId       目标 Scene ID
 * @param modelProfile  "local" | "gemini"
 * @param llmProviderId 指定 LlmProvider（可 null）
 * @param callbacks     chunk / saved / error 回调
 */
export async function streamDraft(
  pid: string,
  sceneId: string,
  modelProfile: string,
  llmProviderId: string | null | undefined,
  callbacks: SceneDraftCallbacks,
): Promise<void> {
  const res = await fetch(`${BASE}/projects/${pid}/ai/scene-draft/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      scene_id: sceneId,
      model_profile: modelProfile,
      llm_provider_id: llmProviderId ?? null,
    }),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => '')
    callbacks.onError(msg || `scene-draft/stream failed: ${res.status}`)
    return
  }
  if (!res.body) { callbacks.onError('响应无流式内容'); return }

  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''

  const processLine = (line: string) => {
    if (!line.startsWith('data: ')) return
    const raw = line.slice(6).trim()
    if (raw === '[DONE]') return
    try {
      const obj = JSON.parse(raw)
      if (obj.error) { callbacks.onError(obj.error); return }
      if (obj.text) callbacks.onChunk(obj.text)
      if (obj.event === 'saved') callbacks.onSaved(obj.scene_id, obj.word_count ?? 0)
    } catch { /* ignore malformed lines */ }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    lines.forEach(processLine)
  }
  buf.split('\n').forEach(processLine)
}

// ── 4. 场景缝合 → chapter.content ──────────────────────────

export interface SceneStitchResult {
  word_count: number
  scene_count: number
  chapter_id: string | null
  content_preview: string
}

/**
 * 调用 /ai/scene-stitch：将所有 status=written 的场景正文缝合写入 Chapter。
 *
 * @param pid       项目 ID
 * @param nodeId    outline_node_id（用于定位场景）
 * @param chapterId 目标章节（非空时写入 chapter.content）
 * @returns         缝合结果元数据
 */
export async function stitch(
  pid: string,
  nodeId: string,
  chapterId?: string | null,
): Promise<SceneStitchResult> {
  const res = await fetch(`${BASE}/projects/${pid}/ai/scene-stitch`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      outline_node_id: nodeId,
      chapter_id: chapterId ?? null,
    }),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => '')
    throw new Error(msg || `scene-stitch failed: ${res.status}`)
  }
  return res.json()
}
