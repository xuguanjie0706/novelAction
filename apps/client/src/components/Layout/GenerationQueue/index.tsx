/**
 * GenerationQueuePanel — 右下角悬浮 AI 任务队列
 */
import { Loader2, ChevronUp, ChevronDown, BookOpen } from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../../store'
import { useGenerationQueue } from './useGenerationQueue'
import { QueueList } from './QueueList'

export default function GenerationQueuePanel() {
  const genQueueOpen = useAppStore(s => s.genQueueOpen)
  const aiPanelOpen = useAppStore(s => s.aiPanelOpen)
  const setGenQueueOpen = useAppStore(s => s.setGenQueueOpen)
  const removeGenTask = useAppStore(s => s.removeGenTask)
  const retryGenTask = useAppStore(s => s.retryGenTask)

  const { genQueue, cancelTask, queueAvoidRightDrawer, runningCount, hasRunning } = useGenerationQueue()

  if (genQueue.length === 0) return null

  const rightOffset = queueAvoidRightDrawer
    ? 'calc(min(100vw, 36rem) + 0.5rem)'
    : aiPanelOpen
      ? 'calc(20rem + 0.5rem)'
      : '1rem'

  return (
    <div
      className="fixed bottom-4 z-50 flex flex-col items-end gap-2 transition-all"
      style={{ right: rightOffset }}
    >
      {genQueueOpen && (
        <QueueList
          genQueue={genQueue}
          runningCount={runningCount}
          hasRunning={hasRunning}
          onClose={() => setGenQueueOpen(false)}
          onRemove={removeGenTask}
          onCancel={cancelTask}
          onRetry={retryGenTask}
        />
      )}

      <button
        type="button"
        onClick={() => setGenQueueOpen(!genQueueOpen)}
        className={clsx(
          'flex items-center gap-2 px-3.5 py-2 rounded-full shadow-lg border transition-all text-xs font-medium',
          hasRunning
            ? 'bg-amber-500 hover:bg-amber-600 text-white border-amber-400'
            : 'bg-white hover:bg-gray-50 text-gray-700 border-gray-200',
        )}
      >
        {hasRunning ? (
          <>
            <Loader2 size={13} className="animate-spin" />
            <span>执行中 {runningCount} 任务</span>
          </>
        ) : (
          <>
            <BookOpen size={13} />
            <span>AI 队列</span>
          </>
        )}
        {genQueueOpen ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
      </button>
    </div>
  )
}
