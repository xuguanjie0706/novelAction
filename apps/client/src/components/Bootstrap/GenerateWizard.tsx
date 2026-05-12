/**
 * @file GenerateWizard — 一键生成小说的主向导面板
 *
 * 职责：
 * - 渲染「输入 → 生成中 → 闸门确认 → 完成」四阶段 UI
 * - SSE 业务状态委托给 useBootstrapStream hook
 * - 本文件 < 450 行
 *
 * 阶段流转（由 hook 驱动）：
 *   input → generating → gate（立项定位确认）→ generating → done
 *
 * 注意：单次全量（single_shot）模式不经过 gate；gate 仅用于串行模式。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X, CheckCircle, Loader, AlertCircle, ChevronRight, ShieldAlert, BookOpen } from 'lucide-react'
import clsx from 'clsx'
import { llmApi, projectsApi } from '../../api/client'
import type { LlmOverview } from '../../types'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../store'
import { TargetWordsInput } from '../TargetWordsInput'
import { useBootstrapStream } from './hooks/useBootstrapStream'
import PositioningGatePanel from './PositioningGatePanel'

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
    phase, steps, errorMsg, projectId, positioningData,
    startGenerate: hookStart, handleResume, cancel: hookCancel,
  } = useBootstrapStream()

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

  /**
   * 闸门确认：提交用户审阅/编辑后的立项定位，继续执行图的后半段。
   * @param positioning - 用户确认或修改后的立项定位 JSON
   */
  async function handleGateConfirm(positioning: Record<string, any>) {
    setResumeLoading(true)
    try {
      await handleResume(positioning, {
        modelProfile: modelProfileFromRoute(aiBackendRoute),
        llmProviderId: llmProviderIdFromRoute(aiBackendRoute),
      })
    } finally {
      setResumeLoading(false)
    }
  }

  function cancel() {
    hookCancel()
    onClose()
  }

  // ── 渲染 ─────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh] overflow-hidden">

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

        {/* ── 闸门阶段：立项定位确认 ── */}
        {phase === 'gate' && positioningData && (
          <PositioningGatePanel
            positioning={positioningData}
            onConfirm={handleGateConfirm}
            loading={resumeLoading}
          />
        )}

        {/* ── 生成中 / 完成 ── */}
        {(phase === 'generating' || phase === 'done') && (
          <div className="flex flex-col flex-1 overflow-hidden">
            {/* 固定顶部：Logline 摘要 */}
            <div className="px-6 pt-5 pb-3 shrink-0">
              <p className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed line-clamp-2">
                "{logline}"
              </p>
            </div>

            {/* 可滚动步骤列表 */}
            <div className="flex-1 overflow-y-auto px-6 py-1 space-y-2">
              {steps.map(step => (
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
                  <div className="shrink-0 mt-0.5">
                    {step.status === 'pending' && <div className="w-5 h-5 rounded-full border-2 border-gray-200" />}
                    {step.status === 'running' && <Loader size={18} className="text-amber-500 animate-spin" />}
                    {step.status === 'done'    && <CheckCircle size={18} className="text-green-500" />}
                    {step.status === 'error'   && <AlertCircle size={18} className="text-red-500" />}
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

            {/* 固定底部：提示 / 错误 / 洞察 / 按钮 */}
            <div className="px-6 pb-6 pt-3 shrink-0 space-y-3">
              {phase === 'generating' && waitSec >= 8 && !errorMsg && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 leading-relaxed">
                  仍在等待模型返回…串行方案下每一步都会单独请求当前所选线路，耗时因模型与网络而异。
                  若长期无响应，请确认该线路接口可用；需要单次大 JSON 时更推荐「方案 B · 单次全量」。
                </p>
              )}

              {errorMsg && (
                <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{errorMsg}</div>
              )}

              {/* 完成后：编辑洞察摘要卡 */}
              {phase === 'done' && insights && (
                <div className="space-y-2">
                  {insights.consistency_issues.length > 0 && (
                    <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs">
                      <ShieldAlert size={14} className="text-amber-500 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-medium text-amber-800">发现 {insights.consistency_issues.length} 处一致性待确认项</span>
                        <p className="text-amber-700 mt-0.5 leading-relaxed">
                          {insights.consistency_issues.slice(0, 2).map((issue: any) =>
                            typeof issue === 'string' ? issue : (issue.description || issue.issue || '')
                          ).filter(Boolean).join('；')}
                          {insights.consistency_issues.length > 2 && `…等${insights.consistency_issues.length}项`}
                        </p>
                      </div>
                    </div>
                  )}
                  {insights.opening_contract?.chapter1_hook && (
                    <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2.5 text-xs">
                      <BookOpen size={14} className="text-blue-500 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-medium text-blue-800">开局追读承诺已生成</span>
                        <p className="text-blue-700 mt-0.5 leading-relaxed line-clamp-2">
                          第1章钩子：{insights.opening_contract.chapter1_hook}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {phase === 'done' && projectId && (
                <button
                  onClick={() => { onClose(); navigate(`/project/${projectId}/outline`) }}
                  className="w-full py-3 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
                >
                  进入工作台
                  <ChevronRight size={16} />
                </button>
              )}

              {phase === 'generating' && (
                <button onClick={cancel} className="w-full py-2 text-sm text-gray-400 hover:text-gray-600">
                  取消
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
