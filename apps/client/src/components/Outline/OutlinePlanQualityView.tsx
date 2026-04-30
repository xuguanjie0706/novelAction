import React from 'react'
import clsx from 'clsx'
import type { OutlinePlanQualityReport } from '../../types'

function statusBadgeClass(status: string | undefined) {
  const s = (status || '').toLowerCase()
  if (s === 'fail') return 'bg-red-100 text-red-800 border-red-200'
  if (s === 'warning') return 'bg-amber-100 text-amber-900 border-amber-200'
  if (s === 'pass') return 'bg-green-100 text-green-800 border-green-200'
  return 'bg-gray-100 text-gray-700 border-gray-200'
}

function severityLabel(sev: string | undefined) {
  const m = { critical: '致命', high: '高', medium: '中', low: '低' } as Record<string, string>
  return m[sev || ''] || sev || '—'
}

type Props = {
  report: OutlinePlanQualityReport | Record<string, unknown> | null | undefined
  /** minimal：队列内精简；default：大纲页 */
  variant?: 'minimal' | 'default'
  className?: string
  /** 必修章节号点击（大纲页跳转） */
  onChapterClick?: (chapterNumber: number) => void
}

export default function OutlinePlanQualityView({ report, variant = 'default', className, onChapterClick }: Props) {
  if (!report || typeof report !== 'object') return null
  const r = report as OutlinePlanQualityReport
  if (r.error) {
    return (
      <p className={clsx('text-xs text-red-700', className)}>
        质检错误：{String(r.error)}
      </p>
    )
  }

  const must = r.must_fix_chapter_numbers ?? []
  const issues = r.issues ?? []
  const strengths = r.strengths ?? []

  return (
    <div className={clsx('space-y-2 text-xs', className)}>
      <div className="flex flex-wrap items-center gap-2">
        {r.overall_score != null && (
          <span className="font-semibold text-gray-800">总分：{String(r.overall_score)}</span>
        )}
        {r.status && (
          <span className={clsx('px-1.5 py-0.5 rounded border text-[10px] font-medium', statusBadgeClass(r.status))}>
            {r.status}
          </span>
        )}
        {r.scope && <span className="text-gray-400">范围：{r.scope}</span>}
      </div>
      {r.summary && <p className="text-gray-600 leading-relaxed">{r.summary}</p>}
      {must.length > 0 && (
        <div>
          <span className="text-gray-500 font-medium">必修章节：</span>
          <span className="flex flex-wrap gap-1 mt-0.5">
            {must.map((n) =>
              onChapterClick ? (
                <button
                  key={n}
                  type="button"
                  onClick={() => onChapterClick(n)}
                  className="text-[11px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 hover:bg-amber-200 border border-amber-200"
                >
                  第{n}章
                </button>
              ) : (
                <span key={n} className="text-[11px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-100">
                  第{n}章
                </span>
              ),
            )}
          </span>
        </div>
      )}
      {issues.length > 0 && (
        <ul className={clsx('space-y-1.5', variant === 'minimal' && 'max-h-28 overflow-y-auto pr-1')}>
          {issues.slice(0, variant === 'minimal' ? 8 : issues.length).map((issue, i) => (
            <li key={i} className="border border-gray-100 rounded-lg px-2 py-1.5 bg-gray-50/80">
              <div className="flex flex-wrap gap-1 items-center text-[10px] text-gray-500 mb-0.5">
                <span className="font-medium text-gray-600">{severityLabel(issue.severity)}</span>
                {issue.type && <span className="text-gray-400">· {issue.type}</span>}
                {issue.chapter_numbers && issue.chapter_numbers.length > 0 && (
                  <span>· 章 {issue.chapter_numbers.join('、')}</span>
                )}
              </div>
              <p className="text-gray-700 leading-relaxed">{issue.description || '—'}</p>
              {issue.suggested_patch?.replacement ? (
                <p className="text-[10px] text-gray-500 mt-1 whitespace-pre-wrap border-t border-gray-100 pt-1">
                  建议：{issue.suggested_patch.replacement}
                </p>
              ) : null}
            </li>
          ))}
          {variant === 'minimal' && issues.length > 8 && (
            <li className="text-[10px] text-gray-400">…共 {issues.length} 条，详见大纲页</li>
          )}
        </ul>
      )}
      {strengths.length > 0 && variant === 'default' && (
        <div>
          <span className="text-gray-500 font-medium text-[11px]">亮点</span>
          <ul className="list-disc pl-4 mt-1 text-gray-600 space-y-0.5">
            {strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
