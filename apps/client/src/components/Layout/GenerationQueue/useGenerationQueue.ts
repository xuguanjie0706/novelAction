/**
 * @file 生成任务队列：调度、执行、取消
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { useAppStore } from '../../../store'
import type { GenTask, GenProgressItem } from '../../../types'
import { projectsApi } from '../../../api/client'
import {
  runBatchExpand,
  runContinueChapters,
  runFullGenerate,
  runGatedRewriteChapter,
  runOutlineQualityCheck,
  runOutlineRepair,
  runRewriteChapter,
} from './runners'

export function useGenerationQueue() {
  const genQueue = useAppStore(s => s.genQueue)
  const setOutlineNeedsReload = useAppStore(s => s.setOutlineNeedsReload)
  const setCurrentProject = useAppStore(s => s.setCurrentProject)
  const updateGenTask = useAppStore(s => s.updateGenTask)
  const pushGenProgress = useAppStore(s => s.pushGenProgress)
  const upsertChapter = useAppStore(s => s.upsertChapter)
  const setMemories = useAppStore(s => s.setMemories)
  const markChapterDebriefCommitted = useAppStore(s => s.markChapterDebriefCommitted)
  const [queueAvoidRightDrawer, setQueueAvoidRightDrawer] = useState(false)

  const runningIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const executeTask = useCallback(async (task: GenTask) => {
    runningIdRef.current = task.id
    const abort = new AbortController()
    abortRef.current = abort

    updateGenTask(task.id, { status: 'running' })

    const pushProgress = (item: GenProgressItem) => pushGenProgress(task.id, item)

    const onComplete = (msg: string) => {
      if (abort.signal.aborted) {
        updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
        runningIdRef.current = null
        return
      }
      updateGenTask(task.id, { status: 'done', completedMsg: msg })
      if (task.type === 'full_generate' || task.type === 'batch_expand' || task.type === 'outline_quality' || task.type === 'outline_repair') {
        setOutlineNeedsReload(true)
      }
      runningIdRef.current = null
    }

    const onError = (msg: string) => {
      updateGenTask(task.id, { status: 'error', errorMsg: msg })
      runningIdRef.current = null
    }

    if (task.type === 'full_generate') {
      const generated = await runFullGenerate(task, pushProgress, onComplete, onError, abort.signal)
      const shouldCheckOutline = generated && !abort.signal.aborted && (task.params.model_profile ?? 'gemini') === 'gemini'
      const checked = shouldCheckOutline ? await runOutlineQualityCheck(task, pushProgress, abort.signal) : false
      if (checked && !abort.signal.aborted) {
        toast.success('大纲质检已写入。请在「大纲」页查看卷/全书报告与必修章节。', { duration: 5000 })
        setOutlineNeedsReload(true)
        try {
          const { data } = await projectsApi.get(task.projectId)
          setCurrentProject(data)
        } catch { /* ignore */ }
      }
    } else if (task.type === 'outline_quality') {
      const checked = await runOutlineQualityCheck(task, pushProgress, abort.signal)
      if (abort.signal.aborted) {
        updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
        runningIdRef.current = null
      } else if (checked) {
        const scope = task.params.scope === 'volume' ? '单卷' : task.params.scope === 'book' ? '全书' : '大纲'
        toast.success(`${scope}质检已写入。`, { duration: 4000 })
        try {
          const { data } = await projectsApi.get(task.projectId)
          setCurrentProject(data)
        } catch { /* ignore */ }
        onComplete(`${scope}质检完成`)
      } else {
        onError('大纲质检失败')
      }
    } else if (task.type === 'outline_repair') {
      const repaired = await runOutlineRepair(task, pushProgress, abort.signal)
      if (abort.signal.aborted) {
        updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
        runningIdRef.current = null
      } else if (repaired) {
        toast.success('大纲修复已应用，并已保存修复前/后快照。', { duration: 5000 })
        try {
          const { data } = await projectsApi.get(task.projectId)
          setCurrentProject(data)
        } catch { /* ignore */ }
        onComplete('大纲修复完成')
      } else {
        onError('大纲修复失败')
      }
    } else if (task.type === 'batch_expand') {
      await runBatchExpand(task, pushProgress, onComplete, onError, abort.signal)
    } else if (task.type === 'continue_chapters') {
      await runContinueChapters(task, pushProgress, onComplete, onError, abort.signal, upsertChapter, setMemories, markChapterDebriefCommitted)
    } else if (task.type === 'rewrite_chapter') {
      await runRewriteChapter(task, pushProgress, onComplete, onError, abort.signal, upsertChapter, setMemories, markChapterDebriefCommitted)
    } else if (task.type === 'gated_rewrite_chapter') {
      await runGatedRewriteChapter(
        task,
        pushProgress,
        onComplete,
        onError,
        abort.signal,
        upsertChapter,
        setMemories,
        markChapterDebriefCommitted,
      )
    } else {
      onError('未知任务类型')
    }

    if (runningIdRef.current === task.id) {
      updateGenTask(task.id, { status: 'error', errorMsg: '任务异常结束（未收到明确完成或失败信号）' })
      runningIdRef.current = null
    }
  }, [
    updateGenTask,
    pushGenProgress,
    setOutlineNeedsReload,
    setCurrentProject,
    upsertChapter,
    setMemories,
    markChapterDebriefCommitted,
  ])

  const cancelTask = useCallback((task: GenTask) => {
    if (task.status === 'pending') {
      updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
      return
    }
    if (task.status === 'running') {
      abortRef.current?.abort()
      updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
      runningIdRef.current = null
    }
  }, [updateGenTask])

  useEffect(() => {
    if (runningIdRef.current) return
    const next = genQueue.find(t => t.status === 'pending')
    if (next) executeTask(next)
  }, [genQueue, executeTask])

  useEffect(() => {
    const onQueueDrawerAvoid = (event: Event) => {
      const custom = event as CustomEvent<boolean>
      setQueueAvoidRightDrawer(!!custom.detail)
    }
    window.addEventListener('queue-drawer-avoid', onQueueDrawerAvoid)
    return () => window.removeEventListener('queue-drawer-avoid', onQueueDrawerAvoid)
  }, [])

  const runningCount = genQueue.filter(t => t.status === 'running' || t.status === 'pending').length
  const hasRunning = runningCount > 0

  return { genQueue, cancelTask, queueAvoidRightDrawer, runningCount, hasRunning }
}
