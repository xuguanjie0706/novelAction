/**
 * DabaiInlineProgress — 编辑器内联生成进度。
 * 数据来源：全局 genQueue 中当前章的 rewrite/gated 任务 progress 数组，
 * 不另起 SSE，避免与队列 runner 重复消费流。
 */
import { useMemo } from 'react'
import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { useAppStore } from '../../store'
import type { GenProgressItem, GenTask } from '../../types'

const VISIBLE_ITEMS = 5

function findChapterTask(queue: GenTask[], projectId: string, chapterId: string): GenTask | undefined {
  // 取最新创建的进行中任务；都结束时取最近一条已完成任务（用于展示收尾状态）
  const mine = queue
    .filter(t =>
      t.projectId === projectId
      && (t.type === 'rewrite_chapter' || t.type === 'gated_rewrite_chapter')
      && t.params?.chapterId === chapterId,
    )
    .sort((a, b) => b.createdAt - a.createdAt)
  return mine.find(t => t.status === 'running' || t.status === 'pending') ?? mine[0]
}

function ProgressRow({ item }: { item: GenProgressItem }) {
  return (
    <div className="flex items-start gap-1.5 text-[11px] leading-relaxed">
      {item.error ? (
        <AlertTriangle size={12} className="mt-0.5 shrink-0 text-rose-500" />
      ) : item.done ? (
        <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-500" />
      ) : (
        <Loader2 size={12} className="mt-0.5 shrink-0 animate-spin text-rose-400" />
      )}
      <span className={clsx(
        'min-w-0 flex-1',
        item.error ? 'text-rose-700' : item.done ? 'text-gray-500' : 'text-gray-800 font-medium',
      )}>
        {item.label}
      </span>
    </div>
  )
}

export default function DabaiInlineProgress({
  projectId,
  chapterId,
}: {
  projectId: string
  chapterId: string
}) {
  const genQueue = useAppStore(s => s.genQueue)
  const task = useMemo(
    () => findChapterTask(genQueue, projectId, chapterId),
    [genQueue, projectId, chapterId],
  )

  // 只在「进行中」或「刚出错」时占位；正常完成的历史任务不打扰
  if (!task) return null
  const active = task.status === 'running' || task.status === 'pending'
  if (!active && task.status !== 'error') return null

  const items = (task.progress ?? []).slice(-VISIBLE_ITEMS)

  return (
    <div className={clsx(
      'rounded-xl border px-3 py-2.5 space-y-1.5',
      task.status === 'error'
        ? 'border-rose-200 bg-rose-50/60'
        : 'border-rose-100 bg-rose-50/40',
    )}>
      <div className="flex items-center gap-2 text-xs font-semibold text-rose-800">
        {active ? <Loader2 size={13} className="animate-spin" /> : <AlertTriangle size={13} />}
        <span className="min-w-0 flex-1 truncate">{task.label}</span>
        <span className="text-[10px] font-normal text-rose-400">
          {task.status === 'pending' ? '排队中' : task.status === 'running' ? '生成中' : '失败'}
        </span>
      </div>
      {items.length > 0 && (
        <div className="space-y-1">
          {items.map(item => (
            <ProgressRow key={`${item.progressKey ?? item.step}`} item={item} />
          ))}
        </div>
      )}
      {task.status === 'error' && task.errorMsg && (
        <p className="text-[11px] text-rose-700">{task.errorMsg}</p>
      )}
    </div>
  )
}
