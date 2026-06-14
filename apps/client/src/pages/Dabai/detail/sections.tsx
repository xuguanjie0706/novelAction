/**
 * @file pages/Dabai/detail/sections.tsx
 * 大白文详情页的分区元数据配置。
 *
 * 每个分区给出 id / 中文标签 / 图标 / 强调色 / 条目数计算函数。
 * 仅当该分区有内容时才在左侧导航显示（count>0 或始终显示的概览/质检）。
 * 分区取舍体现大白文「爽点流水线」特色：对标、金手指、反派阶梯、谜题排程、爽点节拍。
 */
import type { ReactNode } from 'react'
import {
  BookOpen, Target, Sparkles, Zap, Swords, Castle,
  Users, GitBranch, KeyRound, Layers, Flame, Package, ShieldCheck,
} from 'lucide-react'
import type { DabaiProjectDetail } from '../../../types/dabai'

export interface DabaiSectionCfg {
  id: string
  label: string
  icon: ReactNode
  accent: string
  /** 条目数（0 且非 always 时该分区隐藏）。 */
  count: (d: DabaiProjectDetail) => number
  /** 始终显示（即便 count=0）。 */
  always?: boolean
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

export function antagonistLadder(d: DabaiProjectDetail): unknown[] {
  return arr((d.extra ?? {}).antagonist_ladder)
}

export function mysteries(d: DabaiProjectDetail): unknown[] {
  const ms = (d.extra ?? {}).mystery_schedule as Record<string, unknown> | undefined
  return arr(ms?.mysteries)
}

export const DABAI_SECTIONS: DabaiSectionCfg[] = [
  { id: 'overview', label: '立项概览', icon: <BookOpen size={16} />, accent: '#f43f5e', count: () => 1, always: true },
  { id: 'benchmark', label: '对标分析', icon: <Target size={16} />, accent: '#fb7185', count: d => (d.benchmark?.reference_books?.length ?? 0) },
  { id: 'golden', label: '金手指', icon: <Sparkles size={16} />, accent: '#f59e0b', count: d => (Object.keys(d.golden_finger ?? {}).length ? 1 : 0) },
  { id: 'power', label: '境界阶梯', icon: <Zap size={16} />, accent: '#06b6d4', count: d => (d.power_ladder?.levels?.length ?? 0) },
  { id: 'antagonist', label: '反派阶梯', icon: <Swords size={16} />, accent: '#ef4444', count: d => antagonistLadder(d).length },
  { id: 'factions', label: '势力', icon: <Castle size={16} />, accent: '#a78bfa', count: d => d.factions.length },
  { id: 'characters', label: '人物', icon: <Users size={16} />, accent: '#22c55e', count: d => d.characters.length },
  { id: 'storylines', label: '故事线', icon: <GitBranch size={16} />, accent: '#8b5cf6', count: d => d.storylines.length },
  { id: 'mystery', label: '谜题排程', icon: <KeyRound size={16} />, accent: '#0ea5e9', count: d => mysteries(d).length },
  { id: 'volumes', label: '卷骨架', icon: <Layers size={16} />, accent: '#f97316', count: d => d.volumes.length },
  { id: 'beats', label: '爽点节拍', icon: <Flame size={16} />, accent: '#e11d48', count: d => d.chapter_outlines.length },
  {
    id: 'ledger',
    label: '功法·道具',
    icon: <Package size={16} />,
    accent: '#f59e0b',
    count: d => {
      const sa = (d.extra ?? {}).story_assets as { plot_assets?: unknown[] } | undefined
      const planned = arr(sa?.plot_assets).length
      return planned || (Object.keys(d.golden_finger ?? {}).length ? 1 : 0)
    },
    always: true,
  },
  { id: 'quality', label: '卷纲质检', icon: <ShieldCheck size={16} />, accent: '#10b981', count: d => (d.linter_report?.issue_count ?? 0), always: true },
]

/** 计算可见分区：始终显示项 + count>0 项。 */
export function visibleSections(d: DabaiProjectDetail): DabaiSectionCfg[] {
  return DABAI_SECTIONS.filter(s => s.always || s.count(d) > 0)
}
