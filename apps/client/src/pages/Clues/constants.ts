/**
 * Clues 页面共享常量与工具函数
 *
 * 伏笔 / 情节档案 / 质量债务三个 Tab 共用的状态映射、颜色、工具函数。
 */
import React from 'react'
import { CheckCircle, XCircle, Circle, Star } from 'lucide-react'
import type { QualityDebt } from '../../types'

// ── 章节号解析 ───────────────────────────────────────────────────────────────
const CHAPTER_NUM_PREFIX = /^\s*第\s*0*(\d+)\s*章/

export function displayChapterNumber(title?: string, sortOrder?: number): number {
  const raw = (title || '').trim()
  const m = CHAPTER_NUM_PREFIX.exec(raw)
  if (m) return Math.max(1, Number(m[1]))
  const so = Number.isFinite(sortOrder as number) ? Number(sortOrder) : 0
  return Math.max(1, so + 1)
}

// ── 伏笔状态 ─────────────────────────────────────────────────────────────────
export const STATUS_LABEL: Record<string, string> = {
  planned: '章纲规划',
  open: '未回收',
  resolved: '已回收',
  dropped: '已放弃',
}
export const STATUS_COLOR: Record<string, string> = {
  planned: 'bg-sky-100 text-sky-700 border-sky-200',
  open: 'bg-amber-100 text-amber-700 border-amber-200',
  resolved: 'bg-green-100 text-green-700 border-green-200',
  dropped: 'bg-gray-100 text-gray-400 border-gray-200',
}
export const STATUS_ICON: Record<string, React.ReactNode> = {
  planned: React.createElement(Circle, { size: 12 }),
  open: React.createElement(Circle, { size: 12 }),
  resolved: React.createElement(CheckCircle, { size: 12 }),
  dropped: React.createElement(XCircle, { size: 12 }),
}

export const PLANNED_ACTION_LABEL: Record<'resolve' | 'develop', string> = {
  resolve: '预计回收',
  develop: '预计铺垫',
}
export const PLANNED_ACTION_COLOR: Record<'resolve' | 'develop', string> = {
  resolve: 'bg-amber-50 text-amber-600',
  develop: 'bg-indigo-50 text-indigo-600',
}

// ── 质量债务状态 ──────────────────────────────────────────────────────────────
export const QUALITY_DEBT_STATUS_LABEL: Record<QualityDebt['status'], string> = {
  pending: '未解决',
  resolved: '已修复',
  dismissed: '已忽略',
}
export const QUALITY_DEBT_STATUS_COLOR: Record<QualityDebt['status'], string> = {
  pending: 'bg-red-50 text-red-700 border-red-100',
  resolved: 'bg-green-50 text-green-700 border-green-100',
  dismissed: 'bg-gray-50 text-gray-500 border-gray-100',
}
export const QUALITY_DEBT_SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-gray-100 text-gray-500',
}

// ── 重要度星标 ───────────────────────────────────────────────────────────────
export const PRIORITY_STARS = (p: number) =>
  Array.from({ length: 5 }).map((_, i) =>
    React.createElement(Star, {
      key: i,
      size: 10,
      className: i < p ? 'text-amber-400 fill-amber-400' : 'text-gray-200',
    }),
  )
