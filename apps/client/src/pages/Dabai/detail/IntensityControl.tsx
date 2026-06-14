/**
 * @file pages/Dabai/detail/IntensityControl.tsx
 * 叙事烈度档选择器（克制/标准/够炸）。改动经 PATCH /dabai/projects/{id}/settings
 * 双写 positioning+extra，下游写正文/质检统一读取。
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { dabaiApi } from '../../../api/dabai'
import {
  DABAI_INTENSITY_HINTS,
  DABAI_INTENSITY_LABELS,
  type DabaiIntensity,
} from '../../../types/dabai'

const OPTIONS: DabaiIntensity[] = ['restrained', 'standard', 'loud']

export default function IntensityControl({
  projectId,
  value,
}: {
  projectId: string
  value: DabaiIntensity
}) {
  const [current, setCurrent] = useState<DabaiIntensity>(value)
  const [saving, setSaving] = useState<DabaiIntensity | null>(null)

  const pick = async (next: DabaiIntensity) => {
    if (next === current || saving) return
    const prev = current
    setCurrent(next)
    setSaving(next)
    try {
      await dabaiApi.setIntensity(projectId, next)
      toast.success(`叙事烈度 · ${DABAI_INTENSITY_LABELS[next]}`)
    } catch {
      setCurrent(prev)
      toast.error('保存失败，请重试')
    } finally {
      setSaving(null)
    }
  }

  return (
    <div>
      <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5">
        {OPTIONS.map(opt => (
          <button
            key={opt}
            type="button"
            onClick={() => void pick(opt)}
            disabled={!!saving}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              current === opt
                ? 'bg-rose-500 text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            {DABAI_INTENSITY_LABELS[opt]}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-gray-400">{DABAI_INTENSITY_HINTS[current]}</p>
    </div>
  )
}
