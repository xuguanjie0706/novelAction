/**
 * 阵营分层图 — ReactFlow 卡片节点 + 固定分区布局。
 */
import { useEffect } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { Character, CharacterRelationship } from '../../../types'
import { ROLE_COLOR } from './constants'
import { buildEdges, buildNodes, degreeMap } from './graphUtils'
import { CharCardNode } from './nodes'

const NODE_TYPES = { charCard: CharCardNode }

interface TierFlowGraphProps {
  characters: Character[]
  relationships: CharacterRelationship[]
  allCharacters: Character[]
  positions: Map<string, { x: number; y: number }>
  selectedId: string | null
  highlightIds: Set<string> | null
  onSelect: (c: Character | null) => void
}

function TierFlowGraphInner(props: TierFlowGraphProps) {
  const { fitView } = useReactFlow()
  const degrees = degreeMap(props.relationships)
  const focusId = props.selectedId

  const initialNodes = buildNodes(props.characters, props.positions, {
    variant: 'card',
    focusId,
    highlightIds: props.highlightIds,
    degrees,
    onSelect: props.onSelect,
  })

  const initialEdges = buildEdges(props.relationships, props.allCharacters, {
    dark: false,
    focusId,
    highlightIds: props.highlightIds,
  })

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes, setNodes])

  useEffect(() => {
    setEdges(initialEdges)
  }, [initialEdges, setEdges])

  useEffect(() => {
    const t = window.setTimeout(() => fitView({ padding: 0.22, duration: 350 }), 100)
    return () => window.clearTimeout(t)
  }, [props.characters.length, props.relationships.length, fitView])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.22 }}
      minZoom={0.25}
      maxZoom={2.5}
      proOptions={{ hideAttribution: true }}
      onPaneClick={() => props.onSelect(null)}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#e5e7eb" />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={n => {
          const role = (n.data as { character?: Character })?.character?.role
          return ROLE_COLOR[role ?? 'neutral']?.dot ?? '#9ca3af'
        }}
        maskColor="rgba(255,255,255,0.7)"
        style={{ borderRadius: 8 }}
      />
    </ReactFlow>
  )
}

export function TierFlowGraph(props: TierFlowGraphProps) {
  return (
    <ReactFlowProvider>
      <TierFlowGraphInner {...props} />
    </ReactFlowProvider>
  )
}
