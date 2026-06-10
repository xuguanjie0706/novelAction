/**
 * dabai 设定一致性预警（正文写后规则校验，非文采质检）。
 */
import { AlertTriangle, ShieldCheck } from 'lucide-react'

interface DabaiConsistencyReport {
  consistency_pass?: boolean
  status?: string
  blockers?: { rule_id: string; message: string }[]
  warnings?: { rule_id: string; message: string }[]
}

export default function DabaiConsistencyBanner({
  report,
}: {
  report: DabaiConsistencyReport | null | undefined
}) {
  if (!report || report.consistency_pass === undefined) return null
  const blockers = report.blockers ?? []
  const warnings = report.warnings ?? []
  if (!blockers.length && !warnings.length) {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 flex items-center gap-2">
        <ShieldCheck size={14} />
        设定一致性通过
      </div>
    )
  }
  return (
    <div className="space-y-2">
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
    </div>
  )
}
