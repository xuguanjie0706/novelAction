/**
 * 质检卡片 — 章节质检报告（规则 + LLM：衔接/五拍/钩子）。
 * 切章时拉最新落库报告；「跑质检」按当前模型线路调用并落库。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Loader2, ShieldCheck } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabQualityReport } from '../../../../types/dabaiLab'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../../store'
import { BEAT_KEYS, BEAT_LABELS } from './labels'

interface Props {
  projectId: string
  chapterId: string
  mock: boolean
  hasContent: boolean
  /** 自增信号：写后自动质检完成后 +1，触发重拉落库报告。 */
  refreshKey: number
}

function scoreColor(v: number): string {
  if (v >= 80) return 'text-emerald-600'
  if (v >= 60) return 'text-amber-600'
  return 'text-rose-600'
}

function ScoreRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-gray-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-gray-100">
        <div
          className={clsx('h-full rounded', value >= 80 ? 'bg-emerald-400' : value >= 60 ? 'bg-amber-400' : 'bg-rose-400')}
          style={{ width: `${Math.max(value, 4)}%` }}
        />
      </div>
      <span className={clsx('w-8 text-right tabular-nums', scoreColor(value))}>{value}</span>
    </div>
  )
}

export default function QualityCard({ projectId, chapterId, mock, hasContent, refreshKey }: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [report, setReport] = useState<DabaiLabQualityReport | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    dabaiLabApi.getQualityReport(projectId, chapterId)
      .then(res => { if (!cancelled) setReport(res.data.report) })
      .catch(() => { if (!cancelled) setReport(null) })
    return () => { cancelled = true }
  }, [projectId, chapterId, refreshKey])

  const run = async () => {
    setRunning(true)
    try {
      const res = await dabaiLabApi.qualityCheck(projectId, chapterId, {
        mock,
        mode: mock ? 'rules' : 'full',
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...(llmProviderIdFromRoute(aiBackendRoute)
          ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
          : {}),
      })
      setReport(res.data)
      toast.success('质检完成')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '质检失败')
    } finally {
      setRunning(false)
    }
  }

  const issues = [...(report?.blockers ?? []), ...(report?.warnings ?? [])]
  const llm = report?.llm

  return (
    <div className="space-y-3 text-xs">
      <button
        type="button"
        disabled={running || !hasContent}
        onClick={() => void run()}
        className={clsx(
          'inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold text-white',
          running || !hasContent ? 'bg-gray-300' : 'bg-emerald-500 hover:bg-emerald-600',
        )}
      >
        {running ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
        {hasContent ? (running ? '质检中…' : '跑质检（衔接/五拍/钩子）') : '本章尚无正文'}
      </button>

      {report ? (
        <>
          <div className="flex items-baseline gap-2">
            <span className={clsx('text-2xl font-bold', scoreColor(report.overall_score ?? 0))}>
              {report.overall_score ?? '—'}
            </span>
            <span className="text-gray-500">
              分 · {{ ok: '通过', warning: '有警告', blocked: '被阻断' }[report.status ?? ''] ?? report.status}
            </span>
            {report.llm_status && report.llm_status !== 'ok' ? (
              <span className="ml-auto rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                LLM {report.llm_status === 'skipped' ? '未启用（仅规则）' : '降级'}
              </span>
            ) : null}
          </div>

          {llm ? (
            <div className="space-y-1.5">
              <ScoreRow label="衔接" value={llm.continuity_score} />
              <ScoreRow label="五拍" value={llm.beat_score} />
              <ScoreRow label="钩子" value={llm.hook_score} />
              <div className="flex flex-wrap gap-1 pt-1">
                {BEAT_KEYS.map(k => {
                  const st = (llm.beats?.[k] ?? 'pass').toLowerCase()
                  return (
                    <span
                      key={k}
                      className={clsx(
                        'rounded px-1.5 py-0.5 text-[10px]',
                        st === 'pass' ? 'bg-emerald-50 text-emerald-700'
                          : st === 'partial' ? 'bg-amber-50 text-amber-700'
                            : 'bg-rose-50 text-rose-700',
                      )}
                    >
                      {BEAT_LABELS[k]}·{st}
                    </span>
                  )
                })}
              </div>
            </div>
          ) : null}

          {issues.length > 0 && (
            <ul className="space-y-1">
              {issues.map((it, i) => (
                <li key={i} className="text-gray-600">
                  <span className="font-mono text-[10px] text-rose-500">[{it.rule_id}]</span> {it.message}
                </li>
              ))}
            </ul>
          )}

          {(llm?.suggestions?.length ?? 0) > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-semibold text-gray-500">修改建议</p>
              <ul className="space-y-1 text-gray-700">
                {llm!.suggestions.map((s, i) => <li key={i}>· {s}</li>)}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="text-gray-400">暂无质检报告</p>
      )}
    </div>
  )
}
