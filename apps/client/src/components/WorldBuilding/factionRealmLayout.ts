import type { Faction, PowerLevel, PowerSystem } from '../../types'

/** 关系边类型：决定连线颜色与图例归类 */
export type FactionEdgeKind = 'subordinate' | 'ally' | 'rival' | 'control'

export interface FactionEdge {
  fromId: string
  toId: string
  kind: FactionEdgeKind
  label: string
}

export interface FactionCardLayout {
  factionId: string
  x: number
  y: number
  bandIndex: number
  matchedLevelName?: string
}

export interface RealmBandLayout {
  level: PowerLevel
  bandIndex: number
  y: number
  color: RealmBandColor
}

export interface RealmBandColor {
  bg: string
  stroke: string
  title: string
  sub: string
}

export interface DiagramLayout {
  width: number
  height: number
  headerH: number
  legendH: number
  sidebarW: number
  bandH: number
  cardW: number
  cardH: number
  bands: RealmBandLayout[]
  cards: FactionCardLayout[]
  edges: FactionEdge[]
  powerSystemName: string
}

const HEADER_H = 54
const LEGEND_H = 88
const SIDEBAR_W = 186
const BAND_H = 86
const CARD_W = 165
const CARD_H = 81
const CANVAS_W = 1100

const BAND_PALETTE: RealmBandColor[] = [
  { bg: '#fffbeb', stroke: '#fbbf24', title: '#92400e', sub: '#78350f' },
  { bg: '#faf5ff', stroke: '#c084fc', title: '#6b21a8', sub: '#7e22ce' },
  { bg: '#eff6ff', stroke: '#60a5fa', title: '#1e40af', sub: '#1d4ed8' },
  { bg: '#f0fdf4', stroke: '#34d399', title: '#15803d', sub: '#16a34a' },
  { bg: '#f7fee7', stroke: '#a3e635', title: '#3f6212', sub: '#4d7c0f' },
  { bg: '#f0fdf4', stroke: '#4ade80', title: '#166534', sub: '#15803d' },
  { bg: '#f1f5f9', stroke: '#94a3b8', title: '#334155', sub: '#475569' },
]

const EDGE_STYLE: Record<FactionEdgeKind, { stroke: string; dash?: string; label: string }> = {
  control:    { stroke: '#f59e0b', label: '宗主/控制' },
  subordinate:{ stroke: '#8b5cf6', dash: '4 3', label: '附庸' },
  ally:       { stroke: '#22c55e', dash: '6 4', label: '盟友' },
  rival:      { stroke: '#ef4444', dash: '7 4', label: '对立' },
}

export { EDGE_STYLE }

/**
 * 取项目主境界体系：优先 levels 最多的那条，供纵轴分带使用。
 */
export function pickPrimaryPowerSystem(systems: PowerSystem[]): PowerSystem | null {
  if (!systems.length) return null
  return [...systems].sort((a, b) => (b.levels?.length ?? 0) - (a.levels?.length ?? 0))[0]
}

/**
 * 境界按 rank 从高到低排列（高境界在画布上方）。
 */
export function sortLevelsForDisplay(levels: PowerLevel[]): PowerLevel[] {
  return [...levels].sort((a, b) => (b.rank ?? 0) - (a.rank ?? 0))
}

/**
 * 在势力文本字段中匹配境界名，返回分带索引（0 = 最高境）。
 */
export function matchFactionBandIndex(
  faction: Faction,
  displayLevels: PowerLevel[],
): { bandIndex: number; matchedLevelName?: string } {
  if (displayLevels.length === 0) return { bandIndex: 0 }

  const haystack = [faction.top_power, faction.strength_level, faction.description]
    .filter(Boolean)
    .join(' ')

  if (!haystack.trim()) {
    return { bandIndex: Math.floor(displayLevels.length / 2) }
  }

  const candidates = [...displayLevels].sort(
    (a, b) => (b.name?.length ?? 0) - (a.name?.length ?? 0),
  )

  let bestRank = -1
  let bestName: string | undefined

  for (const lvl of candidates) {
    const name = (lvl.name ?? '').trim()
    if (!name) continue
    const short = name.replace(/[境阶层期]/g, '')
    const hit =
      haystack.includes(name) ||
      (short.length >= 2 && haystack.includes(short))
    if (hit && (lvl.rank ?? 0) > bestRank) {
      bestRank = lvl.rank ?? 0
      bestName = name
    }
  }

  if (bestRank < 0) {
    return { bandIndex: Math.floor(displayLevels.length / 2) }
  }

  const bandIndex = displayLevels.findIndex(l => (l.rank ?? 0) === bestRank)
  return {
    bandIndex: bandIndex >= 0 ? bandIndex : Math.floor(displayLevels.length / 2),
    matchedLevelName: bestName,
  }
}

function resolveFactionIdByName(name: string, factions: Faction[]): string | null {
  const trimmed = name.trim()
  if (!trimmed) return null
  const exact = factions.find(f => f.name === trimmed)
  if (exact) return exact.id
  const loose = factions.find(
    f => f.name.includes(trimmed) || trimmed.includes(f.name),
  )
  return loose?.id ?? null
}

/**
 * 从 parent / allies / rivals 字段抽取有向关系边。
 */
export function buildFactionEdges(factions: Faction[]): FactionEdge[] {
  const edges: FactionEdge[] = []
  const seen = new Set<string>()

  const push = (edge: FactionEdge) => {
    const key = `${edge.kind}:${edge.fromId}:${edge.toId}`
    if (seen.has(key) || edge.fromId === edge.toId) return
    seen.add(key)
    edges.push(edge)
  }

  for (const f of factions) {
    if (f.parent_faction_id) {
      push({
        fromId: f.parent_faction_id,
        toId: f.id,
        kind: 'subordinate',
        label: EDGE_STYLE.subordinate.label,
      })
    }
    for (const allyName of f.allies ?? []) {
      const tid = resolveFactionIdByName(String(allyName), factions)
      if (tid) {
        push({ fromId: f.id, toId: tid, kind: 'ally', label: EDGE_STYLE.ally.label })
      }
    }
    for (const rivalName of f.rivals ?? []) {
      const tid = resolveFactionIdByName(String(rivalName), factions)
      if (tid) {
        push({ fromId: f.id, toId: tid, kind: 'rival', label: EDGE_STYLE.rival.label })
      }
    }
  }

  return edges
}

/**
 * 计算整张势力·境界关系图的布局（纯函数，便于单测）。
 */
export function computeFactionRealmDiagramLayout(
  factions: Faction[],
  powerSystems: PowerSystem[],
): DiagramLayout {
  const primary = pickPrimaryPowerSystem(powerSystems)
  const displayLevels = sortLevelsForDisplay(primary?.levels ?? [])
  const bandCount = Math.max(displayLevels.length, 1)
  const contentH = bandCount * BAND_H
  const height = HEADER_H + contentH + LEGEND_H

  const bands: RealmBandLayout[] = displayLevels.map((level, bandIndex) => ({
    level,
    bandIndex,
    y: HEADER_H + bandIndex * BAND_H,
    color: BAND_PALETTE[bandIndex % BAND_PALETTE.length],
  }))

  const byBand = new Map<number, Faction[]>()
  for (const f of factions) {
    const { bandIndex } = matchFactionBandIndex(f, displayLevels)
    const list = byBand.get(bandIndex) ?? []
    list.push(f)
    byBand.set(bandIndex, list)
  }

  const cards: FactionCardLayout[] = []
  for (const [bandIndex, group] of byBand) {
    const y = HEADER_H + bandIndex * BAND_H + 3
    const startX = SIDEBAR_W + 12
    const maxX = CANVAS_W - CARD_W - 16
    const n = group.length
    const span = maxX - startX
    group.forEach((f, i) => {
      const x =
        n <= 1
          ? startX + span / 2 - CARD_W / 2
          : startX + (span * i) / Math.max(n - 1, 1)
      const { matchedLevelName } = matchFactionBandIndex(f, displayLevels)
      cards.push({
        factionId: f.id,
        x: Math.min(Math.max(x, startX), maxX),
        y,
        bandIndex,
        matchedLevelName,
      })
    })
  }

  return {
    width: CANVAS_W,
    height,
    headerH: HEADER_H,
    legendH: LEGEND_H,
    sidebarW: SIDEBAR_W,
    bandH: BAND_H,
    cardW: CARD_W,
    cardH: CARD_H,
    bands,
    cards,
    edges: buildFactionEdges(factions),
    powerSystemName: primary?.name ?? '未配置境界体系',
  }
}

export function getCardCenter(card: FactionCardLayout, layout: DiagramLayout): { x: number; y: number } {
  return {
    x: card.x + layout.cardW / 2,
    y: card.y + layout.cardH / 2,
  }
}
