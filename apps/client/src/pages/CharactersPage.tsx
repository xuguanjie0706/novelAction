import React, { useEffect, useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Crown, User, Swords, Zap, BookOpen, Eye, Trash2, Heart, TrendingUp, FileText, Target, NotebookPen, Search, Users, History, Eraser, X, RotateCcw, Check, Loader2 } from 'lucide-react'
import { charactersApi, outlineApi, aiApi } from '../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../store'
import type { Character, CharacterChangeLog } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// ── 常量 ──────────────────────────────────────────────────

const ROLE_META = {
  protagonist: { label: '主角', color: 'bg-amber-100 text-amber-700 border-amber-200', Icon: Crown },
  supporting:  { label: '配角', color: 'bg-blue-100 text-blue-700 border-blue-200',    Icon: User  },
  antagonist:  { label: '反派', color: 'bg-red-100 text-red-700 border-red-200',        Icon: Swords },
  neutral:     { label: '中立', color: 'bg-gray-100 text-gray-700 border-gray-200',     Icon: User  },
} as const

/**
 * 叙事层级（character_tier）
 * core        = 核心长线：贯穿全书，长期驱动主线/支线
 * arc         = 弧线支柱：某卷/某段主导剧情，随弧线完结淡出
 * plot        = 剧情推手：短期内推进特定剧情节点后退场
 * background  = 背景填充：增加世界厚度，无强情节绑定
 */
const TIER_META: Record<string, { label: string; short: string; color: string; dot: string; desc: string }> = {
  core:       { label: '核心长线', short: '长线', color: 'bg-violet-100 text-violet-700 border-violet-300', dot: 'bg-violet-500', desc: '贯穿全书，长期驱动主线' },
  arc:        { label: '弧线支柱', short: '弧线', color: 'bg-blue-100 text-blue-700 border-blue-300',       dot: 'bg-blue-500',   desc: '某卷/某段主导剧情，随弧线完结淡出' },
  plot:       { label: '剧情推手', short: '短期', color: 'bg-orange-100 text-orange-700 border-orange-300', dot: 'bg-orange-400', desc: '短期推进剧情节点后退场' },
  background: { label: '背景填充', short: '背景', color: 'bg-gray-100 text-gray-500 border-gray-300',       dot: 'bg-gray-400',   desc: '增加世界厚度，无强情节绑定' },
}

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

type DetailTab = 'basic' | 'appearance' | 'power' | 'depth' | 'growth' | 'changelog'

const DETAIL_TABS: { key: DetailTab; label: string; icon: React.ElementType }[] = [
  { key: 'basic',      label: '基础',     icon: User },
  { key: 'appearance', label: '外貌风格', icon: Eye },
  { key: 'power',      label: '实力体系', icon: Zap },
  { key: 'depth',      label: '深度性格', icon: Heart },
  { key: 'growth',     label: '成长轨迹', icon: TrendingUp },
  { key: 'changelog',  label: '变更记录', icon: History },
]

function CharacterTag({ children, tone = 'amber' }: { children: React.ReactNode; tone?: 'amber' | 'green' | 'red' }) {
  const colors = {
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    red: 'bg-red-50 text-red-600 border-red-200',
  }

  return (
    <span className={clsx('text-sm px-4 py-2 rounded-lg border font-medium shadow-sm', colors[tone])}>
      {children}
    </span>
  )
}

function InfoPanel({
  icon: Icon,
  title,
  accent,
  children,
}: {
  icon: React.ElementType
  title: string
  accent: string
  children: React.ReactNode
}) {
  return (
    <section className={clsx('bg-white rounded-2xl border border-gray-100 shadow-sm p-6 border-l-4', accent)}>
      <div className="flex items-center gap-3 mb-4">
        <Icon size={22} className="text-current" />
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
      </div>
      {children}
    </section>
  )
}

interface ProtagonistRealmMilestone {
  chapter_number: number
  chapter_title: string
  realm_name: string
  realm_rank: number
  character_change: string
  /** outline=大纲人物变化；debrief=正文复盘提交 character_updates */
  source?: string
}

interface ProtagonistRealmTimelinePayload {
  protagonist_display_name?: string | null
  protagonist_anchor_names?: string[]
  has_realm_whitelist: boolean
  anchored: boolean
  chapter_plans_scanned: number
  debrief_snapshots?: number
  milestones: ProtagonistRealmMilestone[]
  source?: string
}

function CharacterDetail({ char, projectId, onUpdate, onDelete }: {
  char: Character
  projectId: string
  onUpdate: (c: Character) => void
  onDelete: (id: string) => void
}) {
  const [form, setForm] = useState<Character>({ ...char })
  const [saving, setSaving] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('basic')
  const [realmTimeline, setRealmTimeline] = useState<ProtagonistRealmTimelinePayload | null>(null)
  const [realmTimelineLoading, setRealmTimelineLoading] = useState(false)
  const [changelog, setChangelog] = useState<CharacterChangeLog[]>([])
  const [changelogLoading, setChangelogLoading] = useState(false)

  useEffect(() => { setForm({ ...char }); setDetailTab('basic') }, [char.id])

  useEffect(() => {
    if (detailTab !== 'changelog') return
    let cancelled = false
    setChangelogLoading(true)
    charactersApi.getChangelog(projectId, char.id)
      .then(res => { if (!cancelled) setChangelog(res.data) })
      .catch(() => { if (!cancelled) setChangelog([]) })
      .finally(() => { if (!cancelled) setChangelogLoading(false) })
    return () => { cancelled = true }
  }, [detailTab, char.id, projectId])

  useEffect(() => {
    if (detailTab !== 'growth' || char.role !== 'protagonist') return
    let cancelled = false
    setRealmTimelineLoading(true)
    outlineApi.protagonistRealmTimeline(projectId)
      .then((res) => {
        if (!cancelled) setRealmTimeline(res.data as ProtagonistRealmTimelinePayload)
      })
      .catch(() => {
        if (!cancelled) setRealmTimeline(null)
      })
      .finally(() => {
        if (!cancelled) setRealmTimelineLoading(false)
      })
    return () => { cancelled = true }
  }, [detailTab, char.role, char.id, projectId])

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
    <div className="flex flex-col h-full bg-[#FAF8F4] p-6 overflow-auto">
      {/* 人物头部卡片 */}
      <div className="shrink-0 bg-white rounded-2xl border border-gray-100 shadow-sm px-8 py-7">
        <div className="flex items-start gap-8">
          <div className="w-28 h-28 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 flex items-center justify-center shrink-0 shadow-sm">
            <span className="text-white text-5xl font-bold">{char.name[0]}</span>
          </div>
          <div className="flex-1 min-w-0 pt-2">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-4xl font-bold text-gray-900 leading-tight">{char.name}</h2>
              {(form.alias ?? []).map(a => (
                <span key={a} className="text-sm px-2 py-1 bg-gray-100 text-gray-500 rounded-lg">"{a}"</span>
              ))}
              <span className={clsx('text-base px-3 py-1 rounded-lg border font-semibold', meta.color)}>{meta.label}</span>
              <span className="flex items-center gap-2 text-base text-gray-400">
                <span className={clsx('w-2.5 h-2.5 rounded-full', statusM.dot)} />{statusM.label}
              </span>
            </div>
            <div className="text-lg text-gray-500 flex flex-wrap gap-x-4 gap-y-1 mt-4">
              {form.gender && <span>{form.gender}</span>}
              {form.gender && form.age && <span className="text-gray-300">|</span>}
              {form.age && <span>{form.age}岁</span>}
              {(form.gender || form.age) && (form.current_realm || form.faction || form.current_location) && <span className="text-gray-300">|</span>}
              {form.current_realm && <span className="text-amber-600 font-medium">{form.current_realm}</span>}
              {form.faction && <span className="text-blue-600">{form.faction}</span>}
              {form.current_location && <span className="text-gray-400">{form.current_location}</span>}
            </div>
          </div>
          <button onClick={() => onDelete(char.id)} className="w-11 h-11 rounded-xl border border-gray-200 text-gray-400 hover:text-red-400 hover:border-red-200 transition-colors shrink-0 flex items-center justify-center">
            <Trash2 size={20} />
          </button>
        </div>

        {/* 标签只保留在头部，避免和基础信息卡片重复展示 */}
        {((form.special_traits?.length ?? 0) > 0 || (form.strengths?.length ?? 0) > 0 || (form.weaknesses?.length ?? 0) > 0) && (
          <div className="flex flex-wrap gap-3 mt-6 pl-36">
            {form.special_traits?.map(t => (
              <CharacterTag key={`trait-${t}`} tone="amber">{t}</CharacterTag>
            ))}
            {form.strengths?.map(t => (
              <CharacterTag key={`strength-${t}`} tone="green">+ {t}</CharacterTag>
            ))}
            {form.weaknesses?.map(t => (
              <CharacterTag key={`weakness-${t}`} tone="red">− {t}</CharacterTag>
            ))}
          </div>
        )}
      </div>

      {/* 子Tab */}
      <div className="shrink-0 bg-white rounded-2xl border border-gray-100 shadow-sm mt-5 px-8">
        <div className="grid grid-cols-6">
          {DETAIL_TABS.map(({ key, label, icon: Icon }) => (
            <button key={key} onClick={() => setDetailTab(key)}
              className={clsx('relative flex items-center justify-center gap-3 py-5 text-lg font-semibold transition-colors',
                detailTab === key ? 'text-gray-900' : 'text-gray-500 hover:text-gray-700')}>
              <Icon size={24} className={detailTab === key ? 'text-amber-500' : 'text-gray-500'} />{label}
              {detailTab === key && <span className="absolute left-5 right-5 bottom-0 h-0.5 bg-amber-400 rounded-full" />}
            </button>
          ))}
        </div>
      </div>

      {/* 详情内容 */}
      <div className="flex-1 pt-7">
        <div className="space-y-6">

          {detailTab === 'basic' && (
            <div className="grid grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] gap-6">
              <section className="bg-white rounded-2xl p-8 border border-gray-100 shadow-sm space-y-5">
                <div className="flex items-center gap-3 border-b border-gray-100 pb-5">
                  <FileText size={22} className="text-amber-500" />
                  <h3 className="text-lg font-bold text-gray-900">基础信息</h3>
                </div>
                <div className="grid grid-cols-3 gap-5">
                  <Field label="姓名"><TInput value={form.name} onChange={f('name')} /></Field>
                  <Field label="性别"><TInput value={form.gender ?? ''} onChange={f('gender')} /></Field>
                  <Field label="年龄"><TInput value={form.age ?? ''} onChange={f('age')} /></Field>
                </div>
                <Field label="叙事层级">
                  <div className="grid grid-cols-2 gap-2">
                    {(Object.entries(TIER_META) as [string, typeof TIER_META[string]][]).map(([key, tm]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setForm(p => ({ ...p, character_tier: key as any }))}
                        className={clsx(
                          'flex items-start gap-2.5 px-3 py-2.5 rounded-xl border text-left transition-all',
                          (form.character_tier ?? 'core') === key
                            ? tm.color + ' shadow-sm ring-1 ring-current/30'
                            : 'bg-gray-50 text-gray-400 border-gray-200 hover:border-gray-300',
                        )}
                      >
                        <span className={clsx('w-2 h-2 rounded-full shrink-0 mt-1', tm.dot)} />
                        <div>
                          <div className="text-xs font-semibold leading-tight">{tm.label}</div>
                          <div className="text-[10px] leading-tight mt-0.5 opacity-70">{tm.desc}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </Field>
                <div className="grid grid-cols-2 gap-5">
                  <Field label="所属势力"><TInput value={form.faction ?? ''} onChange={f('faction')} /></Field>
                  <Field label="势力职位"><TInput value={form.faction_rank ?? ''} onChange={f('faction_rank')} placeholder="如：内门首席弟子" /></Field>
                </div>
                <Field label="出生地"><TInput value={form.birthplace ?? ''} onChange={f('birthplace')} placeholder="未填写" /></Field>
                <SaveBtn />
              </section>

              <div className="space-y-6">
                <InfoPanel icon={BookOpen} title="背景经历" accent="border-l-blue-400">
                  <TArea value={form.background ?? ''} onChange={f('background')} rows={5} />
                </InfoPanel>
                <InfoPanel icon={Target} title="核心动机" accent="border-l-emerald-400">
                  <TArea value={form.motivation ?? ''} onChange={f('motivation')} rows={4} placeholder="想要什么？为什么这样行动？" />
                </InfoPanel>
                <InfoPanel icon={NotebookPen} title="作者备注（仅自用）" accent="border-l-purple-400">
                  <TArea value={form.author_notes ?? ''} onChange={f('author_notes')} rows={3} placeholder="提醒自己犯错的错误、待展开的细节" />
                </InfoPanel>
                <div className="flex justify-end"><SaveBtn /></div>
              </div>
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
              {char.role === 'protagonist' && (
                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="text-xs font-semibold text-slate-700">境界时间轴（只读）</div>
                    <span className="text-[10px] text-slate-500 shrink-0 text-right">
                      大纲「人物变化」+ 正文复盘 character_updates
                      {typeof realmTimeline?.debrief_snapshots === 'number' && realmTimeline.debrief_snapshots > 0
                        ? ` · 已存 ${realmTimeline.debrief_snapshots} 条复盘快照`
                        : ''}
                    </span>
                  </div>
                  {realmTimelineLoading && (
                    <p className="text-xs text-slate-500">加载中…</p>
                  )}
                  {!realmTimelineLoading && realmTimeline
                    && (realmTimeline.milestones?.length ?? 0) === 0
                    && realmTimeline.chapter_plans_scanned === 0
                    && (realmTimeline.debrief_snapshots ?? 0) === 0 && (
                    <p className={clsx(
                      'text-xs',
                      realmTimeline.has_realm_whitelist ? 'text-slate-600' : 'text-amber-700',
                    )}>
                      {realmTimeline.has_realm_whitelist
                        ? '尚无大纲章节计划，也未提交过带境界的主角复盘；写作保存复盘后会自动累积此处。'
                        : '尚未配置力量体系 levels，且尚无正文复盘境界快照；配置体系或提交复盘后可在此查看。'}
                    </p>
                  )}
                  {!realmTimelineLoading && realmTimeline && !realmTimeline.has_realm_whitelist
                    && (realmTimeline.milestones?.length ?? 0) > 0 && (
                    <p className="text-xs text-slate-600">未配置 levels 时，rank 主要依赖复盘填写或境界名子串匹配，建议补全力量体系以便与大纲对齐。</p>
                  )}
                  {!realmTimelineLoading && realmTimeline?.has_realm_whitelist && realmTimeline.chapter_plans_scanned > 0 && realmTimeline.milestones.length === 0 && (
                    <p className="text-xs text-slate-600">
                      已扫描 {realmTimeline.chapter_plans_scanned} 个章节计划，未解析到带主角归因的境界提升（请在大纲「人物变化」中写明突破/晋升等，且与主角姓名共现）。
                    </p>
                  )}
                  {!realmTimelineLoading && (realmTimeline?.milestones?.length ?? 0) > 0 && (
                    <ul className="space-y-2 max-h-56 overflow-y-auto">
                      {realmTimeline!.milestones.map((m, i) => (
                        <li key={`${m.chapter_number}-${m.realm_rank}-${i}`} className="text-xs border border-slate-200 rounded-md bg-white p-2.5">
                          <div className="font-medium text-slate-800 flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span>
                              第{m.chapter_number}章
                              {m.chapter_title ? `《${m.chapter_title}》` : ''}
                              <span className="text-violet-700 ml-1">→ {m.realm_name}</span>
                              <span className="text-slate-400 font-normal ml-1">(rank {m.realm_rank})</span>
                            </span>
                            {(m.source === 'debrief' || m.source === 'outline') && (
                              <span className={clsx(
                                'text-[10px] px-1.5 py-0.5 rounded border font-medium',
                                m.source === 'debrief'
                                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                  : 'bg-slate-100 text-slate-600 border-slate-200',
                              )}>
                                {m.source === 'debrief' ? '复盘' : '大纲'}
                              </span>
                            )}
                          </div>
                          {m.character_change ? (
                            <p className="text-slate-500 mt-1 line-clamp-2">{m.character_change}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
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

          {detailTab === 'changelog' && (
            <ChangelogTab
              logs={changelog}
              loading={changelogLoading}
              charId={char.id}
              onClear={async () => {
                if (!confirm('确认清空该人物的全部变更记录？此操作不可撤销。')) return
                try {
                  await charactersApi.clearChangelog(projectId, char.id)
                  setChangelog([])
                  toast.success('变更记录已清空')
                } catch {
                  toast.error('清空失败')
                }
              }}
              onDelete={async (logId) => {
                if (!confirm('确认删除这条变更记录？')) return
                try {
                  await charactersApi.deleteChangelogEntry(projectId, char.id, logId)
                  setChangelog(prev => prev.filter(l => (l.id as string) !== logId))
                  toast.success('已删除')
                } catch {
                  toast.error('删除失败')
                }
              }}
              onRedebrief={async (chapterId) => {
                const route = useAppStore.getState().aiBackendRoute
                const res = await aiApi.autoDebrief(projectId, {
                  chapter_id: chapterId,
                  model_profile: modelProfileFromRoute(route),
                  ...routeLlmProviderPayload(route),
                })
                const data = res.data as any
                // 过滤出本人物的变化，映射为 ChangePill 格式
                const cu = (data.character_updates ?? []).find(
                  (u: any) => u.character_id === char.id || u.character_name === char.name,
                )
                if (!cu) return []
                const updates: Array<{ field: string; label: string; before: string | null; after: string | null }> = []
                if (cu.current_realm)    updates.push({ field: 'current_realm',    label: '境界',    before: char.current_realm    ?? null, after: cu.current_realm })
                if (cu.current_location) updates.push({ field: 'current_location', label: '位置',    before: char.current_location ?? null, after: cu.current_location })
                if (cu.current_status)   updates.push({ field: 'current_status',   label: '状态',    before: char.current_status   ?? null, after: cu.current_status })
                if (cu.add_skill_name)   updates.push({ field: 'skill_gained',     label: '习得技能', before: null,                         after: cu.add_skill_name })
                return updates
              }}
              onConfirmRedebrief={async (chapterId, charId, updates) => {
                const charUpdate: Record<string, any> = { character_id: charId }
                for (const u of updates) {
                  if (u.field === 'current_realm')    charUpdate.current_realm    = u.after
                  if (u.field === 'current_location') charUpdate.current_location = u.after
                  if (u.field === 'current_status')   charUpdate.current_status   = u.after
                  if (u.field === 'skill_gained')     charUpdate.add_skill        = { skill_name: u.after, mastery: '初学' }
                }
                await aiApi.chapterDebrief(projectId, {
                  chapter_id: chapterId,
                  character_updates: [charUpdate] as any,
                })
                // 刷新变更记录
                const fresh = await charactersApi.getChangelog(projectId, char.id)
                setChangelog(fresh.data)
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ── 变更记录 Tab ──────────────────────────────────────────

const CHANGE_FIELD_STYLE: Record<string, { dot: string; pill: string; label?: string }> = {
  current_realm:    { dot: 'bg-violet-500', pill: 'bg-violet-50 text-violet-700 border-violet-200' },
  current_status:   { dot: 'bg-red-500',    pill: 'bg-red-50 text-red-700 border-red-200' },
  current_location: { dot: 'bg-blue-500',   pill: 'bg-blue-50 text-blue-700 border-blue-200' },
  skill_gained:     { dot: 'bg-emerald-500',pill: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  item_gained:      { dot: 'bg-amber-500',  pill: 'bg-amber-50 text-amber-700 border-amber-200' },
  item_lost:        { dot: 'bg-orange-400', pill: 'bg-orange-50 text-orange-700 border-orange-200' },
  created:          { dot: 'bg-orange-500', pill: 'bg-orange-50 text-orange-700 border-orange-200' },
  character_tier:   { dot: 'bg-purple-400', pill: 'bg-purple-50 text-purple-700 border-purple-200' },
  faction:          { dot: 'bg-cyan-500',   pill: 'bg-cyan-50 text-cyan-700 border-cyan-200' },
  role:             { dot: 'bg-gray-400',   pill: 'bg-gray-50 text-gray-600 border-gray-200' },
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  debrief:   { label: '复盘', color: 'bg-blue-100 text-blue-700' },
  manual:    { label: '手动', color: 'bg-gray-100 text-gray-600' },
  bootstrap: { label: '生成', color: 'bg-violet-100 text-violet-700' },
}

function ChangePill({ field, label, before, after }: {
  field: string; label: string; before: string | null; after: string | null
}) {
  const style = CHANGE_FIELD_STYLE[field] ?? { dot: 'bg-gray-400', pill: 'bg-gray-50 text-gray-600 border-gray-200' }
  let text = ''
  if (field === 'created') {
    text = `首次入库 · ${after ?? ''}`
  } else if (before && after) {
    text = `${label} ${before} → ${after}`
  } else if (after) {
    text = `${label}：${after}`
  } else if (before) {
    text = `失去${label}：${before}`
  }
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border font-medium', style.pill)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0', style.dot)} />
      {text}
    </span>
  )
}

type RedebriefState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'result'; updates: Array<{ field: string; label: string; before: string | null; after: string | null }>; chapterId: string }
  | { status: 'submitting' }

function ChangelogTab({
  logs, loading, onClear, onDelete, onRedebrief, onConfirmRedebrief,
}: {
  logs: CharacterChangeLog[]
  loading: boolean
  charId: string
  onClear: () => void
  onDelete: (logId: string) => void
  onRedebrief: (chapterId: string, charId: string) => Promise<Array<{ field: string; label: string; before: string | null; after: string | null }>>
  onConfirmRedebrief: (chapterId: string, charId: string, updates: Array<{ field: string; after: string | null }>) => Promise<void>
}) {
  // per-entry redebrief state
  const [redebriefStates, setRedebriefStates] = useState<Record<string, RedebriefState>>({})

  const setEntryState = (logId: string, state: RedebriefState) =>
    setRedebriefStates(prev => ({ ...prev, [logId]: state }))

  const handleRedebrief = async (log: CharacterChangeLog) => {
    if (!log.chapter_id) return
    setEntryState(log.id as string, { status: 'loading' })
    try {
      const updates = await onRedebrief(log.chapter_id as string, log.character_id as string)
      setEntryState(log.id as string, { status: 'result', updates, chapterId: log.chapter_id as string })
    } catch {
      setEntryState(log.id as string, { status: 'idle' })
      toast.error('重新复盘失败')
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16 text-gray-400 text-sm">加载中…</div>
  }
  if (logs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center text-gray-400">
        <History size={32} className="mb-3 opacity-30" />
        <p className="text-sm">暂无变更记录</p>
        <p className="text-xs mt-1 text-gray-300">复盘提交或手动保存后会自动记录</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <History size={16} className="text-gray-400" />
          <span className="text-sm font-semibold text-gray-700">变更时间轴</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{logs.length} 条记录</span>
          <button onClick={onClear} className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors" title="清空全部">
            <Eraser size={12} />
            清空全部
          </button>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-3.5 top-2 bottom-2 w-px bg-gray-100" />

        <div className="space-y-0">
          {logs.map((log) => {
            const srcMeta = SOURCE_META[log.source] ?? SOURCE_META.manual
            const firstField = log.changes[0]?.field ?? 'created'
            const dotColor = (CHANGE_FIELD_STYLE[firstField] ?? CHANGE_FIELD_STYLE.created).dot
            const rstate = redebriefStates[log.id as string] ?? { status: 'idle' }

            return (
              <div key={log.id as string} className="flex gap-4 pb-5 relative group">
                {/* 时间轴节点 */}
                <div className="flex-shrink-0 w-7 flex justify-center pt-0.5">
                  <div className={clsx('w-3 h-3 rounded-full border-2 border-white ring-1 ring-gray-200 relative z-10', dotColor)} />
                </div>

                {/* 内容卡片 */}
                <div className="flex-1 min-w-0">
                  <div className="bg-gray-50 rounded-xl p-3.5 border border-gray-100">
                    {/* 头部 */}
                    <div className="flex items-center justify-between gap-2 mb-2.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {log.chapter_number
                          ? <span className="text-xs font-semibold text-gray-700 truncate">{log.chapter_number}{log.chapter_title ? `《${log.chapter_title}》` : ''}</span>
                          : <span className="text-xs font-semibold text-gray-500">无章节关联</span>
                        }
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', srcMeta.color)}>{srcMeta.label}</span>
                        <span className="text-[10px] text-gray-300">
                          {new Date(log.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                        {/* 操作按钮：hover 显示 */}
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {log.chapter_id && rstate.status === 'idle' && (
                            <button
                              onClick={() => handleRedebrief(log)}
                              className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded text-blue-500 hover:bg-blue-50 transition-colors"
                              title="重新复盘该章，补入新记录"
                            >
                              <RotateCcw size={10} />
                              重新复盘
                            </button>
                          )}
                          <button
                            onClick={() => onDelete(log.id as string)}
                            className="p-0.5 rounded text-gray-300 hover:text-red-400 hover:bg-red-50 transition-colors"
                            title="删除此条记录"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* 变更 Pills */}
                    <div className="flex flex-wrap gap-1.5">
                      {log.changes.map((c, i) => (
                        <ChangePill key={i} field={c.field} label={c.label} before={c.before} after={c.after} />
                      ))}
                    </div>
                  </div>

                  {/* 重新复盘内联结果 */}
                  {rstate.status === 'loading' && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-blue-500 pl-2">
                      <Loader2 size={12} className="animate-spin" />
                      AI 正在分析该章节…
                    </div>
                  )}
                  {rstate.status === 'result' && (
                    <div className="mt-2 bg-blue-50 border border-blue-100 rounded-xl p-3.5">
                      <p className="text-xs font-semibold text-blue-700 mb-2">
                        {rstate.updates.length > 0 ? `检测到 ${rstate.updates.length} 项变化` : 'AI 未检测到该章节的人物变化'}
                      </p>
                      {rstate.updates.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {rstate.updates.map((u, i) => (
                            <ChangePill key={i} field={u.field} label={u.label} before={u.before} after={u.after} />
                          ))}
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={() => setEntryState(log.id as string, { status: 'idle' })}
                          className="flex-1 py-1.5 text-xs text-gray-500 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                        >
                          取消
                        </button>
                        {rstate.updates.length > 0 && (
                          <button
                            onClick={async () => {
                              setEntryState(log.id as string, { status: 'submitting' })
                              try {
                                await onConfirmRedebrief(
                                  rstate.chapterId,
                                  log.character_id as string,
                                  rstate.updates.map(u => ({ field: u.field, after: u.after })),
                                )
                                setEntryState(log.id as string, { status: 'idle' })
                                toast.success('已补入新变更记录')
                              } catch {
                                setEntryState(log.id as string, { status: 'result', updates: rstate.updates, chapterId: rstate.chapterId })
                                toast.error('提交失败')
                              }
                            }}
                            className="flex-1 py-1.5 text-xs text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors flex items-center justify-center gap-1"
                          >
                            <Check size={11} />
                            确认补入
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                  {rstate.status === 'submitting' && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-blue-500 pl-2">
                      <Loader2 size={12} className="animate-spin" />
                      提交中…
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────

type RoleFilter   = 'all' | 'protagonist' | 'supporting' | 'antagonist' | 'neutral'
type StatusFilter = 'all' | 'alive' | 'dead' | 'missing' | 'sealed' | 'transformed'
type TierFilter   = 'all' | 'core' | 'arc' | 'plot' | 'background'
type GroupBy      = 'role' | 'faction'

const ROLE_CHIPS: { key: RoleFilter; label: string }[] = [
  { key: 'all',         label: '全部' },
  { key: 'protagonist', label: '主角' },
  { key: 'antagonist',  label: '反派' },
  { key: 'supporting',  label: '配角' },
  { key: 'neutral',     label: '中立' },
]
const STATUS_CHIPS: { key: StatusFilter; label: string }[] = [
  { key: 'all',         label: '全部' },
  { key: 'alive',       label: '存活' },
  { key: 'dead',        label: '死亡' },
  { key: 'missing',     label: '失踪' },
  { key: 'sealed',      label: '封印' },
]

const TIER_CHIPS: { key: TierFilter; label: string }[] = [
  { key: 'all',        label: '全部' },
  { key: 'core',       label: '长线' },
  { key: 'arc',        label: '弧线' },
  { key: 'plot',       label: '短期' },
  { key: 'background', label: '背景' },
]

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { characters, setCharacters, upsertCharacter, removeCharacter } = useAppStore()
  const [selected, setSelected]         = useState<Character | null>(null)
  const [creating, setCreating]         = useState(false)
  const [searchQ, setSearchQ]           = useState('')
  const [roleFilter, setRoleFilter]     = useState<RoleFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [tierFilter, setTierFilter]     = useState<TierFilter>('all')
  const [groupBy, setGroupBy]           = useState<GroupBy>('role')

  useEffect(() => {
    if (!projectId) return
    charactersApi.list(projectId).then(res => {
      setCharacters(res.data)
      if (res.data.length > 0) setSelected(res.data[0])
    })
  }, [projectId])

  // ── 过滤 ──────────────────────────────────────────────────
  const filteredChars = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return characters.filter(c => {
      if (q && !c.name.toLowerCase().includes(q) && !(c.faction ?? '').toLowerCase().includes(q)) return false
      if (roleFilter !== 'all' && c.role !== roleFilter) return false
      if (statusFilter !== 'all' && (c.current_status ?? 'alive') !== statusFilter) return false
      if (tierFilter !== 'all' && (c.character_tier ?? 'core') !== tierFilter) return false
      return true
    })
  }, [characters, searchQ, roleFilter, statusFilter, tierFilter])

  // ── 分组 ──────────────────────────────────────────────────
  const groups = useMemo(() => {
    if (groupBy === 'role') {
      const order: RoleFilter[] = ['protagonist', 'antagonist', 'supporting', 'neutral']
      return order
        .map(role => ({
          key: role,
          label: ROLE_META[role as keyof typeof ROLE_META]?.label ?? role,
          color: ROLE_META[role as keyof typeof ROLE_META]?.color ?? '',
          chars: filteredChars.filter(c => c.role === role),
        }))
        .filter(g => g.chars.length > 0)
    } else {
      const map = new Map<string, Character[]>()
      filteredChars.forEach(c => {
        const key = c.faction?.trim() || '无势力'
        if (!map.has(key)) map.set(key, [])
        map.get(key)!.push(c)
      })
      return Array.from(map.entries())
        .sort((a, b) => {
          if (a[0] === '无势力') return 1
          if (b[0] === '无势力') return -1
          return b[1].length - a[1].length
        })
        .map(([faction, chars]) => ({
          key: faction,
          label: faction,
          color: 'bg-blue-50 text-blue-700 border-blue-200',
          chars,
        }))
    }
  }, [filteredChars, groupBy])

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

  const hasFilter = searchQ.trim() !== '' || roleFilter !== 'all' || statusFilter !== 'all' || tierFilter !== 'all'

  return (
    <div className="flex h-full">
      {/* 左栏：人物列表 */}
      <div className="w-60 border-r border-gray-100 bg-white flex flex-col shrink-0">

        {/* 顶栏 */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">人物库</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              {hasFilter ? `${filteredChars.length}/` : ''}{characters.length} 人
            </span>
            <button onClick={handleCreate} disabled={creating} className="text-amber-500 hover:text-amber-600 disabled:opacity-50">
              <Plus size={16} />
            </button>
          </div>
        </div>

        {/* 搜索框 */}
        <div className="px-3 pt-2.5 pb-1.5 shrink-0">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              placeholder="搜索姓名、势力…"
              className="w-full pl-7 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:bg-white transition-colors"
            />
            {searchQ && (
              <button onClick={() => setSearchQ('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
            )}
          </div>
        </div>

        {/* 分组切换 */}
        <div className="px-3 pb-1.5 shrink-0">
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => setGroupBy('role')}
              className={clsx('flex-1 flex items-center justify-center gap-1 text-[10px] py-1 rounded-md font-medium transition-colors',
                groupBy === 'role' ? 'bg-white text-amber-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
              <Crown size={9} />按角色
            </button>
            <button
              onClick={() => setGroupBy('faction')}
              className={clsx('flex-1 flex items-center justify-center gap-1 text-[10px] py-1 rounded-md font-medium transition-colors',
                groupBy === 'faction' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
              <Users size={9} />按势力
            </button>
          </div>
        </div>

        {/* 角色筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <div className="flex gap-1 flex-wrap">
            {ROLE_CHIPS.map(chip => (
              <button key={chip.key} onClick={() => setRoleFilter(chip.key)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  roleFilter === chip.key
                    ? chip.key === 'all' ? 'bg-gray-700 text-white border-gray-700'
                      : ROLE_META[chip.key as keyof typeof ROLE_META]?.color + ' border-current'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* 状态筛选 */}
        <div className="px-3 pb-1 shrink-0">
          <div className="flex gap-1 flex-wrap">
            {STATUS_CHIPS.map(chip => (
              <button key={chip.key} onClick={() => setStatusFilter(chip.key)}
                className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                  statusFilter === chip.key
                    ? 'bg-gray-700 text-white border-gray-700'
                    : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                {chip.key !== 'all' && (
                  <span className={clsx('inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle',
                    STATUS_META[chip.key]?.dot ?? 'bg-gray-400')} />
                )}
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* 叙事层级筛选 */}
        <div className="px-3 pb-2 shrink-0">
          <div className="text-[9px] font-semibold text-gray-400 uppercase tracking-wider mb-1">叙事层级</div>
          <div className="flex gap-1 flex-wrap">
            {TIER_CHIPS.map(chip => {
              const tm = TIER_META[chip.key as string]
              return (
                <button key={chip.key} onClick={() => setTierFilter(chip.key)}
                  className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium transition-colors',
                    tierFilter === chip.key
                      ? chip.key === 'all'
                        ? 'bg-gray-700 text-white border-gray-700'
                        : tm.color + ' shadow-sm'
                      : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400')}>
                  {tm && chip.key !== 'all' && (
                    <span className={clsx('inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle', tm.dot)} />
                  )}
                  {chip.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-auto border-t border-gray-100">
          {groups.length > 0 ? groups.map(group => (
            <div key={group.key} className="mb-1">
              <div className="px-3 pt-2 pb-1 flex items-center gap-1.5">
                <span className={clsx('text-[10px] font-semibold px-1.5 py-0.5 rounded-full border', group.color)}>
                  {group.label}
                </span>
                <span className="text-[10px] text-gray-400">{group.chars.length}</span>
              </div>
              {group.chars.map(c => {
                const sm = STATUS_META[c.current_status ?? 'alive'] ?? STATUS_META.alive
                const rm = ROLE_META[c.role as keyof typeof ROLE_META] ?? ROLE_META.supporting
                return (
                  <button key={c.id} onClick={() => setSelected(c)}
                    className={clsx('w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors border-l-2',
                      selected?.id === c.id ? 'bg-amber-50 border-l-amber-400' : 'border-l-transparent hover:bg-gray-50')}>
                    <div className="relative shrink-0">
                      <div className={clsx('w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold',
                        c.role === 'protagonist' ? 'bg-gradient-to-br from-amber-300 to-amber-500'
                        : c.role === 'antagonist' ? 'bg-gradient-to-br from-red-300 to-red-500'
                        : 'bg-gradient-to-br from-gray-300 to-gray-400')}>
                        {c.name[0]}
                      </div>
                      <span className={clsx('absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border-2 border-white', sm.dot)} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="text-xs font-medium text-gray-800 truncate">{c.name}</span>
                        {groupBy === 'faction' && c.role && (
                          <span className={clsx('shrink-0 text-[9px] px-1 rounded border', rm.color)}>{rm.label}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {/* 叙事层级 badge */}
                        {(() => {
                          const tier = c.character_tier ?? 'core'
                          const tm = TIER_META[tier]
                          return tm ? (
                            <span className={clsx('shrink-0 text-[9px] px-1 py-px rounded border leading-tight font-medium', tm.color)}>
                              {tm.short}
                            </span>
                          ) : null
                        })()}
                        <span className="text-[10px] text-gray-400 truncate">
                          {groupBy === 'role'
                            ? (c.current_realm ?? c.faction ?? c.current_location ?? c.gender ?? '')
                            : (c.current_realm ?? c.faction_rank ?? c.gender ?? '')}
                        </span>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )) : (
            <div className="py-10 text-center">
              {characters.length === 0
                ? <p className="text-xs text-gray-400 px-4">暂无人物，点击 + 创建</p>
                : <p className="text-xs text-gray-400 px-4">无匹配人物<br /><button onClick={() => { setSearchQ(''); setRoleFilter('all'); setStatusFilter('all'); setTierFilter('all') }} className="mt-1 text-amber-500 hover:underline">清除筛选</button></p>
              }
            </div>
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
