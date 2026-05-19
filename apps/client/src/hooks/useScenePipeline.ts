/**
 * @file useScenePipeline.ts — 三层调度（章纲→分场→正文→缝合）的状态管理 hook。
 *
 * 使用方式：
 * ```tsx
 * const pipeline = useScenePipeline({ projectId, outlineNodeId, chapterId, modelProfile, llmProviderId })
 * ```
 *
 * 依赖：
 *   - `api/scene.ts` 中的四个 HTTP 函数
 *   - `store/index.ts` 中的 `upsertChapter`（缝合后同步 store）
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { fetchScenes, planAndSave, streamDraft, stitch } from '../api/scene'
import { useAppStore, modelProfileFromRoute } from '../store'
import type { Scene } from '../types'

// ── 类型 ─────────────────────────────────────────────────────

/** 单场起草的实时状态。 */
export interface SceneDraftState {
  /** idle=未开始，streaming=进行中，done=已完成，error=出错 */
  status: 'idle' | 'streaming' | 'done' | 'error'
  /** 已积累的字数（streaming 时实时更新） */
  charCount: number
  /** 错误信息（status=error 时非空） */
  errorMsg?: string
}

export interface UseScenePipelineOptions {
  projectId: string
  /** chapter_plan 节点 ID；为空时不加载场景 */
  outlineNodeId: string | undefined
  /** 目标章节 ID；缝合时写入 chapter.content */
  chapterId: string | undefined
  /** 模型线路标识（"local" | "gemini"） */
  modelProfile: string
  llmProviderId?: string | null
}

export interface UseScenePipelineReturn {
  /** 当前分场列表，按 order 排序 */
  scenes: Scene[]
  /** 是否正在请求生成分场计划 */
  planLoading: boolean
  /** 各场的起草状态 Map，key = scene.id */
  draftStates: Record<string, SceneDraftState>
  /** 是否正在执行缝合 */
  stitching: boolean
  /** 是否有任意场景正在流式起草 */
  anyDrafting: boolean
  /** 所有分场是否均已写完 */
  allWritten: boolean
  /** 重新从服务端加载分场列表 */
  reload: () => Promise<void>
  /** AI 生成分场计划（替换旧场景） */
  generatePlan: () => Promise<void>
  /**
   * 起草单个场景。
   * @param sceneId 目标 Scene ID
   */
  draftScene: (sceneId: string) => Promise<void>
  /**
   * 顺序起草所有 status=planned 的场景（已写跳过）。
   * 顺序执行以便每场能利用上一场正文作为上下文。
   */
  draftAll: () => Promise<void>
  /**
   * 将所有 written 场景缝合写入章节正文。
   * 缝合完成后触发 onStitchDone 回调，供父组件更新编辑器。
   *
   * @param onStitchDone 缝合成功时调用，参数为缝合后的 content_preview
   */
  stitch: (onStitchDone?: (wordCount: number) => void) => Promise<void>
}

// ── Hook 实现 ─────────────────────────────────────────────────

/**
 * 三层调度状态管理 hook。
 *
 * @param options 配置选项（projectId / outlineNodeId / chapterId / modelProfile / llmProviderId）
 * @returns       场景列表、各类加载状态和操作函数
 */
export function useScenePipeline(options: UseScenePipelineOptions): UseScenePipelineReturn {
  const { projectId, outlineNodeId, chapterId, modelProfile, llmProviderId } = options

  const [scenes, setScenes] = useState<Scene[]>([])
  const [planLoading, setPlanLoading] = useState(false)
  const [draftStates, setDraftStates] = useState<Record<string, SceneDraftState>>({})
  const [stitching, setStitching] = useState(false)

  // 防止 outlineNodeId 切换时旧请求覆盖新状态
  const loadingNodeRef = useRef<string | undefined>(undefined)

  // ── 加载分场列表 ──────────────────────────────────────────

  const reload = useCallback(async () => {
    if (!outlineNodeId) { setScenes([]); return }
    loadingNodeRef.current = outlineNodeId
    try {
      const data = await fetchScenes(projectId, outlineNodeId)
      if (loadingNodeRef.current === outlineNodeId) {
        setScenes(data)
        // 已写完的场景初始化为 done 状态
        setDraftStates(prev => {
          const next = { ...prev }
          data.forEach(s => {
            if (s.status === 'written' && !next[s.id]) {
              next[s.id] = { status: 'done', charCount: s.actual_word_count ?? 0 }
            }
          })
          return next
        })
      }
    } catch (err) {
      toast.error('加载分场列表失败')
      console.error(err)
    }
  }, [projectId, outlineNodeId])

  useEffect(() => { void reload() }, [reload])

  // ── 生成分场计划 ──────────────────────────────────────────

  const generatePlan = useCallback(async () => {
    if (!outlineNodeId) { toast.error('当前章节未挂载大纲节点'); return }
    setPlanLoading(true)
    try {
      const newScenes = await planAndSave(projectId, {
        outline_node_id: outlineNodeId,
        chapter_id: chapterId ?? null,
        model_profile: modelProfile,
        llm_provider_id: llmProviderId ?? null,
      })
      setScenes(newScenes)
      setDraftStates({})
      toast.success(`已生成 ${newScenes.length} 个分场`)
    } catch (err) {
      toast.error(`生成分场失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setPlanLoading(false)
    }
  }, [projectId, outlineNodeId, chapterId, modelProfile, llmProviderId])

  // ── 起草单场 ─────────────────────────────────────────────

  /** 安全地合并更新单场 draftState。 */
  const patchDraftState = useCallback((sceneId: string, patch: Partial<SceneDraftState>) => {
    setDraftStates(prev => {
      const base: SceneDraftState = prev[sceneId] ?? { status: 'idle', charCount: 0 }
      return { ...prev, [sceneId]: { ...base, ...patch } }
    })
  }, [])

  const draftScene = useCallback(async (sceneId: string) => {
    patchDraftState(sceneId, { status: 'streaming', charCount: 0 })
    try {
      await streamDraft(projectId, sceneId, modelProfile, llmProviderId, {
        onChunk: (text) => {
          // 累加字数：必须用函数式更新读取最新 charCount
          setDraftStates(prev => {
            const cur = prev[sceneId] ?? { status: 'streaming' as const, charCount: 0 }
            return { ...prev, [sceneId]: { ...cur, charCount: cur.charCount + text.length } }
          })
        },
        onSaved: (_id, wordCount) => {
          patchDraftState(sceneId, { status: 'done', charCount: wordCount })
          setScenes(prev =>
            prev.map(s => s.id === sceneId ? { ...s, status: 'written', actual_word_count: wordCount } : s)
          )
        },
        onError: (msg) => {
          patchDraftState(sceneId, { status: 'error', errorMsg: msg })
          toast.error(`场景起草失败：${msg.slice(0, 80)}`)
        },
      })
    } catch (err) {
      patchDraftState(sceneId, { status: 'error', errorMsg: String(err) })
      toast.error('场景起草发生未知错误')
    }
  }, [projectId, modelProfile, llmProviderId, patchDraftState])

  // ── 顺序起草全部 ──────────────────────────────────────────

  const draftAll = useCallback(async () => {
    const targets = scenes.filter(s => s.status !== 'written')
    if (targets.length === 0) { toast('所有分场已写完'); return }
    for (const scene of targets) {
      await draftScene(scene.id)
    }
  }, [scenes, draftScene])

  // ── 缝合 → chapter.content ───────────────────────────────

  const stitchFn = useCallback(async (onStitchDone?: (wordCount: number) => void) => {
    if (!outlineNodeId) { toast.error('未挂载大纲节点'); return }
    setStitching(true)
    try {
      const result = await stitch(projectId, outlineNodeId, chapterId ?? null)
      // 缝合成功后通知父组件刷新章节内容
      onStitchDone?.(result.word_count)
      toast.success(`缝合完成，共 ${result.word_count} 字（${result.scene_count} 场）`)
    } catch (err) {
      toast.error(`缝合失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setStitching(false)
    }
  }, [projectId, outlineNodeId, chapterId])

  // ── 派生状态 ──────────────────────────────────────────────

  const anyDrafting = Object.values(draftStates).some(s => s.status === 'streaming')
  const allWritten = scenes.length > 0 && scenes.every(s => s.status === 'written')

  return {
    scenes,
    planLoading,
    draftStates,
    stitching,
    anyDrafting,
    allWritten,
    reload,
    generatePlan,
    draftScene,
    draftAll,
    stitch: stitchFn,
  }
}
