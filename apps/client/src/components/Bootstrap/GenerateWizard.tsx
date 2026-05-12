/**
 * @file GenerateWizard — 一键生成小说的主向导面板
 *
 * 职责：
 * - 渲染「输入 → 生成中 → 闸门确认 → 完成」四阶段 UI
 * - SSE 业务状态委托给 useBootstrapStream hook
 * - generating / done 阶段渲染时间轴纪要（BootstrapTimeline + BootstrapTimelineDetail）
 *
 * 阶段流转（由 hook 驱动）：
 *   input → generating → gate（立项定位确认）→ generating → done
 *
 * 注意：单次全量（single_shot）模式不经过 gate；gate 仅用于串行模式。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import clsx from 'clsx'
import { llmApi, projectsApi } from '../../api/client'
import type { LlmOverview } from '../../types'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../store'
import { TargetWordsInput } from '../TargetWordsInput'
import { useBootstrapStream } from './hooks/useBootstrapStream'
import type { StepKey } from './hooks/useBootstrapStream'
import PositioningGatePanel from './PositioningGatePanel'
import BootstrapStepGatePanel from './BootstrapStepGatePanel'
import BootstrapTimeline from './BootstrapTimeline'
import BootstrapTimelineDetail from './BootstrapTimelineDetail'

// ── 字数目标选项 ──────────────────────────────────────────────
const WORD_OPTIONS = [
  { label: '短篇',   value: 800000,  desc: '80万字 · 约6卷' },
  { label: '标准',   value: 1200000, desc: '120万字 · 约9卷' },
  { label: '长篇',   value: 1500000, desc: '150万字 · 约11卷' },
  { label: '超长篇', value: 2000000, desc: '200万字 · 约15卷' },
] as const

interface Props {
  /** 关闭弹窗（取消或完成后跳转前调用） */
  onClose: () => void
}

type Mode = 'sequential' | 'single_shot'

export default function GenerateWizard({ onClose }: Props) {
  const navigate       = useNavigate()
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const setAiBackendRoute = useAppStore(s => s.setAiBackendRoute)

  // ── Bootstrap SSE 状态（委托给 hook）──────────────────────────
  const {
    phase, steps, errorMsg, projectId, positioningData, generationStartMs,
    gateStep, gateMessage, gatePreview,
    startGenerate: hookStart, handleResume, cancel: hookCancel,
  } = useBootstrapStream()

  /** 时间轴当前选中的步骤 key */
  const [selectedStepKey, setSelectedStepKey] = useState<StepKey | null>(null)

  // ── 本地 UI 状态 ──────────────────────────────────────────────
  const [logline, setLogline]               = useState('')
  const [mode, setMode]                     = useState<Mode>('sequential')
  const [targetWords, setTargetWords]       = useState(1200000)
  const [customWordMode, setCustomWordMode] = useState(false)
  const [insights, setInsights]             = useState<{
    consistency_issues: any[]
    opening_contract: Record<string, any>
  } | null>(null)
  const [llmOverview, setLlmOverview]   = useState<LlmOverview | null>(null)
  const [llmLoading, setLlmLoading]     = useState(false)
  const [waitSec, setWaitSec]           = useState(0)
  /** resume 请求进行中（gate 面板按钮禁用态） */
  const [resumeLoading, setResumeLoading] = useState(false)

  // ── 初始化：拉取 LLM 概况 ────────────────────────────────────
  useEffect(() => {
    let alive = true
    setLlmLoading(true)
    llmApi.overview()
      .then(res => { if (alive) setLlmOverview(res.data) })
      .catch(() => { if (alive) setLlmOverview(null) })
      .finally(() => { if (alive) setLlmLoading(false) })
    return () => { alive = false }
  }, [])

  // ── 等待计时器（仅 generating 阶段计时，gate/done 时停止）────
  useEffect(() => {
    if (phase !== 'generating') return
    setWaitSec(0)
    const id = window.setInterval(() => setWaitSec(s => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [phase])

  // ── 自动选中默认远程 provider ─────────────────────────────────
  useEffect(() => {
    if (!llmOverview?.remote_providers?.length) return
    const pick = () =>
      llmOverview.remote_providers.find(p => p.is_default) ?? llmOverview.remote_providers[0]
    if (aiBackendRoute === 'remote') {
      setAiBackendRoute(`remote:${pick().id}`)
      return
    }
    if (aiBackendRoute.startsWith('remote:')) {
      const id = aiBackendRoute.slice('remote:'.length)
      if (!llmOverview.remote_providers.some(p => p.id === id)) {
        setAiBackendRoute(`remote:${pick().id}`)
      }
    }
  }, [llmOverview, aiBackendRoute, setAiBackendRoute])

  // ── 生成完成后拉取 Bootstrap 写入的编辑洞察数据 ──────────────
  useEffect(() => {
    if (!projectId) return
    projectsApi.getInsights(projectId)
      .then(res => setInsights(res.data))
      .catch(() => {/* 非关键，忽略 */})
  }, [projectId])

  const modelHint = useMemo(() => {
    const selectedProviderId = llmProviderIdFromRoute(aiBackendRoute)
    const selectedProvider = llmOverview?.remote_providers?.find(p => p.id === selectedProviderId)
    if (selectedProvider) return `当前：远程 · ${selectedProvider.name} (${selectedProvider.model_name})`
    if (aiBackendRoute === 'local') {
      return `当前：本地兼容端点 · ${llmOverview?.local_model_name ?? '见后端 LLM_BASE_URL / AI_MODEL'}`
    }
    if (llmOverview?.remote_ready) return `当前：远程 · 环境变量 (${llmOverview.effective_remote_model ?? '默认'})`
    return '当前：远程（未配置）'
  }, [aiBackendRoute, llmOverview])

  // ── 开始生成 ─────────────────────────────────────────────────
  function handleStart() {
    if (!logline.trim()) return
    hookStart({
      logline: logline.trim(),
      mode,
      targetWords,
      modelProfile: modelProfileFromRoute(aiBackendRoute),
      llmProviderId: llmProviderIdFromRoute(aiBackendRoute),
    })
  }

  const resumeParams = {
    modelProfile: modelProfileFromRoute(aiBackendRoute),
    llmProviderId: llmProviderIdFromRoute(aiBackendRoute),
  }

  /**
   * Step0 闸门：提交用户审阅/编辑后的立项定位后继续。
   */
  async function handleGateConfirm(positioning: Record<string, any>) {
    setResumeLoading(true)
    try {
      await handleResume({ action: 'approve', positioning }, resumeParams)
    } finally {
      setResumeLoading(false)
    }
  }

  /** Step0：整步重新召开立项会议 */
  async function handlePositioningRegenerate() {
    setResumeLoading(true)
    try {
      await handleResume({ action: 'regenerate' }, resumeParams)
    } finally {
      setResumeLoading(false)
    }
  }

  /** Step 2 / 5 / 9 闸门：确认继续 */
  async function handleRootGateApprove() {
    setResumeLoading(true)
    try {
      await handleResume({ action: 'approve' }, resumeParams)
    } finally {
      setResumeLoading(false)
    }
  }

  /** Step 2 / 5 / 9 闸门：重跑本步 */
  async function handleRootGateRegenerate() {
    setResumeLoading(true)
    try {
      await handleResume({ action: 'regenerate' }, resumeParams)
    } finally {
      setResumeLoading(false)
    }
  }

  function cancel() {
    hookCancel()
    onClose()
  }

  // ── 时间轴阶段自动选中第一个 running/done 步骤 ────────────────
  const isTimelinePhase = phase === 'generating' || phase === 'done'
  useEffect(() => {
    if (!isTimelinePhase) return
    if (selectedStepKey != null) return   // 已手动选中，不覆盖
    const first = steps.find(s => s.status === 'running' || s.status === 'done')
    if (first) setSelectedStepKey(first.key)
  }, [isTimelinePhase, steps, selectedStepKey])

  // 随着生成推进，自动跟进到当前运行中的步骤
  useEffect(() => {
    if (!isTimelinePhase) return
    const running = steps.find(s => s.status === 'running')
    if (running) setSelectedStepKey(running.key)
  }, [steps]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 渲染 ─────────────────────────────────────────────────────
  const selectedStep = steps.find(s => s.key === selectedStepKey) ?? null

  return (
    <div className={clsx(
      'fixed inset-0 z-50 flex',
      isTimelinePhase ? 'items-stretch' : 'items-center justify-center bg-black/40 backdrop-blur-sm p-4',
    )}>
      {/* 时间轴模式：全屏深色沉浸式；其他模式：居中白卡 */}
      <div className={clsx(
        'flex flex-col overflow-hidden',
        isTimelinePhase
          ? 'w-full h-full'
          : 'bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh]',
        phase === 'gate' && 'max-w-2xl',
      )}
        style={isTimelinePhase ? { background: '#0d0d12' } : undefined}
      >

        {/* 标题栏 */}
        <div
          className={clsx('flex items-center justify-between px-6 py-4 flex-shrink-0')}
          style={isTimelinePhase
            ? { background: '#13131a', borderBottom: '1px solid #2a2a3a' }
            : { borderBottom: '1px solid #f3f4f6' }
          }
        >
          <div className="flex items-center gap-2">
            <Sparkles size={18} className={isTimelinePhase ? 'text-purple-400' : 'text-amber-500'} />
            <span
              className="font-semibold"
              style={isTimelinePhase ? { color: '#e2e2ec' } : { color: '#111827' }}
            >
              {phase === 'done' ? '生成纪要' : 'AI 一键生成小说'}
            </span>
            {isTimelinePhase && phase === 'done' && (
              <span style={{ fontSize: 11, padding: '1px 8px', borderRadius: 20, border: '1px solid #22c55e50', color: '#22c55e', background: '#22c55e10', marginLeft: 4 }}>
                ✓ 全部完成
              </span>
            )}
            {isTimelinePhase && phase === 'generating' && (
              <span style={{ fontSize: 11, padding: '1px 8px', borderRadius: 20, border: '1px solid #7c6af750', color: '#a78bfa', background: '#7c6af710', marginLeft: 4 }}>
                生成中…
              </span>
            )}
          </div>
          <button
            onClick={cancel}
            style={isTimelinePhase ? { color: '#5a5a78' } : { color: '#9ca3af' }}
            className="hover:opacity-80 transition-opacity"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── 输入阶段 ── */}
        {phase === 'input' && (
          <div className="p-6 space-y-5 overflow-y-auto flex-1">
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
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
              立意、主题和设定将由 AI 根据一句话创意自动生成，你无需额外填写设定项。
            </p>

            {/* 模型线路 */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">模型线路</label>
              <select
                value={aiBackendRoute}
                onChange={e => setAiBackendRoute(e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-amber-400"
                disabled={llmLoading}
              >
                <option value="local">本地兼容 · {llmLoading ? '加载中…' : (llmOverview?.local_model_name ?? 'OpenAI 兼容')}</option>
                {!!llmOverview?.remote_providers?.length && llmOverview.remote_providers.map(p => (
                  <option key={p.id} value={`remote:${p.id}`}>
                    远程 · {p.name} ({p.model_name}){p.is_default ? ' ★' : ''}
                  </option>
                ))}
                {!llmLoading && llmOverview?.remote_ready && (llmOverview.remote_providers?.length ?? 0) === 0 && (
                  <option value="remote">远程 · 环境变量 ({llmOverview.effective_remote_model ?? '—'})</option>
                )}
                {!llmLoading && !llmOverview?.remote_ready && (llmOverview?.remote_providers?.length ?? 0) === 0 && (
                  <option value="remote" disabled>远程（未配置）</option>
                )}
              </select>
              <p className="text-xs text-gray-400 mt-1">{modelHint}</p>
            </div>

            {/* 生成方案 */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">生成方案</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setMode('sequential')}
                  className={clsx(
                    'p-3 rounded-xl border-2 text-left transition-all',
                    mode === 'sequential' ? 'border-amber-400 bg-amber-50' : 'border-gray-100 hover:border-gray-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">
                    方案 A · 串行步进
                    {mode === 'sequential' && (
                      <span className="ml-2 text-xs bg-amber-500 text-white px-1.5 py-0.5 rounded-full">推荐</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 leading-relaxed">
                    多步分别生成，含章级大纲 + 场景蓝图 + 一致性扫描<br />
                    内容最完整，适合所有模型
                  </div>
                </button>
                <button
                  onClick={() => setMode('single_shot')}
                  className={clsx(
                    'p-3 rounded-xl border-2 text-left transition-all',
                    mode === 'single_shot' ? 'border-blue-400 bg-blue-50' : 'border-gray-100 hover:border-gray-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">方案 B · 单次全量</div>
                  <div className="text-xs text-gray-500 leading-relaxed">
                    1 次生成世界蓝图，速度快<br />
                    适合大上下文远程模型，章级大纲需手动展开
                  </div>
                </button>
              </div>
            </div>

            {/* 字数目标 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700">全书字数目标</label>
                <button
                  type="button"
                  onClick={() => setCustomWordMode(m => !m)}
                  className="text-xs text-amber-500 hover:text-amber-600"
                >
                  {customWordMode ? '快捷选择' : '自定义'}
                </button>
              </div>
              {customWordMode ? (
                <TargetWordsInput
                  value={targetWords}
                  onChange={setTargetWords}
                  hint={
                    <>· 约 {Math.round(targetWords / 2300)} 章 / {Math.ceil(Math.round(targetWords / 2300) / 60)} 卷</>
                  }
                />
              ) : (
                <div className="grid grid-cols-4 gap-2">
                  {WORD_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setTargetWords(opt.value)}
                      className={clsx(
                        'rounded-xl border py-2.5 text-center transition-all',
                        targetWords === opt.value
                          ? 'border-amber-400 bg-amber-50 ring-1 ring-amber-300'
                          : 'border-gray-100 hover:border-gray-200 bg-white'
                      )}
                    >
                      <div className={clsx('text-sm font-semibold', targetWords === opt.value ? 'text-amber-700' : 'text-gray-700')}>
                        {opt.label}
                      </div>
                      <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={handleStart}
              disabled={!logline.trim()}
              className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              <Sparkles size={16} />
              开始生成
            </button>
          </div>
        )}

        {/* ── 闸门：Step0 立项 / Step2·5·9 根设定 ── */}
        {phase === 'gate' && gateStep === 'positioning' && positioningData && (
          <PositioningGatePanel
            positioning={positioningData}
            onConfirm={handleGateConfirm}
            onRegenerate={handlePositioningRegenerate}
            loading={resumeLoading}
          />
        )}
        {phase === 'gate' && (gateStep === 'power_systems' || gateStep === 'characters' || gateStep === 'volumes') && (
          <BootstrapStepGatePanel
            step={gateStep}
            message={gateMessage || '请确认后继续生成'}
            preview={gatePreview}
            loading={resumeLoading}
            onApprove={handleRootGateApprove}
            onRegenerate={handleRootGateRegenerate}
          />
        )}

        {/* ── 生成中 / 完成：时间轴纪要 ── */}
        {isTimelinePhase && (
          <div className="flex flex-1 overflow-hidden">
            <BootstrapTimeline
              steps={steps}
              selectedKey={selectedStepKey}
              onSelect={key => setSelectedStepKey(key)}
              phase={phase}
              logline={logline}
              elapsedSec={waitSec}
              generationStartMs={generationStartMs}
            />
            <BootstrapTimelineDetail
              step={selectedStep}
              positioningData={positioningData}
              insights={insights}
              generationStartMs={generationStartMs}
              phase={phase}
              projectId={projectId}
              onNavigate={() => { onClose(); navigate(`/project/${projectId}/outline`) }}
              onCancel={cancel}
              errorMsg={errorMsg}
            />
          </div>
        )}
      </div>
    </div>
  )
}
