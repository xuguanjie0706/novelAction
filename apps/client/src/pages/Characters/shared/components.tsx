/**
 * @file 人物页共享展示组件（无 API）
 */
import React from 'react'
import clsx from 'clsx'
import type { Character } from '../../../types'

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

export function TInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
    />
  )
}

export function TArea({ value, onChange, rows = 3, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
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

export function CharacterTag({ children, tone = 'amber' }: { children: React.ReactNode; tone?: 'amber' | 'green' | 'red' }) {
  const colors = {
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    red: 'bg-red-50 text-red-600 border-red-200',
  }
  return (
    <span className={clsx('text-sm px-4 py-2 rounded-lg border font-medium shadow-sm', colors[tone])}>
      {children}
    </span>
  )
}

export function InfoPanel({
  icon: Icon,
  title,
  accent,
  children,
}: {
  icon: React.ElementType
  title: string
  accent: string
  children: React.ReactNode
}) {
  return (
    <section className={clsx('bg-white rounded-2xl border border-gray-100 shadow-sm p-6 border-l-4', accent)}>
      <div className="flex items-center gap-3 mb-4">
        <Icon size={22} className="text-current" />
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
      </div>
      {children}
    </section>
  )
}

export interface CharacterGrowthMilestone {
  chapter_number: number
  chapter_title: string
  realm_name: string
  realm_rank: number
  character_change: string
  source?: string
}

export interface CharacterGrowthTimelinePayload {
  character_display_name?: string | null
  character_anchor_names?: string[]
  has_realm_whitelist: boolean
  anchored: boolean
  chapter_plans_scanned: number
  debrief_snapshots?: number
  changelog_entries?: number
  milestones: CharacterGrowthMilestone[]
  source?: string
}

export function CharacterAvatar({ char, size = 'md' }: { char: Character; size?: 'sm' | 'md' | 'lg' }) {
  const dim = size === 'sm' ? 'w-7 h-7 text-xs' : size === 'lg' ? 'w-28 h-28 text-5xl' : 'w-10 h-10 text-sm'
  if (char.avatar_url) {
    return (
      <img
        src={char.avatar_url}
        alt={char.name}
        className={clsx(dim, 'rounded-full object-cover shrink-0 shadow-sm border border-white')}
      />
    )
  }
  return (
    <div
      className={clsx(
        dim,
        'rounded-full flex items-center justify-center text-white font-bold shrink-0 shadow-sm',
        char.role === 'protagonist'
          ? 'bg-gradient-to-br from-amber-300 to-amber-500'
          : char.role === 'antagonist'
            ? 'bg-gradient-to-br from-red-300 to-red-500'
            : 'bg-gradient-to-br from-gray-300 to-gray-400',
      )}
    >
      {char.name[0]}
    </div>
  )
}
