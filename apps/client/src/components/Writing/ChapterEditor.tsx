import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi, aiApi, storylinesApi, foreshadowsApi, chapterIndexesApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../../store'
import type { Chapter, Character, OutlineNode, StoryLine, Foreshadow, ChapterIndex } from '../../types'
import toast from 'react-hot-toast'
import {
  BookOpen, Sparkles, X, Zap, Target, Users, Flag, GitBranch, RefreshCw,
  Maximize2, Minimize2, Clock, ChevronDown, ChevronRight, Anchor,
  Feather, PenLine, ListPlus, CheckCircle, Circle,
  CheckSquare, TrendingUp, MapPin, Swords, Bot, Save, Trash2,
} from 'lucide-react'
import clsx from 'clsx'
import { autoCommitGeneratedChapterDebrief } from '../../utils/generatedChapterDebrief'

// ─── props ──────────────────────────────────────────────────────────────────
interface Props {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  prevChapter?: Chapter            // 上一章（场景助手 — 上章结尾）
  onFocusModeChange?: (v: boolean) => void
}

// ─── helpers ─────────────────────────────────────────────────────────────────
function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function plainTextDraftToHtml(s: string) {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

function parseSseDataLine(line: string): { text?: string; error?: string; done?: boolean } | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try { return JSON.parse(raw) } catch { return null }
}

function isUuidLike(s?: string): boolean {
  if (!s) return false
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
}

/** 剥离 HTML 取末尾 N 字作为「上章结尾」预览 */
function htmlTail(html: string, maxChars = 200): string {
  const div = document.createElement('div')
  div.innerHTML = html
  const text = (div.innerText || div.textContent || '').replace(/\s+/g, ' ').trim()
  return text.length <= maxChars ? text : '…' + text.slice(-maxChars)
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
const TOP_TOOL_PRIMARY_BUTTON =
  'inline-flex h-8 min-w-[72px] items-center justify-center gap-1.5 rounded-novel border border-novel-accent bg-novel-accent px-3 text-sm font-medium leading-none text-white transition-novel hover:bg-novel-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-novel-accent focus-visible:ring-offset-2'

// ─────────────────────────────────────────────────────────────────────────────
export default function ChapterEditor({
  projectId, chapter, outlineNode, prevChapter, onFocusModeChange,
}: Props) {
  const {
    upsertChapter, removeChapter, setActiveChapterId,
    chapters, characters, storyLines, setStoryLines, setMemories, addGenTask,
  } = useAppStore()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()
  const storylineAutoSyncingRef = useRef(false)
  const memoryAutoSyncingRef = useRef(false)
  const lastMemoryAutoExtractAtRef = useRef(0)

  // ── 面板 UI 状态 ───────────────────────────────────────────────────
  const [contextOpen, setContextOpen]   = useState(!!outlineNode)
  const [contextTab, setContextTab]     = useState<'plan' | 'scene' | 'debrief'>('plan')
  const [focusMode, setFocusMode]       = useState(false)
  const [statusOpen, setStatusOpen]     = useState(false)
  const statusRef = useRef<HTMLDivElement>(null)

  // ── 原有 AI 草稿功能 ───────────────────────────────────────────────
  const [aiDrafting, setAiDrafting]                     = useState(false)
  const [aiExtraPrompt, setAiExtraPrompt]               = useState('')
  const [continueChapterCount, setContinueChapterCount] = useState(1)
  const [selectionText, setSelectionText]               = useState('')
  const [showSelectionBar, setShowSelectionBar]         = useState(false)

  // ── 章节复盘（写完后提交状态更新）────────────────────────────────
  const [debriefSubmitting, setDebriefSubmitting] = useState(false)
  const [autoDebriefing, setAutoDebriefing]       = useState(false)
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

  // ── 底部伏笔面板 ───────────────────────────────────────────────────
  const [bottomPanelOpen, setBottomPanelOpen]   = useState(false)
  const [openForeshadows, setOpenForeshadows]   = useState<Foreshadow[]>([])
  const [currentChIndex, setCurrentChIndex]     = useState<ChapterIndex | null>(null)

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

  // ─────────────────────────────────────────────────────────────────
  // Effects
  // ─────────────────────────────────────────────────────────────────

  /** 章节切换：重置所有会话状态 */
  useEffect(() => {
    sessionStartWords.current = chapter.word_count
    sessionStartTime.current  = Date.now()
    setSessionDelta(0)
    setSessionElapsed(0)
    setAiDrafting(false)
    setSelectionText('')
    setShowSelectionBar(false)
    setAiSuggestedAssetUpdates(null)
  }, [chapter.id])

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
  // AI 草稿生成（保留原逻辑，额外支持传入 prompt）
  // ─────────────────────────────────────────────────────────────────

  const insertDraftToEditorAndSave = useCallback(async (text: string, replace: boolean) => {
    if (!editor || !text.trim()) return
    const html = plainTextDraftToHtml(text.trim())
    if (replace) editor.commands.setContent(html)
    else editor.chain().focus().insertContentAt(editor.state.doc.content.size, html).run()
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content: editor.getHTML() })
      upsertChapter(res.data)
      toast.success(replace ? '已替换全文并保存' : '已插入文末并保存')
    } catch { toast.error('保存失败，请点顶部「保存」重试') }
  }, [editor, projectId, chapter.id, upsertChapter])

  /** 核心生成逻辑，可接受临时 prompt（选中快捷动作用） */
  const triggerGenerate = async (overridePrompt?: string, opts?: { replaceExisting?: boolean }) => {
    setAiDrafting(true)
    let accumulated = ''
    const promptToSend = overridePrompt ?? (aiExtraPrompt.trim() || null)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await fetch(`/api/v1/projects/${projectId}/ai/draft-assist/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapter_id: chapter.id,
          model_profile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
          user_prompt: promptToSend,
          replace_existing: !!opts?.replaceExisting,
        }),
      })
      if (!res.ok) throw new Error((await res.text().catch(() => '')).slice(0, 240) || `HTTP ${res.status}`)
      if (!res.body) throw new Error('响应无流式内容')

      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n'); buf = lines.pop() ?? ''
        for (const line of lines) {
          const p = parseSseDataLine(line)
          if (!p) continue
          if (p.done) break
          if (p.error) throw new Error(p.error)
          if (p.text) { accumulated += p.text }
        }
      }
      for (const line of buf.split('\n')) {
        const p = parseSseDataLine(line)
        if (p?.error) throw new Error(p.error)
        if (p?.text) { accumulated += p.text }
      }
      if (!accumulated.trim()) { toast.error('未收到内容，请检查模型或稍后重试'); return }
      await insertDraftToEditorAndSave(accumulated, !!opts?.replaceExisting)
      try {
        setAutoDebriefing(true)
        const applied = await autoCommitGeneratedChapterDebrief(
          projectId,
          chapter.id,
          modelProfileFromRoute(route),
          llmProviderIdFromRoute(route),
        )
        if (
          applied.characterCount > 0
          || applied.storylineCount > 0
          || applied.memoryCount > 0
          || applied.assetCreatedCount > 0
          || applied.assetUpdatedCount > 0
        ) {
          toast.success(
            `已自动复盘 ${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，资产新增${applied.assetCreatedCount}/更新${applied.assetUpdatedCount}`,
          )
        }
      } catch (e: unknown) {
        toast.error(e instanceof Error ? `自动复盘失败：${e.message}` : '自动复盘失败')
      } finally {
        setAutoDebriefing(false)
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'AI 生成失败')
    } finally {
      setAiDrafting(false)
    }
  }

  const generateDraft = (opts?: { replaceExisting?: boolean; overridePrompt?: string }) => {
    if (opts?.replaceExisting) {
      if (!window.confirm('「重新生成本章」将按大纲重写当前正文。建议先手动保存快照。确定继续？')) return
      const route = useAppStore.getState().aiBackendRoute
      addGenTask({
        type: 'rewrite_chapter',
        projectId,
        label: `重写《${chapter.title}》`,
        params: {
          chapterId: chapter.id,
          userPrompt: opts.overridePrompt ?? aiExtraPrompt.trim(),
          modelProfile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        },
      })
      toast.success('已加入 AI 队列：开始重写本章')
      return
    }
    void triggerGenerate(opts?.overridePrompt, opts)
  }

  const runPromptAction = (action: 'rewrite' | 'expand') => {
    if (!selectionText.trim()) {
      toast.error('请先选中需要处理的正文')
      return
    }
    const actionConfig = INLINE_ACTIONS.find(item => item.key === action)
    if (!actionConfig) return
    const actionPrompt = actionConfig.buildPrompt(selectionText.slice(0, 400))
    void triggerGenerate(actionPrompt, { replaceExisting: false })
    setShowSelectionBar(false)
  }

  const enqueueContinueChapters = async () => {
    const ordered = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
    const startIndex = ordered.findIndex(c => c.id === chapter.id)
    if (startIndex < 0) {
      toast.error('未找到当前章节顺序，请刷新后重试')
      return
    }
    const remaining = Math.max(1, ordered.length - startIndex)
    const count = Math.min(Math.max(1, continueChapterCount || 1), remaining)
    const targetChapters = ordered.slice(startIndex, startIndex + count)
    if (targetChapters.length <= 1) {
      generateDraft()
      return
    }

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
      label: `从《${chapter.title}》起续写 ${targetChapters.length} 章`,
      params: {
        chapterIds: targetChapters.map(c => c.id),
        userPrompt: aiExtraPrompt.trim(),
        modelProfile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      },
    })
    toast.success(`已加入 AI 队列：连续续写 ${targetChapters.length} 章`)
  }

  /** 调用 AI 自动分析章节，预填复盘面板 */
  const runAutoDebrief = async () => {
    setAutoDebriefing(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.autoDebrief(projectId, {
        chapter_id: chapter.id,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const data = res.data as {
        character_updates: Array<{
          character_id: string; character_name?: string
          current_realm?: string; current_location?: string
          current_status?: string; add_skill_name?: string; add_skill_mastery?: string
        }>
        storyline_updates: Array<{
          storyline_id: string; storyline_name?: string
          status?: string; beat?: string
        }>
        asset_updates?: Record<string, unknown>
        summary?: string
        error?: string
      }

      if (data.error) {
        toast.error(`AI 自动复盘解析失败：${data.error}`)
        return
      }

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
      if (data.summary) setAiDebriefSummary(data.summary)

      const total = suggestedCharIds.size + suggestedSlIds.size
      const assetCount = data.asset_updates
        ? Object.values(data.asset_updates).reduce<number>(
          (sum, value) => sum + (Array.isArray(value) ? value.length : 0),
          0,
        )
        : 0
      if (total > 0 || assetCount > 0) {
        toast.success(`AI 自动提取了 ${suggestedCharIds.size} 个人物变化、${suggestedSlIds.size} 条故事线更新、${assetCount} 条资产变化，请确认后提交`)
        // 自动打开复盘面板
        setContextOpen(true)
        setContextTab('debrief')
      } else {
        toast('AI 未检测到明确的状态变化', { icon: 'ℹ️' })
      }
    } catch {
      toast.error('AI 自动复盘失败，请手动填写')
    } finally {
      setAutoDebriefing(false)
    }
  }

  const submitDebrief = async () => {
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

    const hasAssetUpdates = Boolean(
      aiSuggestedAssetUpdates
      && Object.values(aiSuggestedAssetUpdates).some(value => Array.isArray(value) && value.length > 0),
    )

    if (characterUpdates.length === 0 && storylineUpdates.length === 0 && !debriefNotes && !hasAssetUpdates) {
      toast('没有需要提交的更新', { icon: 'ℹ️' })
      return
    }

    setDebriefSubmitting(true)
    try {
      const res = await aiApi.chapterDebrief(projectId, {
        chapter_id: chapter.id,
        character_updates: characterUpdates as any,
        storyline_updates: storylineUpdates as any,
        asset_updates: hasAssetUpdates ? aiSuggestedAssetUpdates || undefined : undefined,
        notes: debriefNotes || undefined,
      })
      toast.success(res.data.message)
      const [refreshedStorylines, refreshedMemories] = await Promise.all([
        storylinesApi.list(projectId),
        aiApi.listMemory(projectId),
      ])
      setStoryLines(refreshedStorylines.data)
      setMemories(refreshedMemories.data)
      // 清空表单
      setCharUpdates({})
      setStorylineBeats({})
      setAiSuggestedAssetUpdates(null)
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

          {/* 复盘 */}
          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'debrief')); setContextTab('debrief') }}
              title="章节复盘（更新人物状态/故事线）"
              className={clsx(TOP_TOOL_BUTTON_BASE,
                contextOpen && contextTab === 'debrief'
                  ? TOP_TOOL_BUTTON_ACTIVE
                  : TOP_TOOL_BUTTON_IDLE)}>
              <CheckSquare size={14} />复盘
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

          {/* 保存 */}
          <button type="button" onClick={manualSave}
            className={TOP_TOOL_PRIMARY_BUTTON}>
            <Save size={14} />
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
            <div className={clsx(focusMode && 'w-full max-w-2xl')}>
              <EditorContent editor={editor} className="h-full" />
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
                  disabled={aiDrafting}
                  onClick={() => runPromptAction('rewrite')}
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50">
                  <RefreshCw size={11} />改写
                </button>
                <button type="button"
                  disabled={aiDrafting}
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
                      disabled={aiDrafting}
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
                        disabled={aiDrafting}
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
                        <button type="button" onClick={enqueueContinueChapters} disabled={aiDrafting}
                          className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-60">
                          {normalizedContinueCount > 1
                            ? <ListPlus size={15} />
                            : <Sparkles size={15} className={aiDrafting ? 'animate-pulse' : ''} />}
                          {normalizedContinueCount > 1 ? '加入队列' : aiDrafting ? '生成中…' : '生成'}
                        </button>

                        {wordCount > 0 && (
                          <button type="button" onClick={() => generateDraft({ replaceExisting: true })} disabled={aiDrafting}
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
            <div className="flex justify-center pb-5 shrink-0 pointer-events-none">
              <div className="flex items-center gap-4 bg-white/80 backdrop-blur border border-gray-200 rounded-full px-6 py-2 shadow-sm pointer-events-auto">
                <span className="text-xs text-gray-400">{wordCount.toLocaleString()} 字</span>
                {sessionDelta !== 0 && (
                  <span className={clsx('text-xs font-medium', sessionDelta > 0 ? 'text-green-500' : 'text-red-400')}>
                    {sessionDelta > 0 ? '+' : ''}{sessionDelta}
                  </span>
                )}
                <button type="button" onClick={manualSave}
                  className="text-xs text-gray-500 hover:text-gray-800 transition-colors">
                  保存
                </button>
                <button type="button" onClick={() => setFocusMode(false)}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1">
                  <Minimize2 size={11} />退出专注
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ══════════════════ 右侧上下文面板 ══════════════════════ */}
        {contextOpen && !focusMode && (
          <div className="w-72 shrink-0 border-l border-novel-border bg-novel-panel flex flex-col overflow-hidden">

            {/* Tab 导航头 */}
            <div className="flex items-center border-b border-novel-border bg-novel-card/80 shrink-0">
              {(
                [
                  { key: 'plan',    label: '计划',  icon: <BookOpen size={11} /> },
                  { key: 'scene',   label: '场景',  icon: <Users size={11} /> },
                  { key: 'debrief', label: '复盘',  icon: <CheckSquare size={11} /> },
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
                  aiSuggestedCharIds={aiSuggestedCharIds}
                  aiSuggestedSlIds={aiSuggestedSlIds}
                  aiSummary={aiDebriefSummary}
                  onAutoDebrief={runAutoDebrief}
                  onSubmit={submitDebrief}
                />
              )}

            </div>
          </div>
        )}
      </div>
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
  aiSuggestedCharIds?: Set<string>
  aiSuggestedSlIds?: Set<string>
  aiSummary?: string
  onAutoDebrief?: () => void
  onSubmit: () => void
}

const STATUS_LABEL: Record<string, string> = {
  alive: '存活', dead: '死亡', missing: '失踪', sealed: '封印', transformed: '变异',
}
const STORYLINE_STATUS_LABEL: Record<string, string> = {
  planned: '规划中', active: '进行中', climax: '高潮', resolved: '已结局', dropped: '已废弃',
}

function DebriefPanel({
  chapter, outlineNode, characters, storyLines,
  charUpdates, setCharUpdates,
  storylineBeats, setStorylineBeats,
  debriefNotes, setDebriefNotes,
  submitting, autoDebriefing,
  aiSuggestedCharIds = new Set(),
  aiSuggestedSlIds = new Set(),
  aiSummary,
  onAutoDebrief,
  onSubmit,
}: DebriefPanelProps) {
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

  const hasAiSuggestions = aiSuggestedCharIds.size > 0 || aiSuggestedSlIds.size > 0

  return (
    <div className="p-4 space-y-4">

      {/* AI 自动分析区 */}
      {hasAiSuggestions && aiSummary ? (
        <div className="rounded-novel border border-amber-200 bg-amber-50/80 px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <Bot size={12} className="text-amber-500" />
            <span className="text-[11px] font-semibold text-amber-700">AI 已自动分析本章</span>
          </div>
          <p className="text-[11px] text-amber-800 leading-relaxed">{aiSummary}</p>
          <p className="text-[10px] text-amber-500 mt-1">
            已预填 {aiSuggestedCharIds.size} 个人物、{aiSuggestedSlIds.size} 条故事线，请检查后提交
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-novel-ink-faint leading-relaxed">
            写完本章后，让 AI 自动提取变化，或手动填写后提交
          </p>
          {onAutoDebrief && (
            <button
              type="button"
              onClick={onAutoDebrief}
              disabled={autoDebriefing || !chapter.content?.trim()}
              className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-novel border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={11} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中…' : 'AI 自动复盘'}
            </button>
          )}
        </div>
      )}

      {/* 加载中遮罩 */}
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

      {/* 空状态提示 */}
      {displayChars.length === 0 && activeStorylines.length === 0 && (
        <p className="text-xs text-novel-ink-faint italic text-center py-4">
          暂无人物或活跃故事线<br />
          <span className="text-[10px]">请先在「人物」和「世界」页创建数据，<br />并在大纲节点上标注本章出场人物</span>
        </p>
      )}

      {/* 操作按钮区 */}
      <div className="flex gap-2">
        {onAutoDebrief && (
          <button
            type="button"
            onClick={onAutoDebrief}
            disabled={autoDebriefing || submitting || !chapter.content?.trim()}
            className="flex items-center justify-center gap-1.5 text-xs py-2 px-3 border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-novel font-medium disabled:opacity-50 transition-novel shrink-0"
          >
            <Bot size={12} className={autoDebriefing ? 'animate-pulse' : ''} />
            {autoDebriefing ? '分析中' : hasAiSuggestions ? '重新分析' : 'AI 分析'}
          </button>
        )}
        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting || autoDebriefing}
          className="flex-1 flex items-center justify-center gap-2 text-sm py-2.5 bg-novel-accent hover:bg-novel-accent-hover text-white rounded-novel font-medium disabled:opacity-60 transition-novel"
        >
          <CheckSquare size={14} className={submitting ? 'animate-pulse' : ''} />
          {submitting ? '提交中…' : hasAiSuggestions ? '确认并提交' : '提交复盘'}
        </button>
      </div>
    </div>
  )
}
