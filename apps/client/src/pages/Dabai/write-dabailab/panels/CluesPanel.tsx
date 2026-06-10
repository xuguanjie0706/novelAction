/**
 * 线索台账 — 钩子/伏笔/承诺的埋设与回收追踪，支持状态筛选与手动纠偏。
 * 数据：GET /dabai/projects/{pid}/clues（复盘自动埋设/回收）+ PATCH 改状态。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { CheckCircle2, Loader2, Milestone, RotateCcw, XCircle } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabClue } from '../../../../types/dabaiLab'
import { CLUE_STATUS_LABELS, CLUE_TYPE_LABELS } from '../side/labels'

interface Props {
  projectId: string
}

const STATUS_FILTERS = ['all', 'open', 'resolved', 'dropped'] as const
type StatusFilter = (typeof STATUS_FILTERS)[number]

const TYPE_BADGE: Record<string, string> = {
  hook: 'bg-rose-50 text-rose-600',
  foreshadow: 'bg-sky-50 text-sky-600',
  promise: 'bg-amber-50 text-amber-700',
}

export default function CluesPanel({ projectId }: Props) {
  const [items, setItems] = useState<DabaiLabClue[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<StatusFilter>('all')

  const refresh = useCallback(() => {
    setLoading(true)
    dabaiLabApi.listClues(projectId)
      .then(res => setItems(res.data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const filtered = useMemo(
    () => items.filter(c => filter === 'all' || c.status === filter),
    [items, filter],
  )
  const openCount = items.filter(c => c.status === 'open').length

  const patch = async (clue: DabaiLabClue, status: 'open' | 'resolved' | 'dropped') => {
    try {
      await dabaiLabApi.patchClue(projectId, clue.id, { status })
      refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Milestone size={16} className="text-sky-500" />
        <h2 className="text-sm font-semibold text-gray-900">线索台账</h2>
        <span className="text-xs text-gray-400">
          {items.length} 条 · {openCount} 条未回收 · 复盘自动维护
        </span>
      </div>

      <div className="flex flex-wrap gap-1">
        {STATUS_FILTERS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(s)}
            className={clsx(
              'rounded-full px-2.5 py-0.5 text-xs',
              filter === s ? 'bg-sky-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200',
            )}
          >
            {s === 'all' ? '全部' : CLUE_STATUS_LABELS[s] ?? s}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 size={14} className="animate-spin" /> 加载中…
        </p>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          暂无线索——复盘已写章节后自动埋设章末钩子/伏笔
        </p>
      ) : (
        <ul className="space-y-2">
          {filtered.map(c => (
            <li key={c.id} className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
              <div className="flex items-center gap-2">
                <span className={clsx('rounded px-1.5 py-0.5 text-[10px]', TYPE_BADGE[c.clue_type] ?? 'bg-gray-100 text-gray-500')}>
                  {CLUE_TYPE_LABELS[c.clue_type] ?? c.clue_type}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-900">{c.title}</span>
                <span
                  className={clsx(
                    'rounded-full px-2 py-0.5 text-[10px]',
                    c.status === 'open' ? 'bg-amber-50 text-amber-700'
                      : c.status === 'resolved' ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-gray-100 text-gray-400',
                  )}
                >
                  {CLUE_STATUS_LABELS[c.status] ?? c.status}
                </span>
              </div>
              {c.description ? <p className="mt-1 text-xs text-gray-600">{c.description}</p> : null}
              <div className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-400">
                <span>
                  第{c.chapter_planted ?? '?'}章埋设
                  {c.chapter_resolved ? ` → 第${c.chapter_resolved}章回收` : ''}
                </span>
                <span className="ml-auto flex gap-1">
                  {c.status === 'open' && (
                    <>
                      <button
                        type="button"
                        onClick={() => void patch(c, 'resolved')}
                        className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-emerald-600 hover:bg-emerald-50"
                      >
                        <CheckCircle2 size={12} /> 标记回收
                      </button>
                      <button
                        type="button"
                        onClick={() => void patch(c, 'dropped')}
                        className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-gray-400 hover:bg-gray-100"
                      >
                        <XCircle size={12} /> 弃用
                      </button>
                    </>
                  )}
                  {c.status !== 'open' && (
                    <button
                      type="button"
                      onClick={() => void patch(c, 'open')}
                      className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-gray-400 hover:bg-gray-100"
                    >
                      <RotateCcw size={12} /> 重新打开
                    </button>
                  )}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
