import type { CSSProperties } from 'react'
import type { Character, CharacterRelationship } from '../../../types'
import type { Edge, Node } from 'reactflow'
import { MarkerType } from 'reactflow'
import { DYNAMIC_LABEL, intensityToWidth, roleColor } from './constants'
import type { CharNodeData } from './nodes'

export function neighborIds(
  charId: string,
  relationships: CharacterRelationship[],
): Set<string> {
  const set = new Set<string>([charId])
  for (const r of relationships) {
    if (r.from_character_id === charId) set.add(r.to_character_id)
    if (r.to_character_id === charId) set.add(r.from_character_id)
  }
  return set
}

export function relationsForCharacter(
  charId: string,
  relationships: CharacterRelationship[],
): CharacterRelationship[] {
  return relationships.filter(
    r => r.from_character_id === charId || r.to_character_id === charId,
  )
}

export function degreeMap(
  relationships: CharacterRelationship[],
): Map<string, number> {
  const m = new Map<string, number>()
  const bump = (id: string) => m.set(id, (m.get(id) ?? 0) + 1)
  for (const r of relationships) {
    bump(r.from_character_id)
    bump(r.to_character_id)
  }
  return m
}

function dynamicEdgeStyle(d: string, dark: boolean): CSSProperties {
  if (d === 'deteriorating') return { strokeDasharray: '6 4' }
  if (d === 'broken') return { strokeDasharray: '2 5', opacity: dark ? 0.35 : 0.45 }
  if (d === 'evolving') return { strokeDasharray: '8 3' }
  return {}
}

export function buildEdges(
  relationships: CharacterRelationship[],
  characters: Character[],
  opts: {
    dark: boolean
    focusId: string | null
    highlightIds: Set<string> | null
  },
): Edge[] {
  const charById = new Map(characters.map(c => [c.id, c]))
  const hasFocus = !!opts.focusId && !!opts.highlightIds

  return relationships.map(r => {
    const from = charById.get(r.from_character_id)
    const color = roleColor(from?.role ?? 'neutral')
    const stroke = opts.dark ? color.dot : color.border
    const active =
      !hasFocus ||
      (opts.highlightIds!.has(r.from_character_id) &&
        opts.highlightIds!.has(r.to_character_id))

    return {
      id: r.id,
      source: r.from_character_id,
      target: r.to_character_id,
      type: opts.dark ? 'default' : 'smoothstep',
      label: r.relation_type,
      labelStyle: {
        fontSize: 10,
        fill: opts.dark ? '#e2e8f0' : '#4b5563',
        fontWeight: 600,
      },
      labelBgStyle: {
        fill: opts.dark ? 'rgba(15,23,42,0.88)' : '#ffffff',
        fillOpacity: opts.dark ? 0.92 : 0.9,
      },
      labelBgPadding: [5, 7] as [number, number],
      labelBgBorderRadius: 6,
      style: {
        stroke,
        strokeWidth: intensityToWidth(r.intensity) + (active && hasFocus ? 1 : 0),
        opacity: active ? (opts.dark ? 0.92 : 1) : hasFocus ? 0.12 : opts.dark ? 0.55 : 0.7,
        filter: opts.dark && active ? `drop-shadow(0 0 4px ${color.glow})` : undefined,
        ...dynamicEdgeStyle(r.is_dynamic, opts.dark),
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: stroke,
        width: 12,
        height: 12,
      },
      animated: r.is_dynamic === 'evolving' && active,
      zIndex: active ? 2 : 0,
    }
  })
}

export function buildNodes(
  characters: Character[],
  positions: Map<string, { x: number; y: number }>,
  opts: {
    variant: 'star' | 'card'
    focusId: string | null
    highlightIds: Set<string> | null
    degrees: Map<string, number>
    onSelect: (c: Character) => void
  },
): Node<CharNodeData>[] {
  const hasFocus = !!opts.focusId && !!opts.highlightIds

  return characters.map(c => {
    const active = !hasFocus || opts.highlightIds!.has(c.id)
    const isCenter = opts.focusId === c.id
    return {
      id: c.id,
      type: opts.variant === 'star' ? 'charStar' : 'charCard',
      position: positions.get(c.id) ?? { x: 200, y: 200 },
      zIndex: isCenter ? 10 : active ? 3 : 1,
      data: {
        character: c,
        variant: opts.variant,
        dimmed: hasFocus && !active,
        isCenter,
        connectionCount: opts.degrees.get(c.id) ?? 0,
        onClick: opts.onSelect,
      },
    }
  })
}

export function relationRowLabel(
  rel: CharacterRelationship,
  selfId: string,
  nameById: Map<string, string>,
): { otherName: string; direction: string; type: string; dynamic: string } {
  const isFrom = rel.from_character_id === selfId
  const otherId = isFrom ? rel.to_character_id : rel.from_character_id
  return {
    otherName: nameById.get(otherId) ?? '未知',
    direction: isFrom ? '→' : '←',
    type: rel.relation_type,
    dynamic: DYNAMIC_LABEL[rel.is_dynamic] ?? rel.is_dynamic,
  }
}
