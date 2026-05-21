/**
 * @file 人物页常量与筛选配置
 */
import type React from 'react'
import { Crown, User, Swords, Eye, Zap, Heart, TrendingUp, History } from 'lucide-react'

export const ROLE_META = {
  protagonist: { label: '主角', color: 'bg-amber-100 text-amber-700 border-amber-200', Icon: Crown },
  supporting: { label: '配角', color: 'bg-blue-100 text-blue-700 border-blue-200', Icon: User },
  antagonist: { label: '反派', color: 'bg-red-100 text-red-700 border-red-200', Icon: Swords },
  neutral: { label: '中立', color: 'bg-gray-100 text-gray-700 border-gray-200', Icon: User },
} as const

export const TIER_META: Record<string, { label: string; short: string; color: string; dot: string; desc: string }> = {
  core: { label: '核心长线', short: '长线', color: 'bg-violet-100 text-violet-700 border-violet-300', dot: 'bg-violet-500', desc: '贯穿全书，长期驱动主线' },
  arc: { label: '弧线支柱', short: '弧线', color: 'bg-blue-100 text-blue-700 border-blue-300', dot: 'bg-blue-500', desc: '某卷/某段主导剧情，随弧线完结淡出' },
  plot: { label: '剧情推手', short: '短期', color: 'bg-orange-100 text-orange-700 border-orange-300', dot: 'bg-orange-400', desc: '短期推进剧情节点后退场' },
  background: { label: '背景填充', short: '背景', color: 'bg-gray-100 text-gray-500 border-gray-300', dot: 'bg-gray-400', desc: '增加世界厚度，无强情节绑定' },
}

export const STATUS_META: Record<string, { label: string; dot: string }> = {
  alive: { label: '存活', dot: 'bg-green-500' },
  dead: { label: '已死', dot: 'bg-gray-400' },
  missing: { label: '失踪', dot: 'bg-yellow-500' },
  sealed: { label: '封印', dot: 'bg-purple-500' },
  transformed: { label: '变化', dot: 'bg-blue-500' },
}

export type DetailTab = 'basic' | 'appearance' | 'power' | 'depth' | 'growth' | 'changelog'

export const DETAIL_TABS: { key: DetailTab; label: string; icon: React.ElementType }[] = [
  { key: 'basic', label: '基础', icon: User },
  { key: 'appearance', label: '外貌风格', icon: Eye },
  { key: 'power', label: '实力体系', icon: Zap },
  { key: 'depth', label: '深度性格', icon: Heart },
  { key: 'growth', label: '成长轨迹', icon: TrendingUp },
  { key: 'changelog', label: '变更记录', icon: History },
]

export const CHANGE_FIELD_STYLE: Record<string, { dot: string; pill: string; label?: string }> = {
  current_realm: { dot: 'bg-violet-500', pill: 'bg-violet-50 text-violet-700 border-violet-200' },
  current_status: { dot: 'bg-red-500', pill: 'bg-red-50 text-red-700 border-red-200' },
  current_location: { dot: 'bg-blue-500', pill: 'bg-blue-50 text-blue-700 border-blue-200' },
  skill_gained: { dot: 'bg-emerald-500', pill: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  item_gained: { dot: 'bg-amber-500', pill: 'bg-amber-50 text-amber-700 border-amber-200' },
  item_lost: { dot: 'bg-orange-400', pill: 'bg-orange-50 text-orange-700 border-orange-200' },
  created: { dot: 'bg-orange-500', pill: 'bg-orange-50 text-orange-700 border-orange-200' },
  character_tier: { dot: 'bg-purple-400', pill: 'bg-purple-50 text-purple-700 border-purple-200' },
  faction: { dot: 'bg-cyan-500', pill: 'bg-cyan-50 text-cyan-700 border-cyan-200' },
  role: { dot: 'bg-gray-400', pill: 'bg-gray-50 text-gray-600 border-gray-200' },
}

export const SOURCE_META: Record<string, { label: string; color: string }> = {
  debrief: { label: '复盘', color: 'bg-blue-100 text-blue-700' },
  manual: { label: '手动', color: 'bg-gray-100 text-gray-600' },
  bootstrap: { label: '生成', color: 'bg-violet-100 text-violet-700' },
}

export type RoleFilter = 'all' | 'protagonist' | 'supporting' | 'antagonist' | 'neutral'
export type StatusFilter = 'all' | 'alive' | 'dead' | 'missing' | 'sealed' | 'transformed'
export type TierFilter = 'all' | 'core' | 'arc' | 'plot' | 'background'
export type GroupBy = 'role' | 'faction'

export const ROLE_CHIPS: { key: RoleFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'protagonist', label: '主角' },
  { key: 'antagonist', label: '反派' },
  { key: 'supporting', label: '配角' },
  { key: 'neutral', label: '中立' },
]

export const STATUS_CHIPS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'alive', label: '存活' },
  { key: 'dead', label: '死亡' },
  { key: 'missing', label: '失踪' },
  { key: 'sealed', label: '封印' },
]

export const TIER_CHIPS: { key: TierFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'core', label: '长线' },
  { key: 'arc', label: '弧线' },
  { key: 'plot', label: '短期' },
  { key: 'background', label: '背景' },
]
