/**
 * index.tsx — ChapterEditor 主组件（编排壳）
 *
 * 职责：章节写作编辑器顶层组件，协调 TipTap 编辑器、AI 草稿队列、
 * 自动保存、写前预警、复盘面板、版本历史、侧栏 Tab 面板等所有交互。
 *
 * ⚠️ 本文件已达架构软警戒线（>400 行），需进一步抽取 hooks：
 *   - useChapterAutosave   (autoSave / manualSave / cleanupChapter)
 *   - usePreWriteWarning   (runPreWriteWarning / warnResult / warnHistory)
 *   - useDebriefRun        (runAutoDebrief / submitDebrief / applyAutoDebriefData)
 * 新需求请加入上述 hooks，禁止直接在本文件内新增 useState / useEffect。
 *
 * 子组件/工具：
 *   - PlanCard              → ./PlanCard
 *   - CharacterMiniCard     → ./CharacterMiniCard
 *   - DebriefPanel          → ./DebriefPanel
 *   - 类型                  → ./types
 *   - 纯工具函数            → ./utils
 *   - UI 常量               → ./constants
 */
import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi, aiApi, storylinesApi, foreshadowsApi, chapterIndexesApi, charactersApi, projectsApi } from '../../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../../../store'
import type { Chapter, Character, OutlineNode, StoryLine, Foreshadow, ChapterIndex, ChapterVersion, ChapterVersionDetail } from '../../../types'
import toast from 'react-hot-toast'
import {
  BookOpen, Sparkles, X, Zap, Target, Users, Flag, GitBranch, RefreshCw,
  Maximize2, Minimize2, Clock, ChevronDown, ChevronRight, Anchor, History,
  Feather, PenLine, ListPlus, CheckCircle, Circle,
  CheckSquare, TrendingUp, MapPin, Swords, Bot, Save, Trash2, ClipboardList, UserPlus,
  ShieldAlert, ShieldCheck, Layers,
} from 'lucide-react'
import clsx from 'clsx'
import {
  splitStreamedDraftText,
  htmlToPlainForSplit,
  plainTextBlocksToHtml,
} from '../../../utils/draftChapterIndexSplit'
import ChapterIndexEditPanel from '../ChapterIndexEditPanel'
import ScenePipelinePanel from '../ScenePipelinePanel'
import { chapterHasNarrativeBody, shouldUseGatedDraft } from '../../../utils/writingConfigGate'
import { formatApiError } from '../../../utils/apiError'

// ─── 包内子模块 ───────────────────────────────────────────────────────────────
import PlanCard from './PlanCard'
import CharacterMiniCard from './CharacterMiniCard'
import DebriefPanel from './DebriefPanel'
import type { ChapterEditorProps as Props, AutoDebriefResponse, PreWriteWarnResult, PreWriteWarnHistoryRow, NewCharacterSuggestion } from './types'
import {
  normalizePreWriteWarnResult,
  parsePreWriteWarningHistoryPayload,
  isUuidLike,
  htmlTail,
  hasHtmlTextContent,
  isBookFirstChapterTitle,
} from './utils'
import {
  STATUS_OPTIONS,
  ROLE_BADGE,
  INLINE_ACTIONS,
  TOP_TOOL_BUTTON_BASE,
  TOP_TOOL_BUTTON_IDLE,
  TOP_TOOL_BUTTON_ACTIVE,
  TOP_TOOL_ICON_BUTTON,
  TOP_TOOL_PRIMARY_BUTTON,
  TOP_TOOL_DEBRIEF_BUTTON_IDLE,
} from './constants'

export default function ChapterEditor({
  projectId, chapter, outlineNode, prevChapter, onFocusModeChange,
}: Props) {
  const {
    upsertChapter, removeChapter, setActiveChapterId,
    chapters, characters, storyLines, setStoryLines, setMemories, addGenTask,
    setCurrentProject,
  } = useAppStore()
  const currentProject = useAppStore(s => s.currentProject)
  /**
   * 项目级写作质量门控配置，从 currentProject.extra.writing_config 读取。
   * 用于判断「重新生成」按钮应走普通重写还是门控重写任务。
   */
  const writingConfig = useAppStore(s => {
    const ex = (s.currentProject as any)?.extra
    return (ex && typeof ex === 'object') ? (ex.writing_config ?? null) : null
  })

  useEffect(() => {
    if (!projectId || currentProject?.id !== projectId) return
    const ex = (currentProject.extra as Record<string, unknown> | undefined) ?? {}
    if (ex.writing_config && typeof ex.writing_config === 'object') return
    projectsApi.getWritingConfig(projectId)
      .then(res => {
        const cp = useAppStore.getState().currentProject
        if (!cp || cp.id !== projectId) return
        setCurrentProject({
          ...cp,
          extra: {
            ...((cp.extra as Record<string, unknown>) ?? {}),
            writing_config: res.data.writing_config,
          } as typeof cp.extra,
        })
      })
      .catch(() => { /* 静默；门控退化为关闭 */ })
  }, [projectId, currentProject?.id, currentProject?.extra, setCurrentProject])
  const genQueue = useAppStore(s => s.genQueue)
  const queueCommittedDebriefIds = useAppStore(s => s.queueCommittedDebriefIds)
  const queueDebriefSnapshot = useAppStore(s => s.queueDebriefUiSnapshotByChapterId[chapter.id])
  const setQueueDebriefUiSnapshot = useAppStore(s => s.setQueueDebriefUiSnapshot)
  const clearQueueDebriefUiSnapshots = useAppStore(s => s.clearQueueDebriefUiSnapshots)
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()
  const storylineAutoSyncingRef = useRef(false)
  const memoryAutoSyncingRef = useRef(false)
  const lastMemoryAutoExtractAtRef = useRef(0)
  /** 队列已落库复盘提示，每章最多 toast 一次（避免依赖项抖动重复弹） */
  const queueDebriefToastShownRef = useRef<Set<string>>(new Set())
  /** 已为当前章应用过「队列复盘 UI 快照」，避免 effect 重复预填 */
  const queueSnapHydratedChapterRef = useRef<string | null>(null)

  // ── 面板 UI 状态 ───────────────────────────────────────────────────
  const [contextOpen, setContextOpen]   = useState(!!outlineNode)
  const [contextTab, setContextTab]     = useState<'plan' | 'scene' | 'debrief' | 'chindex' | 'warn'>('plan')
  const [warnLoading, setWarnLoading]   = useState(false)
  const [warnResult, setWarnResult]     = useState<PreWriteWarnResult | null>(null)
  const [warnHistory, setWarnHistory]   = useState<PreWriteWarnHistoryRow[]>([])
  const [selectedWarnRecordId, setSelectedWarnRecordId] = useState<string | null>(null)
  const [focusMode, setFocusMode]       = useState(false)
  const [statusOpen, setStatusOpen]     = useState(false)
  const statusRef = useRef<HTMLDivElement>(null)

  // ── 原有 AI 草稿功能（正文生成走全局队列，见 chapterGenBusy）────────────
  const [aiExtraPrompt, setAiExtraPrompt]               = useState('')
  const [continueChapterCount, setContinueChapterCount] = useState(1)
  const [selectionText, setSelectionText]               = useState('')
  const [showSelectionBar, setShowSelectionBar]         = useState(false)

  // ── 章节复盘（写完后提交状态更新）────────────────────────────────
  const [debriefSubmitting, setDebriefSubmitting] = useState(false)
  const [autoDebriefing, setAutoDebriefing]       = useState(false)
  /** 打开复盘 Tab 时仅读缓存，与 AI 分析区分开 */
  const [debriefCacheHydrating, setDebriefCacheHydrating] = useState(false)
  /** 当前面板展示的是「生成队列自动复盘」的快照（黄标含义） */
  const [debriefFromQueueSnapshot, setDebriefFromQueueSnapshot] = useState(false)
  /** 复盘提交成功后刷新「落库记录」列表 */
  const [debriefHistoryTick, setDebriefHistoryTick] = useState(0)

  const prevProjectIdForDebriefRef = useRef<string | null>(null)
  const [cleaningChapter, setCleaningChapter]     = useState(false)
  // charUpdates: map of characterId → partial update
  const [charUpdates, setCharUpdates] = useState<Record<string, {
    current_realm?: string
    current_location?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>>({})
  const [storylineBeats, setStorylineBeats] = useState<Record<string, {
    status?: string
    beat?: string
  }>>({})
  const [debriefNotes, setDebriefNotes] = useState('')
  // AI 自动建议：记录哪些字段是 AI 预填的，用于显示标注
  const [aiSuggestedCharIds, setAiSuggestedCharIds]   = useState<Set<string>>(new Set())
  const [aiSuggestedSlIds, setAiSuggestedSlIds]       = useState<Set<string>>(new Set())
  const [aiDebriefSummary, setAiDebriefSummary]       = useState('')
  const [aiSuggestedAssetUpdates, setAiSuggestedAssetUpdates] = useState<Record<string, unknown> | null>(null)
  const [aiNewCharacters, setAiNewCharacters] = useState<NewCharacterSuggestion[]>([])
  const [aiChapterIndex, setAiChapterIndex] = useState<AutoDebriefResponse['chapter_index'] | null>(null)
  const [aiNewReaderPromises, setAiNewReaderPromises] = useState<NonNullable<AutoDebriefResponse['new_reader_promises']>>([])
  const [aiFulfilledPromiseTexts, setAiFulfilledPromiseTexts] = useState<string[]>([])

  // ── 底部伏笔面板 ───────────────────────────────────────────────────
  const [bottomPanelOpen, setBottomPanelOpen]   = useState(false)
  const [openForeshadows, setOpenForeshadows]   = useState<Foreshadow[]>([])
  const [currentChIndex, setCurrentChIndex]     = useState<ChapterIndex | null>(null)

  const [historyOpen, setHistoryOpen]           = useState(false)
  const [versionsList, setVersionsList]         = useState<ChapterVersion[]>([])
  const [versionsLoading, setVersionsLoading]  = useState(false)
  const [historyPreview, setHistoryPreview]     = useState<ChapterVersionDetail | null>(null)
  const [historyPreviewLoading, setHistoryPreviewLoading] = useState(false)

  /**
   * 无 AI 快照：原文 = 可编辑 HTML；正文 = 只读预览（截去稿末索引块）。
   * 有 manuscript_raw_snapshot：正文 = 可编辑叙事；原文 = 只读对照（模型全文含稿末）。
   */
  const [manuscriptView, setManuscriptView]     = useState<'source' | 'prose'>('source')
  const [editorHtmlTick, setEditorHtmlTick]     = useState(0)

  const hasManuscriptRawSnapshot = useMemo(
    () => Boolean((chapter.manuscript_raw_snapshot || '').trim()),
    [chapter.manuscript_raw_snapshot],
  )

  const rawSnapshotPreviewHtml = useMemo(() => {
    const s = (chapter.manuscript_raw_snapshot || '').trim()
    if (!s) return ''
    return plainTextBlocksToHtml(s)
  }, [chapter.manuscript_raw_snapshot])

  // 切换章节时重新拉取伏笔 + 情节档案
  useEffect(() => {
    if (!projectId) return
    foreshadowsApi.list(projectId, 'open').then(r => setOpenForeshadows(r.data)).catch(() => {})
    chapterIndexesApi.getByChapter(projectId, chapter.id)
      .then(r => setCurrentChIndex(r.data))
      .catch(() => setCurrentChIndex(null))
  }, [projectId, chapter.id])

  // ── 写作统计 ───────────────────────────────────────────────────────
  const sessionStartWords = useRef<number>(chapter.word_count)
  const sessionStartTime  = useRef<number>(Date.now())
  const [sessionDelta, setSessionDelta]   = useState(0)   // 本次新增字数（可负）
  const [sessionElapsed, setSessionElapsed] = useState(0) // 秒

  // ─────────────────────────────────────────────────────────────────
  // Editor
  // ─────────────────────────────────────────────────────────────────
  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder: '从这里落笔，写下这一章的第一个句子……' }),
    ],
    content: chapter.content,
    editorProps: {
      attributes: {
        class: 'prose prose-lg max-w-readable w-full focus:outline-none min-h-[60vh] px-6 sm:px-10 py-8 mx-auto',
      },
    },
    onUpdate: ({ editor }) => {
      clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => autoSave(editor.getHTML()), 2000)
      const current = editor.storage.characterCount?.characters() ?? 0
      setSessionDelta(current - sessionStartWords.current)
      setEditorHtmlTick((n) => n + 1)
    },
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection
      if (from === to) { setShowSelectionBar(false); setSelectionText(''); return }
      const selected = editor.state.doc.textBetween(from, to, ' ').trim()
      if (selected.length >= 6) {
        setSelectionText(selected)
        setShowSelectionBar(true)
      } else {
        setShowSelectionBar(false)
      }
    },
  })

  const prosePreviewHtml = useMemo(() => {
    if (!editor || manuscriptView !== 'prose') return ''
    const plain = htmlToPlainForSplit(editor.getHTML())
    const { body } = splitStreamedDraftText(plain.trim())
    return plainTextBlocksToHtml(body.trim())
  }, [editor, editorHtmlTick, manuscriptView, chapter.id])

  const manuscriptViewToggle = (
    <div
      className="flex items-center rounded-full border border-novel-border overflow-hidden text-[11px] shadow-sm bg-novel-card/95 backdrop-blur-sm"
      title={
        hasManuscriptRawSnapshot
          ? '正文：编辑入库叙事；原文：模型最近一次返回全文（含稿末索引），仅对照'
          : '无 AI 快照时：原文可编辑；正文为隐藏稿末索引块的只读预览'
      }
    >
      <button
        type="button"
        onClick={() => setManuscriptView('source')}
        className={clsx(
          'px-3 py-1.5 font-medium transition-novel',
          manuscriptView === 'source'
            ? 'bg-novel-panel text-novel-accent'
            : 'text-novel-ink-muted hover:text-novel-ink',
        )}
      >
        原文
      </button>
      <button
        type="button"
        onClick={() => setManuscriptView('prose')}
        className={clsx(
          'px-3 py-1.5 font-medium border-l border-novel-border transition-novel',
          manuscriptView === 'prose'
            ? 'bg-novel-panel text-novel-accent'
            : 'text-novel-ink-muted hover:text-novel-ink',
        )}
      >
        正文
      </button>
    </div>
  )

  // ─────────────────────────────────────────────────────────────────
  // Effects
  // ─────────────────────────────────────────────────────────────────

  /** 章节切换：重置所有会话状态 */
  useEffect(() => {
    sessionStartWords.current = chapter.word_count
    sessionStartTime.current  = Date.now()
    setSessionDelta(0)
    setSessionElapsed(0)
    setSelectionText('')
    setShowSelectionBar(false)
    setCharUpdates({})
    setStorylineBeats({})
    setDebriefNotes('')
    setAiDebriefSummary('')
    setAiSuggestedCharIds(new Set())
    setAiSuggestedSlIds(new Set())
    setAiSuggestedAssetUpdates(null)
    setAiNewCharacters([])
    setDebriefFromQueueSnapshot(false)
    queueSnapHydratedChapterRef.current = null
    setManuscriptView((chapter.manuscript_raw_snapshot || '').trim() ? 'prose' : 'source')
    setHistoryOpen(false)
    setVersionsList([])
    setHistoryPreview(null)
    setWarnResult(null)
    setWarnHistory([])
    setSelectedWarnRecordId(null)
  }, [chapter.id])

  useEffect(() => {
    if (prevProjectIdForDebriefRef.current !== null && prevProjectIdForDebriefRef.current !== projectId) {
      queueDebriefToastShownRef.current.clear()
      clearQueueDebriefUiSnapshots()
    }
    prevProjectIdForDebriefRef.current = projectId
  }, [projectId, clearQueueDebriefUiSnapshots])

  /** 同章经队列写入/更新快照后，回到可编辑「正文」 */
  useEffect(() => {
    const s = (chapter.manuscript_raw_snapshot || '').trim()
    if (!s) return
    setManuscriptView('prose')
  }, [chapter.manuscript_raw_snapshot])

  /** 同步大纲节点变化时自动展开 */
  useEffect(() => { setContextOpen(!!outlineNode) }, [outlineNode?.id])

  /** 专注模式变化通知父级 */
  useEffect(() => { onFocusModeChange?.(focusMode) }, [focusMode])

  /** 内容切换时同步 editor */
  useEffect(() => {
    if (!editor) return
    if (chapter.content !== editor.getHTML()) editor.commands.setContent(chapter.content)
  }, [chapter.id, chapter.content, editor])

  /** 计时器：每 15 秒更新一次显示 */
  useEffect(() => {
    const t = setInterval(
      () => setSessionElapsed(Math.floor((Date.now() - sessionStartTime.current) / 1000)),
      15000,
    )
    return () => clearInterval(t)
  }, [])

  /** 状态下拉外点关闭 */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) setStatusOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  /** 门控队列内联写前预警完成（落库后需刷新侧栏，与手动「预警」API 同源） */
  const gatedPreWarnDoneForChapter = useMemo(
    () =>
      genQueue.some(
        t =>
          t.projectId === projectId
          && t.type === 'gated_rewrite_chapter'
          && t.params?.chapterId === chapter.id
          && (t.progress ?? []).some(p => p.step === 'pre_warn' && p.done && !p.error),
      ),
    [genQueue, projectId, chapter.id],
  )
  const gatedPreWarnSyncedRef = useRef(false)

  const refreshWarnHistoryFromServer = useCallback(() => {
    if (!chapter.id || !projectId) return
    void aiApi.preWriteWarningHistory(projectId, chapter.id).then((r) => {
      const rows = parsePreWriteWarningHistoryPayload(r.data)
      setWarnHistory(rows)
    }).catch(() => {
      setWarnHistory([])
    })
  }, [chapter.id, projectId])

  /** 写前预警：打开 Tab 时拉取本章历史（响应体非数组时安全降级） */
  useEffect(() => {
    if (contextTab !== 'warn' || !chapter.id || !projectId) return
    refreshWarnHistoryFromServer()
  }, [contextTab, chapter.id, projectId, refreshWarnHistoryFromServer])

  /** 门控写作完成写前预警后自动刷新历史（用户可能已停在「预警」Tab） */
  useEffect(() => {
    if (!gatedPreWarnDoneForChapter) {
      gatedPreWarnSyncedRef.current = false
      return
    }
    if (gatedPreWarnSyncedRef.current) return
    gatedPreWarnSyncedRef.current = true
    refreshWarnHistoryFromServer()
  }, [gatedPreWarnDoneForChapter, refreshWarnHistoryFromServer])

  /** 有历史且当前无展示结果时，默认显示最新一条 */
  useEffect(() => {
    if (contextTab !== 'warn') return
    if (warnResult !== null) return
    const first = warnHistory[0]
    if (!first?.id) return
    setWarnResult(normalizePreWriteWarnResult(first.result))
    setSelectedWarnRecordId(first.id)
  }, [contextTab, warnHistory, warnResult])

  // ─────────────────────────────────────────────────────────────────
  // Handlers
  // ─────────────────────────────────────────────────────────────────

  const autoSave = useCallback(async (content: string) => {
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
      // 自动保存路径也纳入记忆提取，但做节流避免高频触发
      const now = Date.now()
      const plainLen = (content || '').replace(/<[^>]+>/g, '').trim().length
      if (plainLen >= 120 && now - lastMemoryAutoExtractAtRef.current > 90_000) {
        await autoExtractMemoryAfterChapter(false)
        lastMemoryAutoExtractAtRef.current = now
      }
    } catch { /* 静默失败 */ }
  }, [projectId, chapter.id, upsertChapter])

  const autoSyncStorylinesAfterChapter = async (showToast = false) => {
    if (storylineAutoSyncingRef.current) return
    storylineAutoSyncingRef.current = true
    try {
      const route = useAppStore.getState().aiBackendRoute
      const auto = await aiApi.autoDebrief(projectId, {
        chapter_id: chapter.id,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const data = auto.data as {
        storyline_updates?: Array<{ storyline_id?: string; storyline_name?: string; status?: string; beat?: string }>
      }

      const storylineUpdates = (data.storyline_updates || [])
        .map((su) => {
          const fields: Record<string, any> = {}
          if (su.status) fields.status = su.status
          if (su.beat) fields.append_beat = su.beat
          if (Object.keys(fields).length === 0) return null

          let resolvedId = su.storyline_id || ''
          if (!isUuidLike(resolvedId) && su.storyline_name) {
            const byName = storyLines.find(sl => sl.name === su.storyline_name)
            if (byName?.id && isUuidLike(byName.id)) resolvedId = byName.id
          }
          if (!isUuidLike(resolvedId)) return null
          return { storyline_id: resolvedId, ...fields }
        })
        .filter((x): x is { storyline_id: string; status?: string; append_beat?: string } => !!x)

      if (storylineUpdates.length === 0) return

      await aiApi.chapterDebrief(projectId, {
        chapter_id: chapter.id,
        storyline_updates: storylineUpdates,
      })

      // 提交后刷新故事线，保证写作页复盘面板与数据库一致
      const refreshed = await storylinesApi.list(projectId)
      setStoryLines(refreshed.data)
      if (showToast) toast.success(`已自动推进 ${storylineUpdates.length} 条故事线`)
    } catch {
      if (showToast) toast.error('自动更新故事线失败，请在复盘面板手动提交')
    } finally {
      storylineAutoSyncingRef.current = false
    }
  }

  const autoExtractMemoryAfterChapter = async (showToast = false) => {
    if (memoryAutoSyncingRef.current) return
    memoryAutoSyncingRef.current = true
    try {
      const route = useAppStore.getState().aiBackendRoute
      const extracted = await aiApi.extractMemory(
        projectId,
        chapter.id,
        modelProfileFromRoute(route),
        llmProviderIdFromRoute(route),
      )
      const count = Array.isArray(extracted.data) ? extracted.data.length : 0

      // 刷新全量记忆，确保和后端一致
      const allMemories = await aiApi.listMemory(projectId)
      setMemories(allMemories.data)

      if (showToast) {
        if (count > 0) toast.success(`已自动提取 ${count} 条记忆`)
        else toast('本章未提取到新记忆', { icon: 'ℹ️' })
      }
    } catch {
      if (showToast) toast.error('自动提取记忆失败，请在 AI 面板手动提取')
    } finally {
      memoryAutoSyncingRef.current = false
    }
  }

  const manualSave = async () => {
    if (!editor) return
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content: editor.getHTML() })
      upsertChapter(res.data)
      await chaptersApi.snapshot(projectId, chapter.id, '手动保存')
      await autoExtractMemoryAfterChapter(true)
      await autoSyncStorylinesAfterChapter(true)
      toast.success('已保存快照')
    } catch { toast.error('保存失败') }
  }

  const updateStatus = async (status: Chapter['status']) => {
    setStatusOpen(false)
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { status })
      upsertChapter(res.data)
      if (status === 'done' || status === 'reviewed') {
        await autoExtractMemoryAfterChapter(true)
        await autoSyncStorylinesAfterChapter(true)
      }
      toast.success(`状态 → 「${STATUS_OPTIONS.find(o => o.value === status)?.label}」`)
    } catch { toast.error('状态更新失败') }
  }

  // ─────────────────────────────────────────────────────────────────
  // AI 草稿生成：首发生成 / 选区扩写改写 → 全局队列（与多章续写同一套流水线）
  // ─────────────────────────────────────────────────────────────────

  const generateDraft = (opts?: { replaceExisting?: boolean; overridePrompt?: string }) => {
    if (!previousChapterGenerated) {
      toast.error(generateBlockedReason ?? '请先生成上一章')
      return
    }
    if (opts?.replaceExisting) {
      if (!window.confirm('「重新生成本章」将按大纲替换当前正文；若有旧稿会在保存前自动留版本快照。确定继续？')) return
      const route = useAppStore.getState().aiBackendRoute
      // 满足以下任一条件时走门控路由（gated_rewrite_chapter）：
      //   1. pre_write_warning_enabled=true：写前简报会在门控路由内联生成（普通续写走 draft-assist 也会注入）
      //   2. auto_quality_gate=true 且至少一个门槛 > 0：需要质检循环
      // 两者独立，均可单独启用；仅两者均关闭时才走轻量 rewrite_chapter。
      const useGated = shouldUseGatedDraft(writingConfig)
      const gatedLabel = (() => {
        const hasWarn = writingConfig?.pre_write_warning_enabled === true
        const hasGate = writingConfig?.auto_quality_gate === true &&
          (writingConfig.min_overall_score > 0 || writingConfig.min_subscribe_intent > 0)
        if (hasWarn && hasGate) return `预警+门控重写《${chapter.title}》`
        if (hasWarn) return `写前预警重写《${chapter.title}》`
        return `门控重写《${chapter.title}》`
      })()
      addGenTask({
        type: useGated ? 'gated_rewrite_chapter' : 'rewrite_chapter',
        projectId,
        label: useGated ? gatedLabel : `重写《${chapter.title}》`,
        params: {
          chapterId: chapter.id,
          userPrompt: opts.overridePrompt ?? aiExtraPrompt.trim(),
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      const toastMsg = (() => {
        const hasWarn = writingConfig?.pre_write_warning_enabled === true
        const warnReuseHint = hasWarn ? '（本章若已有预警记录将自动复用，跳过重复审稿）' : ''
        if (!useGated) return `已加入 AI 队列：开始重写本章${warnReuseHint}`
        const hasGate = writingConfig?.auto_quality_gate === true
        if (hasWarn && hasGate) return `已加入 AI 队列：写前预警 + 质量门控写作${warnReuseHint}`
        if (hasWarn) return `已加入 AI 队列：写前预警写作（质检仅参考）${warnReuseHint}`
        return '已加入 AI 队列：质量门控写作（自动质检+重写）'
      })()
      toast.success(toastMsg)
      setAiExtraPrompt('')
      return
    }
    void (async () => {
      if (editor) {
        try {
          const currentContent = editor.getHTML()
          if (currentContent !== chapter.content) {
            const res = await chaptersApi.update(projectId, chapter.id, { content: currentContent })
            upsertChapter(res.data)
          }
        } catch {
          toast.error('当前章节保存失败，请稍后重试')
          return
        }
      }
      const route = useAppStore.getState().aiBackendRoute
      const userPrompt =
        opts?.overridePrompt !== undefined ? String(opts.overridePrompt) : aiExtraPrompt.trim()
      addGenTask({
        type: 'continue_chapters',
        projectId,
        label: `生成《${chapter.title}》正文`,
        params: {
          chapterIds: [chapter.id],
          userPrompt,
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      toast.success('已加入 AI 队列：生成本章正文')
      setAiExtraPrompt('')
    })()
  }

  const runPromptAction = (action: 'rewrite' | 'expand') => {
    if (!selectionText.trim()) {
      toast.error('请先选中需要处理的正文')
      return
    }
    const actionConfig = INLINE_ACTIONS.find(item => item.key === action)
    if (!actionConfig) return
    const actionPrompt = actionConfig.buildPrompt(selectionText.slice(0, 400))
    void (async () => {
      if (editor) {
        try {
          const currentContent = editor.getHTML()
          if (currentContent !== chapter.content) {
            const res = await chaptersApi.update(projectId, chapter.id, { content: currentContent })
            upsertChapter(res.data)
          }
        } catch {
          toast.error('当前章节保存失败，请稍后重试')
          return
        }
      }
      const route = useAppStore.getState().aiBackendRoute
      addGenTask({
        type: 'continue_chapters',
        projectId,
        label: `生成《${chapter.title}》正文（选区）`,
        params: {
          chapterIds: [chapter.id],
          userPrompt: actionPrompt,
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      toast.success('已加入 AI 队列')
    })()
    setShowSelectionBar(false)
  }

  const enqueueContinueChapters = async () => {
    if (!previousChapterGenerated) {
      toast.error(generateBlockedReason ?? '请先生成上一章')
      return
    }
    const ordered = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
    const startIndex = ordered.findIndex(c => c.id === chapter.id)
    if (startIndex < 0) {
      toast.error('未找到当前章节顺序，请刷新后重试')
      return
    }
    const remaining = Math.max(1, ordered.length - startIndex)
    const count = Math.min(Math.max(1, continueChapterCount || 1), remaining)
    const targetChapters = ordered.slice(startIndex, startIndex + count)

    if (editor) {
      try {
        const currentContent = editor.getHTML()
        if (currentContent !== chapter.content) {
          const res = await chaptersApi.update(projectId, chapter.id, { content: currentContent })
          upsertChapter(res.data)
        }
      } catch {
        toast.error('当前章节保存失败，请稍后重试')
        return
      }
    }

    const route = useAppStore.getState().aiBackendRoute
    const userPrompt = aiExtraPrompt.trim()
    const modelProfile = modelProfileFromRoute(route)
    const llmPayload = routeLlmProviderPayload(route)

    // 单章且正文为空：与「重写本章」相同，走门控流（质检未达标会循环重写）
    if (
      targetChapters.length === 1 &&
      shouldUseGatedDraft(writingConfig) &&
      !chapterHasNarrativeBody(targetChapters[0].content)
    ) {
      const sole = targetChapters[0]
      addGenTask({
        type: 'gated_rewrite_chapter',
        projectId,
        label: `门控生成《${sole.title}》`,
        params: {
          chapterId: sole.id,
          userPrompt,
          modelProfile,
          ...llmPayload,
        },
      })
      toast.success('已加入 AI 队列：质量门控写作（自动质检+重写）')
      setAiExtraPrompt('')
      return
    }

    addGenTask({
      type: 'continue_chapters',
      projectId,
      label: `从《${chapter.title}》起续写 ${targetChapters.length} 章`,
      params: {
        chapterIds: targetChapters.map(c => c.id),
        userPrompt,
        modelProfile,
        ...llmPayload,
      },
    })
    toast.success(`已加入 AI 队列：连续续写 ${targetChapters.length} 章`)
    setAiExtraPrompt('')
  }

  const applyAutoDebriefData = useCallback((
    data: AutoDebriefResponse,
    source: 'cache' | 'llm',
    opts?: { silent?: boolean },
  ) => {
    // 预填人物更新
    const newCharUpdates: typeof charUpdates = {}
    const suggestedCharIds = new Set<string>()
    for (const cu of data.character_updates || []) {
      const { character_id, character_name: _n, ...fields } = cu
      if (character_id && Object.keys(fields).some(k => (fields as any)[k])) {
        newCharUpdates[character_id] = fields
        suggestedCharIds.add(character_id)
      }
    }

    // 预填故事线更新
    const newSlBeats: typeof storylineBeats = {}
    const suggestedSlIds = new Set<string>()
    for (const su of data.storyline_updates || []) {
      const { storyline_id, storyline_name, ...fields } = su
      if (!Object.keys(fields).some(k => (fields as any)[k])) continue

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
        setContextOpen(true)
        setContextTab('debrief')
      }
    } else if (source === 'llm' && !opts?.silent) {
      toast('AI 未检测到明确的状态变化', { icon: 'ℹ️' })
    }
  }, [storyLines])

  /** 复盘前立即落库正文（服务端只读 DB，不读编辑器未保存内容） */
  const flushChapterSaveForDebrief = useCallback(async (): Promise<boolean> => {
    if (!editor) return hasHtmlTextContent(chapter.content)
    clearTimeout(saveTimer.current)
    const html = editor.getHTML()
    if (!hasHtmlTextContent(html)) return false
    if (html === chapter.content) return true
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content: html })
      upsertChapter(res.data)
      return true
    } catch {
      toast.error('保存正文失败，无法开始 AI 复盘')
      return false
    }
  }, [editor, chapter.content, chapter.id, projectId, upsertChapter])

  const debriefContentReady = useMemo(() => {
    if (editor && hasHtmlTextContent(editor.getHTML())) return true
    return hasHtmlTextContent(chapter.content)
  }, [editor, chapter.content, editorHtmlTick])

  /** 调用 AI 自动分析章节，预填复盘面板 */
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
        chapter_id: chapter.id,
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

  /** 打开复盘 Tab 时：仅读服务端缓存并预填（不调用 LLM） */
  const loadDebriefTabCache = useCallback(async () => {
    if (!hasHtmlTextContent(chapter.content)) return
    setDebriefCacheHydrating(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.autoDebrief(projectId, {
        chapter_id: chapter.id,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
        cache_only: true,
      })
      const data = res.data as AutoDebriefResponse
      if (data.error || data.cache_only_miss || !data.cached) return
      applyAutoDebriefData(data, 'cache', { silent: true })
      setDebriefFromQueueSnapshot(false)
    } catch { /* 静默：无缓存或网络失败不打扰 */ }
    finally {
      setDebriefCacheHydrating(false)
    }
  }, [projectId, chapter.id, applyAutoDebriefData])

  useEffect(() => {
    if (!contextOpen || contextTab !== 'debrief') return
    if (!hasHtmlTextContent(chapter.content)) return
    if (autoDebriefing || debriefSubmitting) return
    if (queueCommittedDebriefIds.has(chapter.id)) {
      const snap = queueDebriefSnapshot as AutoDebriefResponse | undefined
      const snapHasUi = snap && (
        (snap.character_updates?.length ?? 0) > 0
        || (snap.storyline_updates?.length ?? 0) > 0
        || (snap.new_characters?.length ?? 0) > 0
        || (snap.asset_updates && Object.keys(snap.asset_updates).length > 0)
        || (typeof snap.summary === 'string' && snap.summary.trim().length > 0)
        || !!snap.chapter_index
      )
      if (snapHasUi && queueSnapHydratedChapterRef.current !== chapter.id) {
        queueSnapHydratedChapterRef.current = chapter.id
        applyAutoDebriefData(snap, 'cache', { silent: true })
        setDebriefFromQueueSnapshot(true)
      }
      if (!queueDebriefToastShownRef.current.has(chapter.id)) {
        queueDebriefToastShownRef.current.add(chapter.id)
        toast('此章复盘已由队列自动完成', { icon: '✅' })
      }
      return
    }
    void loadDebriefTabCache()
  }, [
    contextOpen,
    contextTab,
    chapter.id,
    chapter.updated_at,
    autoDebriefing,
    debriefSubmitting,
    queueCommittedDebriefIds,
    queueDebriefSnapshot,
    loadDebriefTabCache,
    applyAutoDebriefData,
  ])

  const submitDebrief = async (selectedAssetUpdates?: Record<string, unknown>) => {
    const characterUpdates = Object.entries(charUpdates)
      .map(([character_id, upd]) => {
        const entry: Record<string, any> = { character_id }
        if (upd.current_realm) entry.current_realm = upd.current_realm
        if ((upd as { realm_rank?: number }).realm_rank != null) {
          entry.realm_rank = (upd as { realm_rank?: number }).realm_rank
        }
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
      .filter(e => Object.keys(e).length > 1) // exclude empty updates

    const storylineUpdates = Object.entries(storylineBeats)
      .map(([storyline_id, upd]) => {
        if (!isUuidLike(storyline_id)) return null
        const entry: Record<string, any> = { storyline_id }
        if (upd.status) entry.status = upd.status
        if (upd.beat) entry.append_beat = upd.beat
        return entry
      })
      .filter((e): e is Record<string, any> => !!e && Object.keys(e).length > 1)

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

    if (characterUpdates.length === 0 && storylineUpdates.length === 0 && !debriefNotes && !hasAssetUpdates && !hasChapterIndex && !hasReaderPromises) {
      toast('没有需要提交的更新', { icon: 'ℹ️' })
      return
    }

    setDebriefSubmitting(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.chapterDebrief(projectId, {
        chapter_id: chapter.id,
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
      const pc = Number((res.data as { promises_created?: number })?.promises_created ?? 0)
      const pf = Number((res.data as { promises_fulfilled?: number })?.promises_fulfilled ?? 0)
      const promiseToast = (pc > 0 || pf > 0) ? `（承诺 +${pc} / 兑现 ${pf}）` : ''
      toast.success(`${res.data.message}${promiseToast}`)
      setDebriefHistoryTick((t) => t + 1)
      const [refreshedStorylines, refreshedMemories, refreshedCharsRes] = await Promise.all([
        storylinesApi.list(projectId),
        aiApi.listMemory(projectId),
        charactersApi.list(projectId),
      ])
      setStoryLines(refreshedStorylines.data)
      setMemories(refreshedMemories.data)
      refreshedCharsRes.data.forEach((c: any) => useAppStore.getState().upsertCharacter(c))
      setQueueDebriefUiSnapshot(chapter.id, null)
      setDebriefFromQueueSnapshot(false)
      queueSnapHydratedChapterRef.current = null
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

  const cleanupChapter = async () => {
    const ok = window.confirm(
      `确认清理《${chapter.title}》？\n\n这会删除本章正文、版本历史、对应记忆数据和 ChapterIndex。大纲中的章节计划会保留，可稍后重新创建。`,
    )
    if (!ok) return

    setCleaningChapter(true)
    try {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      await chaptersApi.delete(projectId, chapter.id)

      const sorted = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
      const currentIndex = sorted.findIndex(c => c.id === chapter.id)
      const nextChapter = sorted[currentIndex + 1] || sorted[currentIndex - 1]

      removeChapter(chapter.id)
      setActiveChapterId(nextChapter?.id ?? null)

      const memoriesRes = await aiApi.listMemory(projectId)
      setMemories(memoriesRes.data)
      toast.success('章节已清理')
    } catch {
      toast.error('清理章节失败')
    } finally {
      setCleaningChapter(false)
    }
  }

  const runPreWriteWarning = async () => {
    setWarnLoading(true)
    setContextOpen(true)
    setContextTab('warn')
    // 拼接本章计划摘要（优先用 outlineNode，降级用章节标题）
    const planSummary = outlineNode
      ? [
          outlineNode.summary && `概述：${outlineNode.summary}`,
          outlineNode.hook && `开篇钩子：${outlineNode.hook}`,
          outlineNode.conflict && `核心事件：${outlineNode.conflict}`,
          outlineNode.highlight && `章末方向：${outlineNode.highlight}`,
        ].filter(Boolean).join('\n')
      : `第${chapter.sort_order ?? '?'}章《${chapter.title}》`
    try {
      const route = useAppStore.getState().aiBackendRoute
      const { data } = await aiApi.preWriteWarning(projectId, {
        chapter_id: chapter.id,
        chapter_plan_summary: planSummary,
        chapter_number: chapter.sort_order ?? 0,
        model_profile: modelProfileFromRoute(route),
        llm_provider_id: llmProviderIdFromRoute(route),
      })
      setWarnResult(normalizePreWriteWarnResult(data))
      if (data.record_id) setSelectedWarnRecordId(data.record_id)
      void aiApi.preWriteWarningHistory(projectId, chapter.id).then((r) => {
        setWarnHistory(parsePreWriteWarningHistoryPayload(r.data))
      }).catch(() => {})
    } catch {
      toast.error('写前预警请求失败')
    } finally {
      setWarnLoading(false)
    }
  }

  const openChapterHistory = async () => {
    setHistoryOpen(true)
    setVersionsLoading(true)
    setHistoryPreview(null)
    try {
      const r = await chaptersApi.listVersions(projectId, chapter.id)
      setVersionsList(r.data as ChapterVersion[])
    } catch {
      setVersionsList([])
      toast.error('无法加载版本列表')
    } finally {
      setVersionsLoading(false)
    }
  }

  const loadHistoryPreview = async (versionId: string) => {
    setHistoryPreviewLoading(true)
    try {
      const r = await chaptersApi.getVersion(projectId, chapter.id, versionId)
      setHistoryPreview(r.data as ChapterVersionDetail)
    } catch {
      toast.error('加载该版本正文失败')
    } finally {
      setHistoryPreviewLoading(false)
    }
  }

  const restoreHistoryVersion = async () => {
    if (!historyPreview || !editor) return
    if (!window.confirm('将用此历史版本替换当前正文（会先自动备份当前稿）。确定？')) return
    try {
      const plain = (chapter.content || '').replace(/<[^>]+>/g, '').trim()
      if (plain.length >= 1) {
        await chaptersApi.snapshot(projectId, chapter.id, '恢复历史版本前备份', true)
      }
      const res = await chaptersApi.update(projectId, chapter.id, {
        content: historyPreview.content,
        manuscript_raw_snapshot: null,
      })
      upsertChapter(res.data)
      editor.commands.setContent(historyPreview.content)
      setManuscriptView('source')
      toast.success('已恢复为所选历史版本')
      setHistoryOpen(false)
      setHistoryPreview(null)
    } catch {
      toast.error('恢复失败')
    }
  }

  // ─────────────────────────────────────────────────────────────────
  // 派生值
  // ─────────────────────────────────────────────────────────────────
  const wordCount       = editor?.storage.characterCount?.characters() ?? chapter.word_count
  const hasOutlineContent = outlineNode && (
    outlineNode.hook || outlineNode.summary || outlineNode.conflict || outlineNode.highlight
  )
  const currentStatus   = STATUS_OPTIONS.find(o => o.value === chapter.status) ?? STATUS_OPTIONS[0]
  const orderedChapters = useMemo(
    () => [...chapters].sort((a, b) => a.sort_order - b.sort_order),
    [chapters],
  )
  const currentChapterIndex = orderedChapters.findIndex(c => c.id === chapter.id)
  const previousChapter = currentChapterIndex > 0 ? orderedChapters[currentChapterIndex - 1] : null
  const previousChapterGenerated =
    !previousChapter
    || hasHtmlTextContent(previousChapter.content)
    || (
      isBookFirstChapterTitle(chapter, outlineNode)
      && !!previousChapter
      && !hasHtmlTextContent(previousChapter.content)
    )
  const generateBlockedReason = previousChapterGenerated
    ? null
    : `请先生成上一章《${previousChapter?.title ?? '未命名章节'}》`
  const chapterGenBusy = useMemo(
    () =>
      genQueue.some(
        t =>
          t.projectId === projectId
          && (t.status === 'pending' || t.status === 'running')
          && (
            (t.type === 'continue_chapters'
              && Array.isArray(t.params?.chapterIds)
              && t.params.chapterIds.includes(chapter.id))
            || (t.type === 'rewrite_chapter' && t.params?.chapterId === chapter.id)
            || (t.type === 'gated_rewrite_chapter' && t.params?.chapterId === chapter.id)
          ),
      ),
    [genQueue, projectId, chapter.id],
  )
  const generateDisabled = chapterGenBusy || !previousChapterGenerated
  const remainingChapterCount = currentChapterIndex >= 0
    ? Math.max(1, orderedChapters.length - currentChapterIndex)
    : 1
  const normalizedContinueCount = Math.min(
    Math.max(1, continueChapterCount || 1),
    remainingChapterCount,
  )
  const prevTail        = prevChapter?.content ? htmlTail(prevChapter.content) : null
  const elapsedMin      = Math.floor(sessionElapsed / 60)
  const elapsedLabel    = elapsedMin > 0 ? `${elapsedMin}m` : sessionElapsed > 0 ? `${sessionElapsed}s` : ''

  // ─────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────
  return (
    <div className={clsx(
      'flex flex-col h-full transition-colors duration-200',
      focusMode ? 'bg-[#fafaf8]' : 'bg-novel-shell/40',
    )}>

      {/* ══════════════════════ 顶部工具栏 ══════════════════════════ */}
      <div className={clsx(
        'flex items-center justify-between px-5 py-2.5 border-b shrink-0 transition-all duration-200',
        focusMode ? 'border-transparent bg-transparent' : 'border-novel-border bg-novel-raised/95',
      )}>
        {/* 左侧：章名 + 状态 */}
        <div className="flex items-center gap-3 min-w-0">
          <h2 className={clsx(
            'font-semibold truncate max-w-xs lg:max-w-lg transition-colors',
            focusMode ? 'text-gray-400 text-sm font-normal' : 'text-novel-ink',
          )}>
            {chapter.title}
          </h2>

          {/* 状态下拉（专注模式隐藏）*/}
          {!focusMode && (
            <div className="relative" ref={statusRef}>
              <button type="button" onClick={() => setStatusOpen(v => !v)}
                className="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border border-novel-border bg-novel-card hover:bg-novel-panel transition-novel">
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', currentStatus.dotCls)} />
                <span className={currentStatus.textCls}>{currentStatus.label}</span>
                <ChevronDown size={10} className="text-novel-ink-faint" />
              </button>
              {statusOpen && (
                <div className="absolute top-full left-0 mt-1 bg-white border border-novel-border rounded-novel shadow-lg z-50 py-1 min-w-[96px]">
                  {STATUS_OPTIONS.map(opt => (
                    <button key={opt.value} type="button" onClick={() => updateStatus(opt.value)}
                      className={clsx(
                        'w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-novel-panel transition-novel',
                        chapter.status === opt.value && 'bg-novel-panel',
                      )}>
                      <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', opt.dotCls)} />
                      <span className={opt.textCls}>{opt.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 右侧：统计 + 工具按钮 */}
        <div className="flex items-center gap-2 shrink-0">
          {/* 本次写作统计 */}
          {sessionDelta !== 0 && !focusMode && (
            <div className="hidden sm:flex items-center gap-2 text-[11px]">
              <span className={clsx('flex items-center gap-1 font-medium', sessionDelta > 0 ? 'text-green-600' : 'text-red-500')}>
                <PenLine size={11} className="opacity-70" />
                {sessionDelta > 0 ? '+' : ''}{sessionDelta.toLocaleString()} 字
              </span>
              {elapsedLabel && (
                <span className="flex items-center gap-0.5 text-novel-ink-faint">
                  <Clock size={10} />{elapsedLabel}
                </span>
              )}
            </div>
          )}

          {/* 总字数 */}
          <span className={clsx('text-sm', focusMode ? 'text-gray-400' : 'text-novel-ink-muted')}>
            {wordCount.toLocaleString()} 字
          </span>

          {/* 分场写作入口（三层调度：章纲→分场→正文→缝合） */}
          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'scene')); setContextTab('scene') }}
              title="分场写作（推荐）：生成分场 → 逐场起草 → 缝合进章节"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'scene'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_BUTTON_IDLE)}>
              <Layers size={14} />分场
            </button>
          )}

          {/* 章节计划 */}
          {!focusMode && outlineNode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'plan')); setContextTab('plan') }}
              title="章节计划"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'plan'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_BUTTON_IDLE)}>
              <BookOpen size={14} />计划
            </button>
          )}

          {/* 复盘（暖色强调，与灰底工具区分） */}
          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'debrief')); setContextTab('debrief') }}
              title="章节复盘（更新人物状态/故事线）"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'debrief'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_DEBRIEF_BUTTON_IDLE)}>
              <CheckSquare size={15} strokeWidth={2.25} className="shrink-0" />复盘
            </button>
          )}

          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'chindex')); setContextTab('chindex') }}
              title="情节索引（核心事件、钩子、伏笔、连续性 — 可编辑保存）"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'chindex'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_BUTTON_IDLE)}>
              <ClipboardList size={14} />索引
            </button>
          )}

          {/* 写前预警 */}
          {!focusMode && (
            <button type="button"
              onClick={runPreWriteWarning}
              disabled={warnLoading}
              title="写前预警：对照记忆/伏笔台账检查本章计划的潜在矛盾"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'warn'
                  ? 'border-rose-300 bg-rose-50 text-rose-600'
                  : warnResult && !warnResult.ok
                    ? 'border-rose-300 bg-rose-50 text-rose-500'
                    : TOP_TOOL_BUTTON_IDLE)}>
              {warnLoading
                ? <RefreshCw size={14} className="animate-spin" />
                : warnResult && !warnResult.ok
                  ? <ShieldAlert size={14} />
                  : <ShieldAlert size={14} />}
              预警
            </button>
          )}

          {!focusMode && (
            <button type="button"
              onClick={() => void openChapterHistory()}
              title="正文版本历史：查看、对比此前保存或 AI 覆盖前的快照"
              className={clsx(TOP_TOOL_BUTTON_BASE, TOP_TOOL_BUTTON_IDLE)}>
              <History size={14} />版本
            </button>
          )}

          {!focusMode && (
            <button type="button" onClick={cleanupChapter} disabled={cleaningChapter}
              title="清理章节"
              className={TOP_TOOL_ICON_BUTTON}>
              {cleaningChapter ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          )}

          {/* 专注模式切换 */}
          <button type="button" onClick={() => setFocusMode(v => !v)}
            title={focusMode ? '退出专注模式' : '专注写作模式（隐藏工具栏）'}
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              focusMode ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_BUTTON_IDLE,
            )}>
            {focusMode ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            {focusMode ? '退出专注' : '专注'}
          </button>

          {/* 保存（与左侧工具组视觉分隔） */}
          <div className="hidden sm:block h-6 w-px bg-novel-border shrink-0 mx-0.5" aria-hidden />
          <button type="button" onClick={manualSave}
            className={TOP_TOOL_PRIMARY_BUTTON}>
            <Save size={16} strokeWidth={2.25} className="shrink-0" />
            保存
          </button>
        </div>
      </div>

      {/* ══════════════════════ 主体区 ══════════════════════════════ */}
      <div className="flex flex-1 min-h-0">

        {/* ── 编辑区 ── */}
        <div className="flex-1 flex flex-col min-h-0">

          {/* 正文编辑器 */}
          <div className={clsx(
            'flex-1 overflow-auto',
            focusMode && 'flex justify-center',
          )}>
            <div className={clsx(focusMode && 'w-full max-w-2xl', 'relative w-full min-h-[50vh]')}>
              <div className="sticky top-2 z-30 flex justify-end pointer-events-none px-4 sm:px-10 pt-1">
                <div className="pointer-events-auto">{manuscriptViewToggle}</div>
              </div>
              {manuscriptView === 'prose' && !focusMode && (
                <div className="rounded-novel border border-dashed border-amber-200/80 bg-amber-50/40 px-3 py-2 mx-4 sm:mx-10 mb-2 text-[11px] text-amber-900/90">
                  {hasManuscriptRawSnapshot ? (
                    <>
                      正文视图：编辑入库叙事。切换「原文」可对照模型最近一次返回全文（含{' '}
                      <code className="text-[10px] px-1">### ch_…</code> 稿末索引）。
                    </>
                  ) : (
                    <>
                      正文视图：只读预览叙事部分（稿末 <code className="text-[10px] px-1">### ch_…</code>{' '}
                      索引块已隐藏）。编辑请切回「原文」。
                    </>
                  )}
                </div>
              )}
              {manuscriptView === 'prose' && focusMode && (
                <p className="text-[10px] text-center text-novel-ink-faint px-4 mb-2">
                  {hasManuscriptRawSnapshot ? '叙事编辑 · 切「原文」对照模型全文' : '正文预览 · 切「原文」可编辑'}
                </p>
              )}
              {manuscriptView === 'prose' ? (
                hasManuscriptRawSnapshot ? (
                  <EditorContent editor={editor} className="h-full" />
                ) : (
                  <div
                    className="prose prose-lg max-w-readable w-full px-6 sm:px-10 pb-8 pt-2 mx-auto min-h-[55vh]"
                    dangerouslySetInnerHTML={{ __html: prosePreviewHtml }}
                  />
                )
              ) : null}
              <div className={clsx(manuscriptView === 'prose' && 'hidden')}>
                {hasManuscriptRawSnapshot ? (
                  <div
                    className="prose prose-lg max-w-readable w-full px-6 sm:px-10 pb-8 pt-2 mx-auto min-h-[55vh]"
                    dangerouslySetInnerHTML={{ __html: rawSnapshotPreviewHtml }}
                  />
                ) : (
                  <EditorContent editor={editor} className="h-full" />
                )}
              </div>
            </div>
          </div>

          {/* 选中文字快捷操作栏（专注模式下隐藏）*/}
          {showSelectionBar && !focusMode && (
            <div className="border-t border-violet-100 bg-violet-50/80 px-5 py-2.5 shrink-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] text-violet-600 font-medium flex items-center gap-1 mr-1 shrink-0">
                  <Sparkles size={11} />
                  已选 {selectionText.length} 字
                </span>
                <button type="button"
                  disabled={chapterGenBusy}
                  onClick={() => runPromptAction('rewrite')}
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50">
                  <RefreshCw size={11} />改写
                </button>
                <button type="button"
                  disabled={chapterGenBusy}
                  onClick={() => runPromptAction('expand')}
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50">
                  <Feather size={11} />扩写
                </button>
                <button type="button" onClick={() => setShowSelectionBar(false)}
                  className="ml-auto text-violet-300 hover:text-violet-500 p-0.5 shrink-0">
                  <X size={12} />
                </button>
              </div>
            </div>
          )}

          {/* AI 输入工具区（专注模式下隐藏）*/}
          {!focusMode && (
            <div className="border-t border-gray-100 bg-[#fbfaf7] px-5 py-4 shrink-0">
              <div className="rounded-lg border border-gray-200 bg-white px-3 py-3 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
                  <label className="flex-1 min-w-0">
                    <span className="mb-1.5 block text-[11px] font-semibold text-gray-500">AI 续写要求</span>
                    <input
                      type="text"
                      value={aiExtraPrompt}
                      onChange={e => setAiExtraPrompt(e.target.value)}
                      disabled={chapterGenBusy}
                      placeholder="输入风格、情节走向或禁忌；留空则按大纲和上下文续写"
                      className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-amber-400 focus:ring-2 focus:ring-amber-100 disabled:opacity-60"
                    />
                  </label>

                  <div className="flex flex-wrap items-end gap-2 lg:self-end">
                    <label className="w-28">
                      <span className="mb-1.5 block text-[11px] font-semibold text-gray-500">连续章节</span>
                      <input
                        type="number"
                        min={1}
                        max={remainingChapterCount}
                        value={normalizedContinueCount}
                        disabled={chapterGenBusy}
                        onChange={e => {
                          const next = Number(e.target.value)
                          setContinueChapterCount(Number.isFinite(next) ? next : 1)
                        }}
                        className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-800 outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100 disabled:opacity-60"
                      />
                    </label>

                    <div className="flex flex-col gap-1.5">
                      <span className="block text-[11px] font-semibold text-transparent select-none">操作</span>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={enqueueContinueChapters}
                          disabled={generateDisabled}
                          title={generateBlockedReason ?? undefined}
                          className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-60">
                          {normalizedContinueCount > 1
                            ? <ListPlus size={15} />
                            : <Sparkles size={15} className={chapterGenBusy ? 'animate-pulse' : ''} />}
                          {normalizedContinueCount > 1 ? '加入队列' : chapterGenBusy ? '队列中…' : '生成'}
                        </button>

                        {wordCount > 0 && (
                          <button type="button" onClick={() => generateDraft({ replaceExisting: true })} disabled={chapterGenBusy}
                            className="flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:opacity-60">
                            <RefreshCw size={14} />重写本章
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* ── 底部伏笔快查面板（专注模式隐藏）── */}
          {!focusMode && (openForeshadows.length > 0 || currentChIndex) && (
            <div className="border-t border-amber-100 bg-amber-50/40 shrink-0">
              {/* 折叠头 */}
              <button
                type="button"
                onClick={() => setBottomPanelOpen(v => !v)}
                className="w-full flex items-center justify-between px-4 py-2 text-xs text-amber-700 hover:bg-amber-50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Anchor size={12} />
                  <span className="font-medium">线索面板</span>
                  {openForeshadows.length > 0 && (
                    <span className="bg-amber-200 text-amber-800 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
                      {openForeshadows.length} 条未回收伏笔
                    </span>
                  )}
                  {currentChIndex && (
                    <span className="bg-blue-100 text-blue-600 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
                      情节档案已生成
                    </span>
                  )}
                </div>
                {bottomPanelOpen
                  ? <ChevronDown size={12} className="text-amber-400" />
                  : <ChevronRight size={12} className="text-amber-400" />}
              </button>

              {/* 展开内容 */}
              {bottomPanelOpen && (
                <div className="px-4 pb-3 space-y-3 max-h-52 overflow-auto">
                  {/* 未回收伏笔列表 */}
                  {openForeshadows.length > 0 && (
                    <div>
                      <div className="text-[10px] font-semibold text-amber-600 uppercase tracking-wider mb-1.5">
                        未回收伏笔 · {openForeshadows.length} 条
                      </div>
                      <div className="space-y-1">
                        {openForeshadows.map(f => (
                          <div key={f.id} className="flex items-start gap-2 text-xs">
                            <Circle size={8} className="text-amber-400 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <span className="font-medium text-gray-700">{f.title}</span>
                              {f.code && (
                                <span className="ml-1.5 font-mono text-[10px] text-gray-400">{f.code}</span>
                              )}
                              {f.planned_resolve_chapter && (
                                <span className="ml-1.5 text-[10px] text-amber-500">
                                  预计第 {f.planned_resolve_chapter} 章{f.planned_action === 'develop' ? '铺垫' : '回收'}
                                </span>
                              )}
                              {f.description && (
                                <p className="text-[11px] text-gray-400 mt-0.5 truncate">{f.description}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 当前章情节档案摘要 */}
                  {currentChIndex && (
                    <div>
                      <div className="text-[10px] font-semibold text-blue-500 uppercase tracking-wider mb-1.5">
                        情节档案 · 第 {currentChIndex.chapter_number} 章
                      </div>
                      {currentChIndex.core_events?.length > 0 && (
                        <div className="space-y-0.5">
                          {currentChIndex.core_events.slice(0, 3).map((ev, i) => (
                            <div key={i} className="text-[11px] text-gray-600 flex gap-1.5">
                              <span className="text-blue-300 shrink-0">•</span>
                              <span>{typeof ev === 'string' ? ev : JSON.stringify(ev)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {currentChIndex.ending_hook && (
                        <p className="text-[11px] text-gray-400 italic mt-1">
                          钩子："{currentChIndex.ending_hook}"
                        </p>
                      )}
                      {currentChIndex.actual_foreshadows_laid?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {currentChIndex.actual_foreshadows_laid.map((f, i) => (
                            <span key={i} className="text-[10px] bg-amber-50 text-amber-600 border border-amber-100 px-1.5 py-0.5 rounded">
                              埋：{typeof f === 'string' ? f : (f.description as string)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 专注模式浮动状态栏 */}
          {focusMode && (
            <div className="flex justify-center pb-5 shrink-0 pointer-events-none px-3">
              <div className="flex flex-wrap items-center justify-center gap-3 bg-white/90 backdrop-blur-md border border-gray-200/90 rounded-2xl px-4 py-2.5 shadow-md pointer-events-auto max-w-full">
                <span className="text-xs text-gray-500 font-medium">{wordCount.toLocaleString()} 字</span>
                {sessionDelta !== 0 && (
                  <span className={clsx('text-xs font-semibold', sessionDelta > 0 ? 'text-green-600' : 'text-red-400')}>
                    {sessionDelta > 0 ? '+' : ''}{sessionDelta}
                  </span>
                )}
                <div className="hidden sm:block h-5 w-px bg-gray-200 shrink-0" aria-hidden />
                <button type="button" onClick={manualSave}
                  className={`${TOP_TOOL_PRIMARY_BUTTON} h-8 min-w-[5rem] px-3 text-[13px]`}>
                  <Save size={14} strokeWidth={2.25} className="shrink-0" />
                  保存
                </button>
                <button type="button" onClick={() => void openChapterHistory()}
                  className="text-xs font-medium text-gray-600 hover:text-gray-900 flex items-center gap-1 rounded-lg px-2 py-1 border border-gray-200 bg-white hover:bg-gray-50">
                  <History size={12} />版本
                </button>
                <button type="button" onClick={() => setFocusMode(false)}
                  className="text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-gray-100">
                  <Minimize2 size={11} />退出专注
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ══════════════════ 右侧上下文面板 ══════════════════════ */}
        {contextOpen && !focusMode && (
          <div className={clsx(
            'shrink-0 border-l border-novel-border bg-novel-panel flex flex-col overflow-hidden',
            contextTab === 'chindex' ? 'w-[24rem]' : contextTab === 'warn' ? 'w-[22rem]' : 'w-80',
          )}>

            {/* Tab 导航头 */}
            <div className="flex items-center border-b border-novel-border bg-novel-card/80 shrink-0">
              {(
                [
                  { key: 'plan',    label: '计划',  icon: <BookOpen size={11} /> },
                  { key: 'scene',   label: '场景',  icon: <Users size={11} /> },
                  { key: 'debrief', label: '复盘',  icon: <CheckSquare size={11} /> },
                  { key: 'chindex', label: '索引',  icon: <ClipboardList size={11} /> },
                  { key: 'warn',    label: '预警',  icon: <ShieldAlert size={11} /> },
                ] as const
              ).map(tab => (
                <button key={tab.key} type="button"
                  onClick={() => setContextTab(tab.key)}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-1 py-2.5 text-[11px] font-medium border-b-2 transition-novel',
                    contextTab === tab.key
                      ? 'border-novel-accent text-novel-accent'
                      : 'border-transparent text-novel-ink-muted hover:text-novel-ink',
                  )}>
                  {tab.icon}{tab.label}
                </button>
              ))}
              <button type="button" onClick={() => setContextOpen(false)}
                className="px-2.5 text-novel-ink-faint hover:text-novel-ink">
                <X size={13} />
              </button>
            </div>

            {/* Tab 内容区 */}
            <div className="flex-1 overflow-auto">

              {/* ── 章节计划 Tab ── */}
              {contextTab === 'plan' && (
                <div className="p-4 space-y-3">
                  {outlineNode ? (
                    <>
                      {outlineNode.hook && (
                        <PlanCard icon={<Zap size={12} className="text-amber-500" />}
                          label="开篇钩子" sublabel="第一句话的使命"
                          content={outlineNode.hook} accent="amber" />
                      )}
                      {outlineNode.summary && (
                        <PlanCard icon={<Target size={12} className="text-blue-500" />}
                          label="核心事件" sublabel="删掉会损失什么"
                          content={outlineNode.summary} accent="blue" />
                      )}
                      {outlineNode.conflict && (
                        <PlanCard icon={<Users size={12} className="text-purple-500" />}
                          label="人物变化" sublabel="不可逆的认知或处境转变"
                          content={outlineNode.conflict} accent="purple" />
                      )}
                      {outlineNode.highlight && (
                        <PlanCard icon={<Flag size={12} className="text-red-500" />}
                          label="章末钩子" sublabel="让读者无法放下的最后一句"
                          content={outlineNode.highlight} accent="red" />
                      )}
                      {(outlineNode.extra as Record<string, string>)?.foreshadow && (
                        <PlanCard icon={<GitBranch size={12} className="text-green-500" />}
                          label="伏笔管理" sublabel="埋[…] 收[…]"
                          content={(outlineNode.extra as Record<string, string>).foreshadow} accent="green" />
                      )}
                      {outlineNode.power_milestone && (
                        <PlanCard icon={<TrendingUp size={12} className="text-indigo-500" />}
                          label="实力里程碑" sublabel="本章境界突破或技能习得"
                          content={outlineNode.power_milestone} accent="indigo" />
                      )}
                      {outlineNode.emotional_tone && (
                        <div className="rounded-novel border border-gray-100 bg-gray-50/70 px-3 py-2">
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span className="text-[10px] font-semibold text-gray-500">情感基调</span>
                          </div>
                          <p className="text-xs text-novel-ink">{outlineNode.emotional_tone}</p>
                        </div>
                      )}
                      {outlineNode.foreshadows_laid && outlineNode.foreshadows_laid.length > 0 && (
                        <div className="rounded-novel border border-green-100 bg-green-50/60 px-3 py-2">
                          <div className="flex items-center gap-1.5 mb-1.5">
                            <GitBranch size={12} className="text-green-500" />
                            <span className="text-xs font-semibold text-green-700">本章埋设的伏笔</span>
                          </div>
                          <ul className="space-y-1">
                            {outlineNode.foreshadows_laid.map((f, i) => (
                              <li key={i} className="text-xs text-novel-ink leading-snug before:content-['·'] before:mr-1.5 before:text-green-400">
                                {typeof f === 'string' ? f : f.description}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {!hasOutlineContent && (
                        <p className="text-xs text-novel-ink-faint text-center py-6 italic leading-relaxed">
                          大纲节点尚未填写计划细节<br />可在「大纲」页选中本章节点后编辑
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-xs text-novel-ink-faint text-center py-6 italic">
                      此章节未挂载大纲节点
                    </p>
                  )}
                </div>
              )}

              {/* ── 分场写作 Tab（三层调度：章纲→分场→正文→缝合） ── */}
              {contextTab === 'scene' && (
                <ScenePipelinePanel
                  projectId={projectId}
                  chapter={chapter}
                  outlineNode={outlineNode}
                  onStitchDone={async () => {
                    try {
                      const res = await chaptersApi.get(projectId, chapter.id)
                      upsertChapter(res.data)
                    } catch { /* 缝合后刷新失败时静默，用户可手动保存 */ }
                  }}
                />
              )}

              {/* ── 复盘 Tab ── */}
              {contextTab === 'debrief' && (
                <DebriefPanel
                  projectId={projectId}
                  chapter={chapter}
                  outlineNode={outlineNode}
                  characters={characters}
                  storyLines={storyLines}
                  charUpdates={charUpdates}
                  setCharUpdates={setCharUpdates}
                  storylineBeats={storylineBeats}
                  setStorylineBeats={setStorylineBeats}
                  debriefNotes={debriefNotes}
                  setDebriefNotes={setDebriefNotes}
                  submitting={debriefSubmitting}
                  autoDebriefing={autoDebriefing}
                  cacheHydrating={debriefCacheHydrating}
                  aiSuggestedCharIds={aiSuggestedCharIds}
                  aiSuggestedSlIds={aiSuggestedSlIds}
                  aiSuggestedAssetUpdates={aiSuggestedAssetUpdates}
                  aiNewCharacters={aiNewCharacters}
                  aiNewReaderPromises={aiNewReaderPromises}
                  aiFulfilledPromiseTexts={aiFulfilledPromiseTexts}
                  onRemoveNewPromise={(idx) => setAiNewReaderPromises(prev => prev.filter((_, i) => i !== idx))}
                  onRemoveFulfilledPromise={(idx) => setAiFulfilledPromiseTexts(prev => prev.filter((_, i) => i !== idx))}
                  aiSummary={aiDebriefSummary}
                  onAutoDebrief={runAutoDebrief}
                  onSubmit={submitDebrief}
                  fromQueueSnapshot={debriefFromQueueSnapshot}
                  debriefHistoryTick={debriefHistoryTick}
                  debriefContentReady={debriefContentReady}
                />
              )}

              {contextTab === 'chindex' && (
                <ChapterIndexEditPanel
                  projectId={projectId}
                  chapter={chapter}
                  index={currentChIndex}
                  onSaved={setCurrentChIndex}
                  onForeshadowsMayChange={() => {
                    foreshadowsApi.list(projectId, 'open').then(r => setOpenForeshadows(r.data)).catch(() => {})
                  }}
                />
              )}

              {/* ── 写前预警 Tab ── */}
              {contextTab === 'warn' && (
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-novel-ink flex items-center gap-1.5">
                      <ShieldAlert size={13} className="text-rose-500" />写前预警
                    </span>
                    <button type="button" onClick={runPreWriteWarning} disabled={warnLoading}
                      className="text-xs px-2.5 py-1 rounded-lg border border-novel-border bg-novel-card hover:bg-novel-panel transition-novel disabled:opacity-40 flex items-center gap-1">
                      {warnLoading ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                      重新检测
                    </button>
                  </div>

                  {warnHistory.length > 0 && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">历史记录</label>
                      <select
                        value={selectedWarnRecordId ?? warnHistory[0]?.id ?? ''}
                        onChange={(e) => {
                          const id = e.target.value
                          const row = warnHistory.find(h => h.id === id)
                          if (row) {
                            setSelectedWarnRecordId(id)
                            setWarnResult(normalizePreWriteWarnResult(row.result))
                          }
                        }}
                        className="w-full text-xs rounded-lg border border-novel-border bg-novel-panel px-2 py-1.5 text-novel-ink"
                      >
                        {warnHistory.map((h) => (
                          <option key={h.id} value={h.id}>
                            {(h.created_at && !Number.isNaN(new Date(h.created_at).getTime()))
                              ? new Date(h.created_at).toLocaleString()
                              : '未知时间'}
                            {' · '}{h.result?.risk_count ?? 0} 条风险 · {h.model_profile || 'local'}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {warnLoading && (
                    <div className="text-xs text-novel-ink-muted text-center py-8">
                      <RefreshCw size={16} className="animate-spin mx-auto mb-2 text-rose-400" />
                      正在对照记忆库检查矛盾…
                    </div>
                  )}

                  {!warnLoading && !warnResult && (
                    <div className="text-xs text-novel-ink-faint text-center py-8 leading-relaxed">
                      {gatedPreWarnDoneForChapter
                        ? <>门控写作已完成写前预警，正在同步记录…<br />若仍为空请点「重新检测」</>
                        : <>点击工具栏「预警」或门控生成后<br />可查看连续性、伏笔与写法简报</>}
                    </div>
                  )}

                  {!warnLoading && warnResult && (
                    <>
                      {/* 总体状态 */}
                      <div className={clsx(
                        'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium',
                        warnResult.ok
                          ? 'bg-green-50 border border-green-200 text-green-700'
                          : 'bg-rose-50 border border-rose-200 text-rose-700',
                      )}>
                        {warnResult.ok ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
                        {warnResult.ok
                          ? `未发现高危风险，可以动笔`
                          : `发现 ${warnResult.risk_count} 处风险，建议先修正`}
                      </div>

                      {/* ── 主角状态锁定 ── */}
                      {warnResult.protagonist_fact_sheet && (
                        warnResult.protagonist_fact_sheet.realm ||
                        warnResult.protagonist_fact_sheet.key_skills.length > 0 ||
                        warnResult.protagonist_fact_sheet.forbidden.length > 0
                      ) && (
                        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-2.5 space-y-1.5">
                          <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wide flex items-center gap-1">
                            <Target size={10} />主角状态锁定
                          </p>
                          {warnResult.protagonist_fact_sheet.realm && (
                            <p className="text-xs text-blue-900">
                              <span className="font-medium">境界：</span>{warnResult.protagonist_fact_sheet.realm}
                              {warnResult.protagonist_fact_sheet.location && (
                                <span className="ml-2 text-blue-700">／位置：{warnResult.protagonist_fact_sheet.location}</span>
                              )}
                            </p>
                          )}
                          {warnResult.protagonist_fact_sheet.key_skills.length > 0 && (
                            <div className="text-xs text-blue-800 space-y-0.5">
                              <span className="font-medium">可用技能：</span>
                              {warnResult.protagonist_fact_sheet.key_skills.map((s, i) => (
                                <div key={i} className="pl-2 text-blue-700 leading-relaxed">· {s}</div>
                              ))}
                            </div>
                          )}
                          {warnResult.protagonist_fact_sheet.key_items.length > 0 && (
                            <div className="text-xs text-blue-800 space-y-0.5">
                              <span className="font-medium">持有道具：</span>
                              {warnResult.protagonist_fact_sheet.key_items.map((s, i) => (
                                <div key={i} className="pl-2 text-blue-700 leading-relaxed">· {s}</div>
                              ))}
                            </div>
                          )}
                          {warnResult.protagonist_fact_sheet.forbidden.length > 0 && (
                            <div className="text-xs space-y-0.5">
                              <span className="font-medium text-rose-700">⛔ 本章禁止：</span>
                              {warnResult.protagonist_fact_sheet.forbidden.map((s, i) => (
                                <div key={i} className="pl-2 text-rose-600 leading-relaxed">· {s}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* ── 本章写作简报 ── */}
                      {warnResult.writing_brief && (
                        warnResult.writing_brief.opening_strategy ||
                        warnResult.writing_brief.conflict_structure ||
                        warnResult.writing_brief.closing_hook
                      ) && (
                        <div className="rounded-lg border border-purple-200 bg-purple-50/50 p-2.5 space-y-1.5">
                          <p className="text-[10px] font-semibold text-purple-700 uppercase tracking-wide flex items-center gap-1">
                            <Feather size={10} />本章写法简报
                          </p>
                          {warnResult.writing_brief.opening_strategy && (
                            <div className="text-xs">
                              <span className="font-medium text-purple-800">开篇策略：</span>
                              <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.opening_strategy}</span>
                            </div>
                          )}
                          {warnResult.writing_brief.conflict_structure && (
                            <div className="text-xs">
                              <span className="font-medium text-purple-800">冲突节拍：</span>
                              <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.conflict_structure}</span>
                            </div>
                          )}
                          {warnResult.writing_brief.closing_hook && (
                            <div className="text-xs">
                              <span className="font-medium text-purple-800">章末钩子：</span>
                              <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.closing_hook}</span>
                            </div>
                          )}
                          {warnResult.writing_brief.word_rhythm && (
                            <div className="text-xs">
                              <span className="font-medium text-purple-800">字数节奏：</span>
                              <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.word_rhythm}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* ── 必发事件 ── */}
                      {(warnResult.must_events?.length ?? 0) > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide flex items-center gap-1">
                            <CheckCircle size={10} className="text-emerald-500" />必发事件
                          </p>
                          {warnResult.must_events!.map((ev, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-xs text-novel-ink">
                              <span className="text-emerald-500 shrink-0 mt-0.5 font-bold">{i + 1}.</span>
                              <span className="leading-relaxed">{ev}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* ── 幻觉预防 ── */}
                      {(warnResult.hallucination_traps?.length ?? 0) > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide flex items-center gap-1">
                            <ShieldAlert size={10} className="text-amber-500" />幻觉预防清单
                          </p>
                          {warnResult.hallucination_traps!.map((trap, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                              <span className="shrink-0 mt-0.5">⚠</span>
                              <span className="leading-relaxed">{trap}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* ── 风险列表 ── */}
                      {warnResult.risks.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">风险扫描</p>
                          {warnResult.risks.map((risk, i) => (
                            <div key={i} className={clsx(
                              'rounded-lg border p-2.5 text-xs space-y-1',
                              risk.severity === 'critical' || risk.severity === 'high'
                                ? 'border-rose-200 bg-rose-50'
                                : 'border-amber-200 bg-amber-50',
                            )}>
                              <div className="flex items-center gap-1.5 font-medium">
                                <span className={clsx(
                                  'px-1.5 py-0.5 rounded text-[10px]',
                                  risk.severity === 'critical' || risk.severity === 'high'
                                    ? 'bg-rose-200 text-rose-700'
                                    : 'bg-amber-200 text-amber-700',
                                )}>{risk.severity}</span>
                                <span className="text-novel-ink-muted">{risk.type}</span>
                              </div>
                              <p className="text-novel-ink leading-relaxed">{risk.description}</p>
                              {risk.suggested_fix && (
                                <p className="text-novel-ink-muted leading-relaxed border-t border-current/10 pt-1">
                                  建议：{risk.suggested_fix}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* ── 写前提醒 ── */}
                      {warnResult.reminders.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">写前提醒</p>
                          {warnResult.reminders.map((r, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-xs text-novel-ink-muted">
                              <span className="text-novel-accent shrink-0 mt-0.5">·</span>
                              <span className="leading-relaxed">{r}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

            </div>
          </div>
        )}
      </div>

      {historyOpen && (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/50 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="chapter-history-title"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setHistoryOpen(false) }}
        >
          <div
            className="w-full max-w-4xl max-h-[min(90vh,720px)] flex flex-col rounded-2xl border border-novel-border bg-novel-card shadow-2xl overflow-hidden"
            onMouseDown={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-novel-border bg-novel-panel shrink-0">
              <h3 id="chapter-history-title" className="text-sm font-semibold text-novel-ink flex items-center gap-2">
                <History size={16} className="text-novel-accent" />
                正文版本历史
              </h3>
              <button type="button" onClick={() => setHistoryOpen(false)}
                className="p-1.5 rounded-lg text-novel-ink-faint hover:text-novel-ink hover:bg-novel-shell transition-novel">
                <X size={16} />
              </button>
            </div>
            <p className="text-[11px] text-novel-ink-faint px-4 py-2 border-b border-novel-border/80 bg-novel-shell/40">
              含「手动保存」与 AI 续写/重写覆盖前的自动备份。点选一条可预览；恢复会先备份当前正文再替换。
            </p>
            <div className="flex flex-1 min-h-0">
              <div className="w-[13.5rem] shrink-0 border-r border-novel-border overflow-auto bg-novel-shell/30">
                {versionsLoading ? (
                  <p className="text-xs text-novel-ink-faint p-3">加载中…</p>
                ) : versionsList.length === 0 ? (
                  <p className="text-xs text-novel-ink-faint p-3">暂无历史版本<br /><span className="text-[10px]">保存本章或经 AI 改写后会自动生成</span></p>
                ) : (
                  <ul className="p-2 space-y-1">
                    {versionsList.map(v => (
                      <li key={v.id}>
                        <button type="button"
                          onClick={() => void loadHistoryPreview(v.id)}
                          className={clsx(
                            'w-full text-left rounded-lg px-2.5 py-2 text-[11px] transition-novel border',
                            historyPreview?.id === v.id
                              ? 'border-novel-accent bg-novel-panel text-novel-accent'
                              : 'border-transparent hover:bg-novel-card text-novel-ink',
                          )}>
                          <div className="font-medium truncate">
                            {new Date(v.created_at).toLocaleString('zh-CN', {
                              month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                            })}
                          </div>
                          <div className="text-[10px] text-novel-ink-faint truncate mt-0.5">
                            {v.is_auto ? '自动' : '手动'}
                            {v.note ? ` · ${v.note}` : ''}
                            {typeof v.word_count === 'number' ? ` · ${v.word_count} 字` : ''}
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-white">
                {historyPreviewLoading && (
                  <div className="flex-1 flex items-center justify-center text-sm text-novel-ink-faint">加载正文…</div>
                )}
                {!historyPreviewLoading && !historyPreview && (
                  <div className="flex-1 flex items-center justify-center text-sm text-novel-ink-faint px-6 text-center">
                    在左侧选择一条版本以预览 HTML 正文
                  </div>
                )}
                {!historyPreviewLoading && historyPreview && (
                  <>
                    <div className="shrink-0 px-3 py-2 border-b border-gray-100 flex flex-wrap items-center gap-2">
                      <button type="button" onClick={() => void restoreHistoryVersion()}
                        className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500">
                        恢复此版本到编辑器
                      </button>
                      <span className="text-[10px] text-gray-400">当前为只读预览</span>
                    </div>
                    <div
                      className="flex-1 overflow-auto prose prose-sm max-w-none px-4 py-3 text-novel-ink"
                      dangerouslySetInnerHTML={{ __html: historyPreview.content || '<p>（空）</p>' }}
                    />
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
