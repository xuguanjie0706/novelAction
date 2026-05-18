import clsx from 'clsx'
import { Focus, Layers, Search, Sparkles, X } from 'lucide-react'
import type { Character, CharacterRelationship } from '../../../types'
import type { GraphLayoutMode } from './constants'
import { GRAPH_THEME, ROLE_LABEL, roleColor } from './constants'
import { relationRowLabel, relationsForCharacter } from './graphUtils'
import { OrbitPanel } from './OrbitPanel'

interface GraphSidebarProps {
  layoutMode: GraphLayoutMode
  onLayoutModeChange: (m: GraphLayoutMode) => void
  search: string
  onSearchChange: (q: string) => void
  roleFilter: string
  onRoleFilterChange: (r: string) => void
  characters: Character[]
  relationships: CharacterRelationship[]
  selected: Character | null
  onSelect: (c: Character | null) => void
  onFocusProtagonist: () => void
  stats: { people: number; edges: number }
}

export function GraphSidebar({
  layoutMode,
  onLayoutModeChange,
  search,
  onSearchChange,
  roleFilter,
  onRoleFilterChange,
  characters,
  relationships,
  selected,
  onSelect,
  onFocusProtagonist,
  stats,
}: GraphSidebarProps) {
  const isConstellation = layoutMode === 'constellation'
  const nameById = new Map(characters.map(c => [c.id, c.name]))

  const filteredList = characters.filter(c => {
    if (roleFilter !== 'all' && c.role !== roleFilter) return false
    if (!search.trim()) return true
    const q = search.trim().toLowerCase()
    return (
      c.name.toLowerCase().includes(q) ||
      (c.faction ?? '').toLowerCase().includes(q) ||
      (c.alias ?? []).some(a => a.toLowerCase().includes(q))
    )
  })

  const selectedRels = selected
    ? relationsForCharacter(selected.id, relationships)
    : []

  return (
    <aside
      className={clsx(
        'w-72 shrink-0 flex flex-col border-r overflow-hidden',
        isConstellation
          ? 'border-slate-800 text-slate-200'
          : 'bg-white border-gray-100 text-gray-800',
      )}
      style={isConstellation ? { background: GRAPH_THEME.sidebarBg } : undefined}
    >
      <div className={clsx('p-3 border-b shrink-0', isConstellation ? 'border-slate-800' : 'border-gray-100')}>
        <div className="flex items-center gap-1 mb-2">
          <button
            type="button"
            onClick={() => onLayoutModeChange('constellation')}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1 text-[10px] py-1.5 rounded-lg font-medium transition-colors',
              layoutMode === 'constellation'
                ? 'text-white shadow-sm'
                : isConstellation
                  ? 'text-slate-400 hover:bg-slate-800'
                  : 'text-gray-500 hover:bg-gray-50',
            )}
            style={layoutMode === 'constellation' && isConstellation ? { background: GRAPH_THEME.accent } : undefined}
          >
            <Sparkles size={11} /> 3D 星图
          </button>
          <button
            type="button"
            onClick={() => onLayoutModeChange('tier')}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1 text-[10px] py-1.5 rounded-lg font-medium transition-colors',
              layoutMode === 'tier'
                ? 'bg-amber-500 text-white shadow-sm'
                : isConstellation
                  ? 'text-slate-400 hover:bg-slate-800'
                  : 'text-gray-500 hover:bg-gray-50',
            )}
          >
            <Layers size={11} /> 阵营分层
          </button>
        </div>
        <p className={clsx('text-[10px] mb-2', isConstellation ? 'text-slate-500' : 'text-gray-400')}>
          {stats.people} 人 · {stats.edges} 条关系 · 点击节点高亮一度连接
        </p>
        <div className="relative mb-2">
          <Search size={12} className={clsx('absolute left-2.5 top-1/2 -translate-y-1/2', isConstellation ? 'text-slate-500' : 'text-gray-400')} />
          <input
            value={search}
            onChange={e => onSearchChange(e.target.value)}
            placeholder="搜索人物…"
            className={clsx(
              'w-full pl-7 pr-2 py-1.5 text-xs rounded-lg border focus:outline-none focus:ring-1',
              isConstellation
                ? 'bg-slate-900 border-slate-700 text-slate-100 focus:ring-indigo-500'
                : 'bg-gray-50 border-gray-200 focus:ring-amber-400',
            )}
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {['all', 'protagonist', 'antagonist', 'supporting', 'neutral'].map(r => (
            <button
              key={r}
              type="button"
              onClick={() => onRoleFilterChange(r)}
              className={clsx(
                'text-[9px] px-2 py-0.5 rounded-full border transition-colors',
                roleFilter === r
                  ? isConstellation
                    ? 'bg-indigo-900/80 border-indigo-500 text-indigo-100'
                    : 'bg-amber-50 border-amber-300 text-amber-800'
                  : isConstellation
                    ? 'border-slate-700 text-slate-500 hover:border-slate-500'
                    : 'border-gray-200 text-gray-500 hover:border-gray-300',
              )}
            >
              {r === 'all' ? '全部' : ROLE_LABEL[r]}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onFocusProtagonist}
          className={clsx(
            'mt-2 w-full flex items-center justify-center gap-1 text-[10px] py-1.5 rounded-lg border transition-colors',
            isConstellation
              ? 'border-slate-700 text-slate-300 hover:bg-slate-800'
              : 'border-gray-200 text-gray-600 hover:bg-gray-50',
          )}
        >
          <Focus size={11} /> 聚焦主角
        </button>
      </div>

      {selected && (
        <div className="px-3 pt-3 shrink-0">
          <OrbitPanel
            center={selected}
            relationships={relationships}
            characters={characters}
            onPick={onSelect}
          />
        </div>
      )}

      <div className="flex-1 overflow-y-auto min-h-0">
        {selected ? (
          <div className="p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold">{selected.name} 的关系</span>
              <button type="button" onClick={() => onSelect(null)} className="text-slate-500 hover:text-slate-300">
                <X size={12} />
              </button>
            </div>
            {selectedRels.length === 0 ? (
              <p className={clsx('text-[10px]', isConstellation ? 'text-slate-500' : 'text-gray-400')}>
                暂无关系记录（Bootstrap Step 11 会生成）
              </p>
            ) : (
              <ul className="space-y-1.5">
                {selectedRels.map(rel => {
                  const row = relationRowLabel(rel, selected.id, nameById)
                  const otherId =
                    rel.from_character_id === selected.id
                      ? rel.to_character_id
                      : rel.from_character_id
                  const other = characters.find(c => c.id === otherId)
                  return (
                    <li key={rel.id}>
                      <button
                        type="button"
                        onClick={() => other && onSelect(other)}
                        className={clsx(
                          'w-full text-left text-[11px] px-2 py-1.5 rounded-lg border transition-colors',
                          isConstellation
                            ? 'border-slate-800 hover:bg-slate-800/80'
                            : 'border-gray-100 hover:bg-amber-50/50',
                        )}
                      >
                        <span className="font-medium">{row.otherName}</span>
                        <span className={clsx('mx-1', isConstellation ? 'text-slate-500' : 'text-gray-400')}>
                          {row.direction}
                        </span>
                        <span className={isConstellation ? 'text-indigo-300' : 'text-amber-700'}>
                          {row.type}
                        </span>
                        <span className={clsx('ml-1 text-[9px]', isConstellation ? 'text-slate-600' : 'text-gray-400')}>
                          强度 {rel.intensity} · {row.dynamic}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        ) : (
          <div className="p-2">
            <p className={clsx('text-[10px] px-1 py-1 mb-1', isConstellation ? 'text-slate-500' : 'text-gray-400')}>
              人物列表（点击定位）
            </p>
            {filteredList.map(c => {
              const deg = relationsForCharacter(c.id, relationships).length
              const color = roleColor(c.role)
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onSelect(c)}
                  className={clsx(
                    'w-full flex items-center gap-2 text-left text-xs px-2 py-1.5 rounded-lg mb-0.5 transition-colors',
                    isConstellation ? 'hover:bg-slate-800' : 'hover:bg-gray-50',
                  )}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: color.dot }}
                  />
                  <span className="flex-1 truncate">{c.name}</span>
                  <span className={clsx('text-[9px]', isConstellation ? 'text-slate-600' : 'text-gray-400')}>
                    {deg} 连
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </aside>
  )
}
