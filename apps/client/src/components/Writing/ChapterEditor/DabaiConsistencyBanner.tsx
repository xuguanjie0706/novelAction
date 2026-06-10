/**
 * dabai 质检横幅 v2：规则一致性（阻断/提醒）+ LLM 衔接/五拍/钩子分数与建议。
 * 兼容旧报告（无 llm 字段时只渲染规则部分）。
 */
import { AlertTriangle, Lightbulb, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'

interface DabaiQualityLlm {
  continuity_score?: number
  beat_score?: number
  hook_score?: number
  suggestions?: string[]
}

interface DabaiConsistencyReport {
  consistency_pass?: boolean
  status?: string
  overall_score?: number
  blockers?: { rule_id: string; message: string }[]
  warnings?: { rule_id: string; message: string }[]
  llm?: DabaiQualityLlm
  llm_status?: string
}

function scoreCls(v: number): string {
  if (v >= 80) return 'text-emerald-700 bg-emerald-50 border-emerald-200'
  if (v >= 60) return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-rose-700 bg-rose-50 border-rose-200'
}

function ScoreChip({ label, value }: { label: string; value?: number }) {
  if (typeof value !== 'number') return null
  return (
    <span className={clsx('rounded-md border px-1.5 py-0.5 text-[10px] tabular-nums', scoreCls(value))}>
      {label} {value}
    </span>
  )
}

export default function DabaiConsistencyBanner({
  report,
}: {
  report: DabaiConsistencyReport | null | undefined
}) {
  if (!report || report.consistency_pass === undefined) return null
  const blockers = report.blockers ?? []
  const warnings = report.warnings ?? []
  const llm = report.llm
  const suggestions = llm?.suggestions ?? []

  const scoreRow = llm ? (
    <div className="flex flex-wrap items-center gap-1.5">
      <ScoreChip label="衔接" value={llm.continuity_score} />
      <ScoreChip label="五拍" value={llm.beat_score} />
      <ScoreChip label="钩子" value={llm.hook_score} />
      {typeof report.overall_score === 'number' && (
        <span className="text-[10px] text-gray-400 tabular-nums">综合 {report.overall_score}</span>
      )}
    </div>
  ) : null

  if (!blockers.length && !warnings.length) {
    return (
      <div className="space-y-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-emerald-800">
          <ShieldCheck size={14} />
          质检通过
          {report.llm_status && report.llm_status !== 'ok' && (
            <span className="text-[10px] text-emerald-600/70">
              （LLM 质检{report.llm_status === 'skipped' ? '未启用' : '降级'}，仅规则校验）
            </span>
          )}
        </div>
        {scoreRow}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {scoreRow && (
        <div className="rounded-lg border border-gray-200 bg-white px-3 py-2">{scoreRow}</div>
      )}
      {blockers.map((b) => (
        <div key={b.rule_id + b.message} className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800 flex gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span><strong>{b.rule_id}</strong> {b.message}</span>
        </div>
      ))}
      {warnings.map((w) => (
        <div key={w.rule_id + w.message} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span><strong>{w.rule_id}</strong> {w.message}</span>
        </div>
      ))}
      {suggestions.length > 0 && (
        <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
          <div className="mb-1 flex items-center gap-1.5 font-medium">
            <Lightbulb size={13} />
            修改建议
          </div>
          <ul className="list-disc space-y-0.5 pl-4">
            {suggestions.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
