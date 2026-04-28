import React, { useEffect, useCallback, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../store'
import type { Chapter, Character, OutlineNode } from '../../types'
import toast from 'react-hot-toast'
import {
  BookOpen, Sparkles, X, Zap, Target, Users, Flag, GitBranch, RefreshCw,
  Maximize2, Minimize2, Clock, StickyNote, ChevronDown,
  Wand2, Feather, Flame, MessageSquare, PenLine,
} from 'lucide-react'
import clsx from 'clsx'

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

/** 剥离 HTML 取末尾 N 字作为「上章结尾」预览 */
function htmlTail(html: string, maxChars = 200): string {
  const div = document.createElement('div')
  div.innerHTML = html
  const text = (div.innerText || div.textContent || '').replace(/\s+/g, ' ').trim()
  return text.length <= maxChars ? text : '…' + text.slice(-maxChars)
}

/** 便笺本 localStorage key */
const scratchKey = (cid: string) => `novel:scratch:${cid}`

// ─── 章节状态选项 ─────────────────────────────────────────────────────────────
const STATUS_OPTIONS: { value: Chapter['status']; label: string; dotCls: string; textCls: string }[] = [
  { value: 'draft',    label: '初稿',  dotCls: 'bg-gray-300',   textCls: 'text-gray-500' },
  { value: 'writing',  label: '修改中', dotCls: 'bg-blue-400',   textCls: 'text-blue-600' },
  { value: 'done',     label: '完稿',  dotCls: 'bg-green-400',  textCls: 'text-green-600' },
  { value: 'reviewed', label: '已审',  dotCls: 'bg-amber-400',  textCls: 'text-amber-600' },
]

// ─── 选中文字快捷 AI 动作 ─────────────────────────────────────────────────────
const INLINE_ACTIONS = [
  {
    key: 'rewrite',  label: '改写',     icon: <RefreshCw size={11} />,
    buildPrompt: (t: string) =>
      `请将以下选中段落改写，保持语义不变但改变表达方式，只返回改写后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'expand',   label: '扩写',     icon: <Feather size={11} />,
    buildPrompt: (t: string) =>
      `请将以下段落扩写，增加细节和描写，只返回扩写后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'tension',  label: '加强张力', icon: <Flame size={11} />,
    buildPrompt: (t: string) =>
      `请改写以下段落，增强紧张感、情绪张力和节奏感，只返回改写后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'dialogue', label: '优化对话', icon: <MessageSquare size={11} />,
    buildPrompt: (t: string) =>
      `请优化以下对话内容，让其更自然流畅且更有角色特色，只返回修改后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'continue', label: '续写',     icon: <Wand2 size={11} />,
    buildPrompt: (t: string) =>
      `请从以下内容结尾处续写，风格保持一致，只返回续写的新内容，不要任何解释：\n\n「${t}」`,
  },
]

// ─── 人物角色标签 ─────────────────────────────────────────────────────────────
const ROLE_BADGE: Record<Character['role'], { label: string; cls: string }> = {
  protagonist: { label: '主角', cls: 'bg-amber-100 text-amber-700' },
  supporting:  { label: '配角', cls: 'bg-blue-50 text-blue-600' },
  antagonist:  { label: '反派', cls: 'bg-red-50 text-red-600' },
}

// ─────────────────────────────────────────────────────────────────────────────
export default function ChapterEditor({
  projectId, chapter, outlineNode, prevChapter, onFocusModeChange,
}: Props) {
  const { upsertChapter, characters } = useAppStore()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()

  // ── 面板 UI 状态 ───────────────────────────────────────────────────
  const [contextOpen, setContextOpen]   = useState(!!outlineNode)
  const [contextTab, setContextTab]     = useState<'plan' | 'scene' | 'notes'>('plan')
  const [focusMode, setFocusMode]       = useState(false)
  const [statusOpen, setStatusOpen]     = useState(false)
  const statusRef = useRef<HTMLDivElement>(null)

  // ── 便笺本（按章节 ID 存 localStorage）────────────────────────────
  const [notepad, setNotepad] = useState(() => {
    try { return localStorage.getItem(scratchKey(chapter.id)) ?? '' } catch { return '' }
  })

  // ── 原有 AI 草稿功能 ───────────────────────────────────────────────
  const [aiDrafting, setAiDrafting]                     = useState(false)
  const [draftText, setDraftText]                       = useState('')
  const [showDraft, setShowDraft]                       = useState(false)
  const [aiExtraPrompt, setAiExtraPrompt]               = useState('')
  const [autoInsertAfterDraft, setAutoInsertAfterDraft] = useState(true)

  // ── 选中文字快捷 AI ────────────────────────────────────────────────
  const [selectionText, setSelectionText]       = useState('')
  const [showSelectionBar, setShowSelectionBar] = useState(false)

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
    setShowDraft(false)
    setDraftText('')
    setAiDrafting(false)
    setShowSelectionBar(false)
    setSelectionText('')
    setNotepad(() => { try { return localStorage.getItem(scratchKey(chapter.id)) ?? '' } catch { return '' } })
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
    } catch { /* 静默失败 */ }
  }, [projectId, chapter.id, upsertChapter])

  const manualSave = async () => {
    if (!editor) return
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content: editor.getHTML() })
      upsertChapter(res.data)
      await chaptersApi.snapshot(projectId, chapter.id, '手动保存')
      toast.success('已保存快照')
    } catch { toast.error('保存失败') }
  }

  const updateStatus = async (status: Chapter['status']) => {
    setStatusOpen(false)
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { status })
      upsertChapter(res.data)
      toast.success(`状态 → 「${STATUS_OPTIONS.find(o => o.value === status)?.label}」`)
    } catch { toast.error('状态更新失败') }
  }

  const handleNotepadChange = (val: string) => {
    setNotepad(val)
    try { localStorage.setItem(scratchKey(chapter.id), val) } catch { /* ignore */ }
  }

  /** 点击选中快捷动作：预填 prompt 并自动触发生成 */
  const applyInlineAction = (actionKey: string) => {
    const action = INLINE_ACTIONS.find(a => a.key === actionKey)
    if (!action || !selectionText) return
    const prompt = action.buildPrompt(selectionText.slice(0, 400))
    setAiExtraPrompt(prompt)
    setShowSelectionBar(false)
    setShowDraft(true)
    // 稍作延迟让 state 更新后触发生成
    setTimeout(() => triggerGenerate(prompt), 80)
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
      setShowDraft(false); setDraftText('')
    } catch { toast.error('保存失败，请点顶部「保存」重试') }
  }, [editor, projectId, chapter.id, upsertChapter])

  /** 核心生成逻辑，可接受临时 prompt（选中快捷动作用） */
  const triggerGenerate = async (overridePrompt?: string, opts?: { replaceExisting?: boolean }) => {
    setAiDrafting(true); setDraftText(''); setShowDraft(true)
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
          if (p.text) { accumulated += p.text; setDraftText(accumulated) }
        }
      }
      for (const line of buf.split('\n')) {
        const p = parseSseDataLine(line)
        if (p?.error) throw new Error(p.error)
        if (p?.text) { accumulated += p.text; setDraftText(accumulated) }
      }
      if (!accumulated.trim()) { toast.error('未收到内容，请检查模型或稍后重试'); return }
      toast.success('生成完成')
      if (autoInsertAfterDraft) await insertDraftToEditorAndSave(accumulated, !!opts?.replaceExisting)
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'AI 生成失败')
    } finally {
      setAiDrafting(false)
    }
  }

  const generateDraft = (opts?: { replaceExisting?: boolean }) => {
    if (opts?.replaceExisting) {
      if (!window.confirm('「重新生成本章」将按大纲重写当前正文。建议先手动保存快照。确定继续？')) return
    }
    void triggerGenerate(undefined, opts)
  }

  // ─────────────────────────────────────────────────────────────────
  // 派生值
  // ─────────────────────────────────────────────────────────────────
  const wordCount       = editor?.storage.characterCount?.characters() ?? chapter.word_count
  const hasOutlineContent = outlineNode && (
    outlineNode.hook || outlineNode.summary || outlineNode.conflict || outlineNode.highlight
  )
  const currentStatus   = STATUS_OPTIONS.find(o => o.value === chapter.status) ?? STATUS_OPTIONS[0]
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
        <div className="flex items-center gap-2.5 shrink-0">
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
              className={clsx('flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-novel border transition-novel',
                contextOpen && contextTab === 'scene'
                  ? 'bg-novel-panel border-novel-border text-novel-accent'
                  : 'border-novel-border text-novel-ink-muted hover:bg-novel-panel')}>
              <Users size={12} />场景
            </button>
          )}

          {/* 章节计划 */}
          {!focusMode && outlineNode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'plan')); setContextTab('plan') }}
              title="章节计划"
              className={clsx('flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-novel border transition-novel',
                contextOpen && contextTab === 'plan'
                  ? 'bg-novel-panel border-novel-border text-novel-accent'
                  : 'border-novel-border text-novel-ink-muted hover:bg-novel-panel')}>
              <BookOpen size={12} />计划
            </button>
          )}

          {/* 便笺本 */}
          {!focusMode && (
            <button type="button"
              onClick={() => { setContextOpen(v => !(v && contextTab === 'notes')); setContextTab('notes') }}
              title="便笺本（本地保存，不进入正文）"
              className={clsx('flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-novel border transition-novel',
                contextOpen && contextTab === 'notes'
                  ? 'bg-novel-panel border-novel-border text-novel-accent'
                  : 'border-novel-border text-novel-ink-muted hover:bg-novel-panel')}>
              <StickyNote size={12} />便笺
            </button>
          )}

          {/* 专注模式切换 */}
          <button type="button" onClick={() => setFocusMode(v => !v)}
            title={focusMode ? '退出专注模式' : '专注写作模式（隐藏工具栏）'}
            className={clsx(
              'flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-novel border transition-novel',
              focusMode
                ? 'border-novel-accent text-novel-accent bg-novel-panel'
                : 'border-novel-border text-novel-ink-muted hover:bg-novel-panel',
            )}>
            {focusMode ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
            {focusMode ? '退出专注' : '专注'}
          </button>

          {/* 保存 */}
          <button type="button" onClick={manualSave}
            className="text-sm px-3 py-1.5 bg-novel-accent hover:bg-novel-accent-hover text-white rounded-novel transition-novel focus:outline-none focus-visible:ring-2 focus-visible:ring-novel-accent focus-visible:ring-offset-2">
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
                {INLINE_ACTIONS.map(action => (
                  <button key={action.key} type="button"
                    disabled={aiDrafting}
                    onClick={() => applyInlineAction(action.key)}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50">
                    {action.icon}{action.label}
                  </button>
                ))}
                <button type="button" onClick={() => setShowSelectionBar(false)}
                  className="ml-auto text-violet-300 hover:text-violet-500 p-0.5 shrink-0">
                  <X size={12} />
                </button>
              </div>
            </div>
          )}

          {/* AI 草稿预览 */}
          {showDraft && (
            <div className="border-t border-amber-100 bg-amber-50/60 px-6 py-4 shrink-0">
              <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <Sparkles size={13} className="text-amber-500" />
                  <span className="text-xs font-medium text-amber-800">
                    {aiDrafting ? 'AI 正在生成…' : 'AI 草稿预览'}
                  </span>
                  {aiDrafting && (
                    <span className="flex gap-0.5 ml-1">
                      {[0, 1, 2].map(i => (
                        <span key={i} className="w-1 h-1 rounded-full bg-amber-400 animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }} />
                      ))}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {!aiDrafting && draftText.trim() && (
                    <>
                      <button type="button"
                        onClick={() => insertDraftToEditorAndSave(draftText, false)}
                        className="text-xs px-2.5 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-novel transition-novel">
                        插入文末并保存
                      </button>
                      <button type="button"
                        onClick={() => { if (window.confirm('用草稿替换全部正文？')) insertDraftToEditorAndSave(draftText, true) }}
                        className="text-xs px-2.5 py-1 border border-amber-400 text-amber-800 rounded-novel hover:bg-amber-100 transition-novel">
                        替换全文并保存
                      </button>
                      <button type="button" onClick={() => generateDraft()}
                        className="text-xs px-2.5 py-1 border border-amber-300 text-amber-700 rounded-novel hover:bg-amber-100 transition-novel">
                        重新生成
                      </button>
                    </>
                  )}
                  <button type="button" onClick={() => setShowDraft(false)}
                    className="text-amber-400 hover:text-amber-600 p-1"><X size={14} /></button>
                </div>
              </div>
              <div className="text-sm text-gray-800 whitespace-pre-wrap max-h-52 overflow-auto leading-relaxed bg-white rounded-novel px-4 py-3 border border-amber-100">
                {draftText || <span className="text-gray-400 italic">{aiDrafting ? '等待首包…' : '（空）'}</span>}
              </div>
            </div>
          )}

          {/* AI 输入工具区（专注模式下隐藏）*/}
          {!focusMode && (
            <div className="border-t border-novel-border bg-novel-panel/90 px-6 py-3 shrink-0 space-y-2">
              <label className="block text-[11px] font-medium text-novel-ink-muted">
                起笔 / 续写说明（可选；选中文字后点快捷动作可自动填入）
              </label>
              <textarea
                value={aiExtraPrompt}
                onChange={e => setAiExtraPrompt(e.target.value)}
                rows={2}
                disabled={aiDrafting}
                placeholder="例如：偏压抑、少对话、突出某某伏笔；或重写时希望的开场氛围…"
                className="w-full text-xs border border-novel-border rounded-novel px-3 py-2 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-y min-h-[2.5rem] disabled:opacity-60"
              />
              <label className="flex items-center gap-2 text-[11px] text-novel-ink-muted cursor-pointer select-none">
                <input type="checkbox" checked={autoInsertAfterDraft}
                  onChange={e => setAutoInsertAfterDraft(e.target.checked)}
                  disabled={aiDrafting} className="rounded border-novel-border" />
                生成完成后自动写入正文并保存（续写插文末；「重新生成」为替换全文）
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={() => generateDraft()} disabled={aiDrafting}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 font-medium bg-novel-accent text-white rounded-novel hover:bg-novel-accent-hover disabled:opacity-60 transition-novel">
                  <Sparkles size={13} className={aiDrafting ? 'animate-pulse' : ''} />
                  {aiDrafting ? '生成中…' : chapter.word_count > 100 ? 'AI 续写' : 'AI 起笔'}
                </button>
                <button type="button" onClick={() => generateDraft({ replaceExisting: true })} disabled={aiDrafting}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 font-medium border border-red-200 text-red-700 bg-red-50/80 rounded-novel hover:bg-red-100 disabled:opacity-60 transition-novel">
                  <RefreshCw size={13} />重新生成本章
                </button>
                <span className="text-[10px] text-novel-ink-faint">模型在顶部栏选择</span>
              </div>
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
                  { key: 'plan',  label: '章节计划', icon: <BookOpen size={11} /> },
                  { key: 'scene', label: '场景助手', icon: <Users size={11} /> },
                  { key: 'notes', label: '便笺本',   icon: <StickyNote size={11} /> },
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

              {/* ── 便笺本 Tab ── */}
              {contextTab === 'notes' && (
                <div className="p-4 flex flex-col" style={{ minHeight: '320px' }}>
                  <p className="text-[10px] text-novel-ink-faint mb-2 leading-relaxed">
                    本章私人便笺，不进入正文，自动本地保存
                  </p>
                  <textarea
                    value={notepad}
                    onChange={e => handleNotepadChange(e.target.value)}
                    placeholder="随手记：场景线索、待填坑、灵感片段……"
                    className="flex-1 text-xs border border-novel-border rounded-novel px-3 py-2.5 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-none leading-relaxed"
                    style={{ minHeight: '280px' }}
                  />
                  {notepad && (
                    <p className="text-[10px] text-novel-ink-faint mt-1.5 text-right">
                      {notepad.length} 字符 · 已自动保存
                    </p>
                  )}
                </div>
              )}

            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── 子组件：PlanCard ────────────────────────────────────────────────────────
type AccentColor = 'amber' | 'blue' | 'purple' | 'red' | 'green'
const accentCls: Record<AccentColor, { border: string; label: string; bg: string }> = {
  amber:  { border: 'border-amber-100',  label: 'text-amber-700',  bg: 'bg-amber-50/70' },
  blue:   { border: 'border-blue-100',   label: 'text-blue-700',   bg: 'bg-blue-50/70' },
  purple: { border: 'border-purple-100', label: 'text-purple-700', bg: 'bg-purple-50/70' },
  red:    { border: 'border-red-100',    label: 'text-red-700',    bg: 'bg-red-50/70' },
  green:  { border: 'border-green-100',  label: 'text-green-700',  bg: 'bg-green-50/70' },
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

      {expanded && (character.motivation || character.personality || character.arc || character.faction) && (
        <div className="px-3 pb-2.5 pt-2 border-t border-novel-border space-y-1.5">
          {character.motivation  && <InfoRow label="动机" value={character.motivation} />}
          {character.personality && <InfoRow label="性格" value={character.personality} />}
          {character.arc         && <InfoRow label="弧线" value={character.arc} />}
          {character.faction     && <InfoRow label="阵营" value={character.faction} />}
        </div>
      )}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-[10px] text-novel-ink-faint shrink-0 w-8">{label}</span>
      <span className="text-[10px] text-novel-ink leading-relaxed">{value}</span>
    </div>
  )
}
