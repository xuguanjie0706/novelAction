/**
 * CoverModal — 更换封面弹窗（本地上传 / AI 生成）
 *
 * 独立子组件，内部管理所有封面上传 & AI 生成状态。
 * 依赖 coverApi / projectsApi，无 store 写入。
 */
import React, { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ImagePlus,
  Loader2,
  Settings,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { coverApi, projectsApi } from '../../api/client'
import { generateCoverSvg, svgToDataUrl } from './CoverSvgUtils'
import type { ImageProviderBrief, Project } from '../../types'

// ── 预设尺寸 ───────────────────────────────────────────────────────────────
const SIZE_OPTIONS = [
  { label: '1:1 方形 (1024×1024)', value: '1024x1024' },
  { label: '2:3 竖版 (1024×1536)', value: '1024x1536' },
  { label: '3:4 竖版 (1024×1365)', value: '1024x1365' },
  { label: '4:3 横版 (1365×1024)', value: '1365x1024' },
]

const MAX_COVER_FILE_BYTES = 15 * 1024 * 1024

export interface CoverModalProps {
  project: Project
  onSave: (url: string) => void
  onClose: () => void
}

export default function CoverModal({ project, onSave, onClose }: CoverModalProps) {
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
