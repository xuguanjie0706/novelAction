import type { DabaiLinterReport } from '../../../../types/dabai'

interface Props {
  report: DabaiLinterReport
}

export default function LinterPanel({ report }: Props) {
  const status = report?.status ?? 'ok'
  const label = { ok: '通过', warning: '有警告', blocked: '被阻断' }[status] ?? status

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-gray-900">{report?.score ?? 100}</span>
          <span className="text-sm text-gray-500">分 · {label}</span>
          {report?.issue_count != null && (
            <span className="ml-auto text-xs text-gray-400">{report.issue_count} 项问题</span>
          )}
        </div>
      </div>
      {(report.issues?.length ?? 0) > 0 ? (
        <ul className="space-y-2 rounded-xl border border-gray-100 bg-white p-4 text-sm shadow-sm">
          {report.issues!.map((it, i) => (
            <li key={i} className="border-b border-gray-50 pb-2 last:border-0 last:pb-0">
              <span className="font-mono text-xs text-rose-500">[{it.severity}] {it.rule_id}</span>
              <span className="text-gray-600">
                {it.chapter ? ` 第${it.chapter}章` : ' 卷级'}：{it.message}
              </span>
              {it.suggestion ? <p className="mt-0.5 text-xs text-gray-400">{it.suggestion}</p> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-center text-sm text-gray-400">无 linter 问题</p>
      )}
    </div>
  )
}
