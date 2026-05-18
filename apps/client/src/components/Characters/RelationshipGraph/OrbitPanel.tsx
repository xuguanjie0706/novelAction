import type { Character, CharacterRelationship } from '../../../types'
import { relationRowLabel, relationsForCharacter } from './graphUtils'
import { roleColor } from './constants'

interface OrbitPanelProps {
  center: Character
  relationships: CharacterRelationship[]
  characters: Character[]
  onPick: (c: Character) => void
}

/**
 * 轨道星图：以选中人物为「恒星」，直接关系为「卫星」轨道。
 * 与主画布星图配合，用于快速看清一度关系。
 */
export function OrbitPanel({ center, relationships, characters, onPick }: OrbitPanelProps) {
  const rels = relationsForCharacter(center.id, relationships)
  const nameById = new Map(characters.map(c => [c.id, c.name]))
  const charById = new Map(characters.map(c => [c.id, c]))
  const cx = 120
  const cy = 100
  const orbitR = 72

  const satellites = rels.map((rel, i) => {
    const otherId =
      rel.from_character_id === center.id ? rel.to_character_id : rel.from_character_id
    const angle = (2 * Math.PI * i) / Math.max(rels.length, 1) - Math.PI / 2
    return {
      rel,
      other: charById.get(otherId),
      x: cx + orbitR * Math.cos(angle),
      y: cy + orbitR * Math.sin(angle),
      label: relationRowLabel(rel, center.id, nameById),
    }
  })

  const centerColor = roleColor(center.role)

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/60 p-3">
      <div className="text-[10px] font-medium text-slate-400 mb-2 uppercase tracking-wider">
        轨道星图 · 一度关系
      </div>
      <svg viewBox="0 0 240 200" className="w-full h-[168px]">
        <circle cx={cx} cy={cy} r={orbitR} fill="none" stroke="rgba(148,163,184,0.25)" strokeDasharray="4 4" />
        {satellites.map(({ rel, other, x, y, label }, i) => {
          if (!other) return null
          const oc = roleColor(other.role)
          return (
            <g key={rel.id}>
              <line
                x1={cx}
                y1={cy}
                x2={x}
                y2={y}
                stroke={oc.dot}
                strokeOpacity={0.5}
                strokeWidth={1 + rel.intensity / 5}
              />
              <text
                x={(cx + x) / 2}
                y={(cy + y) / 2 - 4}
                textAnchor="middle"
                fill="#94a3b8"
                fontSize={8}
              >
                {label.type}
              </text>
              <g
                className="cursor-pointer"
                onClick={() => onPick(other)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && onPick(other)}
              >
                <circle cx={x} cy={y} r={10} fill={oc.dot} opacity={0.9} />
                <circle cx={x} cy={y} r={14} fill="none" stroke={oc.glow} strokeWidth={1} opacity={0.6} />
                <text x={x} y={y + 22} textAnchor="middle" fill="#e2e8f0" fontSize={9} fontWeight={600}>
                  {other.name.length > 5 ? `${other.name.slice(0, 5)}…` : other.name}
                </text>
              </g>
            </g>
          )
        })}
        <circle cx={cx} cy={cy} r={16} fill={centerColor.dot} />
        <circle cx={cx} cy={cy} r={22} fill="none" stroke={centerColor.glow} strokeWidth={2} />
        <text x={cx} y={cy + 34} textAnchor="middle" fill="#fef3c7" fontSize={10} fontWeight={700}>
          {center.name}
        </text>
      </svg>
      {rels.length === 0 && (
        <p className="text-[10px] text-slate-500 text-center -mt-2">暂无已记录关系</p>
      )}
    </div>
  )
}
