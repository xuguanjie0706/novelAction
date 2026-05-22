/**
 * @file BootstrapTimelineDetail — Bootstrap 生成步骤右侧详情
 *
 * 与书架/首页一致：``#f8fafc`` 底、白卡、灰字层次、琥珀主按钮。
 * 正文区保持 ``max-w-*`` 居中便于阅读；**生成中 / 完成** 的 CTA 放在**全宽底栏**并右对齐，占满右栏底边空白，与顶栏分工（生成中顶栏不再重复「终止」）。
 *
 * 一致性问题修复 + 自动重扫：
 *  - ConsistencyContent 从本文件提取为独立组件（ConsistencyContent.tsx）
 *  - 本文件持有 selectedIndices / fixState / rescanState 等修复流程状态
 *  - 修复成功后自动调用 /consistency/rescan，结果通过 onInsightsUpdate 回调上报给父组件
 *  - 底栏在 consistency 步骤 done 时展示「修复选中 (N)」按钮与重扫状态指示
 */
import React, { useState, useCallback } from 'react'
import { ChevronRight, Loader2, MousePointerClick, Wrench } from 'lucide-react'
import type { LinterIssuePreview, StepState, Phase } from './hooks/useBootstrapStream'
import type { StepDataMap } from './hooks/useBootstrapStepData'
import ConsistencyContent, { type FixState } from './ConsistencyContent'
import StepDataContent from './StepDataContent'
import { projectsApi } from '../../api/client'
import BootstrapStepIcon from './BootstrapStepIcon'

function fmtDuration(ms: number): string {
  const s = ms / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

function fmtOffset(offsetMs: number): string {
  const s = Math.round(offsetMs / 1000)
  return s < 60 ? `+${s}s` : `+${Math.floor(s / 60)}m ${s % 60}s`
}

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      {title && (
        <div className="mb-3 text-[10px] font-bold uppercase tracking-wider text-gray-400">
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="mb-2 flex gap-2 text-sm last:mb-0">
      <span className="w-20 flex-shrink-0 text-xs text-gray-500">{label}</span>
      <span className="min-w-0 flex-1 text-gray-900">{value}</span>
    </div>
  )
}

function LinterIssuesList({ issues }: { issues: LinterIssuePreview[] }) {
  return (
    <ul className="max-h-48 overflow-y-auto space-y-1 rounded-lg border border-red-100 bg-white/60 px-3 py-2 text-xs text-red-900">
      {issues.map((issue, idx) => (
        <li key={`${issue.rule_id}-${idx}`} className="leading-snug">
          {issue.chapter_number_in_volume != null && (
            <span className="text-red-500/80 font-medium">第{issue.chapter_number_in_volume}章 · </span>
          )}
          {issue.message}
          {issue.suggestion ? (
            <span className="text-red-700/70"> — 建议：{issue.suggestion}</span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function PositioningContent({ data }: { data: Record<string, any> }) {
  const tropes: string[] = Array.isArray(data.tropes) ? data.tropes : []
  const refs: string[] = Array.isArray(data.reference_works) ? data.reference_works : []
  const taboos: string[] = Array.isArray(data.taboo_lines) ? data.taboo_lines : []

  return (
    <>
      <Card title="定位决策">
        {data.target_audience && <Row label="目标读者" value={data.target_audience} />}
        {data.pace_type && (
          <Row
            label="节奏类型"
            value={
              data.pace_type === 'fast'
                ? '⚡ fast · 番茄式爽快'
                : data.pace_type === 'medium'
                  ? '📘 medium · 起点中速'
                  : '🎨 slow · 文笔流'
            }
          />
        )}
        {data.emotional_arc && (
          <Row
            label="感情线占比"
            value={
              ({ none: '无', low: 'low · 约10%', medium: 'medium · 约25%', high: 'high · 约40%' } as Record<
                string,
                string
              >)[data.emotional_arc as string] ?? data.emotional_arc
            }
          />
        )}
        {data.face_slap_pattern && <Row label="打脸频率" value={data.face_slap_pattern} />}
        {refs.length > 0 && <Row label="参照作品" value={refs.join(' · ')} />}
      </Card>

      {(tropes.length > 0 || taboos.length > 0) && (
        <Card title="爽点与红线">
          {tropes.length > 0 && (
            <div className="mb-3">
              <div className="mb-2 text-xs text-gray-500">核心爽点</div>
              <div className="flex flex-wrap gap-1.5">
                {tropes.map((t, i) => (
                  <span
                    key={i}
                    className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
          {taboos.length > 0 && (
            <div>
              <div className="mb-2 text-xs text-gray-500">禁忌红线</div>
              <div className="flex flex-wrap gap-1.5">
                {taboos.map((t, i) => (
                  <span
                    key={i}
                    className="rounded-full border border-red-100 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {data.selling_point && (
        <Card title="封面卖点">
          <p className="text-sm italic leading-relaxed text-gray-900">「{data.selling_point}」</p>
          {data.hook_test && <p className="mt-2 text-xs leading-relaxed text-gray-500">{data.hook_test}</p>}
        </Card>
      )}

      {(data.market_risk || data.differentiation_durability) && (
        <Card title="风险评估">
          {data.market_risk && <p className="mb-2 text-sm leading-relaxed text-gray-600">{data.market_risk}</p>}
          {data.differentiation_durability && (
            <p className="text-sm leading-relaxed text-gray-600">{data.differentiation_durability}</p>
          )}
        </Card>
      )}
    </>
  )
}


function OpeningContractContent({ data }: { data: Record<string, any> }) {
  const promises: any[] = Array.isArray(data.promises)
    ? data.promises
    : Array.isArray(data.items)
      ? data.items
      : data.chapter1_hook
        ? [{ text: data.chapter1_hook }]
        : []

  return (
    <>
      {data.chapter1_hook && (
        <Card title="第1章核心钩子">
          <p className="text-sm italic leading-relaxed text-gray-900">「{data.chapter1_hook}」</p>
        </Card>
      )}
      {promises.length > 0 && (
        <Card title={`追读承诺清单（${promises.length} 条）`}>
          {promises.map((p: any, i: number) => (
            <div key={i} className="mb-3 flex gap-2 last:mb-0">
              <span
                className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[10px] font-bold text-white"
                style={{
                  background: i < 2 ? '#ef4444' : i < 4 ? '#f97316' : '#22c55e',
                }}
              >
                P{typeof p === 'object' && p.priority != null ? p.priority : 5 - Math.min(i, 4)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs leading-relaxed text-gray-800">
                  {typeof p === 'string' ? p : (p.text || p.content || JSON.stringify(p))}
                </p>
                {typeof p === 'object' && p.type && (
                  <p className="mt-1 text-[10px] text-gray-400">{p.type}</p>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
      {promises.length === 0 && !data.chapter1_hook && (
        <Card>
          <p className="text-sm text-gray-500">
            承诺数据已写入数据库，前往工作台的「大纲」页查看完整列表。
          </p>
        </Card>
      )}
    </>
  )
}

interface Insights {
  consistency_issues: any[]
  opening_contract: Record<string, any>
}

/** 重扫进行中 / 完成 / 出错 三态 */
interface RescanState {
  loading: boolean
  /** 重扫完成后的新问题列表；null 表示尚未扫描 */
  issues: any[] | null
  error: string | null
}

interface Props {
  step: StepState | null
  positioningData: Record<string, any> | null
  insights: Insights | null
  generationStartMs: number | null
  phase: Phase
  projectId: string | null
  onNavigate: () => void
  /** 与顶栏「终止生成」同源：请求后端取消并清理本地状态 */
  onCancel: () => void | Promise<void>
  errorMsg: string
  /** 当前暂停等待重试的步骤（与失败步一致时展示重试按钮） */
  haltedStep?: string | null
  onRetryStep?: () => void | Promise<void>
  retryLoading?: boolean
  /** 终止请求进行中，禁用底部按钮 */
  terminating?: boolean
  /**
   * 当前选用的模型线路（``"local"`` | ``"gemini"``）。
   * 传给一致性修复 / 重扫接口；省略时默认 ``"gemini"``（Bootstrap 使用的线路）。
   */
  modelProfile?: 'local' | 'gemini'
  /** 管理后台 LlmProvider UUID，与 modelProfile 配合使用 */
  llmProviderId?: string | null
  /**
   * 重扫完成后将最新 insights 上报给父组件，父组件更新 setInsights 以刷新视图。
   * @param updated - 覆盖写入后从后端返回的最新一致性问题列表
   */
  onInsightsUpdate?: (updated: { consistency_issues: any[] }) => void
  /**
   * 各步骤完成后从 API 拉取的真实数据 map（来自 useBootstrapStepData）。
   * 用于在右侧详情面板展示富内容；拉取中或失败时为 undefined，降级到"X 条"摘要。
   */
  stepData?: StepDataMap
  /**
   * 单步重新生成回调（phase=done 时传入）；触发后端 regenerate 端点并通过 SSE 更新步骤状态。
   * 传入时，detail 底栏会出现「重新生成本步」按钮。
   */
  onRegen?: (step: import('./hooks/useBootstrapStream').StepKey) => void
  /** 当前正在重跑的步骤 key；重跑时禁用按钮并显示旋转图标 */
  regenStep?: import('./hooks/useBootstrapStream').StepKey | null
}

export default function BootstrapTimelineDetail({
  step,
  positioningData,
  insights,
  stepData,
  generationStartMs,
  phase,
  projectId,
  onNavigate,
  onCancel,
  errorMsg,
  haltedStep = null,
  onRetryStep,
  retryLoading = false,
  terminating = false,
  modelProfile = 'gemini',
  llmProviderId = null,
  onInsightsUpdate,
  onRegen,
  regenStep = null,
}: Props) {
  const scrollClass =
    'flex-1 min-h-0 overflow-y-auto bg-[#f8fafc] [scrollbar-width:thin] [scrollbar-color:#e5e7eb_transparent]'

  // ── 一致性问题修复 + 重扫状态 ────────────────────────────────────────────
  const [selectedConsistencyIndices, setSelectedConsistencyIndices] = useState<Set<number>>(new Set())
  const [fixState, setFixState] = useState<FixState>({ loading: false, result: null, error: null })
  const [rescanState, setRescanState] = useState<RescanState>({ loading: false, issues: null, error: null })

  const handleToggleIssue = useCallback((idx: number) => {
    setSelectedConsistencyIndices((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }, [])

  const handleFixRequest = useCallback(async (indices: number[], userPrompt: string) => {
    if (!projectId || indices.length === 0) return
    setFixState({ loading: true, result: null, error: null })
    setRescanState({ loading: false, issues: null, error: null })
    try {
      const res = await projectsApi.fixConsistencyIssues(projectId, {
        selected_indices: indices,
        user_prompt: userPrompt,
        model_profile: modelProfile,
        llm_provider_id: llmProviderId,
      })
      setFixState({ loading: false, result: res.data, error: null })
      // 清除已成功修复条目的选中状态
      const fixedSet = new Set(res.data.applied.map((a) => a.issue_index))
      setSelectedConsistencyIndices((prev) => {
        const next = new Set(prev)
        fixedSet.forEach((i) => next.delete(i))
        return next
      })

      // 有成功修复项时自动触发重扫，刷新 insights
      if (res.data.applied.length > 0) {
        setRescanState({ loading: true, issues: null, error: null })
        try {
          const scanRes = await projectsApi.rescanConsistency(projectId, {
            model_profile: modelProfile,
            llm_provider_id: llmProviderId,
          })
          setRescanState({ loading: false, issues: scanRes.data.issues, error: null })
          onInsightsUpdate?.({ consistency_issues: scanRes.data.issues })
        } catch (scanErr: any) {
          const msg = scanErr?.response?.data?.detail ?? scanErr?.message ?? '重新扫描失败'
          setRescanState({ loading: false, issues: null, error: msg })
        }
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? err?.message ?? '修复请求失败，请重试'
      setFixState({ loading: false, result: null, error: msg })
    }
  }, [projectId, modelProfile, llmProviderId, onInsightsUpdate])

  // 是否展示「修复选中」按钮（仅在 done 阶段且存在未修复问题时）
  const consistencyIssues = insights?.consistency_issues ?? []
  const hasUnfixedIssues =
    phase === 'done' &&
    consistencyIssues.some((iss: any) => iss?.status !== 'fixed')
  // ──────────────────────────────────────────────────────────────────────────

  if (!step) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f8fafc]">
        <div className="flex h-full min-h-[200px] flex-1 flex-col items-center justify-center gap-3 px-6 text-center text-gray-500">
          <MousePointerClick size={36} className="text-amber-400/80" strokeWidth={1.5} />
          <p className="max-w-xs text-sm">点击左侧步骤，查看本步说明与生成结果摘要</p>
        </div>
      </div>
    )
  }

  const offsetMsRaw =
    step.startedAt != null && generationStartMs != null ? step.startedAt - generationStartMs : null
  const offsetMs = offsetMsRaw != null ? Math.max(0, offsetMsRaw) : null
  const durationMs =
    step.startedAt != null && step.completedAt != null ? step.completedAt - step.startedAt : null

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f8fafc]">
      <div className={scrollClass}>
        <div className="mx-auto max-w-2xl px-5 py-6 sm:max-w-3xl sm:px-8">
        <div className="mb-6 flex flex-col gap-4 border-b border-gray-200 pb-6 sm:flex-row sm:items-start">
          <div className="flex min-w-0 flex-1 gap-3">
            <BootstrapStepIcon iconKey={step.key} size={32} title={step.label} />
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-gray-950">{step.label}</h2>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                <span
                  className="rounded border px-2 py-0.5 text-[10px] font-bold"
                  style={{
                    color: step.stepColor,
                    borderColor: `${step.stepColor}55`,
                    background: `${step.stepColor}12`,
                  }}
                >
                  {step.stepNum}
                </span>
                <span className="leading-relaxed">{step.desc}</span>
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-col items-end gap-1 sm:text-right">
            {durationMs != null && (
              <>
                <div className="text-2xl font-bold tabular-nums text-gray-900">{fmtDuration(durationMs)}</div>
                <div className="text-[10px] font-medium uppercase tracking-wide text-gray-400">耗时</div>
                {offsetMs != null && (
                  <div className="text-xs text-gray-500">开始于 {fmtOffset(offsetMs)}</div>
                )}
              </>
            )}
            {step.status === 'running' && (
              <div className="flex items-center gap-2 rounded-full border border-amber-100 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700">
                <Loader2 size={14} className="animate-spin" />
                生成中…
              </div>
            )}
          </div>
        </div>

        {step.status === 'error' && (
          <div className="mb-4 space-y-3 rounded-xl border border-red-100 bg-red-50/80 px-4 py-3 text-sm text-red-800">
            <p className="whitespace-pre-wrap leading-relaxed">
              ⚠ {step.detail || errorMsg || '该步骤生成失败，请检查后端日志'}
            </p>
            {(step.linterBlockingRules?.length ?? 0) > 0 && (
              <p className="text-xs text-red-700/90">
                须优先处理：{step.linterBlockingRules!.length} 类阻断项（见下方列表）
              </p>
            )}
            {(step.linterIssues?.length ?? 0) > 0 && (
              <LinterIssuesList issues={step.linterIssues!} />
            )}
            {haltedStep === step.key && onRetryStep && (
              <button
                type="button"
                disabled={retryLoading}
                onClick={() => void onRetryStep()}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                {retryLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                {retryLoading ? '重试中…' : '重试此步骤'}
              </button>
            )}
          </div>
        )}

        {/* 步骤完成且已拉取到真实数据时展示富内容；否则降级为 count/preview 摘要 */}
        {step.status === 'done' && stepData?.[step.key] != null
          ? <StepDataContent stepKey={step.key} data={stepData[step.key]} />
          : (step.count != null || step.preview) && (
              <Card title="输出摘要">
                {step.count != null && <Row label="生成数量" value={`${step.count} 条`} />}
                {step.preview && <Row label="内容预览" value={<span className="text-gray-600">{step.preview}</span>} />}
              </Card>
            )
        }

        {step.key === 'positioning' && positioningData && Object.keys(positioningData).length > 0 && (
          <PositioningContent data={positioningData} />
        )}

        {step.key === 'consistency' && step.status === 'done' && (
          <ConsistencyContent
            issues={insights?.consistency_issues ?? []}
            stepDoneCount={step.count}
            selectedIndices={selectedConsistencyIndices}
            onToggle={handleToggleIssue}
            onFixRequest={handleFixRequest}
            fixState={fixState}
          />
        )}

        {step.key === 'opening_contract' && insights && Object.keys(insights.opening_contract ?? {}).length > 0 && (
          <OpeningContractContent data={insights.opening_contract} />
        )}

        {step.status === 'pending' && (
          <Card>
            <p className="text-sm text-gray-500">该步骤尚未开始，等待前序步骤完成后自动触发。</p>
          </Card>
        )}
        </div>
      </div>

      {phase === 'done' && projectId && (
        <div className="flex shrink-0 flex-col gap-3 border-t border-gray-200 bg-white/95 px-5 py-4 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-end sm:px-8">
          {/* 重扫状态指示：修复成功后、按钮左侧显示 */}
          {(rescanState.loading || rescanState.issues !== null || rescanState.error) && (
            <div className="flex flex-1 items-center gap-2 text-xs">
              {rescanState.loading && (
                <>
                  <Loader2 size={13} className="animate-spin text-amber-500" />
                  <span className="text-gray-500">正在重新扫描一致性…</span>
                </>
              )}
              {!rescanState.loading && rescanState.issues !== null && (
                <span className="text-green-600">
                  ✓ 重扫完成
                  {rescanState.issues.filter((i: any) => i?.status !== 'fixed').length > 0
                    ? `，仍有 ${rescanState.issues.filter((i: any) => i?.status !== 'fixed').length} 处待确认`
                    : '，暂无矛盾项'}
                </span>
              )}
              {!rescanState.loading && rescanState.error && (
                <span className="text-red-500">重扫失败：{rescanState.error}</span>
              )}
            </div>
          )}
          {/* 修复按钮：仅在存在未修复问题且重扫未进行时显示 */}
          {hasUnfixedIssues && !rescanState.loading && (
            <button
              type="button"
              disabled={fixState.loading}
              onClick={() => {
                // 若当前不在 consistency 步骤视图，通过提示引导用户切换；
                // 若已有选中项，直接弹出修复面板（步骤视图由用户自行切换）
                if (selectedConsistencyIndices.size === 0) {
                  // 自动全选所有未修复问题并触发
                  const allUnfixed = consistencyIssues
                    .map((_: any, i: number) => i)
                    .filter((i: number) => {
                      const iss = consistencyIssues[i]
                      return iss?.status !== 'fixed' && !fixState.result?.applied.some((a) => a.issue_index === i)
                    })
                  void handleFixRequest(allUnfixed, '')
                } else {
                  void handleFixRequest(Array.from(selectedConsistencyIndices), '')
                }
              }}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-amber-300 bg-white py-3 text-sm font-semibold text-amber-700 shadow-sm transition-colors hover:bg-amber-50 disabled:opacity-50 sm:w-auto sm:px-6"
            >
              {fixState.loading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Wrench size={16} />
              )}
              {fixState.loading
                ? 'AI 修复中…'
                : selectedConsistencyIndices.size > 0
                  ? `修复选中 (${selectedConsistencyIndices.size})`
                  : '一键修复全部'}
            </button>
          )}
          {/* 单步重新生成：仅在选中步骤已完成且 onRegen 已传入时显示 */}
          {onRegen && step && step.status === 'done' && (
            <button
              type="button"
              disabled={!!regenStep}
              onClick={() => onRegen(step.key)}
              title={`重新生成「${step.label}」步骤`}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white py-3 text-sm font-semibold text-gray-700 shadow-sm transition-colors hover:border-amber-300 hover:bg-amber-50 hover:text-amber-700 disabled:opacity-40 sm:w-auto sm:px-5"
            >
              {regenStep === step.key ? (
                <Loader2 size={15} className="animate-spin text-amber-500" />
              ) : (
                <span className="text-[15px] leading-none">↻</span>
              )}
              {regenStep === step.key ? '重新生成中…' : '重新生成本步'}
            </button>
          )}
          <button
            type="button"
            onClick={onNavigate}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-amber-500 py-3 text-sm font-semibold text-white shadow-md transition-colors hover:bg-amber-600 sm:w-auto sm:px-8"
          >
            进入工作台
            <ChevronRight size={18} />
          </button>
        </div>
      )}

      {phase === 'generating' && (
        <div className="flex shrink-0 flex-col gap-3 border-t border-gray-200 bg-white/95 px-5 py-4 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:px-8">
          <p className="text-xs leading-relaxed text-gray-500 sm:max-w-xl">
            {haltedStep
              ? '生成已暂停：请先重试失败步骤，后续步骤不会继续，直到本步成功。'
              : '关闭将中断当前连接；未结束的生成可在书架顶部「继续」恢复。'}
          </p>
          <div className="flex flex-wrap justify-end gap-2 sm:shrink-0">
            {haltedStep && onRetryStep && (
              <button
                type="button"
                disabled={retryLoading}
                onClick={() => void onRetryStep()}
                className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-amber-600 disabled:opacity-50"
              >
                {retryLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                {retryLoading ? '重试中…' : '重试失败步骤'}
              </button>
            )}
            <button
              type="button"
              disabled={terminating}
              onClick={() => void onCancel()}
              className="rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 shadow-sm transition-colors hover:bg-red-50 disabled:opacity-50"
            >
              {terminating ? '终止中…' : '终止生成'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
