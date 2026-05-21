/**
 * @file 世界观 — 势力 CRUD + 境界关系图
 */
import React, { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, ChevronRight, Shield, Zap, GitBranch, Search, Network, List } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { factionsApi, powerSystemsApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { Faction } from '../../../types'
import PageSpinner from '../../../components/common/PageSpinner'
import { ChipSelect, EditorHeader, Field, Section, Select, TextArea, TextInput } from '../shared/components'

const FactionRealmDiagram = lazy(
  () => import('../../../components/WorldBuilding/FactionRealmDiagram'),
)

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

export default function FactionsTab({ projectId }: { projectId: string }) {
  const { factions, setFactions, upsertFaction, removeFaction, powerSystems, setPowerSystems } = useAppStore()
  const [selected, setSelected] = useState<Faction | null>(null)
  const [form, setForm] = useState<Partial<Faction>>({})
  const [saving, setSaving] = useState(false)
  const [searchQ, setSearchQ]               = useState('')
  const [filterAlignment, setFilterAlignment] = useState('')
  const [viewMode, setViewMode] = useState<'edit' | 'diagram'>('edit')

  useEffect(() => {
    factionsApi.list(projectId).then(r => {
      setFactions(r.data)
      if (r.data.length > 0) { setSelected(r.data[0]); setForm(r.data[0]) }
    })
    if (powerSystems.length === 0) {
      powerSystemsApi.list(projectId).then(r => setPowerSystems(r.data)).catch(() => {})
    }
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

  const parseNameList = (raw: string): string[] =>
    raw.split(/[,，、]/).map(s => s.trim()).filter(Boolean)

  const joinNameList = (arr: string[] | undefined): string =>
    (arr ?? []).join('、')

  if (viewMode === 'diagram') {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-white shrink-0">
          <div className="flex items-center gap-2">
            <Network size={14} className="text-amber-600" />
            <span className="text-sm font-semibold text-gray-700">势力 · 境界进阶关系图</span>
            <span className="text-xs text-gray-400">
              {factions.length} 势力 · {powerSystems[0]?.levels?.length ?? 0} 个境界层
            </span>
          </div>
          <button
            type="button"
            onClick={() => setViewMode('edit')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
          >
            <List size={12} /> 返回列表编辑
          </button>
        </div>
        <div className="flex-1 min-h-0">
          <Suspense fallback={<PageSpinner label="关系图加载中…" />}>
            <FactionRealmDiagram
              factions={factions}
              powerSystems={powerSystems}
              selectedId={selected?.id}
              onSelectFaction={f => { setSelected(f); setForm({ ...f }) }}
            />
          </Suspense>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* 左栏 */}
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">势力组织</span>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400">{hasFilter ? `${filtered.length}/` : ''}{factions.length}</span>
            <button
              type="button"
              title="境界进阶关系图"
              onClick={() => setViewMode('diagram')}
              className="text-gray-400 hover:text-amber-600 transition-colors"
            >
              <Network size={15} />
            </button>
            <button type="button" onClick={handleCreate} className="text-amber-500 hover:text-amber-600"><Plus size={16} /></button>
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
                  <Field label="实力级别"><TextInput value={form.strength_level ?? ''} onChange={f('strength_level')} placeholder="如：顶级宗门、含境界名" /></Field>
                  <Field label="成员规模"><TextInput value={form.member_count ?? ''} onChange={f('member_count')} placeholder="如：数万弟子" /></Field>
                </div>
                <Field label="最强战力"><TextInput value={form.top_power ?? ''} onChange={f('top_power')} placeholder="如：掌门·元婴后期（关系图纵轴匹配）" /></Field>
              </Section>

              <Section title="势力关系（关系图连线）" icon={<Network size={12} />} accent="bg-sky-50/60">
                <Field label="上级势力">
                  <Select
                    value={form.parent_faction_id ?? ''}
                    onChange={v => setForm(p => ({ ...p, parent_faction_id: v || undefined }))}
                    options={[
                      { value: '', label: '无（顶层势力）' },
                      ...factions
                        .filter(x => x.id !== selected.id)
                        .map(x => ({ value: x.id, label: x.name })),
                    ]}
                  />
                </Field>
                <Field label="盟友势力">
                  <TextInput
                    value={joinNameList(form.allies)}
                    onChange={v => setForm(p => ({ ...p, allies: parseNameList(v) }))}
                    placeholder="多个用顿号分隔，如：紫霞谷、玄武帝国"
                  />
                </Field>
                <Field label="敌对势力">
                  <TextInput
                    value={joinNameList(form.rivals)}
                    onChange={v => setForm(p => ({ ...p, rivals: parseNameList(v) }))}
                    placeholder="多个用顿号分隔"
                  />
                </Field>
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
