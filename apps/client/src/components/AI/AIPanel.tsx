import React, { useState, useRef } from 'react'
import { X, Zap, BookMarked, MessageSquare } from 'lucide-react'
import { useAppStore } from '../../store'
import { aiApi } from '../../api/client'
import type { QualityReport } from '../../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

interface Props { projectId: string }

type Tab = 'check' | 'suggest' | 'memory'

export default function AIPanel({ projectId }: Props) {
  const { setAiPanelOpen, activeChapterId, memories, setMemories } = useAppStore()
  const [tab, setTab] = useState<Tab>('check')
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState<QualityReport | null>(null)
  const [suggestText, setSuggestText] = useState('')
  const [streamOutput, setStreamOutput] = useState('')

  // ── 质检 ──────────────────────────────────────────────
  const runQualityCheck = async () => {
    if (!activeChapterId) return toast.error('请先选择一个章节')
    setLoading(true)
    try {
      const res = await aiApi.qualityCheck(projectId, {
        chapter_id: activeChapterId,
        model_profile: useAppStore.getState().aiModelProfile,
      })
      setReport(res.data)
    } finally {
      setLoading(false)
    }
  }

  // ── AI 建议（流式）──────────────────────────────────────
  const runSuggest = async () => {
    if (!activeChapterId || !suggestText.trim()) return
    setStreamOutput('')
    setLoading(true)
    try {
      const response = await fetch(
        `/api/v1/projects/${projectId}/ai/suggest/stream`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chapter_id: activeChapterId,
            prompt: suggestText,
            model_profile: useAppStore.getState().aiModelProfile,
          }),
        }
      )
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const lines = decoder.decode(value).split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ') && !line.includes('[DONE]')) {
            try {
              const { text } = JSON.parse(line.slice(6))
              setStreamOutput(prev => prev + text)
            } catch { }
          }
        }
      }
    } finally {
      setLoading(false)
    }
  }

  // ── 记忆提取 ──────────────────────────────────────────
  const extractMemory = async () => {
    if (!activeChapterId) return toast.error('请先选择一个章节')
    setLoading(true)
    try {
      const res = await aiApi.extractMemory(projectId, activeChapterId, useAppStore.getState().aiModelProfile)
      setMemories([...memories, ...res.data])
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
          { key: 'suggest', icon: MessageSquare, label: '建议' },
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

      <p className="px-4 py-2 text-[11px] text-gray-400 border-b border-gray-100 bg-gray-50/50">
        模型在顶部栏统一选择
      </p>

      {/* 内容 */}
      <div className="flex-1 overflow-auto p-4">

        {/* 质检 */}
        {tab === 'check' && (
          <div className="space-y-4">
            <button
              onClick={runQualityCheck}
              disabled={loading}
              className="w-full py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg"
            >
              {loading ? '检查中...' : '开始质检当前章节'}
            </button>
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
                        <div className="text-xs font-medium text-gray-700 capitalize">{key}</div>
                        <div className="text-xs text-gray-500">{dim.comment}</div>
                      </div>
                    </div>
                  ))}
                </div>
                {report.suggestions.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-700 mb-2">优化建议</div>
                    <ul className="space-y-1">
                      {report.suggestions.map((s, i) => (
                        <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                          <span className="text-amber-500 shrink-0">•</span>
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* AI 建议 */}
        {tab === 'suggest' && (
          <div className="space-y-3">
            <textarea
              value={suggestText}
              onChange={e => setSuggestText(e.target.value)}
              placeholder="告诉 AI 你想优化什么...&#10;例如：这章节奏太慢，帮我想想如何加强冲突"
              className="w-full h-28 text-sm border border-gray-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <button
              onClick={runSuggest}
              disabled={loading || !suggestText.trim()}
              className="w-full py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg"
            >
              {loading ? '生成中...' : '获取建议'}
            </button>
            {streamOutput && (
              <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 rounded-lg p-3 max-h-96 overflow-auto">
                {streamOutput}
              </div>
            )}
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
              {memories.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">暂无记忆条目</p>
              )}
              {memories.map(m => (
                <div key={m.id} className="p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">
                      {m.memory_type}
                    </span>
                    {m.chapter_number && (
                      <span className="text-xs text-gray-400">第{m.chapter_number}章</span>
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
