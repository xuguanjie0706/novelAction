import React, { useCallback, useEffect, useState } from 'react'
import { Database, Loader2, Search } from 'lucide-react'
import { aiApi } from '../../api/client'
import type { RagQueryResponse, RagRetrievalLog, RagSearchHit } from '../../types'
import clsx from 'clsx'

const EXAMPLE_QUERIES = [
  '反派1号起了没',
  '反派1号怎么死的',
  '主角当前境界',
  '未回收伏笔',
]

function sourceLabel(source: RagSearchHit['retrieval_source']) {
  if (source === 'semantic') return '语义'
  if (source === 'recency_anchor') return '时序锚'
  return '时序兜底'
}

function statusLabel(status: string) {
  if (status === 'ok') return '语义检索'
  if (status === 'embed_failed') return '向量化失败·时序兜底'
  return '时序兜底'
}

export interface MemoryRagPanelProps {
  projectId: string
  maxChapter?: number
}

/** 记忆库 RAG 查询与检索日志面板（结构化输入/输出）。 */
export default function MemoryRagPanel({ projectId, maxChapter }: MemoryRagPanelProps) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RagQueryResponse | null>(null)
  const [logs, setLogs] = useState<RagRetrievalLog[]>([])
  const [selectedLog, setSelectedLog] = useState<RagRetrievalLog | null>(null)
  const [tab, setTab] = useState<'query' | 'logs'>('query')

  const loadLogs = useCallback(async () => {
    const res = await aiApi.listRagLogs(projectId, { limit: 40 })
    setLogs(res.data)
  }, [projectId])

  useEffect(() => {
    loadLogs().catch(() => {})
  }, [loadLogs])

  const runQuery = async (q?: string) => {
    const text = (q ?? query).trim()
    if (!text) return
    setLoading(true)
    setResult(null)
    try {
      const res = await aiApi.ragQuery(projectId, {
        q: text,
        top_k: 20,
        max_chapter: maxChapter,
        include_injected_summary: true,
      })
      setResult(res.data)
      setTab('query')
      await loadLogs()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full border-l border-gray-100 bg-white w-[420px] shrink-0">
      <div className="px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-800">
          <Database size={16} className="text-amber-600" />
          RAG 语义检索
        </div>
        <p className="text-xs text-gray-500 mt-1">
          查看检索 query 与命中记忆；写章时相同逻辑会注入大模型 prompt。
        </p>
        <div className="flex gap-1 mt-2">
          {(['query', 'logs'] as const).map(k => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={clsx(
                'text-xs px-2.5 py-1 rounded-md',
                tab === k ? 'bg-amber-100 text-amber-800' : 'text-gray-500 hover:bg-gray-50',
              )}
            >
              {k === 'query' ? '查询' : '日志'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'query' ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="p-4 space-y-2 border-b border-gray-50">
            <div className="flex gap-2">
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && void runQuery()}
                placeholder="例如：反派1号起了没、怎么死的"
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
              <button
                type="button"
                disabled={loading}
                onClick={() => void runQuery()}
                className="shrink-0 px-3 py-2 rounded-lg bg-amber-500 text-white text-sm hover:bg-amber-600 disabled:opacity-50 flex items-center gap-1"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                检索
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_QUERIES.map(ex => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => { setQuery(ex); void runQuery(ex) }}
                  className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-100 hover:border-amber-200"
                >
                  {ex}
                </button>
              ))}
            </div>
            {maxChapter != null && (
              <p className="text-[11px] text-gray-400">仅检索第 {maxChapter} 章及之前的记忆（防剧透）</p>
            )}
          </div>

          <div className="flex-1 overflow-auto p-4 space-y-4">
            {!result && !loading && (
              <p className="text-sm text-gray-400 text-center py-8">输入问题后检索记忆库</p>
            )}
            {result && (
              <>
                <div className="text-xs text-gray-500 space-y-1 bg-gray-50 rounded-lg p-3">
                  <div>
                    状态：{statusLabel(result.status)} · {result.duration_ms}ms · log{' '}
                    {result.log_id.slice(0, 8)}
                  </div>
                  <div className="font-mono text-[11px] break-all">query: {result.query}</div>
                </div>
                <div className="rounded-lg border border-amber-100 bg-amber-50/50 p-3">
                  <div className="text-xs font-semibold text-amber-800 mb-1">摘要（answer_hint）</div>
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">
                    {result.answer_hint}
                  </pre>
                </div>
                {result.memory_summary ? (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-gray-600 font-medium">注入 prompt 的记忆摘要</summary>
                    <pre className="mt-2 p-2 bg-gray-50 rounded text-gray-600 whitespace-pre-wrap max-h-40 overflow-auto">
                      {result.memory_summary}
                    </pre>
                  </details>
                ) : null}
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-gray-600">命中 {result.hits.length} 条</div>
                  {result.hits.map(h => (
                    <HitCard key={h.memory_id} hit={h} />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-3 space-y-2">
          {logs.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">暂无 RAG 日志</p>
          ) : (
            logs.map(log => (
              <button
                key={log.id}
                type="button"
                onClick={() => setSelectedLog(selectedLog?.id === log.id ? null : log)}
                className={clsx(
                  'w-full text-left rounded-lg border p-3 text-xs transition-colors',
                  selectedLog?.id === log.id ? 'border-amber-300 bg-amber-50' : 'border-gray-100 hover:bg-gray-50',
                )}
              >
                <div className="flex justify-between gap-2">
                  <span className="font-medium text-gray-800">{log.source}</span>
                  <span className="text-gray-400">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <div className="text-gray-600 mt-1 truncate">
                  {(log.input_payload?.query as string) || '—'}
                </div>
                <div className="text-gray-400 mt-0.5">
                  {statusLabel(log.status)} · {(log.output_payload?.hit_count as number) ?? 0} 条
                </div>
                {selectedLog?.id === log.id ? (
                  <pre className="mt-2 p-2 bg-white rounded border border-gray-100 text-[10px] overflow-auto max-h-48 whitespace-pre-wrap">
                    {JSON.stringify({ input: log.input_payload, output: log.output_payload }, null, 2)}
                  </pre>
                ) : null}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function HitCard({ hit }: { hit: RagSearchHit }) {
  return (
    <div className="rounded-lg border border-gray-100 p-3 text-sm bg-white">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
        <span>#{hit.rank}</span>
        <span className="px-1.5 py-0.5 rounded bg-gray-100">{sourceLabel(hit.retrieval_source)}</span>
        {hit.score != null ? <span>score {hit.score.toFixed(3)}</span> : null}
        {hit.chapter_number != null ? <span>第{hit.chapter_number}章</span> : null}
        <span>{hit.memory_type}</span>
      </div>
      {hit.title ? <div className="font-medium text-gray-800">{hit.title}</div> : null}
      <p className="text-gray-700 mt-1 leading-relaxed">{hit.content_preview}</p>
    </div>
  )
}
