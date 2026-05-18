import { X } from 'lucide-react'
import type { Character } from '../../../types'
import { roleColor } from './constants'

interface CharMiniCardProps {
  character: Character
  dark?: boolean
  onClose: () => void
}

export function CharMiniCard({ character: c, dark, onClose }: CharMiniCardProps) {
  const color = roleColor(c.role)
  return (
    <div
      className={
        dark
          ? 'absolute bottom-4 right-4 z-10 rounded-2xl shadow-2xl border border-slate-700 bg-slate-900/95 p-4 w-56 backdrop-blur-sm'
          : 'absolute top-4 right-4 z-10 bg-white rounded-2xl shadow-xl border border-gray-100 p-4 w-56'
      }
      style={{ borderTop: `3px solid ${color.border}` }}
    >
      <button
        type="button"
        onClick={onClose}
        className={
          dark
            ? 'absolute top-3 right-3 text-slate-500 hover:text-slate-300'
            : 'absolute top-3 right-3 text-gray-300 hover:text-gray-500'
        }
      >
        <X size={14} />
      </button>
      <div className="flex items-center gap-3 mb-3">
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: '50%',
            background: color.border,
            color: '#fff',
            fontSize: 18,
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {c.name.slice(0, 1)}
        </div>
        <div>
          <div className={dark ? 'text-sm font-semibold text-slate-100' : 'text-sm font-semibold text-gray-800'}>
            {c.name}
          </div>
          {c.alias?.length > 0 && (
            <div className={dark ? 'text-[10px] text-slate-500' : 'text-[10px] text-gray-400'}>
              {c.alias.join(' / ')}
            </div>
          )}
        </div>
      </div>
      <div className={dark ? 'space-y-1.5 text-xs text-slate-300' : 'space-y-1.5 text-xs text-gray-600'}>
        {c.current_realm && <MiniRow dark={dark} label="境界" value={c.current_realm} />}
        {c.faction && <MiniRow dark={dark} label="势力" value={c.faction} />}
        {c.appearance && (
          <div className={dark ? 'mt-2 pt-2 border-t border-slate-700' : 'mt-2 pt-2 border-t border-gray-100'}>
            <div className={dark ? 'text-[10px] text-slate-500 mb-0.5' : 'text-[10px] text-gray-400 mb-0.5'}>外貌</div>
            <div className="line-clamp-3">{c.appearance}</div>
          </div>
        )}
      </div>
    </div>
  )
}

function MiniRow({ label, value, dark }: { label: string; value: string; dark?: boolean }) {
  return (
    <div className="flex items-start gap-1.5">
      <span className={dark ? 'text-slate-500 shrink-0' : 'text-gray-400 shrink-0'}>{label}</span>
      <span className={dark ? 'text-slate-200 break-words' : 'text-gray-700 break-words'}>{value}</span>
    </div>
  )
}
