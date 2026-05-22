/**
 * @file ConfirmActionModal.tsx
 * @description 通用高风险操作确认弹窗（与 RepairConfirmModal 同套视觉）。
 */

import { useEffect, useRef } from 'react'
import { AlertTriangle, RefreshCw, X } from 'lucide-react'
import clsx from 'clsx'

export interface ConfirmActionModalProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  /** 副标题或卷名等 */
  subtitle?: string
  bullets?: string[]
  confirmLabel?: string
  cancelLabel?: string
  /** 确认按钮强调色 */
  tone?: 'amber' | 'rose'
}

export default function ConfirmActionModal({
  open,
  onClose,
  onConfirm,
  title,
  subtitle,
  bullets = [],
  confirmLabel = '确定继续',
  cancelLabel = '取消',
  tone = 'amber',
}: ConfirmActionModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    if (open) setTimeout(() => panelRef.current?.focus(), 50)
  }, [open])

  if (!open) return null

  const confirmBtnClass = tone === 'rose'
    ? 'bg-rose-600 hover:bg-rose-700 focus:ring-rose-300'
    : 'bg-amber-600 hover:bg-amber-700 focus:ring-amber-300'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[2px]"
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative w-full max-w-md mx-4 rounded-xl border border-gray-200 bg-white shadow-xl outline-none"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2 min-w-0">
            <AlertTriangle size={15} className="text-amber-500 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-900 truncate">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors shrink-0"
            aria-label="关闭"
          >
            <X size={15} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {subtitle && (
            <p className="text-sm text-gray-800 leading-relaxed">{subtitle}</p>
          )}
          {bullets.length > 0 && (
            <ul className="rounded-lg border border-amber-100 bg-amber-50/60 px-3.5 py-2.5 space-y-1.5 text-xs text-amber-900/90">
              {bullets.map((b, i) => (
                <li key={i} className="flex gap-2 leading-relaxed">
                  <span className="text-amber-500 shrink-0">·</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-gray-100 bg-gray-50/50 rounded-b-xl">
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-3.5 py-2 rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm()
              onClose()
            }}
            className={clsx(
              'flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1',
              confirmBtnClass,
            )}
          >
            <RefreshCw size={12} />
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
