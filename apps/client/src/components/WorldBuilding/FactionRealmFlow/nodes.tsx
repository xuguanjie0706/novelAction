import { Handle, Position, type NodeProps } from 'reactflow'
import clsx from 'clsx'
import type { Faction } from '../../../types'
import type { RealmBandColor } from '../factionRealmLayout'
import type { PowerLevel } from '../../../types'

const FACTION_TYPE_ICON: Record<string, string> = {
  sect: '🏯',
  kingdom: '👑',
  family: '🏠',
  guild: '💰',
  evil: '💀',
  race: '🌐',
  other: '⚙️',
}

const ALIGNMENT_STYLE: Record<string, { border: string; bg: string; badge: string }> = {
  protagonist: { border: '#22c55e', bg: '#f0fdf4', badge: '友方' },
  neutral:     { border: '#94a3b8', bg: '#ffffff', badge: '中立' },
  antagonist:  { border: '#ef4444', bg: '#fef2f2', badge: '敌方' },
  unknown:     { border: '#f59e0b', bg: '#fffbeb', badge: '不明' },
}

export interface RealmSwimlaneData {
  color: RealmBandColor
  width: number
  height: number
}

/** 全宽境界分带底色（不可交互） */
export function RealmSwimlaneNode({ data }: NodeProps<RealmSwimlaneData>) {
  return (
    <div
      className="pointer-events-none rounded-sm"
      style={{
        width: data.width,
        height: data.height,
        background: data.color.bg,
        borderBottom: '1px solid #e2e8f0',
        opacity: 0.92,
      }}
    />
  )
}

export interface RealmBandNodeData {
  level: PowerLevel
  color: RealmBandColor
}

/** 左侧境界说明卡 */
export function RealmBandNode({ data }: NodeProps<RealmBandNodeData>) {
  const { level, color } = data
  const desc = typeof level.description === 'string' ? level.description : ''
  const req = typeof level.requirements === 'string' ? level.requirements : ''

  return (
    <div
      className="pointer-events-none select-none rounded-lg shadow-sm"
      style={{
        width: 170,
        minHeight: 78,
        background: color.bg,
        border: `1.5px solid ${color.stroke}`,
        padding: '10px 12px',
      }}
    >
      <div className="text-sm font-bold text-center" style={{ color: color.title }}>
        {level.name}
      </div>
      <p className="text-[10px] text-center mt-1 leading-snug" style={{ color: color.sub }}>
        第{level.rank}境{desc ? ` · ${desc.slice(0, 16)}` : ''}
      </p>
      {req && (
        <p className="text-[9px] text-center mt-1.5 leading-snug" style={{ color: color.title }}>
          突破：{req.slice(0, 20)}
        </p>
      )}
    </div>
  )
}

export interface FactionCardNodeData {
  faction: Faction
  selected: boolean
  dimmed: boolean
  onSelect?: (f: Faction) => void
}

/** 势力卡片（可点击选中） */
export function FactionCardNode({ data }: NodeProps<FactionCardNodeData>) {
  const { faction: f, selected, dimmed, onSelect } = data
  const align = ALIGNMENT_STYLE[f.alignment] ?? ALIGNMENT_STYLE.neutral
  const icon = FACTION_TYPE_ICON[f.faction_type] ?? '⚙️'

  return (
    <>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-slate-300 !border-0" />
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-slate-300 !border-0" />
      <button
        type="button"
        onClick={() => onSelect?.(f)}
        className={clsx(
          'text-left border-0 p-0 cursor-pointer select-none transition-all duration-200',
          dimmed && 'opacity-40',
        )}
        style={{
          width: 168,
          minHeight: 88,
          background: align.bg,
          borderRadius: 12,
          border: `2px solid ${selected ? '#f59e0b' : align.border}`,
          boxShadow: selected
            ? '0 0 0 3px rgba(245,158,11,0.25), 0 8px 24px rgba(0,0,0,0.12)'
            : '0 4px 14px rgba(15,23,42,0.08)',
          padding: '10px 12px',
        }}
      >
        <div className="flex items-start justify-between gap-1 mb-1">
          <span className="text-sm font-bold text-slate-800 leading-tight truncate flex-1">
            {f.name}
          </span>
          <span
            className="shrink-0 text-[9px] px-1.5 py-0.5 rounded-full font-medium"
            style={{ background: `${align.border}22`, color: align.border }}
          >
            {align.badge}
          </span>
        </div>
        <p className="text-[10px] text-slate-500 truncate">
          {icon} {f.strength_level?.slice(0, 18) || '势力'}
        </p>
        {f.top_power && (
          <p className="text-[9px] text-slate-600 mt-1 truncate">顶战力 · {f.top_power.slice(0, 22)}</p>
        )}
        {f.member_count && (
          <p className="text-[9px] text-slate-400 mt-0.5 truncate">{f.member_count.slice(0, 24)}</p>
        )}
      </button>
    </>
  )
}
