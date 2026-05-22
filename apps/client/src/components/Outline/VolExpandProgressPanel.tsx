/**
 * @file VolExpandProgressPanel.tsx
 * @description 「展开章纲」中间区域进度面板。
 *
 * 职责：
 * - 生成期间展示实时 SSE 步骤日志（running=true）。
 * - 生成成功（非阻断）：简短成功条 + "查看检测结果"按钮。
 * - 质量门控阻断（linterBlocked=true）：紧凑的警告条，提供三个操作：
 *     ① 查看 & 修复 → 跳到「质检」Tab
 *     ② 强制采用    → 绕过质量门控直接启用草稿
 *     ③ 关闭        → 仅关闭本面板
 *   不在此面板重复显示完整 linter 错误文本——详情在「质检」Tab 的 VolumeLinterPanel 中。
 * - 真实生成失败：展示错误摘要。
 *
 * 数据来源：
 * - volExpandState 由父层（OutlinePage）通过 useVolExpandBridge 维护并传入。
 */

import React from 'react'
import { CheckCircle2, AlertCircle, AlertTriangle, Loader2, X, Wrench, ShieldOff } from 'lucide-react'
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
  /** 生成成功但被质量门控阻断（区分于真正的生成失败） */
  linterBlocked: boolean
}

interface Props {
  state: VolExpandState
  /** 用户点击关闭时通知父层清除状态 */
  onDismiss: () => void
  /** 用户点击「查看 & 修复」时跳到质检 tab */
  onViewLinter?: () => void
  /**
   * 用户点击「强制采用」——绕过质量门控直接将草稿标记为已接受。
   * 父层负责调用 API 清除 linter_blocked 并刷新节点。
   */
  onForceAccept?: () => void
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

/**
 * 中间区域章纲展开进度面板。
 *
 * 三种终态：
 * - succeeded：绿色成功条（linter 通过）
 * - linterBlocked：黄色警告条 + 三操作按钮（不重复显示详细 linter 文本）
 * - failed：红色错误条 + 简短错误摘要
 */
const VolExpandProgressPanel: React.FC<Props> = ({ state, onDismiss, onViewLinter, onForceAccept }) => {
  const { volumeTitle, running, progress, error, done, chapterCount, linterBlocked } = state

  const succeeded    = done && !error && !linterBlocked && chapterCount > 0
  const reallyFailed = !running && !succeeded && !linterBlocked && Boolean(error || (!done && chapterCount === 0))

  // ── 标题栏颜色 ────────────────────────────────────────────────────────────
  const headerCls = clsx(
    'flex items-center justify-between px-4 py-2.5 border-b',
    succeeded      ? 'bg-emerald-50 border-emerald-100' :
    linterBlocked  ? 'bg-amber-50 border-amber-100' :
    reallyFailed   ? 'bg-red-50 border-red-100' :
                     'bg-gray-50 border-gray-100',
  )

  const titleCls = clsx(
    'text-xs font-medium',
    succeeded     ? 'text-emerald-700' :
    linterBlocked ? 'text-amber-700' :
    reallyFailed  ? 'text-red-700' :
                    'text-gray-600',
  )

  return (
    <div className="mx-6 mt-6 mb-2 rounded-xl border bg-white shadow-sm overflow-hidden">
      {/* 标题栏 */}
      <div className={headerCls}>
        <div className="flex items-center gap-2">
          {running       && <Loader2      size={13} className="animate-spin text-amber-500 shrink-0" />}
          {succeeded     && <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />}
          {linterBlocked && <AlertTriangle size={13} className="text-amber-500 shrink-0" />}
          {reallyFailed  && <AlertCircle  size={13} className="text-red-500 shrink-0" />}
          <span className={titleCls}>{volumeTitle} · 展开章纲</span>
        </div>
        <button
          onClick={onDismiss}
          className="text-gray-400 hover:text-gray-600 p-0.5 rounded transition-colors ml-3 shrink-0"
          title="关闭"
        >
          <X size={13} />
        </button>
      </div>

      {/* 进度日志（生成中或历史步骤） */}
      {(running || progress.length > 0) && (
        <div className="px-4 py-3 space-y-1.5 max-h-40 overflow-y-auto border-b border-gray-50">
          {progress.length === 0 && running && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Loader2 size={11} className="animate-spin" />正在连接 AI…
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
              <Loader2 size={11} className="animate-spin" />AI 正在规划章节因果链…
            </div>
          )}
        </div>
      )}

      {/* 终态区域 */}
      {!running && (succeeded || linterBlocked || reallyFailed) && (
        <div className={clsx(
          'px-4 py-3',
          succeeded     ? 'bg-emerald-50/60' :
          linterBlocked ? 'bg-amber-50/60' :
                          'bg-red-50/60',
        )}>

          {/* ── 成功 ── */}
          {succeeded && (
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-emerald-700">
                ✓ 已生成 {chapterCount} 章节计划，linter 检测结果已就绪
              </span>
              {onViewLinter && (
                <button
                  onClick={onViewLinter}
                  className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
                >
                  查看检测结果
                </button>
              )}
            </div>
          )}

          {/* ── 质量门控阻断 —— 紧凑操作条，不重复完整错误文本 ── */}
          {linterBlocked && (
            <div className="space-y-2.5">
              <p className="text-xs text-amber-800">
                已生成 <span className="font-semibold">{chapterCount}</span> 章草稿，但被质量门控阻断。
                完整问题列表见右侧「质检」Tab。
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {onViewLinter && (
                  <button
                    onClick={onViewLinter}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-600 text-white hover:bg-amber-700 transition-colors"
                  >
                    <Wrench size={11} />查看 &amp; 修复
                  </button>
                )}
                {onForceAccept && (
                  <button
                    onClick={onForceAccept}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white text-amber-700 border border-amber-300 hover:bg-amber-50 transition-colors"
                    title="跳过质量门控，直接将此次生成的章纲标记为已接受"
                  >
                    <ShieldOff size={11} />强制采用
                  </button>
                )}
                <button
                  onClick={onDismiss}
                  className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  稍后处理
                </button>
              </div>
            </div>
          )}

          {/* ── 真实失败 ── */}
          {reallyFailed && (
            <p className="text-xs text-red-600">
              {error || 'AI 未返回有效章纲，请检查模型线路与 API Key 后重试。'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default VolExpandProgressPanel
