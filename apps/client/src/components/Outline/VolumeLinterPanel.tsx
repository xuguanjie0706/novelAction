/**
 * @file VolumeLinterPanel.tsx
 * @description 卷节点章纲 linter 结果展示（读 volume.extra.linter_*）。
 *
 * 职责：
 * - 展示 linter 汇总状态与问题列表（按章节分组）。
 * - 当草稿被质量门控阻断时（draftHeld=true），提供两个操作：
 *     ① 按 linter 建议发起卷级修复
 *     ② 强制采用（onForceAccept）——绕过门控直接启用草稿
 * - 支持「重新检测」按钮触发在线 relint。
 */

import React, { useState } from 'react'
import { AlertTriangle, CheckCircle, Loader2, RefreshCw, ShieldOff, Wrench } from 'lucide-react'
import clsx from 'clsx'
import { outlineApi } from '../../api/client'
import type { OutlineNode } from '../../types'

// ── 类型 ─────────────────────────────────────────────────────────────────────

export interface LinterIssueRow {
  rule_id: string
  severity: string
  scope: string
  message: string
  suggestion?: string
  field?: string
  chapter_number_in_volume?: number | null
}

interface LinterSummary {
  issue_count?: number
  critical_count?: number
  high_count?: number
}

interface LinterReport {
  status: string
  issue_count: number
  critical_count: number
  high_count: number
  issues: LinterIssueRow[]
}

interface Props {
  volumeNode: OutlineNode
  projectId: string
  onRelintDone?: () => void
  onRequestRepair?: (mustFixChapters: number[]) => void
  /**
   * 绕过质量门控，直接将阻断的草稿标记为已接受。
   * 由父层调用 API 清除 linter_blocked 并刷新节点。
   */
  onForceAccept?: () => void
}

// ── 样式常量 ─────────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  ok:     'text-emerald-700 bg-emerald-50 border-emerald-200',
  warn:   'text-amber-700 bg-amber-50 border-amber-200',
  failed: 'text-red-700 bg-red-50 border-red-200',
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'text-red-600',
  high:     'text-amber-600',
  medium:   'text-gray-500',
  low:      'text-gray-400',
}

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  high:     'bg-amber-50 text-amber-700 border-amber-200',
  medium:   'bg-gray-50 text-gray-600 border-gray-200',
  low:      'bg-gray-50 text-gray-400 border-gray-200',
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────

/** 将 issue 列表按章节编号分组；全局规则归入 key=null */
function groupByChapter(issues: LinterIssueRow[]): Map<number | null, LinterIssueRow[]> {
  const map = new Map<number | null, LinterIssueRow[]>()
  for (const issue of issues) {
    const key = issue.chapter_number_in_volume ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(issue)
  }
  return map
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const VolumeLinterPanel: React.FC<Props> = ({
  volumeNode,
  projectId,
  onRelintDone,
  onRequestRepair,
  onForceAccept,
}) => {
  const extra    = volumeNode.extra ?? {}
  const status   = (extra.linter_status as string) || 'unknown'
  const summary  = (extra.linter_summary as LinterSummary) || {}
  const issues   = (extra.linter_issues as LinterIssueRow[]) || []
  const draftHeld = Boolean(extra.linter_blocked)

  const [running,     setRunning]     = useState(false)
  const [localReport, setLocalReport] = useState<LinterReport | null>(null)

  const displayStatus  = localReport?.status  ?? status
  const displayIssues  = localReport?.issues  ?? issues
  const issueCount     = localReport?.issue_count    ?? summary.issue_count    ?? displayIssues.length
  const criticalCount  = localReport?.critical_count ?? summary.critical_count ?? 0
  const highCount      = localReport?.high_count     ?? summary.high_count     ?? 0

  const handleRelint = async () => {
    setRunning(true)
    try {
      const data = await outlineApi.lintVolume(projectId, volumeNode.id, true)
      setLocalReport(data)
      onRelintDone?.()
    } finally {
      setRunning(false)
    }
  }

  const mustFix = displayIssues
    .filter(i => i.severity === 'critical' || i.severity === 'high')
    .map(i => i.chapter_number_in_volume)
    .filter((n): n is number => typeof n === 'number')

  const importantIssues = displayIssues
    .filter(i => ['critical', 'high', 'medium'].includes(i.severity))

  // 按章节分组（全量展示，不截断）
  const grouped = groupByChapter(importantIssues)
  // 全局规则排第一，然后按章节号排序
  const sortedKeys = [...grouped.keys()].sort((a, b) => {
    if (a === null) return -1
    if (b === null) return 1
    return a - b
  })

  // ── 未检测 ──
  if (displayStatus === 'unknown' && displayIssues.length === 0) {
    return (
      <Panel>
        <p className="text-xs text-gray-400">章纲生成后尚未运行 linter。</p>
        <button
          type="button"
          disabled={running}
          onClick={handleRelint}
          className="mt-2 text-xs text-indigo-600 hover:underline disabled:opacity-50"
        >
          {running ? '检测中…' : '立即检测'}
        </button>
      </Panel>
    )
  }

  return (
    <div className="space-y-3">
      {/* ── 状态栏 ── */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded border inline-flex items-center gap-1',
            STATUS_STYLE[displayStatus] ?? 'text-gray-600 bg-gray-50 border-gray-200',
          )}>
            {displayStatus === 'ok'
              ? <CheckCircle size={12} />
              : <AlertTriangle size={12} />}
            linter · {displayStatus}
          </span>
          <span className="text-[11px] text-gray-500">
            共 {issueCount} 项
            {criticalCount > 0 && <span className="ml-1 text-red-600 font-medium">· critical {criticalCount}</span>}
            {highCount     > 0 && <span className="ml-1 text-amber-600 font-medium">· high {highCount}</span>}
            {draftHeld && <span className="ml-1 text-amber-700"> · 草稿已暂存</span>}
          </span>
        </div>
        <button
          type="button"
          disabled={running}
          onClick={handleRelint}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-indigo-600 shrink-0"
        >
          {running ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
          重新检测
        </button>
      </div>

      {/* ── 问题列表（按章节分组） ── */}
      {importantIssues.length > 0 ? (
        <div className="space-y-2 max-h-72 overflow-y-auto pr-0.5">
          {sortedKeys.map(chapterKey => {
            const chIssues = grouped.get(chapterKey)!
            return (
              <div key={chapterKey ?? 'global'} className="rounded-lg border border-gray-100 bg-gray-50/70 overflow-hidden">
                {/* 章节 header */}
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100/70 border-b border-gray-100">
                  <span className="text-[10px] font-semibold text-gray-600">
                    {chapterKey === null ? '全局规则' : `第 ${chapterKey} 章`}
                  </span>
                  <span className="text-[10px] text-gray-400">{chIssues.length} 项</span>
                </div>
                {/* 该章 issues */}
                <ul className="divide-y divide-gray-100">
                  {chIssues.map((issue, idx) => (
                    <li key={`${issue.rule_id}-${idx}`} className="px-3 py-2 space-y-0.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={clsx(
                          'text-[10px] font-mono px-1.5 py-0.5 rounded border',
                          SEVERITY_BADGE[issue.severity] ?? SEVERITY_BADGE.low,
                        )}>
                          {issue.rule_id}
                        </span>
                        <span className={clsx('text-[10px] font-medium uppercase', SEVERITY_COLOR[issue.severity] ?? 'text-gray-400')}>
                          {issue.severity}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-700 leading-snug">{issue.message}</p>
                      {issue.suggestion && (
                        <p className="text-[10px] text-indigo-600 leading-snug">↳ {issue.suggestion}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-xs text-emerald-600">未发现 critical / high / medium 问题。</p>
      )}

      {/* ── 操作按钮区 ── */}
      {displayStatus !== 'ok' && (onRequestRepair || onForceAccept) && (
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-gray-100">
          {onRequestRepair && mustFix.length > 0 && (
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 transition-colors"
              onClick={() => onRequestRepair([...new Set(mustFix)])}
            >
              <Wrench size={11} />
              按 linter 建议修复（{[...new Set(mustFix)].length} 章）
            </button>
          )}
          {onForceAccept && draftHeld && (
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white text-gray-600 border border-gray-200 hover:bg-gray-50 hover:text-gray-800 transition-colors"
              title="跳过质量门控，直接将此次生成的章纲标记为已接受"
              onClick={onForceAccept}
            >
              <ShieldOff size={11} />强制采用（跳过质量门控）
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── 内部布局辅助 ─────────────────────────────────────────────────────────────

function Panel({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={clsx('rounded-lg border border-gray-100 bg-gray-50/80 p-3', className)}>
      {children}
    </div>
  )
}

export default VolumeLinterPanel
