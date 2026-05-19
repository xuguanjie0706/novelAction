import type { Edge, Node } from 'reactflow'
import { MarkerType } from 'reactflow'
import type { Faction } from '../../../types'
import {
  EDGE_STYLE,
  type DiagramLayout,
  type FactionEdge,
  type FactionEdgeKind,
} from '../factionRealmLayout'
import type {
  FactionCardNodeData,
  RealmBandNodeData,
  RealmSwimlaneData,
} from './nodes'

function dashToCss(dash?: string): string | undefined {
  if (!dash) return undefined
  return dash.replace(/\s+/g, ', ')
}

function buildFlowEdge(
  edge: FactionEdge,
  index: number,
  focusId: string | null,
  highlightIds: Set<string> | null,
): Edge {
  const style = EDGE_STYLE[edge.kind]
  const hasFocus = !!focusId && !!highlightIds
  const active =
    !hasFocus ||
    (highlightIds!.has(edge.fromId) && highlightIds!.has(edge.toId))

  return {
    id: `fe-${index}-${edge.fromId}-${edge.toId}`,
    source: edge.fromId,
    target: edge.toId,
    type: 'smoothstep',
    label: edge.label,
    labelStyle: {
      fontSize: 10,
      fill: style.stroke,
      fontWeight: 600,
    },
    labelBgStyle: {
      fill: '#ffffff',
      fillOpacity: 0.95,
    },
    labelBgPadding: [6, 8] as [number, number],
    labelBgBorderRadius: 6,
    style: {
      stroke: style.stroke,
      strokeWidth: edge.kind === 'rival' ? 2.25 : 1.75,
      strokeDasharray: dashToCss(style.dash),
      opacity: active ? 1 : hasFocus ? 0.15 : 0.85,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: style.stroke,
      width: 14,
      height: 14,
    },
    zIndex: active ? 2 : 0,
    animated: edge.kind === 'ally' && active,
  }
}

export interface BuildFlowGraphOptions {
  layout: DiagramLayout
  factions: Faction[]
  selectedId?: string | null
  onSelectFaction?: (f: Faction) => void
}

/**
 * 将 factionRealmLayout 产物转为 React Flow 节点/边。
 */
export function buildFactionFlowGraph(opts: BuildFlowGraphOptions): {
  nodes: Node[]
  edges: Edge[]
  highlightIds: Set<string> | null
} {
  const { layout, factions, selectedId, onSelectFaction } = opts
  const factionById = new Map(factions.map(f => [f.id, f]))

  let highlightIds: Set<string> | null = null
  if (selectedId) {
    highlightIds = new Set<string>([selectedId])
    for (const e of layout.edges) {
      if (e.fromId === selectedId) highlightIds.add(e.toId)
      if (e.toId === selectedId) highlightIds.add(e.fromId)
    }
  }

  const nodes: Node[] = []

  for (const band of layout.bands) {
    nodes.push({
      id: `swim-${band.bandIndex}`,
      type: 'realmSwimlane',
      position: { x: 0, y: band.y },
      data: {
        color: band.color,
        width: layout.width,
        height: layout.bandH,
      } satisfies RealmSwimlaneData,
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      zIndex: 0,
    })

    nodes.push({
      id: `realm-${band.bandIndex}`,
      type: 'realmBand',
      position: { x: 8, y: band.y + 2 },
      data: {
        level: band.level,
        color: band.color,
      } satisfies RealmBandNodeData,
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      zIndex: 1,
    })
  }

  for (const card of layout.cards) {
    const f = factionById.get(card.factionId)
    if (!f) continue
    const hasFocus = !!highlightIds
    const active = !hasFocus || highlightIds!.has(f.id)
    const selected = selectedId === f.id

    nodes.push({
      id: f.id,
      type: 'factionCard',
      position: { x: card.x, y: card.y },
      zIndex: selected ? 10 : active ? 4 : 2,
      data: {
        faction: f,
        selected,
        dimmed: hasFocus && !active,
        onSelect: onSelectFaction,
      } satisfies FactionCardNodeData,
      draggable: false,
    })
  }

  const edges = layout.edges.map((e, i) =>
    buildFlowEdge(e, i, selectedId ?? null, highlightIds),
  )

  return { nodes, edges, highlightIds }
}

export const FACTION_EDGE_LEGEND: { kind: FactionEdgeKind; label: string }[] = [
  { kind: 'control', label: '宗主/控制' },
  { kind: 'subordinate', label: '附庸' },
  { kind: 'ally', label: '盟友' },
  { kind: 'rival', label: '对立' },
]
