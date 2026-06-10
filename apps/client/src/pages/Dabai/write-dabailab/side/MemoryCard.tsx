/**
 * 记忆卡片 — 本章复盘记忆列表 + 一键复盘（提取记忆与线索并落库，幂等可重跑）。
 */
import { useCallback, useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Brain, Loader2 } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabDebriefResult, DabaiLabMemory } from '../../../../types/dabaiLab'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../../store'
import { MEM_TYPE_LABELS } from './labels'

interface Props {
  projectId: string
  chapterId: string
  mock: boolean
  hasContent: boolean
  /** 自增信号：写后自动复盘完成后 +1，触发重拉本章记忆。 */
  refreshKey: number
}

export default function MemoryCard({ projectId, chapterId, mock, hasContent, refreshKey }: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [items, setItems] = useState<DabaiLabMemory[]>([])
  const [running, setRunning] = useState(false)
  const [lastResult, setLastResult] = useState<DabaiLabDebriefResult | null>(null)

  const refresh = useCallback(() => {
    dabaiLabApi.listMemory(projectId, chapterId)
      .then(res => setItems(res.data.items))
      .catch(() => setItems([]))
  }, [projectId, chapterId])

  useEffect(() => {
    setLastResult(null)
    refresh()
  }, [refresh, refreshKey])

  const debrief = async () => {
    setRunning(true)
    try {
      const res = await dabaiLabApi.debrief(projectId, chapterId, {
        mock,
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...(llmProviderIdFromRoute(aiBackendRoute)
          ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
          : {}),
      })
      setLastResult(res.data)
      toast.success(`复盘完成：${res.data.memory_count} 条记忆`)
      refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '复盘失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-3 text-xs">
      <button
        type="button"
        disabled={running || !hasContent}
        onClick={() => void debrief()}
        className={clsx(
          'inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold text-white',
          running || !hasContent ? 'bg-gray-300' : 'bg-violet-500 hover:bg-violet-600',
        )}
      >
        {running ? <Loader2 size={13} className="animate-spin" /> : <Brain size={13} />}
        {hasContent ? (running ? '复盘中…' : '复盘本章（记忆+线索）') : '本章尚无正文'}
      </button>

      {lastResult ? (
        <div className="rounded-lg bg-violet-50/60 p-2 text-violet-800">
          <p>{lastResult.summary}</p>
          {lastResult.new_clues.length > 0 && (
            <p className="mt-1 text-[11px]">新埋线索：{lastResult.new_clues.join('、')}</p>
          )}
          {lastResult.resolved_clues.length > 0 && (
            <p className="mt-0.5 text-[11px]">回收线索：{lastResult.resolved_clues.join('、')}</p>
          )}
          {(lastResult.asset_changes?.length ?? 0) > 0 && (
            <p className="mt-0.5 text-[11px]">资产：{lastResult.asset_changes!.join('、')}</p>
          )}
          {(lastResult.relation_changes?.length ?? 0) > 0 && (
            <p className="mt-0.5 text-[11px]">关系：{lastResult.relation_changes!.join('、')}</p>
          )}
        </div>
      ) : null}

      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map(m => (
            <li key={m.id} className="rounded-lg border border-gray-100 p-2">
              <div className="mb-1 flex items-center gap-1.5">
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                  {MEM_TYPE_LABELS[m.mem_type] ?? m.mem_type}
                </span>
                <span className="text-[10px] text-amber-500">{'★'.repeat(m.importance)}</span>
                {m.tags.map(t => (
                  <span key={t} className="text-[10px] text-gray-400">#{t}</span>
                ))}
              </div>
              <p className="text-gray-700">{m.content}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-gray-400">本章暂无记忆——复盘后生成</p>
      )}
    </div>
  )
}
