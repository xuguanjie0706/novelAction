/**
 * RelationshipGraph — 人物关系可视化
 * - 星座星图：react-force-graph-3d（MIT，Three.js 3D 力导向 + 粒子连线）
 * - 阵营分层：ReactFlow 卡片布局
 */
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2, Users } from 'lucide-react'
import clsx from 'clsx'
import { charactersApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { Character, CharacterRelationship } from '../../../types'
import type { GraphLayoutMode } from './constants'
import { GRAPH_THEME, ROLE_COLOR, ROLE_LABEL } from './constants'
import { tierLayout } from './layouts'
import { neighborIds } from './graphUtils'
import { GraphSidebar } from './GraphSidebar'
import { CharMiniCard } from './CharMiniCard'
import PageSpinner from '../../common/PageSpinner'

const ConstellationForceGraph = lazy(() =>
  import('./ConstellationForceGraph').then(m => ({ default: m.ConstellationForceGraph })),
)
const TierFlowGraph = lazy(() =>
  import('./TierFlowGraph').then(m => ({ default: m.TierFlowGraph })),
)

interface RelationshipGraphProps {
  projectId: string
}

export default function RelationshipGraph({ projectId }: RelationshipGraphProps) {
  const { characters: allCharacters } = useAppStore()

  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>('constellation')
  const [relationships, setRelationships] = useState<CharacterRelationship[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Character | null>(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')

  const isConstellation = layoutMode === 'constellation'

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    charactersApi
      .listRelationships(projectId)
      .then(res => setRelationships(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [projectId])

  const visibleCharacters = useMemo(() => {
    return allCharacters.filter(c => {
      if (roleFilter !== 'all' && c.role !== roleFilter) return false
      if (!search.trim()) return true
      const q = search.trim().toLowerCase()
      return (
        c.name.toLowerCase().includes(q) ||
        (c.faction ?? '').toLowerCase().includes(q) ||
        (c.alias ?? []).some(a => a.toLowerCase().includes(q))
      )
    })
  }, [allCharacters, roleFilter, search])

  const highlightIds = useMemo(
    () => (selected ? neighborIds(selected.id, relationships) : null),
    [selected, relationships],
  )

  const visibleIds = useMemo(
    () => new Set(visibleCharacters.map(c => c.id)),
    [visibleCharacters],
  )

  const visibleRelationships = useMemo(
    () =>
      relationships.filter(
        r =>
          visibleIds.has(r.from_character_id) && visibleIds.has(r.to_character_id),
      ),
    [relationships, visibleIds],
  )

  const tierPositions = useMemo(
    () => tierLayout(visibleCharacters),
    [visibleCharacters],
  )

  const handleFocusProtagonist = useCallback(() => {
    const p = allCharacters.find(c => c.role === 'protagonist')
    if (p) setSelected(p)
    else if (allCharacters[0]) setSelected(allCharacters[0])
  }, [allCharacters])

  if (!loading && allCharacters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400">
        <Users size={40} className="mb-3 opacity-30" />
        <p className="text-sm">暂无人物数据</p>
        <p className="text-xs mt-1 text-gray-300">先在人物库创建角色，关系图将自动生成</p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full">
      <GraphSidebar
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        search={search}
        onSearchChange={setSearch}
        roleFilter={roleFilter}
        onRoleFilterChange={setRoleFilter}
        characters={allCharacters}
        relationships={relationships}
        selected={selected}
        onSelect={setSelected}
        onFocusProtagonist={handleFocusProtagonist}
        stats={{ people: allCharacters.length, edges: relationships.length }}
      />

      <div
        className={clsx(
          'relative flex-1 min-w-0 min-h-0',
          isConstellation ? '' : 'bg-slate-50',
        )}
        style={isConstellation ? { background: GRAPH_THEME.canvasBg } : undefined}
      >

        {loading && (
          <div
            className={clsx(
              'absolute inset-0 z-20 flex items-center justify-center',
              isConstellation ? 'bg-slate-950/60' : 'bg-white/70',
            )}
          >
            <Loader2 size={28} className="animate-spin text-amber-400" />
          </div>
        )}

        <div
          className={clsx(
            'absolute top-3 right-3 z-10 flex items-center gap-2 rounded-xl px-3 py-2 text-[10px] shadow-sm border backdrop-blur-sm',
            isConstellation
              ? 'border-slate-700 text-slate-400'
              : 'bg-white/90 border-gray-100',
          )}
          style={isConstellation ? { background: 'rgba(10,12,20,0.85)' } : undefined}
        >
          {Object.entries(ROLE_COLOR).map(([role, c]) => (
            <span key={role} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: c.dot }} />
              <span>{ROLE_LABEL[role]}</span>
            </span>
          ))}
        </div>

        <Suspense fallback={<PageSpinner label="关系图渲染中…" />}>
          {isConstellation ? (
            <ConstellationForceGraph
              characters={visibleCharacters}
              relationships={visibleRelationships}
              selectedId={selected?.id ?? null}
              highlightIds={highlightIds}
              onSelect={setSelected}
            />
          ) : (
            <div className="absolute inset-0">
              <TierFlowGraph
                characters={visibleCharacters}
                relationships={visibleRelationships}
                allCharacters={allCharacters}
                positions={tierPositions}
                selectedId={selected?.id ?? null}
                highlightIds={highlightIds}
                onSelect={setSelected}
              />
            </div>
          )}
        </Suspense>

        {selected && !isConstellation && (
          <CharMiniCard
            character={selected}
            dark={false}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
    </div>
  )
}
