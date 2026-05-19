import React, { useEffect, useState } from 'react'
import { ImagePlus, Loader2, Wand2 } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { coverApi, charactersApi } from '../../api/client'
import type { Character } from '../../types'
import CharacterSpriteSheet from './CharacterSpriteSheet'

interface ImageProvider {
  id: string
  name: string
  model_name: string
}

interface CharacterPortraitPanelProps {
  projectId: string
  character: Character
  onUpdated: (c: Character) => void
  /** 当前筛选列表，用于批量生成 */
  batchTargets?: Character[]
}

/**
 * 人物立绘生成：选择图片模型 → 调用后端生成雪碧图 → 更新 store。
 */
export default function CharacterPortraitPanel({
  projectId,
  character,
  onUpdated,
  batchTargets,
}: CharacterPortraitPanelProps) {
  const [providers, setProviders] = useState<ImageProvider[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [styleHint, setStyleHint] = useState('Chinese xianxia illustration, vivid colors')
  const [generating, setGenerating] = useState(false)
  const [batching, setBatching] = useState(false)

  useEffect(() => {
    coverApi.imageProviders().then(res => {
      const list = res.data as ImageProvider[]
      setProviders(list)
      if (list.length > 0) setSelectedId(list[0].id)
    }).catch(() => {})
  }, [])

  const generateOne = async () => {
    if (!selectedId) return toast.error('请先在管理后台配置并启用图片模型（provider_type=image）')
    if (!character.appearance?.trim() && !character.clothing_style?.trim()) {
      return toast.error('请先填写外貌或服装描述，以便 AI 生成立绘')
    }
    setGenerating(true)
    try {
      const res = await charactersApi.generatePortrait(projectId, character.id, {
        llm_provider_id: selectedId,
        style_hint: styleHint.trim() || undefined,
      })
      const updated: Character = {
        ...character,
        avatar_url: res.data.avatar_url,
        extra: { ...character.extra, sprite_sheet: res.data.sprite_sheet },
      }
      onUpdated(updated)
      toast.success('立绘雪碧图已生成')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(typeof msg === 'string' ? msg : '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const generateBatch = async () => {
    if (!selectedId) return toast.error('请选择图片模型')
    const targets = (batchTargets?.length ? batchTargets : [character]).slice(0, 20)
    if (!confirm(`将为 ${targets.length} 名人物生成立绘（每人约 1–2 分钟），继续？`)) return
    setBatching(true)
    try {
      const res = await charactersApi.generatePortraitsBatch(projectId, {
        llm_provider_id: selectedId,
        character_ids: targets.map(c => c.id),
        style_hint: styleHint.trim() || undefined,
        skip_existing: true,
      })
      let ok = 0
      for (const item of res.data.results) {
        if (item.status === 'ok' && item.avatar_url && item.sprite_sheet) {
          ok += 1
          const found = targets.find(t => t.id === item.character_id)
          if (found) {
            onUpdated({
              ...found,
              avatar_url: item.avatar_url,
              extra: { ...found.extra, sprite_sheet: item.sprite_sheet },
            })
          }
        }
      }
      type BatchItem = { status: string }
      const skipped = res.data.results.filter((r: BatchItem) => r.status === 'skipped').length
      const failed = res.data.results.filter((r: BatchItem) => r.status === 'error').length
      toast.success(`完成：成功 ${ok}，跳过 ${skipped}，失败 ${failed}`)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(typeof msg === 'string' ? msg : '批量生成失败')
    } finally {
      setBatching(false)
    }
  }

  const busy = generating || batching

  return (
    <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 space-y-4">
      <div className="flex items-center gap-2 border-b border-gray-100 pb-4">
        <ImagePlus size={20} className="text-violet-500" />
        <h3 className="text-lg font-bold text-gray-900">立绘雪碧图</h3>
        <span className="text-xs text-gray-400">4 帧横排 · 图片模型生成</span>
      </div>

      <CharacterSpriteSheet character={character} />

      {providers.length === 0 ? (
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          未检测到图片模型。请在管理后台添加 LLM 提供者，并将类型设为 <code className="text-xs">image</code>。
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs font-medium text-gray-500">图片模型</span>
            <select
              value={selectedId}
              onChange={e => setSelectedId(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              disabled={busy}
            >
              {providers.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.model_name})</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-500">风格补充（英文更佳）</span>
            <input
              value={styleHint}
              onChange={e => setStyleHint(e.target.value)}
              className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              disabled={busy}
              placeholder="anime / realistic / ink wash..."
            />
          </label>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={generateOne}
          disabled={busy || providers.length === 0}
          className={clsx(
            'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors',
            busy ? 'bg-violet-300' : 'bg-violet-600 hover:bg-violet-700',
          )}
        >
          {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
          {generating ? '生成中…' : '生成当前人物立绘'}
        </button>
        {batchTargets && batchTargets.length > 1 && (
          <button
            type="button"
            onClick={generateBatch}
            disabled={busy || providers.length === 0}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-violet-200 text-violet-700 hover:bg-violet-50 disabled:opacity-50"
          >
            {batching ? <Loader2 size={16} className="animate-spin" /> : <ImagePlus size={16} />}
            批量生成筛选列表（{Math.min(batchTargets.length, 20)} 人）
          </button>
        )}
      </div>
    </section>
  )
}
