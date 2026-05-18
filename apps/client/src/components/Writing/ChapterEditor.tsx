import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi, aiApi, storylinesApi, foreshadowsApi, chapterIndexesApi, charactersApi, projectsApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../../store'
import type { Chapter, Character, OutlineNode, StoryLine, Foreshadow, ChapterIndex, ChapterVersion, ChapterVersionDetail } from '../../types'
import toast from 'react-hot-toast'
import {
  BookOpen, Sparkles, X, Zap, Target, Users, Flag, GitBranch, RefreshCw,
  Maximize2, Minimize2, Clock, ChevronDown, ChevronRight, Anchor, History,
  Feather, PenLine, ListPlus, CheckCircle, Circle,
  CheckSquare, TrendingUp, MapPin, Swords, Bot, Save, Trash2, ClipboardList, UserPlus,
  ShieldAlert, ShieldCheck,
} from 'lucide-react'
import clsx from 'clsx'
import {
  splitStreamedDraftText,
  htmlToPlainForSplit,
  plainTextBlocksToHtml,
} from '../../utils/draftChapterIndexSplit'
import ChapterIndexEditPanel from './ChapterIndexEditPanel'
import { chapterHasNarrativeBody, shouldUseGatedDraft } from '../../utils/writingConfigGate'

// ─── props ──────────────────────────────────────────────────────────────────
interface Props {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  prevChapter?: Chapter            // 上一章（场景助手 — 上章结尾）
  onFocusModeChange?: (v: boolean) => void
}

type NewCharacterSuggestion = {
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
}

type PreWriteWarnResult = {
  ok: boolean
  risk_count: number
  risks: Array<{ type: string; severity: string; description: string; suggested_fix: string }>
  reminders: string[]
  /** 主角状态锁定：境界/位置/可用技能/持有道具/禁止项 */
  protagonist_fact_sheet?: {
    realm: string
    location: string
    key_skills: string[]
    key_items: string[]
    forbidden: string[]
  }
  /** 本章写作简报：开篇策略/冲突节拍/章末钩子/字数节奏 */
  writing_brief?: {
    opening_strategy: string
    conflict_structure: string
    closing_hook: string
    word_rhythm: string
  }
  /** 本章必发事件列表 */
  must_events?: string[]
  /** 幻觉预防清单 */
  hallucination_traps?: string[]
  error?: string
  record_id?: string
}

type PreWriteWarnHistoryRow = {
  id: string
  created_at: string | null
  model_profile: string
  chapter_plan_summary: string
  result: PreWriteWarnResult
}

/** 接口/DB 历史中的 result 可能缺字段，避免渲染时 .risks.length 抛错 */
function normalizePreWriteWarnResult(raw: unknown): PreWriteWarnResult {
  const r = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const risksRaw = r.risks
  const risks: PreWriteWarnResult['risks'] = Array.isArray(risksRaw)
    ? (risksRaw as unknown[]).filter(
        (x): x is PreWriteWarnResult['risks'][number] =>
          !!x &&
          typeof x === 'object' &&
          typeof (x as { description?: unknown }).description === 'string',
      )
    : []
  const remindersRaw = r.reminders
  const reminders: string[] = Array.isArray(remindersRaw)
    ? remindersRaw.map((x) => String(x)).filter(Boolean)
    : []
  const risk_count = typeof r.risk_count === 'number' ? r.risk_count : risks.length
  const ok =
    typeof r.ok === 'boolean'
      ? r.ok
      : !risks.some((x) => x.severity === 'high' || x.severity === 'critical')

  // 主角状态锁定
  const pfsRaw = r.protagonist_fact_sheet
  const protagonist_fact_sheet: PreWriteWarnResult['protagonist_fact_sheet'] =
    pfsRaw && typeof pfsRaw === 'object'
      ? {
          realm: String((pfsRaw as any).realm || ''),
          location: String((pfsRaw as any).location || ''),
          key_skills: Array.isArray((pfsRaw as any).key_skills) ? (pfsRaw as any).key_skills.map(String) : [],
          key_items: Array.isArray((pfsRaw as any).key_items) ? (pfsRaw as any).key_items.map(String) : [],
          forbidden: Array.isArray((pfsRaw as any).forbidden) ? (pfsRaw as any).forbidden.map(String) : [],
        }
      : undefined

  // 写作简报
  const wbRaw = r.writing_brief
  const writing_brief: PreWriteWarnResult['writing_brief'] =
    wbRaw && typeof wbRaw === 'object'
      ? {
          opening_strategy: String((wbRaw as any).opening_strategy || ''),
          conflict_structure: String((wbRaw as any).conflict_structure || ''),
          closing_hook: String((wbRaw as any).closing_hook || ''),
          word_rhythm: String((wbRaw as any).word_rhythm || ''),
        }
      : undefined

  const must_events = Array.isArray(r.must_events) ? r.must_events.map(String).filter(Boolean) : []
  const hallucination_traps = Array.isArray(r.hallucination_traps) ? r.hallucination_traps.map(String).filter(Boolean) : []

  return {
    ok,
    risk_count,
    risks,
    reminders,
    protagonist_fact_sheet,
    writing_brief,
    must_events,
    hallucination_traps,
    error: typeof r.error === 'string' ? r.error : undefined,
    record_id: typeof r.record_id === 'string' ? r.record_id : undefined,
  }
}

function parsePreWriteWarningHistoryPayload(data: unknown): PreWriteWarnHistoryRow[] {
  if (!Array.isArray(data)) return []
  return data
    .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
    .map((row) => ({
      id: String(row.id ?? ''),
      chapter_number: typeof row.chapter_number === 'number' ? row.chapter_number : 0,
      chapter_plan_summary: typeof row.chapter_plan_summary === 'string' ? row.chapter_plan_summary : '',
      model_profile: typeof row.model_profile === 'string' ? row.model_profile : 'local',
      created_at: row.created_at == null ? null : String(row.created_at),
      result: normalizePreWriteWarnResult(row.result),
    }))
    .filter((row) => row.id.length > 0)
}

type AutoDebriefResponse = {
  character_updates: Array<{
    character_id: string
    character_name?: string
    current_realm?: string
    current_location?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>
  storyline_updates: Array<{
    storyline_id: string
    storyline_name?: string
    status?: string
    beat?: string
  }>
  new_characters?: NewCharacterSuggestion[]
  asset_updates?: Record<string, unknown>
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
  summary?: string
  error?: string
  cached?: boolean
  cache_only_miss?: boolean
  new_reader_promises?: Array<{
    promise_text: string
    promise_type?: string
    expected_within_chapters?: number
    priority?: number
    audience_aware?: number
  }>
  fulfilled_promise_texts?: string[]
}

// ─── helpers ─────────────────────────────────────────────────────────────────
function isUuidLike(s?: string): boolean {
  if (!s) return false
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
}

/** 剥离 HTML 取末尾 N 字作为「上章结尾」预览 */
function htmlTail(html: string, maxChars = 200): string {
  const div = document.createElement('div')
  div.innerHTML = html
  const raw = (div.innerText || div.textContent || '').trim()
  const text = stripTailMetaLines(raw).replace(/\s+/g, ' ').trim()
  return text.length <= maxChars ? text : '…' + text.slice(-maxChars)
}

/** 过滤章末常见的结构化元信息，避免当成正文尾段展示/带入 */
function stripTailMetaLines(text: string): string {
  if (!text) return ''
  const skipLine = (line: string): boolean => {
    const t = line.trim()
    if (!t) return false
    if (/^\*{0,2}\s*章末钩子强度/.test(t)) return true
    if (/^\*{0,2}\s*伏笔埋设/.test(t)) return true
    if (/^[-•]\s*F[-_ ]?\d{1,4}\s*[:：\-]/i.test(t)) return true
    if (/\bch[_-]?\d+\s*(?:回收|铺垫)\b/i.test(t)) return true
    return false
  }
  return text
    .split('\n')
    .filter((line) => !skipLine(line))
    .join('\n')
}

function hasHtmlTextContent(html?: string): boolean {
  if (!html) return false
  const div = document.createElement('div')
  div.innerHTML = html
  const text = (div.innerText || div.textContent || '').replace(/\s+/g, ' ').trim()
  return text.length > 0
}

/**
 * 是否全书第 1 章（按大纲/章标题）。用于 sort_order 前有未写正文的序章、占位章时，
 * 不误拦「第一章」的正文生成。
 */
function isBookFirstChapterTitle(ch: Chapter, outlineNode?: OutlineNode): boolean {
  const raw = (outlineNode?.title || ch.title || '').trim()
  if (!raw) return false
  if (/^第\s*0*1\s*章/.test(raw)) return true
  if (/^第一章/.test(raw)) return true
  return false
}

// ─── 章节状态选项 ─────────────────────────────────────────────────────────────
const STATUS_OPTIONS: { value: Chapter['status']; label: string; dotCls: string; textCls: string }[] = [
  { value: 'draft',    label: '初稿',  dotCls: 'bg-gray-300',   textCls: 'text-gray-500' },
  { value: 'writing',  label: '修改中', dotCls: 'bg-blue-400',   textCls: 'text-blue-600' },
  { value: 'done',     label: '完稿',  dotCls: 'bg-green-400',  textCls: 'text-green-600' },
  { value: 'reviewed', label: '已审',  dotCls: 'bg-amber-400',  textCls: 'text-amber-600' },
]

// ─── 人物角色标签 ─────────────────────────────────────────────────────────────
const ROLE_BADGE: Record<Character['role'], { label: string; cls: string }> = {
  protagonist: { label: '主角', cls: 'bg-amber-100 text-amber-700' },
  supporting:  { label: '配角', cls: 'bg-blue-50 text-blue-600' },
  antagonist:  { label: '反派', cls: 'bg-red-50 text-red-600' },
  neutral:     { label: '中立', cls: 'bg-gray-100 text-gray-600' },
}

const INLINE_ACTIONS = [
  {
    key: 'rewrite',
    label: '改写',
    icon: <RefreshCw size={11} />,
    buildPrompt: (t: string) =>
      `请将以下选中段落改写，保持语义不变但改变表达方式，只返回改写后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'expand',
    label: '扩写',
    icon: <Feather size={11} />,
    buildPrompt: (t: string) =>
      `请将以下段落扩写，增加细节和描写，只返回扩写后的文字，不要任何解释：\n\n「${t}」`,
  },
] as const

const TOP_TOOL_BUTTON_BASE =
  'inline-flex h-8 items-center justify-center gap-1.5 rounded-novel border px-3 text-sm font-medium leading-none transition-novel focus:outline-none focus-visible:ring-2 focus-visible:ring-novel-accent focus-visible:ring-offset-2'
const TOP_TOOL_BUTTON_IDLE =
  'border-novel-border bg-novel-card text-novel-ink-muted hover:bg-novel-panel hover:text-novel-ink'
const TOP_TOOL_BUTTON_ACTIVE =
  'border-novel-accent/35 bg-novel-panel text-novel-accent'
const TOP_TOOL_ICON_BUTTON =
  'inline-flex h-8 w-8 items-center justify-center rounded-novel border border-red-100 bg-novel-card text-red-400 transition-novel hover:bg-red-50 hover:text-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
/** 写作页主操作：保存（与次要工具按钮区分） */
const TOP_TOOL_PRIMARY_BUTTON =
  'inline-flex h-9 min-w-[5.75rem] items-center justify-center gap-2 rounded-xl border-2 border-emerald-700/25 bg-emerald-600 px-4 text-sm font-semibold leading-none text-white shadow-md shadow-emerald-900/20 transition-novel hover:bg-emerald-500 hover:shadow-lg hover:border-emerald-600/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 active:scale-[0.98]'
const TOP_TOOL_DEBRIEF_BUTTON_IDLE =
  'border-amber-200 bg-amber-50/90 text-amber-900 hover:bg-amber-100 hover:border-amber-300'

// ─────────────────────────────────────────────────────────────────────────────
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

  /** 写前预警：打开 Tab 时拉取本章历史（响应体非数组时安全降级） */
  useEffect(() => {
    if (contextTab !== 'warn' || !chapter.id || !projectId) return
    let cancelled = false
    void aiApi.preWriteWarningHistory(projectId, chapter.id).then((r) => {
      if (!cancelled) setWarnHistory(parsePreWriteWarningHistoryPayload(r.data))
    }).catch(() => {
      if (!cancelled) setWarnHistory([])
    })
    return () => { cancelled = true }
  }, [contextTab, chapter.id, projectId])

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
      //   1. pre_write_warning_enabled=true：需要写前预警，必须走门控路由才能触发
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
        if (!useGated) return '已加入 AI 队列：开始重写本章'
        const hasWarn = writingConfig?.pre_write_warning_enabled === true
        const hasGate = writingConfig?.auto_quality_gate === true
        if (hasWarn && hasGate) return '已加入 AI 队列：写前预警 + 质量门控写作'
        if (hasWarn) return '已加入 AI 队列：写前预警写作（质检仅参考，不循环重写）'
        return '已加入 AI 队列：质量门控写作（自动质检+重写）'
      })()
      toast.success(toastMsg)
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

  /** 调用 AI 自动分析章节，预填复盘面板 */
  const runAutoDebrief = async (forceRefresh = false) => {
    setAutoDebriefing(true)
    try {
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

      applyAutoDebriefData(data, data.cached ? 'cache' : 'llm')
      setDebriefFromQueueSnapshot(false)
    } catch {
      toast.error('AI 自动复盘失败，请手动填写')
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
      })
      const pc = Number((res.data as { promises_created?: number })?.promises_created ?? 0)
      const pf = Number((res.data as { promises_fulfilled?: number })?.promises_fulfilled ?? 0)
      const promiseToast = (pc > 0 || pf > 0) ? `（承诺 +${pc} / 兑现 ${pf}）` : ''
      toast.success(`${res.data.message}${promiseToast}`)
      setDebriefHistoryTick((t) => t + 1)
      const refreshRequests: Promise<any>[] = [
        storylinesApi.list(projectId),
        aiApi.listMemory(projectId),
      ]
      if (aiNewCharacters.length > 0) refreshRequests.push(charactersApi.list(projectId))
      const [refreshedStorylines, refreshedMemories, refreshedCharsRes] = await Promise.all(refreshRequests)
      setStoryLines(refreshedStorylines.data)
      setMemories(refreshedMemories.data)
      if (refreshedCharsRes) {
        refreshedCharsRes.data.forEach((c: any) => useAppStore.getState().upsertCharacter(c))
      }
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

          {/* 场景助手 */}
          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'scene')); setContextTab('scene') }}
              title="场景助手（上章结尾 + 人物卡）"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'scene'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_BUTTON_IDLE)}>
              <Users size={14} />场景
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

              {/* ── 场景助手 Tab ── */}
              {contextTab === 'scene' && (
                <div className="p-4 space-y-4">

                  {/* 上章结尾 */}
                  <section>
                    <div className="flex items-center gap-1.5 mb-2">
                      <BookOpen size={11} className="text-novel-ink-muted" />
                      <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">上章结尾</span>
                    </div>
                    {prevChapter ? (
                      prevTail ? (
                        <div className="text-xs text-novel-ink leading-relaxed bg-novel-card border border-novel-border rounded-novel px-3 py-2.5 italic">
                          <p className="text-[10px] text-novel-ink-faint mb-1 not-italic truncate">《{prevChapter.title}》</p>
                          {prevTail}
                        </div>
                      ) : (
                        <p className="text-xs text-novel-ink-faint italic px-1">（上章暂无内容）</p>
                      )
                    ) : (
                      <p className="text-xs text-novel-ink-faint italic px-1">这是第一章，没有上一章</p>
                    )}
                  </section>

                  <div className="border-t border-novel-border" />

                  {/* 人物档案 */}
                  <section>
                    <div className="flex items-center gap-1.5 mb-2">
                      <Users size={11} className="text-novel-ink-muted" />
                      <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
                        人物档案
                      </span>
                      <span className="text-[10px] text-novel-ink-faint">（{characters.length} 位）</span>
                    </div>
                    {characters.length === 0 ? (
                      <p className="text-xs text-novel-ink-faint italic px-1">暂无人物，请在「人物」页创建</p>
                    ) : (
                      <div className="space-y-2">
                        {characters.map(c => <CharacterMiniCard key={c.id} character={c} />)}
                      </div>
                    )}
                  </section>
                </div>
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
                      点击工具栏「预警」按钮<br />动笔前检查连续性、伏笔和人物OOC风险
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

// ─── 子组件：PlanCard ────────────────────────────────────────────────────────
type AccentColor = 'amber' | 'blue' | 'purple' | 'red' | 'green' | 'indigo'
const accentCls: Record<AccentColor, { border: string; label: string; bg: string }> = {
  amber:  { border: 'border-amber-100',  label: 'text-amber-700',  bg: 'bg-amber-50/70' },
  blue:   { border: 'border-blue-100',   label: 'text-blue-700',   bg: 'bg-blue-50/70' },
  purple: { border: 'border-purple-100', label: 'text-purple-700', bg: 'bg-purple-50/70' },
  red:    { border: 'border-red-100',    label: 'text-red-700',    bg: 'bg-red-50/70' },
  green:  { border: 'border-green-100',  label: 'text-green-700',  bg: 'bg-green-50/70' },
  indigo: { border: 'border-indigo-100', label: 'text-indigo-700', bg: 'bg-indigo-50/70' },
}

function PlanCard({ icon, label, sublabel, content, accent }: {
  icon: React.ReactNode; label: string; sublabel?: string; content: string; accent: AccentColor
}) {
  const c = accentCls[accent]
  return (
    <div className={clsx('rounded-novel border p-3', c.border, c.bg)}>
      <div className="flex items-center gap-1.5 mb-1.5">
        {icon}
        <span className={clsx('text-xs font-semibold', c.label)}>{label}</span>
        {sublabel && <span className="text-[10px] text-novel-ink-faint">{sublabel}</span>}
      </div>
      <p className="text-xs text-novel-ink leading-relaxed">{content}</p>
    </div>
  )
}

// ─── 子组件：CharacterMiniCard ───────────────────────────────────────────────
function CharacterMiniCard({ character }: { character: Character }) {
  const [expanded, setExpanded] = useState(false)
  const badge = ROLE_BADGE[character.role]
  return (
    <div className="rounded-novel border border-novel-border bg-novel-card overflow-hidden">
      <button type="button" onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-novel-panel transition-novel text-left">
        {/* 头像 or 首字母 */}
        {character.avatar_url ? (
          <img src={character.avatar_url} alt="" className="w-6 h-6 rounded-full object-cover shrink-0" />
        ) : (
          <div className="w-6 h-6 rounded-full bg-novel-shell flex items-center justify-center shrink-0">
            <span className="text-[10px] text-novel-ink-muted font-semibold">{character.name[0]}</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-xs font-medium text-novel-ink truncate">{character.name}</span>
            <span className={clsx('text-[10px] px-1 py-0.5 rounded font-medium shrink-0', badge.cls)}>
              {badge.label}
            </span>
          </div>
          {character.motivation && !expanded && (
            <p className="text-[10px] text-novel-ink-muted truncate">{character.motivation}</p>
          )}
        </div>
        <ChevronDown size={11} className={clsx(
          'shrink-0 text-novel-ink-faint transition-transform duration-150',
          expanded && 'rotate-180',
        )} />
      </button>

      {expanded && (
        <div className="px-3 pb-2.5 pt-2 border-t border-novel-border space-y-1.5">
          {character.current_realm    && <InfoRow label="境界" value={character.current_realm} highlight />}
          {character.current_location && <InfoRow label="位置" value={character.current_location} highlight />}
          {character.current_status && character.current_status !== 'alive' && (
            <InfoRow label="状态" value={character.current_status} highlight />
          )}
          {character.motivation  && <InfoRow label="动机" value={character.motivation} />}
          {character.personality && <InfoRow label="性格" value={character.personality} />}
          {character.arc         && <InfoRow label="弧线" value={character.arc} />}
          {character.faction     && <InfoRow label="阵营" value={character.faction} />}
          {character.known_skills && (character.known_skills as any[]).length > 0 && (
            <InfoRow label="技能"
              value={(character.known_skills as any[])
                .slice(0, 4)
                .map(s => typeof s === 'string' ? s : s.skill_name || '')
                .filter(Boolean)
                .join('、')} />
          )}
        </div>
      )}
    </div>
  )
}

function InfoRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-[10px] text-novel-ink-faint shrink-0 w-8">{label}</span>
      <span className={clsx(
        'text-[10px] leading-relaxed',
        highlight ? 'text-novel-accent font-medium' : 'text-novel-ink',
      )}>{value}</span>
    </div>
  )
}

// ─── 章节复盘面板 ───────────────────────────────────────────────────────────
interface DebriefPanelProps {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  characters: Character[]
  storyLines: StoryLine[]
  charUpdates: Record<string, { current_realm?: string; current_location?: string; current_status?: string; add_skill_name?: string; add_skill_mastery?: string }>
  setCharUpdates: React.Dispatch<React.SetStateAction<DebriefPanelProps['charUpdates']>>
  storylineBeats: Record<string, { status?: string; beat?: string }>
  setStorylineBeats: React.Dispatch<React.SetStateAction<DebriefPanelProps['storylineBeats']>>
  debriefNotes: string
  setDebriefNotes: (v: string) => void
  submitting: boolean
  autoDebriefing?: boolean
  /** 打开 Tab 时从服务端缓存恢复建议（非 LLM） */
  cacheHydrating?: boolean
  aiSuggestedCharIds?: Set<string>
  aiSuggestedSlIds?: Set<string>
  aiSuggestedAssetUpdates?: Record<string, unknown> | null
  aiNewCharacters?: NewCharacterSuggestion[]
  aiNewReaderPromises?: Array<{
    promise_text: string
    promise_type?: string
    expected_within_chapters?: number
    priority?: number
    audience_aware?: number
  }>
  aiFulfilledPromiseTexts?: string[]
  onRemoveNewPromise?: (index: number) => void
  onRemoveFulfilledPromise?: (index: number) => void
  aiSummary?: string
  onAutoDebrief?: (forceRefresh?: boolean) => void
  onSubmit: (selectedAssetUpdates?: Record<string, unknown>) => void
  /** 展示内容来自生成队列自动复盘快照（已落库），与手动 AI 分析区分 */
  fromQueueSnapshot?: boolean
  /** 变更时重新拉取本章复盘落库审计列表 */
  debriefHistoryTick?: number
}

const STATUS_LABEL: Record<string, string> = {
  alive: '存活', dead: '死亡', missing: '失踪', sealed: '封印', transformed: '变异',
}
const STORYLINE_STATUS_LABEL: Record<string, string> = {
  planned: '规划中', active: '进行中', climax: '高潮', resolved: '已结局', dropped: '已废弃',
}
const DEBRIEF_APPLY_SOURCE_LABEL: Record<string, string> = {
  queue_auto: '生成队列 · 自动落库',
  manual_tab: '复盘 Tab · 手动提交',
}
const ASSET_UPDATE_LABELS: Record<string, string> = {
  new_items: '新增道具/法宝',
  item_updates: '更新道具/法宝',
  new_skills: '新增功法/技能',
  skill_updates: '更新功法/技能',
  new_factions: '新增势力',
  faction_updates: '更新势力',
}

function DebriefPanel({
  projectId,
  chapter, outlineNode, characters, storyLines,
  charUpdates, setCharUpdates,
  storylineBeats, setStorylineBeats,
  debriefNotes, setDebriefNotes,
  submitting, autoDebriefing,
  cacheHydrating = false,
  aiSuggestedCharIds = new Set(),
  aiSuggestedSlIds = new Set(),
  aiSuggestedAssetUpdates = null,
  aiNewCharacters = [],
  aiNewReaderPromises = [],
  aiFulfilledPromiseTexts = [],
  onRemoveNewPromise,
  onRemoveFulfilledPromise,
  aiSummary,
  onAutoDebrief,
  onSubmit,
  fromQueueSnapshot = false,
  debriefHistoryTick = 0,
}: DebriefPanelProps) {
  const [applyRecords, setApplyRecords] = useState<Array<{
    id: string
    apply_source: string
    content_hash: string | null
    payload: Record<string, unknown>
    result_message: string | null
    created_at: string | null
  }>>([])
  const [applyRecordsLoading, setApplyRecordsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setApplyRecordsLoading(true)
    chaptersApi.listDebriefApplyRecords(projectId, chapter.id, 25)
      .then((r) => {
        if (!cancelled) setApplyRecords(r.data)
      })
      .catch(() => {
        if (!cancelled) setApplyRecords([])
      })
      .finally(() => {
        if (!cancelled) setApplyRecordsLoading(false)
      })
    return () => { cancelled = true }
  }, [projectId, chapter.id, debriefHistoryTick])

  // 本章出场人物（优先从大纲节点 involved_character_ids 取，否则展示全部）
  const involvedIds = new Set(outlineNode?.involved_character_ids?.map(String) || [])
  const displayChars = involvedIds.size > 0
    ? characters.filter(c => involvedIds.has(String(c.id)))
    : characters.slice(0, 8)

  // 活跃故事线（只显示 active/climax/planned）
  const activeStorylines = storyLines.filter(s =>
    ['active', 'climax', 'planned'].includes(s.status)
  )

  const updateChar = (id: string, field: string, value: string) => {
    setCharUpdates(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  const updateStoryline = (id: string, field: string, value: string) => {
    setStorylineBeats(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  const assetSections = useMemo(() => {
    const source = aiSuggestedAssetUpdates || {}
    return Object.entries(ASSET_UPDATE_LABELS)
      .map(([key, label]) => {
        const list = source[key]
        return {
          key,
          label,
          items: Array.isArray(list) ? list.filter(item => typeof item === 'object' && item !== null) : [],
        }
      })
      .filter(section => section.items.length > 0)
  }, [aiSuggestedAssetUpdates])
  const [assetSelections, setAssetSelections] = useState<Record<string, boolean[]>>({})

  useEffect(() => {
    const nextSelections: Record<string, boolean[]> = {}
    for (const section of assetSections) {
      nextSelections[section.key] = section.items.map(() => true)
    }
    setAssetSelections(nextSelections)
  }, [assetSections])

  const totalAssetCount = assetSections.reduce((sum, section) => sum + section.items.length, 0)
  const selectedAssetCount = assetSections.reduce((sum, section) => {
    const flags = assetSelections[section.key] || []
    return sum + flags.filter(Boolean).length
  }, 0)
  const hasAiSuggestions = aiSuggestedCharIds.size > 0 || aiSuggestedSlIds.size > 0 || totalAssetCount > 0
    || aiNewReaderPromises.length > 0 || aiFulfilledPromiseTexts.length > 0

  const PROMISE_TYPE_LABEL: Record<string, string> = {
    chapter_ending: '章末悬念',
    volume_ending: '卷末钩子',
    name_implication: '名字/开篇暗示',
    chapter_comment_consensus: '章评共识',
    protagonist_claim: '主角宣言',
  }

  const buildSelectedAssetUpdates = (): Record<string, unknown> | undefined => {
    const picked: Record<string, unknown> = {}
    for (const section of assetSections) {
      const flags = assetSelections[section.key] || []
      const selectedItems = section.items.filter((_, idx) => flags[idx])
      if (selectedItems.length > 0) picked[section.key] = selectedItems
    }
    return Object.keys(picked).length > 0 ? picked : undefined
  }

  return (
    <div className="p-4 space-y-4">

      {fromQueueSnapshot && (
        <div className="rounded-novel border border-amber-200 bg-amber-50/90 px-3 py-2 text-[10px] text-amber-900 leading-relaxed">
          <span className="font-semibold">生成队列已自动复盘并写入数据库。</span>
          以下为当时的 AI 提取快照（黄标与预填一致），便于对照；若再改正文可点「重新分析」刷新。
        </div>
      )}

      <section className="rounded-novel border border-novel-border bg-novel-card/90 px-3 py-2.5 space-y-2">
        <div className="flex items-center gap-1.5">
          <History size={11} className="text-novel-ink-muted" />
          <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">复盘落库记录</span>
          {applyRecordsLoading && <span className="text-[10px] text-novel-ink-faint">加载中…</span>}
        </div>
        <p className="text-[9px] text-novel-ink-faint leading-relaxed">
          每次落库（队列自动或本页提交）都会在服务端留档：时间、来源、摘要与完整填入 JSON，便于回溯本章做过哪些复盘操作。
        </p>
        {!applyRecordsLoading && applyRecords.length === 0 && (
          <p className="text-[10px] text-novel-ink-faint italic">本章尚无落库记录。</p>
        )}
        <div className="space-y-1.5 max-h-56 overflow-y-auto">
          {applyRecords.map((r) => {
            const t = r.created_at ? r.created_at.replace('T', ' ').slice(0, 19) : '—'
            const src = DEBRIEF_APPLY_SOURCE_LABEL[r.apply_source] ?? r.apply_source
            return (
              <details
                key={r.id}
                className="rounded border border-novel-border bg-white/70 px-2 py-1.5 text-[10px] text-novel-ink"
              >
                <summary className="cursor-pointer select-none list-none flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="font-medium text-novel-ink">{t}</span>
                  <span className="text-[9px] text-novel-accent">{src}</span>
                  {r.content_hash && (
                    <span className="text-[9px] text-novel-ink-faint font-mono truncate max-w-[10rem]" title={r.content_hash}>
                      正文哈希 {r.content_hash.slice(0, 8)}…
                    </span>
                  )}
                </summary>
                {r.result_message && (
                  <p className="mt-1.5 text-[10px] text-novel-ink-muted leading-relaxed border-t border-novel-border/60 pt-1.5">
                    {r.result_message}
                  </p>
                )}
                <pre className="mt-1.5 max-h-36 overflow-auto text-[9px] leading-snug text-novel-ink-faint whitespace-pre-wrap break-words">
                  {JSON.stringify(r.payload, null, 2)}
                </pre>
              </details>
            )
          })}
        </div>
      </section>

      {/* AI 自动分析区 */}
      {hasAiSuggestions && aiSummary ? (
        <div className="rounded-novel border border-amber-200 bg-amber-50/80 px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <Bot size={12} className="text-amber-500" />
            <span className="text-[11px] font-semibold text-amber-700">AI 已自动分析本章</span>
          </div>
          <p className="text-[11px] text-amber-800 leading-relaxed">{aiSummary}</p>
          <p className="text-[10px] text-amber-500 mt-1">
            已预填 {aiSuggestedCharIds.size} 个人物、{aiSuggestedSlIds.size} 条故事线、{totalAssetCount} 条资产变化{aiNewCharacters.length > 0 ? `、${aiNewCharacters.length} 个新配角` : ''}{aiNewReaderPromises.length > 0 ? `、${aiNewReaderPromises.length} 条新承诺` : ''}{aiFulfilledPromiseTexts.length > 0 ? `、${aiFulfilledPromiseTexts.length} 条待兑现` : ''}，请检查后提交
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-novel-ink-faint leading-relaxed">
            点击下方「AI 分析」提取变化（若此前分析过且正文未改，打开本页会自动载入缓存）；也可纯手动填写后提交
          </p>
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || !chapter.content?.trim()}
              className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-novel border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={11} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中…' : 'AI 自动复盘'}
            </button>
          )}
        </div>
      )}

      {/* 加载中：区分「读缓存」与「AI 分析」 */}
      {cacheHydrating && (
        <div className="flex items-center justify-center gap-2 py-2 text-slate-500">
          <span className="text-xs">正在载入已保存的复盘建议…</span>
        </div>
      )}
      {autoDebriefing && (
        <div className="flex items-center justify-center gap-2 py-3 text-amber-600">
          <Bot size={14} className="animate-pulse" />
          <span className="text-xs">AI 正在读取章节并提取变化…</span>
        </div>
      )}

      {/* 人物状态更新 */}
      {displayChars.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <Users size={11} className="text-novel-ink-muted" />
            <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
              人物状态更新
            </span>
          </div>
          <div className="space-y-3">
            {displayChars.map(c => {
              const upd = charUpdates[c.id] || {}
              const hasChange = Object.values(upd).some(Boolean)
              const isAiSuggested = aiSuggestedCharIds.has(c.id)
              return (
                <div key={c.id} className={clsx(
                  'rounded-novel border px-3 py-2.5 space-y-2',
                  isAiSuggested ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                    : hasChange ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
                )}>
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full bg-novel-shell flex items-center justify-center shrink-0">
                      <span className="text-[9px] text-novel-ink-muted font-semibold">{c.name[0]}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-medium text-novel-ink">{c.name}</span>
                        {isAiSuggested && (
                          <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium">
                            <Bot size={8} />AI 建议
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {c.current_realm && (
                          <span className="text-[10px] text-novel-accent">{c.current_realm}</span>
                        )}
                        {c.current_location && (
                          <span className="text-[10px] text-novel-ink-faint">
                            <MapPin size={8} className="inline mr-0.5" />{c.current_location}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">新境界</label>
                      <input
                        type="text"
                        value={upd.current_realm || ''}
                        onChange={e => updateChar(c.id, 'current_realm', e.target.value)}
                        placeholder={c.current_realm || '不变'}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">新位置</label>
                      <input
                        type="text"
                        value={upd.current_location || ''}
                        onChange={e => updateChar(c.id, 'current_location', e.target.value)}
                        placeholder={c.current_location || '不变'}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">状态</label>
                      <select
                        value={upd.current_status || ''}
                        onChange={e => updateChar(c.id, 'current_status', e.target.value)}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      >
                        <option value="">不变（{STATUS_LABEL[c.current_status || 'alive'] || c.current_status}）</option>
                        {Object.entries(STATUS_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">习得技能</label>
                      <input
                        type="text"
                        value={upd.add_skill_name || ''}
                        onChange={e => updateChar(c.id, 'add_skill_name', e.target.value)}
                        placeholder="技能名称（可空）"
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 故事线推进 */}
      {activeStorylines.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <Swords size={11} className="text-novel-ink-muted" />
            <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
              故事线推进
            </span>
          </div>
          <div className="space-y-2">
            {activeStorylines.map(sl => {
              const upd = storylineBeats[sl.id] || {}
              const hasChange = Object.values(upd).some(Boolean)
              const isAiSuggested = aiSuggestedSlIds.has(sl.id)
              return (
                <div key={sl.id} className={clsx(
                  'rounded-novel border px-3 py-2.5 space-y-1.5',
                  isAiSuggested ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                    : hasChange ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
                )}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-medium text-novel-ink truncate">{sl.name}</span>
                      {isAiSuggested && (
                        <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium shrink-0">
                          <Bot size={8} />AI
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-novel-ink-faint shrink-0">
                      {STORYLINE_STATUS_LABEL[sl.status] || sl.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">更新状态</label>
                      <select
                        value={upd.status || ''}
                        onChange={e => updateStoryline(sl.id, 'status', e.target.value)}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      >
                        <option value="">不变</option>
                        {Object.entries(STORYLINE_STATUS_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">本章节拍</label>
                      <input
                        type="text"
                        value={upd.beat || ''}
                        onChange={e => updateStoryline(sl.id, 'beat', e.target.value)}
                        placeholder="发生了什么（可空）"
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 资产变化（AI 建议，可勾选） */}
      {assetSections.length > 0 && (
        <section>
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-1.5">
              <Flag size={11} className="text-novel-ink-muted" />
              <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
                资产变化（可勾选提交）
              </span>
              <span className="text-[10px] text-novel-ink-faint">
                {selectedAssetCount}/{totalAssetCount}
              </span>
            </div>
            <button
              type="button"
              onClick={() => {
                const allSelected = selectedAssetCount === totalAssetCount && totalAssetCount > 0
                setAssetSelections(prev => {
                  const next = { ...prev }
                  for (const section of assetSections) {
                    next[section.key] = section.items.map(() => !allSelected)
                  }
                  return next
                })
              }}
              className="text-[10px] px-2 py-1 rounded border border-novel-border bg-white text-novel-ink-muted hover:bg-novel-panel transition-novel"
            >
              {selectedAssetCount === totalAssetCount && totalAssetCount > 0 ? '全部取消' : '全部勾选'}
            </button>
          </div>

          <div className="space-y-2.5">
            {assetSections.map(section => (
              <div key={section.key} className="rounded-novel border border-novel-border bg-novel-card px-3 py-2.5">
                <div className="text-[10px] font-semibold text-novel-ink-muted mb-1.5">{section.label}</div>
                <div className="space-y-1">
                  {section.items.map((item, idx) => {
                    const row = item as Record<string, unknown>
                    const name = String(
                      row.name
                      || row.item_name
                      || row.skill_name
                      || row.faction_name
                      || `${section.label}#${idx + 1}`,
                    )
                    const note = String(
                      row.reason_to_store
                      || row.event_note
                      || row.story_significance
                      || row.effects
                      || row.goals
                      || '',
                    )
                    const checked = assetSelections[section.key]?.[idx] ?? false
                    return (
                      <label key={`${section.key}-${idx}`} className="flex items-start gap-2 text-[11px] text-novel-ink">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={e => {
                            const { checked: nextChecked } = e.target
                            setAssetSelections(prev => {
                              const sectionFlags = [...(prev[section.key] || section.items.map(() => true))]
                              sectionFlags[idx] = nextChecked
                              return { ...prev, [section.key]: sectionFlags }
                            })
                          }}
                          className="mt-0.5"
                        />
                        <span className="leading-relaxed">
                          <span className="font-medium">{name}</span>
                          {note && <span className="text-novel-ink-faint"> · {note}</span>}
                        </span>
                      </label>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {(aiNewReaderPromises.length > 0 || aiFulfilledPromiseTexts.length > 0) && (
        <section className="rounded-novel border border-violet-200 bg-violet-50/50 px-3 py-2.5 space-y-2">
          <span className="text-[10px] font-semibold text-violet-800 uppercase tracking-wider block">
            读者承诺台账
          </span>
          {aiNewReaderPromises.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[9px] text-violet-700/80">本章新承诺（提交后写入台账）</p>
              {aiNewReaderPromises.map((p, idx) => (
                <div
                  key={`new-promise-${idx}`}
                  className="flex items-start gap-2 text-[11px] text-violet-950 bg-white/80 rounded border border-violet-100 px-2 py-1.5"
                >
                  <span className="flex-1 leading-relaxed">
                    <span className="text-[9px] text-violet-600 mr-1">
                      {PROMISE_TYPE_LABEL[p.promise_type || ''] || p.promise_type || '承诺'}
                    </span>
                    {p.promise_text}
                    {typeof p.expected_within_chapters === 'number' && p.expected_within_chapters > 0 && (
                      <span className="text-[9px] text-violet-500 ml-1">
                        · {p.expected_within_chapters} 章内
                      </span>
                    )}
                  </span>
                  {onRemoveNewPromise && !fromQueueSnapshot && (
                    <button
                      type="button"
                      onClick={() => onRemoveNewPromise(idx)}
                      className="text-[9px] text-violet-500 hover:text-violet-800 shrink-0"
                    >
                      移除
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {aiFulfilledPromiseTexts.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[9px] text-violet-700/80">本章已兑现（提交后匹配 open 台账标 fulfilled）</p>
              {aiFulfilledPromiseTexts.map((text, idx) => (
                <div
                  key={`fulfilled-${idx}`}
                  className="flex items-start gap-2 text-[11px] text-emerald-900 bg-emerald-50/90 rounded border border-emerald-100 px-2 py-1.5"
                >
                  <span className="flex-1 leading-relaxed">{text}</span>
                  {onRemoveFulfilledPromise && !fromQueueSnapshot && (
                    <button
                      type="button"
                      onClick={() => onRemoveFulfilledPromise(idx)}
                      className="text-[9px] text-emerald-600 hover:text-emerald-900 shrink-0"
                    >
                      移除
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 作者备注 */}
      <section>
        <label className="text-[10px] font-semibold text-novel-ink-muted block mb-1.5">作者备注（可选）</label>
        <textarea
          value={debriefNotes}
          onChange={e => setDebriefNotes(e.target.value)}
          rows={2}
          placeholder="本章写作感受、待调整之处……"
          className="w-full text-[11px] border border-novel-border rounded-novel px-3 py-2 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-none"
        />
      </section>

      {/* AI 建议新配角入库 */}
      {aiNewCharacters.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <UserPlus size={11} className="text-emerald-600" />
            <span className="text-[11px] font-semibold text-novel-ink">本章新配角入库</span>
            <span className="ml-auto text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">AI 建议</span>
          </div>
          <div className="space-y-1.5">
            {aiNewCharacters.map((nc, i) => (
              <div key={i} className="rounded-novel border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-novel-ink">{nc.name}</span>
                  {nc.faction && <span className="text-emerald-700 bg-emerald-100 rounded px-1">{nc.faction}</span>}
                  {nc.current_realm && <span className="text-novel-ink-muted">{nc.current_realm}</span>}
                </div>
                {nc.personality && <p className="text-novel-ink-muted mt-0.5 leading-relaxed">{nc.personality}</p>}
                {nc.motivation && <p className="text-novel-ink-faint mt-0.5">动机：{nc.motivation}</p>}
                {nc.author_notes && <p className="text-amber-700 mt-0.5 italic">{nc.author_notes}</p>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-novel-ink-faint mt-1.5">提交后自动写入人物库</p>
        </section>
      )}

      {/* 空状态提示 */}
      {displayChars.length === 0 && activeStorylines.length === 0 && (
        <p className="text-xs text-novel-ink-faint italic text-center py-4">
          暂无人物或活跃故事线<br />
          <span className="text-[10px]">请先在「人物」和「世界」页创建数据，<br />并在大纲节点上标注本章出场人物</span>
        </p>
      )}

      {/* 操作按钮区：吸底 + 主按钮加粗阴影，长表单时仍易发现 */}
      <div
        className={clsx(
          'sticky bottom-0 z-10 -mx-4 mt-2 border-t border-novel-border/90 bg-novel-panel/95 backdrop-blur-sm px-4 pb-4 pt-3 shadow-[0_-8px_24px_-4px_rgba(0,0,0,0.06)]',
          hasAiSuggestions && 'ring-1 ring-inset ring-amber-200/80',
        )}
      >
        <p className="text-[10px] text-novel-ink-faint mb-2 text-center">
          {hasAiSuggestions ? '核对预填项后点击下方按钮写入数据库' : '填写或 AI 分析后，提交以同步人物 / 故事线 / 资产'}
        </p>
        <div className="flex gap-2">
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || submitting || !chapter.content?.trim()}
              className="flex items-center justify-center gap-1.5 text-xs py-2.5 px-3 border border-amber-300 text-amber-800 bg-amber-50 hover:bg-amber-100 rounded-xl font-semibold disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={13} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中' : hasAiSuggestions ? '重新分析' : 'AI 分析'}
            </button>
          )}
          <button
            type="button"
            onClick={() => onSubmit(buildSelectedAssetUpdates())}
            disabled={submitting || autoDebriefing || cacheHydrating}
            className={clsx(
              'flex-1 flex items-center justify-center gap-2 min-h-[3rem] rounded-xl text-[15px] font-semibold text-white shadow-lg transition-all disabled:opacity-55 disabled:shadow-none active:scale-[0.99]',
              hasAiSuggestions
                ? 'bg-gradient-to-b from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 ring-2 ring-amber-300/70 shadow-amber-900/25'
                : 'bg-novel-accent hover:bg-novel-accent-hover ring-2 ring-black/10 shadow-stone-900/20',
            )}
          >
            <CheckSquare size={18} strokeWidth={2.25} className={submitting ? 'animate-pulse' : ''} />
            {submitting ? '提交中…' : hasAiSuggestions ? '确认并提交' : '提交复盘'}
          </button>
        </div>
      </div>
    </div>
  )
}
