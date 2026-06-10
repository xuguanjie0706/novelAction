/**
 * 大白文写作页 — 通用章节质检报告（/ai/quality-check 链路，与 AIPanel 同源）。
 */
import clsx from 'clsx'
import type { QualityReport } from '../../types'

const DIMENSION_LABELS: Record<string, string> = {
  plot: '情节',
  character: '人物',
  setting_consistency: '设定一致性',
  pacing: '节奏',
  hooks: '悬念',
  outline_alignment: '大纲对齐',
  face_slap_payoff: '打脸兑现',
  emotional_resonance: '情感共鸣',
  subscribe_intent: '追读意愿',
  storyline_progress: '故事线推进',
  realm_check: '境界体系',
  readability: '可读性',
}

function scoreColor(score: number): string {
  if (score >= 8) return 'text-emerald-600'
  if (score >= 6) return 'text-amber-600'
  return 'text-rose-600'
}

function statusBadge(status: string): string {
  if (status === 'excellent' || status === 'pass') return 'bg-emerald-100 text-emerald-800'
  if (status === 'warning') return 'bg-amber-100 text-amber-800'
  return 'bg-rose-100 text-rose-800'
}

export function isGenericQualityReport(report: unknown): report is QualityReport {
  return !!report && typeof report === 'object' && 'dimensions' in report
}

export default function DabaiWriteQualityBanner({ report }: { report: QualityReport | null | undefined }) {
  if (!report || !isGenericQualityReport(report)) return null
  const score = Number(report.overall_score) || 0
  const dims = Object.entries(report.dimensions || {}).slice(0, 6)
  const suggestions = report.suggestions ?? []

  return (
    <div className="space-y-2 rounded-xl border border-gray-200 bg-gray-50/80 px-3 py-3">
      <div className="flex items-baseline gap-2">
        <span className={clsx('text-2xl font-bold tabular-nums', scoreColor(score))}>
          {score.toFixed(1)}
        </span>
        <span className="text-xs text-gray-400">/ 10</span>
        {report.summary ? (
          <p className="min-w-0 flex-1 text-xs leading-snug text-gray-600">{report.summary}</p>
        ) : null}
      </div>
      {dims.length > 0 && (
        <div className="space-y-1.5">
          {dims.map(([key, dim]) => {
            if (!dim || typeof dim !== 'object') return null
            return (
              <div key={key} className="flex items-start gap-2">
                <span className={clsx('shrink-0 rounded-full px-2 py-0.5 text-[10px] tabular-nums', statusBadge(dim.status))}>
                  {dim.score}
                </span>
                <div className="min-w-0">
                  <div className="text-[11px] font-medium text-gray-700">
                    {DIMENSION_LABELS[key] ?? key}
                  </div>
                  {dim.comment ? (
                    <div className="text-[10px] leading-snug text-gray-500">{dim.comment}</div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}
      {suggestions.length > 0 && (
        <ul className="list-disc space-y-0.5 border-t border-gray-200 pt-2 pl-4 text-[11px] text-gray-600">
          {suggestions.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      )}
    </div>
  )
}
