/**
 * @file VolumeLinterPanel.tsx
 * @description 卷节点章纲 linter 结果展示 + 勾选定向修复（对标 ConsistencyContent）。
 */

import React, { useCallback, useMemo, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  CheckCircle2,
  CheckSquare,
  Loader2,
  RefreshCw,
  ShieldOff,
  Square,
  Wrench,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { outlineApi } from '../../api/client'
import { useAppStore, toOutlineApiModelProfile, routeLlmProviderPayload } from '../../store'
import type { OutlineNode } from '../../types'
import { linterIssueHeading } from './linterDisplay'

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

interface FixApplied {
  issue_index: number
  chapter_number?: number | null
  rule_id?: string
  fields_changed?: string[]
  reason?: string
}

interface FixSkipped {
  issue_index: number
  reason: string
  suggestion?: string
}

interface FixState {
  loading: boolean
  result: { applied: FixApplied[]; skipped: FixSkipped[]; message: string } | null
  error: string | null
}

interface Props {
  volumeNode: OutlineNode
  projectId: string
  onRelintDone?: () => void
  onRequestRepair?: (mustFixChapters: number[]) => void
  onForceAccept?: () => void
}

const STATUS_STYLE: Record<string, string> = {
  ok:     'text-emerald-700 bg-emerald-50 border-emerald-200',
  warn:   'text-amber-700 bg-amber-50 border-amber-200',
  failed: 'text-red-700 bg-red-50 border-red-200',
}

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  high:     'bg-amber-50 text-amber-700 border-amber-200',
  medium:   'bg-gray-50 text-gray-600 border-gray-200',
  low:      'bg-gray-50 text-gray-400 border-gray-200',
}

const FIXABLE_SEVERITIES = new Set(['critical', 'high', 'medium'])

function severityColor(sev: string): string {
  if (sev === 'critical' || sev === 'high') return '#ef4444'
  if (sev === 'medium') return '#f97316'
  return '#f59e0b'
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const VolumeLinterPanel: React.FC<Props> = ({
  volumeNode,
  projectId,
  onRelintDone,
  onRequestRepair,
  onForceAccept,
}) => {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const extra     = volumeNode.extra ?? {}
  const status    = (extra.linter_status as string) || 'unknown'
  const summary   = (extra.linter_summary as LinterSummary) || {}
  const issues    = (extra.linter_issues as LinterIssueRow[]) || []
  const draftHeld = Boolean(extra.linter_blocked)

  const [running, setRunning] = useState(false)
  const [localReport, setLocalReport] = useState<LinterReport | null>(null)
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())
  const [userPrompt, setUserPrompt] = useState('')
  const [showFixPanel, setShowFixPanel] = useState(false)
  const [fixState, setFixState] = useState<FixState>({ loading: false, result: null, error: null })

  const displayStatus = localReport?.status ?? status
  const displayIssues = localReport?.issues ?? issues
  const issueCount    = localReport?.issue_count ?? summary.issue_count ?? displayIssues.length
  const criticalCount = localReport?.critical_count ?? summary.critical_count ?? 0
  const highCount     = localReport?.high_count ?? summary.high_count ?? 0

  const indexedFixable = useMemo(
    () => displayIssues
      .map((issue, index) => ({ issue, index }))
      .filter(({ issue }) => FIXABLE_SEVERITIES.has(issue.severity)),
    [displayIssues],
  )

  const appliedIndices = useMemo(
    () => new Set(fixState.result?.applied.map(a => a.issue_index) ?? []),
    [fixState.result],
  )
  const skippedIndices = useMemo(
    () => new Set(fixState.result?.skipped.map(s => s.issue_index) ?? []),
    [fixState.result],
  )

  const handleRelint = async () => {
    setRunning(true)
    try {
      const data = await outlineApi.lintVolume(projectId, volumeNode.id, true)
      setLocalReport(data)
      setFixState({ loading: false, result: null, error: null })
      onRelintDone?.()
    } finally {
      setRunning(false)
    }
  }

  const handleToggle = useCallback((idx: number) => {
    setSelectedIndices(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }, [])

  const handleFixRequest = async () => {
    const indices = [...selectedIndices]
    if (indices.length === 0) {
      toast.error('请先勾选要修复的问题')
      return
    }
    setFixState({ loading: true, result: null, error: null })
    try {
      const res = await outlineApi.fixLinterIssues(projectId, volumeNode.id, {
        selected_indices: indices,
        user_prompt: userPrompt.trim(),
        model_profile: toOutlineApiModelProfile(aiBackendRoute),
        ...routeLlmProviderPayload(aiBackendRoute),
      })
      setFixState({
        loading: false,
        result: { applied: res.applied, skipped: res.skipped, message: res.message },
        error: null,
      })
      if (res.linter_report) {
        setLocalReport(res.linter_report)
      }
      const fixedSet = new Set(res.applied.map(a => a.issue_index))
      setSelectedIndices(prev => {
        const next = new Set(prev)
        fixedSet.forEach(i => next.delete(i))
        return next
      })
      onRelintDone?.()
      if (res.applied.length > 0) {
        toast.success(res.message || `已修复 ${res.applied.length} 项`)
      } else {
        toast.error('未能自动修复，请调整补充说明后重试')
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail
        ?? (err as Error)?.message
        ?? '修复失败'
      setFixState({ loading: false, result: null, error: String(msg) })
    }
  }

  const mustFixChapters = displayIssues
    .filter(i => i.severity === 'critical' || i.severity === 'high')
    .map(i => i.chapter_number_in_volume)
    .filter((n): n is number => typeof n === 'number')

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
      {/* 状态栏 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded border inline-flex items-center gap-1',
            STATUS_STYLE[displayStatus] ?? 'text-gray-600 bg-gray-50 border-gray-200',
          )}>
            {displayStatus === 'ok'
              ? <CheckCircle size={12} />
              : <AlertTriangle size={12} />}
            章纲质检 · {displayStatus === 'ok' ? '通过' : displayStatus === 'warn' ? '有警告' : displayStatus === 'failed' ? '未通过' : displayStatus}
          </span>
          <span className="text-[11px] text-gray-500">
            共 {issueCount} 项
            {criticalCount > 0 && <span className="ml-1 text-red-600 font-medium">· 严重 {criticalCount}</span>}
            {highCount > 0 && <span className="ml-1 text-amber-600 font-medium">· 较高 {highCount}</span>}
            {draftHeld && <span className="ml-1 text-amber-700"> · 草稿已暂存</span>}
          </span>
        </div>
        <button
          type="button"
          disabled={running || fixState.loading}
          onClick={handleRelint}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-indigo-600 shrink-0"
        >
          {running ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
          重新检测
        </button>
      </div>

      {indexedFixable.length > 0 && (
        <p className="text-[11px] text-gray-500">
          勾选问题后 AI 定向修复（含选择代价等因果链字段），修完自动重检。
        </p>
      )}

      {/* 可勾选问题列表 */}
      {indexedFixable.length > 0 ? (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-0.5">
          {indexedFixable.map(({ issue, index }) => {
            const isFixed = appliedIndices.has(index)
            const isSkipped = skippedIndices.has(index)
            const isSelected = selectedIndices.has(index)
            const color = severityColor(issue.severity)

            return (
              <div
                key={`${issue.rule_id}-${index}`}
                className={clsx(
                  'rounded-lg border bg-white p-2.5 shadow-sm transition-opacity',
                  isFixed && 'opacity-50',
                )}
                style={{
                  borderLeftWidth: 3,
                  borderLeftColor: isFixed ? '#10b981' : color,
                }}
              >
                <div className="flex items-start gap-2">
                  {!isFixed && (
                    <button
                      type="button"
                      onClick={() => handleToggle(index)}
                      className="mt-0.5 shrink-0 text-gray-400 hover:text-amber-500"
                      aria-label={isSelected ? '取消选择' : '选择此问题'}
                    >
                      {isSelected
                        ? <CheckSquare size={14} className="text-amber-500" />
                        : <Square size={14} />}
                    </button>
                  )}
                  {isFixed && <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-500" />}
                  <div className="flex-1 min-w-0 space-y-0.5">
                    <span className={clsx(
                      'inline-block text-[10px] font-medium px-1.5 py-0.5 rounded border',
                      SEVERITY_BADGE[issue.severity] ?? SEVERITY_BADGE.low,
                    )}>
                      {linterIssueHeading(issue)}
                    </span>
                    <p className="text-[11px] text-gray-700 leading-snug">{issue.message}</p>
                    {issue.suggestion && (
                      <p className="text-[10px] text-indigo-600 leading-snug">↳ {issue.suggestion}</p>
                    )}
                    {isSkipped && (
                      <p className="text-[10px] text-amber-700">
                        未自动修复：{fixState.result?.skipped.find(s => s.issue_index === index)?.reason}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : displayStatus === 'ok' ? (
        <p className="text-xs text-emerald-600">未发现需处理的问题。</p>
      ) : (
        <p className="text-xs text-gray-500">仅有轻微项或未记录问题。</p>
      )}

      {/* 修复面板 */}
      {indexedFixable.some(({ index }) => !appliedIndices.has(index)) && (
        <div className="rounded-lg border border-amber-100 bg-amber-50/60 p-3 space-y-2">
          {!showFixPanel ? (
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs font-medium text-amber-800 hover:text-amber-900"
              onClick={() => setShowFixPanel(true)}
            >
              <Wrench size={12} />
              {selectedIndices.size > 0
                ? `修复选中 (${selectedIndices.size})`
                : '展开修复面板'}
            </button>
          ) : (
            <>
              <p className="text-xs font-medium text-amber-900">AI 定向修复</p>
              <textarea
                value={userPrompt}
                onChange={e => setUserPrompt(e.target.value)}
                rows={2}
                placeholder="可选：补充修改方向，如「第7章要让身份暴露的代价落地，第8章开篇承接追兵」"
                className="w-full text-xs border border-amber-200 rounded-lg px-2.5 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-amber-300"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={fixState.loading || selectedIndices.size === 0}
                  onClick={() => void handleFixRequest()}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  {fixState.loading
                    ? <><Loader2 size={11} className="animate-spin" />修复中…</>
                    : <><Wrench size={11} />确认修复 ({selectedIndices.size})</>}
                </button>
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-gray-700"
                  onClick={() => setShowFixPanel(false)}
                >
                  收起
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {fixState.loading && (
        <p className="text-xs text-amber-700 flex items-center gap-1.5">
          <Loader2 size={12} className="animate-spin" />
          AI 正在结合前后章上下文生成修复补丁…
        </p>
      )}

      {fixState.error && (
        <p className="text-xs text-red-600 flex items-center gap-1">
          <AlertCircle size={12} />{fixState.error}
        </p>
      )}

      {fixState.result && (
        <p className="text-xs text-emerald-700">{fixState.result.message}</p>
      )}

      {/* 深度修复 / 强制采用 */}
      {displayStatus !== 'ok' && (onRequestRepair || onForceAccept) && (
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-gray-100">
          {onRequestRepair && mustFixChapters.length > 0 && (
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              onClick={() => onRequestRepair([...new Set(mustFixChapters)])}
              title="整卷 Graph 深度修复（较慢，适合大面积问题）"
            >
              <Wrench size={11} />
              深度修复整卷（{[...new Set(mustFixChapters)].length} 章）
            </button>
          )}
          {onForceAccept && draftHeld && (
            <button
              type="button"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              onClick={onForceAccept}
            >
              <ShieldOff size={11} />强制采用（跳过门控）
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50/80 p-3">{children}</div>
  )
}

export default VolumeLinterPanel
