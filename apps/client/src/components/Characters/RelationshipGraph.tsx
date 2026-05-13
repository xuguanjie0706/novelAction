/**
 * RelationshipGraph — 人物关系图（只读）
 *
 * 职责：以 ReactFlow 渲染项目内所有人物节点及其关系连线，
 * 支持拖拽布局、缩放、minimap；点击节点弹出人物小卡片。
 *
 * 数据来源：
 *   - 节点：来自 Zustand store 的 characters[]
 *   - 边：GET /api/v1/projects/{pid}/characters/relationships/all
 *
 * 约束：只读展示，不支持在图上增删关系（需在人物详情页操作）。
 *
 * @see CharacterRelationship（apps/client/src/types/index.ts）
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  MarkerType,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  NodeProps,
  BackgroundVariant,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { charactersApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Character, CharacterRelationship } from '../../types'
import clsx from 'clsx'
import { X, Loader2, Users } from 'lucide-react'

// ── 常量 ──────────────────────────────────────────────────

/** 角色 → 节点主色，与 CharactersPage 保持一致 */
const ROLE_COLOR: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  protagonist: { bg: '#fffbeb', border: '#f59e0b', text: '#92400e', dot: '#f59e0b' },
  antagonist:  { bg: '#fff1f2', border: '#f43f5e', text: '#9f1239', dot: '#f43f5e' },
  supporting:  { bg: '#eff6ff', border: '#3b82f6', text: '#1e40af', dot: '#3b82f6' },
  neutral:     { bg: '#f9fafb', border: '#9ca3af', text: '#374151', dot: '#9ca3af' },
}

const ROLE_LABEL: Record<string, string> = {
  protagonist: '主角',
  antagonist: '反派',
  supporting: '配角',
  neutral: '中立',
}

/** 关系强度 → 边线宽度（1-10 映射到 1-4px） */
const intensityToWidth = (n: number) => 1 + Math.round((n - 1) / 9 * 3)

/** 动态类型 → 边线样式 */
const dynamicToStyle = (d: string): React.CSSProperties => {
  if (d === 'deteriorating') return { strokeDasharray: '6 3' }
  if (d === 'broken')        return { strokeDasharray: '2 4', opacity: 0.4 }
  if (d === 'evolving')      return { strokeDasharray: '8 2' }
  return {}
}

/** 自动布局：按角色分层，主角中心，支角外围 */
function autoLayout(characters: Character[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const groups: Record<string, Character[]> = {
    protagonist: [],
    antagonist: [],
    supporting: [],
    neutral: [],
  }
  characters.forEach(c => {
    const g = groups[c.role] ?? groups.neutral
    g.push(c)
  })

  const placeGroup = (chars: Character[], cx: number, cy: number, radius: number) => {
    chars.forEach((c, i) => {
      const angle = (2 * Math.PI * i) / Math.max(chars.length, 1) - Math.PI / 2
      positions.set(c.id, {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      })
    })
  }

  placeGroup(groups.protagonist, 400, 300, groups.protagonist.length <= 1 ? 0 : 100)
  placeGroup(groups.antagonist,  750, 150, 120)
  placeGroup(groups.supporting,  400, 550, 180)
  placeGroup(groups.neutral,     100, 300, 100)

  return positions
}

// ── 自定义节点 ────────────────────────────────────────────

interface CharNodeData {
  character: Character
  onClick: (c: Character) => void
}

/**
 * CharNode — ReactFlow 自定义节点，展示人物头像缩写、姓名、角色标签。
 * 点击时调用 onClick 展开人物小卡片。
 */
function CharNode({ data }: NodeProps<CharNodeData>) {
  const { character: c, onClick } = data
  const color = ROLE_COLOR[c.role] ?? ROLE_COLOR.neutral

  return (
    <>
      <Handle type="target" position={Position.Top}    style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Left}   style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right}  style={{ opacity: 0 }} />
      <div
        onClick={() => onClick(c)}
        className="cursor-pointer select-none"
        style={{
          background: color.bg,
          border: `2px solid ${color.border}`,
          borderRadius: 12,
          padding: '8px 12px',
          minWidth: 90,
          maxWidth: 130,
          textAlign: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          transition: 'box-shadow .15s',
        }}
        onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)')}
        onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.08)')}
      >
        {/* 头像缩写 */}
        <div
          style={{
            width: 36, height: 36,
            borderRadius: '50%',
            background: color.border,
            color: '#fff',
            fontSize: 15,
            fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 6px',
          }}
        >
          {c.name.slice(0, 1)}
        </div>
        {/* 姓名 */}
        <div style={{ fontSize: 12, fontWeight: 600, color: color.text, lineHeight: 1.3, marginBottom: 3 }}>
          {c.name}
        </div>
        {/* 角色标签 */}
        <div style={{ fontSize: 10, color: color.border, fontWeight: 500 }}>
          {ROLE_LABEL[c.role] ?? '中立'}
        </div>
        {/* 境界（若有） */}
        {c.current_realm && (
          <div style={{ fontSize: 9, color: '#9ca3af', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {c.current_realm}
          </div>
        )}
      </div>
    </>
  )
}

const NODE_TYPES = { charNode: CharNode }

// ── 人物小卡片（点击节点弹出） ─────────────────────────────

interface CharMiniCardProps {
  character: Character
  onClose: () => void
}

/** CharMiniCard — 悬浮在图右侧的人物简要信息卡，点击关闭或点击其他节点切换。 */
function CharMiniCard({ character: c, onClose }: CharMiniCardProps) {
  const color = ROLE_COLOR[c.role] ?? ROLE_COLOR.neutral
  return (
    <div
      className="absolute top-4 right-4 z-10 bg-white rounded-2xl shadow-xl border border-gray-100 p-4 w-56 animate-fade-in"
      style={{ borderTop: `3px solid ${color.border}` }}
    >
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-gray-300 hover:text-gray-500"
      >
        <X size={14} />
      </button>
      {/* 头像 + 姓名 */}
      <div className="flex items-center gap-3 mb-3">
        <div
          style={{ width: 40, height: 40, borderRadius: '50%', background: color.border, color: '#fff', fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
        >
          {c.name.slice(0, 1)}
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-800">{c.name}</div>
          {c.alias?.length > 0 && (
            <div className="text-[10px] text-gray-400">{c.alias.join(' / ')}</div>
          )}
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-gray-600">
        {c.current_realm && <MiniRow label="境界" value={c.current_realm} />}
        {c.faction && <MiniRow label="势力" value={c.faction} />}
        {c.gender && <MiniRow label="性别" value={c.gender} />}
        {c.age && <MiniRow label="年龄" value={c.age} />}
        {c.current_status && c.current_status !== 'alive' && (
          <MiniRow label="状态" value={{ dead: '已死', missing: '失踪', sealed: '封印', transformed: '变化' }[c.current_status] ?? c.current_status} />
        )}
        {c.appearance && (
          <div className="mt-2 pt-2 border-t border-gray-100">
            <div className="text-[10px] text-gray-400 mb-0.5">外貌</div>
            <div className="text-gray-600 line-clamp-3">{c.appearance}</div>
          </div>
        )}
      </div>
    </div>
  )
}

function MiniRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5">
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className="text-gray-700 break-words">{value}</span>
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────

interface RelationshipGraphProps {
  /** 所属项目 ID */
  projectId: string
}

/**
 * RelationshipGraph — 人物关系全图（ReactFlow v11）。
 *
 * 生命周期：
 *   1. 从 store 取 characters（已在 CharactersPage 加载）
 *   2. 首次渲染时拉取 relationships/all
 *   3. 自动布局（按角色分层）→ 生成 nodes/edges → 交给 ReactFlow
 *
 * 交互：
 *   - 拖拽节点调整布局（ReactFlow 内置）
 *   - 点击节点展开右侧小卡片
 *   - minimap + controls（缩放/重置）
 */
export default function RelationshipGraph({ projectId }: RelationshipGraphProps) {
  const { characters } = useAppStore()
  const [relationships, setRelationships] = useState<CharacterRelationship[]>([])
  const [loading, setLoading]             = useState(false)
  const [selected, setSelected]           = useState<Character | null>(null)

  // ── 数据拉取 ────────────────────────────────────────────
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    charactersApi.listRelationships(projectId)
      .then(res => setRelationships(res.data))
      .catch(() => {/* toast 由 axios 拦截器已处理 */})
      .finally(() => setLoading(false))
  }, [projectId])

  // ── 自动布局 ────────────────────────────────────────────
  const positions = useMemo(() => autoLayout(characters), [characters])

  // ── 构建 ReactFlow nodes ─────────────────────────────────
  const initialNodes: Node<CharNodeData>[] = useMemo(() =>
    characters.map(c => ({
      id: c.id,
      type: 'charNode',
      position: positions.get(c.id) ?? { x: Math.random() * 600, y: Math.random() * 400 },
      data: { character: c, onClick: setSelected },
    })),
    [characters, positions]
  )

  // ── 构建 ReactFlow edges ─────────────────────────────────
  const initialEdges: Edge[] = useMemo(() =>
    relationships.map(r => {
      const color = ROLE_COLOR[
        characters.find(c => c.id === r.from_character_id)?.role ?? 'neutral'
      ]?.dot ?? '#9ca3af'
      return {
        id: r.id,
        source: r.from_character_id,
        target: r.to_character_id,
        label: r.relation_type,
        labelStyle: { fontSize: 10, fill: '#6b7280', fontWeight: 500 },
        labelBgStyle: { fill: '#ffffff', opacity: 0.85 },
        labelBgPadding: [4, 6] as [number, number],
        labelBgBorderRadius: 4,
        style: {
          stroke: color,
          strokeWidth: intensityToWidth(r.intensity),
          ...dynamicToStyle(r.is_dynamic),
        },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
        animated: r.is_dynamic === 'evolving',
      }
    }),
    [relationships, characters]
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange]         = useEdgesState(initialEdges)

  // 当 initialNodes / initialEdges 因数据变化重算时同步到 state
  useEffect(() => { setNodes(initialNodes) }, [initialNodes])

  // ── 空态 ────────────────────────────────────────────────
  if (!loading && characters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400">
        <Users size={40} className="mb-3 opacity-30" />
        <p className="text-sm">暂无人物数据</p>
        <p className="text-xs mt-1 text-gray-300">先在人物库创建角色，关系图将自动生成</p>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full">
      {/* 加载蒙层 */}
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/70 rounded-xl">
          <Loader2 size={28} className="animate-spin text-amber-400" />
        </div>
      )}

      {/* 图例 */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-3 bg-white/90 backdrop-blur-sm rounded-xl px-3 py-2 shadow-sm border border-gray-100 text-[10px]">
        {Object.entries(ROLE_COLOR).map(([role, c]) => (
          <span key={role} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ background: c.dot }} />
            <span className="text-gray-500">{ROLE_LABEL[role]}</span>
          </span>
        ))}
        <span className="text-gray-300 mx-1">|</span>
        <span className="text-gray-400">线粗 = 关系强度</span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        attributionPosition="bottom-left"
        onPaneClick={() => setSelected(null)}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e7eb" />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={n => ROLE_COLOR[(n.data as CharNodeData)?.character?.role]?.dot ?? '#9ca3af'}
          maskColor="rgba(255,255,255,0.7)"
          style={{ borderRadius: 8 }}
        />
      </ReactFlow>

      {/* 人物小卡片 */}
      {selected && (
        <CharMiniCard character={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
