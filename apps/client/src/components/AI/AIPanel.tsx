import React, { useEffect, useMemo, useState, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { X, Zap, BookMarked, MessageSquare, SendHorizontal, Loader2, Wand2 } from 'lucide-react'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../../store'
import { aiApi } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import { memoryDisplayChapter } from '../../utils/chapterNumber'
import type { AiChatMessage, Chapter, QualityReport } from '../../types'
import {
  normalizeQualityIssues,
  normalizeQualitySuggestions,
  qualityReportHasFixableHints,
} from '../../utils/qualityReport'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { AxiosError } from 'axios'

interface Props { projectId: string }

type Tab = 'check' | 'chat' | 'memory'
type ChatContextType = 'outline' | 'writing' | 'general'

const DIMENSION_LABELS: Record<string, string> = {
  plot: '情节',
  character: '人物',
  setting_consistency: '设定一致性',
  pacing: '节奏',
  hooks: '悬念',
  outline_alignment: '大纲对齐',
  face_slap_payoff: '打脸兑现',
  emotional_resonance: '情感共鸣',
  subscribe_intent: '追读意愿',
  storyline_progress: '故事线推进',
  realm_check: '境界体系',
}

function chapterPlainTextLen(ch: Chapter): number {
  return (ch.content || '').replace(/<[^>]*>/g, '').replace(/\u00a0/g, ' ').trim().length
}

/** 参考上下文：正文有可用内容即可（不限定完稿/已审）；空占位不可选 */
function isChapterReferenceSelectable(ch: Chapter): boolean {
  if ((ch.word_count ?? 0) > 0) return true
  return chapterPlainTextLen(ch) >= 10
}

function microFixErrorMessage(err: unknown): string {
  const ax = err as AxiosError<{ detail?: string | { message?: string; rationale?: string } }>
  const detail = ax.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && detail.message) {
    const why = (detail.rationale || '').trim()
    return why.length > 0 ? `${detail.message}（${why.length > 80 ? `${why.slice(0, 80)}…` : why}）` : detail.message
  }
  return err instanceof Error ? err.message : '快速修复失败'
}

export default function AIPanel({ projectId }: Props) {
  const { setAiPanelOpen, activeChapterId, memories, setMemories, chapters, upsertChapter } = useAppStore()
  const location = useLocation()
  const [tab, setTab] = useState<Tab>('check')
  const [loading, setLoading] = useState(false)
  const [microFixing, setMicroFixing] = useState(false)
  const [microFixingIndex, setMicroFixingIndex] = useState<number | null>(null)
  const [report, setReport] = useState<QualityReport | null>(null)
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<AiChatMessage[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  /** 写作对话：并入模型上下文的额外章节（不含当前章） */
  const [chatRefChapterIds, setChatRefChapterIds] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!projectId || !activeChapterId) return
    aiApi.listMemory(projectId).then(res => setMemories(res.data)).catch(() => {})
  }, [projectId, activeChapterId, setMemories])

  useEffect(() => {
    setChatRefChapterIds([])
  }, [projectId])

  useEffect(() => {
    if (!activeChapterId) return
    setChatRefChapterIds(prev => prev.filter(id => id !== activeChapterId))
  }, [activeChapterId])

  useEffect(() => {
    setChatRefChapterIds((prev) => {
      const next = prev.filter((id) => {
        const c = chapters.find((x) => x.id === id)
        return c && isChapterReferenceSelectable(c)
      })
      return next.length === prev.length ? prev : next
    })
  }, [chapters])

  const chapterById = useMemo(() => {
    const m = new Map<string, { title: string; sort_order: number }>()
    for (const c of chapters) m.set(c.id, { title: c.title, sort_order: c.sort_order })
    return m
  }, [chapters])

  const activeChapter = useMemo(
    () => chapters.find((c) => c.id === activeChapterId),
    [activeChapterId, chapters],
  )

  const chatContextType = useMemo<ChatContextType>(() => {
    if (location.pathname.includes('/outline')) return 'outline'
    if (location.pathname.includes('/write')) return 'writing'
    return 'general'
  }, [location.pathname])

  const chatChapterId = chatContextType === 'writing' ? activeChapterId ?? undefined : undefined

  const chatContextLabel = useMemo(() => {
    if (chatContextType === 'outline') return '大纲'
    if (chatContextType === 'writing') return activeChapter ? `正文：${activeChapter.title}` : '正文'
    return '项目'
  }, [activeChapter, chatContextType])

  /** 参考章节：按正文列表顺位正序（第1章在上，依次向下） */
  const chaptersSortedForChat = useMemo(
    () =>
      [...chapters].sort((a, b) => {
        if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order
        return String(a.id).localeCompare(String(b.id))
      }),
    [chapters],
  )

  const toggleChatRefChapter = (id: string) => {
    if (id === activeChapterId) return
    const target = chapters.find((c) => c.id === id)
    if (!target || !isChapterReferenceSelectable(target)) return
    setChatRefChapterIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id)
      if (prev.length >= 8) {
        toast.error('参考章节最多 8 章')
        return prev
      }
      return [...prev, id]
    })
  }

  const chatPlaceholder = chatContextType === 'outline'
    ? '这个大纲里面主角怎么突破的？'
    : chatContextType === 'writing'
      ? '这段正文里主角突破的代价写清楚了吗？'
      : '这个项目当前最需要补强什么？'

  const currentChapterMemories = useMemo(
    () => activeChapterId
      ? memories.filter(m => m.chapter_id === activeChapterId)
      : [],
    [activeChapterId, memories],
  )

  useEffect(() => {
    if (!activeChapterId) {
      setReport(null)
      return
    }
    const cached = activeChapter && 'last_quality_report' in activeChapter
      ? (activeChapter as { last_quality_report?: QualityReport }).last_quality_report
      : undefined
    setReport(cached ?? null)
  }, [activeChapter, activeChapterId])

  useEffect(() => {
    if (tab !== 'chat') return
    if (chatContextType === 'writing' && !chatChapterId) {
      setChatMessages([])
      return
    }
    aiApi.listChatMessages(projectId, {
      context_type: chatContextType,
      chapter_id: chatChapterId,
    }).then(res => setChatMessages(res.data)).catch(() => {})
  }, [chatChapterId, chatContextType, projectId, tab])

  useEffect(() => {
    if (tab === 'chat') messagesEndRef.current?.scrollIntoView({ block: 'end' })
  }, [chatMessages, chatLoading, tab])

  const reportSuggestions = useMemo(
    () => (report ? normalizeQualitySuggestions(report.suggestions) : []),
    [report],
  )

  const reportIssues = useMemo(
    () => (report ? normalizeQualityIssues(report.issues) : []),
    [report],
  )

  const canQuickFix = Boolean(
    activeChapterId
    && activeChapter
    && report
    && qualityReportHasFixableHints(report)
    && chapterPlainTextLen(activeChapter) >= 10,
  )

  // ── 质检 ──────────────────────────────────────────────
  const runQualityCheck = async () => {
    if (!activeChapterId) return toast.error('请先选择一个章节')
    setLoading(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.qualityCheck(projectId, {
        chapter_id: activeChapterId,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const data = res.data as QualityReport & { error?: string }
      if (data.error || (data.overall_score === 0 && !Object.keys(data.dimensions || {}).length)) {
        toast.error(data.summary || '质检失败，请稍后重试')
      }
      setReport(data)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '质检请求失败')
    } finally {
      setLoading(false)
    }
  }

  const runQualityMicroFix = async (focusSuggestionIndex?: number) => {
    if (!activeChapterId || !report) return toast.error('请先完成章节质检')
    if (!canQuickFix) return toast.error('当前章节无正文或报告无可修复项')
    const route = useAppStore.getState().aiBackendRoute
    setMicroFixing(true)
    setMicroFixingIndex(focusSuggestionIndex ?? null)
    try {
      const res = await aiApi.qualityCheckMicroFix(projectId, {
        chapter_id: activeChapterId,
        suggestions: reportSuggestions,
        issues: reportIssues,
        ...(focusSuggestionIndex != null ? { focus_suggestion_index: focusSuggestionIndex } : {}),
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      upsertChapter(res.data.chapter)
      const why = (res.data.rationale || '').trim()
      toast.success(
        why.length > 0
          ? `已应用局部修改：${why.length > 100 ? `${why.slice(0, 100)}…` : why}`
          : '已根据优化建议更新正文（局部修改）',
      )
    } catch (e) {
      toast.error(microFixErrorMessage(e))
    } finally {
      setMicroFixing(false)
      setMicroFixingIndex(null)
    }
  }

  // ── AI 对话（流式 + 后端持久化）───────────────────────────
  const sendChat = async () => {
    const prompt = chatInput.trim()
    if (!prompt || chatLoading) return
    if (chatContextType === 'writing') {
      if (!activeChapterId) {
        toast.error('请先选择一个章节')
        return
      }
      if (!chapters.some(c => c.id === activeChapterId)) {
        toast.error('当前章节不在本书列表中，请在左侧重新选择一章后再试')
        return
      }
    }

    const now = new Date().toISOString()
    const assistantId = `tmp-assistant-${Date.now()}`
    const userMessage: AiChatMessage = {
      id: `tmp-user-${Date.now()}`,
      project_id: projectId,
      chapter_id: chatChapterId ?? null,
      context_type: chatContextType,
      role: 'user',
      content: prompt,
      created_at: now,
    }
    const assistantMessage: AiChatMessage = {
      id: assistantId,
      project_id: projectId,
      chapter_id: chatChapterId ?? null,
      context_type: chatContextType,
      role: 'assistant',
      content: '',
      created_at: now,
    }
    setChatMessages(prev => [...prev, userMessage, assistantMessage])
    setChatInput('')
    setChatLoading(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const response = await authFetch(aiApi.chatStreamUrl(projectId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          context_type: chatContextType,
          chapter_id: chatChapterId,
          ...(chatContextType === 'writing' && chatRefChapterIds.length > 0
            ? { additional_chapter_ids: chatRefChapterIds }
            : {}),
          model_profile: modelProfileFromRoute(route),
          ...routeLlmProviderPayload(route),
        }),
      })
      if (!response.ok || !response.body) throw new Error('对话请求失败')
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const applyLine = (rawLine: string) => {
        const line = rawLine.trim()
        if (!line.startsWith('data: ') || line.includes('[DONE]')) return
        const payload = JSON.parse(line.slice(6)) as { text?: string; error?: string }
        if (payload.error) throw new Error(payload.error)
        if (!payload.text) return
        setChatMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: m.content + payload.text } : m
        ))
      }
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) applyLine(line)
      }
      if (buffer.trim()) applyLine(buffer)
      const refreshed = await aiApi.listChatMessages(projectId, {
        context_type: chatContextType,
        chapter_id: chatChapterId,
      })
      setChatMessages(refreshed.data)
    } catch (err) {
      const message = err instanceof Error ? err.message : '对话失败'
      setChatMessages(prev => prev.map(m => {
        if (m.id !== assistantId) return m
        const partial = m.content.trim()
        return {
          ...m,
          content: partial
            ? `${partial}\n\n⚠️ 回复未完整：${message}`
            : `对话失败：${message}`,
        }
      }))
      toast.error(message)
    } finally {
      setChatLoading(false)
    }
  }

  const handleChatKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendChat()
    }
  }

  // ── 记忆提取 ──────────────────────────────────────────
  const extractMemory = async () => {
    if (!activeChapterId) return toast.error('请先选择一个章节')
    setLoading(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.extractMemory(
        projectId,
        activeChapterId,
        modelProfileFromRoute(route),
        llmProviderIdFromRoute(route),
      )
      const allMemories = await aiApi.listMemory(projectId)
      setMemories(allMemories.data)
      toast.success(`提取了 ${res.data.length} 条记忆`)
    } finally {
      setLoading(false)
    }
  }

  const scoreColor = (score: number) =>
    score >= 8 ? 'text-green-600' : score >= 6 ? 'text-amber-600' : 'text-red-500'

  const statusBadge = (status: string) => ({
    excellent: 'bg-green-100 text-green-700',
    pass: 'bg-blue-100 text-blue-700',
    warning: 'bg-amber-100 text-amber-700',
    fail: 'bg-red-100 text-red-600',
  }[status] ?? 'bg-gray-100 text-gray-600')

  const dimensionLabel = (key: string) => DIMENSION_LABELS[key] ?? key

  return (
    <aside className="w-80 flex flex-col border-l border-gray-100 bg-white shrink-0">
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <span className="font-semibold text-sm text-gray-800">AI 助手</span>
        <button onClick={() => setAiPanelOpen(false)} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>

      {/* Tab */}
      <div className="flex border-b border-gray-100 shrink-0">
        {([
          { key: 'check', icon: Zap, label: '质检' },
          { key: 'chat', icon: MessageSquare, label: '对话' },
          { key: 'memory', icon: BookMarked, label: '记忆库' },
        ] as const).map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1 py-2 text-xs transition-colors',
              tab === key
                ? 'border-b-2 border-amber-500 text-amber-600 font-semibold'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>
      {/* 内容 */}
      <div className={clsx('flex-1 min-h-0', tab === 'chat' ? 'flex flex-col' : 'overflow-auto p-4')}>

        {/* 质检 */}
        {tab === 'check' && (
          <div className="space-y-4">
            <button
              onClick={runQualityCheck}
              disabled={loading || microFixing}
              className="w-full py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg"
            >
              {loading ? '检查中...' : report ? '重新质检当前章节' : '开始质检当前章节'}
            </button>
            {report && canQuickFix && (
              <button
                type="button"
                onClick={() => void runQualityMicroFix()}
                disabled={loading || microFixing || !activeChapterId}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 py-2 text-sm text-emerald-800 transition-colors hover:bg-emerald-100 disabled:opacity-50"
              >
                {microFixing && microFixingIndex === null ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Wand2 size={14} />
                )}
                {microFixing && microFixingIndex === null ? '正在快速修复…' : '快速修复（按建议改正文）'}
              </button>
            )}
            {report && canQuickFix && (
              <p className="text-[11px] leading-snug text-gray-500">
                仅替换与建议相关的一小段正文，不会整章重写；修改前会自动备份版本。
              </p>
            )}
            {report && (
              <>
                <div className="text-center">
                  <span className={clsx('text-4xl font-bold', scoreColor(report.overall_score))}>
                    {report.overall_score.toFixed(1)}
                  </span>
                  <span className="text-gray-400 text-sm"> / 10</span>
                  <p className="text-xs text-gray-500 mt-1">{report.summary}</p>
                </div>
                <div className="space-y-2">
                  {Object.entries(report.dimensions).map(([key, dim]) => (
                    <div key={key} className="flex items-start gap-2">
                      <span className={clsx('text-xs px-2 py-0.5 rounded-full shrink-0 mt-0.5', statusBadge(dim.status))}>
                        {dim.score}
                      </span>
                      <div>
                        <div className="text-xs font-medium text-gray-700">{dimensionLabel(key)}</div>
                        <div className="text-xs text-gray-500">{dim.comment}</div>
                      </div>
                    </div>
                  ))}
                </div>
                {reportSuggestions.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-700 mb-2">优化建议</div>
                    <ul className="space-y-2">
                      {reportSuggestions.map((text, i) => (
                        <li key={i} className="text-xs text-gray-600">
                          <div className="flex gap-1.5">
                            <span className="text-amber-500 shrink-0">•</span>
                            <span className="min-w-0 flex-1">{text}</span>
                          </div>
                          {canQuickFix && (
                            <button
                              type="button"
                              onClick={() => void runQualityMicroFix(i)}
                              disabled={loading || microFixing}
                              className="mt-1 ml-4 text-[11px] text-emerald-700 hover:text-emerald-900 disabled:opacity-50"
                            >
                              {microFixing && microFixingIndex === i ? '修复中…' : '修这条'}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* AI 对话 */}
        {tab === 'chat' && (
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
            <div className="flex items-center justify-between gap-2 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
              <span className="min-w-0 truncate text-xs font-medium text-amber-800">{chatContextLabel}</span>
              {chatLoading && <Loader2 size={13} className="shrink-0 animate-spin text-amber-600" />}
            </div>

            {chatContextType === 'writing' && chaptersSortedForChat.length > 0 && (
              <details className="rounded-lg border border-gray-200 bg-gray-50/80 text-xs">
                <summary className="cursor-pointer select-none px-3 py-2 font-medium text-gray-700 hover:bg-gray-100/80">
                  参考章节（可选）
                  {chatRefChapterIds.length > 0 && (
                    <span className="ml-1.5 font-normal text-amber-700">已选 {chatRefChapterIds.length} 章</span>
                  )}
                </summary>
                <p className="border-t border-gray-100 px-3 py-1.5 text-[11px] leading-snug text-gray-500">
                  勾选后，本轮对话会把对应章节的正文一并交给模型。当前章已默认在上下文中，无需勾选。
                  列表按正文顺序从前往后排列；只要该章已有正文（字数大于 0 或去掉格式后约有少量文字）即可勾选，空章节不可选。
                </p>
                <div className="max-h-36 space-y-0.5 overflow-y-auto border-t border-gray-100 px-2 py-2">
                  {chaptersSortedForChat.map(ch => {
                    const isCurrent = ch.id === activeChapterId
                    const refOk = isChapterReferenceSelectable(ch)
                    const checked = chatRefChapterIds.includes(ch.id)
                    const disabled = isCurrent || chatLoading || !refOk
                    const blockReason = isCurrent
                      ? '当前章节已带入对话'
                      : !refOk
                        ? '该章暂无正文'
                        : undefined
                    return (
                      <label
                        key={ch.id}
                        title={blockReason}
                        className={clsx(
                          'flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-white/90',
                          disabled && 'cursor-not-allowed opacity-55',
                        )}
                      >
                        <input
                          type="checkbox"
                          className="shrink-0 rounded border-gray-300 text-amber-600 focus:ring-amber-400 disabled:opacity-40"
                          checked={checked}
                          disabled={disabled}
                          onChange={() => toggleChatRefChapter(ch.id)}
                        />
                        <span className="min-w-0 truncate text-gray-700">{ch.title}</span>
                        {isCurrent && <span className="shrink-0 text-[10px] text-gray-400">当前</span>}
                        {!isCurrent && !refOk && (
                          <span className="shrink-0 text-[10px] text-gray-400">无正文</span>
                        )}
                      </label>
                    )
                  })}
                </div>
              </details>
            )}

            <div className="min-h-0 flex-1 overflow-auto space-y-3 pr-1">
              {chatMessages.length === 0 && (
                <div className="rounded-lg bg-gray-50 px-3 py-4 text-center text-xs text-gray-400">
                  {chatPlaceholder}
                </div>
              )}
              {chatMessages.map((m) => (
                <div
                  key={m.id}
                  className={clsx(
                    'flex',
                    m.role === 'user' ? 'justify-end' : 'justify-start',
                  )}
                >
                  <div
                    className={clsx(
                      'max-w-[92%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed',
                      m.role === 'user'
                        ? 'bg-amber-500 text-white'
                        : 'bg-gray-50 text-gray-700',
                    )}
                  >
                    {m.content || (m.role === 'assistant' && chatLoading ? '思考中...' : '')}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="flex items-end gap-2 border-t border-gray-100 pt-3">
              <textarea
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={handleChatKeyDown}
                disabled={chatLoading || (chatContextType === 'writing' && !activeChapterId)}
                placeholder={chatPlaceholder}
                className="min-h-[44px] max-h-28 flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <button
                type="button"
                onClick={() => void sendChat()}
                disabled={chatLoading || !chatInput.trim() || (chatContextType === 'writing' && !activeChapterId)}
                title="发送"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white transition-colors hover:bg-amber-600 disabled:opacity-50"
              >
                {chatLoading ? <Loader2 size={16} className="animate-spin" /> : <SendHorizontal size={16} />}
              </button>
            </div>
          </div>
        )}

        {/* 记忆库 */}
        {tab === 'memory' && (
          <div className="space-y-3">
            <button
              onClick={extractMemory}
              disabled={loading}
              className="w-full py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg"
            >
              {loading ? '提取中...' : '从当前章节提取记忆'}
            </button>
            <div className="space-y-2">
              {currentChapterMemories.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">暂无记忆条目</p>
              )}
              {currentChapterMemories.map(m => (
                <div key={m.id} className="p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">
                      {m.memory_type}
                    </span>
                    {(m.chapter_id || m.chapter_number != null) && (
                      <span className="text-xs text-gray-400">
                        第{memoryDisplayChapter(m, chapterById) || '?'}章
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-700 leading-relaxed">{m.content}</p>
                  {m.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {m.tags.map(t => (
                        <span key={t} className="text-xs text-gray-400">#{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
