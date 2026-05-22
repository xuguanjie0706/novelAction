/**
 * @file ChapterLinterBadge.tsx
 * @description 卷章节清单中的 linter 问题徽章：悬停预览（Portal）；展开详情由父层渲染。
 */

import { useCallback, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { LinterIssueRow } from './VolumeLinterPanel'

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  high: 'bg-amber-50 text-amber-700 border-amber-200',
  medium: 'bg-gray-50 text-gray-600 border-gray-200',
  low: 'bg-gray-50 text-gray-400 border-gray-200',
}

const HOVER_PREVIEW_MAX = 4

function IssuePreviewList({ issues }: { issues: LinterIssueRow[] }) {
  return (
    <ul className="space-y-1.5">
      {issues.map((issue, idx) => (
        <li key={`${issue.rule_id}-${idx}`} className="space-y-0.5">
          <div className="flex items-center gap-1 flex-wrap">
            <span
              className={clsx(
                'text-[10px] font-mono px-1 py-0 rounded border',
                SEVERITY_BADGE[issue.severity] ?? SEVERITY_BADGE.low,
              )}
            >
              {issue.rule_id}
            </span>
            <span className="text-[10px] text-gray-400 uppercase">{issue.severity}</span>
          </div>
          <p className="text-[11px] text-gray-700 leading-snug">{issue.message}</p>
          {issue.suggestion && (
            <p className="text-[10px] text-indigo-600 leading-snug">↳ {issue.suggestion}</p>
          )}
        </li>
      ))}
    </ul>
  )
}

interface TriggerProps {
  issues: LinterIssueRow[]
  expanded: boolean
  onToggle: () => void
}

/** 章节标题行内的 linter 徽章（固定宽度；悬停预览走 Portal 避免被列表裁剪）。 */
export function ChapterLinterBadgeTrigger({ issues, expanded, onToggle }: TriggerProps) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [hoverOpen, setHoverOpen] = useState(false)
  const [hoverPos, setHoverPos] = useState<{ top: number; left: number } | null>(null)

  const critical = issues.filter(i => i.severity === 'critical').length
  const hasCritical = critical > 0
  const hoverIssues = issues.slice(0, HOVER_PREVIEW_MAX)
  const hoverMore = issues.length - hoverIssues.length

  const updateHoverPos = useCallback(() => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setHoverPos({ top: r.bottom + 6, left: r.left })
  }, [])

  const openHover = useCallback(() => {
    if (expanded) return
    updateHoverPos()
    setHoverOpen(true)
  }, [expanded, updateHoverPos])

  const closeHover = useCallback(() => setHoverOpen(false), [])

  if (issues.length === 0) return null

  const hoverPortal = hoverOpen && hoverPos && !expanded && typeof document !== 'undefined'
    ? createPortal(
        <div
          className={clsx(
            'fixed z-[200] w-72 rounded-lg border shadow-lg p-2.5 pointer-events-none',
            hasCritical ? 'border-red-100 bg-white' : 'border-amber-100 bg-white',
          )}
          style={{ top: hoverPos.top, left: hoverPos.left }}
          role="tooltip"
        >
          <p className="text-[10px] font-medium text-gray-500 mb-1.5">悬停预览 · 点击展开</p>
          <IssuePreviewList issues={hoverIssues} />
          {hoverMore > 0 && (
            <p className="text-[10px] text-gray-400 mt-1">还有 {hoverMore} 项…</p>
          )}
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`本章 ${issues.length} 项 linter 问题，点击${expanded ? '收起' : '展开'}`}
        onClick={e => {
          e.stopPropagation()
          onToggle()
        }}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            e.stopPropagation()
            onToggle()
          }
        }}
        onMouseEnter={openHover}
        onMouseLeave={closeHover}
        onFocus={openHover}
        onBlur={closeHover}
        className={clsx(
          'inline-flex items-center justify-center gap-0.5 min-w-[1.35rem] h-[1.125rem] px-1 rounded border',
          'text-[10px] cursor-pointer select-none shrink-0',
          hasCritical
            ? 'border-red-200 text-red-600 bg-red-50'
            : 'border-amber-200 text-amber-600 bg-amber-50',
          expanded && (hasCritical ? 'ring-1 ring-red-200' : 'ring-1 ring-amber-200'),
        )}
      >
        <AlertTriangle size={8} className="shrink-0" />
        <span className="tabular-nums leading-none">{issues.length}</span>
      </span>
      {hoverPortal}
    </>
  )
}

/** 章节标题行下方的 linter 详情。 */
export function ChapterLinterIssuePanel({ issues }: { issues: LinterIssueRow[] }) {
  const critical = issues.filter(i => i.severity === 'critical').length
  const hasCritical = critical > 0

  return (
    <div
      className={clsx(
        'rounded-md border px-2.5 py-2',
        hasCritical ? 'border-red-100 bg-red-50/40' : 'border-amber-100 bg-amber-50/50',
      )}
      onClick={e => e.stopPropagation()}
    >
      <p className="text-[10px] font-medium text-gray-600 mb-1.5">
        章纲质检 · {issues.length} 项
        {hasCritical && <span className="text-red-600 ml-1">（含 {critical} 项 critical）</span>}
      </p>
      <IssuePreviewList issues={issues} />
    </div>
  )
}
