/**
 * @file 世界观子 Tab 配置
 */
import type React from 'react'
import { GitBranch, Zap, Sword, Package, Shield, MapPin } from 'lucide-react'

export type SubTab = 'storylines' | 'power' | 'skills' | 'items' | 'factions' | 'locations'

export const SUB_TABS: { key: SubTab; label: string; icon: React.ElementType; color: string }[] = [
  { key: 'storylines', label: '故事线', icon: GitBranch, color: 'text-purple-600' },
  { key: 'power',      label: '境界体系', icon: Zap,       color: 'text-amber-600' },
  { key: 'skills',     label: '功法技能', icon: Sword,     color: 'text-blue-600'  },
  { key: 'items',      label: '道具法宝', icon: Package,   color: 'text-emerald-600'},
  { key: 'factions',   label: '势力',    icon: Shield,    color: 'text-red-600'   },
  { key: 'locations',  label: '地点',    icon: MapPin,    color: 'text-sky-600'   },
]
