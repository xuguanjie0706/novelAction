/**
 * 质检卡片 — 章节质检报告（规则 + LLM：衔接/五拍/钩子）。
 * 切章时拉最新落库报告；「跑质检」按当前模型线路调用并落库。
 * 「按本章建议重写」：一次 LLM（正文+质检报告）定点修订，完成后自动再跑质检。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Loader2, PenLine, ShieldCheck, Wand2 } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabQualityReport } from '../../../../types/dabaiLab'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../../store'
import {
  canApplyQualityRewrite,
  canQcPatchRewrite,
  formatQualityRewriteInstruction,
} from '../../../../utils/dabaiQualityRewrite'
import { BEAT_KEYS, BEAT_LABELS } from './labels'

interface Props {
  projectId: string
  chapterId: string
  hasContent: boolean
  /** 自增信号：写后自动质检完成后 +1，触发重拉落库报告。 */
  refreshKey: number
  /** 将质检建议填入重写弹窗。 */
  onApplyRewrite?: (instruction: string) => void
  /** 按本章质检建议直接修订（轻上下文，不弹窗）。 */
  onQcPatchRewrite?: () => void
  /** 轻量修订进行中。 */
  qcPatchRunning?: boolean
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

export default function QualityCard({
  projectId, chapterId, hasContent, refreshKey, onApplyRewrite,
  onQcPatchRewrite, qcPatchRunning = false,
}: Props) {
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
        mode: 'full',
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

  const applyRewrite = () => {
    if (!report || !onApplyRewrite) return
    const instruction = formatQualityRewriteInstruction(report)
    if (!instruction.trim()) {
      toast.error('暂无可用的重写建议')
      return
    }
    onApplyRewrite(instruction)
    toast.success('已填入重写指令，请确认后启动')
  }

  const issues = [...(report?.blockers ?? []), ...(report?.warnings ?? [])]
  const llm = report?.llm
  const chapterTips = llm?.chapter_suggestions?.length
    ? llm.chapter_suggestions
    : (llm?.suggestions ?? [])
  const futureTips = llm?.future_chapter_suggestions ?? []
  const showRewritePrompt = Boolean(
    report && (report.overall_score ?? 100) < 80 && report.rewrite_prompt?.trim(),
  )
  const canRewrite = canApplyQualityRewrite(report) && Boolean(onApplyRewrite)
  const canQcPatch = canQcPatchRewrite(report) && hasContent && Boolean(onQcPatchRewrite)
  const qualityScore = report?.status === 'blocked' && report.raw_score != null
    ? report.raw_score
    : report?.overall_score

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
        {hasContent ? (running ? '质检中…' : '重新跑质检') : '本章尚无正文'}
      </button>

      {canRewrite || canQcPatch ? (
        <div className="flex gap-2">
          {canRewrite ? (
            <button
              type="button"
              onClick={applyRewrite}
              className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2 py-1.5 font-semibold text-rose-600 hover:bg-rose-100"
            >
              <PenLine size={13} />
              填入重写指令
            </button>
          ) : null}
          {canQcPatch ? (
            <button
              type="button"
              disabled={qcPatchRunning || running}
              onClick={() => onQcPatchRewrite?.()}
              title="一次 LLM：按本章正文+质检报告修订，完成后自动再跑质检"
              className={clsx(
                'inline-flex flex-1 items-center justify-center gap-1 rounded-lg border px-2 py-1.5 font-semibold',
                qcPatchRunning || running
                  ? 'cursor-not-allowed border-gray-100 bg-gray-50 text-gray-300'
                  : 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100',
              )}
            >
              {qcPatchRunning ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Wand2 size={13} />
              )}
              按本章建议重写
            </button>
          ) : null}
        </div>
      ) : null}

      {report ? (
        <>
          <div className="flex items-baseline gap-2">
            <span className={clsx('text-2xl font-bold', scoreColor(qualityScore ?? 0))}>
              {qualityScore ?? '—'}
            </span>
            <span className="text-gray-500">
              {report.status === 'blocked' && report.raw_score != null
                ? `质量分 · 未通过（门控 ${report.overall_score ?? 40}）`
                : report.status === 'unverified'
                  ? '分 · 质检未完成'
                  : `分 · ${{ ok: '通过', warning: '有警告', blocked: '被阻断' }[report.status ?? ''] ?? report.status}`}
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

          {showRewritePrompt ? (
            <div className="rounded-lg border border-rose-100 bg-rose-50/60 p-2">
              <p className="mb-1 text-[11px] font-semibold text-rose-700">重写提示词（&lt;80分）</p>
              <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-gray-700">
                {report.rewrite_prompt}
              </p>
            </div>
          ) : null}

          {chapterTips.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-semibold text-gray-500">本章建议</p>
              <ul className="space-y-1 text-gray-700">
                {chapterTips.map((s, i) => <li key={i}>· {s}</li>)}
              </ul>
            </div>
          )}

          {futureTips.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] font-semibold text-gray-500">后续章节建议</p>
              <ul className="space-y-1 text-gray-700">
                {futureTips.map((s, i) => <li key={i}>· {s}</li>)}
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
