import { Handle, Position, type NodeProps } from 'reactflow'
import type { Character } from '../../../types'
import { ROLE_LABEL, roleColor } from './constants'

export interface CharNodeData {
  character: Character
  variant: 'star' | 'card'
  dimmed: boolean
  isCenter: boolean
  connectionCount: number
  onClick: (c: Character) => void
}

/** 星图节点：发光星点 + 姓名，连接越多星越大 */
export function CharStarNode({ data }: NodeProps<CharNodeData>) {
  const { character: c, dimmed, isCenter, connectionCount, onClick } = data
  const color = roleColor(c.role)
  const size = 10 + Math.min(connectionCount, 8) * 2 + (isCenter ? 6 : 0)

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <button
        type="button"
        onClick={() => onClick(c)}
        className="flex flex-col items-center gap-1.5 border-0 bg-transparent p-0 cursor-pointer select-none"
        style={{ opacity: dimmed ? 0.22 : 1, transition: 'opacity .2s' }}
      >
        <span
          className="rounded-full block"
          style={{
            width: size,
            height: size,
            background: `radial-gradient(circle at 35% 35%, #fff 0%, ${color.dot} 45%, ${color.border} 100%)`,
            boxShadow: isCenter
              ? `0 0 20px ${color.glow}, 0 0 40px ${color.glow}`
              : `0 0 10px ${color.glow}`,
          }}
        />
        <span
          className="text-[11px] font-semibold max-w-[88px] truncate text-center leading-tight"
          style={{ color: isCenter ? '#fef3c7' : '#e2e8f0', textShadow: '0 1px 6px rgba(0,0,0,0.8)' }}
        >
          {c.name}
        </span>
        {isCenter && (
          <span className="text-[9px] text-amber-200/80 tracking-wide">当前焦点</span>
        )}
      </button>
    </>
  )
}

/** 分层卡片节点 */
export function CharCardNode({ data }: NodeProps<CharNodeData>) {
  const { character: c, dimmed, isCenter, onClick } = data
  const color = roleColor(c.role)

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <button
        type="button"
        onClick={() => onClick(c)}
        className="text-left border-0 p-0 cursor-pointer select-none"
        style={{
          opacity: dimmed ? 0.35 : 1,
          background: color.bg,
          border: `2px solid ${isCenter ? color.border : `${color.border}99`}`,
          borderRadius: 12,
          padding: '8px 12px',
          minWidth: 90,
          maxWidth: 130,
          textAlign: 'center',
          boxShadow: isCenter
            ? `0 0 0 3px ${color.glow}, 0 4px 14px rgba(0,0,0,0.12)`
            : '0 1px 4px rgba(0,0,0,0.08)',
          transition: 'opacity .2s, box-shadow .15s',
        }}
      >
        <CharAvatarBadge name={c.name} border={color.border} />
        <div style={{ fontSize: 12, fontWeight: 600, color: color.text, lineHeight: 1.3, marginBottom: 3 }}>
          {c.name}
        </div>
        <div style={{ fontSize: 10, color: color.border, fontWeight: 500 }}>
          {ROLE_LABEL[c.role] ?? '中立'}
        </div>
        {c.current_realm && (
          <div
            style={{
              fontSize: 9,
              color: '#9ca3af',
              marginTop: 2,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {c.current_realm}
          </div>
        )}
      </button>
    </>
  )
}

function CharAvatarBadge({ name, border }: { name: string; border: string }) {
  return (
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: '50%',
        background: border,
        color: '#fff',
        fontSize: 15,
        fontWeight: 700,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '0 auto 6px',
      }}
    >
      {name.slice(0, 1)}
    </div>
  )
}
