/**
 * @file BootstrapTimelineDetail — Bootstrap 生成步骤右侧详情
 *
 * 与书架/首页一致：``#f8fafc`` 底、白卡、灰字层次、琥珀主按钮。
 * 正文区保持 ``max-w-*`` 居中便于阅读；**生成中 / 完成** 的 CTA 放在**全宽底栏**并右对齐，占满右栏底边空白，与顶栏分工（生成中顶栏不再重复「终止」）。
 */
import React from 'react'
import { ChevronRight, Loader2, MousePointerClick } from 'lucide-react'
import type { StepState, Phase } from './hooks/useBootstrapStream'

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

function ConsistencyContent({ issues }: { issues: any[] }) {
  if (issues.length === 0) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-sm text-emerald-600">
          <span className="text-base">✓</span>
          <span>未检测到一致性问题，可直接开始写作</span>
        </div>
      </Card>
    )
  }

  const severityColor = (s: string) =>
    s === 'high' || s === 'critical' ? '#ef4444' : s === 'medium' ? '#f97316' : '#f59e0b'
  const severityLabel = (s: string) =>
    ({ critical: '严重', high: '严重', medium: '中等', low: '轻微' }[s] ?? s)

  return (
    <>
      <p className="mb-3 text-sm text-gray-600">
        发现{' '}
        <span className="font-semibold text-amber-600">{issues.length}</span> 处待确认问题，不影响开始写作，建议进入第
        3 章前处理。
      </p>
      {issues.map((issue: any, i: number) => {
        const text = typeof issue === 'string' ? issue : (issue.description || issue.issue || JSON.stringify(issue))
        const sev = issue.severity ?? (i === 0 ? 'high' : i === 1 ? 'medium' : 'low')
        const color = severityColor(sev)
        return (
          <div
            key={i}
            className="mb-2 rounded-lg border border-gray-100 bg-white p-3 shadow-sm"
            style={{ borderLeftWidth: 3, borderLeftColor: color }}
          >
            <div className="mb-1 flex items-center gap-2">
              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                style={{ background: `${color}18`, color }}
              >
                {severityLabel(sev)}
              </span>
              <span className="text-sm font-medium text-gray-900">
                {typeof issue === 'object' ? (issue.title ?? `问题 ${i + 1}`) : `问题 ${i + 1}`}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-gray-600">{text}</p>
            {issue.suggestion && <p className="mt-2 text-xs text-amber-700">▸ {issue.suggestion}</p>}
          </div>
        )
      })}
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
  /** 终止请求进行中，禁用底部按钮 */
  terminating?: boolean
}

export default function BootstrapTimelineDetail({
  step,
  positioningData,
  insights,
  generationStartMs,
  phase,
  projectId,
  onNavigate,
  onCancel,
  errorMsg,
  terminating = false,
}: Props) {
  const scrollClass =
    'flex-1 min-h-0 overflow-y-auto bg-[#f8fafc] [scrollbar-width:thin] [scrollbar-color:#e5e7eb_transparent]'

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

  const offsetMs =
    step.startedAt != null && generationStartMs != null ? step.startedAt - generationStartMs : null
  const durationMs =
    step.startedAt != null && step.completedAt != null ? step.completedAt - step.startedAt : null

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f8fafc]">
      <div className={scrollClass}>
        <div className="mx-auto max-w-2xl px-5 py-6 sm:max-w-3xl sm:px-8">
        <div className="mb-6 flex flex-col gap-4 border-b border-gray-200 pb-6 sm:flex-row sm:items-start">
          <div className="flex min-w-0 flex-1 gap-3">
            <span className="flex-shrink-0 text-3xl leading-none">{step.icon}</span>
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
          <div className="mb-4 rounded-xl border border-red-100 bg-red-50/80 px-4 py-3 text-sm text-red-800">
            ⚠ {step.detail || errorMsg || '该步骤生成失败，请检查后端日志'}
          </div>
        )}

        {(step.count != null || step.preview) && (
          <Card title="输出摘要">
            {step.count != null && <Row label="生成数量" value={`${step.count} 条`} />}
            {step.preview && <Row label="内容预览" value={<span className="text-gray-600">{step.preview}</span>} />}
          </Card>
        )}

        {step.key === 'positioning' && positioningData && Object.keys(positioningData).length > 0 && (
          <PositioningContent data={positioningData} />
        )}

        {step.key === 'consistency' && insights && <ConsistencyContent issues={insights.consistency_issues} />}

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
            关闭将中断当前连接；未结束的生成可在书架顶部「继续」恢复。
          </p>
          <div className="flex flex-wrap justify-end gap-2 sm:shrink-0">
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
