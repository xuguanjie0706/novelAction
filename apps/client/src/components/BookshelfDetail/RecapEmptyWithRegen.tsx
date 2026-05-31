/**
 * 纪要页空态：提示 + 一键补跑缺失的 Bootstrap 步骤。
 */
import React from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useRecapStepRegen, type RecapRegenStep } from '../../hooks/useRecapStepRegen'

const STEP_LABEL: Record<RecapRegenStep, string> = {
  emotion_arc: '情绪节律',
  villain_arc: '反派行动线',
  opening_contract: '开局承诺',
}

interface Props {
  projectId: string
  step: RecapRegenStep
  hint: string
  onSuccess: () => void | Promise<void>
}

export default function RecapEmptyWithRegen({ projectId, step, hint, onSuccess }: Props) {
  const { loadingStep, runRegen } = useRecapStepRegen()
  const busy = loadingStep === step

  const handleRegen = async () => {
    try {
      const result = await runRegen(projectId, step)
      if (result.count > 0) {
        toast.success(`${STEP_LABEL[step]}已生成 ${result.count} 条`)
        await onSuccess()
        return
      }
      toast.error(
        `${STEP_LABEL[step]}仍为空，可能是模型未返回有效 JSON。请切换远程线路后重试。`,
        { duration: 5000 },
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '重新生成失败'
      toast.error(msg)
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-start',
      gap: 14,
      maxWidth: 480,
    }}>
      <p style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.6, margin: 0 }}>
        {hint}
      </p>
      <button
        type="button"
        disabled={!!loadingStep}
        onClick={() => void handleRegen()}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          padding: '9px 16px',
          borderRadius: 8,
          border: '1px solid #fde68a',
          background: busy ? '#fffbeb' : '#fef3c7',
          color: '#b45309',
          fontSize: 13,
          fontWeight: 600,
          cursor: loadingStep ? 'not-allowed' : 'pointer',
          opacity: loadingStep && !busy ? 0.6 : 1,
        }}
      >
        {busy ? (
          <Loader2 size={15} className="animate-spin" />
        ) : (
          <RefreshCw size={15} />
        )}
        {busy ? `正在生成${STEP_LABEL[step]}…` : `重新生成${STEP_LABEL[step]}`}
      </button>
      <p style={{ fontSize: 11, color: '#9ca3af', margin: 0, lineHeight: 1.5 }}>
        使用当前创作端所选 AI 线路；生成约需 10–30 秒。
      </p>
    </div>
  )
}
