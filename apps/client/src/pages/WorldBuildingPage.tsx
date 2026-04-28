import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Trash2, ChevronRight, GitBranch, Zap, Sword, Package, Shield } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { storylinesApi, powerSystemsApi, skillsApi, itemsApi, factionsApi } from '../api/client'
import { useAppStore } from '../store'
import type { StoryLine, PowerSystem, Skill, Item, Faction } from '../types'

// ─────────────────────────────────────────────────────────
//  Sub-tab 配置
// ─────────────────────────────────────────────────────────

type SubTab = 'storylines' | 'power' | 'skills' | 'items' | 'factions'

const SUB_TABS: { key: SubTab; label: string; icon: React.ElementType; color: string }[] = [
  { key: 'storylines', label: '故事线', icon: GitBranch, color: 'text-purple-600' },
  { key: 'power',      label: '境界体系', icon: Zap,       color: 'text-amber-600' },
  { key: 'skills',     label: '功法技能', icon: Sword,     color: 'text-blue-600'  },
  { key: 'items',      label: '道具法宝', icon: Package,   color: 'text-emerald-600'},
  { key: 'factions',   label: '势力',    icon: Shield,    color: 'text-red-600'   },
]

// ─────────────────────────────────────────────────────────
//  通用工具
// ─────────────────────────────────────────────────────────

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
      className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
    >
      {saving ? '保存中...' : '保存'}
    </button>
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
          <div className="max-w-2xl mx-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">编辑故事线</h2>
              <button onClick={() => handleDelete(selected.id)} className="text-gray-400 hover:text-red-500 transition-colors">
                <Trash2 size={16} />
              </button>
            </div>
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="类型">
                  <Select value={form.line_type ?? 'sub'} onChange={f('line_type')}
                    options={Object.entries(LINE_TYPE_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <Field label="状态">
                  <Select value={form.status ?? 'planned'} onChange={f('status')}
                    options={Object.entries(STATUS_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Field label="起始章节">
                  <input type="number" value={form.start_chapter ?? ''} onChange={e => setForm(p => ({ ...p, start_chapter: Number(e.target.value) || undefined }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
                <Field label="预计结束章节">
                  <input type="number" value={form.end_chapter ?? ''} onChange={e => setForm(p => ({ ...p, end_chapter: Number(e.target.value) || undefined }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
              </div>
              <Field label="故事线简述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
              <Field label="核心矛盾"><TextArea value={form.core_conflict ?? ''} onChange={f('core_conflict')} rows={3} placeholder="这条线的核心冲突是什么？" /></Field>
              <Field label="解决方向"><TextArea value={form.resolution_direction ?? ''} onChange={f('resolution_direction')} rows={2} placeholder="预计如何收尾？" /></Field>
              <SaveBtn saving={saving} onClick={handleSave} />
            </div>
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
    const levels = [...(form.levels ?? []), { rank: (form.levels?.length ?? 0) + 1, name, description: '', requirements: '', abilities: [] }]
    setForm(p => ({ ...p, levels }))
    setLevelInput('')
  }

  const removeLevel = (idx: number) => {
    const levels = (form.levels ?? []).filter((_, i) => i !== idx).map((l, i) => ({ ...l, rank: i + 1 }))
    setForm(p => ({ ...p, levels }))
  }

  const updateLevel = (idx: number, key: string, val: string) => {
    const levels = (form.levels ?? []).map((l, i) => i === idx ? { ...l, [key]: val } : l)
    setForm(p => ({ ...p, levels }))
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
          <div className="max-w-3xl mx-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">编辑境界体系</h2>
              <button onClick={() => handleDelete(selected.id)} className="text-gray-400 hover:text-red-500 transition-colors"><Trash2 size={16} /></button>
            </div>

            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="体系名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
                <Field label="类型">
                  <Select value={form.system_type ?? 'cultivation'} onChange={f('system_type')}
                    options={Object.entries(SYSTEM_TYPE_META).map(([k, v]) => ({ value: k, label: v }))} />
                </Field>
              </div>
              <Field label="体系简介"><TextArea value={form.description ?? ''} onChange={f('description')} rows={2} /></Field>
              <Field label="修炼方式"><TextArea value={form.cultivation_method ?? ''} onChange={f('cultivation_method')} rows={2} placeholder="如何修炼？靠什么提升？" /></Field>
              <Field label="突破条件"><TextArea value={form.breakthrough_condition ?? ''} onChange={f('breakthrough_condition')} rows={2} placeholder="通用的境界突破条件" /></Field>
              <Field label="特殊规则"><TextArea value={form.special_rules ?? ''} onChange={f('special_rules')} rows={2} placeholder="天才/废柴判定、禁忌、特殊法则等" /></Field>
            </div>

            {/* 境界列表 */}
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
              <div className="text-sm font-semibold text-gray-700 mb-4">境界层级（从低到高）</div>
              <div className="space-y-3 mb-4">
                {(form.levels ?? []).map((lv, idx) => (
                  <div key={idx} className="flex gap-3 p-3 bg-amber-50 rounded-lg border border-amber-100">
                    <div className="flex flex-col items-center justify-start pt-1">
                      <span className="w-6 h-6 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center font-bold shrink-0">{lv.rank}</span>
                      {idx < (form.levels?.length ?? 0) - 1 && <div className="w-0.5 h-full bg-amber-200 mt-1" />}
                    </div>
                    <div className="flex-1 space-y-1.5 min-w-0">
                      <input value={lv.name} onChange={e => updateLevel(idx, 'name', e.target.value)}
                        className="w-full font-medium text-sm border-0 bg-transparent focus:outline-none text-gray-800 p-0"
                        placeholder="境界名称" />
                      <textarea value={lv.description ?? ''} onChange={e => updateLevel(idx, 'description', e.target.value)}
                        rows={1} placeholder="该境界的描述（可选）"
                        className="w-full text-xs text-gray-500 border-0 bg-transparent focus:outline-none resize-none p-0" />
                      <input value={lv.requirements ?? ''} onChange={e => updateLevel(idx, 'requirements', e.target.value)}
                        className="w-full text-xs text-gray-500 border-0 bg-transparent focus:outline-none p-0"
                        placeholder="突破到此境界的条件" />
                    </div>
                    <button onClick={() => removeLevel(idx)} className="text-gray-300 hover:text-red-400 shrink-0 self-start"><Trash2 size={14} /></button>
                  </div>
                ))}
                {(form.levels ?? []).length === 0 && (
                  <p className="text-xs text-gray-400 text-center py-4">暂无境界，在下方输入新增</p>
                )}
              </div>
              <div className="flex gap-2">
                <input value={levelInput} onChange={e => setLevelInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addLevel()}
                  placeholder="输入境界名称后回车添加（如：淬体境）"
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400" />
                <button onClick={addLevel} className="px-3 py-2 bg-amber-100 text-amber-600 rounded-lg text-sm hover:bg-amber-200 transition-colors">添加</button>
              </div>
            </div>

            <SaveBtn saving={saving} onClick={handleSave} />
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
  const [filterType, setFilterType] = useState<string>('')

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
  const filtered = filterType ? skills.filter(s => s.skill_type === filterType) : skills

  return (
    <div className="flex h-full">
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">功法技能</span>
          <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
        </div>
        {/* 类型筛选 */}
        <div className="px-3 py-2 border-b border-gray-100 flex flex-wrap gap-1">
          <button onClick={() => setFilterType('')} className={clsx('text-xs px-2 py-0.5 rounded-full border', !filterType ? 'bg-amber-100 text-amber-700 border-amber-200' : 'text-gray-400 border-gray-200')}>全部</button>
          {Object.entries(SKILL_TYPE_META).map(([k, v]) => (
            <button key={k} onClick={() => setFilterType(filterType === k ? '' : k)}
              className={clsx('text-xs px-2 py-0.5 rounded-full border', filterType === k ? v.color : 'text-gray-400 border-gray-200')}>
              {v.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto py-2">
          {filtered.map(s => {
            const tm = SKILL_TYPE_META[s.skill_type]
            const gm = GRADE_META[s.grade]
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-2 px-4 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <div className="min-w-0 w-full">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-sm font-medium text-gray-800 truncate">{s.name}</span>
                    <span className={clsx('text-xs shrink-0', gm?.color)}>{gm?.label}</span>
                  </div>
                  <div className="flex gap-1 mt-0.5">
                    <span className={clsx('text-xs px-1.5 py-0.5 rounded border', tm?.color)}>{tm?.label}</span>
                    {s.level_required && <span className="text-xs text-gray-400 truncate">{s.level_required}</span>}
                  </div>
                </div>
              </button>
            )
          })}
          {filtered.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无技能</p>}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (
          <div className="max-w-2xl mx-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">编辑功法技能</h2>
              <button onClick={() => handleDelete(selected.id)} className="text-gray-400 hover:text-red-500 transition-colors"><Trash2 size={16} /></button>
            </div>
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="类型">
                  <Select value={form.skill_type ?? 'combat'} onChange={f('skill_type')}
                    options={Object.entries(SKILL_TYPE_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <Field label="品阶">
                  <Select value={form.grade ?? 'earth'} onChange={f('grade')}
                    options={Object.entries(GRADE_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
              </div>
              <Field label="来源"><TextInput value={form.source ?? ''} onChange={f('source')} placeholder="如：上古秘典、师门传承" /></Field>
              <Field label="修炼要求（境界）"><TextInput value={form.level_required ?? ''} onChange={f('level_required')} placeholder="如：斗者三星以上" /></Field>
              <Field label="前置条件"><TextArea value={form.prerequisites ?? ''} onChange={f('prerequisites')} rows={2} placeholder="其他前置条件" /></Field>
              <Field label="功法/技能描述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
              <Field label="使用效果"><TextArea value={form.effects ?? ''} onChange={f('effects')} rows={3} /></Field>
              <Field label="限制与副作用"><TextArea value={form.limitations ?? ''} onChange={f('limitations')} rows={2} placeholder="消耗、反噬、使用限制" /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="首次登场章节">
                  <input type="number" value={form.first_appearance_chapter ?? ''}
                    onChange={e => setForm(p => ({ ...p, first_appearance_chapter: Number(e.target.value) || undefined }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
                </Field>
              </div>
              <SaveBtn saving={saving} onClick={handleSave} />
            </div>
          </div>
        ) : (
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

  return (
    <div className="flex h-full">
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">道具法宝</span>
          <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {items.map(s => {
            const tm = ITEM_TYPE_META[s.item_type]
            const rm = RARITY_META[s.rarity]
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-3 px-4 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <span className="text-xl leading-none mt-0.5 shrink-0">{tm?.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-800 truncate">{s.name}</div>
                  <div className="flex gap-1 items-center">
                    <span className={clsx('text-xs', rm?.color)}>{rm?.label}</span>
                    <span className="text-xs text-gray-300">·</span>
                    <span className="text-xs text-gray-400">{tm?.label}</span>
                  </div>
                </div>
              </button>
            )
          })}
          {items.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无道具</p>}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (
          <div className="max-w-2xl mx-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">编辑道具法宝</h2>
              <button onClick={() => handleDelete(selected.id)} className="text-gray-400 hover:text-red-500 transition-colors"><Trash2 size={16} /></button>
            </div>
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
              <div className="grid grid-cols-3 gap-3">
                <Field label="类型">
                  <Select value={form.item_type ?? 'artifact'} onChange={f('item_type')}
                    options={Object.entries(ITEM_TYPE_META).map(([k, v]) => ({ value: k, label: `${v.icon} ${v.label}` }))} />
                </Field>
                <Field label="稀有度">
                  <Select value={form.rarity ?? 'rare'} onChange={f('rarity')}
                    options={Object.entries(RARITY_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
                <Field label="状态">
                  <Select value={form.status ?? 'intact'} onChange={f('status')}
                    options={Object.entries(ITEM_STATUS_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
              </div>
              <Field label="道具描述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
              <Field label="来历"><TextArea value={form.origin ?? ''} onChange={f('origin')} rows={2} placeholder="如何诞生/从何而来" /></Field>
              <Field label="能力效果"><TextArea value={form.effects ?? ''} onChange={f('effects')} rows={3} /></Field>
              <Field label="使用限制"><TextArea value={form.limitations ?? ''} onChange={f('limitations')} rows={2} /></Field>
              <Field label="在故事中的意义"><TextArea value={form.story_significance ?? ''} onChange={f('story_significance')} rows={2} placeholder="这件道具对剧情的作用/象征意义" /></Field>
              <Field label="首次登场章节">
                <input type="number" value={form.first_appearance_chapter ?? ''}
                  onChange={e => setForm(p => ({ ...p, first_appearance_chapter: Number(e.target.value) || undefined }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
              </Field>
              <SaveBtn saving={saving} onClick={handleSave} />
            </div>
          </div>
        ) : (
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

function FactionsTab({ projectId }: { projectId: string }) {
  const { factions, setFactions, upsertFaction, removeFaction } = useAppStore()
  const [selected, setSelected] = useState<Faction | null>(null)
  const [form, setForm] = useState<Partial<Faction>>({})
  const [saving, setSaving] = useState(false)

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

  return (
    <div className="flex h-full">
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">势力组织</span>
          <button onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {factions.map(s => {
            const tm = FACTION_TYPE_META[s.faction_type]
            const am = ALIGNMENT_META[s.alignment]
            return (
              <button key={s.id} onClick={() => selectItem(s)}
                className={clsx('w-full flex items-start gap-3 px-4 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                <span className="text-xl leading-none mt-0.5 shrink-0">{tm?.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-800 truncate">{s.name}</div>
                  <span className={clsx('text-xs px-1.5 py-0.5 rounded border', am?.color)}>{am?.label}</span>
                </div>
              </button>
            )
          })}
          {factions.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无势力</p>}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected ? (
          <div className="max-w-2xl mx-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-gray-900">编辑势力</h2>
              <button onClick={() => handleDelete(selected.id)} className="text-gray-400 hover:text-red-500 transition-colors"><Trash2 size={16} /></button>
            </div>
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <Field label="名称"><TextInput value={form.name ?? ''} onChange={f('name')} /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="类型">
                  <Select value={form.faction_type ?? 'sect'} onChange={f('faction_type')}
                    options={Object.entries(FACTION_TYPE_META).map(([k, v]) => ({ value: k, label: `${v.icon} ${v.label}` }))} />
                </Field>
                <Field label="阵营">
                  <Select value={form.alignment ?? 'neutral'} onChange={f('alignment')}
                    options={Object.entries(ALIGNMENT_META).map(([k, v]) => ({ value: k, label: v.label }))} />
                </Field>
              </div>
              <Field label="势力描述"><TextArea value={form.description ?? ''} onChange={f('description')} rows={3} /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="实力级别"><TextInput value={form.strength_level ?? ''} onChange={f('strength_level')} placeholder="如：顶级宗门" /></Field>
                <Field label="成员规模"><TextInput value={form.member_count ?? ''} onChange={f('member_count')} placeholder="如：数万弟子" /></Field>
              </div>
              <Field label="领地/活动范围"><TextArea value={form.territory ?? ''} onChange={f('territory')} rows={2} /></Field>
              <Field label="目标图谋"><TextArea value={form.goals ?? ''} onChange={f('goals')} rows={2} /></Field>
              <Field label="势力资源"><TextArea value={form.resources ?? ''} onChange={f('resources')} rows={2} /></Field>
              <Field label="历史背景"><TextArea value={form.history ?? ''} onChange={f('history')} rows={3} /></Field>
              <Field label="内部秘密（作者视角）"><TextArea value={form.secrets ?? ''} onChange={f('secrets')} rows={2} placeholder="读者暂时不知道的隐藏信息" /></Field>
              <SaveBtn saving={saving} onClick={handleSave} />
            </div>
          </div>
        ) : (
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
      </div>
    </div>
  )
}
