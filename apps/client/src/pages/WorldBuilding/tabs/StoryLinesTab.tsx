/**
 * @file 世界观 — 故事线 CRUD
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, ChevronRight, GitBranch } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { storylinesApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { StoryLine } from '../../../types'
import { ChipSelect, EditorHeader, Field, Section, TextArea, TextInput } from '../shared/components'
import StorylineWeaveSummary from './StorylineWeaveSummary'
import { hasStorylineWeave } from '../../../utils/storylineWeaveUtils'

const LINE_TYPE_META: Record<string, { label: string; color: string }> = {
  main:       { label: '主线',   color: 'bg-purple-100 text-purple-700 border-purple-200' },
  sub:        { label: '支线',   color: 'bg-blue-100 text-blue-700 border-blue-200' },
  romance:    { label: '感情线', color: 'bg-pink-100 text-pink-700 border-pink-200' },
  growth:     { label: '成长线', color: 'bg-green-100 text-green-700 border-green-200' },
  mystery:    { label: '悬疑线', color: 'bg-gray-100 text-gray-700 border-gray-200' },
  faction:    { label: '势力线', color: 'bg-red-100 text-red-700 border-red-200' },
  antagonist: { label: '反派线', color: 'bg-orange-100 text-orange-700 border-orange-200' },
}

const STATUS_META: Record<string, { label: string; dot: string }> = {
  planned:  { label: '规划中', dot: 'bg-gray-400' },
  active:   { label: '进行中', dot: 'bg-green-500' },
  climax:   { label: '高潮中', dot: 'bg-red-500' },
  resolved: { label: '已完结', dot: 'bg-blue-400' },
  dropped:  { label: '已放弃', dot: 'bg-gray-300' },
}

export default function StoryLinesTab({ projectId }: { projectId: string }) {
  const { storyLines, setStoryLines, upsertStoryLine, removeStoryLine } = useAppStore()
  const [selected, setSelected] = useState<StoryLine | null>(null)
  const [form, setForm] = useState<Partial<StoryLine>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    storylinesApi.list(projectId).then(r => {
      setStoryLines(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
  }, [projectId])

  const selectItem = (s: StoryLine) => { setSelected(s); setForm({ ...s }) }

  const handleCreate = async () => {
    const res = await storylinesApi.create(projectId, { name: '新故事线', line_type: 'sub', status: 'planned' })
    upsertStoryLine(res.data); selectItem(res.data)
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const res = await storylinesApi.update(projectId, selected.id, form)
      upsertStoryLine(res.data); setSelected(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除这条故事线？')) return
    await storylinesApi.delete(projectId, id)
    removeStoryLine(id)
    const rest = storyLines.filter(s => s.id !== id)
    if (rest.length > 0) selectItem(rest[0]); else { setSelected(null); setForm({}) }
    toast.success('已删除')
  }

  const f = (key: keyof StoryLine) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  return (
    <div className="flex h-full">
      {/* 左栏 */}
      <div className="w-52 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">故事线</span>
          <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600">
            <Plus size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {storyLines.map(s => {
            const tm = LINE_TYPE_META[s.line_type] ?? LINE_TYPE_META.sub
            const sm = STATUS_META[s.status] ?? STATUS_META.planned
            return (
              <button
                key={s.id}
                onClick={() => selectItem(s)}
                className={clsx(
                  'w-full flex items-start gap-2 px-4 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50'
                )}
              >
                <span className={clsx('mt-0.5 w-1.5 h-1.5 rounded-full shrink-0', sm.dot)} />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-800 truncate">{s.name}</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className={clsx('text-xs px-1.5 py-0.5 rounded border', tm.color)}>{tm.label}</span>
                    {hasStorylineWeave(s) && (
                      <span className="text-[9px] text-indigo-600">织网</span>
                    )}
                  </div>
                </div>
              </button>
            )
          })}
          {storyLines.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无故事线</p>}
        </div>
      </div>

      {/* 右栏 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (
          <div className="max-w-2xl mx-auto p-6 space-y-3">
            <EditorHeader
              name={form.name ?? selected.name}
              badge={<>
                <span className={clsx('text-xs px-2 py-0.5 rounded-full border font-medium', LINE_TYPE_META[form.line_type ?? 'sub']?.color)}>
                  {LINE_TYPE_META[form.line_type ?? 'sub']?.label}
                </span>
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  <span className={clsx('w-2 h-2 rounded-full', STATUS_META[form.status ?? 'planned']?.dot)} />
                  {STATUS_META[form.status ?? 'planned']?.label}
                </span>
              </>}
              onDelete={() => handleDelete(selected.id)}
              saving={saving} onSave={handleSave}
            />

            <Section title="基本设定" icon={<GitBranch size={12} />}>
              <Field label="故事线名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
              <Field label="线型">
                <ChipSelect value={form.line_type ?? 'sub'} onChange={f('line_type')}
                  options={Object.entries(LINE_TYPE_META).map(([k, v]) => ({ value: k, label: v.label, color: v.color }))} />
              </Field>
              <Field label="状态">
                <ChipSelect value={form.status ?? 'planned'} onChange={f('status')}
                  options={Object.entries(STATUS_META).map(([k, v]) => ({ value: k, label: v.label }))} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="起始章节">
                  <input type="number" value={form.start_chapter ?? ''} onChange={e => setForm(p => ({ ...p, start_chapter: Number(e.target.value) || undefined }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
                <Field label="预计结束章节">
                  <input type="number" value={form.end_chapter ?? ''} onChange={e => setForm(p => ({ ...p, end_chapter: Number(e.target.value) || undefined }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
              </div>
            </Section>

            <Section title="内容详情" icon={<ChevronRight size={12} />}>
              <Field label="故事线简述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} placeholder="这条线讲什么故事？" /></Field>
              <Field label="核心矛盾"><TextArea value={form.core_conflict ?? ''} onChange={f('core_conflict')} rows={3} placeholder="核心冲突是什么？" /></Field>
              <Field label="解决方向"><TextArea value={form.resolution_direction ?? ''} onChange={f('resolution_direction')} rows={2} placeholder="预计如何收尾？" /></Field>
            </Section>

            <Section title="织网导演单" icon={<GitBranch size={12} />}>
              <StorylineWeaveSummary projectId={projectId} storyline={selected} />
              <Link
                to={`/project/${projectId}/storyweave`}
                className="inline-block text-xs text-indigo-600 hover:underline mt-2"
              >
                查看全书织网矩阵 →
              </Link>
            </Section>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <GitBranch size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">点击左上角 + 新建故事线</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
