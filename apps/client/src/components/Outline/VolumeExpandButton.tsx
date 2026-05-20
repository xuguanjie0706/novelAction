/**
 * @file VolumeExpandButton.tsx
 * @description 卷节点专属的"展开章纲"按钮 + 内联 SSE 进度面板。
 *
 * 职责：
 * - 展示当前卷已有多少章节计划（徽章）。
 * - 无章节计划时显示"展开章纲"按钮；有章节计划时通过 hover 菜单提供"重新生成"入口。
 * - 点击后通过 SSE 实时展示生成进度，完成后调用 onExpanded 刷新大纲树。
 * - 所有 UI 状态（展开中、进度消息）为组件内 local state，不污染 Zustand store。
 *
 * 数据来源：
 * - volumeNode.children 用于计算已有章节计划数。
 * - aiBackendRoute 来自父组件从 useAppStore 读取的 aiBackendRoute。
 */

import React, { useState, useRef } from 'react'
import { BookOpen, Loader2, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { outlineApi } from '../../api/client'
import { modelProfileFromRoute, llmProviderIdFromRoute } from '../../store'
import type { OutlineNode } from '../../types'

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ProgressLine {
  /** SSE event 名称，用于图标和颜色区分 */
  event: string
  /** 展示给用户的描述 */
  label: string
}

interface Props {
  /** 目标卷节点（node_type 必须为 "volume"） */
  volumeNode: OutlineNode
  /** 项目 UUID */
  projectId: string
  /**
   * 全局 AI 线路字符串（来自 useAppStore.aiBackendRoute）。
   * 格式：`local` | `remote` | `remote:<uuid>`
   */
  aiBackendRoute: string
  /** 章纲生成完成后的回调，父组件在此处刷新大纲树 */
  onExpanded: () => void
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

/** SSE event → 中文标签 */
const EVENT_LABEL: Record<string, string> = {
  step_start:    '开始生成章节计划…',
  context_ready: '已读取已写上下文',
  step_done:     '章节计划生成完成',
  error:         '生成失败',
  end:           '完成',
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

/**
 * 卷节点展开按钮，内嵌 SSE 进度展示。
 *
 * @param volumeNode    - 目标卷节点。
 * @param projectId     - 所属项目 UUID。
 * @param aiBackendRoute - 全局 AI 线路。
 * @param onExpanded    - 生成成功后刷新大纲树的回调。
 */
const VolumeExpandButton: React.FC<Props> = ({
  volumeNode,
  projectId,
  aiBackendRoute,
  onExpanded,
}) => {
  // ── 衍生数据 ───────────────────────────────────────────────────────────────
  const chapterPlanCount = (volumeNode.children ?? []).filter(
    (c) => c.node_type === 'chapter_plan'
  ).length

  const hasChapterPlans = chapterPlanCount > 0

  // ── 状态 ───────────────────────────────────────────────────────────────────
  const [running, setRunning]     = useState(false)
  const [progress, setProgress]   = useState<ProgressLine[]>([])
  const [panelOpen, setPanelOpen] = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [done, setDone]           = useState(false)

  /** 用于强制中止 fetch */
  const abortRef = useRef<AbortController | null>(null)

  // ── 工具 ───────────────────────────────────────────────────────────────────

  const appendProgress = (event: string, extra?: string) => {
    const label = extra
      ? `${EVENT_LABEL[event] ?? event}${extra}`
      : (EVENT_LABEL[event] ?? event)
    setProgress((prev) => [...prev, { event, label }])
  }

  // ── SSE 执行 ───────────────────────────────────────────────────────────────

  /**
   * 调用后端 SSE 接口，消费进度流。
   *
   * @param force - 是否强制覆盖已有章节计划（对应后端 force 参数）。
   */
  const handleExpand = async (force = false) => {
    if (running) return
    setRunning(true)
    setPanelOpen(true)
    setProgress([])
    setError(null)
    setDone(false)

    const modelProfile = modelProfileFromRoute(aiBackendRoute)
    const llmProviderId = llmProviderIdFromRoute(aiBackendRoute)

    const url = outlineApi.expandVolChaptersUrl(projectId, volumeNode.id)
    const body = JSON.stringify({
      model_profile: modelProfile,
      llm_provider_id: llmProviderId ?? null,
      force,
    })

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: ctrl.signal,
      })

      if (!resp.ok) {
        const text = await resp.text()
        // 409 是幂等保护：已有章节计划
        if (resp.status === 409) {
          setError(`该卷已有章节计划（${chapterPlanCount} 章）。如需重新生成，请点击"重新生成"。`)
        } else {
          setError(`请求失败 ${resp.status}: ${text}`)
        }
        setRunning(false)
        return
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const payload = JSON.parse(line.slice(6))
            const evt: string = payload.event ?? ''

            if (evt === 'step_done') {
              const count: number = payload.chapter_count ?? 0
              const linterStatus: string = payload.linter_status ?? 'ok'
              const linterIssues: number = payload.linter_issue_count ?? 0
              const blocked: boolean = Boolean(payload.linter_blocked)
              let suffix = blocked
                ? `，生成 ${count} 章但落库被 linter 阻断`
                : `，共生成 ${count} 章`
              if (!blocked && linterStatus !== 'ok' && linterIssues > 0) {
                suffix += ` · linter ${linterStatus}（${linterIssues} 项）`
              }
              appendProgress(evt, suffix)
              if (blocked) {
                setError(
                  '存在 critical 章纲问题，未写入数据库。请打开卷详情「章纲检测」处理后重新展开。'
                )
              }
              setDone(!blocked)
              onExpanded()
            } else if (evt === 'context_ready') {
              const w: number = payload.written_count ?? 0
              const p: number = payload.promise_count ?? 0
              const m: number = payload.memory_count ?? 0
              appendProgress(evt, `（已写${w}章摘要 / ${p}条承诺 / ${m}条记忆）`)
            } else if (evt === 'error') {
              setError(payload.message ?? '未知错误')
              appendProgress('error', `: ${payload.message ?? ''}`)
            } else if (evt !== 'end') {
              appendProgress(evt)
            }
          } catch {
            // 忽略非 JSON 行
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
      }
    } finally {
      setRunning(false)
    }
  }

  // ── 渲染 ───────────────────────────────────────────────────────────────────

  return (
    <span
      className="inline-flex items-center gap-1 shrink-0"
      onClick={(e) => e.stopPropagation()}
    >
      {/* 章节计划徽章 / 展开按钮 */}
      {hasChapterPlans ? (
        <span className="flex items-center gap-1">
          <span className="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full font-medium">
            ✓ {chapterPlanCount}章
          </span>
          {volumeNode.extra?.linter_status && volumeNode.extra.linter_status !== 'ok' && (
            <span
              className="text-[10px] text-amber-700 bg-amber-50 px-1 py-0.5 rounded-full"
              title="章纲 linter 有问题，点开卷详情查看"
            >
              ⚠
            </span>
          )}
          <button
            title="重新生成章纲（会覆盖已有）"
            disabled={running}
            onClick={() => handleExpand(true)}
            className={clsx(
              'p-0.5 rounded text-gray-300 hover:text-amber-500 hover:bg-amber-50 transition-colors',
              running && 'opacity-50 cursor-not-allowed'
            )}
          >
            <RefreshCw size={10} />
          </button>
        </span>
      ) : (
        <button
          title="展开本卷章节计划"
          disabled={running}
          onClick={() => handleExpand(false)}
          className={clsx(
            'flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded',
            'bg-amber-50 text-amber-600 hover:bg-amber-100 transition-colors font-medium',
            running && 'opacity-60 cursor-not-allowed'
          )}
        >
          {running ? (
            <Loader2 size={9} className="animate-spin" />
          ) : (
            <BookOpen size={9} />
          )}
          {running ? '生成中' : '展开章纲'}
        </button>
      )}

      {/* 内联进度面板 */}
      {panelOpen && (
        <span
          className={clsx(
            'absolute left-0 right-0 z-20 mt-1 mx-2 p-2 rounded-lg border shadow-sm text-[11px]',
            'bg-white border-gray-200'
          )}
          style={{ top: '100%' }}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-gray-700">
              {volumeNode.title} · 章纲生成
            </span>
            <button
              className="text-gray-400 hover:text-gray-600 text-[10px]"
              onClick={() => {
                if (running) abortRef.current?.abort()
                setPanelOpen(false)
              }}
            >
              {running ? '取消' : '关闭'}
            </button>
          </div>

          <div className="space-y-0.5 max-h-28 overflow-y-auto">
            {progress.map((line, i) => (
              <div key={i} className={clsx('flex items-center gap-1', {
                'text-emerald-600': line.event === 'step_done',
                'text-red-500':     line.event === 'error',
                'text-gray-500':    !['step_done', 'error'].includes(line.event),
              })}>
                {line.event === 'step_done' && <CheckCircle size={10} />}
                {line.event === 'error'     && <AlertCircle size={10} />}
                {!['step_done', 'error'].includes(line.event) && (
                  <span className="w-2.5 inline-block" />
                )}
                {line.label}
              </div>
            ))}
            {running && (
              <div className="flex items-center gap-1 text-amber-500">
                <Loader2 size={10} className="animate-spin" />
                AI 正在规划章节因果链…
              </div>
            )}
          </div>

          {error && (
            <div className="mt-1 text-red-500 text-[10px] leading-tight">{error}</div>
          )}
          {done && !error && (
            <div className="mt-1 text-emerald-600 text-[10px]">
              大纲树已刷新，可展开本卷查看章节计划。
            </div>
          )}
        </span>
      )}
    </span>
  )
}

export default VolumeExpandButton
