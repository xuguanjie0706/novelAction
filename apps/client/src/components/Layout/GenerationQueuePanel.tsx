/**
 * GenerationQueuePanel — 右下角悬浮 AI 任务队列
 *
 * 特性：
 *  - 固定在右下角，始终可见（有任务时）
 *  - 点击展开/收起任务列表
 *  - 自动执行 pending 任务（full_generate / batch_expand / continue_chapters / rewrite_chapter）
 *  - 实时 SSE 进度更新
 *  - 任务完成后触发大纲树刷新
 */

import React, { useEffect, useRef, useCallback } from 'react'
import {
  Loader2, CheckCircle2, AlertCircle, ChevronUp, ChevronDown,
  ListTodo, X, BookOpen,
} from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../store'
import type { Chapter, GenTask, GenProgressItem, MemoryChunk } from '../../types'
import { aiApi, chaptersApi } from '../../api/client'
import {
  fetchOutlineExpandResult,
  commitOutlineExpand,
} from '../../utils/outlineAiExpand'
import { autoCommitGeneratedChapterDebrief } from '../../utils/generatedChapterDebrief'

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function plainTextDraftToHtml(s: string) {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

function parseSseDataLine(line: string): { text?: string; error?: string; done?: boolean } | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try { return JSON.parse(raw) } catch { return null }
}

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
  let settled = false
  const wrapComplete = (msg: string) => {
    if (settled) return
    settled = true
    onComplete(msg)
  }
  const wrapError = (msg: string) => {
    if (settled) return
    settled = true
    onError(msg)
  }

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
        let evt: { event?: string; label?: string; step?: number; done?: boolean; error?: boolean; message?: string }
        try {
          evt = JSON.parse(raw)
        } catch {
          continue
        }
        if (evt.event === 'progress') {
          pushProgress({
            step: evt.step ?? 0,
            label: evt.label ?? '',
            done: !!evt.done,
            error: !!evt.error,
          })
        } else if (evt.event === 'complete') {
          wrapComplete(evt.message || '生成完成')
          return
        } else if (evt.event === 'error') {
          wrapError(evt.message || '生成失败')
          return
        }
      }
    }
    if (!settled && !signal.aborted) {
      wrapError('连接已结束，未收到生成完成事件（可能网络中断或后端异常）')
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') return
    wrapError(e?.message || '流读取异常')
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
  const chapterCount: number = params.chapterCount ?? 60
  const modelProfile: 'default' | 'gemini' = params.modelProfile ?? 'default'
  const llmProviderId: string | undefined = params.llm_provider_id

  let successCount = 0
  for (let i = 0; i < nodes.length; i++) {
    if (signal.aborted) {
      onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
      return
    }
    const node = nodes[i]
    const stepLabel = `${node.title}（${i + 1}/${nodes.length}）`
    pushProgress({ step: i + 1, label: `正在展开 ${stepLabel}…`, done: false, error: false })
    try {
      const result = await fetchOutlineExpandResult(
        projectId,
        node.id,
        chapterCount,
        modelProfile,
        llmProviderId,
      )
      await commitOutlineExpand(projectId, node.id, result.chapters)
      pushProgress({ step: i + 1, label: `✓ ${stepLabel}，写入 ${result.chapters.length} 章`, done: true, error: false })
      successCount++
    } catch (e: any) {
      if (signal.aborted) {
        onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
        return
      }
      pushProgress({ step: i + 1, label: `✗ ${stepLabel} 失败：${e?.message || '未知'}`, done: true, error: true })
    }
  }

  if (signal.aborted) {
    onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
    return
  }
  onComplete(`批量展开完成：${successCount}/${nodes.length} 个节点成功`)
}

/** 执行 continue_chapters 任务：从当前章开始逐章续写，并把结果保存回章节正文 */
async function runContinueChapters(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
  upsertChapter: (chapter: Chapter) => void,
  setMemories: (memories: MemoryChunk[]) => void,
) {
  const { projectId, params } = task
  const chapterIds: string[] = Array.isArray(params.chapterIds) ? params.chapterIds : []
  const userPrompt: string = typeof params.userPrompt === 'string' ? params.userPrompt : ''
  const modelProfile: 'local' | 'gemini' = params.modelProfile ?? 'local'
  const llmProviderId: string | undefined = params.llm_provider_id

  let successCount = 0
  for (let i = 0; i < chapterIds.length; i++) {
    if (signal.aborted) {
      onComplete(`已取消（已完成 ${successCount}/${chapterIds.length} 章）`)
      return
    }

    const chapterId = chapterIds[i]
    let chapter: Chapter
    try {
      const chapterRes = await chaptersApi.get(projectId, chapterId)
      chapter = chapterRes.data
    } catch (e: any) {
      pushProgress({ step: i + 1, label: `读取第 ${i + 1} 章失败：${e?.message || '未知错误'}`, done: true, error: true })
      onError(`读取章节失败，已完成 ${successCount}/${chapterIds.length} 章`)
      return
    }

    const stepLabel = `${chapter.title}（${i + 1}/${chapterIds.length}）`
    const phaseStep = (phase: string) => `${i + 1}-${phase}`
    pushProgress({ step: phaseStep('draft'), label: `正在生成正文 ${stepLabel}…`, done: false, error: false })

    let accumulated = ''
    try {
      const res = await fetch(`/api/v1/projects/${projectId}/ai/draft-assist/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapter_id: chapterId,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
          user_prompt: userPrompt.trim() || null,
          replace_existing: false,
        }),
        signal,
      })

      if (!res.ok) throw new Error((await res.text().catch(() => '')).slice(0, 240) || `HTTP ${res.status}`)
      if (!res.body) throw new Error('响应无流式内容')

      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          const parsed = parseSseDataLine(line)
          if (!parsed) continue
          if (parsed.error) throw new Error(parsed.error)
          if (parsed.text) accumulated += parsed.text
        }
      }
      for (const line of buf.split('\n')) {
        const parsed = parseSseDataLine(line)
        if (parsed?.error) throw new Error(parsed.error)
        if (parsed?.text) accumulated += parsed.text
      }

      if (!accumulated.trim()) throw new Error('未收到正文内容')

      pushProgress({ step: phaseStep('draft'), label: `✓ 正文生成完成 ${stepLabel}`, done: true, error: false })
      pushProgress({ step: phaseStep('save'), label: `正在保存 ${stepLabel}…`, done: false, error: false })

      const appendedHtml = plainTextDraftToHtml(accumulated.trim())
      const nextContent = `${chapter.content || ''}${chapter.content ? '\n' : ''}${appendedHtml}`
      const updateRes = await chaptersApi.update(projectId, chapterId, { content: nextContent })
      upsertChapter(updateRes.data)
      pushProgress({ step: phaseStep('save'), label: `✓ ${stepLabel} 已保存`, done: true, error: false })

      pushProgress({ step: phaseStep('quality'), label: `正在质检 ${stepLabel}…`, done: false, error: false })
      try {
        const qualityRes = await aiApi.qualityCheck(projectId, {
          chapter_id: chapterId,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        })
        const score = Number(qualityRes.data?.overall_score)
        pushProgress({
          step: phaseStep('quality'),
          label: Number.isFinite(score) ? `✓ 质检完成：${score.toFixed(1)}/10` : '✓ 质检完成',
          done: true,
          error: false,
        })
        const refreshedChapter = await chaptersApi.get(projectId, chapterId)
        upsertChapter(refreshedChapter.data)
      } catch (e: any) {
        pushProgress({
          step: phaseStep('quality'),
          label: `质检失败，可稍后手动检查：${e?.message || '未知错误'}`,
          done: true,
          error: true,
        })
      }

      pushProgress({ step: phaseStep('debrief'), label: `正在复盘并写入 ChapterIndex ${stepLabel}…`, done: false, error: false })
      try {
        const applied = await autoCommitGeneratedChapterDebrief(projectId, chapterId, modelProfile, llmProviderId)
        const indexLabel = applied.chapterIndexSaved ? 'ChapterIndex 已写入' : 'ChapterIndex 未更新'
        pushProgress({
          step: phaseStep('debrief'),
          label: `✓ 复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${indexLabel}`,
          done: true,
          error: false,
        })
      } catch (e: any) {
        pushProgress({
          step: phaseStep('debrief'),
          label: `自动复盘失败，可稍后手动提交：${e?.message || '未知错误'}`,
          done: true,
          error: true,
        })
      }

      pushProgress({ step: phaseStep('memory'), label: '正在刷新记忆库…', done: false, error: false })
      try {
        const memoriesRes = await aiApi.listMemory(projectId)
        setMemories(memoriesRes.data)
        pushProgress({ step: phaseStep('memory'), label: `✓ 记忆库已刷新：${memoriesRes.data.length} 条`, done: true, error: false })
      } catch (e: any) {
        pushProgress({
          step: phaseStep('memory'),
          label: `记忆库刷新失败：${e?.message || '未知错误'}`,
          done: true,
          error: true,
        })
      }

      pushProgress({ step: phaseStep('done'), label: `✓ ${stepLabel} 流程完成`, done: true, error: false })
      successCount++
    } catch (e: any) {
      if (signal.aborted || e?.name === 'AbortError') {
        onComplete(`已取消（已完成 ${successCount}/${chapterIds.length} 章）`)
        return
      }
      pushProgress({ step: i + 1, label: `✗ ${stepLabel} 失败：${e?.message || '未知错误'}`, done: true, error: true })
      onError(`续写中断：${stepLabel} 失败，已完成 ${successCount}/${chapterIds.length} 章`)
      return
    }
  }

  onComplete(`多章续写完成：${successCount}/${chapterIds.length} 章已保存`)
}

/** 执行 rewrite_chapter 任务：重写单章、替换正文、保存，并尝试自动复盘 */
async function runRewriteChapter(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
  upsertChapter: (chapter: Chapter) => void,
  setMemories: (memories: MemoryChunk[]) => void,
) {
  const { projectId, params } = task
  const chapterId: string | undefined = typeof params.chapterId === 'string' ? params.chapterId : undefined
  const userPrompt: string = typeof params.userPrompt === 'string' ? params.userPrompt : ''
  const modelProfile: 'local' | 'gemini' = params.modelProfile ?? 'local'
  const llmProviderId: string | undefined = params.llm_provider_id

  if (!chapterId) {
    onError('缺少章节 ID')
    return
  }

  pushProgress({ step: 'start', label: '重写任务已开始，正在读取章节…', done: false, error: false })

  let chapter: Chapter
  try {
    const chapterRes = await chaptersApi.get(projectId, chapterId)
    chapter = chapterRes.data
  } catch (e: any) {
    onError(`读取章节失败：${e?.message || '未知错误'}`)
    return
  }

  let accumulated = ''
  try {
    pushProgress({ step: 'draft', label: `正在重写《${chapter.title}》…`, done: false, error: false })
    const res = await fetch(`/api/v1/projects/${projectId}/ai/draft-assist/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chapter_id: chapterId,
        model_profile: modelProfile,
        ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        user_prompt: userPrompt.trim() || null,
        replace_existing: true,
      }),
      signal,
    })

    if (!res.ok) throw new Error((await res.text().catch(() => '')).slice(0, 240) || `HTTP ${res.status}`)
    if (!res.body) throw new Error('响应无流式内容')

    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const parsed = parseSseDataLine(line)
        if (!parsed) continue
        if (parsed.error) throw new Error(parsed.error)
        if (parsed.text) accumulated += parsed.text
      }
    }
    for (const line of buf.split('\n')) {
      const parsed = parseSseDataLine(line)
      if (parsed?.error) throw new Error(parsed.error)
      if (parsed?.text) accumulated += parsed.text
    }

    if (!accumulated.trim()) throw new Error('未收到正文内容')

    pushProgress({ step: 'draft', label: `✓ 《${chapter.title}》重写完成，正在保存…`, done: true, error: false })
    const updateRes = await chaptersApi.update(projectId, chapterId, { content: plainTextDraftToHtml(accumulated.trim()) })
    upsertChapter(updateRes.data)
    pushProgress({ step: 'save', label: '✓ 新正文已替换并保存', done: true, error: false })

    pushProgress({ step: 'quality', label: '正在质检重写后的章节…', done: false, error: false })
    try {
      const qualityRes = await aiApi.qualityCheck(projectId, {
        chapter_id: chapterId,
        model_profile: modelProfile,
        ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
      })
      const score = Number(qualityRes.data?.overall_score)
      pushProgress({
        step: 'quality',
        label: Number.isFinite(score) ? `✓ 质检完成：${score.toFixed(1)}/10` : '✓ 质检完成',
        done: true,
        error: false,
      })
      const refreshedChapter = await chaptersApi.get(projectId, chapterId)
      upsertChapter(refreshedChapter.data)
    } catch (e: any) {
      pushProgress({
        step: 'quality',
        label: `质检失败，可稍后手动检查：${e?.message || '未知错误'}`,
        done: true,
        error: true,
      })
    }

    pushProgress({ step: 'debrief', label: '正在自动复盘人物、故事线、记忆和 ChapterIndex…', done: false, error: false })
    try {
      const applied = await autoCommitGeneratedChapterDebrief(projectId, chapterId, modelProfile, llmProviderId)
      pushProgress({
        step: 'debrief',
        label: `✓ 自动复盘完成：${applied.characterCount} 个人物/${applied.storylineCount} 条故事线/${applied.memoryCount} 条记忆，${applied.chapterIndexSaved ? 'ChapterIndex 已写入' : 'ChapterIndex 未更新'}`,
        done: true,
        error: false,
      })
    } catch (e: any) {
      pushProgress({
        step: 'debrief',
        label: `自动复盘失败，可稍后在复盘面板手动提交：${e?.message || '未知错误'}`,
        done: true,
        error: true,
      })
    }

    pushProgress({ step: 'memory', label: '正在刷新记忆库…', done: false, error: false })
    try {
      const memoriesRes = await aiApi.listMemory(projectId)
      setMemories(memoriesRes.data)
      pushProgress({ step: 'memory', label: `✓ 记忆库已刷新：${memoriesRes.data.length} 条`, done: true, error: false })
    } catch (e: any) {
      pushProgress({
        step: 'memory',
        label: `记忆库刷新失败：${e?.message || '未知错误'}`,
        done: true,
        error: true,
      })
    }

    onComplete(`《${chapter.title}》已重写并保存`)
  } catch (e: any) {
    if (signal.aborted || e?.name === 'AbortError') {
      onComplete('已取消')
      return
    }
    pushProgress({ step: 'error', label: `重写失败：${e?.message || '未知错误'}`, done: true, error: true })
    onError(`重写失败：${e?.message || '未知错误'}`)
  }
}

// ── 单任务卡片 ─────────────────────────────────────────────

function TaskCard({ task, onRemove, onCancel }: { task: GenTask; onRemove: () => void; onCancel: () => void }) {
  const isRunning = task.status === 'running'
  const isPending = task.status === 'pending'
  const isDone = task.status === 'done'
  const isError = task.status === 'error'
  const isCancelled = task.status === 'cancelled'

  const statusIcon = isRunning ? (
    <Loader2 size={13} className="text-amber-500 animate-spin shrink-0" />
  ) : isDone ? (
    <CheckCircle2 size={13} className="text-green-500 shrink-0" />
  ) : isError ? (
    <AlertCircle size={13} className="text-red-500 shrink-0" />
  ) : isCancelled ? (
    <X size={13} className="text-gray-500 shrink-0" />
  ) : (
    <span className="w-3 h-3 rounded-full bg-gray-300 shrink-0" />
  )

  return (
    <div className={clsx(
      'rounded-xl border px-3 py-2.5 text-xs transition-colors',
      isDone ? 'bg-green-50 border-green-200' :
      isError ? 'bg-red-50 border-red-200' :
      isCancelled ? 'bg-gray-50 border-gray-200' :
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
          isCancelled ? 'text-gray-500' :
          isRunning ? 'text-amber-800' :
          'text-gray-600'
        )}>
          {task.label}
        </span>
        {(isRunning || isPending) && (
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-red-500 p-0.5 rounded"
            title="取消任务"
          >
            <X size={11} />
          </button>
        )}
        {(isDone || isError || isCancelled) && (
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
      {isCancelled && (
        <p className="text-[11px] text-gray-500 mt-1.5">已取消</p>
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
  const upsertChapter = useAppStore(s => s.upsertChapter)
  const setMemories = useAppStore(s => s.setMemories)

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
      if (abort.signal.aborted) {
        updateGenTask(task.id, { status: 'cancelled', completedMsg: undefined, errorMsg: undefined })
        runningIdRef.current = null
        return
      }
      updateGenTask(task.id, { status: 'done', completedMsg: msg })
      if (task.type === 'full_generate' || task.type === 'batch_expand') setOutlineNeedsReload(true)
      runningIdRef.current = null
    }

    const onError = (msg: string) => {
      updateGenTask(task.id, { status: 'error', errorMsg: msg })
      runningIdRef.current = null
    }

    if (task.type === 'full_generate') {
      await runFullGenerate(task, pushProgress, onComplete, onError, abort.signal)
    } else if (task.type === 'batch_expand') {
      await runBatchExpand(task, pushProgress, onComplete, onError, abort.signal)
    } else if (task.type === 'continue_chapters') {
      await runContinueChapters(task, pushProgress, onComplete, onError, abort.signal, upsertChapter, setMemories)
    } else if (task.type === 'rewrite_chapter') {
      await runRewriteChapter(task, pushProgress, onComplete, onError, abort.signal, upsertChapter, setMemories)
    } else {
      onError('未知任务类型')
    }

    // 若仍是 running（回调未正确结束任务），标为错误而非假成功
    if (runningIdRef.current === task.id) {
      updateGenTask(task.id, { status: 'error', errorMsg: '任务异常结束（未收到明确完成或失败信号）' })
      runningIdRef.current = null
    }
  }, [updateGenTask, pushGenProgress, setOutlineNeedsReload, upsertChapter, setMemories])

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
            <span className="text-xs font-semibold text-gray-700 flex-1">AI 任务队列</span>
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
                onCancel={() => cancelTask(task)}
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
            <span>执行中 {runningCount} 任务</span>
          </>
        ) : (
          <>
            <BookOpen size={13} />
            <span>AI 队列</span>
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
