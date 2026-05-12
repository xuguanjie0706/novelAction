/**
 * @file BootstrapGateTimelineDetail — 根闸门 UI，嵌入「时间轴 + 右侧详情」工作台
 *
 * 与独立 ``BootstrapGateExperience`` 双栏不同：本组件仅占**右栏**，与 ``BootstrapTimeline`` 组合为同一套生成页，
 * 避免「审阅」与「生成中」两种全屏形态切换。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, Loader2, RefreshCw, ScrollText } from 'lucide-react'
import PositioningGatePanel, { type PositioningGatePanelHandle } from './PositioningGatePanel'
import type { GatePendingStep } from './hooks/useBootstrapStream'
import { STEP_META } from './hooks/useBootstrapStream'

const LOG_PREFIX = '[BootstrapGate]'

function logBootstrap(message: string, detail?: Record<string, unknown>) {
  const ts = new Date().toISOString()
  if (detail && Object.keys(detail).length > 0) {
    // eslint-disable-next-line no-console -- 闸门可观测
    console.log(LOG_PREFIX, ts, message, detail)
  } else {
    // eslint-disable-next-line no-console -- 闸门可观测
    console.log(LOG_PREFIX, ts, message)
  }
}

const GATE_LABEL: Record<GatePendingStep, string> = {
  positioning: '立项会议',
  power_systems: '境界体系',
  characters: '人物档案',
  volumes: '卷级骨架',
}

function previewSummary(
  step: GatePendingStep,
  preview: Record<string, unknown> | null,
): string | null {
  if (!preview) return null
  if (step === 'power_systems') {
    const n = preview.power_systems_count
    return typeof n === 'number' ? `已写入 ${n} 套境界体系` : null
  }
  if (step === 'characters') {
    const n = preview.characters_count
    return typeof n === 'number' ? `已写入 ${n} 名角色（含关系）` : null
  }
  if (step === 'volumes') {
    const n = preview.volumes_count
    return typeof n === 'number' ? `已规划 ${n} 卷骨架` : null
  }
  return null
}

export interface BootstrapGateTimelineDetailProps {
  gateStep: GatePendingStep
  gateMessage: string
  gatePreview: Record<string, unknown> | null
  positioningData: Record<string, any> | null
  loading: boolean
  terminating?: boolean
  onDismiss: () => void
  onApprovePositioning: (p: Record<string, any>) => void
  onRegeneratePositioning: () => void
  onApproveOther: () => void
  onRegenerateOther: () => void
  onTerminate: () => void | Promise<void>
}

export default function BootstrapGateTimelineDetail({
  gateStep,
  gateMessage,
  gatePreview,
  positioningData,
  loading,
  terminating = false,
  onDismiss,
  onApprovePositioning,
  onRegeneratePositioning,
  onApproveOther,
  onRegenerateOther,
  onTerminate,
}: BootstrapGateTimelineDetailProps) {
  const posRef = useRef<PositioningGatePanelHandle>(null)
  const isPos = gateStep === 'positioning'
  const meta = STEP_META[gateStep as keyof typeof STEP_META]
  const accent = meta?.stepColor ?? '#f59e0b'
  const summary = previewSummary(gateStep, gatePreview)

  const [logLines, setLogLines] = useState<string[]>([])

  const appendLog = useCallback((line: string) => {
    const t = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    setLogLines(prev => [...prev.slice(-80), `${t}  ${line}`])
  }, [])

  useEffect(() => {
    const label = GATE_LABEL[gateStep]
    appendLog(`进入闸门：${label}（${meta?.stepNum ?? ''}）`)
    logBootstrap('gate_open', { step: gateStep, label })
  }, [gateStep, meta?.stepNum, appendLog])

  function primary() {
    appendLog('点击「确认并继续」')
    logBootstrap('gate_primary', { step: gateStep, mode: isPos ? 'positioning' : 'approve' })
    if (!isPos) {
      onApproveOther()
      return
    }
    const p = posRef.current?.submitApprove()
    if (p) {
      appendLog('已提交立项 JSON，请求 resume（approve）')
      onApprovePositioning(p)
    } else {
      appendLog('立项 JSON 校验未通过，未提交')
      logBootstrap('gate_primary_blocked', { step: gateStep, reason: 'invalid_json' })
    }
  }

  function secondaryRegen() {
    appendLog('点击「重新生成此步」')
    logBootstrap('gate_regenerate', { step: gateStep })
    if (isPos) onRegeneratePositioning()
    else onRegenerateOther()
  }

  function handleDismiss() {
    appendLog('关闭审阅（稍后可在首页/书架继续）')
    logBootstrap('gate_dismiss', { step: gateStep })
    onDismiss()
  }

  const scrollClass =
    'flex-1 min-h-0 overflow-y-auto bg-[#f8fafc] [scrollbar-width:thin] [scrollbar-color:#e5e7eb_transparent]'

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f8fafc]">
      <div className={scrollClass}>
        <div className="mx-auto max-w-2xl px-5 py-6 sm:max-w-3xl sm:px-8">
          <div className="relative mb-6 border-b border-gray-200 pb-6 pl-3">
            <div
              className="pointer-events-none absolute left-0 top-0 h-[calc(100%-0.5rem)] w-1 rounded-full bg-amber-400/90"
              aria-hidden
            />
            <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
              <div className="flex min-w-0 flex-1 gap-3">
                <span className="flex-shrink-0 text-3xl leading-none">{meta?.icon}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                    <span>{meta?.stepNum}</span>
                    <span className="text-gray-300">·</span>
                    <span style={{ color: accent }}>{GATE_LABEL[gateStep]}</span>
                  </div>
                  <h2 className="mt-1.5 text-lg font-bold text-gray-950">审阅后再继续</h2>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">
                    {gateMessage || '请确认当前步骤产出；根设定错误会在后续步骤被放大。'}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                <div className="flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800">
                  待审阅
                </div>
              </div>
            </div>
          </div>

          {isPos && positioningData && (
            <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
              <PositioningGatePanel ref={posRef} positioning={positioningData} externalActions />
            </div>
          )}
          {!isPos && (
            <div className="flex flex-col items-center gap-4 rounded-xl border border-gray-100 bg-white px-6 py-12 text-center shadow-sm">
              <div className="text-5xl leading-none opacity-90">{meta?.icon}</div>
              {summary && (
                <p className="max-w-md rounded-xl border border-gray-100 bg-gray-50 px-4 py-2.5 text-sm font-medium text-gray-800">
                  {summary}
                </p>
              )}
              <p className="max-w-sm text-xs leading-relaxed text-gray-500">
                若结构大体满意请点底栏「确认并继续」；「重新生成」将按后端策略回滚本步产物后重跑。
              </p>
            </div>
          )}

          <div className="mt-6 rounded-xl border border-gray-200 bg-gray-50/80 p-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-gray-600">
              <ScrollText size={14} className="text-gray-500" />
              操作记录
            </div>
            <div
              className="max-h-40 overflow-y-auto rounded-lg border border-gray-100 bg-white px-2 py-2 font-mono text-[11px] leading-relaxed text-gray-600"
              role="log"
              aria-live="polite"
            >
              {logLines.length === 0 ? (
                <span className="text-gray-400">暂无记录</span>
              ) : (
                logLines.map((line, i) => (
                  <div
                    key={`${i}-${line.slice(0, 12)}`}
                    className="whitespace-pre-wrap break-words border-b border-gray-50 py-1 last:border-0"
                  >
                    {line}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-3 border-t border-gray-200 bg-white/95 px-5 py-4 backdrop-blur-sm sm:px-8">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-xs leading-relaxed text-gray-500">
              可先关闭本窗口；首页或书架顶部提示条可再次进入，刷新不会丢失进度。
            </p>
            <button
              type="button"
              onClick={handleDismiss}
              className="text-left text-[11px] text-gray-400 transition-colors hover:text-gray-700 hover:underline"
            >
              稍后再审
            </button>
          </div>
          <div className="flex flex-wrap justify-end gap-2 sm:shrink-0">
            <button
              type="button"
              disabled={terminating}
              onClick={() => void onTerminate()}
              className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 shadow-sm transition-colors hover:bg-red-50 disabled:opacity-50"
            >
              {terminating ? '终止中…' : '终止生成'}
            </button>
            <button
              type="button"
              disabled={loading || terminating}
              onClick={secondaryRegen}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-800 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              重新生成此步
            </button>
            <button
              type="button"
              disabled={loading || terminating}
              onClick={primary}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-amber-600 disabled:opacity-50"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
              确认并继续
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
