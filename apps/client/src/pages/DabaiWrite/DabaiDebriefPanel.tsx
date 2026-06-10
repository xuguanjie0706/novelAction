/**
 * DabaiDebriefPanel — 复盘/记忆侧栏：
 * 一键复盘（图事实→Neo4j + 记忆→pgvector，幂等可重跑）+ 本章记忆列表 + 图谱同步状态。
 */
import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Brain, Loader2, Network, RefreshCw, Sparkles, X } from 'lucide-react'
import clsx from 'clsx'
import { aiApi } from '../../api/client'
import { modelProfileFromRoute, llmProviderIdFromRoute, useAppStore } from '../../store'
import type { Chapter, MemoryChunk } from '../../types'

interface DebriefResult {
  graph_sync: { status: string; applied: number; message?: string }
  graph_fact_count: number
  vector_count: number
  stale_deleted: number
  warnings: string[]
}

const GRAPH_STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  ok: { text: '图谱已同步', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  fallback: { text: '图谱未启用（Neo4j 未配置）', cls: 'bg-gray-50 text-gray-500 border-gray-200' },
  error: { text: '图谱同步失败', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
}

export default function DabaiDebriefPanel({
  projectId,
  chapter,
  onClose,
}: {
  projectId: string
  chapter: Chapter
  onClose: () => void
}) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<DebriefResult | null>(null)
  const [memories, setMemories] = useState<MemoryChunk[]>([])
  const [loadingMem, setLoadingMem] = useState(false)

  const loadMemories = useCallback(async () => {
    setLoadingMem(true)
    try {
      const res = await aiApi.listMemory(projectId, { chapter_id: chapter.id, sort_by: 'importance' })
      setMemories(res.data as MemoryChunk[])
    } catch {
      /* 静默：记忆列表非关键路径 */
    } finally {
      setLoadingMem(false)
    }
  }, [projectId, chapter.id])

  useEffect(() => {
    setResult(null)
    void loadMemories()
  }, [loadMemories])

  const runDebrief = async () => {
    if (running) return
    setRunning(true)
    try {
      const route = useAppStore.getState().aiBackendRoute
      const res = await aiApi.dabaiDebrief(projectId, chapter.id, {
        model_profile: modelProfileFromRoute(route),
        llm_provider_id: llmProviderIdFromRoute(route),
      })
      setResult(res.data)
      toast.success(`复盘完成：${res.data.graph_fact_count} 条图事实 / ${res.data.vector_count} 条记忆`)
      void loadMemories()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : '复盘失败')
    } finally {
      setRunning(false)
    }
  }

  const graphBadge = result
    ? GRAPH_STATUS_LABEL[result.graph_sync?.status ?? ''] ?? GRAPH_STATUS_LABEL.error
    : null

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-rose-100 bg-rose-50/20">
      <div className="flex items-center gap-2 border-b border-rose-100 px-3 py-2.5">
        <Brain size={15} className="text-rose-500" />
        <span className="flex-1 text-xs font-semibold text-rose-800">复盘 / 记忆</span>
        <button type="button" onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-rose-100 hover:text-rose-600">
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-auto p-3">
        <button
          type="button"
          disabled={running || (chapter.word_count ?? 0) === 0}
          onClick={() => void runDebrief()}
          className={clsx(
            'flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold text-white',
            running || (chapter.word_count ?? 0) === 0 ? 'bg-rose-300' : 'bg-rose-500 hover:bg-rose-600',
          )}
        >
          {running ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {running ? '复盘中（提取图事实+记忆）…' : '复盘本章（可重跑，幂等）'}
        </button>
        {(chapter.word_count ?? 0) === 0 && (
          <p className="text-[11px] text-gray-400">本章还没有正文，写完后再复盘。</p>
        )}

        {result && (
          <div className="space-y-1.5 rounded-xl border border-rose-100 bg-white p-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
              <Network size={13} className="text-rose-400" />
              本次复盘结果
            </div>
            {graphBadge && (
              <span className={clsx('inline-block rounded-md border px-1.5 py-0.5 text-[10px]', graphBadge.cls)}>
                {graphBadge.text}
                {result.graph_sync?.status === 'ok' ? `（${result.graph_sync.applied} 条边）` : ''}
              </span>
            )}
            <p className="text-[11px] text-gray-600">
              图事实 {result.graph_fact_count} 条 · 新记忆 {result.vector_count} 条
              {result.stale_deleted > 0 ? ` · 覆盖旧记忆 ${result.stale_deleted} 条` : ''}
            </p>
            {(result.warnings ?? []).map((w, i) => (
              <p key={i} className="text-[11px] text-amber-700">⚠ {w}</p>
            ))}
          </div>
        )}

        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <span className="flex-1 text-xs font-semibold text-gray-700">本章记忆（{memories.length}）</span>
            <button
              type="button"
              onClick={() => void loadMemories()}
              className="rounded p-1 text-gray-400 hover:bg-rose-100 hover:text-rose-600"
              title="刷新"
            >
              <RefreshCw size={12} className={loadingMem ? 'animate-spin' : ''} />
            </button>
          </div>
          {memories.length === 0 ? (
            <p className="rounded-lg border border-dashed border-gray-200 px-3 py-4 text-center text-[11px] text-gray-400">
              {loadingMem ? '加载中…' : '尚无记忆，复盘后这里会显示提取的事件/状态'}
            </p>
          ) : (
            memories.map(m => (
              <div key={m.id} className="rounded-lg border border-gray-100 bg-white px-2.5 py-2">
                <div className="flex items-center gap-1.5">
                  <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-gray-800">
                    {m.title || '（无标题）'}
                  </span>
                  <span className="shrink-0 rounded bg-rose-50 px-1 text-[10px] text-rose-500">
                    {m.memory_type}
                  </span>
                </div>
                <p className="mt-0.5 line-clamp-3 text-[11px] leading-relaxed text-gray-500">{m.content}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
