/**
 * @file VolExpandProgressPanel.tsx
 * @description 「展开章纲」中间区域进度面板。
 *
 * 职责：
 * - 在生成期间展示 SSE 步骤日志（running=true）。
 * - 完成后展示成功摘要或 linter 阻断错误，并提示用户切到「章纲检测」Tab。
 * - 提供「关闭」按钮让用户收起面板。
 *
 * 数据来源：
 * - volExpandState 由父层（OutlinePage）通过 useVolExpandBridge 维护并传入。
 */

import React from 'react'
import { CheckCircle2, AlertCircle, Loader2, X } from 'lucide-react'
import clsx from 'clsx'
import type { ProgressLine } from './VolumeExpandButton'

// ── 类型 ─────────────────────────────────────────────────────────────────────

export interface VolExpandState {
  /** 正在展开的卷节点标题（用于面板标题） */
  volumeTitle: string
  /** SSE 流是否仍在运行 */
  running: boolean
  /** 累积进度行 */
  progress: ProgressLine[]
  /** 错误/linter 阻断消息；null 表示无错误 */
  error: string | null
  /** 是否成功落库 */
  done: boolean
  /** 生成章节数 */
  chapterCount: number
}

interface Props {
  state: VolExpandState
  /** 用户点击关闭时通知父层清除状态 */
  onDismiss: () => void
  /** 用户点击「查看检测结果」时跳到 linter tab */
  onViewLinter?: () => void
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

/**
 * 中间区域章纲展开进度面板。
 * 生成中展示实时日志；完成后展示结果摘要，引导用户查看 linter 结果。
 */
const VolExpandProgressPanel: React.FC<Props> = ({ state, onDismiss, onViewLinter }) => {
  const { volumeTitle, running, progress, error, done, chapterCount } = state

  return (
    <div className="mx-6 mt-6 mb-2 rounded-xl border bg-white shadow-sm overflow-hidden">
      {/* 标题栏 */}
      <div className={clsx(
        'flex items-center justify-between px-4 py-3 border-b',
        done && !error  ? 'bg-emerald-50 border-emerald-100' :
        error           ? 'bg-red-50 border-red-100' :
                          'bg-amber-50 border-amber-100',
      )}>
        <div className="flex items-center gap-2 text-sm font-medium">
          {running && <Loader2 size={14} className="animate-spin text-amber-500" />}
          {done && !error && <CheckCircle2 size={14} className="text-emerald-500" />}
          {error && <AlertCircle size={14} className="text-red-500" />}
          <span className={clsx(
            done && !error ? 'text-emerald-700' :
            error          ? 'text-red-700' :
                             'text-amber-700'
          )}>
            {volumeTitle} · 展开章纲
          </span>
        </div>
        <button
          onClick={onDismiss}
          className="text-gray-400 hover:text-gray-600 p-0.5 rounded transition-colors"
          title="关闭"
        >
          <X size={14} />
        </button>
      </div>

      {/* 进度日志 */}
      <div className="px-4 py-3 space-y-1.5 max-h-48 overflow-y-auto">
        {progress.length === 0 && running && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Loader2 size={11} className="animate-spin" />
            正在连接 AI…
          </div>
        )}
        {progress.map((line, i) => (
          <div key={i} className={clsx('flex items-start gap-2 text-xs', {
            'text-emerald-600': line.event === 'step_done',
            'text-red-500':     line.event === 'error',
            'text-blue-600':    line.event === 'context_ready',
            'text-gray-500':    !['step_done', 'error', 'context_ready'].includes(line.event),
          })}>
            <span className="mt-0.5 shrink-0">
              {line.event === 'step_done'     && <CheckCircle2 size={11} />}
              {line.event === 'error'         && <AlertCircle size={11} />}
              {line.event === 'context_ready' && <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400" />}
              {!['step_done', 'error', 'context_ready'].includes(line.event) && (
                <span className="inline-block w-2.5" />
              )}
            </span>
            <span>{line.label}</span>
          </div>
        ))}
        {running && progress.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-amber-500 mt-1">
            <Loader2 size={11} className="animate-spin" />
            AI 正在规划章节因果链…
          </div>
        )}
      </div>

      {/* 结果区域 */}
      {!running && (done || error) && (
        <div className={clsx(
          'px-4 py-3 border-t text-xs flex items-center justify-between gap-3',
          done && !error ? 'bg-emerald-50/60 border-emerald-100' : 'bg-red-50/60 border-red-100',
        )}>
          <span className={done && !error ? 'text-emerald-700' : 'text-red-600'}>
            {done && !error
              ? `✓ 已生成 ${chapterCount} 章节计划，linter 检测结果已就绪`
              : error}
          </span>
          {onViewLinter && (
            <button
              onClick={onViewLinter}
              className={clsx(
                'shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                done && !error
                  ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                  : 'bg-red-600 text-white hover:bg-red-700',
              )}
            >
              查看检测结果
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default VolExpandProgressPanel
