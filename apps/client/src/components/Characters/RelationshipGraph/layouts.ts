import type { Character, CharacterRelationship } from '../../../types'

/** 分层布局：按角色分区，便于看清阵营结构 */
export function tierLayout(characters: Character[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const groups: Record<string, Character[]> = {
    protagonist: [],
    antagonist: [],
    supporting: [],
    neutral: [],
  }
  characters.forEach(c => {
    ;(groups[c.role] ?? groups.neutral).push(c)
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
  placeGroup(groups.antagonist, 750, 150, 120)
  placeGroup(groups.supporting, 400, 550, 180)
  placeGroup(groups.neutral, 100, 300, 100)

  return positions
}

/**
 * 力导向「星座」布局：关系越密越靠近，主角锚定中心。
 */
export function constellationLayout(
  characters: Character[],
  relationships: CharacterRelationship[],
  size = { w: 900, h: 640 },
): Map<string, { x: number; y: number }> {
  if (characters.length === 0) return new Map()

  const { w, h } = size
  const cx = w / 2
  const cy = h / 2
  const nodes = characters.map((c, i) => {
    const angle = (2 * Math.PI * i) / characters.length
    const r = 80 + Math.random() * 40
    return {
      id: c.id,
      role: c.role,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
      vx: 0,
      vy: 0,
    }
  })
  const byId = new Map(nodes.map(n => [n.id, n]))
  const links = relationships
    .filter(r => byId.has(r.from_character_id) && byId.has(r.to_character_id))
    .map(r => ({
      source: r.from_character_id,
      target: r.to_character_id,
      pull: 0.4 + (r.intensity / 10) * 0.6,
    }))

  const protagonistIds = new Set(
    characters.filter(c => c.role === 'protagonist').map(c => c.id),
  )

  const iterations = Math.min(180, 60 + characters.length * 8)
  for (let t = 0; t < iterations; t++) {
    const cool = 1 - t / iterations

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        const dist = Math.max(Math.hypot(dx, dy), 12)
        const repulse = (4200 * cool) / (dist * dist)
        dx = (dx / dist) * repulse
        dy = (dy / dist) * repulse
        a.vx -= dx
        a.vy -= dy
        b.vx += dx
        b.vy += dy
      }
    }

    for (const link of links) {
      const a = byId.get(link.source)!
      const b = byId.get(link.target)!
      let dx = b.x - a.x
      let dy = b.y - a.y
      const dist = Math.max(Math.hypot(dx, dy), 1)
      const ideal = 100 + (12 - Math.min(links.length, 12)) * 6
      const force = ((dist - ideal) * 0.06 * cool) * link.pull
      dx = (dx / dist) * force
      dy = (dy / dist) * force
      a.vx += dx
      a.vy += dy
      b.vx -= dx
      b.vy -= dy
    }

    for (const n of nodes) {
      const toCenter = protagonistIds.has(n.id) ? 0.045 : 0.012
      n.vx += (cx - n.x) * toCenter * cool
      n.vy += (cy - n.y) * toCenter * cool
      n.x += n.vx * 0.35
      n.y += n.vy * 0.35
      n.vx *= 0.55
      n.vy *= 0.55
      n.x = Math.max(40, Math.min(w - 80, n.x))
      n.y = Math.max(40, Math.min(h - 80, n.y))
    }
  }

  return new Map(nodes.map(n => [n.id, { x: n.x - 36, y: n.y - 28 }]))
}
