/**
 * @file 复盘 — 读者承诺台账预览
 */
import { PROMISE_TYPE_LABEL } from './constants'
import type { DebriefPanelProps } from '../types'

export interface ReaderPromisesSectionProps {
  aiNewReaderPromises: NonNullable<DebriefPanelProps['aiNewReaderPromises']>
  aiFulfilledPromiseTexts: NonNullable<DebriefPanelProps['aiFulfilledPromiseTexts']>
  fromQueueSnapshot?: boolean
  onRemoveNewPromise?: DebriefPanelProps['onRemoveNewPromise']
  onRemoveFulfilledPromise?: DebriefPanelProps['onRemoveFulfilledPromise']
}

export function ReaderPromisesSection({
  aiNewReaderPromises,
  aiFulfilledPromiseTexts,
  fromQueueSnapshot = false,
  onRemoveNewPromise,
  onRemoveFulfilledPromise,
}: ReaderPromisesSectionProps) {
  if (aiNewReaderPromises.length === 0 && aiFulfilledPromiseTexts.length === 0) return null

  return (
    <section className="rounded-novel border border-violet-200 bg-violet-50/50 px-3 py-2.5 space-y-2">
      <span className="text-[10px] font-semibold text-violet-800 uppercase tracking-wider block">
        读者承诺台账
      </span>
      {aiNewReaderPromises.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[9px] text-violet-700/80">本章新承诺（提交后写入台账）</p>
          {aiNewReaderPromises.map((p, idx) => (
            <div
              key={`new-promise-${idx}`}
              className="flex items-start gap-2 text-[11px] text-violet-950 bg-white/80 rounded border border-violet-100 px-2 py-1.5"
            >
              <span className="flex-1 leading-relaxed">
                <span className="text-[9px] text-violet-600 mr-1">
                  {PROMISE_TYPE_LABEL[p.promise_type || ''] || p.promise_type || '承诺'}
                </span>
                {p.promise_text}
                {typeof p.expected_within_chapters === 'number' && p.expected_within_chapters > 0 && (
                  <span className="text-[9px] text-violet-500 ml-1">
                    · {p.expected_within_chapters} 章内
                  </span>
                )}
              </span>
              {onRemoveNewPromise && !fromQueueSnapshot && (
                <button
                  type="button"
                  onClick={() => onRemoveNewPromise(idx)}
                  className="text-[9px] text-violet-500 hover:text-violet-800 shrink-0"
                >
                  移除
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {aiFulfilledPromiseTexts.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[9px] text-violet-700/80">本章已兑现（提交后匹配 open 台账标 fulfilled）</p>
          {aiFulfilledPromiseTexts.map((text, idx) => (
            <div
              key={`fulfilled-${idx}`}
              className="flex items-start gap-2 text-[11px] text-emerald-900 bg-emerald-50/90 rounded border border-emerald-100 px-2 py-1.5"
            >
              <span className="flex-1 leading-relaxed">{text}</span>
              {onRemoveFulfilledPromise && !fromQueueSnapshot && (
                <button
                  type="button"
                  onClick={() => onRemoveFulfilledPromise(idx)}
                  className="text-[9px] text-emerald-600 hover:text-emerald-900 shrink-0"
                >
                  移除
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
