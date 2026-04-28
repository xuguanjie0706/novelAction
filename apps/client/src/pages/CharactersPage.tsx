import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Crown, User, Swords, Zap, BookOpen, Eye, Trash2 } from 'lucide-react'
import { charactersApi } from '../api/client'
import { useAppStore } from '../store'
import type { Character } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// ── 常量 ──────────────────────────────────────────────────

const ROLE_META = {
  protagonist: { label: '主角', color: 'bg-amber-100 text-amber-700 border-amber-200', Icon: Crown },
  supporting:  { label: '配角', color: 'bg-blue-100 text-blue-700 border-blue-200',    Icon: User  },
  antagonist:  { label: '反派', color: 'bg-red-100 text-red-700 border-red-200',        Icon: Swords },
  neutral:     { label: '中立', color: 'bg-gray-100 text-gray-700 border-gray-200',     Icon: User  },
} as const

const STATUS_META: Record<string, { label: string; dot: string }> = {
  alive:       { label: '存活', dot: 'bg-green-500' },
  dead:        { label: '已死', dot: 'bg-gray-400' },
  missing:     { label: '失踪', dot: 'bg-yellow-500' },
  sealed:      { label: '封印', dot: 'bg-purple-500' },
  transformed: { label: '变化', dot: 'bg-blue-500' },
}

// ── 通用表单组件 ──────────────────────────────────────────

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

function TArea({ value, onChange, rows = 3, placeholder }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string }) {
  return (
    <textarea value={value ?? ''} onChange={e => onChange(e.target.value)} rows={rows} placeholder={placeholder}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none" />
  )
}

// ── 人物详情 ──────────────────────────────────────────────

type DetailTab = 'basic' | 'appearance' | 'power' | 'depth' | 'growth'

const DETAIL_TABS: { key: DetailTab; label: string; icon: React.ElementType }[] = [
  { key: 'basic',      label: '基础',     icon: User },
  { key: 'appearance', label: '外貌风格', icon: Eye },
  { key: 'power',      label: '实力体系', icon: Zap },
  { key: 'depth',      label: '深度性格', icon: BookOpen },
  { key: 'growth',     label: '成长轨迹', icon: Crown },
]

function CharacterDetail({ char, projectId, onUpdate, onDelete }: {
  char: Character
  projectId: string
  onUpdate: (c: Character) => void
  onDelete: (id: string) => void
}) {
  const [form, setForm] = useState<Character>({ ...char })
  const [saving, setSaving] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('basic')

  useEffect(() => { setForm({ ...char }); setDetailTab('basic') }, [char.id])

  const meta = ROLE_META[char.role as keyof typeof ROLE_META] ?? ROLE_META.supporting
  const statusM = STATUS_META[form.current_status] ?? STATUS_META.alive

  const save = async () => {
    setSaving(true)
    try {
      const res = await charactersApi.update(projectId, char.id, form)
      onUpdate(res.data); toast.success('已保存')
    } catch { toast.error('保存失败') } finally { setSaving(false) }
  }

  const f = (key: keyof Character) => (v: string) => setForm(prev => ({ ...prev, [key]: v }))

  const SaveBtn = () => (
    <button onClick={save} disabled={saving}
      className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors">
      {saving ? '保存中...' : '保存'}
    </button>
  )

  return (
    <div className="flex flex-col h-full">
      {/* 人物头部卡片 */}
      <div className="shrink-0 bg-white border-b border-gray-100 px-5 pt-5 pb-3">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 flex items-center justify-center shrink-0">
            <span className="text-white text-xl font-bold">{char.name[0]}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-gray-900">{char.name}</h2>
              {(form.alias ?? []).map(a => (
                <span key={a} className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">"{a}"</span>
              ))}
              <span className={clsx('text-xs px-2 py-0.5 rounded-full border font-medium', meta.color)}>{meta.label}</span>
              <span className="flex items-center gap-1 text-xs text-gray-400">
                <span className={clsx('w-1.5 h-1.5 rounded-full', statusM.dot)} />{statusM.label}
              </span>
            </div>
            <div className="text-sm text-gray-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
              {form.gender && <span>{form.gender}</span>}
              {form.age && <span>{form.age}岁</span>}
              {form.current_realm && <span className="text-amber-600 font-medium">⚡ {form.current_realm}</span>}
              {form.faction && <span className="text-blue-600">⚔ {form.faction}</span>}
              {form.current_location && <span className="text-gray-400">📍 {form.current_location}</span>}
            </div>
          </div>
          <button onClick={() => onDelete(char.id)} className="text-gray-300 hover:text-red-400 transition-colors shrink-0">
            <Trash2 size={16} />
          </button>
        </div>

        {/* 标签条 */}
        {((form.special_traits?.length ?? 0) > 0 || (form.strengths?.length ?? 0) > 0 || (form.weaknesses?.length ?? 0) > 0) && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {form.special_traits?.map(t => (
              <span key={t} className="text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full border border-amber-200">{t}</span>
            ))}
            {form.strengths?.map(t => (
              <span key={t} className="text-xs px-2 py-0.5 bg-green-50 text-green-700 rounded-full border border-green-200">+{t}</span>
            ))}
            {form.weaknesses?.map(t => (
              <span key={t} className="text-xs px-2 py-0.5 bg-red-50 text-red-600 rounded-full border border-red-200">−{t}</span>
            ))}
          </div>
        )}

        {/* 子Tab */}
        <div className="flex gap-1 mt-3">
          {DETAIL_TABS.map(({ key, label, icon: Icon }) => (
            <button key={key} onClick={() => setDetailTab(key)}
              className={clsx('flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                detailTab === key ? 'bg-amber-50 text-amber-700 ring-1 ring-amber-200' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50')}>
              <Icon size={12} />{label}
            </button>
          ))}
        </div>
      </div>

      {/* 详情内容 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4] p-5">
        <div className="max-w-2xl mx-auto space-y-4">

          {detailTab === 'basic' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">基础信息</div>
              <div className="grid grid-cols-3 gap-3">
                <Field label="姓名"><TInput value={form.name} onChange={f('name')} /></Field>
                <Field label="性别"><TInput value={form.gender ?? ''} onChange={f('gender')} /></Field>
                <Field label="年龄"><TInput value={form.age ?? ''} onChange={f('age')} /></Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="所属势力"><TInput value={form.faction ?? ''} onChange={f('faction')} /></Field>
                <Field label="势力职位"><TInput value={form.faction_rank ?? ''} onChange={f('faction_rank')} placeholder="如：内门首席弟子" /></Field>
              </div>
              <Field label="出生地"><TInput value={form.birthplace ?? ''} onChange={f('birthplace')} /></Field>
              <Field label="背景经历"><TArea value={form.background ?? ''} onChange={f('background')} rows={4} /></Field>
              <Field label="核心动机"><TArea value={form.motivation ?? ''} onChange={f('motivation')} rows={2} placeholder="想要什么？为什么这样行动？" /></Field>
              <Field label="作者备注（仅自用）"><TArea value={form.author_notes ?? ''} onChange={f('author_notes')} rows={2} placeholder="提醒自己别犯的错误、待展开的细节" /></Field>
              <SaveBtn />
            </div>
          )}

          {detailTab === 'appearance' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">外貌与风格</div>
              <Field label="外貌描述">
                <TArea value={form.appearance ?? ''} onChange={f('appearance')} rows={4} placeholder="身高、容貌、气质、标志性特征（如疤痕、眼色）" />
              </Field>
              <Field label="常见服装与风格">
                <TArea value={form.clothing_style ?? ''} onChange={f('clothing_style')} rows={3} placeholder="习惯穿什么？有何风格特点？" />
              </Field>
              <Field label="说话风格与口头禅">
                <TArea value={form.speech_style ?? ''} onChange={f('speech_style')} rows={3} placeholder="说话方式、语气、惯用词、沉默还是话多？" />
              </Field>
              <SaveBtn />
            </div>
          )}

          {detailTab === 'power' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">实力与体系</div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="当前境界">
                  <TInput value={form.current_realm ?? ''} onChange={f('current_realm')} placeholder="如：斗者七星" />
                </Field>
                <Field label="当前状态">
                  <select value={form.current_status ?? 'alive'} onChange={e => setForm(p => ({ ...p, current_status: e.target.value as any }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400">
                    {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="当前位置"><TInput value={form.current_location ?? ''} onChange={f('current_location')} /></Field>
              <Field label="特殊体质/血脉/天赋（逗号分隔）">
                <TArea value={form.special_traits?.join('、') ?? ''} rows={2} placeholder="如：混沌体、先天道体"
                  onChange={v => setForm(p => ({ ...p, special_traits: v.split(/[,，、]/).map(s => s.trim()).filter(Boolean) }))} />
              </Field>
              <Field label="擅长优点（逗号分隔）">
                <TArea value={form.strengths?.join('、') ?? ''} rows={2}
                  onChange={v => setForm(p => ({ ...p, strengths: v.split(/[,，、]/).map(s => s.trim()).filter(Boolean) }))} />
              </Field>
              <Field label="弱点缺点（逗号分隔）">
                <TArea value={form.weaknesses?.join('、') ?? ''} rows={2}
                  onChange={v => setForm(p => ({ ...p, weaknesses: v.split(/[,，、]/).map(s => s.trim()).filter(Boolean) }))} />
              </Field>
              {(form.known_skills ?? []).length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-2">已掌握技能</div>
                  <div className="flex flex-wrap gap-2">
                    {form.known_skills.map((sk: any, i: number) => (
                      <span key={i} className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded-full border border-blue-200">
                        {sk.skill_name ?? sk}{sk.mastery ? ` · ${sk.mastery}` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {(form.owned_items ?? []).length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-2">持有道具</div>
                  <div className="flex flex-wrap gap-2">
                    {form.owned_items.map((it: any, i: number) => (
                      <span key={i} className="text-xs px-2 py-1 bg-amber-50 text-amber-700 rounded-full border border-amber-200">
                        {it.item_name ?? it}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <SaveBtn />
            </div>
          )}

          {detailTab === 'depth' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">深度性格设定</div>
              <Field label="性格特点"><TArea value={form.personality ?? ''} onChange={f('personality')} rows={3} /></Field>
              <Field label="价值观与底线">
                <TArea value={form.values ?? ''} onChange={f('values')} rows={2} placeholder="什么是他绝对不会做的？最看重什么？" />
              </Field>
              <Field label="内心恐惧">
                <TArea value={form.fear ?? ''} onChange={f('fear')} rows={2} placeholder="最害怕什么？什么能击垮他？" />
              </Field>
              <Field label="心理创伤/执念">
                <TArea value={form.trauma ?? ''} onChange={f('trauma')} rows={3} placeholder="过去的阴影、无法释怀的事" />
              </Field>
              <Field label="秘密（作者知道，读者暂不知）">
                <TArea value={form.secrets ?? ''} onChange={f('secrets')} rows={3} placeholder="隐藏身份、隐瞒的事、不为人知的过去" />
              </Field>
              <SaveBtn />
            </div>
          )}

          {detailTab === 'growth' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">人物弧线与成长</div>
              <Field label="人物弧线（整体描述）">
                <TArea value={form.arc ?? ''} onChange={f('arc')} rows={3} placeholder="从开始到结局，这个人物会经历怎样的转变？" />
              </Field>
              <div>
                <div className="text-xs font-medium text-gray-500 mb-3">结构化成长阶段</div>
                <div className="space-y-2 mb-2">
                  {(form.arc_stages ?? []).map((stage: any, idx: number) => (
                    <div key={idx} className="flex gap-3 p-3 bg-amber-50 rounded-lg border border-amber-100">
                      <div className="w-5 h-5 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center shrink-0 mt-0.5 font-bold">
                        {idx + 1}
                      </div>
                      <div className="flex-1 grid grid-cols-2 gap-2 min-w-0">
                        <input value={stage.stage ?? ''} placeholder="阶段名" onChange={e => {
                          const stages = [...(form.arc_stages ?? [])]
                          stages[idx] = { ...stages[idx], stage: e.target.value }
                          setForm(p => ({ ...p, arc_stages: stages }))
                        }} className="col-span-2 text-sm font-medium bg-transparent border-0 focus:outline-none text-gray-800 border-b border-amber-200 pb-1" />
                        <input value={stage.realm ?? ''} placeholder="此阶段境界" onChange={e => {
                          const stages = [...(form.arc_stages ?? [])]
                          stages[idx] = { ...stages[idx], realm: e.target.value }
                          setForm(p => ({ ...p, arc_stages: stages }))
                        }} className="text-xs text-amber-600 bg-transparent border-0 focus:outline-none" />
                        <input value={stage.chapter_range ?? ''} placeholder="章节范围 (如1-30)" onChange={e => {
                          const stages = [...(form.arc_stages ?? [])]
                          stages[idx] = { ...stages[idx], chapter_range: e.target.value }
                          setForm(p => ({ ...p, arc_stages: stages }))
                        }} className="text-xs text-gray-400 bg-transparent border-0 focus:outline-none" />
                        <input value={stage.state ?? ''} placeholder="人物状态描述" onChange={e => {
                          const stages = [...(form.arc_stages ?? [])]
                          stages[idx] = { ...stages[idx], state: e.target.value }
                          setForm(p => ({ ...p, arc_stages: stages }))
                        }} className="col-span-2 text-xs text-gray-500 bg-transparent border-0 focus:outline-none" />
                      </div>
                      <button onClick={() => setForm(p => ({ ...p, arc_stages: (p.arc_stages ?? []).filter((_: any, i: number) => i !== idx) }))}
                        className="text-gray-300 hover:text-red-400 shrink-0 self-start">✕</button>
                    </div>
                  ))}
                </div>
                <button onClick={() => setForm(p => ({ ...p, arc_stages: [...(p.arc_stages ?? []), { stage: '', realm: '', state: '', chapter_range: '' }] }))}
                  className="w-full py-2 border border-dashed border-amber-300 text-amber-500 text-xs rounded-lg hover:bg-amber-50 transition-colors">
                  + 添加成长阶段
                </button>
              </div>
              <SaveBtn />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { characters, setCharacters, upsertCharacter, removeCharacter } = useAppStore()
  const [selected, setSelected] = useState<Character | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!projectId) return
    charactersApi.list(projectId).then(res => {
      setCharacters(res.data)
      if (res.data.length > 0) setSelected(res.data[0])
    })
  }, [projectId])

  const protagonist = characters.find(c => c.role === 'protagonist')
  const supporting  = characters.filter(c => c.role === 'supporting')
  const antagonists = characters.filter(c => c.role === 'antagonist')
  const neutrals    = characters.filter(c => c.role === 'neutral')
  const groups = [
    { key: 'protagonist' as const, chars: protagonist ? [protagonist] : [] },
    { key: 'supporting'  as const, chars: supporting },
    { key: 'antagonist'  as const, chars: antagonists },
    { key: 'neutral'     as const, chars: neutrals },
  ]

  const handleCreate = async () => {
    if (!projectId || creating) return
    setCreating(true)
    try {
      const res = await charactersApi.create(projectId, { name: '新人物', role: 'supporting' })
      upsertCharacter(res.data); setSelected(res.data)
    } catch { toast.error('创建失败') } finally { setCreating(false) }
  }

  const handleDelete = async (id: string) => {
    if (!projectId || !confirm('确认删除这个人物？')) return
    await charactersApi.delete(projectId, id)
    removeCharacter(id)
    const rest = characters.filter(c => c.id !== id)
    setSelected(rest.length > 0 ? rest[0] : null)
    toast.success('已删除')
  }

  return (
    <div className="flex h-full">
      {/* 左栏：人物列表 */}
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0 overflow-auto">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">人物库</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{characters.length} 人</span>
            <button onClick={handleCreate} disabled={creating} className="text-amber-500 hover:text-amber-600 disabled:opacity-50">
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {groups.map(({ key, chars }) => chars.length > 0 && (
            <div key={key} className="mb-2">
              <div className="px-4 py-1">
                <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full border', ROLE_META[key].color)}>
                  {ROLE_META[key].label}
                </span>
              </div>
              {chars.map(c => {
                const sm = STATUS_META[c.current_status ?? 'alive'] ?? STATUS_META.alive
                return (
                  <button key={c.id} onClick={() => setSelected(c)}
                    className={clsx('w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors border-l-2',
                      selected?.id === c.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                    <div className="relative shrink-0">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-200 to-amber-400 flex items-center justify-center">
                        <span className="text-white text-xs font-bold">{c.name[0]}</span>
                      </div>
                      <span className={clsx('absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white', sm.dot)} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-800 truncate">{c.name}</div>
                      <div className="text-xs text-gray-400 truncate">
                        {c.current_realm ?? c.faction ?? c.gender ?? ''}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          ))}
          {characters.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8 px-4">暂无人物，点击 + 创建</p>
          )}
        </div>
      </div>

      {/* 右栏：人物详情 */}
      <div className="flex-1 overflow-hidden bg-[#FAF8F4]">
        {selected
          ? <CharacterDetail char={selected} projectId={projectId!} onUpdate={upsertCharacter} onDelete={handleDelete} />
          : <div className="flex items-center justify-center h-full text-gray-400 text-sm">选择左侧人物查看详情</div>
        }
      </div>
    </div>
  )
}
