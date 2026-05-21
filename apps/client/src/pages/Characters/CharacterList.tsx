/**
 * @file 人物列表侧栏（筛选 + 分组列表）
 */
import { Plus, Crown, Users, Search, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import type { Character } from '../../types'
import {
  ROLE_META, STATUS_META, TIER_META,
  ROLE_CHIPS, STATUS_CHIPS, TIER_CHIPS,
  type RoleFilter, type StatusFilter, type TierFilter, type GroupBy,
} from './shared/constants'
import { CharacterAvatar } from './shared/components'

export interface CharacterGroup {
  key: string
  label: string
  color: string
  chars: Character[]
}

export interface CharacterListProps {
  projectId: string
  characters: Character[]
  filteredChars: Character[]
  groups: CharacterGroup[]
  selected: Character | null
  hasFilter: boolean
  creating: boolean
  searchQ: string
  roleFilter: RoleFilter
  statusFilter: StatusFilter
  tierFilter: TierFilter
  groupBy: GroupBy
  onSearchChange: (q: string) => void
  onRoleFilter: (f: RoleFilter) => void
  onStatusFilter: (f: StatusFilter) => void
  onTierFilter: (f: TierFilter) => void
  onGroupBy: (g: GroupBy) => void
  onSelect: (c: Character) => void
  onCreate: () => void
  onOpenGraph: () => void
  onClearFilters: () => void
}

export function CharacterList(props: CharacterListProps) {
  const {
    projectId, characters, filteredChars, groups, selected, hasFilter, creating,
    searchQ, roleFilter, statusFilter, tierFilter, groupBy,
    onSearchChange, onRoleFilter, onStatusFilter, onTierFilter, onGroupBy,
    onSelect, onCreate, onOpenGraph, onClearFilters,
  } = props
  return (
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">

        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">人物库</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              {hasFilter ? `${filteredChars.length}/` : ''}{characters.length} 人
            </span>
            <button onClick={onCreate} disabled={creating} className="text-amber-500 hover:text-amber-600 disabled:opacity-50">
              <Plus size={16} />
            </button>
          </div>
        </div>

        {/* 关系图入口 */}
        <div className="px-3 pt-2 pb-1 shrink-0 space-y-1">
          <Link
            to={`/project/${projectId}/relations`}
            className="flex items-center justify-center gap-1.5 w-full py-2 rounded-lg text-xs font-medium bg-indigo-50 text-indigo-800 border border-indigo-200 hover:bg-indigo-100 transition-colors"
          >
            <Sparkles size={14} />
            打开星座关系图
          </Link>
          <button
            type="button"
            onClick={onOpenGraph}
            className="w-full text-[10px] text-gray-400 hover:text-indigo-600 transition-colors"
          >
            或在本页内嵌查看
          </button>
        </div>

        {/* 搜索框 */}
        <div className="px-3 pt-1 pb-1.5 shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              value={searchQ}
              onChange={e => onSearchChange(e.target.value)}
              placeholder="搜索姓名、势力…"
              className="w-full pl-7 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:bg-white transition-colors"
            />
            {searchQ && (
              <button onClick={() => onClearFilters()}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
            )}
          </div>
        </div>

        {/* 分组切换 */}
        <div className="px-3 pb-1.5 shrink-0">
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => onGroupBy('role')}
              className={clsx('flex-1 flex items-center justify-center gap-1 text-[10px] py-1 rounded-md font-medium transition-colors',
                groupBy === 'role' ? 'bg-white text-amber-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
              <Crown size={9} />按角色
            </button>
            <button
              onClick={() => onGroupBy('faction')}
              className={clsx('flex-1 flex items-center justify-center gap-1 text-[10px] py-1 rounded-md font-medium transition-colors',
                groupBy === 'faction' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
              <Users size={9} />按势力
            </button>
          </div>
        </div>

        {/* 角色筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <div className="flex gap-1 flex-wrap">
            {ROLE_CHIPS.map(chip => (
              <button key={chip.key} onClick={() => onRoleFilter(chip.key)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  roleFilter === chip.key
                    ? chip.key === 'all' ? 'bg-gray-700 text-white border-gray-700'
                      : ROLE_META[chip.key as keyof typeof ROLE_META]?.color + ' border-current'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* 状态筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <div className="flex gap-1 flex-wrap">
            {STATUS_CHIPS.map(chip => (
              <button key={chip.key} onClick={() => onStatusFilter(chip.key)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  statusFilter === chip.key
                    ? 'bg-gray-700 text-white border-gray-700'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {chip.key !== 'all' && (
                  <span className={clsx('inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle',
                    STATUS_META[chip.key]?.dot ?? 'bg-gray-400')} />
                )}
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* 叙事层级筛选 */}
        <div className="px-3 pb-2 shrink-0">
          <div className="text-[9px] font-semibold text-gray-400 uppercase tracking-wider mb-1">叙事层级</div>
          <div className="flex gap-1 flex-wrap">
            {TIER_CHIPS.map(chip => {
              const tm = TIER_META[chip.key as string]
              return (
                <button key={chip.key} onClick={() => onTierFilter(chip.key)}
                  className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                    tierFilter === chip.key
                      ? chip.key === 'all'
                        ? 'bg-gray-700 text-white border-gray-700'
                        : tm.color + ' shadow-sm'
                      : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                  {tm && chip.key !== 'all' && (
                    <span className={clsx('inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle', tm.dot)} />
                  )}
                  {chip.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-auto border-t border-gray-100">
          {groups.length > 0 ? groups.map(group => (
            <div key={group.key} className="mb-1">
              <div className="px-3 pt-2 pb-1 flex items-center gap-1.5">
                <span className={clsx('text-[10px] font-semibold px-1.5 py-0.5 rounded-full border', group.color)}>
                  {group.label}
                </span>
                <span className="text-[10px] text-gray-400">{group.chars.length}</span>
              </div>
              {group.chars.map(c => {
                const sm = STATUS_META[c.current_status ?? 'alive'] ?? STATUS_META.alive
                const rm = ROLE_META[c.role as keyof typeof ROLE_META] ?? ROLE_META.supporting
                return (
                  <button key={c.id} onClick={() => onSelect(c)}
                    className={clsx('w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors border-l-2',
                      selected?.id === c.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                    <div className="relative shrink-0">
                      <CharacterAvatar char={c} size="sm" />
                      <span className={clsx('absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border-2 border-white', sm.dot)} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="text-xs font-medium text-gray-800 truncate">{c.name}</span>
                        {groupBy === 'faction' && c.role && (
                          <span className={clsx('shrink-0 text-[9px] px-1 rounded border', rm.color)}>{rm.label}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {/* 叙事层级 badge */}
                        {(() => {
                          const tier = c.character_tier ?? 'core'
                          const tm = TIER_META[tier]
                          return tm ? (
                            <span className={clsx('shrink-0 text-[9px] px-1 py-px rounded border leading-tight font-medium', tm.color)}>
                              {tm.short}
                            </span>
                          ) : null
                        })()}
                        <span className="text-[10px] text-gray-400 truncate">
                          {groupBy === 'role'
                            ? (c.current_realm ?? c.faction ?? c.current_location ?? c.gender ?? '')
                            : (c.current_realm ?? c.faction_rank ?? c.gender ?? '')}
                        </span>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )) : (
            <div className="py-10 text-center">
              {characters.length === 0
                ? <p className="text-xs text-gray-400 px-4">暂无人物，点击 + 创建</p>
                : <p className="text-xs text-gray-400 px-4">无匹配人物<br /><button type="button" onClick={onClearFilters} className="mt-1 text-amber-500 hover:underline">清除筛选</button></p>
              }
            </div>
          )}
        </div>
      </div>
  )
}
