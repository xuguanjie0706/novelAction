/**
 * @file ConsistencyContent — Bootstrap 全局一致性扫描结果展示 + AI 修复面板
 *
 * 职责：
 *  - 渲染 consistency_issues 列表，每条可勾选
 *  - 当有选中项时展示「修复面板」（用户提示词输入 + 修复按钮）
 *  - 展示修复结果（成功/跳过/需手动处理）
 *
 * 数据来源：父组件 BootstrapTimelineDetail 通过 props 传入
 *  - issues：Project.extra.consistency_issues 数组
 *  - selectedIndices/onToggle：受控多选状态
 *  - onFixRequest：触发修复 API 调用的回调
 *  - fixState：修复的进行/完成状态
 */

import React, { useState } from 'react'
import { CheckSquare, Square, Wrench, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

export interface AppliedPatch {
  issue_index: number
  entity_type: string
  entity_name: string
  field: string
  old_value: string | null
  new_value: string
  applied: boolean
  reason: string
}

export interface SkippedPatch {
  issue_index: number
  reason: string
  suggestion: string
}

export interface FixResult {
  applied: AppliedPatch[]
  skipped: SkippedPatch[]
  message: string
}

export interface FixState {
  loading: boolean
  result: FixResult | null
  error: string | null
}

interface Props {
  issues: any[]
  stepDoneCount?: number | null
  /** 当前已选中的 issue 序号（受控） */
  selectedIndices: Set<number>
  /** 勾选/取消某条 issue */
  onToggle: (idx: number) => void
  /**
   * 触发修复请求
   * @param indices  - 选中的序号列表
   * @param userPrompt - 用户补充说明
   */
  onFixRequest: (indices: number[], userPrompt: string) => Promise<void>
  fixState: FixState
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function severityColor(s: string): string {
  if (s === 'high' || s === 'critical') return '#ef4444'
  if (s === 'medium') return '#f97316'
  return '#f59e0b'
}

function severityLabel(s: string): string {
  return ({ critical: '严重', high: '严重', medium: '中等', low: '轻微' } as Record<string, string>)[s] ?? s
}

// ---------------------------------------------------------------------------
// ConsistencyContent
// ---------------------------------------------------------------------------

export default function ConsistencyContent({
  issues,
  stepDoneCount,
  selectedIndices,
  onToggle,
  onFixRequest,
  fixState,
}: Props) {
  const [userPrompt, setUserPrompt] = useState('')
  const [showPanel, setShowPanel] = useState(false)
  const n = issues.length
  const sseCount = stepDoneCount != null && stepDoneCount > 0 ? stepDoneCount : 0

  // 修复结果辅助
  const appliedIndices = new Set(fixState.result?.applied.map((a) => a.issue_index) ?? [])
  const skippedIndices = new Set(fixState.result?.skipped.map((s) => s.issue_index) ?? [])

  if (n === 0 && sseCount === 0) {
    return (
      <div className="mb-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2 text-sm text-emerald-600">
          <span className="text-base">✓</span>
          <span>未检测到一致性问题，可直接开始写作</span>
        </div>
      </div>
    )
  }

  if (n === 0 && sseCount > 0) {
    return (
      <div className="mb-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <p className="text-sm text-amber-800">
          已标记 <span className="font-semibold">{sseCount}</span> 处需确认项；若列表仍空白，请刷新后重试。
        </p>
      </div>
    )
  }

  const unfixedCount = issues.filter(
    (iss, i) => !(iss?.status === 'fixed') && !appliedIndices.has(i)
  ).length

  return (
    <>
      {/* 说明文字 */}
      <p className="mb-3 text-sm text-gray-600">
        发现{' '}
        <span className="font-semibold text-amber-600">{issues.length}</span> 处待确认问题，不影响开始写作，建议进入第
        3 章前处理。
        {unfixedCount > 0 && (
          <span className="ml-1 text-gray-400 text-xs">勾选后可 AI 辅助修复</span>
        )}
      </p>

      {/* 问题列表 */}
      {issues.map((issue: any, i: number) => {
        const text = typeof issue === 'string' ? issue : (issue.description || issue.issue || JSON.stringify(issue))
        const sev = issue.severity ?? (i === 0 ? 'high' : i === 1 ? 'medium' : 'low')
        const color = severityColor(sev)
        const isFixed = issue?.status === 'fixed' || appliedIndices.has(i)
        const isSkipped = skippedIndices.has(i)
        const isSelected = selectedIndices.has(i)

        return (
          <div
            key={i}
            className={`mb-2 rounded-lg border bg-white p-3 shadow-sm transition-opacity ${isFixed ? 'opacity-50' : ''}`}
            style={{
              borderColor: isFixed ? '#d1fae5' : 'rgb(243,244,246)',
              borderLeftWidth: 3,
              borderLeftColor: isFixed ? '#10b981' : color,
            }}
          >
            <div className="mb-1 flex items-center gap-2">
              {/* 勾选框（已修复的不可再勾） */}
              {!isFixed && (
                <button
                  type="button"
                  onClick={() => onToggle(i)}
                  className="flex-shrink-0 text-gray-400 hover:text-amber-500 transition-colors"
                  aria-label={isSelected ? '取消选择' : '选择此问题'}
                >
                  {isSelected ? (
                    <CheckSquare size={15} className="text-amber-500" />
                  ) : (
                    <Square size={15} />
                  )}
                </button>
              )}
              {/* 已修复图标 */}
              {isFixed && <CheckCircle2 size={14} className="flex-shrink-0 text-emerald-500" />}

              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                style={{ background: `${color}18`, color }}
              >
                {severityLabel(sev)}
              </span>
              <span className="text-sm font-medium text-gray-900">
                {typeof issue === 'object' ? (issue.title ?? `问题 ${i + 1}`) : `问题 ${i + 1}`}
              </span>
              {isFixed && (
                <span className="ml-auto text-[10px] text-emerald-600 font-medium">已修复</span>
              )}
              {isSkipped && !isFixed && (
                <span className="ml-auto text-[10px] text-orange-500 font-medium flex items-center gap-1">
                  <AlertCircle size={10} /> 需手动处理
                </span>
              )}
            </div>
            <p className="text-xs leading-relaxed text-gray-600 ml-5">{text}</p>
            {issue.suggestion && !isFixed && (
              <p className="mt-2 text-xs text-amber-700 ml-5">▸ {issue.suggestion}</p>
            )}
            {/* 修复详情 */}
            {appliedIndices.has(i) && fixState.result && (() => {
              const patch = fixState.result.applied.find((a) => a.issue_index === i)
              return patch ? (
                <p className="mt-2 text-xs text-emerald-700 ml-5 bg-emerald-50 rounded px-2 py-1">
                  ✓ 已将 {patch.entity_name} 的 {patch.field} 从「{patch.old_value ?? '（空）'}」改为「{patch.new_value}」
                </p>
              ) : null
            })()}
            {skippedIndices.has(i) && fixState.result && (() => {
              const s = fixState.result.skipped.find((sk) => sk.issue_index === i)
              return s ? (
                <p className="mt-2 text-xs text-orange-600 ml-5 bg-orange-50 rounded px-2 py-1">
                  ⚠ {s.reason}{s.suggestion ? `：${s.suggestion}` : ''}
                </p>
              ) : null
            })()}
          </div>
        )
      })}

      {/* 修复面板 */}
      {selectedIndices.size > 0 && !fixState.loading && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 flex items-center gap-2">
            <Wrench size={14} className="text-amber-600" />
            <span className="text-sm font-semibold text-amber-800">
              AI 辅助修复（已选 {selectedIndices.size} 项）
            </span>
            <button
              type="button"
              onClick={() => setShowPanel(!showPanel)}
              className="ml-auto text-xs text-amber-600 underline hover:text-amber-800"
            >
              {showPanel ? '收起' : '展开设置'}
            </button>
          </div>

          {showPanel && (
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="可选：输入修复方向的补充说明，例如「主角姓叶，家族为叶家」…"
              className="mb-3 w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs text-gray-800 placeholder-gray-400 focus:border-amber-400 focus:outline-none resize-none"
              rows={3}
            />
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={fixState.loading}
              onClick={() => void onFixRequest(Array.from(selectedIndices), userPrompt)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-amber-600 disabled:opacity-50 transition-colors"
            >
              <Wrench size={13} />
              确认修复
            </button>
            <span className="text-xs text-amber-700">修复将直接写入人物/势力/技能数据</span>
          </div>
        </div>
      )}

      {/* 修复加载中 */}
      {fixState.loading && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          <Loader2 size={15} className="animate-spin" />
          AI 正在分析并修复数据，请稍候…
        </div>
      )}

      {/* 修复错误 */}
      {fixState.error && !fixState.loading && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
          <span>{fixState.error}</span>
        </div>
      )}

      {/* 修复完成总结 */}
      {fixState.result && !fixState.loading && !fixState.error && (
        <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <span className="font-semibold">修复完成：</span>
          {fixState.result.message}
        </div>
      )}
    </>
  )
}
