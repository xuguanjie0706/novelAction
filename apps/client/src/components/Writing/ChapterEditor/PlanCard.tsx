/**
 * PlanCard.tsx — 大纲计划信息卡片组件
 *
 * 职责：展示大纲节点的单个属性（钩子/冲突/里程碑/情感基调等），
 * 无副作用，无 store 依赖，纯展示组件。
 */
import React from 'react'
import clsx from 'clsx'

type AccentColor = 'amber' | 'blue' | 'purple' | 'red' | 'green' | 'indigo'

const accentCls: Record<AccentColor, { border: string; label: string; bg: string }> = {
  amber:  { border: 'border-amber-100',  label: 'text-amber-700',  bg: 'bg-amber-50/70' },
  blue:   { border: 'border-blue-100',   label: 'text-blue-700',   bg: 'bg-blue-50/70' },
  purple: { border: 'border-purple-100', label: 'text-purple-700', bg: 'bg-purple-50/70' },
  red:    { border: 'border-red-100',    label: 'text-red-700',    bg: 'bg-red-50/70' },
  green:  { border: 'border-green-100',  label: 'text-green-700',  bg: 'bg-green-50/70' },
  indigo: { border: 'border-indigo-100', label: 'text-indigo-700', bg: 'bg-indigo-50/70' },
}

/**
 * 大纲计划属性卡片。
 *
 * @param icon - 左侧图标节点
 * @param label - 主标签文字
 * @param sublabel - 可选次级标签（小字）
 * @param content - 卡片正文内容
 * @param accent - 配色主题
 */
export default function PlanCard({ icon, label, sublabel, content, accent }: {
  icon: React.ReactNode
  label: string
  sublabel?: string
  content: string
  accent: AccentColor
}) {
  const c = accentCls[accent]
  return (
    <div className={clsx('rounded-novel border p-3', c.border, c.bg)}>
      <div className="flex items-center gap-1.5 mb-1.5">
        {icon}
        <span className={clsx('text-xs font-semibold', c.label)}>{label}</span>
        {sublabel && <span className="text-[10px] text-novel-ink-faint">{sublabel}</span>}
      </div>
      <p className="text-xs text-novel-ink leading-relaxed">{content}</p>
    </div>
  )
}
