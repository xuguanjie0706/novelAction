import { useState } from 'react'
import { Loader2, RefreshCw, ShieldCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { dabaiApi } from '../../../../api/dabai'
import type { DabaiLinterReport } from '../../../../types/dabai'

interface Props {
  report: DabaiLinterReport
  projectId: string
  onRelinted?: () => void
}

function isPending(report: DabaiLinterReport): boolean {
  return !report?.status || report.status === 'pending'
}

export default function LinterPanel({ report, projectId, onRelinted }: Props) {
  const [running, setRunning] = useState(false)
  const pending = isPending(report)
  const status = report?.status ?? 'pending'
  const label = { ok: '通过', warning: '有警告', blocked: '被阻断', pending: '尚未检测' }[status] ?? status

  const handleRelint = async () => {
    setRunning(true)
    try {
      await dabaiApi.relintOutline(projectId)
      toast.success('卷纲质检完成')
      onRelinted?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '质检失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          {pending ? (
            <ShieldCheck size={28} className="text-gray-300" />
          ) : (
            <span className="text-2xl font-bold text-gray-900">{report.score ?? '—'}</span>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm text-gray-600">
              {pending ? '卷纲质检' : `分 · ${label}`}
            </p>
            {!pending && report.linted_at && (
              <p className="text-xs text-gray-400">
                检测于 {new Date(report.linted_at).toLocaleString()}
                {report.chapter_count != null ? ` · ${report.chapter_count} 章` : ''}
              </p>
            )}
            {pending && (
              <p className="text-xs text-gray-400">
                尚无章纲或尚未跑过质检；展开卷纲后将自动检测，也可手动重检。
              </p>
            )}
          </div>
          {!pending && report.issue_count != null && (
            <span className="text-xs text-gray-400">{report.issue_count} 项问题</span>
          )}
          <button
            type="button"
            onClick={() => void handleRelint()}
            disabled={running}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs text-rose-700 hover:bg-rose-100 disabled:opacity-50"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {running ? '检测中…' : '重新检测'}
          </button>
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
        <p className="text-center text-sm text-gray-400">
          {pending ? '请先展开章纲或点击「重新检测」' : '无 linter 问题'}
        </p>
      )}
    </div>
  )
}
