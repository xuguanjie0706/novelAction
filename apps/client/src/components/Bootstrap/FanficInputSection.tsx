/**
 * @file 同人·番茄建书输入区：原著名 + AI 梗概三选一 + 同人类型。
 */
import React, { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { Loader2, RefreshCw, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import { bootstrapFanficApi, type CanonSynopsisOption } from '../../api/bootstrap'
import { formatApiError } from '../../utils/apiError'

export type FanficTrope = 'transmigration' | 'rebirth' | 'au'

export interface FanficInputValues {
  sourceWorkTitle: string
  canonSynopsis: string
  fanficTrope: FanficTrope
  focalCharacters: string
}

interface Props {
  logline: string
  modelProfile: 'local' | 'gemini'
  llmProviderId?: string | null
  values: FanficInputValues
  onChange: (patch: Partial<FanficInputValues>) => void
}

export default function FanficInputSection({
  logline,
  modelProfile,
  llmProviderId,
  values,
  onChange,
}: Props) {
  const [options, setOptions] = useState<CanonSynopsisOption[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  /** 仅当原著名 / 同人类型 / 一句话创意变化时清空候选，避免 onChange 引用变化误触发 */
  const inputsKey = `${values.sourceWorkTitle}|${values.fanficTrope}|${logline}`
  const prevInputsKeyRef = useRef(inputsKey)
  useEffect(() => {
    if (prevInputsKeyRef.current === inputsKey) return
    prevInputsKeyRef.current = inputsKey
    setOptions([])
    setSelectedId(null)
    onChangeRef.current({ canonSynopsis: '' })
  }, [inputsKey])

  async function generateOptions() {
    const title = values.sourceWorkTitle.trim()
    if (!title) {
      toast.error('请先填写原著名')
      return
    }
    if (!logline.trim()) {
      toast.error('请先填写一句话创意')
      return
    }
    setGenerating(true)
    try {
      const res = await bootstrapFanficApi.generateCanonSynopsisOptions({
        source_work_title: title,
        logline: logline.trim(),
        fanfic_trope: values.fanficTrope,
        focal_characters: values.focalCharacters.trim(),
        model_profile: modelProfile,
        llm_provider_id: llmProviderId ?? undefined,
      })
      const next = res.data.options
      if (!next.length) {
        toast.error('未生成有效梗概，请重试')
        return
      }
      setOptions(next)
      setSelectedId(next[0].id)
      onChange({ canonSynopsis: next[0].synopsis })
      toast.success('已生成 3 条梗概候选，请选择一条')
    } catch (e: unknown) {
      toast.error(formatApiError(e))
    } finally {
      setGenerating(false)
    }
  }

  function selectOption(opt: CanonSynopsisOption) {
    setSelectedId(opt.id)
    onChange({ canonSynopsis: opt.synopsis })
  }

  return (
    <div className="space-y-3 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
      <div>
        <label className="text-sm font-medium text-gray-700 block mb-1">
          原著名 <span className="text-red-400">*</span>
        </label>
        <input
          value={values.sourceWorkTitle}
          onChange={e => onChange({ sourceWorkTitle: e.target.value })}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          placeholder="如：斗破苍穹（系统不爬取原文，梗概由 AI 根据公开认知生成）"
        />
      </div>

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <label className="text-sm font-medium text-gray-700">
            原著梗概 <span className="text-red-400">*</span>
            <span className="ml-1 text-xs font-normal text-gray-400">AI 生成 3 条，择一</span>
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void generateOptions()}
              disabled={generating}
              className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {generating ? <Loader2 size={12} className="animate-spin" /> : options.length ? <RefreshCw size={12} /> : <Sparkles size={12} />}
              {options.length ? '重新生成' : '生成梗概候选'}
            </button>
          </div>
        </div>

        {generating && !options.length && (
          <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-indigo-200 bg-white/80 py-8 text-sm text-indigo-600">
            <Loader2 size={16} className="animate-spin" />
            正在生成 3 条原著梗概…
          </div>
        )}

        {!generating && !options.length && (
          <p className="rounded-lg border border-dashed border-gray-200 bg-white/60 px-3 py-4 text-xs leading-relaxed text-gray-500">
            填写原著名与一句话创意后，点击「生成梗概候选」。系统将一次生成 3 条不同侧重点的梗概，你择一即可开始建书。
          </p>
        )}

        {options.length > 0 && (
          <div className="space-y-2">
            {options.map(opt => {
              const active = selectedId === opt.id
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => selectOption(opt)}
                  className={clsx(
                    'w-full rounded-lg border p-3 text-left transition-all',
                    active
                      ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-300'
                      : 'border-gray-200 bg-white hover:border-indigo-200'
                  )}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className={clsx(
                        'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px]',
                        active ? 'border-indigo-500 bg-indigo-500 text-white' : 'border-gray-300'
                      )}
                    >
                      {active ? '✓' : ''}
                    </span>
                    <span className="text-sm font-medium text-gray-800">{opt.label}</span>
                    <span className="text-xs text-gray-400">{opt.synopsis.length} 字</span>
                  </div>
                  <p className="text-xs leading-relaxed text-gray-600 line-clamp-4">{opt.synopsis}</p>
                </button>
              )
            })}
          </div>
        )}

        {values.canonSynopsis && (
          <p className="mt-2 text-xs text-emerald-600">
            已选梗概 {values.canonSynopsis.length} 字
            {values.canonSynopsis.length < 80 ? '（不足 80 字，请重新生成）' : ''}
          </p>
        )}
      </div>

      <div>
        <label className="text-sm font-medium text-gray-700 block mb-2">同人类型</label>
        <div className="flex flex-wrap gap-2">
          {([
            ['transmigration', '穿书'],
            ['rebirth', '重生'],
            ['au', 'AU平行'],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => onChange({ fanficTrope: id })}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-sm border',
                values.fanficTrope === id
                  ? 'border-indigo-500 bg-indigo-100 text-indigo-800'
                  : 'border-gray-200 bg-white text-gray-600'
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="text-sm font-medium text-gray-700 block mb-1">主 CP / 视角人物（可选）</label>
        <input
          value={values.focalCharacters}
          onChange={e => onChange({ focalCharacters: e.target.value })}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          placeholder="如：萧炎 × 云韵"
        />
      </div>
    </div>
  )
}
