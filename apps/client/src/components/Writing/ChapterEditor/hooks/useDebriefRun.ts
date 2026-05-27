/**
 * useDebriefRun.ts — 章节复盘 hook
 *
 * 职责：封装复盘面板的全部状态与操作：
 *   - applyAutoDebriefData：将 AI 返回的结构化数据预填到复盘表单
 *   - runAutoDebrief：调用 AI 自动复盘 API（LLM 路径）
 *   - loadDebriefTabCache：打开复盘 Tab 时仅读取服务端缓存（非 LLM）
 *   - submitDebrief：提交复盘数据到服务端，触发人物/故事线/资产/承诺更新
 *
 * 不包含：生成队列快照的 hydrate 逻辑（依赖 queueCommittedDebriefIds，由 index.tsx 保留）
 * 原因：队列快照需要感知 queueDebriefSnapshot 等多个 store 切片，放在 hook 里会
 * 导致不必要的订阅，index.tsx 的 useEffect 反而更直接。
 */
import { useCallback, useState } from 'react'
import toast from 'react-hot-toast'
import type { Editor } from '@tiptap/react'
import { chaptersApi, aiApi, storylinesApi, charactersApi } from '../../../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../../../store'
import type { StoryLine } from '../../../../types'
import { isUuidLike, hasHtmlTextContent } from '../utils'
import { formatApiError } from '../../../../utils/apiError'
import type { AutoDebriefResponse, NewCharacterSuggestion, StorylineBeatFormFields } from '../types'

interface UseDebriefRunOptions {
  projectId: string
  chapterId: string
  chapterContent: string
  editor: ReturnType<typeof import('@tiptap/react').useEditor> | null
  /** 当前 store 中的故事线列表，用于 name→UUID 解析 */
  storyLines: StoryLine[]
  upsertChapter: (ch: any) => void
  setStoryLines: (lines: StoryLine[]) => void
  setMemories: (memories: any[]) => void
  /** AI 建议预填后，自动打开侧栏并切换到复盘 Tab */
  onNavigateToDebriefTab: () => void
  /** 外部 saveTimer ref，flush 时需要 clearTimeout */
  saveTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | undefined>
}

// ─── 公共类型 ─────────────────────────────────────────────────────────────────

type CharUpdates = Record<string, {
  current_realm?: string
  realm_rank?: number
  current_location?: string
  current_status?: string
  add_skill_name?: string
  add_skill_mastery?: string
}>

type StorylineBeats = Record<string, StorylineBeatFormFields>

export interface UseDebriefRunReturn {
  debriefSubmitting: boolean
  autoDebriefing: boolean
  debriefCacheHydrating: boolean
  debriefFromQueueSnapshot: boolean
  setDebriefFromQueueSnapshot: React.Dispatch<React.SetStateAction<boolean>>
  debriefHistoryTick: number
  setDebriefHistoryTick: React.Dispatch<React.SetStateAction<number>>

  charUpdates: CharUpdates
  setCharUpdates: React.Dispatch<React.SetStateAction<CharUpdates>>
  storylineBeats: StorylineBeats
  setStorylineBeats: React.Dispatch<React.SetStateAction<StorylineBeats>>
  debriefNotes: string
  setDebriefNotes: (v: string) => void

  aiSuggestedCharIds: Set<string>
  aiSuggestedSlIds: Set<string>
  aiDebriefSummary: string
  aiSuggestedAssetUpdates: Record<string, unknown> | null
  aiNewCharacters: NewCharacterSuggestion[]
  setAiNewCharacters: React.Dispatch<React.SetStateAction<NewCharacterSuggestion[]>>
  aiChapterIndex: AutoDebriefResponse['chapter_index'] | null
  aiNewReaderPromises: NonNullable<AutoDebriefResponse['new_reader_promises']>
  setAiNewReaderPromises: React.Dispatch<React.SetStateAction<NonNullable<AutoDebriefResponse['new_reader_promises']>>>
  aiFulfilledPromiseTexts: string[]
  setAiFulfilledPromiseTexts: React.Dispatch<React.SetStateAction<string[]>>

  /**
   * 将 AI 复盘结构化输出预填到表单状态。
   * source='cache'：静默加载；source='llm'：弹成功 toast + 打开复盘 Tab。
   */
  applyAutoDebriefData: (
    data: AutoDebriefResponse,
    source: 'cache' | 'llm',
    opts?: { silent?: boolean },
  ) => void
  /** 调用 LLM 自动复盘（完整分析） */
  runAutoDebrief: (forceRefresh?: boolean) => Promise<void>
  /** 打开复盘 Tab 时仅读取服务端缓存（不调用 LLM） */
  loadDebriefTabCache: () => Promise<void>
  /** 提交复盘表单到服务端 */
  submitDebrief: (selectedAssetUpdates?: Record<string, unknown>) => Promise<void>
  /** 是否可以执行复盘（编辑器有内容 or DB 有内容） */
  debriefContentReady: boolean
  /** 清除所有 AI 预填状态（换章时调用） */
  resetDebriefState: () => void
}

/**
 * 章节复盘数据管理 hook。
 *
 * @param options - 见 UseDebriefRunOptions
 * @returns 复盘状态 + 操作函数，供 ChapterEditor/index.tsx 解构使用
 */
export function useDebriefRun({
  projectId,
  chapterId,
  chapterContent,
  editor,
  storyLines,
  upsertChapter,
  setStoryLines,
  setMemories,
  onNavigateToDebriefTab,
  saveTimerRef,
}: UseDebriefRunOptions): UseDebriefRunReturn {
  // ── UI 状态 ───────────────────────────────────────────────────────────────
  const [debriefSubmitting, setDebriefSubmitting] = useState(false)
  const [autoDebriefing, setAutoDebriefing] = useState(false)
  const [debriefCacheHydrating, setDebriefCacheHydrating] = useState(false)
  const [debriefFromQueueSnapshot, setDebriefFromQueueSnapshot] = useState(false)
  const [debriefHistoryTick, setDebriefHistoryTick] = useState(0)

  // ── 表单状态 ──────────────────────────────────────────────────────────────
  const [charUpdates, setCharUpdates] = useState<CharUpdates>({})
  const [storylineBeats, setStorylineBeats] = useState<StorylineBeats>({})
  const [debriefNotes, setDebriefNotes] = useState('')

  // ── AI 建议状态 ───────────────────────────────────────────────────────────
  const [aiSuggestedCharIds, setAiSuggestedCharIds] = useState<Set<string>>(new Set())
  const [aiSuggestedSlIds, setAiSuggestedSlIds] = useState<Set<string>>(new Set())
  const [aiDebriefSummary, setAiDebriefSummary] = useState('')
  const [aiSuggestedAssetUpdates, setAiSuggestedAssetUpdates] = useState<Record<string, unknown> | null>(null)
  const [aiNewCharacters, setAiNewCharacters] = useState<NewCharacterSuggestion[]>([])
  const [aiChapterIndex, setAiChapterIndex] = useState<AutoDebriefResponse['chapter_index'] | null>(null)
  const [aiNewReaderPromises, setAiNewReaderPromises] = useState<NonNullable<AutoDebriefResponse['new_reader_promises']>>([])
  const [aiFulfilledPromiseTexts, setAiFulfilledPromiseTexts] = useState<string[]>([])

  // ── 派生值 ────────────────────────────────────────────────────────────────

  /** 编辑器有内容 or 已保存内容非空时允许复盘 */
  const debriefContentReady = (editor && hasHtmlTextContent(editor.getHTML())) || hasHtmlTextContent(chapterContent)

  // ── 操作 ─────────────────────────────────────────────────────────────────

  /**
   * 清除所有 AI 预填与表单状态。
   * 切换章节时必须调用，避免旧章数据污染新章面板。
   */
  const resetDebriefState = useCallback(() => {
    setCharUpdates({})
    setStorylineBeats({})
    setDebriefNotes('')
    setAiDebriefSummary('')
    setAiSuggestedCharIds(new Set())
    setAiSuggestedSlIds(new Set())
    setAiSuggestedAssetUpdates(null)
    setAiNewCharacters([])
    setAiChapterIndex(null)
    setAiNewReaderPromises([])
    setAiFulfilledPromiseTexts([])
    setDebriefFromQueueSnapshot(false)
  }, [])

  /**
   * 将 AI 复盘响应体预填到表单状态。
   *
   * @param data - AutoDebriefResponse（来自 API 或缓存）
   * @param source - 'cache' 表示读缓存（静默），'llm' 表示完整分析（弹 toast + 导航）
   * @param opts.silent - 为 true 时跳过 toast 和 Tab 导航（供队列快照 hydrate 使用）
   */
  const applyAutoDebriefData = useCallback((
    data: AutoDebriefResponse,
    source: 'cache' | 'llm',
    opts?: { silent?: boolean },
  ) => {
    // 预填人物更新
    const newCharUpdates: CharUpdates = {}
    const suggestedCharIds = new Set<string>()
    for (const cu of data.character_updates || []) {
      const { character_id, character_name: _n, ...fields } = cu
      if (character_id && Object.keys(fields).some(k => (fields as any)[k])) {
        newCharUpdates[character_id] = fields
        suggestedCharIds.add(character_id)
      }
    }

    // 预填故事线更新（AI 可能返回名字而非 UUID，做 name→UUID 映射）
    const newSlBeats: StorylineBeats = {}
    const suggestedSlIds = new Set<string>()
    for (const su of data.storyline_updates || []) {
      const { storyline_id, storyline_name, ...fields } = su
      const hasFields = Object.entries(fields).some(([, v]) => {
        if (v === false) return true
        if (v === 0) return true
        return v !== undefined && v !== null && v !== ''
      })
      if (!hasFields) continue
      let resolvedId = storyline_id
      if (!isUuidLike(resolvedId)) {
        const byName = storyline_name
          ? storyLines.find(sl => sl.name === storyline_name)
          : undefined
        if (byName?.id && isUuidLike(byName.id)) resolvedId = byName.id
      }
      if (resolvedId && isUuidLike(resolvedId)) {
        newSlBeats[resolvedId] = fields
        suggestedSlIds.add(resolvedId)
      }
    }

    setCharUpdates(prev => ({ ...prev, ...newCharUpdates }))
    setStorylineBeats(prev => ({ ...prev, ...newSlBeats }))
    setAiSuggestedCharIds(suggestedCharIds)
    setAiSuggestedSlIds(suggestedSlIds)
    setAiSuggestedAssetUpdates(data.asset_updates || null)
    setAiChapterIndex(data.chapter_index || null)
    setAiDebriefSummary(data.summary || '')
    const validNewChars = (data.new_characters || []).filter(nc => typeof nc.name === 'string' && nc.name.trim())
    setAiNewCharacters(validNewChars)
    setAiNewReaderPromises((data.new_reader_promises || []).filter(p => p.promise_text?.trim()))
    setAiFulfilledPromiseTexts((data.fulfilled_promise_texts || []).filter(t => t.trim()))

    const total = suggestedCharIds.size + suggestedSlIds.size
    const assetCount = data.asset_updates
      ? Object.values(data.asset_updates).reduce<number>(
        (sum, value) => sum + (Array.isArray(value) ? value.length : 0),
        0,
      )
      : 0
    const promiseCount = (data.new_reader_promises?.length ?? 0) + (data.fulfilled_promise_texts?.length ?? 0)
    if (total > 0 || assetCount > 0 || validNewChars.length > 0 || promiseCount > 0) {
      if (!opts?.silent) {
        if (source === 'cache') {
          toast('已复用本章复盘结果', { icon: 'ℹ️' })
        } else {
          const promiseHint = promiseCount > 0 ? `、${promiseCount} 条读者承诺` : ''
          toast.success(`AI 自动提取了 ${suggestedCharIds.size} 个人物变化、${suggestedSlIds.size} 条故事线更新、${assetCount} 条资产变化${promiseHint}，请确认后提交`)
        }
        onNavigateToDebriefTab()
      }
    } else if (source === 'llm' && !opts?.silent) {
      toast('AI 未检测到明确的状态变化', { icon: 'ℹ️' })
    }
  }, [storyLines, onNavigateToDebriefTab])

  /**
   * 在调用 LLM 分析前先把编辑器未保存内容落库。
   * 服务端复盘只读 DB，不读编辑器内存内容。
   *
   * @returns true = 已确认有内容落库；false = 内容为空无需分析
   */
  const flushChapterSaveForDebrief = useCallback(async (): Promise<boolean> => {
    if (!editor) return hasHtmlTextContent(chapterContent)
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    const html = editor.getHTML()
    if (!hasHtmlTextContent(html)) return false
    if (html === chapterContent) return true
    try {
      const res = await chaptersApi.update(projectId, chapterId, { content: html })
      upsertChapter(res.data)
      return true
    } catch {
      toast.error('保存正文失败，无法开始 AI 复盘')
      return false
    }
  }, [editor, chapterContent, chapterId, projectId, upsertChapter, saveTimerRef])

  /**
   * 调用 AI 完整复盘分析（LLM）。
   * 先落库正文，再请求 autoDebrief，结果通过 applyAutoDebriefData 预填表单。
   *
   * @param forceRefresh - true 时跳过服务端缓存强制重新分析
   */
  const runAutoDebrief = async (forceRefresh = false) => {
    if (!debriefContentReady) {
      toast.error('本章尚无正文，请先生成或撰写并保存后再复盘')
      return
    }
    setAutoDebriefing(true)
    try {
      const saved = await flushChapterSaveForDebrief()
      if (!saved) {
        toast.error('本章正文为空或未保存成功，无法复盘')
        return
      }
      toast('AI 正在分析本章（thinking 模型可能需 2–5 分钟）…', { icon: '⏳', duration: 5000 })
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.autoDebrief(projectId, {
        chapter_id: chapterId,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
        force_refresh: forceRefresh,
      })
      const data = res.data as AutoDebriefResponse
      if (data.error) {
        toast.error(`AI 自动复盘解析失败：${data.error}`)
        return
      }
      if (data.summary === '章节内容为空，无法分析') {
        toast.error('服务端未读到本章正文，请先保存后再复盘')
        return
      }
      applyAutoDebriefData(data, data.cached ? 'cache' : 'llm')
      setDebriefFromQueueSnapshot(false)
    } catch (e) {
      toast.error(`AI 自动复盘失败：${formatApiError(e)}`)
    } finally {
      setAutoDebriefing(false)
    }
  }

  /**
   * 打开复盘 Tab 时仅读服务端缓存（cache_only=true），不调用 LLM。
   * 缓存命中时静默预填；未命中或失败时静默忽略。
   */
  const loadDebriefTabCache = useCallback(async () => {
    if (!hasHtmlTextContent(chapterContent)) return
    setDebriefCacheHydrating(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.autoDebrief(projectId, {
        chapter_id: chapterId,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
        cache_only: true,
      })
      const data = res.data as AutoDebriefResponse
      if (data.error || data.cache_only_miss || !data.cached) return
      applyAutoDebriefData(data, 'cache', { silent: true })
      setDebriefFromQueueSnapshot(false)
    } catch { /* 静默：无缓存或网络失败不打扰写作流 */ }
    finally {
      setDebriefCacheHydrating(false)
    }
  }, [projectId, chapterId, chapterContent, applyAutoDebriefData])

  /**
   * 提交复盘表单：人物更新 + 故事线推进 + 资产变化 + 新配角 + 承诺台账。
   * 成功后刷新故事线/记忆/人物，并清空 AI 建议状态。
   *
   * @param selectedAssetUpdates - 用户勾选的资产更新（来自 DebriefPanel 的勾选逻辑）
   */
  const submitDebrief = async (selectedAssetUpdates?: Record<string, unknown>) => {
    const characterUpdates = Object.entries(charUpdates)
      .map(([character_id, upd]) => {
        const entry: Record<string, any> = { character_id }
        if (upd.current_realm) entry.current_realm = upd.current_realm
        if (upd.realm_rank != null) entry.realm_rank = upd.realm_rank
        if (upd.current_location) entry.current_location = upd.current_location
        if (upd.current_status) entry.current_status = upd.current_status
        if (upd.add_skill_name) {
          entry.add_skill = {
            skill_name: upd.add_skill_name,
            mastery: upd.add_skill_mastery || '初学',
          }
        }
        return entry
      })
      .filter(e => Object.keys(e).length > 1)

    const storylineUpdates = Object.entries(storylineBeats)
      .map(([storyline_id, upd]) => {
        if (!isUuidLike(storyline_id)) return null
        const entry: Record<string, unknown> = { storyline_id }
        if (upd.status) entry.status = upd.status
        if (upd.beat) entry.append_beat = upd.beat
        if (upd.actual_tension !== '' && upd.actual_tension != null) {
          entry.actual_tension = Number(upd.actual_tension)
        }
        if (upd.beat_match_score !== '' && upd.beat_match_score != null) {
          entry.beat_match_score = Number(upd.beat_match_score)
        }
        if (upd.crossover_executed === true) entry.crossover_executed = true
        if (upd.crossover_executed === false) entry.crossover_executed = false
        if (upd.screen_time_words !== '' && upd.screen_time_words != null) {
          entry.screen_time_words = Number(upd.screen_time_words)
        }
        return entry
      })
      .filter((e): e is Record<string, unknown> => !!e && Object.keys(e).length > 1)

    const effectiveAssetUpdates = selectedAssetUpdates ?? aiSuggestedAssetUpdates ?? null
    const hasAssetUpdates = Boolean(
      effectiveAssetUpdates
      && Object.values(effectiveAssetUpdates).some(value => Array.isArray(value) && value.length > 0),
    )
    const hasChapterIndex = Boolean(
      aiChapterIndex
      && (
        (aiChapterIndex.actual_foreshadows_laid?.length ?? 0) > 0
        || (aiChapterIndex.actual_foreshadows_resolved?.length ?? 0) > 0
        || aiChapterIndex.story_day
        || (aiChapterIndex.core_events?.length ?? 0) > 0
        || aiChapterIndex.ending_hook
      ),
    )
    const hasReaderPromises = aiNewReaderPromises.length > 0 || aiFulfilledPromiseTexts.length > 0

    if (characterUpdates.length === 0 && storylineUpdates.length === 0
      && !debriefNotes && !hasAssetUpdates && !hasChapterIndex && !hasReaderPromises) {
      toast('没有需要提交的更新', { icon: 'ℹ️' })
      return
    }

    setDebriefSubmitting(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.chapterDebrief(projectId, {
        chapter_id: chapterId,
        character_updates: characterUpdates as any,
        storyline_updates: storylineUpdates as any,
        asset_updates: hasAssetUpdates ? effectiveAssetUpdates || undefined : undefined,
        new_characters: aiNewCharacters.length > 0 ? aiNewCharacters as any : undefined,
        chapter_index: aiChapterIndex || undefined,
        new_reader_promises: aiNewReaderPromises.length > 0 ? aiNewReaderPromises : undefined,
        fulfilled_promise_texts: aiFulfilledPromiseTexts.length > 0 ? aiFulfilledPromiseTexts : undefined,
        notes: debriefNotes || undefined,
        apply_source: 'manual_tab',
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const body = res.data as {
        message?: string
        promises_created?: number
        promises_fulfilled?: number
        storyline_drift_report?: { debts_created?: number; corrections?: unknown[] }
      }
      const pc = Number(body.promises_created ?? 0)
      const pf = Number(body.promises_fulfilled ?? 0)
      const promiseToast = (pc > 0 || pf > 0) ? `（承诺 +${pc} / 兑现 ${pf}）` : ''
      const driftDebts = Number(body.storyline_drift_report?.debts_created ?? 0)
      const driftToast = driftDebts > 0 ? `；织网漂移已记 ${driftDebts} 条质检债` : ''
      toast.success(`${body.message ?? '复盘已提交'}${promiseToast}${driftToast}`)
      setDebriefHistoryTick(t => t + 1)

      const [refreshedStorylines, refreshedMemories, refreshedCharsRes] = await Promise.all([
        storylinesApi.list(projectId),
        aiApi.listMemory(projectId),
        charactersApi.list(projectId),
      ])
      setStoryLines(refreshedStorylines.data)
      setMemories(refreshedMemories.data)
      refreshedCharsRes.data.forEach((c: any) => useAppStore.getState().upsertCharacter(c))

      // 清空 AI 建议状态
      setDebriefFromQueueSnapshot(false)
      setCharUpdates({})
      setStorylineBeats({})
      setAiSuggestedAssetUpdates(null)
      setAiChapterIndex(null)
      setAiNewCharacters([])
      setAiNewReaderPromises([])
      setAiFulfilledPromiseTexts([])
      setDebriefNotes('')
    } catch {
      toast.error('复盘提交失败')
    } finally {
      setDebriefSubmitting(false)
    }
  }

  return {
    debriefSubmitting,
    autoDebriefing,
    debriefCacheHydrating,
    debriefFromQueueSnapshot,
    setDebriefFromQueueSnapshot,
    debriefHistoryTick,
    setDebriefHistoryTick,
    charUpdates,
    setCharUpdates,
    storylineBeats,
    setStorylineBeats,
    debriefNotes,
    setDebriefNotes,
    aiSuggestedCharIds,
    aiSuggestedSlIds,
    aiDebriefSummary,
    aiSuggestedAssetUpdates,
    aiNewCharacters,
    setAiNewCharacters,
    aiChapterIndex,
    aiNewReaderPromises,
    setAiNewReaderPromises,
    aiFulfilledPromiseTexts,
    setAiFulfilledPromiseTexts,
    applyAutoDebriefData,
    runAutoDebrief,
    loadDebriefTabCache,
    submitDebrief,
    debriefContentReady,
    resetDebriefState,
  }
}
