/**
 * @file 世界观 — 境界体系 CRUD
 */
import { useEffect, useState } from 'react'
import { Plus, Trash2, ChevronRight, Zap } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { powerSystemsApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { PowerLevel, PowerSystem } from '../../../types'
import { ChipSelect, EditorHeader, Field, Section, TextArea, TextInput, stringFromLoose } from '../shared/components'

const SYSTEM_TYPE_META: Record<string, string> = {
  cultivation: '修炼/境界',
  magic: '魔法',
  ability: '异能',
  tech: '科技',
  hybrid: '混合体系',
}

export default function PowerSystemTab({ projectId }: { projectId: string }) {
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
