/**
 * @file VolumeLinterPanel.tsx
 * @description 卷节点章纲 linter 结果展示（读 volume.extra.linter_*）。
 */

import React, { useState } from 'react'
import { AlertTriangle, CheckCircle, Loader2, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { outlineApi } from '../../api/client'
import type { OutlineNode } from '../../types'

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
}

const STATUS_STYLE: Record<string, string> = {
  ok: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  warn: 'text-amber-700 bg-amber-50 border-amber-200',
  failed: 'text-red-700 bg-red-50 border-red-200',
}

const VolumeLinterPanel: React.FC<Props> = ({
  volumeNode,
  projectId,
  onRelintDone,
  onRequestRepair,
}) => {
  const extra = volumeNode.extra ?? {}
  const status = (extra.linter_status as string) || 'unknown'
  const summary = (extra.linter_summary as LinterSummary) || {}
  const issues = (extra.linter_issues as LinterIssueRow[]) || []

  const [running, setRunning] = useState(false)
  const [localReport, setLocalReport] = useState<LinterReport | null>(null)

  const displayStatus = localReport?.status ?? status
  const displayIssues = localReport?.issues ?? issues
  const issueCount = localReport?.issue_count ?? summary.issue_count ?? displayIssues.length
  const criticalCount = localReport?.critical_count ?? summary.critical_count ?? 0
  const highCount = localReport?.high_count ?? summary.high_count ?? 0

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
    .filter((i) => i.severity === 'critical' || i.severity === 'high')
    .map((i) => i.chapter_number_in_volume)
    .filter((n): n is number => typeof n === 'number')

  const topIssues = displayIssues
    .filter((i) => ['critical', 'high', 'medium'].includes(i.severity))
    .slice(0, 12)

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
    <Panel>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span
          className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded border',
            STATUS_STYLE[displayStatus] ?? 'text-gray-600 bg-gray-50 border-gray-200'
          )}
        >
          {displayStatus === 'ok' ? (
            <CheckCircle size={12} className="inline mr-1" />
          ) : (
            <AlertTriangle size={12} className="inline mr-1" />
          )}
          linter · {displayStatus}
        </span>
        <button
          type="button"
          disabled={running}
          onClick={handleRelint}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-indigo-600"
        >
          {running ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
          重新检测
        </button>
      </div>

      <p className="text-[11px] text-gray-500 mb-2">
        共 {issueCount} 项 · critical {criticalCount} · high {highCount}
      </p>

      {topIssues.length > 0 ? (
        <ul className="space-y-1 max-h-40 overflow-y-auto text-[11px]">
          {topIssues.map((issue, idx) => (
            <li key={`${issue.rule_id}-${idx}`} className="text-gray-700 leading-snug">
              <span
                className={clsx(
                  'font-mono text-[10px] mr-1',
                  issue.severity === 'critical' && 'text-red-600',
                  issue.severity === 'high' && 'text-amber-600',
                  issue.severity === 'medium' && 'text-gray-500'
                )}
              >
                [{issue.rule_id}]
              </span>
              {issue.chapter_number_in_volume != null && (
                <span className="text-gray-400">第{issue.chapter_number_in_volume}章 · </span>
              )}
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-emerald-600">未发现 critical/high/medium 问题。</p>
      )}

      {onRequestRepair && mustFix.length > 0 && displayStatus !== 'ok' && (
        <button
          type="button"
          className="mt-3 text-xs px-2 py-1 rounded bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100"
          onClick={() => onRequestRepair([...new Set(mustFix)])}
        >
          按 linter 建议发起卷级修复（{mustFix.length} 章）
        </button>
      )}
    </Panel>
  )
}

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
