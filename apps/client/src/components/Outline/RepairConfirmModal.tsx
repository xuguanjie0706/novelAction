/**
 * @file RepairConfirmModal.tsx
 * @description 大纲修复确认弹窗。
 *
 * 替代原先的 `window.confirm()`，提供：
 *   1. 质检报告摘要（总分/状态/问题数/must-fix 数）
 *   2. 修复配置（连续修复开关、最大轮数、分数阈值）
 *   3. 美观的确认/取消 UI
 *
 * 配置参数由调用方通过 `value` / `onChange` 受控管理；
 * 用户点击「开始修复」时触发 `onConfirm`，点击取消或蒙层时触发 `onClose`。
 */

import React, { useEffect, useRef } from 'react'
import { Sparkles, X, AlertTriangle, CheckCircle, TrendingUp } from 'lucide-react'
import clsx from 'clsx'
import type { OutlinePlanQualityReport } from '../../types'

// ── 类型定义 ─────────────────────────────────────────────────────────────────

/** 修复配置，与队列任务参数保持一致。 */
export interface RepairConfig {
  /** 是否启用连续修复（多轮直到达标） */
  continuous: boolean
  /** 连续修复最大轮数（1-20） */
  maxRounds: number
  /**
   * 连续修复停止阈值（0-100，与质检总分同刻度）。
   * 当任一轮质检总分 ≥ 该值或 status 为 pass 时提前结束。
   */
  minScore: number
}

export interface RepairConfirmModalProps {
  open: boolean
  onClose: () => void
  /**
   * 用户确认后回调，携带最新的修复配置。
   * @param config 用户在弹窗中设置的修复参数
   */
  onConfirm: (config: RepairConfig) => void
  /** 修复范围 */
  scope: 'volume' | 'book'
  /** 卷标题（scope='volume' 时展示） */
  volumeTitle?: string
  /** 当前已有的质检报告（可无） */
  qualityReport?: OutlinePlanQualityReport
  /** 修复配置受控值 */
  value: RepairConfig
  /**
   * 修复配置变更回调，用于将配置同步回父组件状态，
   * 确保下次打开弹窗时保留上次的配置。
   */
  onChange: (config: RepairConfig) => void
}

// ── 子组件：质检摘要卡片 ──────────────────────────────────────────────────────

/** 从质检报告的 status 字段推导对应的样式 token。 */
function statusStyle(status?: string): { label: string; color: string } {
  switch (status) {
    case 'pass':
      return { label: '通过', color: 'text-emerald-600' }
    case 'warning':
      return { label: '待改进', color: 'text-amber-600' }
    case 'fail':
      return { label: '需修复', color: 'text-rose-600' }
    default:
      return { label: '未知', color: 'text-gray-500' }
  }
}

interface QualitySummaryProps {
  report: OutlinePlanQualityReport
}

/**
 * 显示质检报告摘要：总分、状态、问题数、must-fix 数。
 *
 * @param report 质检报告，字段均为可选（容错显示）。
 */
function QualitySummary({ report }: QualitySummaryProps) {
  const { overall_score, status, issues, must_fix_chapter_numbers, summary } = report
  const { label: statusLabel, color: statusColor } = statusStyle(status)
  const issueCount = issues?.length ?? 0
  const mustFixCount = must_fix_chapter_numbers?.length ?? 0
  const highSeverityCount = issues?.filter(i => i.severity === 'high').length ?? 0

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">上次质检结果</span>
        <span className={clsx('text-xs font-semibold', statusColor)}>{statusLabel}</span>
      </div>

      {/* 分数 + 状态 */}
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold tabular-nums text-gray-900 leading-none">
          {overall_score ?? '—'}
        </span>
        <span className="text-xs text-gray-400 mb-0.5">/ 100</span>
        {status === 'pass' && (
          <CheckCircle size={14} className="text-emerald-500 mb-0.5" />
        )}
        {(status === 'fail' || status === 'warning') && (
          <AlertTriangle size={14} className="text-amber-500 mb-0.5" />
        )}
      </div>

      {/* 问题数统计 */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500">
        {issueCount > 0 && (
          <span>
            共 <span className="font-semibold text-gray-700">{issueCount}</span> 个问题
            {highSeverityCount > 0 && (
              <span className="ml-1 text-rose-600">
                （{highSeverityCount} 个高优先级）
              </span>
            )}
          </span>
        )}
        {mustFixCount > 0 && (
          <span>
            必修章节 <span className="font-semibold text-rose-600">{mustFixCount}</span> 处
          </span>
        )}
        {issueCount === 0 && <span className="text-emerald-600">暂无发现问题</span>}
      </div>

      {/* 质检摘要文字 */}
      {summary && (
        <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-2">{summary}</p>
      )}
    </div>
  )
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

/**
 * 将轮数夹入合法范围 [1, 20]。
 *
 * @param v 原始输入值
 * @returns 修正后的整数
 */
export function clampMaxRounds(v: number): number {
  return Math.min(20, Math.max(1, Math.round(v)))
}

/**
 * 将分数阈值夹入合法范围 [0, 100]。
 *
 * @param v 原始输入值
 * @returns 修正后的整数
 */
export function clampMinScore(v: number): number {
  return Math.min(100, Math.max(0, Math.round(v)))
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

/**
 * 大纲修复确认弹窗。
 *
 * 使用受控模式管理修复配置，方便父组件在会话期间保留用户的上次配置。
 * 弹窗不管理自身的 loading 状态——确认后直接关闭，进度由队列面板展示。
 */
export default function RepairConfirmModal({
  open,
  onClose,
  onConfirm,
  scope,
  volumeTitle,
  qualityReport,
  value,
  onChange,
}: RepairConfirmModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  // ESC 键关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  // 弹窗打开时聚焦面板，便于键盘操作
  useEffect(() => {
    if (open) {
      setTimeout(() => panelRef.current?.focus(), 50)
    }
  }, [open])

  if (!open) return null

  const targetLabel = scope === 'volume' && volumeTitle ? `「${volumeTitle}」` : '全书'
  const hasReport = qualityReport && typeof qualityReport === 'object' && !qualityReport.error

  function handleConfirm() {
    onConfirm(value)
    onClose()
  }

  return (
    // 蒙层
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[2px]"
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* 弹窗主体 */}
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative w-full max-w-md mx-4 rounded-xl border border-gray-200 bg-white shadow-xl outline-none"
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Sparkles size={15} className="text-rose-500 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-900">
              AI 大纲修复 — {targetLabel}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="关闭"
          >
            <X size={15} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* 质检报告摘要 */}
          {hasReport ? (
            <QualitySummary report={qualityReport!} />
          ) : (
            <div className="rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-400">
              {scope === 'volume'
                ? '当前卷暂无质检报告，建议先执行单卷质检再修复。'
                : '全书暂无质检报告，建议先执行全书质检再修复。'}
            </div>
          )}

          {/* 修复配置 */}
          <div className="space-y-3">
            <p className="text-xs font-medium text-gray-600">修复配置</p>

            {/* 连续修复开关 */}
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs text-gray-700">连续修复</p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  自动循环质检 → 修复，直到达标或达到最大轮数
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value.continuous}
                onClick={() => onChange({ ...value, continuous: !value.continuous })}
                className={clsx(
                  'relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors focus:outline-none focus:ring-2 focus:ring-rose-300 focus:ring-offset-1',
                  value.continuous ? 'border-rose-300 bg-rose-400' : 'border-gray-200 bg-gray-200',
                )}
              >
                <span
                  className={clsx(
                    'inline-block h-4 w-4 translate-x-1 rounded-full bg-white shadow transition-transform',
                    value.continuous && 'translate-x-5',
                  )}
                />
              </button>
            </div>

            {/* 连续修复参数（仅连续模式显示） */}
            {value.continuous && (
              <div className="grid grid-cols-2 gap-3 pl-0">
                {/* 最大轮数 */}
                <div className="space-y-1">
                  <label className="text-[11px] text-gray-500">最大轮数</label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={value.maxRounds}
                      onChange={e => {
                        const v = parseInt(e.target.value, 10)
                        if (!Number.isNaN(v)) onChange({ ...value, maxRounds: clampMaxRounds(v) })
                      }}
                      className="w-16 rounded-md border border-gray-200 px-2 py-1 text-center text-xs text-gray-800 tabular-nums focus:border-rose-300 focus:outline-none focus:ring-1 focus:ring-rose-200"
                    />
                    <span className="text-[11px] text-gray-400">轮（上限 20）</span>
                  </div>
                </div>

                {/* 分数阈值 */}
                <div className="space-y-1">
                  <label
                    className="text-[11px] text-gray-500"
                    title="与质检报告总分同刻度（0-100），达到该分数或 status=pass 时提前结束"
                  >
                    <span className="flex items-center gap-1">
                      达标分数
                      <TrendingUp size={10} className="text-gray-400" />
                    </span>
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={value.minScore}
                      onChange={e => {
                        const v = parseInt(e.target.value, 10)
                        if (!Number.isNaN(v)) onChange({ ...value, minScore: clampMinScore(v) })
                      }}
                      className="w-16 rounded-md border border-gray-200 px-2 py-1 text-center text-xs text-gray-800 tabular-nums focus:border-rose-300 focus:outline-none focus:ring-1 focus:ring-rose-200"
                    />
                    <span className="text-[11px] text-gray-400">分（0-100）</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 说明文字 */}
          <p className="text-[11px] text-gray-400 leading-relaxed">
            {value.continuous
              ? `将对 ${targetLabel} 执行连续修复：最多 ${value.maxRounds} 轮；任一轮质检 status 为 pass 或总分 ≥ ${value.minScore} 时提前结束。每轮均保存修复前/后快照。`
              : `将对 ${targetLabel} 执行单轮修复，并保存修复前/后快照。`}
          </p>
        </div>

        {/* 操作栏 */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg text-xs text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-rose-500 hover:bg-rose-600 border border-rose-500 transition-colors"
          >
            <Sparkles size={12} />
            开始修复
          </button>
        </div>
      </div>
    </div>
  )
}
