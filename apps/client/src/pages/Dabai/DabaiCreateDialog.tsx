import { useState } from 'react'
import { Check, Loader2, Wand2, X } from 'lucide-react'
import LlmAgentMenu from '../../components/Layout/LlmAgentMenu'
import type { StepState } from '../../hooks/useDabaiGenerate'
import { DABAI_STEP_LABELS } from '../../types/dabai'
import { modelProfileFromRoute, routeLlmProviderPayload, useAppStore } from '../../store'

interface Props {
  open: boolean
  generating: boolean
  steps: string[]
  stepStatus: Record<string, StepState>
  chapterTotal: number
  onClose: () => void
  onGenerate: (payload: {
    logline: string
    mock: boolean
    model_profile: 'local' | 'gemini'
    llm_provider_id?: string
    volume_count: number
    volume_chapters: number
    big_beat_every: number
    chapter_batch_size: number
  }) => Promise<void>
}

function StepDot({ state }: { state: StepState }) {
  if (state === 'done') return <Check size={12} className="text-emerald-500" />
  if (state === 'running') return <Loader2 size={12} className="animate-spin text-rose-500" />
  if (state === 'error') return <X size={12} className="text-rose-500" />
  return <span className="h-1.5 w-1.5 rounded-full bg-gray-300" />
}

export default function DabaiCreateDialog({
  open, generating, steps, stepStatus, chapterTotal, onClose, onGenerate,
}: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [logline, setLogline] = useState('废柴少年觉醒吞噬系统，一路逆袭打脸天才')
  const [mock, setMock] = useState(false)
  const [volumeChapters, setVolumeChapters] = useState(30)

  if (!open) return null

  const submit = () => {
    if (!logline.trim() || generating) return
    void onGenerate({
      logline: logline.trim(),
      mock,
      model_profile: modelProfileFromRoute(aiBackendRoute),
      ...routeLlmProviderPayload(aiBackendRoute),
      volume_count: 6,
      volume_chapters: volumeChapters,
      big_beat_every: 5,
      chapter_batch_size: 30,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-gray-100 bg-white p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900">新建大白文</h2>
          <button type="button" onClick={onClose} disabled={generating} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100">
            <X size={18} />
          </button>
        </div>
        <textarea
          value={logline}
          onChange={e => setLogline(e.target.value)}
          rows={3}
          className="mt-4 w-full resize-none rounded-xl border border-gray-200 px-3 py-2 text-sm"
          placeholder="一句话创意"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-gray-600">
          {!mock && (
            <div className="flex items-center gap-2">
              <span className="text-gray-400">模型</span>
              <LlmAgentMenu />
            </div>
          )}
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={mock} onChange={e => setMock(e.target.checked)} />
            mock
          </label>
          <label className="flex items-center gap-1.5">
            每卷
            <input
              type="number"
              min={5}
              max={120}
              value={volumeChapters}
              onChange={e => setVolumeChapters(Number(e.target.value) || 30)}
              className="w-16 rounded border border-gray-200 px-2 py-0.5 text-sm"
            />
            章
          </label>
        </div>
        {generating && steps.length > 0 && (
          <ol className="mt-4 flex flex-wrap gap-1.5">
            {steps.map(s => (
              <li
                key={s}
                className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-2 py-0.5 text-[10px] text-gray-600"
              >
                <StepDot state={stepStatus[s] ?? 'pending'} />
                {DABAI_STEP_LABELS[s] ?? s}
                {s === 'chapter_outlines' && chapterTotal > 0 ? ` ${chapterTotal}` : ''}
              </li>
            ))}
          </ol>
        )}
        <button
          type="button"
          onClick={submit}
          disabled={generating}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-rose-500 py-2.5 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-60"
        >
          {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
          {generating ? '生成中…' : '开始生成'}
        </button>
      </div>
    </div>
  )
}
