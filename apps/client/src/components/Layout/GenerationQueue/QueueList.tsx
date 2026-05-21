/**
 * @file 展开态任务列表
 */
import { ChevronDown, ListTodo } from 'lucide-react'
import type { GenTask } from '../../../types'
import { TaskCard } from './TaskCard'

export interface QueueListProps {
  genQueue: GenTask[]
  runningCount: number
  hasRunning: boolean
  onClose: () => void
  onRemove: (taskId: string) => void
  onCancel: (task: GenTask) => void
  onRetry: (taskId: string) => void
}

export function QueueList({
  genQueue,
  runningCount,
  hasRunning,
  onClose,
  onRemove,
  onCancel,
  onRetry,
}: QueueListProps) {
  return (
    <div className="w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50">
        <ListTodo size={14} className="text-gray-500" />
        <span className="text-xs font-semibold text-gray-700 flex-1">AI 任务队列</span>
        {hasRunning && (
          <span className="text-[10px] text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded-full font-medium">
            {runningCount} 进行中
          </span>
        )}
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 p-0.5 rounded"
        >
          <ChevronDown size={14} />
        </button>
      </div>

      <div className="px-3 py-3 space-y-2 max-h-96 overflow-y-auto">
        {genQueue.map(task => (
          <TaskCard
            key={task.id}
            task={task}
            onRemove={() => onRemove(task.id)}
            onCancel={() => onCancel(task)}
            onRetry={() => onRetry(task.id)}
          />
        ))}
      </div>
    </div>
  )
}
