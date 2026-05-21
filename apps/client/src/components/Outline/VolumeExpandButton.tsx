/**
 * @file VolumeExpandButton.tsx
 * @description 卷节点专属的"展开章纲"按钮。
 *
 * 职责：
 * - 展示当前卷已有多少章节计划（徽章）。
 * - 无章节计划时显示"展开章纲"按钮；有章节计划时通过 hover 菜单提供"重新生成"入口。
 * - 点击后通过 authFetch + SSE 消费进度流；进度与结果通过回调上报给父层。
 * - 本组件不再渲染任何进度面板 —— 由父层（OutlinePage）在中间区域统一展示。
 *
 * 数据来源：
 * - volumeNode.children 用于计算已有章节计划数。
 * - aiBackendRoute 来自父组件从 useAppStore 读取的 aiBackendRoute。
 */

import React, { useState, useRef } from 'react'
import { BookOpen, Loader2, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { outlineApi } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import { modelProfileFromRoute, llmProviderIdFromRoute } from '../../store'
import type { OutlineNode } from '../../types'

// ── 公共类型（由父层复用） ────────────────────────────────────────────────────

/** 进度面板的单条日志行 */
export interface ProgressLine {
  /** SSE event 名称，用于图标和颜色区分 */
  event: string
  /** 展示给用户的描述 */
  label: string
}

/** onExpandEnd 的结果载荷 */
export interface ExpandEndResult {
  /** 是否成功落库（linter 未阻断） */
  done: boolean
  /** 错误或 linter 阻断消息；成功时为 null */
  error: string | null
  /** 本次生成的章节数 */
  chapterCount: number
}

// ── Props ────────────────────────────────────────────────────────────────────

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
  /**
   * 生成开始时触发，父层可据此自动选中卷节点、切换到中间进度面板。
   * @param volumeNode - 正在展开的卷节点
   */
  onExpandStart?: (volumeNode: OutlineNode) => void
  /**
   * SSE 每步到达时触发，传入迄今为止的所有进度行（追加语义）。
   * @param lines - 当前完整进度列表
   */
  onExpandProgress?: (lines: ProgressLine[]) => void
  /**
   * SSE 流结束（成功或失败）时触发。
   * @param volumeNode - 对应的卷节点
   * @param result     - 结果载荷
   */
  onExpandEnd?: (volumeNode: OutlineNode, result: ExpandEndResult) => void
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
 * 卷节点展开按钮。
 * 点击后触发 SSE 生成；进度通过 onExpandStart / onExpandProgress / onExpandEnd 上报。
 * 本组件不渲染进度面板，保持树栏 UI 简洁。
 */
const VolumeExpandButton: React.FC<Props> = ({
  volumeNode,
  projectId,
  aiBackendRoute,
  onExpanded,
  onExpandStart,
  onExpandProgress,
  onExpandEnd,
}) => {
  // ── 衍生数据 ───────────────────────────────────────────────────────────────
  const chapterPlanCount = (volumeNode.children ?? []).filter(
    (c) => c.node_type === 'chapter_plan'
  ).length
  const hasChapterPlans = chapterPlanCount > 0

  // ── 本地状态（仅按钮 UI 需要） ─────────────────────────────────────────────
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // ── SSE 执行 ───────────────────────────────────────────────────────────────

  /**
   * 调用后端 SSE 接口，消费进度流，通过回调将状态上报给父层。
   * @param force - 是否强制覆盖已有章节计划
   */
  const handleExpand = async (force = false) => {
    if (running) return
    setRunning(true)
    onExpandStart?.(volumeNode)

    const lines: ProgressLine[] = []
    const appendLine = (event: string, extra = '') => {
      const label = extra
        ? `${EVENT_LABEL[event] ?? event}${extra}`
        : (EVENT_LABEL[event] ?? event)
      lines.push({ event, label })
      onExpandProgress?.([...lines])
    }

    const modelProfile  = modelProfileFromRoute(aiBackendRoute)
    const llmProviderId = llmProviderIdFromRoute(aiBackendRoute)
    const url  = outlineApi.expandVolChaptersUrl(projectId, volumeNode.id)
    const body = JSON.stringify({
      model_profile: modelProfile,
      llm_provider_id: llmProviderId ?? null,
      force,
    })

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const resp = await authFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: ctrl.signal,
      })

      if (!resp.ok) {
        const text = await resp.text()
        let msg = `请求失败 ${resp.status}: ${text}`
        if (resp.status === 409) msg = `该卷已有章节计划（${chapterPlanCount} 章）。如需重新生成，请点击"重新生成"。`
        if (resp.status === 401) msg = '登录已过期，请重新登录后再试。'
        onExpandEnd?.(volumeNode, { done: false, error: msg, chapterCount: 0 })
        setRunning(false)
        return
      }

      const reader  = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')
      const decoder = new TextDecoder()
      let buf = ''
      let chapterCount = 0
      let finalDone    = false
      let finalError: string | null = null

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break
        buf += decoder.decode(value, { stream: true })
        const rawLines = buf.split('\n')
        buf = rawLines.pop() ?? ''

        for (const line of rawLines) {
          if (!line.startsWith('data: ')) continue
          try {
            const payload = JSON.parse(line.slice(6))
            const evt: string = payload.event ?? ''

            if (evt === 'step_done') {
              chapterCount = payload.chapter_count ?? 0
              const linterStatus: string = payload.linter_status ?? 'ok'
              const linterIssues: number = payload.linter_issue_count ?? 0
              const blocked: boolean     = Boolean(payload.linter_blocked)
              let suffix = blocked
                ? `，生成 ${chapterCount} 章但被 linter 阻断`
                : `，共生成 ${chapterCount} 章`
              if (!blocked && linterStatus !== 'ok' && linterIssues > 0) {
                suffix += ` · linter ${linterStatus}（${linterIssues} 项）`
              }
              appendLine(evt, suffix)
              if (blocked) {
                finalError =
                  (typeof payload.linter_message === 'string' && payload.linter_message.trim())
                    || '存在 critical 章纲问题，请查看下方章纲检测结果并修复后重新展开。'
              } else {
                finalDone = true
              }
              onExpanded()
            } else if (evt === 'context_ready') {
              const w: number = payload.written_count ?? 0
              const p: number = payload.promise_count ?? 0
              const m: number = payload.memory_count ?? 0
              appendLine(evt, `（已写${w}章摘要 · ${p}条承诺 · ${m}条记忆）`)
            } else if (evt === 'error') {
              finalError = payload.message ?? '未知错误'
              appendLine('error', `: ${finalError}`)
            } else if (evt !== 'end') {
              appendLine(evt)
            }
          } catch {
            // 忽略非 JSON 行
          }
        }
      }

      onExpandEnd?.(volumeNode, { done: finalDone, error: finalError, chapterCount })
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        const msg = err instanceof Error ? err.message : String(err)
        onExpandEnd?.(volumeNode, { done: false, error: msg, chapterCount: 0 })
      }
    } finally {
      setRunning(false)
    }
  }

  // ── 渲染（仅按钮，无内联面板） ─────────────────────────────────────────────

  return (
    <span
      className="inline-flex items-center gap-1 shrink-0"
      onClick={(e) => e.stopPropagation()}
    >
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
            {running
              ? <Loader2 size={10} className="animate-spin" />
              : <RefreshCw size={10} />}
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
          {running ? <Loader2 size={9} className="animate-spin" /> : <BookOpen size={9} />}
          {running ? '生成中' : '展开章纲'}
        </button>
      )}
    </span>
  )
}

export default VolumeExpandButton
