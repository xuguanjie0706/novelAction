import React, { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X, CheckCircle, Loader, AlertCircle, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  onClose: () => void
}

type StepKey = 'project' | 'settings' | 'characters' | 'outline' | 'memory' | 'relations' | 'all' | 'saving'
type StepStatus = 'pending' | 'running' | 'done' | 'error'

interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  detail?: string   // count / preview
}

const STEP_DEFS: { key: StepKey; label: string }[] = [
  { key: 'project',    label: '项目基础信息' },
  { key: 'settings',   label: '世界观设定卡' },
  { key: 'characters', label: '人物库' },
  { key: 'outline',    label: '大纲树（3卷+前10章）' },
  { key: 'memory',     label: '记忆库种子' },
  { key: 'relations',  label: '人物关系' },
]

type Mode = 'sequential' | 'single_shot'

export default function GenerateWizard({ onClose }: Props) {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<'input' | 'generating' | 'done'>('input')
  const [logline, setLogline] = useState('')
  const [mode, setMode] = useState<Mode>('sequential')
  const [steps, setSteps] = useState<StepState[]>(
    STEP_DEFS.map(s => ({ ...s, status: 'pending' }))
  )
  const [errorMsg, setErrorMsg] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const isSubmittingRef = useRef(false)   // 防止重复提交

  // ── 开始生成 ──────────────────────────────────────────────
  const startGenerate = async () => {
    if (!logline.trim() || isSubmittingRef.current) return
    isSubmittingRef.current = true
    setPhase('generating')
    setErrorMsg('')

    // single_shot 模式用两个虚拟步骤
    if (mode === 'single_shot') {
      setSteps([
        { key: 'all',    label: 'AI 全量生成（单次调用）', status: 'pending' },
        { key: 'saving', label: '写入数据库',               status: 'pending' },
      ])
    } else {
      setSteps(STEP_DEFS.map(s => ({ ...s, status: 'pending' })))
    }

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const res = await fetch('/api/v1/bootstrap/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logline: logline.trim(), mode }),
        signal: abort.signal,
      })

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw || raw === '[DONE]') continue

          let evt: Record<string, any>
          try { evt = JSON.parse(raw) } catch { continue }

          handleEvent(evt)
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setErrorMsg(err.message || '网络错误')
      }
    } finally {
      isSubmittingRef.current = false
    }
  }

  const handleEvent = (evt: Record<string, any>) => {
    const { event, step, label, count, preview, message, project_id } = evt

    if (event === 'step_start') {
      setSteps(prev => prev.map(s =>
        s.key === step ? { ...s, status: 'running', label: label ?? s.label } : s
      ))
    } else if (event === 'step_done') {
      const detail = [
        count != null ? `${count} 条` : '',
        preview ?? '',
      ].filter(Boolean).join(' · ')
      setSteps(prev => prev.map(s =>
        s.key === step ? { ...s, status: 'done', detail } : s
      ))
    } else if (event === 'error') {
      setSteps(prev => prev.map(s =>
        s.key === step ? { ...s, status: 'error', detail: message } : s
      ))
      setErrorMsg(`[${step}] ${message}`)
    } else if (event === 'complete') {
      setProjectId(project_id)
      setPhase('done')
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
    onClose()
  }

  // ── 渲染 ──────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">

        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-amber-500" />
            <span className="font-semibold text-gray-900">AI 一键生成小说</span>
          </div>
          <button onClick={cancel} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>

        {/* ── 输入阶段 ── */}
        {phase === 'input' && (
          <div className="p-6 space-y-5">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">
                一句话创意 <span className="text-red-400">*</span>
              </label>
              <textarea
                value={logline}
                onChange={e => setLogline(e.target.value)}
                placeholder="例：一个被废掉灵根的天才少年，在死亡边缘觉醒了逆天体质，从此踏上颠覆修仙界的道路"
                rows={4}
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none leading-relaxed"
                autoFocus
              />
              <p className="text-xs text-gray-400 mt-1">越具体越好，包含主角特点、世界背景、核心矛盾</p>
            </div>

            {/* 模式选择 */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">生成方案</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setMode('sequential')}
                  className={clsx(
                    'p-3 rounded-xl border-2 text-left transition-all',
                    mode === 'sequential'
                      ? 'border-amber-400 bg-amber-50'
                      : 'border-gray-100 hover:border-gray-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">
                    方案 A · 串行步进
                    {mode === 'sequential' && (
                      <span className="ml-2 text-xs bg-amber-400 text-white px-1.5 py-0.5 rounded-full">推荐</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 leading-relaxed">
                    6步分别调用，逐步可见进度<br />
                    适合 <b>qwen3:8b</b> 等本地小模型
                  </div>
                </button>
                <button
                  onClick={() => setMode('single_shot')}
                  className={clsx(
                    'p-3 rounded-xl border-2 text-left transition-all',
                    mode === 'single_shot'
                      ? 'border-blue-400 bg-blue-50'
                      : 'border-gray-100 hover:border-gray-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">方案 B · 单次全量</div>
                  <div className="text-xs text-gray-500 leading-relaxed">
                    1次调用生成全部，速度最快<br />
                    适合 <b>Gemini / GPT-4o</b> 大模型
                  </div>
                </button>
              </div>
            </div>

            <button
              onClick={startGenerate}
              disabled={!logline.trim()}
              className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              <Sparkles size={16} />
              开始生成
            </button>
          </div>
        )}

        {/* ── 生成中 ── */}
        {(phase === 'generating' || phase === 'done') && (
          <div className="p-6">
            {/* Logline 摘要 */}
            <p className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 mb-5 leading-relaxed line-clamp-2">
              "{logline}"
            </p>

            {/* 步骤列表 */}
            <div className="space-y-2 mb-5">
              {steps.map((step, idx) => (
                <div
                  key={step.key}
                  className={clsx(
                    'flex items-start gap-3 p-3 rounded-lg transition-colors',
                    step.status === 'running' && 'bg-amber-50',
                    step.status === 'done'    && 'bg-green-50',
                    step.status === 'error'   && 'bg-red-50',
                    step.status === 'pending' && 'opacity-40',
                  )}
                >
                  {/* 图标 */}
                  <div className="shrink-0 mt-0.5">
                    {step.status === 'pending' && (
                      <div className="w-5 h-5 rounded-full border-2 border-gray-200" />
                    )}
                    {step.status === 'running' && (
                      <Loader size={18} className="text-amber-500 animate-spin" />
                    )}
                    {step.status === 'done' && (
                      <CheckCircle size={18} className="text-green-500" />
                    )}
                    {step.status === 'error' && (
                      <AlertCircle size={18} className="text-red-500" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-800">{step.label}</div>
                    {step.detail && (
                      <div className="text-xs text-gray-500 truncate mt-0.5">{step.detail}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* 错误信息 */}
            {errorMsg && (
              <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">
                {errorMsg}
              </div>
            )}

            {/* 完成后的按钮 */}
            {phase === 'done' && projectId && (
              <button
                onClick={() => {
                  onClose()
                  navigate(`/project/${projectId}/outline`)
                }}
                className="w-full py-3 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
              >
                进入工作台
                <ChevronRight size={16} />
              </button>
            )}

            {/* 生成中可取消 */}
            {phase === 'generating' && (
              <button
                onClick={cancel}
                className="w-full py-2 text-sm text-gray-400 hover:text-gray-600"
              >
                取消
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
