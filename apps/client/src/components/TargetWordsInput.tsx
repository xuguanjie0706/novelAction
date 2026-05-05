import React, { useState } from 'react'
import clsx from 'clsx'

export type TargetWordsInputProps = {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  disabled?: boolean
  className?: string
  /** 控件右侧的补充说明（单位「字」已内置在控件内） */
  hint?: React.ReactNode
}

export function TargetWordsInput({
  value,
  onChange,
  min = 300_000,
  max = 5_000_000,
  disabled,
  className,
  hint,
}: TargetWordsInputProps) {
  const [focused, setFocused] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)

  const clamp = (n: number) => Math.min(max, Math.max(min, n))

  const display =
    focused && draft !== null ? draft : value.toLocaleString('zh-CN')

  const commit = () => {
    const raw = (draft ?? '').replace(/\D/g, '')
    if (raw === '') {
      onChange(min)
      return
    }
    const parsed = parseInt(raw, 10)
    onChange(clamp(Number.isFinite(parsed) ? parsed : min))
  }

  return (
    <div className={clsx('flex flex-wrap items-center gap-2', className)}>
      <div
        className={clsx(
          'flex h-9 min-w-[11rem] items-stretch overflow-hidden rounded-xl border border-gray-200 bg-white transition',
          'focus-within:border-amber-400 focus-within:ring-2 focus-within:ring-amber-100',
          disabled && 'pointer-events-none opacity-60'
        )}
      >
        <input
          type="text"
          inputMode="numeric"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          aria-label="全书目标字数"
          value={display}
          onFocus={() => {
            setFocused(true)
            setDraft(String(value))
          }}
          onBlur={() => {
            setFocused(false)
            commit()
            setDraft(null)
          }}
          onChange={e => {
            const raw = e.target.value.replace(/\D/g, '')
            setDraft(raw)
          }}
          className="min-w-0 flex-1 border-0 bg-transparent px-3 py-0 text-sm font-medium tabular-nums text-gray-900 outline-none placeholder:text-gray-300"
        />
        <span className="flex shrink-0 select-none items-center border-l border-gray-100 bg-gray-50/90 px-2.5 text-xs font-medium text-gray-500">
          字
        </span>
      </div>
      {hint != null && (
        <span className="text-xs leading-relaxed text-gray-400">{hint}</span>
      )}
    </div>
  )
}
