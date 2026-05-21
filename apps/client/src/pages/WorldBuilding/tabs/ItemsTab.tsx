/**
 * @file 世界观 — 道具法宝 CRUD
 */
import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, ChevronRight, Package, Search, Zap, GitBranch } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { itemsApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import type { Item } from '../../../types'
import { ChipSelect, EditorHeader, Field, Section, TextArea, TextInput } from '../shared/components'

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

export default function ItemsTab({ projectId }: { projectId: string }) {
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
