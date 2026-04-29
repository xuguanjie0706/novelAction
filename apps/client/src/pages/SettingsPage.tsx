import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Trash2, Globe, Map, BookOpen, Landmark, Scale, Folder } from 'lucide-react'
import { projectsApi, settingsApi } from '../api/client'
import { useAppStore } from '../store'
import type { WorldSetting } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// ─────────────────────────────────────────────────────────
//  分类定义
// ─────────────────────────────────────────────────────────

type CategoryKey = 'all' | '世界背景' | '地理场景' | '历史传说' | '文化风俗' | '规则法则' | '其他'

const CATEGORIES: { key: CategoryKey; label: string; icon: React.ElementType; color: string }[] = [
  { key: 'all',    label: '全部',   icon: Folder,   color: 'text-gray-400'    },
  { key: '世界背景', label: '世界背景', icon: Globe,    color: 'text-blue-500'   },
  { key: '地理场景', label: '地理场景', icon: Map,      color: 'text-emerald-500' },
  { key: '历史传说', label: '历史传说', icon: BookOpen, color: 'text-amber-500'   },
  { key: '文化风俗', label: '文化风俗', icon: Landmark, color: 'text-purple-500'  },
  { key: '规则法则', label: '规则法则', icon: Scale,    color: 'text-rose-500'    },
  { key: '其他',   label: '其他',   icon: Folder,   color: 'text-gray-400'    },
]

const CATEGORY_KEYS = CATEGORIES.map(c => c.key).filter(k => k !== 'all') as Exclude<CategoryKey, 'all'>[]

const GEO_LOCATION_TYPES = ['城市/城镇', '宗门/门派', '王宫/皇城', '远古遗迹', '秘境/异空间', '山脉/荒野', '大陆/地区', '其他']
const GEO_ALIGNMENT_OPTIONS = ['无明确势力', '主角阵营', '反派阵营', '中立势力']

// ─────────────────────────────────────────────────────────
//  工具函数
// ─────────────────────────────────────────────────────────

function getCategory(s: WorldSetting): Exclude<CategoryKey, 'all'> {
  const cat = s.extra?.category as string | undefined
  if (cat && CATEGORY_KEYS.includes(cat as any)) return cat as any
  return '其他'
}

function getCategoryMeta(key: CategoryKey) {
  return CATEGORIES.find(c => c.key === key) ?? CATEGORIES[CATEGORIES.length - 1]
}

function isPremiseSetting(title: string, tags: string[]) {
  const t = title.trim()
  if (t === '作品立意') return true
  if (t.includes('立意') && t.includes('类型')) return true
  return tags.some(tag => tag.includes('立意') || tag.includes('主题'))
}

// ─────────────────────────────────────────────────────────
//  通用输入组件
// ─────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

function TInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400" />
  )
}

function TArea({ value, onChange, rows = 4, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
  return (
    <textarea value={value ?? ''} onChange={e => onChange(e.target.value)} rows={rows} placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none leading-relaxed" />
  )
}

function TSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select value={value ?? ''} onChange={e => onChange(e.target.value)}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400">
      <option value="">请选择...</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

// ─────────────────────────────────────────────────────────
//  地理场景结构化区块
// ─────────────────────────────────────────────────────────

function GeoStructuredFields({ extra, onChange }: {
  extra: Record<string, any>
  onChange: (key: string, val: string) => void
}) {
  return (
    <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100 space-y-3">
      <div className="text-xs font-semibold text-emerald-700 flex items-center gap-1.5">
        <Map size={13} /> 结构化地理信息
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="地点类型">
          <TSelect value={extra.location_type ?? ''} onChange={v => onChange('location_type', v)}
            options={GEO_LOCATION_TYPES} />
        </Field>
        <Field label="势力归属">
          <TSelect value={extra.geo_alignment ?? ''} onChange={v => onChange('geo_alignment', v)}
            options={GEO_ALIGNMENT_OPTIONS} />
        </Field>
      </div>
      <Field label="所属势力（具体名称）">
        <TInput value={extra.controlling_faction ?? ''} onChange={v => onChange('controlling_faction', v)}
          placeholder="如：云岚宗、加玛帝国皇室" />
      </Field>
      <Field label="核心资源 / 特产">
        <TInput value={extra.key_resources ?? ''} onChange={v => onChange('key_resources', v)}
          placeholder="如：斗气晶石矿、天材地宝聚集地" />
      </Field>
      <Field label="故事作用">
        <TInput value={extra.story_significance ?? ''} onChange={v => onChange('story_significance', v)}
          placeholder="如：主角成长地、终极决战场、伏笔揭示地" />
      </Field>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  设定卡详情
// ─────────────────────────────────────────────────────────

function SettingDetail({
  setting, projectId, onUpdate, onDelete, onPremiseSync,
}: {
  setting: WorldSetting
  projectId: string
  onUpdate: (s: WorldSetting) => void
  onDelete: (id: string) => void
  onPremiseSync?: (content: string) => Promise<void>
}) {
  const [form, setForm] = useState({
    title: setting.title,
    content: setting.content ?? '',
    tags: setting.tags,
    extra: { ...setting.extra },
  })
  const [saving, setSaving] = useState(false)
  const [tagInput, setTagInput] = useState('')

  useEffect(() => {
    setForm({ title: setting.title, content: setting.content ?? '', tags: setting.tags, extra: { ...setting.extra } })
  }, [setting.id])

  const save = async () => {
    setSaving(true)
    try {
      const res = await settingsApi.update(projectId, setting.id, form)
      onUpdate(res.data)
      if (isPremiseSetting(form.title, form.tags)) await onPremiseSync?.(form.content)
      toast.success('已保存')
    } catch { toast.error('保存失败') }
    finally { setSaving(false) }
  }

  const setExtra = (key: string, val: string) =>
    setForm(f => ({ ...f, extra: { ...f.extra, [key]: val } }))

  const addTag = () => {
    const t = tagInput.trim()
    if (!t || form.tags.includes(t)) return
    setForm(f => ({ ...f, tags: [...f.tags, t] }))
    setTagInput('')
  }
  const removeTag = (t: string) => setForm(f => ({ ...f, tags: f.tags.filter(x => x !== t) }))

  const category = (form.extra.category as Exclude<CategoryKey, 'all'>) ?? '其他'
  const catMeta = getCategoryMeta(category)
  const CatIcon = catMeta.icon

  const CONTENT_PLACEHOLDER: Record<string, string> = {
    '世界背景': '宏观世界背景、宇宙构成、天地法则...',
    '地理场景': '地形地貌、氛围描写、视觉细节、如何进入...',
    '历史传说': '详细记述历史事件或传说内容、相关人物...',
    '文化风俗': '民俗习惯、礼仪规范、节日、信仰体系...',
    '规则法则': '规则内容、适用范围、例外情况、违反后果...',
    '其他': '在这里记录详细的设定描述...',
  }

  return (
    <div className="space-y-4">
      {/* 标题行 */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <CatIcon size={16} className={catMeta.color} />
            <span className="text-xs font-medium text-gray-400">{catMeta.label}</span>
          </div>
          <button onClick={() => { if (confirm('确认删除这张设定卡？')) onDelete(setting.id) }}
            className="text-gray-300 hover:text-red-400 transition-colors p-1">
            <Trash2 size={14} />
          </button>
        </div>
        <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          className="w-full text-xl font-bold text-gray-900 border-none outline-none bg-transparent"
          placeholder="设定卡标题" />
      </div>

      {/* 分类选择 */}
      <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
        <div className="text-xs font-semibold text-gray-500 mb-2.5">分类</div>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.filter(c => c.key !== 'all').map(c => {
            const Icon = c.icon
            return (
              <button key={c.key} onClick={() => setExtra('category', c.key)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                  category === c.key
                    ? 'bg-amber-50 border-amber-300 text-amber-700'
                    : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                )}>
                <Icon size={12} className={category === c.key ? 'text-amber-500' : c.color} />
                {c.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 地理场景结构化字段 */}
      {category === '地理场景' && (
        <GeoStructuredFields extra={form.extra} onChange={setExtra} />
      )}

      {/* 内容 */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-2">
        <div className="text-xs font-semibold text-gray-500">
          {category === '地理场景' ? '场景描写 / 补充说明' : '详细描述'}
        </div>
        <TArea value={form.content} onChange={v => setForm(f => ({ ...f, content: v }))} rows={10}
          placeholder={CONTENT_PLACEHOLDER[category] ?? CONTENT_PLACEHOLDER['其他']} />
      </div>

      {/* 标签 */}
      <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
        <div className="text-xs font-semibold text-gray-500 mb-2">标签</div>
        <div className="flex flex-wrap gap-1.5 mb-3 min-h-[24px]">
          {form.tags.map(t => (
            <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full border border-amber-200">
              {t}
              <button onClick={() => removeTag(t)} className="text-amber-400 hover:text-amber-700">×</button>
            </span>
          ))}
          {form.tags.length === 0 && <span className="text-xs text-gray-300">暂无标签</span>}
        </div>
        <div className="flex gap-2">
          <input value={tagInput} onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addTag()}
            placeholder="输入标签后回车..."
            className="border border-gray-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400 w-36" />
          <button onClick={addTag} className="text-xs text-amber-600 hover:text-amber-700 font-medium">添加</button>
        </div>
      </div>

      <button onClick={save} disabled={saving}
        className="w-full py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm font-medium rounded-xl transition-colors">
        {saving ? '保存中...' : '保存修改'}
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  主页面
// ─────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { currentProject, setCurrentProject, settings, setSettings, upsertSetting, removeSetting } = useAppStore()
  const [selected, setSelected] = useState<WorldSetting | null>(null)
  const [activeCat, setActiveCat] = useState<CategoryKey>('all')
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newCat, setNewCat] = useState<Exclude<CategoryKey, 'all'>>('世界背景')

  useEffect(() => {
    if (!projectId) return
    settingsApi.list(projectId).then(res => {
      setSettings(res.data)
      if (res.data.length > 0) {
        const premiseCard = res.data.find((s: WorldSetting) => isPremiseSetting(s.title, s.tags))
        setSelected(premiseCard ?? res.data[0])
      }
    })
    projectsApi.get(projectId).then(res => setCurrentProject(res.data)).catch(() => {})
  }, [projectId, setCurrentProject, setSettings])

  const syncProjectPremise = async (content: string) => {
    if (!projectId || !currentProject) return
    try {
      const res = await projectsApi.update(projectId, { premise: content })
      setCurrentProject(res.data)
    } catch {}
  }

  const create = async () => {
    if (!newTitle.trim() || !projectId) return
    setCreating(true)
    try {
      const res = await settingsApi.create(projectId, {
        title: newTitle.trim(),
        content: '',
        tags: [],
        extra: { category: newCat },
      })
      upsertSetting(res.data)
      setSelected(res.data)
      setActiveCat(newCat)
      setNewTitle('')
    } catch { toast.error('创建失败') }
    finally { setCreating(false) }
  }

  const handleDelete = async (id: string) => {
    try {
      await settingsApi.delete(projectId!, id)
      removeSetting(id)
      toast.success('已删除')
    } catch { toast.error('删除失败') }
  }

  const filtered = activeCat === 'all' ? settings : settings.filter(s => getCategory(s) === activeCat)
  const countByCategory = (k: CategoryKey) =>
    k === 'all' ? settings.length : settings.filter(s => getCategory(s) === k).length

  useEffect(() => {
    if (filtered.length === 0) {
      setSelected(null)
      return
    }
    if (!selected || !filtered.some(s => s.id === selected.id)) {
      setSelected(filtered[0])
    }
  }, [activeCat, filtered, selected])

  return (
    <div className="flex h-full">
      {/* 左栏 */}
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">
        {/* 分类筛选 */}
        <div className="px-2.5 py-2 border-b border-gray-100">
          {CATEGORIES.map(({ key, label, icon: Icon, color }) => (
            <button key={key} onClick={() => setActiveCat(key)}
              className={clsx(
                'w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-sm transition-colors',
                activeCat === key ? 'bg-amber-50 text-amber-700' : 'text-gray-500 hover:bg-gray-50'
              )}>
              <div className="flex items-center gap-2">
                <Icon size={14} className={activeCat === key ? 'text-amber-500' : color} />
                <span className="font-medium">{label}</span>
              </div>
              <span className="text-xs text-gray-400 tabular-nums">{countByCategory(key)}</span>
            </button>
          ))}
        </div>

        {/* 卡片列表 */}
        <div className="flex-1 overflow-auto py-1.5">
          {filtered.map(s => {
            const cat = getCategory(s)
            const meta = getCategoryMeta(cat)
            const Icon = meta.icon
            return (
              <button key={s.id} onClick={() => setSelected(s)}
                className={clsx(
                  'w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors border-l-2',
                  selected?.id === s.id
                    ? 'bg-amber-50 border-l-amber-400'
                    : 'border-l-transparent hover:bg-gray-50'
                )}>
                <Icon size={14} className={meta.color} />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-800 truncate">{s.title}</div>
                  {s.tags.length > 0 && (
                    <div className="text-xs text-gray-400 truncate">{s.tags.slice(0, 2).join(' · ')}</div>
                  )}
                </div>
              </button>
            )
          })}
          {filtered.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8 px-4">
              {activeCat === 'all' ? '暂无设定卡' : `暂无「${activeCat}」设定`}
            </p>
          )}
        </div>

        {/* 新建区 */}
        <div className="border-t border-gray-100 p-3 space-y-2 shrink-0">
          <select value={newCat} onChange={e => setNewCat(e.target.value as any)}
            className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400 bg-white">
            {CATEGORIES.filter(c => c.key !== 'all').map(c => (
              <option key={c.key} value={c.key}>{c.label}</option>
            ))}
          </select>
          <div className="flex gap-1.5">
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && create()}
              placeholder="设定卡标题..."
              className="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400" />
            <button onClick={create} disabled={creating || !newTitle.trim()}
              className="px-2 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 text-white rounded-lg">
              <Plus size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* 右栏 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        <div className="max-w-2xl mx-auto p-6">
          {selected ? (
            <SettingDetail
              key={selected.id}
              setting={selected}
              projectId={projectId!}
              onUpdate={s => { upsertSetting(s); setSelected(s) }}
              onDelete={handleDelete}
              onPremiseSync={syncProjectPremise}
            />
          ) : (
            <div className="flex flex-col items-center justify-center min-h-60 gap-3">
              <Globe size={36} className="text-gray-200" />
              <p className="text-gray-400 text-sm">从左侧选择或新建设定卡</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
