/**
 * @file BootstrapTimeline — Bootstrap 生成步骤左侧时间轴
 *
 * 视觉与创作端主壳一致：白/浅灰底、细边框、琥珀进度与选中态（与书架、侧栏同一套语言）。
 */
import React from 'react'
import clsx from 'clsx'
import { Loader2, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react'
import type { StepState, StepKey, Phase, StepPhase } from './hooks/useBootstrapStream'
import BootstrapStepIcon from './BootstrapStepIcon'

interface PhaseConfig {
  key: StepPhase
  label: string
  color: string
}

const PHASE_CONFIGS: PhaseConfig[] = [
  { key: 'foundation', label: '立项基础', color: '#f59e0b' },
  { key: 'world', label: '世界构建', color: '#06b6d4' },
  { key: 'characters', label: '角色与故事', color: '#22c55e' },
  { key: 'narrative', label: '叙事规划', color: '#a78bfa' },
  { key: 'blueprint', label: '执行蓝图', color: '#f97316' },
  { key: 'qa', label: '质量保证', color: '#ef4444' },
]

function fmtOffset(offsetMs: number): string {
  const s = Math.round(offsetMs / 1000)
  if (s < 60) return `+${s}s`
  return `+${Math.floor(s / 60)}m ${s % 60}s`
}

function fmtDuration(durationMs: number): string {
  const s = durationMs / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

function fmtElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

interface StepNodeProps {
  step: StepState
  isSelected: boolean
  generationStartMs: number | null
  onClick: () => void
  /** phase=done 时传入，以便显示「↻」按钮 */
  onRegen?: (key: StepKey) => void
  /** 当前正在重跑的步骤 key */
  regenStep?: StepKey | null
}

function StepNode({ step, isSelected, generationStartMs, onClick, onRegen, regenStep }: StepNodeProps) {
  const offsetMsRaw =
    step.startedAt != null && generationStartMs != null ? step.startedAt - generationStartMs : null
  const offsetMs = offsetMsRaw != null ? Math.max(0, offsetMsRaw) : null
  const durationMs =
    step.startedAt != null && step.completedAt != null ? step.completedAt - step.startedAt : null

  const color = step.stepColor

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'group relative flex w-full items-start gap-0 py-1.5 pl-14 pr-3 text-left transition-colors',
        isSelected ? 'border-l-[3px] border-amber-500 bg-amber-50/80' : 'border-l-[3px] border-transparent hover:bg-gray-50',
      )}
    >
      <span
        className={clsx(
          'absolute left-[26px] top-1/2 flex h-4 w-4 -translate-y-1/2 flex-shrink-0 rounded-full border-2 transition-all',
          step.status === 'pending' && 'border-gray-200 bg-white',
        )}
        style={
          step.status === 'pending'
            ? undefined
            : {
                borderColor: color,
                background: step.status === 'done' ? color : '#fff',
                boxShadow:
                  step.status === 'running' ? `0 0 0 3px ${color}33, 0 0 10px ${color}44` : undefined,
              }
        }
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <BootstrapStepIcon iconKey={step.key} size={15} title={step.label} />
          <span
            className={clsx(
              'truncate text-[13px] font-medium',
              step.status === 'pending' ? 'text-gray-400' : 'text-gray-900',
            )}
          >
            {step.label}
          </span>
          <span className="ml-auto flex-shrink-0">
            {step.status === 'running' && (
              <Loader2 size={12} style={{ color }} className="animate-spin" />
            )}
            {step.status === 'done' && !onRegen && <CheckCircle2 size={12} style={{ color }} />}
            {step.status === 'done' && onRegen && (
              <span className="flex items-center gap-0.5">
                <CheckCircle2 size={12} style={{ color }} />
                {/* 外层 StepNode 已是 button，内层不可用 button（嵌套 button 会触发 DOM/React 报错） */}
                <span
                  role="button"
                  tabIndex={regenStep ? -1 : 0}
                  title="重新生成本步"
                  aria-disabled={!!regenStep}
                  onClick={e => {
                    e.stopPropagation()
                    if (!regenStep) onRegen(step.key)
                  }}
                  onKeyDown={e => {
                    if (regenStep) return
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      e.stopPropagation()
                      onRegen(step.key)
                    }
                  }}
                  className={clsx(
                    'ml-0.5 rounded p-0.5 transition-colors',
                    regenStep === step.key
                      ? 'text-amber-500'
                      : 'text-gray-300 hover:text-amber-500',
                    regenStep && 'opacity-40 pointer-events-none',
                  )}
                >
                  <RefreshCw size={10} className={regenStep === step.key ? 'animate-spin' : ''} />
                </span>
              </span>
            )}
            {step.status === 'error' && <AlertCircle size={12} className="text-red-500" />}
            {step.status === 'blocked' && (
              <span className="text-[10px] text-gray-400">—</span>
            )}
          </span>
        </div>

        {step.status !== 'pending' && (
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-gray-500">
            {offsetMs != null && <span className="tabular-nums">{fmtOffset(offsetMs)}</span>}
            {durationMs != null && (
              <>
                <span>·</span>
                <span className="tabular-nums text-gray-600">{fmtDuration(durationMs)}</span>
              </>
            )}
            {step.status === 'running' && !durationMs && (
              <span className="animate-pulse font-medium" style={{ color }}>
                运行中…
              </span>
            )}
            {step.count != null && (
              <span className="ml-auto rounded-full border border-gray-200 bg-gray-50 px-1.5 py-px text-[10px] text-gray-600">
                {step.count} 条
              </span>
            )}
            {step.status === 'error' && <span className="ml-auto text-[10px] text-red-500">失败</span>}
            {step.status === 'blocked' && (
              <span className="ml-auto text-[10px] text-gray-400">等待</span>
            )}
          </div>
        )}
      </div>
    </button>
  )
}

interface Props {
  steps: StepState[]
  selectedKey: StepKey | null
  onSelect: (key: StepKey) => void
  phase: Phase
  logline: string
  elapsedSec: number
  generationStartMs: number | null
  /** 传入后，done 步骤显示「↻」按钮；仅 phase=done 时由父组件传入 */
  onRegen?: (step: StepKey) => void
  /** 当前正在重跑的步骤 key */
  regenStep?: StepKey | null
}

export default function BootstrapTimeline({
  steps,
  selectedKey,
  onSelect,
  phase,
  logline,
  elapsedSec,
  generationStartMs,
  onRegen,
  regenStep,
}: Props) {
  const doneCount = steps.filter(s => s.status === 'done').length
  const totalCount = steps.length
  const isDone = phase === 'done'

  const totalDurationMs =
    isDone && generationStartMs != null
      ? Math.max(
          0,
          steps.reduce((max, s) => Math.max(max, s.completedAt ?? 0), 0) - generationStartMs,
        )
      : null

  const totalItems = steps.reduce((sum, s) => sum + (s.count ?? 0), 0)

  return (
    <div className="flex h-full w-[300px] shrink-0 flex-col overflow-hidden border-r border-gray-100 bg-white">
      <div className="shrink-0 border-b border-gray-100 bg-[#fafbfc] px-4 py-3">
        <p className="mb-2 line-clamp-2 text-[11px] leading-snug text-gray-500" title={logline}>
          「{logline || '（未填写）'}」
        </p>
        <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
          <div
            className={clsx(
              'h-full rounded-full transition-all duration-500',
              isDone ? 'bg-gradient-to-r from-emerald-400 to-teal-500' : 'bg-gradient-to-r from-amber-400 to-amber-500',
            )}
            style={{ width: `${Math.max(4, (doneCount / totalCount) * 100)}%` }}
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-500">
          <span className={clsx('font-medium', isDone ? 'text-emerald-600' : 'text-gray-700')}>
            {isDone ? '✓ 全部完成' : phase === 'gate' ? `${doneCount} / ${totalCount} 步 · 待审阅` : `${doneCount} / ${totalCount} 步`}
          </span>
          {isDone && totalDurationMs != null && (
            <>
              <span className="text-gray-300">·</span>
              <span>耗时 {fmtDuration(totalDurationMs)}</span>
            </>
          )}
          {!isDone && (
            <>
              <span className="text-gray-300">·</span>
              <span className="tabular-nums text-gray-600">{fmtElapsed(elapsedSec)}</span>
            </>
          )}
          {totalItems > 0 && (
            <>
              <span className="text-gray-300">·</span>
              <span>{totalItems} 条</span>
            </>
          )}
        </div>
      </div>

      <div
        className="relative flex-1 overflow-y-auto py-3"
        style={{ scrollbarWidth: 'thin', scrollbarColor: '#e5e7eb transparent' }}
      >
        <div
          className="pointer-events-none absolute bottom-4 left-[35px] top-4 w-px bg-gradient-to-b from-transparent via-gray-200 to-transparent"
          aria-hidden
        />

        {PHASE_CONFIGS.map(phaseConf => {
          const phaseSteps = steps.filter(s => s.phase === phaseConf.key)
          if (phaseSteps.length === 0) return null
          return (
            <div key={phaseConf.key} className="mb-1">
              <div className="flex items-center gap-2 py-1.5 pl-[52px] pr-4 text-[10px] font-bold uppercase tracking-widest text-gray-400">
                <span
                  className="h-2 w-2 flex-shrink-0 rounded-full shadow-sm"
                  style={{ background: phaseConf.color }}
                />
                {phaseConf.label}
              </div>
              {phaseSteps.map(step => (
                <StepNode
                  key={step.key}
                  step={step}
                  isSelected={selectedKey === step.key}
                  generationStartMs={generationStartMs}
                  onClick={() => onSelect(step.key)}
                  onRegen={onRegen}
                  regenStep={regenStep}
                />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
