/**
 * @file 世界观 — 功法技能 CRUD
 */
import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, ChevronRight, Sword, Search, Zap, GitBranch } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { skillsApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { Skill } from '../../../types'
import { ChipSelect, EditorHeader, Field, Section, TextArea, TextInput, stringFromLoose } from '../shared/components'

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

export default function SkillsTab({ projectId }: { projectId: string }) {
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
