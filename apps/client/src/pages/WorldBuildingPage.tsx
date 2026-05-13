import React, { useCallback, useEffect, useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Trash2, ChevronRight, GitBranch, Zap, Sword, Package, Shield, Search, MapPin } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { storylinesApi, powerSystemsApi, skillsApi, itemsApi, factionsApi, locationsApi } from '../api/client'
import { useAppStore } from '../store'
import type { StoryLine, PowerLevel, PowerSystem, Skill, Item, Faction, Location } from '../types'

// ─────────────────────────────────────────────────────────
//  Sub-tab 配置
// ─────────────────────────────────────────────────────────

type SubTab = 'storylines' | 'power' | 'skills' | 'items' | 'factions' | 'locations'

const SUB_TABS: { key: SubTab; label: string; icon: React.ElementType; color: string }[] = [
  { key: 'storylines', label: '故事线', icon: GitBranch, color: 'text-purple-600' },
  { key: 'power',      label: '境界体系', icon: Zap,       color: 'text-amber-600' },
  { key: 'skills',     label: '功法技能', icon: Sword,     color: 'text-blue-600'  },
  { key: 'items',      label: '道具法宝', icon: Package,   color: 'text-emerald-600'},
  { key: 'factions',   label: '势力',    icon: Shield,    color: 'text-red-600'   },
  { key: 'locations',  label: '地点',    icon: MapPin,    color: 'text-sky-600'   },
]

// ─────────────────────────────────────────────────────────
//  通用工具
// ─────────────────────────────────────────────────────────

/** 后端/模型偶发把本应是字符串的字段写成 { description: string }，不能直接当 React 子节点渲染 */
function stringFromLoose(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'object' && 'description' in (v as object)) {
    const d = (v as { description?: unknown }).description
    return typeof d === 'string' ? d : ''
  }
  return ''
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
    />
  )
}

function TextArea({ value, onChange, rows = 3, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
  return (
    <textarea
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      rows={rows}
      placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none"
    />
  )
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

function SaveBtn({ saving, onClick }: { saving: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={saving}
      className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors font-medium shadow-sm"
    >
      {saving ? '保存中…' : '保存'}
    </button>
  )
}

/** 芯片式分类选择器，替代 <select> 下拉 */
function ChipSelect({ value, onChange, options }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string; color?: string; icon?: string }[]
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => (
        <button key={opt.value} type="button" onClick={() => onChange(opt.value)}
          className={clsx(
            'text-xs px-2.5 py-1 rounded-lg border font-medium transition-all',
            value === opt.value
              ? (opt.color ?? 'bg-amber-100 text-amber-700 border-amber-300 shadow-sm')
              : 'bg-white text-gray-400 border-gray-200 hover:border-gray-300 hover:text-gray-600'
          )}>
          {opt.icon && <span className="mr-1">{opt.icon}</span>}
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** 带标题栏的分区卡片 */
function Section({ title, icon, children, accent }: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  accent?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      <div className={clsx('px-4 py-2 border-b border-gray-100 flex items-center gap-2', accent ?? 'bg-gray-50/60')}>
        {icon && <span className="text-gray-400 flex items-center">{icon}</span>}
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">{title}</span>
      </div>
      <div className="p-4 space-y-3.5">
        {children}
      </div>
    </div>
  )
}

/** 编辑页顶部标题栏：名称大字 + 操作按钮 */
function EditorHeader({ name, subtitle, badge, onDelete, saving, onSave }: {
  name: string
  subtitle?: string
  badge?: React.ReactNode
  onDelete: () => void
  saving: boolean
  onSave: () => void
}) {
  return (
    <div className="flex items-start justify-between gap-4 pb-2">
      <div className="min-w-0">
        <h2 className="text-xl font-bold text-gray-900 leading-tight truncate">{name || '未命名'}</h2>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        {badge && <div className="mt-1.5 flex flex-wrap gap-1">{badge}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0 mt-0.5">
        <button onClick={onSave} disabled={saving}
          className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-xs rounded-lg transition-colors font-medium shadow-sm">
          {saving ? '保存中…' : '保存'}
        </button>
        <button onClick={onDelete} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  故事线 Tab
// ─────────────────────────────────────────────────────────

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

function StoryLinesTab({ projectId }: { projectId: string }) {
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
                  <span className={clsx('text-xs px-1.5 py-0.5 rounded border', tm.color)}>{tm.label}</span>
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

// ─────────────────────────────────────────────────────────
//  境界体系 Tab
// ─────────────────────────────────────────────────────────

const SYSTEM_TYPE_META: Record<string, string> = {
  cultivation: '修炼/境界',
  magic: '魔法',
  ability: '异能',
  tech: '科技',
  hybrid: '混合体系',
}

function PowerSystemTab({ projectId }: { projectId: string }) {
  const { powerSystems, setPowerSystems, upsertPowerSystem, removePowerSystem } = useAppStore()
  const [selected, setSelected] = useState<PowerSystem | null>(null)
  const [form, setForm] = useState<Partial<PowerSystem>>({})
  const [saving, setSaving] = useState(false)
  const [levelInput, setLevelInput] = useState('')

  useEffect(() => {
    powerSystemsApi.list(projectId).then(r => {
      setPowerSystems(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
  }, [projectId])

  const selectItem = (s: PowerSystem) => { setSelected(s); setForm({ ...s }) }

  const handleCreate = async () => {
    const res = await powerSystemsApi.create(projectId, { name: '新境界体系', system_type: 'cultivation', levels: [] })
    upsertPowerSystem(res.data); selectItem(res.data)
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const res = await powerSystemsApi.update(projectId, selected.id, form)
      upsertPowerSystem(res.data); setSelected(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    await powerSystemsApi.delete(projectId, id)
    removePowerSystem(id)
    const rest = powerSystems.filter(s => s.id !== id)
    if (rest.length > 0) selectItem(rest[0]); else { setSelected(null); setForm({}) }
    toast.success('已删除')
  }

  const addLevel = () => {
    const name = levelInput.trim()
    if (!name) return
    const levels = [...(form.levels ?? []), {
      rank: (form.levels?.length ?? 0) + 1,
      name,
      description: '',
      requirements: '',
      abilities: [],
      sub_level_count: 9,
      approximate_chapter: '',
    }]
    setForm(p => ({ ...p, levels }))
    setLevelInput('')
  }

  const removeLevel = (idx: number) => {
    const levels = (form.levels ?? []).filter((_, i) => i !== idx).map((l, i) => ({ ...l, rank: i + 1 }))
    setForm(p => ({ ...p, levels }))
    setAbilityInputs(prev => {
      const next: Record<number, string> = {}
      Object.entries(prev).forEach(([key, value]) => {
        const numericKey = Number(key)
        if (numericKey < idx) next[numericKey] = value
        if (numericKey > idx) next[numericKey - 1] = value
      })
      return next
    })
  }

  const updateLevel = (idx: number, key: keyof PowerLevel, val: PowerLevel[keyof PowerLevel]) => {
    const levels = (form.levels ?? []).map((l, i) => i === idx ? { ...l, [key]: val } : l)
    setForm(p => ({ ...p, levels }))
  }

  // 境界特性 chip 管理
  const [abilityInputs, setAbilityInputs] = useState<Record<number, string>>({})
  const addAbility = (idx: number) => {
    const val = (abilityInputs[idx] ?? '').trim()
    if (!val) return
    const lv = (form.levels ?? [])[idx]
    const abilities = [...(lv?.abilities ?? []).map(a => stringFromLoose(a)).filter(Boolean), val]
    updateLevel(idx, 'abilities', abilities)
    setAbilityInputs(p => ({ ...p, [idx]: '' }))
  }
  const removeAbility = (idx: number, aIdx: number) => {
    const lv = (form.levels ?? [])[idx]
    const abilities = (lv?.abilities ?? []).filter((_, i: number) => i !== aIdx)
    updateLevel(idx, 'abilities', abilities)
  }
  const updateSubLevelCount = (idx: number, raw: string) => {
    if (!raw.trim()) {
      updateLevel(idx, 'sub_level_count', 9)
      return
    }
    const next = Number(raw)
    if (!Number.isFinite(next)) return
    updateLevel(idx, 'sub_level_count', Math.min(99, Math.max(1, Math.round(next))))
  }

  const f = (key: keyof PowerSystem) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  return (
    <div className="flex h-full">
      <div className="w-52 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">境界体系</span>
          <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {powerSystems.map(s => (
            <button key={s.id} onClick={() => selectItem(s)}
              className={clsx('w-full flex items-start gap-2 px-4 py-2.5 text-left transition-colors border-l-2',
                selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-800 truncate">{s.name}</div>
                <div className="text-xs text-gray-400">{SYSTEM_TYPE_META[s.system_type] ?? s.system_type}</div>
                <div className="text-xs text-amber-600">{s.levels?.length ?? 0} 个境界</div>
              </div>
            </button>
          ))}
          {powerSystems.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无境界体系</p>}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (
          <div className="max-w-3xl mx-auto p-6 space-y-3">
            <EditorHeader
              name={form.name ?? selected.name}
              subtitle={SYSTEM_TYPE_META[form.system_type ?? 'cultivation']}
              badge={<span className="text-xs px-2 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-200 font-medium">
                {(form.levels ?? []).length} 个境界层级
              </span>}
              onDelete={() => handleDelete(selected.id)}
              saving={saving} onSave={handleSave}
            />

            <Section title="体系基础" icon={<Zap size={12} />}>
              <div className="grid grid-cols-2 gap-3">
                <Field label="体系名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
                <Field label="修炼类型">
                  <ChipSelect value={form.system_type ?? 'cultivation'} onChange={f('system_type')}
                    options={Object.entries(SYSTEM_TYPE_META).map(([k, v]) => ({ value: k, label: v }))} />
                </Field>
              </div>
              <Field label="体系简介"><TextArea value={form.description ?? ''} onChange={f('description')} rows={2} /></Field>
            </Section>

            <Section title="修炼规则" icon={<ChevronRight size={12} />}>
              <Field label="修炼方式"><TextArea value={form.cultivation_method ?? ''} onChange={f('cultivation_method')} rows={2} placeholder="如何修炼？靠什么提升？" /></Field>
              <Field label="突破条件"><TextArea value={form.breakthrough_condition ?? ''} onChange={f('breakthrough_condition')} rows={2} placeholder="通用的境界突破条件" /></Field>
              <Field label="特殊规则"><TextArea value={form.special_rules ?? ''} onChange={f('special_rules')} rows={2} placeholder="天才/废柴判定、禁忌、特殊法则等" /></Field>
            </Section>

            {/* 境界列表 */}
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm font-semibold text-gray-700">境界层级（从低到高）</div>
                <span className="text-xs text-amber-600 font-medium">{(form.levels ?? []).length} 个境界</span>
              </div>
              <div className="space-y-3 mb-4">
                {(form.levels ?? []).map((lv, idx) => (
                  <div key={idx} className="flex gap-3 p-4 bg-amber-50 rounded-xl border border-amber-100">
                    {/* 左侧：rank + 竖线 */}
                    <div className="flex flex-col items-center shrink-0">
                      <span className="w-7 h-7 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center font-bold">{lv.rank}</span>
                      {idx < (form.levels?.length ?? 0) - 1 && <div className="w-0.5 flex-1 bg-amber-200 mt-1.5 mb-0.5" />}
                    </div>
                    {/* 右侧：字段 */}
                    <div className="flex-1 space-y-2 min-w-0">
                      {/* 境界名 + 细分星级 + 章节 */}
                      <div className="flex items-center gap-2">
                        <input value={lv.name} onChange={e => updateLevel(idx, 'name', e.target.value)}
                          className="flex-1 font-semibold text-sm border-0 bg-transparent focus:outline-none text-gray-900 p-0 min-w-0"
                          placeholder="境界名称（如：斗者）" />
                        <div className="flex items-center gap-1 shrink-0">
                          <input type="number" min={1} max={99}
                            value={lv.sub_level_count ?? 9}
                            onChange={e => updateSubLevelCount(idx, e.target.value)}
                            className="w-10 text-xs text-amber-700 border-0 bg-amber-100 rounded px-1.5 py-0.5 text-center focus:outline-none focus:ring-1 focus:ring-amber-400" />
                          <span className="text-xs text-amber-600">星</span>
                        </div>
                        <button onClick={() => removeLevel(idx)} className="text-gray-300 hover:text-red-400 shrink-0 ml-1"><Trash2 size={13} /></button>
                      </div>
                      {/* 描述 */}
                      <textarea value={stringFromLoose(lv.description)} onChange={e => updateLevel(idx, 'description', e.target.value)}
                        rows={1} placeholder="境界描述（身体变化、修炼特征）"
                        className="w-full text-xs text-gray-500 border-0 bg-transparent focus:outline-none resize-none p-0 leading-relaxed" />
                      {/* 突破条件 */}
                      <input value={stringFromLoose(lv.requirements)} onChange={e => updateLevel(idx, 'requirements', e.target.value)}
                        className="w-full text-xs text-gray-500 border-0 bg-transparent focus:outline-none p-0"
                        placeholder="⬆ 突破至此境界的条件（如：气旋凝聚、能量液化）" />
                      {/* 章节区间 */}
                      <input value={stringFromLoose(lv.approximate_chapter)} onChange={e => updateLevel(idx, 'approximate_chapter', e.target.value)}
                        className="w-full text-xs text-gray-400 border-0 bg-transparent focus:outline-none p-0"
                        placeholder="📖 对应故事章节区间（如：第1-50章）" />
                      {/* 解锁能力 chips */}
                      <div className="pt-1">
                        <div className="flex flex-wrap gap-1 mb-1.5">
                          {(lv.abilities ?? []).map((ab: unknown, aIdx: number) => {
                            const label = stringFromLoose(ab)
                            if (!label) return null
                            return (
                              <span key={aIdx} className="flex items-center gap-1 text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full border border-amber-200">
                                {label}
                                <button onClick={() => removeAbility(idx, aIdx)} className="text-amber-400 hover:text-amber-700 text-xs leading-none">×</button>
                              </span>
                            )
                          })}
                          {(lv.abilities ?? []).length === 0 && (
                            <span className="text-xs text-amber-400 italic">暂无特殊能力解锁</span>
                          )}
                        </div>
                        <div className="flex gap-1">
                          <input value={abilityInputs[idx] ?? ''} onChange={e => setAbilityInputs(p => ({ ...p, [idx]: e.target.value }))}
                            onKeyDown={e => e.key === 'Enter' && addAbility(idx)}
                            placeholder="+ 添加解锁能力（如：斗气化翼）"
                            className="flex-1 text-xs border border-amber-200 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                          <button onClick={() => addAbility(idx)}
                            className="text-xs px-2 py-1 bg-amber-200 text-amber-700 rounded-lg hover:bg-amber-300 transition-colors">添加</button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                {(form.levels ?? []).length === 0 && (
                  <p className="text-xs text-gray-400 text-center py-6">暂无境界，在下方输入名称添加</p>
                )}
              </div>
              <div className="flex gap-2">
                <input value={levelInput} onChange={e => setLevelInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addLevel()}
                  placeholder="输入境界名称后回车（如：斗者、斗师、大斗师…）"
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400" />
                <button onClick={addLevel} className="px-4 py-2 bg-amber-100 text-amber-600 rounded-lg text-sm hover:bg-amber-200 transition-colors font-medium">添加</button>
              </div>
            </div>

          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Zap size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">点击左上角 + 新建境界体系</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  功法技能 Tab
// ─────────────────────────────────────────────────────────

const SKILL_TYPE_META: Record<string, { label: string; color: string }> = {
  combat:    { label: '攻击', color: 'bg-red-100 text-red-700 border-red-200' },
  defense:   { label: '防御', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  movement:  { label: '身法', color: 'bg-cyan-100 text-cyan-700 border-cyan-200' },
  support:   { label: '辅助', color: 'bg-green-100 text-green-700 border-green-200' },
  bloodline: { label: '血脉', color: 'bg-purple-100 text-purple-700 border-purple-200' },
  special:   { label: '特殊', color: 'bg-amber-100 text-amber-700 border-amber-200' },
}

const GRADE_META: Record<string, { label: string; color: string }> = {
  mortal:   { label: '凡品',   color: 'text-gray-500' },
  earth:    { label: '地品',   color: 'text-green-600' },
  sky:      { label: '天品',   color: 'text-blue-600' },
  profound: { label: '玄品',   color: 'text-purple-600' },
  saint:    { label: '圣品',   color: 'text-amber-600' },
  divine:   { label: '神品',   color: 'text-rose-600' },
  supreme:  { label: '无上',   color: 'text-red-700 font-bold' },
}

function SkillsTab({ projectId }: { projectId: string }) {
  const { skills, setSkills, upsertSkill, removeSkill } = useAppStore()
  const [selected, setSelected] = useState<Skill | null>(null)
  const [form, setForm] = useState<Partial<Skill>>({})
  const [saving, setSaving] = useState(false)
  const [searchQ, setSearchQ]         = useState('')
  const [filterType, setFilterType]   = useState('')
  const [filterGrade, setFilterGrade] = useState('')

  useEffect(() => {
    skillsApi.list(projectId).then(r => {
      setSkills(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
  }, [projectId])

  const selectItem = (s: Skill) => { setSelected(s); setForm({ ...s }) }

  const handleCreate = async () => {
    const res = await skillsApi.create(projectId, { name: '新功法', skill_type: 'combat', grade: 'earth' })
    upsertSkill(res.data); selectItem(res.data)
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const res = await skillsApi.update(projectId, selected.id, form)
      upsertSkill(res.data); setSelected(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    await skillsApi.delete(projectId, id)
    removeSkill(id)
    const rest = skills.filter(s => s.id !== id)
    if (rest.length > 0) selectItem(rest[0]); else { setSelected(null); setForm({}) }
    toast.success('已删除')
  }

  const f = (key: keyof Skill) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return skills.filter(s => {
      if (q && !s.name.toLowerCase().includes(q) && !(s.source ?? '').toLowerCase().includes(q)) return false
      if (filterType && s.skill_type !== filterType) return false
      if (filterGrade && s.grade !== filterGrade) return false
      return true
    })
  }, [skills, searchQ, filterType, filterGrade])

  const hasFilter = searchQ.trim() !== '' || filterType !== '' || filterGrade !== ''

  return (
    <div className="flex h-full">
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">功法技能</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{hasFilter ? `${filtered.length}/` : ''}{skills.length}</span>
            <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
          </div>
        </div>
        {/* 搜索 */}
        <div className="px-3 pt-2.5 pb-1.5 shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input value={searchQ} onChange={e => setSearchQ(e.target.value)} placeholder="搜索名称、来源…"
              className="w-full pl-7 pr-6 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:bg-white transition-colors" />
            {searchQ && <button onClick={() => setSearchQ('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>}
          </div>
        </div>
        {/* 类型筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <p className="text-[9px] text-gray-400 mb-1 uppercase tracking-wide">类型</p>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setFilterType('')}
              className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                filterType === '' ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
              全部
            </button>
            {Object.entries(SKILL_TYPE_META).map(([k, v]) => (
              <button key={k} onClick={() => setFilterType(filterType === k ? '' : k)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  filterType === k ? v.color : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
        {/* 品阶筛选 */}
        <div className="px-3 pb-2 shrink-0">
          <p className="text-[9px] text-gray-400 mb-1 uppercase tracking-wide">品阶</p>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setFilterGrade('')}
              className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                filterGrade === '' ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
              全部
            </button>
            {Object.entries(GRADE_META).map(([k, v]) => (
              <button key={k} onClick={() => setFilterGrade(filterGrade === k ? '' : k)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  filterGrade === k ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
        {/* 列表 */}
        <div className="flex-1 overflow-auto border-t border-gray-100">
          {filtered.length > 0 ? filtered.map(s => {
            const tm = SKILL_TYPE_META[s.skill_type]
            const gm = GRADE_META[s.grade]
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <div className="min-w-0 w-full">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-medium text-gray-800 truncate">{s.name}</span>
                    <span className={clsx('text-[10px] shrink-0 font-medium', gm?.color)}>{gm?.label}</span>
                  </div>
                  <div className="flex gap-1 mt-0.5 items-center">
                    <span className={clsx('text-[10px] px-1 py-0.5 rounded border', tm?.color)}>{tm?.label}</span>
                    {stringFromLoose(s.level_required) && (
                      <span className="text-[10px] text-gray-400 truncate">{stringFromLoose(s.level_required)}</span>
                    )}
                  </div>
                </div>
              </button>
            )
          }) : (
            <div className="py-10 text-center">
              {skills.length === 0
                ? <p className="text-xs text-gray-400 px-4">暂无功法，点击 + 创建</p>
                : <p className="text-xs text-gray-400 px-4">无匹配结果<br /><button onClick={() => { setSearchQ(''); setFilterType(''); setFilterGrade('') }} className="mt-1 text-amber-500 hover:underline">清除筛选</button></p>
              }
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (() => {
          const tm = SKILL_TYPE_META[form.skill_type ?? 'combat']
          const gm = GRADE_META[form.grade ?? 'earth']
          return (
            <div className="max-w-2xl mx-auto p-6 space-y-3">
              <EditorHeader
                name={form.name ?? selected.name}
                badge={<>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full border font-medium', tm?.color)}>{tm?.label}</span>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full border border-gray-200 font-medium', gm?.color)}>{gm?.label}</span>
                </>}
                onDelete={() => handleDelete(selected.id)}
                saving={saving} onSave={handleSave}
              />

              <Section title="基本信息" icon={<Sword size={12} />}>
                <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
                <Field label="类型">
                  <ChipSelect value={form.skill_type ?? 'combat'} onChange={f('skill_type')}
                    options={Object.entries(SKILL_TYPE_META).map(([k, v]) => ({ value: k, label: v.label, color: v.color }))} />
                </Field>
                <Field label="品阶">
                  <ChipSelect value={form.grade ?? 'earth'} onChange={f('grade')}
                    options={Object.entries(GRADE_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="来源"><TextInput value={form.source ?? ''} onChange={f('source')} placeholder="如：上古秘典" /></Field>
                  <Field label="修炼境界要求"><TextInput value={form.level_required ?? ''} onChange={f('level_required')} placeholder="如：斗者三星以上" /></Field>
                </div>
                <Field label="首次登场章节">
                  <input type="number" value={form.first_appearance_chapter ?? ''}
                    onChange={e => setForm(p => ({ ...p, first_appearance_chapter: Number(e.target.value) || undefined }))}
                    placeholder="章节数"
                    className="w-32 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
              </Section>

              <Section title="功法描述" icon={<ChevronRight size={12} />}>
                <Field label="功法 / 技能描述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
                <Field label="前置条件"><TextArea value={form.prerequisites ?? ''} onChange={f('prerequisites')} rows={2} placeholder="其他前置条件" /></Field>
              </Section>

              <Section title="战斗效果" icon={<Zap size={12} />} accent="bg-blue-50/60">
                <Field label="使用效果"><TextArea value={form.effects ?? ''} onChange={f('effects')} rows={3} /></Field>
                <Field label="限制与副作用"><TextArea value={form.limitations ?? ''} onChange={f('limitations')} rows={2} placeholder="消耗、反噬、使用限制" /></Field>
              </Section>
            </div>
          )
        })() : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Sword size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">点击左上角 + 新建功法技能</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  道具法宝 Tab
// ─────────────────────────────────────────────────────────

const ITEM_TYPE_META: Record<string, { label: string; icon: string }> = {
  weapon:   { label: '武器', icon: '⚔️' },
  armor:    { label: '防具', icon: '🛡️' },
  pill:     { label: '丹药', icon: '💊' },
  artifact: { label: '法宝', icon: '✨' },
  material: { label: '材料', icon: '💎' },
  scroll:   { label: '典籍', icon: '📜' },
  beast:    { label: '神兽', icon: '🐉' },
  other:    { label: '其他', icon: '📦' },
}

const RARITY_META: Record<string, { label: string; color: string }> = {
  common:    { label: '普通', color: 'text-gray-500' },
  uncommon:  { label: '精品', color: 'text-green-600' },
  rare:      { label: '稀有', color: 'text-blue-600' },
  epic:      { label: '极品', color: 'text-purple-600' },
  legendary: { label: '传说', color: 'text-amber-500' },
  mythic:    { label: '神话', color: 'text-rose-500' },
  unique:    { label: '唯一', color: 'text-red-700 font-bold' },
}

const ITEM_STATUS_META: Record<string, { label: string; color: string }> = {
  intact:    { label: '完好', color: 'text-green-600' },
  damaged:   { label: '受损', color: 'text-amber-500' },
  destroyed: { label: '已毁', color: 'text-red-600' },
  lost:      { label: '遗失', color: 'text-gray-500' },
  unknown:   { label: '不明', color: 'text-gray-400' },
}

function ItemsTab({ projectId }: { projectId: string }) {
  const { items, setItems, upsertItem, removeItem } = useAppStore()
  const [selected, setSelected] = useState<Item | null>(null)
  const [form, setForm] = useState<Partial<Item>>({})
  const [saving, setSaving] = useState(false)
  const [searchQ, setSearchQ]           = useState('')
  const [filterType, setFilterType]     = useState('')
  const [filterRarity, setFilterRarity] = useState('')

  useEffect(() => {
    itemsApi.list(projectId).then(r => {
      setItems(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
  }, [projectId])

  const selectItem = (s: Item) => { setSelected(s); setForm({ ...s }) }

  const handleCreate = async () => {
    const res = await itemsApi.create(projectId, { name: '新道具', item_type: 'artifact', rarity: 'rare', status: 'intact' })
    upsertItem(res.data); selectItem(res.data)
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const res = await itemsApi.update(projectId, selected.id, form)
      upsertItem(res.data); setSelected(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    await itemsApi.delete(projectId, id)
    removeItem(id)
    const rest = items.filter(s => s.id !== id)
    if (rest.length > 0) selectItem(rest[0]); else { setSelected(null); setForm({}) }
    toast.success('已删除')
  }

  const f = (key: keyof Item) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return items.filter(s => {
      if (q && !s.name.toLowerCase().includes(q) && !(s.origin ?? '').toLowerCase().includes(q)) return false
      if (filterType && s.item_type !== filterType) return false
      if (filterRarity && s.rarity !== filterRarity) return false
      return true
    })
  }, [items, searchQ, filterType, filterRarity])

  const hasFilter = searchQ.trim() !== '' || filterType !== '' || filterRarity !== ''

  return (
    <div className="flex h-full">
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">道具法宝</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{hasFilter ? `${filtered.length}/` : ''}{items.length}</span>
            <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
          </div>
        </div>
        {/* 搜索 */}
        <div className="px-3 pt-2.5 pb-1.5 shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input value={searchQ} onChange={e => setSearchQ(e.target.value)} placeholder="搜索名称、来历…"
              className="w-full pl-7 pr-6 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:bg-white transition-colors" />
            {searchQ && <button onClick={() => setSearchQ('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>}
          </div>
        </div>
        {/* 类型筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <p className="text-[9px] text-gray-400 mb-1 uppercase tracking-wide">类型</p>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setFilterType('')}
              className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                filterType === '' ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
              全部
            </button>
            {Object.entries(ITEM_TYPE_META).map(([k, v]) => (
              <button key={k} onClick={() => setFilterType(filterType === k ? '' : k)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  filterType === k ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {v.icon} {v.label}
              </button>
            ))}
          </div>
        </div>
        {/* 稀有度筛选 */}
        <div className="px-3 pb-2 shrink-0">
          <p className="text-[9px] text-gray-400 mb-1 uppercase tracking-wide">稀有度</p>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setFilterRarity('')}
              className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                filterRarity === '' ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
              全部
            </button>
            {Object.entries(RARITY_META).map(([k, v]) => (
              <button key={k} onClick={() => setFilterRarity(filterRarity === k ? '' : k)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  filterRarity === k ? 'bg-gray-700 text-white border-gray-700' : `bg-gray-50 border-gray-200 hover:border-gray-400 ${v.color}`)}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
        {/* 列表 */}
        <div className="flex-1 overflow-auto border-t border-gray-100">
          {filtered.length > 0 ? filtered.map(s => {
            const tm = ITEM_TYPE_META[s.item_type]
            const rm = RARITY_META[s.rarity]
            const sm = ITEM_STATUS_META[s.status ?? 'intact']
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <span className="text-base leading-none mt-0.5 shrink-0">{tm?.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-medium text-gray-800 truncate">{s.name}</span>
                    <span className={clsx('text-[10px] shrink-0 font-medium', rm?.color)}>{rm?.label}</span>
                  </div>
                  <div className="flex gap-1 items-center mt-0.5">
                    <span className="text-[10px] text-gray-400">{tm?.label}</span>
                    {sm && s.status !== 'intact' && (
                      <><span className="text-[10px] text-gray-300">·</span>
                      <span className={clsx('text-[10px]', sm.color)}>{sm.label}</span></>
                    )}
                  </div>
                </div>
              </button>
            )
          }) : (
            <div className="py-10 text-center">
              {items.length === 0
                ? <p className="text-xs text-gray-400 px-4">暂无道具，点击 + 创建</p>
                : <p className="text-xs text-gray-400 px-4">无匹配结果<br /><button onClick={() => { setSearchQ(''); setFilterType(''); setFilterRarity('') }} className="mt-1 text-amber-500 hover:underline">清除筛选</button></p>
              }
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (() => {
          const tm = ITEM_TYPE_META[form.item_type ?? 'artifact']
          const rm = RARITY_META[form.rarity ?? 'rare']
          return (
            <div className="max-w-2xl mx-auto p-6 space-y-3">
              <EditorHeader
                name={form.name ?? selected.name}
                badge={<>
                  <span className="text-base">{tm?.icon}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full border border-gray-200 text-gray-600 font-medium">{tm?.label}</span>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full border border-gray-200 font-medium', rm?.color)}>{rm?.label}</span>
                </>}
                onDelete={() => handleDelete(selected.id)}
                saving={saving} onSave={handleSave}
              />

              <Section title="分类属性" icon={<Package size={12} />}>
                <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
                <Field label="类型">
                  <ChipSelect value={form.item_type ?? 'artifact'} onChange={f('item_type')}
                    options={Object.entries(ITEM_TYPE_META).map(([k, v]) => ({ value: k, label: `${v.icon} ${v.label}` }))} />
                </Field>
                <Field label="稀有度">
                  <ChipSelect value={form.rarity ?? 'rare'} onChange={f('rarity')}
                    options={Object.entries(RARITY_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <Field label="状态">
                  <ChipSelect value={form.status ?? 'intact'} onChange={f('status')}
                    options={Object.entries(ITEM_STATUS_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <Field label="首次登场章节">
                  <input type="number" value={form.first_appearance_chapter ?? ''}
                    onChange={e => setForm(p => ({ ...p, first_appearance_chapter: Number(e.target.value) || undefined }))}
                    placeholder="章节数"
                    className="w-32 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
              </Section>

              <Section title="道具详情" icon={<ChevronRight size={12} />}>
                <Field label="道具描述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
                <Field label="来历"><TextArea value={form.origin ?? ''} onChange={f('origin')} rows={2} placeholder="如何诞生 / 从何而来" /></Field>
              </Section>

              <Section title="能力与限制" icon={<Zap size={12} />} accent="bg-emerald-50/60">
                <Field label="能力效果"><TextArea value={form.effects ?? ''} onChange={f('effects')} rows={3} /></Field>
                <Field label="使用限制"><TextArea value={form.limitations ?? ''} onChange={f('limitations')} rows={2} placeholder="消耗、代价、使用条件" /></Field>
              </Section>

              <Section title="剧情价值" icon={<GitBranch size={12} />} accent="bg-amber-50/60">
                <Field label="在故事中的意义"><TextArea value={form.story_significance ?? ''} onChange={f('story_significance')} rows={3} placeholder="这件道具对剧情的作用 / 象征意义" /></Field>
              </Section>
            </div>
          )
        })() : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Package size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">点击左上角 + 新建道具法宝</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  势力 Tab
// ─────────────────────────────────────────────────────────

const FACTION_TYPE_META: Record<string, { label: string; icon: string }> = {
  sect:     { label: '宗门', icon: '🏯' },
  kingdom:  { label: '国家', icon: '👑' },
  family:   { label: '家族', icon: '🏠' },
  guild:    { label: '商会', icon: '💰' },
  evil:     { label: '魔道', icon: '💀' },
  race:     { label: '种族', icon: '🌐' },
  other:    { label: '其他', icon: '⚙️' },
}

const ALIGNMENT_META: Record<string, { label: string; color: string }> = {
  protagonist: { label: '主角阵营', color: 'bg-green-100 text-green-700 border-green-200' },
  neutral:     { label: '中立',     color: 'bg-gray-100 text-gray-700 border-gray-200' },
  antagonist:  { label: '反派阵营', color: 'bg-red-100 text-red-700 border-red-200' },
  unknown:     { label: '立场不明', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
}

// 势力在故事中的活跃阶段（存 extra.active_period）
const ACTIVE_PERIOD_META: Record<string, { label: string; color: string }> = {
  '':     { label: '未设置',  color: 'text-gray-300' },
  early:  { label: '前期',    color: 'text-emerald-600' },
  mid:    { label: '中期',    color: 'text-blue-600' },
  late:   { label: '后期',    color: 'text-purple-600' },
  full:   { label: '贯穿全书', color: 'text-amber-600' },
}

function FactionsTab({ projectId }: { projectId: string }) {
  const { factions, setFactions, upsertFaction, removeFaction } = useAppStore()
  const [selected, setSelected] = useState<Faction | null>(null)
  const [form, setForm] = useState<Partial<Faction>>({})
  const [saving, setSaving] = useState(false)
  const [searchQ, setSearchQ]               = useState('')
  const [filterAlignment, setFilterAlignment] = useState('')

  useEffect(() => {
    factionsApi.list(projectId).then(r => {
      setFactions(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
  }, [projectId])

  const selectItem = (s: Faction) => { setSelected(s); setForm({ ...s }) }

  const handleCreate = async () => {
    const res = await factionsApi.create(projectId, { name: '新势力', faction_type: 'sect', alignment: 'neutral' })
    upsertFaction(res.data); selectItem(res.data)
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const res = await factionsApi.update(projectId, selected.id, form)
      upsertFaction(res.data); setSelected(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    await factionsApi.delete(projectId, id)
    removeFaction(id)
    const rest = factions.filter(s => s.id !== id)
    if (rest.length > 0) selectItem(rest[0]); else { setSelected(null); setForm({}) }
    toast.success('已删除')
  }

  const f = (key: keyof Faction) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return factions.filter(s => {
      if (q && !s.name.toLowerCase().includes(q) && !(s.description ?? '').toLowerCase().includes(q)) return false
      if (filterAlignment && s.alignment !== filterAlignment) return false
      return true
    })
  }, [factions, searchQ, filterAlignment])

  const hasFilter = searchQ.trim() !== '' || filterAlignment !== ''

  return (
    <div className="flex h-full">
      {/* 左栏 */}
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">势力组织</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{hasFilter ? `${filtered.length}/` : ''}{factions.length}</span>
            <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
          </div>
        </div>
        {/* 搜索 */}
        <div className="px-3 pt-2.5 pb-1.5 shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input value={searchQ} onChange={e => setSearchQ(e.target.value)} placeholder="搜索势力名称…"
              className="w-full pl-7 pr-6 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:bg-white transition-colors" />
            {searchQ && <button onClick={() => setSearchQ('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>}
          </div>
        </div>
        {/* 阵营筛选 */}
        <div className="px-3 pb-2 shrink-0">
          <p className="text-[9px] text-gray-400 mb-1 uppercase tracking-wide">阵营</p>
          <div className="flex flex-wrap gap-1">
            <button onClick={() => setFilterAlignment('')}
              className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                filterAlignment === '' ? 'bg-gray-700 text-white border-gray-700' : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
              全部
            </button>
            {Object.entries(ALIGNMENT_META).map(([k, v]) => (
              <button key={k} onClick={() => setFilterAlignment(filterAlignment === k ? '' : k)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  filterAlignment === k ? v.color : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
        {/* 列表 */}
        <div className="flex-1 overflow-auto border-t border-gray-100">
          {filtered.length > 0 ? filtered.map(s => {
            const tm = FACTION_TYPE_META[s.faction_type]
            const am = ALIGNMENT_META[s.alignment]
            const activePeriod = s.extra?.active_period as string ?? ''
            const pm = ACTIVE_PERIOD_META[activePeriod] ?? ACTIVE_PERIOD_META['']
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-2 px-3 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <span className="text-base leading-none mt-0.5 shrink-0">{tm?.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-gray-800 truncate">{s.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                    <span className={clsx('text-[10px] px-1 py-0.5 rounded border', am?.color)}>{am?.label}</span>
                    {activePeriod && <span className={clsx('text-[10px] font-medium', pm.color)}>{pm.label}</span>}
                  </div>
                </div>
              </button>
            )
          }) : (
            <div className="py-10 text-center">
              {factions.length === 0
                ? <p className="text-xs text-gray-400 px-4">暂无势力，点击 + 创建</p>
                : <p className="text-xs text-gray-400 px-4">无匹配结果<br /><button onClick={() => { setSearchQ(''); setFilterAlignment('') }} className="mt-1 text-amber-500 hover:underline">清除筛选</button></p>
              }
            </div>
          )}
        </div>
      </div>

      {/* 右栏 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (() => {
          const tm = FACTION_TYPE_META[form.faction_type ?? 'sect']
          const am = ALIGNMENT_META[form.alignment ?? 'neutral']
          const activePeriod = (form.extra?.active_period as string) ?? ''
          const pm = ACTIVE_PERIOD_META[activePeriod] ?? ACTIVE_PERIOD_META['']
          return (
            <div className="max-w-2xl mx-auto p-6 space-y-3">
              <EditorHeader
                name={form.name ?? selected.name}
                badge={<>
                  <span className="text-base">{tm?.icon}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full border border-gray-200 text-gray-600 font-medium">{tm?.label}</span>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full border font-medium', am?.color)}>{am?.label}</span>
                  {activePeriod && (
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full border border-gray-200 font-medium', pm.color)}>{pm.label}</span>
                  )}
                </>}
                onDelete={() => handleDelete(selected.id)}
                saving={saving} onSave={handleSave}
              />

              <Section title="基本信息" icon={<Shield size={12} />}>
                <Field label="势力名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
                <Field label="类型">
                  <ChipSelect value={form.faction_type ?? 'sect'} onChange={f('faction_type')}
                    options={Object.entries(FACTION_TYPE_META).map(([k, v]) => ({ value: k, label: v.label, icon: v.icon }))} />
                </Field>
                <Field label="阵营立场">
                  <ChipSelect value={form.alignment ?? 'neutral'} onChange={f('alignment')}
                    options={Object.entries(ALIGNMENT_META).map(([k, v]) => ({ value: k, label: v.label, color: v.color }))} />
                </Field>
                <Field label="活跃阶段">
                  <ChipSelect
                    value={activePeriod}
                    onChange={v => setForm(p => ({ ...p, extra: { ...(p.extra ?? {}), active_period: v } }))}
                    options={Object.entries(ACTIVE_PERIOD_META).filter(([k]) => k !== '').map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="实力级别"><TextInput value={form.strength_level ?? ''} onChange={f('strength_level')} placeholder="如：顶级宗门" /></Field>
                  <Field label="成员规模"><TextInput value={form.member_count ?? ''} onChange={f('member_count')} placeholder="如：数万弟子" /></Field>
                </div>
              </Section>

              <Section title="描述与领地" icon={<ChevronRight size={12} />}>
                <Field label="势力简述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} placeholder="这个势力是什么？有什么特点？" /></Field>
                <Field label="领地 / 活动范围"><TextArea value={form.territory ?? ''} onChange={f('territory')} rows={2} placeholder="控制的地域或主要活动区域" /></Field>
              </Section>

              <Section title="目标与资源" icon={<Zap size={12} />} accent="bg-emerald-50/60">
                <Field label="目标图谋"><TextArea value={form.goals ?? ''} onChange={f('goals')} rows={2} placeholder="这个势力想要什么？" /></Field>
                <Field label="势力资源"><TextArea value={form.resources ?? ''} onChange={f('resources')} rows={2} placeholder="拥有哪些独特资源、底牌、人才" /></Field>
              </Section>

              <Section title="历史与秘密" icon={<GitBranch size={12} />} accent="bg-amber-50/60">
                <Field label="历史背景"><TextArea value={form.history ?? ''} onChange={f('history')} rows={3} placeholder="势力的起源与重要历史事件" /></Field>
                <Field label="内部秘密（作者视角）"><TextArea value={form.secrets ?? ''} onChange={f('secrets')} rows={2} placeholder="读者暂时不知道的隐藏信息" /></Field>
              </Section>
            </div>
          )
        })() : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Shield size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">点击左上角 + 新建势力</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  地点（Location）Tab — 空间连续性管理
//  sensory_signature 是核心字段：固定感官基准，写章时注入 prompt 防止 AI 漂移
// ─────────────────────────────────────────────────────────

const DANGER_LABELS: Record<string, string> = {
  safe: '安全',
  neutral: '中性',
  dangerous: '危险',
  forbidden: '禁区',
}

const DANGER_COLORS: Record<string, string> = {
  safe:      'bg-green-100 text-green-700',
  neutral:   'bg-gray-100 text-gray-600',
  dangerous: 'bg-amber-100 text-amber-700',
  forbidden: 'bg-red-100 text-red-700',
}

function LocationsTab({ projectId }: { projectId: string }) {
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', danger_level: 'neutral', sensory_signature: '', description: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await locationsApi.list(projectId)
      setLocations(res.data)
    } catch { toast.error('地点加载失败') }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.name.trim()) return
    try {
      await locationsApi.create(projectId, {
        name: form.name.trim(),
        danger_level: form.danger_level as Location['danger_level'],
        sensory_signature: form.sensory_signature.trim() || undefined,
        description: form.description.trim() || undefined,
      })
      setForm({ name: '', danger_level: 'neutral', sensory_signature: '', description: '' })
      setCreating(false)
      await load()
    } catch { toast.error('创建失败') }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    try {
      await locationsApi.delete(projectId, id)
      setLocations(prev => prev.filter(l => l.id !== id))
    } catch { toast.error('删除失败') }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 shrink-0">
        <span className="text-xs text-gray-400">共 {locations.length} 个地点 · 感官基准写章时自动注入</span>
        <button onClick={() => setCreating(c => !c)} className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700">
          <Plus size={12} /> 新增地点
        </button>
      </div>

      {creating && (
        <div className="px-4 py-3 border-b border-sky-100 bg-sky-50 shrink-0 space-y-2">
          <div className="flex gap-2">
            <input className="flex-1 border rounded px-2 py-1 text-sm" placeholder="地点名称*" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <select className="border rounded px-2 py-1 text-sm" value={form.danger_level} onChange={e => setForm(f => ({ ...f, danger_level: e.target.value }))}>
              {Object.entries(DANGER_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <textarea className="w-full border rounded px-2 py-1 text-sm resize-none" rows={2} placeholder="感官基准（1-3句）：如 古朴木质气息，烛光昏黄，偶有翻页声" value={form.sensory_signature} onChange={e => setForm(f => ({ ...f, sensory_signature: e.target.value }))} />
          <textarea className="w-full border rounded px-2 py-1 text-sm resize-none" rows={2} placeholder="地点描述（可选）" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <div className="flex gap-2 justify-end">
            <button onClick={() => setCreating(false)} className="px-3 py-1 rounded text-xs text-gray-600 hover:bg-gray-100">取消</button>
            <button onClick={handleCreate} className="px-3 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700">保存</button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
        {loading && <div className="text-center text-gray-400 text-sm py-8">加载中…</div>}
        {!loading && locations.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">
            <MapPin size={32} className="mx-auto mb-2 opacity-40" />
            暂无地点，Bootstrap 生成后自动填充或手动添加
          </div>
        )}
        {locations.map(loc => (
          <div key={loc.id} className="border border-gray-200 rounded-lg bg-white">
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50" onClick={() => setExpanded(e => e === loc.id ? null : loc.id)}>
              <MapPin size={14} className="text-sky-500 shrink-0" />
              <span className="font-medium text-sm flex-1">{loc.name}</span>
              {loc.danger_level && (
                <span className={clsx('px-1.5 py-0.5 rounded text-xs', DANGER_COLORS[loc.danger_level] ?? 'bg-gray-100 text-gray-600')}>
                  {DANGER_LABELS[loc.danger_level] ?? loc.danger_level}
                </span>
              )}
              <button onClick={e => { e.stopPropagation(); handleDelete(loc.id) }} className="text-gray-300 hover:text-red-500 transition-colors ml-1"><Trash2 size={13} /></button>
              <ChevronRight size={13} className={clsx('text-gray-300 transition-transform', expanded === loc.id && 'rotate-90')} />
            </div>
            {expanded === loc.id && (
              <div className="px-3 pb-3 pt-1 border-t border-gray-100 space-y-1.5 text-xs text-gray-600">
                {loc.sensory_signature && (
                  <div><span className="font-medium text-amber-600">感官基准（写章硬约束）：</span><span className="italic">{loc.sensory_signature}</span></div>
                )}
                {loc.controller && <div><span className="font-medium">控制方：</span>{loc.controller}</div>}
                {loc.description && <div className="text-gray-500">{loc.description}</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  主页面
// ─────────────────────────────────────────────────────────

export default function WorldBuildingPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [activeTab, setActiveTab] = useState<SubTab>('storylines')

  if (!projectId) return null

  return (
    <div className="flex flex-col h-full">
      {/* 顶部子导航 */}
      <div className="flex items-center gap-1 px-4 py-2 bg-white border-b border-gray-100 shrink-0">
        {SUB_TABS.map(({ key, label, icon: Icon, color }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              activeTab === key
                ? 'bg-amber-50 text-amber-700 ring-1 ring-amber-200'
                : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
            )}
          >
            <Icon size={15} className={activeTab === key ? 'text-amber-600' : color} />
            {label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="flex-1 min-h-0">
        {activeTab === 'storylines' && <StoryLinesTab projectId={projectId} />}
        {activeTab === 'power'      && <PowerSystemTab projectId={projectId} />}
        {activeTab === 'skills'     && <SkillsTab projectId={projectId} />}
        {activeTab === 'items'      && <ItemsTab projectId={projectId} />}
        {activeTab === 'factions'   && <FactionsTab projectId={projectId} />}
        {activeTab === 'locations'  && <LocationsTab projectId={projectId} />}
      </div>
    </div>
  )
}
