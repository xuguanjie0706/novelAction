import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Edit3,
  ImagePlus,
  Loader2,
  PenLine,
  RefreshCw,
  Settings,
  Sparkles,
  Star,
  Target,
  Upload,
  X,
  Layers,
} from 'lucide-react'
import toast from 'react-hot-toast'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import ActiveBootstrapResumeBar from '../components/Bootstrap/ActiveBootstrapResumeBar'
import { useBootstrapResumeBanner } from '../hooks/useBootstrapResumeBanner'
import {
  bootstrapRunsApi,
  coverApi,
  projectsApi,
  type BootstrapRunHistoryItem,
  type WritingConfig,
} from '../api/client'
import { authFetch } from '../api/authFetch'
import { useAppStore } from '../store'
import { clearActiveBootstrapRun } from '../utils/bootstrapActiveRun'
import type { ImageProviderBrief, Project } from '../types'

// ── SVG 封面（无图片提供者时的占位/预览） ─────────────────────────────────
const GENRE_THEMES: Record<string, {
  bg1: string; bg2: string; bg3: string; accent: string; symbol: string
}> = {
  '玄幻':  { bg1: '#1e0a3c', bg2: '#4a1d96', bg3: '#7c3aed', accent: '#c4b5fd', symbol: '⚡' },
  '修真':  { bg1: '#0f0522', bg2: '#2e1065', bg3: '#6d28d9', accent: '#a78bfa', symbol: '☯' },
  '仙侠':  { bg1: '#1a0533', bg2: '#701a75', bg3: '#a21caf', accent: '#f0abfc', symbol: '✦' },
  '都市':  { bg1: '#0c1a2e', bg2: '#1e3a8a', bg3: '#1d4ed8', accent: '#93c5fd', symbol: '◈' },
  '悬疑':  { bg1: '#0a0a0a', bg2: '#1c1917', bg3: '#292524', accent: '#a8a29e', symbol: '?' },
  '历史':  { bg1: '#1c0f00', bg2: '#451a03', bg3: '#92400e', accent: '#fcd34d', symbol: '⚔' },
  '言情':  { bg1: '#1f0515', bg2: '#500724', bg3: '#9d174d', accent: '#fbcfe8', symbol: '♡' },
  '科幻':  { bg1: '#001a19', bg2: '#064e3b', bg3: '#0f766e', accent: '#5eead4', symbol: '◉' },
  '武侠':  { bg1: '#1a0000', bg2: '#450a0a', bg3: '#b91c1c', accent: '#fca5a5', symbol: '刀' },
  default: { bg1: '#1c0a00', bg2: '#451a03', bg3: '#b45309', accent: '#fde68a', symbol: '✦' },
}

function getTheme(genre?: string) {
  if (!genre) return GENRE_THEMES.default
  for (const key of Object.keys(GENRE_THEMES)) {
    if (genre.includes(key)) return GENRE_THEMES[key]
  }
  return GENRE_THEMES.default
}

function wrapTitle(title: string, maxLen = 6): string[] {
  if (title.length <= maxLen) return [title]
  const lines: string[] = []
  for (let i = 0; i < title.length; i += maxLen) lines.push(title.slice(i, i + maxLen))
  return lines.slice(0, 3)
}

function generateCoverSvg(project: Project): string {
  const t = getTheme(project.genre)
  const lines = wrapTitle(project.title)
  const lineHeight = 52
  const titleY = 200 - ((lines.length - 1) * lineHeight) / 2
  const stars = Array.from({ length: 18 }, (_, i) => ({
    cx: ((i * 137) % 280) + 10, cy: ((i * 97) % 300) + 10,
    r: ((i * 13) % 3) + 1, opacity: ((i % 5) + 3) / 10,
  }))
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 420" width="300" height="420">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${t.bg1}"/>
      <stop offset="45%" stop-color="${t.bg2}"/>
      <stop offset="100%" stop-color="${t.bg3}"/>
    </linearGradient>
    <linearGradient id="spine" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${t.bg1}" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="${t.bg1}" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <radialGradient id="center" cx="50%" cy="50%">
      <stop offset="0%" stop-color="${t.bg3}" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="${t.bg1}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="300" height="420" fill="url(#bg)"/>
  <ellipse cx="150" cy="210" rx="160" ry="200" fill="url(#center)"/>
  ${stars.map(s => `<circle cx="${s.cx}" cy="${s.cy}" r="${s.r}" fill="${t.accent}" opacity="${s.opacity}"/>`).join('')}
  <circle cx="150" cy="210" r="120" fill="none" stroke="${t.accent}" stroke-width="0.5" opacity="0.2"/>
  <text x="150" y="80" text-anchor="middle" font-size="40" fill="${t.accent}" opacity="0.3" filter="url(#glow)">${t.symbol}</text>
  ${lines.map((line, i) => `<text x="150" y="${titleY + i * lineHeight}" text-anchor="middle" font-family="'PingFang SC','Microsoft YaHei',serif" font-size="38" font-weight="700" fill="${t.accent}" filter="url(#glow)">${line}</text>`).join('')}
  ${project.genre ? `<text x="150" y="${titleY + lines.length * lineHeight + 22}" text-anchor="middle" font-family="'PingFang SC','Microsoft YaHei',serif" font-size="15" fill="${t.accent}" opacity="0.7">${project.genre}</text>` : ''}
  <rect width="18" height="420" fill="url(#spine)"/>
  <line x1="60" y1="380" x2="240" y2="380" stroke="${t.accent}" stroke-width="0.8" opacity="0.4"/>
</svg>`
}

function svgToDataUrl(svg: string): string {
  return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)))
}

// ── 预设尺寸 ───────────────────────────────────────────────────────────────
const SIZE_OPTIONS = [
  { label: '1:1 方形 (1024×1024)', value: '1024x1024' },
  { label: '2:3 竖版 (1024×1536)', value: '1024x1536' },
  { label: '3:4 竖版 (1024×1365)', value: '1024x1365' },
  { label: '4:3 横版 (1365×1024)', value: '1365x1024' },
]

const MAX_COVER_FILE_BYTES = 15 * 1024 * 1024

// ── 更换封面弹窗（本地上传 / AI 生成）────────────────────────────────────────
interface CoverModalProps {
  project: Project
  onSave: (url: string) => void
  onClose: () => void
}

function CoverModal({ project, onSave, onClose }: CoverModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [coverTab, setCoverTab] = useState<'upload' | 'ai'>('upload')
  const [providers, setProviders] = useState<ImageProviderBrief[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  const [selectedId, setSelectedId] = useState<string>('')
  const [prompt, setPrompt] = useState(
    project.logline
      ? `Novel book cover for "${project.title}", ${project.genre ?? ''} genre. ${project.logline}. Dramatic lighting, cinematic composition, high quality digital art.`
      : `Novel book cover for "${project.title}", ${project.genre ?? ''} genre. Dramatic lighting, cinematic composition, high quality digital art.`
  )
  const [size, setSize] = useState('1024x1024')
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    coverApi.imageProviders()
      .then(res => {
        setProviders(res.data)
        if (res.data.length > 0) setSelectedId(res.data[0].id)
      })
      .catch(() => setProviders([]))
      .finally(() => setLoadingProviders(false))
  }, [])

  const processUploadFile = async (file: File | undefined | null) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error('请选择图片文件')
      return
    }
    if (file.size > MAX_COVER_FILE_BYTES) {
      toast.error('图片不能超过 15MB')
      return
    }
    setError(null)
    setUploading(true)
    try {
      const res = await coverApi.upload(project.id, file)
      const url = res.data.cover_url ?? null
      if (!url) throw new Error('未返回封面地址')
      setPreviewUrl(url)
      toast.success('已上传，确认后点击「使用此封面」')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '上传失败'
      setError(typeof msg === 'string' ? msg : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const generate = async () => {
    if (!selectedId) return toast.error('请先选择图片模型')
    if (!prompt.trim()) return toast.error('请填写封面描述')
    setError(null)
    setGenerating(true)
    setPreviewUrl(null)
    try {
      const res = await coverApi.generate(project.id, {
        llm_provider_id: selectedId,
        prompt: prompt.trim(),
        size,
        quality: 'standard',
      })
      const url = res.data.cover_url ?? res.data.data_url ?? res.data.image_url ?? null
      if (!url) throw new Error('未返回图片')
      setPreviewUrl(url)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '生成失败，请重试'
      setError(msg)
    } finally {
      setGenerating(false)
    }
  }

  const handleSave = async () => {
    if (!previewUrl) return
    setSaving(true)
    try {
      await projectsApi.update(project.id, { cover_url: previewUrl })
      onSave(previewUrl)
      toast.success('封面已保存！')
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const busyPreview = generating || uploading

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[90vh]">

        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <ImagePlus size={18} className="text-amber-500" />
            <h2 className="text-base font-semibold text-gray-900">更换封面</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1">
          <div className="p-6 flex flex-col gap-6 sm:flex-row sm:items-start">

            <div className="shrink-0 flex flex-col items-center gap-3 mx-auto sm:mx-0">
              <div className="relative h-[240px] w-[172px] overflow-hidden rounded-lg shadow-[0_8px_32px_rgba(0,0,0,0.25)] ring-1 ring-black/10 bg-gray-900">
                {busyPreview ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3">
                    <Loader2 size={28} className="animate-spin text-amber-400" />
                    <span className="text-xs text-amber-300/80 text-center px-3">
                      {generating ? '正在调用 AI 生成…' : '正在上传并压缩…'}
                    </span>
                  </div>
                ) : previewUrl ? (
                  <img src={previewUrl} alt="封面预览" className="h-full w-full object-cover" />
                ) : (
                  <img src={svgToDataUrl(generateCoverSvg(project))} alt="封面预览" className="h-full w-full object-cover" />
                )}
                <div className="pointer-events-none absolute left-0 top-0 h-full w-3 bg-gradient-to-r from-black/30 to-transparent" />
              </div>

              <div className="flex flex-col gap-2 w-full max-w-[172px]">
                {previewUrl && (
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving || busyPreview}
                    className="flex items-center justify-center gap-2 w-full rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-60"
                  >
                    {saving
                      ? <><Loader2 size={15} className="animate-spin" />保存中…</>
                      : <><CheckCircle2 size={15} />使用此封面</>
                    }
                  </button>
                )}
                <p className="text-[11px] text-center text-gray-400 leading-snug">
                  在右侧上传本地图或使用 AI 生成，再保存到作品
                </p>
              </div>
            </div>

            <div className="flex-1 min-w-0 flex flex-col gap-4">
              <div className="flex rounded-lg bg-gray-100 p-1 gap-1">
                <button
                  type="button"
                  onClick={() => { setCoverTab('upload'); setError(null) }}
                  className={`flex-1 flex items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition-colors ${
                    coverTab === 'upload'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Upload size={15} />
                  本地上传
                </button>
                <button
                  type="button"
                  onClick={() => { setCoverTab('ai'); setError(null) }}
                  className={`flex-1 flex items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition-colors ${
                    coverTab === 'ai'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Sparkles size={15} />
                  AI 生成
                </button>
              </div>

              {coverTab === 'upload' && (
                <div className="flex flex-col gap-3">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={e => {
                      processUploadFile(e.target.files?.[0])
                      e.target.value = ''
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className={`flex items-center justify-center gap-2 w-full rounded-lg border border-dashed px-4 py-10 text-sm text-gray-600 transition-colors hover:bg-amber-50/50 disabled:opacity-50 ${
                      dragOver
                        ? 'border-amber-400 bg-amber-50/80'
                        : 'border-gray-300 bg-gray-50 hover:border-amber-300'
                    }`}
                    onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={e => {
                      e.preventDefault()
                      setDragOver(false)
                      processUploadFile(e.dataTransfer.files?.[0])
                    }}
                  >
                    <div className={`flex flex-col items-center gap-2 ${dragOver ? 'text-amber-700' : ''}`}>
                      <Upload size={28} className="text-amber-500 opacity-80" />
                      <span className="font-medium text-gray-800">点击选择图片，或拖拽到此处</span>
                      <span className="text-xs text-gray-400">JPG、PNG、WebP、GIF，最大 15MB，将自动压缩为 WebP</span>
                    </div>
                  </button>
                </div>
              )}

              {coverTab === 'ai' && (
                <div className="flex flex-col gap-5">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                      图片模型
                    </label>
                    {loadingProviders ? (
                      <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
                        <Loader2 size={14} className="animate-spin" />加载中…
                      </div>
                    ) : providers.length === 0 ? (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                        <div className="flex items-start gap-2">
                          <AlertCircle size={15} className="mt-0.5 shrink-0 text-amber-600" />
                          <div>
                            <p className="text-sm font-medium text-amber-800">暂无图片模型</p>
                            <p className="mt-0.5 text-xs text-amber-700 leading-relaxed">
                              请前往管理后台添加类型为「image」的 LLM 提供者。
                            </p>
                            <a
                              href="/admin"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-700 hover:underline"
                            >
                              <Settings size={12} />管理后台配置
                            </a>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="relative">
                        <select
                          value={selectedId}
                          onChange={e => setSelectedId(e.target.value)}
                          className="w-full appearance-none rounded-lg border border-gray-200 bg-white px-3 py-2.5 pr-9 text-sm text-gray-800 outline-none focus:border-amber-400 focus:ring-1 focus:ring-amber-400"
                        >
                          {providers.map(p => (
                            <option key={p.id} value={p.id}>
                              {p.name}（{p.model_name}）
                            </option>
                          ))}
                        </select>
                        <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                      生成尺寸
                    </label>
                    <div className="relative">
                      <select
                        value={size}
                        onChange={e => setSize(e.target.value)}
                        className="w-full appearance-none rounded-lg border border-gray-200 bg-white px-3 py-2 pr-8 text-sm text-gray-700 outline-none focus:border-amber-400 focus:ring-1 focus:ring-amber-400"
                      >
                        {SIZE_OPTIONS.map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                      <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                      封面描述 <span className="font-normal normal-case text-gray-400">（提示词）</span>
                    </label>
                    <textarea
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                      rows={5}
                      placeholder="描述封面风格、画面、色调…"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 outline-none placeholder:text-gray-400 focus:border-amber-400 focus:bg-white focus:ring-1 focus:ring-amber-400 resize-none"
                    />
                    <p className="mt-1 text-xs text-gray-400">建议英文提示词效果更好。</p>
                  </div>

                  <button
                    type="button"
                    onClick={generate}
                    disabled={generating || loadingProviders || !selectedId || providers.length === 0}
                    className="flex items-center justify-center gap-2 w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-50"
                  >
                    {generating
                      ? <><Loader2 size={15} className="animate-spin" />生成中…</>
                      : <><Sparkles size={15} />{previewUrl ? '重新生成' : '开始生成'}</>
                    }
                  </button>
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3">
                  <AlertCircle size={15} className="mt-0.5 shrink-0 text-red-500" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 信息标签 ───────────────────────────────────────────────────────────────
function InfoTag({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl bg-gray-50 px-4 py-3">
      <Icon size={17} className="mt-0.5 shrink-0 text-amber-500" />
      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</div>
        <div className="mt-0.5 text-sm font-semibold text-gray-800">{value}</div>
      </div>
    </div>
  )
}

function statusLabel(s: Project['status']) {
  return { drafting: '规划中', writing: '连载中', completed: '已完成' }[s] ?? '规划中'
}
function statusColor(s: Project['status']) {
  return {
    drafting:  'bg-amber-100 text-amber-700 border-amber-200',
    writing:   'bg-emerald-100 text-emerald-700 border-emerald-200',
    completed: 'bg-blue-100 text-blue-700 border-blue-200',
  }[s] ?? 'bg-gray-100 text-gray-600 border-gray-200'
}

function runStatusLabel(status: string) {
  return {
    pending: '排队中',
    running: '生成中',
    awaiting_gate: '等待确认',
    done: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] ?? status
}

function runStatusColor(status: string) {
  return {
    pending: 'bg-gray-100 text-gray-600',
    running: 'bg-amber-100 text-amber-700',
    awaiting_gate: 'bg-indigo-100 text-indigo-700',
    done: 'bg-emerald-100 text-emerald-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-slate-100 text-slate-600',
  }[status] ?? 'bg-gray-100 text-gray-600'
}

function eventText(ev: Record<string, any>) {
  if (ev.event === 'step_start') return `开始：${ev.label || ev.step || '步骤'}`
  if (ev.event === 'step_done') {
    const detail = [ev.count != null ? `${ev.count} 条` : '', ev.preview || '']
      .filter(Boolean).join(' · ')
    return `完成：${ev.step || '步骤'}${detail ? `（${detail}）` : ''}`
  }
  if (ev.event === 'error') return `异常：${ev.message || ev.step || '未知错误'}`
  if (ev.event === 'gate_pending') {
    const st = ev.step ? String(ev.step) : ''
    const labels: Record<string, string> = {
      positioning: '等待你确认立项定位',
      power_systems: '等待你确认境界体系',
      characters: '等待你确认人物库',
      volumes: '等待你确认卷级骨架',
    }
    return labels[st] || '等待你确认后继续生成'
  }
  if (ev.event === 'gate_passed') return '已确认定位，继续生成'
  if (ev.event === 'cancelled') return ev.message || '生成已取消'
  if (ev.event === 'complete') return '整套流程已完成'
  return ev.event || '事件'
}

function GenerateJourneyPanel({ projectId }: { projectId: string }) {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<BootstrapRunHistoryItem[]>([])
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [cancellingRunId, setCancellingRunId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const aborters: AbortController[] = []

    const applyEvent = (runId: string, ev: Record<string, any>) => {
      setRuns((prev) => prev.map((r) => {
        if (r.run_id !== runId) return r
        const nextEvents = [...(r.events || []), ev]
        let nextStatus = r.status
        if (ev.event === 'complete') nextStatus = 'done'
        if (ev.event === 'gate_pending') nextStatus = 'awaiting_gate'
        if (ev.event === 'gate_passed') nextStatus = 'running'
        if (ev.event === 'error' && !ev.step) nextStatus = 'failed'
        return { ...r, status: nextStatus, events: nextEvents }
      }))
    }

    const subscribeRun = async (run: BootstrapRunHistoryItem) => {
      const controller = new AbortController()
      aborters.push(controller)
      try {
        const res = await authFetch(`/api/v1/bootstrap/runs/${run.run_id}/events`, { signal: controller.signal })
        if (!res.ok || !res.body) return
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (!raw || raw === '[DONE]') continue
            try {
              const ev = JSON.parse(raw)
              applyEvent(run.run_id, ev)
            } catch {
              // ignore malformed chunks
            }
          }
        }
      } catch {
        // keep silent; panel is best-effort
      }
    }

    const load = async () => {
      try {
        const res = await bootstrapRunsApi.listByProject(projectId)
        if (cancelled) return
        const items = res.data || []
        setRuns(items)
        items
          .filter((r) => r.status === 'running' || r.status === 'awaiting_gate')
          .forEach((r) => { void subscribeRun(r) })
      } finally {
        if (!cancelled) setLoadingRuns(false)
      }
    }

    void load()
    return () => {
      cancelled = true
      aborters.forEach((a) => a.abort())
    }
  }, [projectId])

  const cancelRun = async (runId: string) => {
    setCancellingRunId(runId)
    try {
      await bootstrapRunsApi.cancel(runId)
      setRuns((prev) =>
        prev.map((r) =>
          r.run_id === runId
            ? {
                ...r,
                status: 'cancelled',
                events: [...(r.events || []), { event: 'cancelled', message: '用户已取消生成' }],
              }
            : r
        )
      )
      toast.success('已请求停止生成')
    } catch {
      toast.error('停止生成失败')
    } finally {
      setCancellingRunId(null)
    }
  }

  return (
    <section className="mt-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900">
          <RefreshCw size={18} className="text-amber-400" />
          生成纪要
        </h2>
        <button
          type="button"
          onClick={() => navigate(`/bookshelf/${projectId}/recap`)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 transition-colors hover:bg-amber-100"
        >
          <Layers size={14} />
          结构化分区浏览
        </button>
      </div>
      <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        {loadingRuns ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 size={14} className="animate-spin" />载入生成记录...
          </div>
        ) : runs.length === 0 ? (
          <p className="text-sm text-gray-500">暂无一键生成记录。后续每次 AI 生成都会在这里保留完整流程日志。</p>
        ) : (
          <div className="space-y-4">
            {runs.map((run) => (
              <div key={run.run_id} className="rounded-xl border border-gray-100 p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs text-gray-400">
                    Run #{run.run_id.slice(0, 8)}
                    {run.created_at ? ` · ${new Date(run.created_at).toLocaleString('zh-CN')}` : ''}
                  </div>
                  <div className="flex items-center gap-2">
                    {(run.status === 'running' || run.status === 'awaiting_gate') && (
                      <button
                        type="button"
                        onClick={() => void cancelRun(run.run_id)}
                        disabled={cancellingRunId === run.run_id}
                        className="rounded-md border border-red-200 px-2 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        {cancellingRunId === run.run_id ? '停止中...' : '停止生成'}
                      </button>
                    )}
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${runStatusColor(run.status)}`}>
                      {runStatusLabel(run.status)}
                    </span>
                  </div>
                </div>
                {run.error_message && (
                  <div className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{run.error_message}</div>
                )}
                <div className="max-h-48 space-y-1 overflow-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                  {(run.events || []).length === 0 ? (
                    <div className="text-gray-400">暂无事件</div>
                  ) : (
                    (run.events || []).map((ev, idx) => (
                      <div key={`${run.run_id}-${idx}`}>- {eventText(ev)}</div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// ── 写作质量门控配置面板 ────────────────────────────────────────────────────
/**
 * 写作质量门控配置区块，嵌入项目详情页。
 *
 * 读取 /projects/{id}/writing-config，展示可调节的门控参数。
 * 每个参数独立保存（失焦或直接点击时 PATCH）。
 *
 * @param projectId - 当前项目 UUID
 */
function WritingConfigPanel({ projectId }: { projectId: string }) {
  const [cfg, setCfg] = useState<WritingConfig | null>(null)
  const [saving, setSaving] = useState(false)
  /**
   * 写配置保存后需同步更新 store，确保 ChapterEditor 从 currentProject.extra.writing_config
   * 读到的 writingConfig（包括 pre_write_warning_enabled）是最新值，不需要刷新页面才生效。
   */
  const currentProject = useAppStore(s => s.currentProject)
  const setCurrentProject = useAppStore(s => s.setCurrentProject)

  useEffect(() => {
    projectsApi.getWritingConfig(projectId)
      .then(res => setCfg(res.data.writing_config))
      .catch(() => { /* 静默失败，不影响主页渲染 */ })
  }, [projectId])

  const save = async (patch: Partial<typeof cfg>) => {
    if (!cfg) return
    const next = { ...cfg, ...patch }
    setCfg(next)
    setSaving(true)
    try {
      const res = await projectsApi.updateWritingConfig(projectId, patch as any)
      // 同步更新 store，让 ChapterEditor 的 writingConfig 立即感知新配置
      if (currentProject) {
        setCurrentProject({
          ...currentProject,
          extra: {
            ...((currentProject.extra as Record<string, unknown>) ?? {}),
            writing_config: res.data.writing_config,
          } as typeof currentProject.extra,
        })
      }
    } catch {
      toast.error('保存写作配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) return null

  return (
    <section className="mt-8">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
        <Target size={18} className="text-amber-400" />
        写作质量门控
        {saving && <Loader2 size={14} className="ml-1 animate-spin text-gray-400" />}
      </h2>
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm space-y-5">
        {/* 开关 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-800">启用质量门控循环</p>
            <p className="mt-0.5 text-xs text-gray-500">
              开启后每次写章节将自动质检；未达标时按策略重写，最多重试 {cfg.max_rewrite_attempts} 次
            </p>
          </div>
          <button
            type="button"
            onClick={() => save({ auto_quality_gate: !cfg.auto_quality_gate })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
              cfg.auto_quality_gate ? 'bg-amber-400' : 'bg-gray-200'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                cfg.auto_quality_gate ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        {cfg.auto_quality_gate && (
          <>
            {/* 综合分 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">综合质检分下限</label>
                <span className="text-sm font-semibold text-amber-600 w-8 text-right">
                  {cfg.min_overall_score.toFixed(1)}
                </span>
              </div>
              <input
                type="range" min="0" max="10" step="0.5"
                value={cfg.min_overall_score}
                onChange={e => setCfg(c => c ? { ...c, min_overall_score: parseFloat(e.target.value) } : c)}
                onMouseUp={e => save({ min_overall_score: parseFloat((e.target as HTMLInputElement).value) })}
                onTouchEnd={e => save({ min_overall_score: parseFloat((e.target as HTMLInputElement).value) })}
                className="w-full accent-amber-400"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0 宽松</span>
                <span className="text-gray-500">建议 6.0–7.5</span>
                <span>10 严格</span>
              </div>
            </div>

            {/* 订阅意愿分 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">章末订阅意愿分下限</label>
                <span className="text-sm font-semibold text-amber-600 w-8 text-right">
                  {cfg.min_subscribe_intent.toFixed(1)}
                </span>
              </div>
              <input
                type="range" min="0" max="10" step="0.5"
                value={cfg.min_subscribe_intent}
                onChange={e => setCfg(c => c ? { ...c, min_subscribe_intent: parseFloat(e.target.value) } : c)}
                onMouseUp={e => save({ min_subscribe_intent: parseFloat((e.target as HTMLInputElement).value) })}
                onTouchEnd={e => save({ min_subscribe_intent: parseFloat((e.target as HTMLInputElement).value) })}
                className="w-full accent-amber-400"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0 宽松</span>
                <span className="text-gray-500">独立门槛（章末钩子）</span>
                <span>10 严格</span>
              </div>
            </div>

            {/* 最大重写次数 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-gray-700">最大重写次数</label>
                <span className="text-sm font-semibold text-amber-600">{cfg.max_rewrite_attempts} 次</span>
              </div>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(n => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => save({ max_rewrite_attempts: n })}
                    className={`flex-1 rounded-lg border py-1.5 text-sm font-medium transition-colors ${
                      cfg.max_rewrite_attempts === n
                        ? 'border-amber-400 bg-amber-50 text-amber-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-400">
                第1次：初稿 · 第2次：定点修复 · 第3次及以上：全量重写。超出次数后章节置为「待审阅」。
              </p>
            </div>

            {/* 分隔线 */}
            <div className="border-t border-gray-100 pt-1" />

            {/* 写前预警开关 */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                  写前预警
                  <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-rose-50 text-rose-600 border border-rose-200">
                    实验性
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-gray-500 leading-relaxed">
                  开启后，每次门控写作前以「三十年主编」视角生成写前简报：锁定主角境界/位置/技能，给出开篇策略、冲突节拍、章末钩子设计和幻觉预防清单，注入正文 prompt。
                </p>
                <p className="mt-1 text-xs text-amber-600">
                  ⚠️ 会额外消耗一次 AI 调用，小模型/本地模型效果有限，推荐配合 Gemini 线路使用。
                </p>
              </div>
              <button
                type="button"
                onClick={() => save({ pre_write_warning_enabled: !cfg.pre_write_warning_enabled })}
                className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${
                  cfg.pre_write_warning_enabled ? 'bg-rose-400' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    cfg.pre_write_warning_enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────
export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [showCoverModal, setShowCoverModal] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [wizardRecoverRunId, setWizardRecoverRunId] = useState<string | null>(null)
  const [resumeBarHidden, setResumeBarHidden] = useState(false)
  const [resumeCancelLoading, setResumeCancelLoading] = useState(false)
  const { snapshot: bootstrapResumeSnapshot, refresh: refreshBootstrapResume } = useBootstrapResumeBanner(
    projectId ?? null,
  )

  const handleCancelBootstrapRun = async () => {
    const rid = bootstrapResumeSnapshot?.runId?.trim()
    if (!rid) return
    setResumeCancelLoading(true)
    try {
      await bootstrapRunsApi.cancel(rid)
      clearActiveBootstrapRun()
      toast.success('已终止生成')
      await refreshBootstrapResume()
    } catch {
      toast.error('终止失败，请重试')
    } finally {
      setResumeCancelLoading(false)
    }
  }

  useEffect(() => {
    if (!projectId) return
    projectsApi.get(projectId)
      .then(res => { setProject(res.data); setCurrentProject(res.data) })
      .catch(() => toast.error('加载小说信息失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  const enterWorkbench = (tab: 'outline' | 'write' | 'characters' | 'memory' = 'write') => {
    if (!project) return
    setCurrentProject(project)
    navigate(`/project/${project.id}/${tab}`)
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f8fafc]">
        <Loader2 size={36} className="animate-spin text-amber-400" />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f8fafc]">
        <BookOpen size={48} className="text-gray-300" />
        <p className="text-gray-500">找不到该小说</p>
        <button type="button" onClick={() => navigate('/bookshelf')} className="text-sm text-amber-600 hover:underline">
          返回书架
        </button>
      </div>
    )
  }

  const svgCover = svgToDataUrl(generateCoverSvg(project))
  const coverSrc = project.cover_url ?? svgCover

  return (
    <div className="min-h-screen bg-[#f8fafc]">
      {showCoverModal && (
        <CoverModal
          project={project}
          onSave={url => { setProject(p => p ? { ...p, cover_url: url } : p); setShowCoverModal(false) }}
          onClose={() => setShowCoverModal(false)}
        />
      )}
      {showWizard && (
        <GenerateWizard
          onClose={() => {
            setShowWizard(false)
            setWizardRecoverRunId(null)
            void refreshBootstrapResume()
          }}
          recoverRunId={wizardRecoverRunId}
          onRecoverConsumed={() => setWizardRecoverRunId(null)}
        />
      )}

      {/* 顶部导航 */}
      <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-5 sm:px-8">
          <button
            type="button"
            onClick={() => navigate('/bookshelf')}
            className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-900"
          >
            <ArrowLeft size={17} />书架
          </button>
          <ChevronRight size={14} className="text-gray-300" />
          <span className="flex-1 truncate text-sm font-medium text-gray-800">{project.title}</span>
          <button
            type="button"
            onClick={() => enterWorkbench('write')}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-amber-600"
          >
            <PenLine size={15} />进入创作
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-10 sm:px-8">
        <ActiveBootstrapResumeBar
          snapshot={bootstrapResumeSnapshot}
          hidden={resumeBarHidden}
          onContinue={() => {
            if (!bootstrapResumeSnapshot?.runId) return
            setWizardRecoverRunId(bootstrapResumeSnapshot.runId)
            setShowWizard(true)
            setResumeBarHidden(false)
          }}
          onHide={() => setResumeBarHidden(true)}
          onCancelRun={handleCancelBootstrapRun}
          cancelLoading={resumeCancelLoading}
        />

        {/* Hero：封面 + 基础信息 */}
        <div className="flex flex-col gap-10 sm:flex-row sm:items-start">

          {/* 封面 */}
          <div className="group relative mx-auto shrink-0 sm:mx-0">
            <div className="relative h-[300px] w-[210px] overflow-hidden rounded-xl shadow-[0_12px_48px_rgba(0,0,0,0.18)] ring-1 ring-black/10">
              <img src={coverSrc} alt={project.title} className="h-full w-full object-cover" />
              <div className="pointer-events-none absolute left-0 top-0 h-full w-4 bg-gradient-to-r from-black/30 to-transparent" />
              {/* 悬浮按钮 */}
              <div className="absolute inset-0 flex flex-col items-center justify-end gap-2 bg-black/0 pb-4 opacity-0 transition-all duration-200 group-hover:bg-black/40 group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() => setShowCoverModal(true)}
                  className="flex items-center gap-1.5 rounded-full bg-white/90 px-4 py-2 text-xs font-semibold text-gray-800 shadow-lg backdrop-blur transition-transform hover:scale-105"
                >
                  <Sparkles size={13} className="text-amber-500" />AI 生成封面
                </button>
                <button
                  type="button"
                  onClick={() => setShowCoverModal(true)}
                  className="flex items-center gap-1.5 rounded-full bg-white/70 px-3 py-1.5 text-xs text-gray-600 shadow backdrop-blur transition-transform hover:scale-105"
                >
                  <ImagePlus size={12} />更换封面
                </button>
              </div>
            </div>

            {/* 始终可见的 AI 入口 */}
            <button
              type="button"
              onClick={() => setShowCoverModal(true)}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-amber-300 bg-amber-50 py-2 text-xs font-medium text-amber-600 transition-colors hover:bg-amber-100"
            >
              <Sparkles size={12} />AI 生成封面
            </button>
          </div>

          {/* 右侧信息 */}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-start gap-3">
              <h1 className="text-3xl font-bold leading-tight text-gray-950 sm:text-4xl">{project.title}</h1>
              <span className={`mt-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${statusColor(project.status)}`}>
                {statusLabel(project.status)}
              </span>
            </div>

            {project.genre && (
              <div className="mt-2 flex flex-wrap gap-2">
                {project.genre.split(/[\/、，,]/).map(g => (
                  <span key={g} className="rounded-full bg-gray-100 px-3 py-0.5 text-xs font-medium text-gray-600">{g.trim()}</span>
                ))}
              </div>
            )}

            {project.logline && (
              <p className="mt-5 text-[15px] leading-relaxed text-gray-600">{project.logline}</p>
            )}

            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {project.target_words && (
                <InfoTag icon={Target} label="目标字数" value={`${(project.target_words / 10000).toFixed(0)} 万字`} />
              )}
              <InfoTag
                icon={Calendar}
                label="创建时间"
                value={new Date(project.created_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}
              />
              {project.updated_at && (
                <InfoTag
                  icon={Edit3}
                  label="最后更新"
                  value={new Date(project.updated_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}
                />
              )}
            </div>

            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => enterWorkbench('write')}
                className="flex items-center gap-2 rounded-xl bg-amber-500 px-7 py-3 text-sm font-semibold text-white shadow-[0_6px_20px_rgba(245,158,11,0.3)] transition-all hover:bg-amber-600 active:scale-95"
              >
                <PenLine size={16} />进入创作工作台
              </button>
              <button
                type="button"
                onClick={() => enterWorkbench('outline')}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                查看大纲
              </button>
              <button
                type="button"
                onClick={() => enterWorkbench('characters')}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                角色设定
              </button>
              <button
                type="button"
                onClick={() => navigate(`/bookshelf/${project.id}/recap`)}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                <Layers size={16} />
                结构化纪要
              </button>
            </div>
          </div>
        </div>

        {/* 故事简介 */}
        {project.premise && (
          <section className="mt-12">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
              <Star size={18} className="text-amber-400" fill="currentColor" />故事简介
            </h2>
            <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <p className="text-[15px] leading-8 text-gray-700 whitespace-pre-wrap">{project.premise}</p>
            </div>
          </section>
        )}

        {/* 世界观概述 */}
        {project.world_overview && (
          <section className="mt-8">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
              <BookOpen size={18} className="text-amber-400" />世界观概述
            </h2>
            <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <p className="text-[15px] leading-8 text-gray-700 whitespace-pre-wrap">{project.world_overview}</p>
            </div>
          </section>
        )}

        {/* 写作质量门控配置 */}
        <GenerateJourneyPanel projectId={project.id} />

        {/* 写作质量门控配置 */}
        <WritingConfigPanel projectId={project.id} />

        {/* 底部快速操作 */}
        <div className="mt-12 rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-orange-50 p-6">
          <h3 className="text-sm font-semibold text-gray-800">快速进入</h3>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {([
              { label: '写作', tab: 'write' as const, desc: '继续创作章节' },
              { label: '大纲', tab: 'outline' as const, desc: '查看故事结构' },
              { label: '角色', tab: 'characters' as const, desc: '管理人物设定' },
              { label: '记忆', tab: 'memory' as const, desc: '查看故事记忆' },
            ]).map(({ label, tab, desc }) => (
              <button
                key={tab}
                type="button"
                onClick={() => enterWorkbench(tab)}
                className="flex flex-col items-start rounded-xl border border-white bg-white/80 p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-amber-200 hover:shadow-md"
              >
                <span className="text-sm font-semibold text-gray-800">{label}</span>
                <span className="mt-0.5 text-xs text-gray-500">{desc}</span>
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
