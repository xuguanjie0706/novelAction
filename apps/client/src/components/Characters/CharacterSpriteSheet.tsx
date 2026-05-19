import React, { useMemo, useState } from 'react'
import clsx from 'clsx'
import { ImageIcon } from 'lucide-react'
import type { Character } from '../../types'

export interface SpriteSheetMeta {
  url: string
  avatar_url?: string
  cols?: number
  rows?: number
  frame_count?: number
  generated_at?: string
  provider_name?: string
}

export function getSpriteSheetMeta(char: Character): SpriteSheetMeta | null {
  const raw = char.extra?.sprite_sheet
  if (!raw || typeof raw !== 'object' || !raw.url) return null
  return raw as SpriteSheetMeta
}

interface CharacterSpriteSheetProps {
  character: Character
  className?: string
}

const FRAME_LABELS = ['正面', '侧身', '动作', '肖像']

/** 展示人物横排雪碧图；可切换预览单帧。 */
export default function CharacterSpriteSheet({ character, className }: CharacterSpriteSheetProps) {
  const meta = useMemo(() => getSpriteSheetMeta(character), [character])
  const cols = meta?.cols ?? 4
  const rows = meta?.rows ?? 1
  const frameCount = meta?.frame_count ?? cols * rows
  const [activeFrame, setActiveFrame] = useState(0)

  if (!meta?.url) {
    return (
      <div
        className={clsx(
          'flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50 text-gray-400 py-10',
          className,
        )}
      >
        <ImageIcon size={28} className="mb-2 opacity-50" />
        <p className="text-sm">尚未生成立绘雪碧图</p>
      </div>
    )
  }

  const colIndex = activeFrame % cols
  const rowIndex = Math.floor(activeFrame / cols)
  const bgX = cols <= 1 ? 0 : (colIndex / (cols - 1)) * 100
  const bgY = rows <= 1 ? 0 : (rowIndex / (rows - 1)) * 100

  return (
    <div className={clsx('space-y-3', className)}>
        <div className="rounded-xl border border-gray-200 overflow-hidden bg-gradient-to-b from-slate-100 to-slate-200">
        <div className="relative w-full" style={{ aspectRatio: `${cols} / ${rows}` }}>
          <img
            src={meta.url}
            alt={`${character.name} 立绘雪碧图`}
            className="w-full h-full object-contain"
            draggable={false}
          />
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {Array.from({ length: Math.min(frameCount, FRAME_LABELS.length) }).map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActiveFrame(i)}
            className={clsx(
              'text-xs px-2.5 py-1 rounded-lg border font-medium transition-colors',
              activeFrame === i
                ? 'bg-amber-100 text-amber-800 border-amber-300'
                : 'bg-white text-gray-500 border-gray-200 hover:border-gray-300',
            )}
          >
            {FRAME_LABELS[i] ?? `帧 ${i + 1}`}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-gray-100 overflow-hidden bg-white shadow-sm max-w-[200px]">
        <div
          className="w-full"
          style={{
            aspectRatio: '3 / 4',
            backgroundImage: `url(${meta.url})`,
            backgroundSize: `${cols * 100}% ${rows * 100}%`,
            backgroundPosition: `${bgX}% ${bgY}%`,
            backgroundRepeat: 'no-repeat',
          }}
        />
        <p className="text-[10px] text-center text-gray-400 py-1">当前帧预览</p>
      </div>

      {meta.generated_at && (
        <p className="text-[10px] text-gray-400">
          生成于 {new Date(meta.generated_at).toLocaleString('zh-CN')}
          {meta.provider_name ? ` · ${meta.provider_name}` : ''}
        </p>
      )}
    </div>
  )
}
