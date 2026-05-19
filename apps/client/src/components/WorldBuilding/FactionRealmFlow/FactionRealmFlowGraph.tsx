/**
 * 势力 · 境界进阶关系图 — React Flow 实现（与人物关系图同栈）。
 */
import { useEffect, useMemo } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { Faction, PowerSystem } from '../../../types'
import { computeFactionRealmDiagramLayout, EDGE_STYLE } from '../factionRealmLayout'
import { buildFactionFlowGraph, FACTION_EDGE_LEGEND } from './buildFlowGraph'
import {
  FactionCardNode,
  RealmBandNode,
  RealmSwimlaneNode,
} from './nodes'

const NODE_TYPES = {
  realmSwimlane: RealmSwimlaneNode,
  realmBand: RealmBandNode,
  factionCard: FactionCardNode,
}

export interface FactionRealmFlowGraphProps {
  factions: Faction[]
  powerSystems: PowerSystem[]
  selectedId?: string | null
  onSelectFaction?: (faction: Faction | null) => void
}

function FactionRealmFlowInner({
  factions,
  powerSystems,
  selectedId,
  onSelectFaction,
}: FactionRealmFlowGraphProps) {
  const { fitView } = useReactFlow()

  const layout = useMemo(
    () => computeFactionRealmDiagramLayout(factions, powerSystems),
    [factions, powerSystems],
  )

  const graph = useMemo(
    () =>
      buildFactionFlowGraph({
        layout,
        factions,
        selectedId,
        onSelectFaction,
      }),
    [layout, factions, selectedId, onSelectFaction],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges)

  useEffect(() => {
    setNodes(graph.nodes)
  }, [graph.nodes, setNodes])

  useEffect(() => {
    setEdges(graph.edges)
  }, [graph.edges, setEdges])

  useEffect(() => {
    const t = window.setTimeout(
      () => fitView({ padding: 0.12, duration: 400, minZoom: 0.35, maxZoom: 1.2 }),
      120,
    )
    return () => window.clearTimeout(t)
  }, [factions.length, layout.bands.length, layout.edges.length, fitView])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnScroll
      zoomOnScroll
      minZoom={0.2}
      maxZoom={1.8}
      proOptions={{ hideAttribution: true }}
      onPaneClick={() => onSelectFaction?.(null)}
    >
      <Background variant={BackgroundVariant.Lines} gap={28} size={1} color="#e8ecf1" />
      <Controls showInteractive={false} className="!shadow-md !border-gray-200 !rounded-lg" />
      <MiniMap
        nodeColor={n => {
          if (n.type === 'factionCard') {
            const a = (n.data as { faction?: Faction })?.faction?.alignment
            if (a === 'antagonist') return '#fca5a5'
            if (a === 'protagonist') return '#86efac'
            return '#cbd5e1'
          }
          return '#f1f5f9'
        }}
        maskColor="rgba(248,250,252,0.85)"
        className="!rounded-lg !border !border-gray-200 !shadow-md"
        style={{ width: 140, height: 96 }}
      />

      <Panel position="top-center" className="!m-0 !mt-0 w-full pointer-events-none">
        <div className="bg-slate-800 text-white px-4 py-2.5 shadow-md text-center">
          <h2 className="text-base font-bold tracking-tight">势力 · 境界进阶关系图</h2>
          <p className="text-[10px] text-slate-400 mt-0.5">
            {layout.powerSystemName} · {factions.length} 个势力 · 滚轮缩放 · 拖拽平移
          </p>
        </div>
      </Panel>

      <Panel position="bottom-left" className="!mb-3 !ml-3 max-w-[92%] pointer-events-none">
        <div className="bg-white/95 backdrop-blur-sm border border-gray-200 rounded-xl shadow-lg px-4 py-3 text-xs text-slate-600">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-2">
            <span className="font-semibold text-slate-700">关系</span>
            {FACTION_EDGE_LEGEND.map(({ kind, label }) => (
              <span key={kind} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block w-5 h-0.5 rounded"
                  style={{
                    background: EDGE_STYLE[kind].stroke,
                    borderTop: EDGE_STYLE[kind].dash
                      ? `2px dashed ${EDGE_STYLE[kind].stroke}`
                      : undefined,
                  }}
                />
                {label}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-700 shrink-0">境界</span>
            {layout.bands.slice(0, 10).map(b => (
              <span
                key={b.level.rank}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md"
                style={{ background: b.color.bg, color: b.color.title }}
              >
                <span
                  className="w-2 h-2 rounded-sm shrink-0"
                  style={{ background: b.color.stroke }}
                />
                {b.level.name}
              </span>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 mt-2">
            纵轴由 top_power / strength_level 匹配境界；点击势力高亮关联连线
          </p>
        </div>
      </Panel>
    </ReactFlow>
  )
}

export default function FactionRealmFlowGraph(props: FactionRealmFlowGraphProps) {
  return (
    <ReactFlowProvider>
      <div className="h-full w-full bg-slate-50">
        <FactionRealmFlowInner {...props} />
      </div>
    </ReactFlowProvider>
  )
}
