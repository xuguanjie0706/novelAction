/**
 * 星座星图（3D）— 全图常驻 + 柔和高亮；点击仅平移视角，不 zoom 进单节点。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph3D, { type ForceGraphMethods } from 'react-force-graph-3d'
import type { Character, CharacterRelationship } from '../../../types'
import { dimHexColor, GRAPH_THEME, ROLE_LABEL, roleColor } from './constants'
import { type ForceGraphLink, type ForceGraphNode } from './forceGraphPaint'
import { useForceGraphBloom } from './useForceGraphBloom'

const CAMERA_FOCUS_DIST = 155

interface ConstellationForceGraphProps {
  characters: Character[]
  relationships: CharacterRelationship[]
  selectedId: string | null
  highlightIds: Set<string> | null
  onSelect: (c: Character | null) => void
}

function htmlNodeLabel(node: ForceGraphNode): string {
  const role = ROLE_LABEL[node.role] ?? '中立'
  const realm = node.character.current_realm
  return `<div style="
    padding:6px 10px;border-radius:8px;
    background:rgba(10,12,20,0.92);color:#e2e8f0;
    font:12px/1.4 system-ui,sans-serif;
    border:1px solid rgba(79,70,229,0.35);
  "><b>${node.name}</b><br/><span style="color:#94a3b8;font-size:10px">${role}${realm ? ` · ${realm}` : ''}</span></div>`
}

export function ConstellationForceGraph({
  characters,
  relationships,
  selectedId,
  highlightIds,
  onSelect,
}: ConstellationForceGraphProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods<ForceGraphNode, ForceGraphLink> | undefined>(undefined)
  const initialFitDone = useRef(false)
  const [size, setSize] = useState({ w: 800, h: 600 })

  const hasFocus = !!selectedId && !!highlightIds?.size

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const apply = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useForceGraphBloom(fgRef, size)

  const degreeMap = useMemo(() => {
    const m = new Map<string, number>()
    const bump = (id: string) => m.set(id, (m.get(id) ?? 0) + 1)
    for (const r of relationships) {
      bump(r.from_character_id)
      bump(r.to_character_id)
    }
    return m
  }, [relationships])

  const graphData = useMemo(() => {
    const nodes: ForceGraphNode[] = characters.map(c => ({
      id: c.id,
      name: c.name,
      role: c.role,
      character: c,
      val: Math.min(3.5, 0.8 + Math.sqrt(degreeMap.get(c.id) ?? 0) * 0.45 + (c.role === 'protagonist' ? 0.6 : 0)),
    }))
    const links: ForceGraphLink[] = relationships.map(r => ({
      source: r.from_character_id,
      target: r.to_character_id,
      relation_type: r.relation_type,
      intensity: r.intensity,
      is_dynamic: r.is_dynamic,
    }))
    return { nodes, links }
  }, [characters, relationships, degreeMap])

  /** 仅首次 / 数据量变化时全景 fit，选中节点不再 zoomToFit（避免光球炸屏） */
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || graphData.nodes.length === 0) return
    fg.d3Force('charge')?.strength(-85)
    fg.d3Force('link')?.distance(58)
    if (selectedId) return
    const t = window.setTimeout(() => {
      fg.zoomToFit(500, 72)
      initialFitDone.current = true
    }, initialFitDone.current ? 0 : 520)
    return () => window.clearTimeout(t)
  }, [graphData.nodes.length, graphData.links.length, size.w, size.h, selectedId])

  const isHighlighted = useCallback(
    (id: string) => !hasFocus || highlightIds!.has(id),
    [hasFocus, highlightIds],
  )

  const isLinkActive = useCallback(
    (link: ForceGraphLink) => {
      if (!hasFocus) return true
      const sid = typeof link.source === 'object' ? link.source.id : link.source
      const tid = typeof link.target === 'object' ? link.target.id : link.target
      return highlightIds!.has(sid) && highlightIds!.has(tid)
    },
    [hasFocus, highlightIds],
  )

  const nodeColor = useCallback(
    (n: ForceGraphNode) => {
      const base = roleColor(n.role).dot
      if (isHighlighted(n.id)) return base
      return dimHexColor(base, 0.22)
    },
    [isHighlighted],
  )

  const linkColor = useCallback(
    (link: ForceGraphLink) => {
      const sid = typeof link.source === 'object' ? link.source.id : link.source
      const from = characters.find(c => c.id === sid)
      const base = roleColor(from?.role ?? 'neutral').dot
      if (isLinkActive(link)) return base
      return dimHexColor(base, hasFocus ? 0.12 : 0.32)
    },
    [characters, isLinkActive, hasFocus],
  )

  const focusCameraOnNode = useCallback((node: ForceGraphNode) => {
    const fg = fgRef.current
    if (!fg || node.x == null || node.y == null) return
    const nx = node.x
    const ny = node.y
    const nz = node.z ?? 0
    const d = CAMERA_FOCUS_DIST
    fg.cameraPosition(
      { x: nx + d * 0.35, y: ny + d * 0.28, z: nz + d * 0.75 },
      { x: nx, y: ny, z: nz },
      1400,
    )
  }, [])

  const handleNodeClick = useCallback(
    (node: ForceGraphNode) => {
      onSelect(node.character)
      window.setTimeout(() => focusCameraOnNode(node), 80)
    },
    [onSelect, focusCameraOnNode],
  )

  const handleBackgroundClick = useCallback(() => {
    onSelect(null)
    const fg = fgRef.current
    if (fg) fg.zoomToFit(700, 72)
  }, [onSelect])

  return (
    <div ref={wrapRef} className="absolute inset-0" style={{ background: GRAPH_THEME.canvasBg }}>
      <div className="absolute bottom-3 left-3 z-10 text-[10px] pointer-events-none select-none" style={{ color: GRAPH_THEME.textMuted }}>
        拖拽旋转 · 滚轮缩放 · 点击柔焦一度关系 · 点空白还原全景
      </div>
      <ForceGraph3D
        ref={fgRef}
        width={size.w}
        height={size.h}
        graphData={graphData}
        backgroundColor={GRAPH_THEME.canvasBg}
        showNavInfo={false}
        nodeColor={nodeColor}
        nodeVal="val"
        nodeLabel={htmlNodeLabel}
        linkColor={linkColor}
        linkOpacity={0.42}
        linkWidth={0.5}
        linkDirectionalParticles={(link: ForceGraphLink) => (isLinkActive(link) ? 1 : 0)}
        linkDirectionalParticleWidth={0.9}
        linkDirectionalParticleSpeed={0.005}
        linkLabel={(link: ForceGraphLink) =>
          isLinkActive(link)
            ? `<span style="color:#cbd5e1;font-size:10px">${link.relation_type}</span>`
            : ''
        }
        onNodeClick={handleNodeClick}
        onBackgroundClick={handleBackgroundClick}
        enableNodeDrag
        enableNavigationControls
        controlType="orbit"
        cooldownTicks={100}
        d3AlphaDecay={0.025}
        d3VelocityDecay={0.38}
      />
    </div>
  )
}
