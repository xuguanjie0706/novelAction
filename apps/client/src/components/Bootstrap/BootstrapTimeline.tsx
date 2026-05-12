/**
 * @file BootstrapTimeline — Bootstrap 生成纪要左侧时间轴面板
 *
 * 职责：
 * - 将所有步骤按阶段分组渲染为垂直时间轴
 * - 展示每步的时间偏移、耗时、条目数 badge、状态指示
 * - 触发 onSelect 回调，驱动右侧详情面板更新
 *
 * @param steps         来自 useBootstrapStream 的步骤状态数组
 * @param selectedKey   当前选中步骤的 key（高亮用）
 * @param onSelect      点击步骤时触发，参数为被点击的 StepKey
 * @param phase         当前生成阶段，用于顶部状态展示
 * @param logline       一句话创意，展示在顶部摘要区
 * @param elapsedSec    已生成的总秒数（由 GenerateWizard 传入）
 * @param generationStartMs  生成开始时间戳（ms），用于计算步骤偏移
 */
import React from 'react'
import clsx from 'clsx'
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import type { StepState, StepKey, Phase, StepPhase } from './hooks/useBootstrapStream'

// ── 阶段分组配置 ──────────────────────────────────────────────

interface PhaseConfig {
  key: StepPhase
  label: string
  color: string
}

const PHASE_CONFIGS: PhaseConfig[] = [
  { key: 'foundation', label: '立项基础',   color: '#f59e0b' },
  { key: 'world',      label: '世界构建',   color: '#06b6d4' },
  { key: 'characters', label: '角色与故事', color: '#22c55e' },
  { key: 'narrative',  label: '叙事规划',   color: '#a78bfa' },
  { key: 'blueprint',  label: '执行蓝图',   color: '#f97316' },
  { key: 'qa',         label: '质量保证',   color: '#ef4444' },
]

// ── 工具函数 ──────────────────────────────────────────────────

/**
 * 将毫秒偏移量格式化为 "+Xs" 或 "+Xm Xs"。
 * @param offsetMs - 距生成开始的毫秒数
 */
function fmtOffset(offsetMs: number): string {
  const s = Math.round(offsetMs / 1000)
  if (s < 60) return `+${s}s`
  return `+${Math.floor(s / 60)}m ${s % 60}s`
}

/**
 * 将持续时长（毫秒）格式化为 "Xs" 或 "Xm Xs"。
 * @param durationMs - 步骤耗时毫秒数
 */
function fmtDuration(durationMs: number): string {
  const s = durationMs / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

/**
 * 将总秒数格式化为 "Xm Xs" 或 "Xs"。
 * @param sec - 秒数
 */
function fmtElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

// ── 子组件：步骤节点 ──────────────────────────────────────────

interface StepNodeProps {
  step: StepState
  isSelected: boolean
  generationStartMs: number | null
  onClick: () => void
}

/**
 * 单个步骤在时间轴上的节点卡片。
 * 点击触发 onClick，展示时间偏移、耗时、条目数 badge、状态图标。
 */
function StepNode({ step, isSelected, generationStartMs, onClick }: StepNodeProps) {
  const offsetMs = step.startedAt != null && generationStartMs != null
    ? step.startedAt - generationStartMs : null
  const durationMs = step.startedAt != null && step.completedAt != null
    ? step.completedAt - step.startedAt : null

  const color = step.stepColor

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left flex items-start gap-0 pl-14 pr-4 py-1.5 relative',
        'transition-colors duration-100 group',
        isSelected ? 'bg-white/5' : 'hover:bg-white/[0.03]',
      )}
      style={{ borderLeft: `3px solid ${isSelected ? color : 'transparent'}` }}
    >
      {/* axis dot */}
      <span
        className="absolute left-[26px] top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 flex-shrink-0 transition-all duration-200"
        style={{
          borderColor: step.status === 'pending' ? '#2a2a3a' : color,
          background: step.status === 'done' ? color
            : step.status === 'running' ? '#0d0d12'
            : '#0d0d12',
          boxShadow: step.status === 'running' ? `0 0 10px ${color}` : undefined,
        }}
      />

      <div className="flex-1 min-w-0">
        {/* top row: icon + name + status */}
        <div className="flex items-center gap-1.5">
          <span className="text-sm leading-none flex-shrink-0">{step.icon}</span>
          <span
            className="text-[13px] font-medium truncate"
            style={{ color: step.status === 'pending' ? '#5a5a78' : '#e2e2ec' }}
          >
            {step.label}
          </span>
          <span className="ml-auto flex-shrink-0">
            {step.status === 'running' && (
              <Loader2 size={12} style={{ color }} className="animate-spin" />
            )}
            {step.status === 'done' && (
              <CheckCircle2 size={12} style={{ color }} />
            )}
            {step.status === 'error' && (
              <AlertCircle size={12} className="text-red-400" />
            )}
          </span>
        </div>

        {/* meta row: time offset · duration · count badge */}
        {step.status !== 'pending' && (
          <div className="flex items-center gap-1.5 mt-0.5" style={{ color: '#5a5a78' }}>
            {offsetMs != null && (
              <span className="text-[11px] tabular-nums">{fmtOffset(offsetMs)}</span>
            )}
            {durationMs != null && (
              <>
                <span className="text-[11px]">·</span>
                <span className="text-[11px] tabular-nums" style={{ color: '#7a7a90' }}>
                  {fmtDuration(durationMs)}
                </span>
              </>
            )}
            {step.status === 'running' && !durationMs && (
              <span className="text-[11px] animate-pulse" style={{ color }}>运行中…</span>
            )}
            {step.count != null && (
              <span
                className="ml-auto text-[10px] px-1.5 py-px rounded-full border"
                style={{ color: '#9999b8', borderColor: '#2a2a3a', background: '#22222f' }}
              >
                {step.count} 条
              </span>
            )}
            {step.status === 'error' && (
              <span className="ml-auto text-[10px] text-red-400">失败</span>
            )}
          </div>
        )}
      </div>
    </button>
  )
}

// ── 主组件 ────────────────────────────────────────────────────

interface Props {
  steps: StepState[]
  selectedKey: StepKey | null
  onSelect: (key: StepKey) => void
  phase: Phase
  logline: string
  elapsedSec: number
  generationStartMs: number | null
}

/**
 * Bootstrap 生成纪要左侧时间轴面板。
 * 按阶段分组展示所有步骤节点，支持点击选中以驱动右侧详情面板。
 */
export default function BootstrapTimeline({
  steps, selectedKey, onSelect, phase, logline, elapsedSec, generationStartMs,
}: Props) {
  const doneCount = steps.filter(s => s.status === 'done').length
  const totalCount = steps.length
  const isDone = phase === 'done'

  // 计算实际总耗时（生成完成时）
  const totalDurationMs = isDone && generationStartMs != null
    ? steps.reduce((max, s) => Math.max(max, s.completedAt ?? 0), 0) - generationStartMs
    : null

  const totalItems = steps.reduce((sum, s) => sum + (s.count ?? 0), 0)

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: '#0d0d12', borderRight: '1px solid #2a2a3a', width: 300, flexShrink: 0 }}
    >
      {/* ── 顶部统计栏 ──────────────────────────────────── */}
      <div style={{ background: '#13131a', borderBottom: '1px solid #2a2a3a', padding: '12px 16px', flexShrink: 0 }}>
        {/* 一句话创意 */}
        <p
          className="text-[11px] leading-snug line-clamp-2 mb-2"
          style={{ color: '#5a5a78' }}
          title={logline}
        >
          "{logline}"
        </p>
        {/* 进度条 */}
        <div className="h-1 rounded-full mb-2" style={{ background: '#22222f' }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${(doneCount / totalCount) * 100}%`,
              background: isDone
                ? 'linear-gradient(90deg, #22c55e, #06b6d4)'
                : 'linear-gradient(90deg, #7c6af7, #a78bfa)',
            }}
          />
        </div>
        {/* 统计数字 */}
        <div className="flex items-center gap-3 text-[11px]" style={{ color: '#5a5a78' }}>
          <span style={{ color: isDone ? '#22c55e' : '#9999b8' }}>
            {isDone ? '✓ 全部完成' : `${doneCount} / ${totalCount} 步`}
          </span>
          {isDone && totalDurationMs != null && (
            <>
              <span>·</span>
              <span style={{ color: '#7a7a90' }}>耗时 {fmtDuration(totalDurationMs)}</span>
            </>
          )}
          {!isDone && (
            <>
              <span>·</span>
              <span className="tabular-nums" style={{ color: '#7a7a90' }}>{fmtElapsed(elapsedSec)}</span>
            </>
          )}
          {totalItems > 0 && (
            <>
              <span>·</span>
              <span style={{ color: '#7a7a90' }}>{totalItems} 条</span>
            </>
          )}
        </div>
      </div>

      {/* ── 时间轴滚动区域 ──────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-3" style={{ scrollbarWidth: 'thin', scrollbarColor: '#2a2a3a transparent' }}>
        {/* 轴线 */}
        <div
          className="pointer-events-none absolute"
          style={{ left: 35, top: 0, bottom: 0, width: 2, background: 'linear-gradient(to bottom, transparent, #2a2a3a 5%, #2a2a3a 95%, transparent)' }}
        />

        {PHASE_CONFIGS.map(phaseConf => {
          const phaseSteps = steps.filter(s => s.phase === phaseConf.key)
          if (phaseSteps.length === 0) return null
          return (
            <div key={phaseConf.key} className="mb-1">
              {/* 阶段标题 */}
              <div
                className="flex items-center gap-2 pl-[52px] pr-4 py-1.5 text-[10px] font-bold tracking-widest uppercase"
                style={{ color: '#5a5a78' }}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: phaseConf.color, boxShadow: `0 0 6px ${phaseConf.color}` }}
                />
                {phaseConf.label}
              </div>
              {/* 步骤节点 */}
              {phaseSteps.map(step => (
                <StepNode
                  key={step.key}
                  step={step}
                  isSelected={selectedKey === step.key}
                  generationStartMs={generationStartMs}
                  onClick={() => onSelect(step.key)}
                />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
