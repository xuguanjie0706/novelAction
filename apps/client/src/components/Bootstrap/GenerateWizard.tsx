/**
 * @file GenerateWizard — 一键生成小说的主向导面板
 *
 * 入口约定（与书架/小说详情顶条互补）：
 * - **新建**：从首页「用 AI 写」、书架「AI 生成」等进入，``recoverRunId`` 为空；若已有未结束 run，各页会先拦截并提示点「继续」。
 * - **恢复**：仅在用户点 ``ActiveBootstrapResumeBar`` 的「继续」时传入 ``recoverRunId``（关闭向导、刷新后默认留在当前页，不自动打开本组件）。
 *
 * 阶段流转（由 hook 驱动）：
 *   input → generating → gate（根闸门审阅）→ generating → done
 *
 * 支持 ``recoverRunId``：回放事件并重连 SSE。
 *
 * **外壳形态**（互相独立、可顶栏切换）：
 * - ``modal``：正常提交流程——输入 / 闸门 / 生成中 / 纪要均在**居中弹层**内完成（与截图一致）。
 * - ``workspace``：多用于刷新后从顶条「继续」恢复（``recoverRunId``）——默认**全屏工作台**时间轴，便于断线重连后对照步骤；亦可手动与弹层互切。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Maximize2, Minimize2, Sparkles, X } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { llmApi, projectsApi } from '../../api/client'
import type { LlmOverview } from '../../types'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../store'
import { TargetWordsInput } from '../TargetWordsInput'
import { useBootstrapStream } from './hooks/useBootstrapStream'
import type { StepKey } from './hooks/useBootstrapStream'
import BootstrapGateTimelineDetail from './BootstrapGateTimelineDetail'
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
  /** 恢复某次未结束的 run（与首页/书架顶部条联动） */
  recoverRunId?: string | null
  /** 恢复流程已开始消费 recoverRunId 后回调，避免父级 effect 重复触发 */
  onRecoverConsumed?: () => void
}

type Mode = 'sequential' | 'single_shot' | 'fanqie'

/** 弹层（默认正常提交） vs 全屏工作台（默认恢复 run） */
type BootstrapShell = 'modal' | 'workspace'

export default function GenerateWizard({ onClose, recoverRunId, onRecoverConsumed }: Props) {
  const navigate       = useNavigate()
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const setAiBackendRoute = useAppStore(s => s.setAiBackendRoute)

  // ── Bootstrap SSE 状态（委托给 hook）──────────────────────────
  const {
    phase, steps, errorMsg, projectId, positioningData, generationStartMs, runId,
    gateStep, gateMessage, gatePreview, activeLogline,
    haltedStep, retryLoading,
    startGenerate: hookStart, reconnectToRun, handleResume, retryFailedStep, abortSse, cancelRun,
  } = useBootstrapStream()

  /** 时间轴当前选中的步骤 key */
  const [selectedStepKey, setSelectedStepKey] = useState<StepKey | null>(null)

  useEffect(() => {
    if (haltedStep) setSelectedStepKey(haltedStep)
  }, [haltedStep])

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

  /**
   * 有 ``recoverRunId`` 时默认全屏工作台（刷新/断线后继续）；否则默认弹层。
   * 输入阶段强制弹层，避免空状态占满屏。
   */
  const [shell, setShell] = useState<BootstrapShell>(() =>
    recoverRunId?.trim() ? 'workspace' : 'modal',
  )

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

  /** 与 resume / 重连请求体一致，避免每次 render 新对象导致恢复 effect 反复触发 */
  const resumeParams = useMemo(
    () => ({
      modelProfile: modelProfileFromRoute(aiBackendRoute),
      llmProviderId: llmProviderIdFromRoute(aiBackendRoute),
    }),
    [aiBackendRoute],
  )

  /** 从 URL 或 session 恢复 run 后，把时间轴上的「一句话」与后端 logline 对齐 */
  useEffect(() => {
    const t = activeLogline?.trim()
    if (!t) return
    if (phase !== 'input') setLogline(t)
  }, [activeLogline, phase])

  useEffect(() => {
    if (phase === 'input') setShell('modal')
  }, [phase])

  /** 父级传入 recoverRunId（首页/书架条「继续」）时：回放事件 + 重连 SSE */
  useEffect(() => {
    const rid = recoverRunId?.trim()
    if (!rid) return
    let cancelled = false
    void reconnectToRun(rid, resumeParams, { loglineHint: logline.trim() || undefined })
      .then(() => {
        if (!cancelled) onRecoverConsumed?.()
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : '恢复失败'
        toast.error(msg)
        if (!cancelled) onRecoverConsumed?.()
      })
    return () => {
      cancelled = true
    }
    // 刻意仅依赖 recoverRunId：恢复只应在用户点击「继续」时跑一次
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reconnectToRun / resumeParams 稳定由调用方控制
  }, [recoverRunId])

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

  const [terminating, setTerminating] = useState(false)

  async function cancel() {
    if (terminating) return
    setTerminating(true)
    try {
      const ok = await cancelRun()
      if (ok) onClose()
    } finally {
      setTerminating(false)
    }
  }

  /** 闸门阶段：仅断 SSE 并关弹窗；不调用 ``cancelRun``，便于顶条继续 */
  function handleGateDismiss() {
    abortSse()
    onClose()
  }

  /** 时间轴/纪要：关层不关后端；生成任务仍可由顶条「继续」或「终止」处理 */
  function handleHeaderClose() {
    if (phase === 'gate') {
      handleGateDismiss()
      return
    }
    if (phase === 'generating' || phase === 'done') {
      abortSse()
      onClose()
      return
    }
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

  /** 闸门阶段：左侧时间轴锁定在当前闸门步骤，与生成中同一套工作台 */
  useEffect(() => {
    if (phase !== 'gate' || !gateStep) return
    setSelectedStepKey(gateStep)
  }, [phase, gateStep])

  // ── 渲染 ─────────────────────────────────────────────────────
  const selectedStep = steps.find(s => s.key === selectedStepKey) ?? null
  const isGatePhase = phase === 'gate'
  /** 时间轴 + 右栏：生成中 / 完成 / 根闸门（不再单独全屏审阅页） */
  const showWorkbenchSplit = isTimelinePhase || (isGatePhase && !!gateStep)

  const useWorkspaceChrome =
    shell === 'workspace' && phase !== 'input' && showWorkbenchSplit

  const innerShellClass = useWorkspaceChrome
    ? 'flex h-full w-full flex-col overflow-hidden bg-[#f8fafc]'
    : showWorkbenchSplit
      ? 'flex h-[min(92vh,920px)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-gray-200/90 bg-[#f8fafc] shadow-2xl'
      : 'flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl'

  return (
    <div
      className={clsx(
        'fixed inset-0 z-50 flex',
        useWorkspaceChrome
          ? 'items-stretch'
          : 'items-center justify-center bg-gray-950/20 p-3 backdrop-blur-[2px] sm:p-4',
      )}
    >
      <div className={innerShellClass}>

        {/* 标题栏：闸门阶段与首页顶栏一致（白底细边框） */}
        <div
          className={clsx(
            'flex flex-shrink-0 items-center justify-between px-5 py-3.5 sm:px-6',
            showWorkbenchSplit && 'border-b border-gray-100 bg-white',
          )}
          style={!showWorkbenchSplit ? { borderBottom: '1px solid #f3f4f6' } : undefined}
        >
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-amber-500" />
            <span className="font-semibold text-gray-950">
              {phase === 'done' ? '生成纪要' : 'AI 一键生成小说'}
            </span>
            {isTimelinePhase && phase === 'done' && (
              <span className="ml-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                ✓ 全部完成
              </span>
            )}
            {isGatePhase && (
              <span className="ml-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                待审阅
              </span>
            )}
            {isTimelinePhase && phase === 'generating' && (
              <span className="ml-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                生成中…
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {(showWorkbenchSplit || isGatePhase) && (
              <button
                type="button"
                onClick={() => setShell(s => (s === 'modal' ? 'workspace' : 'modal'))}
                className="mr-1 inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:bg-amber-50/50"
                title={shell === 'modal' ? '全屏工作台：适合刷新后继续对照步骤' : '弹窗视图：与正常提交时一致'}
              >
                {shell === 'modal' ? <Maximize2 size={14} className="shrink-0 text-gray-500" /> : <Minimize2 size={14} className="shrink-0 text-gray-500" />}
                <span className="hidden md:inline">{shell === 'modal' ? '全屏工作台' : '弹窗视图'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleHeaderClose}
              className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
              aria-label={isGatePhase ? '关闭，稍后继续' : '关闭'}
            >
              <X size={18} />
            </button>
          </div>
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
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                    多步分别生成，含章级大纲 + 场景蓝图 + 一致性扫描。内容最完整，适合所有模型。
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
                    1 次生成世界蓝图，速度快。适合大上下文远程模型，章级大纲需手动展开。
                  </div>
                </button>
                <button
                  onClick={() => setMode('fanqie')}
                  className={clsx(
                    'p-3 rounded-xl border-2 text-left transition-all',
                    mode === 'fanqie'
                      ? 'border-orange-400 bg-orange-50'
                      : 'border-gray-100 hover:border-orange-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">
                    🍅 方案 C · 番茄专属
                    {mode === 'fanqie' && (
                      <span className="ml-2 text-xs bg-orange-500 text-white px-1.5 py-0.5 rounded-full">已选</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 leading-relaxed">
                    金手指 + 打脸地图 + 开局五章算法工程，把番茄平台逻辑硬编码进生成管道。
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

        {showWorkbenchSplit && (
          <div className="flex min-h-0 flex-1 overflow-hidden">
            <BootstrapTimeline
              steps={steps}
              selectedKey={phase === 'gate' && gateStep ? gateStep : selectedStepKey}
              onSelect={phase === 'gate' ? () => {} : key => setSelectedStepKey(key)}
              phase={phase}
              logline={logline}
              elapsedSec={waitSec}
              generationStartMs={generationStartMs}
            />
            {isGatePhase && gateStep ? (
              gateStep === 'positioning' && !positioningData ? (
                <div className="flex min-h-0 flex-1 flex-col items-center justify-center bg-[#f8fafc] px-6">
                  <Loader2 size={28} className="animate-spin text-amber-500" />
                  <span className="mt-3 text-sm text-gray-500">正在加载立项数据…</span>
                </div>
              ) : (
                <BootstrapGateTimelineDetail
                  gateStep={gateStep}
                  gateMessage={gateMessage}
                  gatePreview={gatePreview}
                  positioningData={positioningData}
                  resumeError={errorMsg}
                  loading={resumeLoading}
                  terminating={terminating}
                  onDismiss={handleGateDismiss}
                  onApprovePositioning={handleGateConfirm}
                  onRegeneratePositioning={handlePositioningRegenerate}
                  onApproveOther={handleRootGateApprove}
                  onRegenerateOther={handleRootGateRegenerate}
                  onTerminate={cancel}
                />
              )
            ) : (
              <BootstrapTimelineDetail
                step={selectedStep}
                positioningData={positioningData}
                insights={insights}
                generationStartMs={generationStartMs}
                phase={phase}
                projectId={projectId}
                onNavigate={() => { onClose(); navigate(`/project/${projectId}/outline`) }}
                onCancel={cancel}
                terminating={terminating}
                errorMsg={errorMsg}
                haltedStep={haltedStep}
                retryLoading={retryLoading}
                onRetryStep={() => {
                  const step = haltedStep ?? selectedStepKey
                  if (step) void retryFailedStep(step, resumeParams)
                }}
                onInsightsUpdate={(updated) =>
                  setInsights(prev => prev ? { ...prev, ...updated } : (updated as typeof prev))
                }
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
