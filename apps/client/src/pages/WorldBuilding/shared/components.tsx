/**
 * @file 世界观页共享表单组件（无 API）
 */
import React from 'react'
import { Trash2 } from 'lucide-react'
import clsx from 'clsx'

/** 后端/模型偶发把本应是字符串的字段写成 { description: string }，不能直接当 React 子节点渲染 */
export function stringFromLoose(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'object' && 'description' in (v as object)) {
    const d = (v as { description?: unknown }).description
    return typeof d === 'string' ? d : ''
  }
  return ''
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

export function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
    />
  )
}

export function TextArea({ value, onChange, rows = 3, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
  return (
    <textarea
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      rows={rows}
      placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none"
    />
  )
}

export function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

export function SaveBtn({ saving, onClick }: { saving: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={saving}
      className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors font-medium shadow-sm"
    >
      {saving ? '保存中…' : '保存'}
    </button>
  )
}

/** 芯片式分类选择器，替代 <select> 下拉 */
export function ChipSelect({ value, onChange, options }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string; color?: string; icon?: string }[]
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => (
        <button key={opt.value} type="button" onClick={() => onChange(opt.value)}
          className={clsx(
            'text-xs px-2.5 py-1 rounded-lg border font-medium transition-all',
            value === opt.value
              ? (opt.color ?? 'bg-amber-100 text-amber-700 border-amber-300 shadow-sm')
              : 'bg-white text-gray-400 border-gray-200 hover:border-gray-300 hover:text-gray-600'
          )}>
          {opt.icon && <span className="mr-1">{opt.icon}</span>}
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** 带标题栏的分区卡片 */
export function Section({ title, icon, children, accent }: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  accent?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      <div className={clsx('px-4 py-2 border-b border-gray-100 flex items-center gap-2', accent ?? 'bg-gray-50/60')}>
        {icon && <span className="text-gray-400 flex items-center">{icon}</span>}
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">{title}</span>
      </div>
      <div className="p-4 space-y-3.5">
        {children}
      </div>
    </div>
  )
}

/** 编辑页顶部标题栏：名称大字 + 操作按钮 */
export function EditorHeader({ name, subtitle, badge, onDelete, saving, onSave }: {
  name: string
  subtitle?: string
  badge?: React.ReactNode
  onDelete: () => void
  saving: boolean
  onSave: () => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 pb-2">
      <div className="min-w-0">
        <h2 className="text-xl font-bold text-gray-900 leading-tight truncate">{name || '未命名'}</h2>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        {badge && <div className="mt-1.5 flex flex-wrap gap-1">{badge}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0 mt-0.5">
        <button onClick={onSave} disabled={saving}
          className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-xs rounded-lg transition-colors font-medium shadow-sm">
          {saving ? '保存中…' : '保存'}
        </button>
        <button onClick={onDelete} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
