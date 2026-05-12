import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X, CheckCircle, Loader, AlertCircle, ChevronRight, ShieldAlert, BookOpen } from 'lucide-react'
import clsx from 'clsx'
import { llmApi, projectsApi } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { LlmOverview } from '../../types'
import { llmProviderIdFromRoute, modelProfileFromRoute, routeLlmProviderPayload, useAppStore } from '../../store'
import { TargetWordsInput } from '../TargetWordsInput'

// ── 字数目标选项 ──────────────────────────────────────────────
const WORD_OPTIONS = [
  { label: '短篇',   value: 800000,  desc: '80万字 · 约6卷' },
  { label: '标准',   value: 1200000, desc: '120万字 · 约9卷' },
  { label: '长篇',   value: 1500000, desc: '150万字 · 约11卷' },
  { label: '超长篇', value: 2000000, desc: '200万字 · 约15卷' },
] as const

interface Props {
  onClose: () => void
}

type StepKey =
  | 'project' | 'settings' | 'characters' | 'outline' | 'memory' | 'relations'
  | 'opening_contract' | 'vol1_chapters' | 'ch1_scenes' | 'consistency'
  | 'all' | 'saving'
type StepStatus = 'pending' | 'running' | 'done' | 'error'

interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  detail?: string   // count / preview
  /** 当前仍在飞行中的子步骤数量（多个后端 step 合并到同一卡片时使用） */
  inflight: number
}

const STEP_DEFS: { key: StepKey; label: string }[] = [
  { key: 'project',          label: '项目基础信息' },
  { key: 'settings',         label: '世界观设定卡' },
  { key: 'characters',       label: '人物库' },
  { key: 'outline',          label: '卷级结构规划' },
  { key: 'memory',           label: '记忆库种子' },
  { key: 'relations',        label: '人物关系' },
  { key: 'opening_contract', label: '开局追读承诺' },
  { key: 'vol1_chapters',    label: '第一卷章级大纲' },
  { key: 'ch1_scenes',       label: '第1章场景蓝图' },
  { key: 'consistency',      label: '全局一致性扫描' },
]

type Mode = 'sequential' | 'single_shot'

const STEP_KEY_ALIAS: Record<string, StepKey> = {
  // Step 0 立项会议：后端 step=positioning，UI 归到「项目基础信息」卡片
  positioning: 'project',
  // 世界观相关结构化子步骤归并到”世界观设定卡”
  power_systems: 'settings',
  factions: 'settings',
  storylines: 'settings',
  skills: 'settings',
  items: 'settings',
  settings: 'settings',
  // 其它后端步骤对齐前端卡片
  volumes: 'outline',
  // Step 12-14：后端 step 名与前端 key 一致，toDisplayStepKey 会直接命中 STEP_DEFS，alias 仅作备份
  opening_contract: 'opening_contract',
  vol1_chapters:    'vol1_chapters',
  ch1_scenes:       'ch1_scenes',
  consistency:      'consistency',
}

function toDisplayStepKey(step: unknown): StepKey | null {
  if (typeof step !== 'string') return null
  if (STEP_DEFS.some(s => s.key === step)) return step as StepKey
  return STEP_KEY_ALIAS[step] ?? null
}

export default function GenerateWizard({ onClose }: Props) {
  const navigate = useNavigate()
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const setAiBackendRoute = useAppStore(s => s.setAiBackendRoute)
  const [phase, setPhase] = useState<'input' | 'generating' | 'done'>('input')
  const [logline, setLogline] = useState('')
  const [mode, setMode] = useState<Mode>('sequential')
  const [targetWords, setTargetWords] = useState(1200000)
  const [customWordMode, setCustomWordMode] = useState(false)
  const [steps, setSteps] = useState<StepState[]>(
    STEP_DEFS.map(s => ({ ...s, status: 'pending', inflight: 0 }))
  )
  const [errorMsg, setErrorMsg] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [insights, setInsights] = useState<{ consistency_issues: any[]; opening_contract: Record<string,any> } | null>(null)
  const [llmOverview, setLlmOverview] = useState<LlmOverview | null>(null)
  const [llmLoading, setLlmLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const isSubmittingRef = useRef(false)   // 防止重复提交
  const streamCompleteRef = useRef(false) // 是否收到 complete（用于检测半道断流）
  const [waitSec, setWaitSec] = useState(0)

  useEffect(() => {
    let alive = true
    setLlmLoading(true)
    llmApi.overview()
      .then(res => {
        if (!alive) return
        setLlmOverview(res.data)
      })
      .catch(() => {
        if (!alive) return
        setLlmOverview(null)
      })
      .finally(() => {
        if (!alive) return
        setLlmLoading(false)
      })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (phase !== 'generating') return
    setWaitSec(0)
    const id = window.setInterval(() => setWaitSec(s => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [phase])

  useEffect(() => {
    if (!llmOverview?.remote_providers?.length) return
    const pick = () =>
      llmOverview.remote_providers.find(p => p.is_default) ?? llmOverview.remote_providers[0]

    if (aiBackendRoute === 'remote') {
      const def = pick()
      setAiBackendRoute(`remote:${def.id}`)
      return
    }
    if (aiBackendRoute.startsWith('remote:')) {
      const id = aiBackendRoute.slice('remote:'.length)
      const ok = llmOverview.remote_providers.some(p => p.id === id)
      if (!ok) {
        const def = pick()
        setAiBackendRoute(`remote:${def.id}`)
      }
    }
  }, [llmOverview, aiBackendRoute, setAiBackendRoute])

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

  // ── 开始生成 ──────────────────────────────────────────────
  const startGenerate = async () => {
    if (!logline.trim() || isSubmittingRef.current) return
    isSubmittingRef.current = true
    streamCompleteRef.current = false
    setPhase('generating')
    setErrorMsg('')
    setWaitSec(0)

    // single_shot 模式用两个虚拟步骤
    // 首步立刻标为 running：SSE 常被代理/缓冲，首个 step_start 可能在整段 AI 结束后才到，否则长时间只有空心圆、无转圈
    if (mode === 'single_shot') {
      setSteps([
        { key: 'all',    label: 'AI 全量生成（单次调用）', status: 'running',  inflight: 1 },
        { key: 'saving', label: '写入数据库',               status: 'pending',  inflight: 0 },
      ])
    } else {
      setSteps(STEP_DEFS.map((s, i) => ({ ...s, status: i === 0 ? 'running' : 'pending', inflight: i === 0 ? 1 : 0 })))
    }

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const res = await authFetch('/api/v1/bootstrap/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          logline: logline.trim(),
          mode,
          target_words: targetWords,
          model_profile: modelProfileFromRoute(aiBackendRoute),
          ...routeLlmProviderPayload(aiBackendRoute),
        }),
        signal: abort.signal,
      })

      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `请求失败 (${res.status})`)
      }
      if (!res.body) {
        throw new Error('响应无流式正文')
      }

      const reader = res.body.getReader()
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
      if (!streamCompleteRef.current && !abort.signal.aborted) {
        setErrorMsg(prev => prev || '连接已结束但未完成生成（可能后端中断或代理超时），请查看后端日志后重试。')
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
    const displayStep = toDisplayStepKey(step)

    if (event === 'step_start') {
      if (!displayStep) return
      // inflight +1：多个后端子步骤可能合并到同一张显示卡片（如 power_systems/factions/settings 全部→'settings'）
      // 只要还有子步骤在飞行就保持 running，避免中途短暂显示 done 后又翻回 running
      setSteps(prev => prev.map(s =>
        s.key === displayStep
          ? { ...s, status: 'running', inflight: s.inflight + 1, label: label ?? s.label }
          : s
      ))
    } else if (event === 'step_done') {
      if (!displayStep) return
      const detail = [
        count != null ? `${count} 条` : '',
        preview ?? '',
      ].filter(Boolean).join(' · ')
      // inflight -1：只有归零时才真正标为 done，避免其他子步骤还在进行时提前完成
      setSteps(prev => prev.map(s => {
        if (s.key !== displayStep) return s
        const nextInflight = Math.max(0, s.inflight - 1)
        return {
          ...s,
          inflight: nextInflight,
          status: nextInflight === 0 ? 'done' : 'running',
          detail: detail || s.detail,
        }
      }))
    } else if (event === 'error') {
      const msg = typeof message === 'string' && message.trim() ? message : '生成失败'
      if (displayStep) {
        setSteps(prev => prev.map(s =>
          s.key === displayStep
            ? { ...s, status: 'error', inflight: Math.max(0, s.inflight - 1), detail: msg }
            : s
        ))
        setErrorMsg(`[${displayStep}] ${msg}`)
      } else {
        setSteps(prev => {
          const running = prev.findIndex(s => s.status === 'running')
          if (running === -1) return prev
          return prev.map((s, i) =>
            i === running ? { ...s, status: 'error' as const, detail: msg } : s
          )
        })
        setErrorMsg(msg)
      }
    } else if (event === 'complete') {
      streamCompleteRef.current = true
      setProjectId(project_id)
      setPhase('done')
      // partial=true：流程中断但 project 已创建，提示内容不完整
      if (evt.partial) {
        setErrorMsg(prev => prev || '部分步骤未完成，已保存的内容可在工作台中查看和补全。')
      }
      // 拉取 Bootstrap 后写入的编辑洞察数据
      if (project_id) {
        projectsApi.getInsights(project_id)
          .then(res => setInsights(res.data))
          .catch(() => {/* 非关键，忽略 */})
      }
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
    onClose()
  }

  // ── 渲染 ──────────────────────────────────────────────────
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

            {/* 模式选择 */}
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
                    mode === 'single_shot'
                      ? 'border-blue-400 bg-blue-50'
                      : 'border-gray-100 hover:border-gray-200'
                  )}
                >
                  <div className="text-sm font-semibold text-gray-800 mb-1">
                    方案 B · 单次全量
                  </div>
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
                    <>
                      · 约 {Math.round(targetWords / 2300)} 章 /{' '}
                      {Math.ceil(Math.round(targetWords / 2300) / 60)} 卷
                    </>
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
                      <div className={clsx(
                        'text-sm font-semibold',
                        targetWords === opt.value ? 'text-amber-700' : 'text-gray-700'
                      )}>
                        {opt.label}
                      </div>
                      <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              )}
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

            {/* 固定底部：提示 / 错误 / 洞察 / 按钮 */}
            <div className="px-6 pb-6 pt-3 shrink-0 space-y-3">
              {phase === 'generating' && waitSec >= 8 && !errorMsg && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 leading-relaxed">
                  仍在等待模型返回…串行方案下每一步都会单独请求当前所选线路，耗时因模型与网络而异。
                  若长期无响应，请确认该线路接口可用；需要单次大 JSON 时更推荐「方案 B · 单次全量」。
                </p>
              )}

              {errorMsg && (
                <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  {errorMsg}
                </div>
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

              {phase === 'generating' && (
                <button
                  onClick={cancel}
                  className="w-full py-2 text-sm text-gray-400 hover:text-gray-600"
                >
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
