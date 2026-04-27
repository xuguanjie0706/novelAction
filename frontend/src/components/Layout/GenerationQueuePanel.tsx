/**
 * GenerationQueuePanel — 右下角悬浮大纲生成队列
 *
 * 特性：
 *  - 固定在右下角，始终可见（有任务时）
 *  - 点击展开/收起任务列表
 *  - 自动执行 pending 任务（full_generate / batch_expand）
 *  - 实时 SSE 进度更新
 *  - 任务完成后触发大纲树刷新
 */

import React, { useEffect, useRef, useCallback } from 'react'
import {
  Loader2, CheckCircle2, AlertCircle, ChevronUp, ChevronDown,
  ListTodo, Sparkles, X, BookOpen,
} from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../store'
import type { GenTask, GenProgressItem } from '../../types'
import {
  fetchOutlineExpandResult,
  commitOutlineExpand,
} from '../../utils/outlineAiExpand'

// ── 任务执行器 ─────────────────────────────────────────────

/** 执行 full_generate 任务，SSE 驱动进度更新 */
async function runFullGenerate(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
) {
  const { projectId, params } = task
  let res: Response
  try {
    res = await fetch(`/api/v1/projects/${projectId}/outline/ai-full-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
      signal,
    })
  } catch (e: any) {
    if (e?.name === 'AbortError') return
    onError(e?.message || '网络请求失败')
    return
  }

  if (!res.ok) {
    onError(`HTTP ${res.status}`)
    return
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          const evt = JSON.parse(raw)
          if (evt.event === 'progress') {
            pushProgress({
              step: evt.step,
              label: evt.label,
              done: !!evt.done,
              error: !!evt.error,
            })
          } else if (evt.event === 'complete') {
            onComplete(evt.message || '生成完成')
          } else if (evt.event === 'error') {
            onError(evt.message || '生成失败')
            return
          }
        } catch { /* ignore parse */ }
      }
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') return
    onError(e?.message || '流读取异常')
  }
}

/** 执行 batch_expand 任务：依次展开每个节点 */
async function runBatchExpand(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
) {
  const { projectId, params } = task
  const nodes: Array<{ id: string; title: string }> = params.nodes ?? []
  const chapterCount: number = params.chapterCount ?? 10
  const modelProfile: 'default' | 'gemini' = params.modelProfile ?? 'default'

  let successCount = 0
  for (let i = 0; i < nodes.length; i++) {
    if (signal.aborted) return
    const node = nodes[i]
    const stepLabel = `${node.title}（${i + 1}/${nodes.length}）`
    pushProgress({ step: i + 1, label: `正在展开 ${stepLabel}…`, done: false, error: false })
    try {
      const result = await fetchOutlineExpandResult(projectId, node.id, chapterCount, modelProfile)
      await commitOutlineExpand(projectId, node.id, result.chapters)
      pushProgress({ step: i + 1, label: `✓ ${stepLabel}，写入 ${result.chapters.length} 章`, done: true, error: false })
      successCount++
    } catch (e: any) {
      if (signal.aborted) return
      pushProgress({ step: i + 1, label: `✗ ${stepLabel} 失败：${e?.message || '未知'}`, done: true, error: true })
    }
  }

  onComplete(`批量展开完成：${successCount}/${nodes.length} 个节点成功`)
}

// ── 单任务卡片 ─────────────────────────────────────────────

function TaskCard({ task, onRemove }: { task: GenTask; onRemove: () => void }) {
  const isRunning = task.status === 'running'
  const isDone = task.status === 'done'
  const isError = task.status === 'error'

  const statusIcon = isRunning ? (
    <Loader2 size={13} className="text-amber-500 animate-spin shrink-0" />
  ) : isDone ? (
    <CheckCircle2 size={13} className="text-green-500 shrink-0" />
  ) : isError ? (
    <AlertCircle size={13} className="text-red-500 shrink-0" />
  ) : (
    <span className="w-3 h-3 rounded-full bg-gray-300 shrink-0" />
  )

  return (
    <div className={clsx(
      'rounded-xl border px-3 py-2.5 text-xs transition-colors',
      isDone ? 'bg-green-50 border-green-200' :
      isError ? 'bg-red-50 border-red-200' :
      isRunning ? 'bg-amber-50 border-amber-200' :
      'bg-gray-50 border-gray-200'
    )}>
      {/* 任务标题行 */}
      <div className="flex items-center gap-1.5 mb-1.5">
        {statusIcon}
        <span className={clsx(
          'flex-1 font-medium truncate',
          isDone ? 'text-green-800' :
          isError ? 'text-red-700' :
          isRunning ? 'text-amber-800' :
          'text-gray-600'
        )}>
          {task.label}
        </span>
        {(isDone || isError) && (
          <button
            onClick={onRemove}
            className="text-gray-400 hover:text-gray-600 p-0.5 rounded"
            title="移除"
          >
            <X size={11} />
          </button>
        )}
      </div>

      {/* 进度条目 */}
      {task.progress.length > 0 && (
        <div className="space-y-1 max-h-32 overflow-y-auto pr-0.5">
          {task.progress.map((p, idx) => (
            <div key={`${p.step}-${idx}`} className={clsx(
              'flex items-start gap-1.5 rounded px-2 py-1',
              p.error ? 'bg-red-100 text-red-700' :
              p.done ? 'bg-green-100 text-green-700' :
              'bg-white text-gray-600'
            )}>
              {p.error ? (
                <AlertCircle size={10} className="shrink-0 mt-0.5" />
              ) : p.done ? (
                <CheckCircle2 size={10} className="shrink-0 mt-0.5" />
              ) : (
                <Loader2 size={10} className="shrink-0 mt-0.5 animate-spin" />
              )}
              <span className="text-[11px] leading-relaxed">{p.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* 完成/错误消息 */}
      {task.completedMsg && (
        <p className="text-[11px] text-green-700 mt-1.5 font-medium">{task.completedMsg}</p>
      )}
      {task.errorMsg && (
        <p className="text-[11px] text-red-700 mt-1.5">{task.errorMsg}</p>
      )}
    </div>
  )
}

// ── 主面板 ────────────────────────────────────────────────

export default function GenerationQueuePanel() {
  const genQueue = useAppStore(s => s.genQueue)
  const genQueueOpen = useAppStore(s => s.genQueueOpen)
  const setGenQueueOpen = useAppStore(s => s.setGenQueueOpen)
  const updateGenTask = useAppStore(s => s.updateGenTask)
  const pushGenProgress = useAppStore(s => s.pushGenProgress)
  const removeGenTask = useAppStore(s => s.removeGenTask)
  const setOutlineNeedsReload = useAppStore(s => s.setOutlineNeedsReload)

  // 避免并发执行：记录正在运行的任务 id
  const runningIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const executeTask = useCallback(async (task: GenTask) => {
    runningIdRef.current = task.id
    const abort = new AbortController()
    abortRef.current = abort

    updateGenTask(task.id, { status: 'running' })

    const pushProgress = (item: GenProgressItem) => pushGenProgress(task.id, item)

    const onComplete = (msg: string) => {
      updateGenTask(task.id, { status: 'done', completedMsg: msg })
      setOutlineNeedsReload(true)
      runningIdRef.current = null
    }

    const onError = (msg: string) => {
      updateGenTask(task.id, { status: 'error', errorMsg: msg })
      runningIdRef.current = null
    }

    if (task.type === 'full_generate') {
      await runFullGenerate(task, pushProgress, onComplete, onError, abort.signal)
    } else {
      await runBatchExpand(task, pushProgress, onComplete, onError, abort.signal)
    }

    // 若仍是 running（onComplete/onError 未被调用），标记完成
    if (runningIdRef.current === task.id) {
      updateGenTask(task.id, { status: 'done', completedMsg: '完成' })
      setOutlineNeedsReload(true)
      runningIdRef.current = null
    }
  }, [updateGenTask, pushGenProgress, setOutlineNeedsReload])

  // 自动调度：有 pending 且无 running 时执行下一个
  useEffect(() => {
    if (runningIdRef.current) return
    const next = genQueue.find(t => t.status === 'pending')
    if (next) {
      executeTask(next)
    }
  }, [genQueue, executeTask])

  // 没有任务时不渲染面板
  if (genQueue.length === 0) return null

  const runningCount = genQueue.filter(t => t.status === 'running' || t.status === 'pending').length
  const hasRunning = runningCount > 0

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
      {/* 展开时的任务列表 */}
      {genQueueOpen && (
        <div className="w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden">
          {/* 面板头 */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50">
            <ListTodo size={14} className="text-gray-500" />
            <span className="text-xs font-semibold text-gray-700 flex-1">大纲生成队列</span>
            {hasRunning && (
              <span className="text-[10px] text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded-full font-medium">
                {runningCount} 进行中
              </span>
            )}
            <button
              onClick={() => setGenQueueOpen(false)}
              className="text-gray-400 hover:text-gray-600 p-0.5 rounded"
            >
              <ChevronDown size={14} />
            </button>
          </div>

          {/* 任务列表 */}
          <div className="px-3 py-3 space-y-2 max-h-96 overflow-y-auto">
            {genQueue.map(task => (
              <TaskCard
                key={task.id}
                task={task}
                onRemove={() => removeGenTask(task.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 悬浮按钮（始终显示） */}
      <button
        onClick={() => setGenQueueOpen(!genQueueOpen)}
        className={clsx(
          'flex items-center gap-2 px-3.5 py-2 rounded-full shadow-lg border transition-all text-xs font-medium',
          hasRunning
            ? 'bg-amber-500 hover:bg-amber-600 text-white border-amber-400'
            : 'bg-white hover:bg-gray-50 text-gray-700 border-gray-200'
        )}
      >
        {hasRunning ? (
          <>
            <Loader2 size={13} className="animate-spin" />
            <span>生成中 {runningCount} 任务</span>
          </>
        ) : (
          <>
            <BookOpen size={13} />
            <span>生成队列</span>
          </>
        )}
        {genQueueOpen
          ? <ChevronDown size={12} />
          : <ChevronUp size={12} />
        }
      </button>
    </div>
  )
}
