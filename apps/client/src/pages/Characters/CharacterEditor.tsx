/**
 * @file 人物详情编辑区（多 Tab）
 */
import { useEffect, useState } from 'react'
import {
  Trash2, FileText, Target, NotebookPen, BookOpen, Zap, Heart, TrendingUp,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { charactersApi, outlineApi, aiApi } from '../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../../store'
import type { Character, CharacterChangeLog } from '../../types'
import CharacterPortraitPanel from '../../components/Characters/CharacterPortraitPanel'
import { ChangelogTab } from './ChangelogTab'
import {
  ROLE_META, STATUS_META, TIER_META, DETAIL_TABS, type DetailTab,
} from './shared/constants'
import {
  Field, TInput, TArea, CharacterTag, InfoPanel, CharacterAvatar,
  type CharacterGrowthTimelinePayload,
} from './shared/components'
import { getDebriefRealmMilestones } from './shared/debriefMilestones'
import { DebriefRealmTimeline, GrowthTimelineEmptyState } from './shared/DebriefRealmTimeline'

export function CharacterEditor({ char, projectId, onUpdate, onDelete, batchTargets }: {
  char: Character
  projectId: string
  onUpdate: (c: Character) => void
  onDelete: (id: string) => void
  batchTargets?: Character[]
}) {
  const [form, setForm] = useState<Character>({ ...char })
  const [saving, setSaving] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('basic')
  const [realmTimeline, setRealmTimeline] = useState<CharacterGrowthTimelinePayload | null>(null)
  const [realmTimelineLoading, setRealmTimelineLoading] = useState(false)
  const [changelog, setChangelog] = useState<CharacterChangeLog[]>([])
  const [changelogLoading, setChangelogLoading] = useState(false)

  useEffect(() => { setForm({ ...char }); setDetailTab('basic') }, [char.id])

  useEffect(() => {
    setForm(prev => ({
      ...prev,
      current_realm: char.current_realm,
      current_location: char.current_location,
      current_status: char.current_status,
      arc_stages: char.arc_stages,
    }))
  }, [char.id, char.current_realm, char.current_location, char.current_status, char.arc_stages])

  useEffect(() => {
    if (detailTab !== 'changelog') return
    let cancelled = false
    setChangelogLoading(true)
    charactersApi.getChangelog(projectId, char.id)
      .then(res => { if (!cancelled) setChangelog(res.data) })
      .catch(() => { if (!cancelled) setChangelog([]) })
      .finally(() => { if (!cancelled) setChangelogLoading(false) })
    return () => { cancelled = true }
  }, [detailTab, char.id, char.current_realm, projectId])

  /** 进入实力/成长 Tab 时拉取最新人物（含复盘写入的 extra 与 arc_stages） */
  useEffect(() => {
    if (detailTab !== 'growth' && detailTab !== 'power') return
    let cancelled = false
    charactersApi.get(projectId, char.id)
      .then((res: { data: Character }) => {
        if (cancelled) return
        onUpdate(res.data)
        setForm((prev) => ({
          ...prev,
          current_realm: res.data.current_realm,
          current_location: res.data.current_location,
          current_status: res.data.current_status,
          arc_stages: res.data.arc_stages,
          extra: res.data.extra,
        }))
      })
      .catch(() => { /* 静默：保留 store 快照 */ })
    return () => { cancelled = true }
  }, [detailTab, char.id, projectId, onUpdate])

  useEffect(() => {
    if (detailTab !== 'growth') return
    let cancelled = false
    setRealmTimelineLoading(true)
    charactersApi.growthTimeline(projectId, char.id)
      .then((res) => {
        if (!cancelled) setRealmTimeline(res.data as CharacterGrowthTimelinePayload)
      })
      .catch(() => {
        if (!cancelled) setRealmTimeline(null)
      })
      .finally(() => {
        if (!cancelled) setRealmTimelineLoading(false)
      })
    return () => { cancelled = true }
  }, [detailTab, char.id, char.current_realm, projectId])

  const debriefMilestones = getDebriefRealmMilestones(char)

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
          <CharacterAvatar char={form} size="lg" />
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
            <div className="space-y-6">
              <CharacterPortraitPanel
                projectId={projectId}
                character={form}
                onUpdated={c => { setForm(c); onUpdate(c) }}
                batchTargets={batchTargets}
              />
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

              {/* P2 结构化语风指纹展示 */}
              <div className="mt-4 border-t pt-4">
                <div className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <NotebookPen size={16} /> 结构化语风指纹（AI 生成）
                </div>
                {form.speech_kit && typeof form.speech_kit === 'object' ? (
                  <div className="space-y-3 text-sm">
                    {/* 标志性词语 */}
                    {(form.speech_kit as any).signature_words?.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 mb-1">标志性词语 / 口头禅</div>
                        <div className="flex flex-wrap gap-1">
                          {(form.speech_kit as any).signature_words.map((w: string, i: number) => (
                            <span key={i} className="inline-block px-2 py-0.5 bg-amber-100 text-amber-700 rounded text-xs">{w}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 句式偏好 */}
                    {(form.speech_kit as any).sentence_length_pref && (
                      <div>
                        <div className="text-xs text-gray-500">句式偏好</div>
                        <div className="text-gray-700">{(form.speech_kit as any).sentence_length_pref}</div>
                      </div>
                    )}

                    {/* 典型台词样本 */}
                    {(form.speech_kit as any).sample_dialogues?.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 mb-1">典型台词样本</div>
                        <ul className="list-disc list-inside text-gray-600 space-y-0.5 pl-1">
                          {(form.speech_kit as any).sample_dialogues.slice(0, 4).map((d: string, i: number) => (
                            <li key={i} className="line-clamp-2">「{d}」</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* 内心独白风格 */}
                    {(form.speech_kit as any).inner_monologue_style && (
                      <div>
                        <div className="text-xs text-gray-500">内心独白风格</div>
                        <div className="text-gray-700">{(form.speech_kit as any).inner_monologue_style}</div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-gray-400">暂无结构化语风数据（生成后会自动填充）</div>
                )}
              </div>

              <SaveBtn />
            </div>
            </div>
          )}

          {detailTab === 'power' && (
            <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
              <div className="text-sm font-semibold text-gray-700">实力与体系</div>
              {debriefMilestones.length > 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-4 space-y-2">
                  <div className="text-xs font-semibold text-emerald-900">复盘境界变更（{debriefMilestones.length} 条）</div>
                  <DebriefRealmTimeline milestones={debriefMilestones} />
                </div>
              )}
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
              <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="text-xs font-semibold text-slate-700">境界时间轴（只读）· {char.name}</div>
                    <span className="text-[10px] text-slate-500 shrink-0 text-right">
                      大纲人物变化/实力里程碑 + 复盘 + 变更记录
                      {typeof realmTimeline?.debrief_snapshots === 'number' && realmTimeline.debrief_snapshots > 0
                        ? ` · 复盘 ${realmTimeline.debrief_snapshots}`
                        : ''}
                      {typeof realmTimeline?.changelog_entries === 'number' && realmTimeline.changelog_entries > 0
                        ? ` · 变更 ${realmTimeline.changelog_entries}`
                        : ''}
                    </span>
                  </div>
                  {realmTimelineLoading && (
                    <p className="text-xs text-slate-500">加载中…</p>
                  )}
                  {!realmTimelineLoading && realmTimeline
                    && (realmTimeline.milestones?.length ?? 0) === 0
                    && realmTimeline.chapter_plans_scanned === 0
                    && (realmTimeline.debrief_snapshots ?? 0) === 0
                    && (realmTimeline.changelog_entries ?? 0) === 0
                    && debriefMilestones.length === 0 && (
                    <GrowthTimelineEmptyState
                      debriefCount={0}
                      hasWhitelist={realmTimeline.has_realm_whitelist}
                      charName={char.name}
                    />
                  )}
                  {!realmTimelineLoading
                    && (realmTimeline?.milestones?.length ?? 0) === 0
                    && debriefMilestones.length > 0 && (
                    <GrowthTimelineEmptyState
                      debriefCount={debriefMilestones.length}
                      hasWhitelist={realmTimeline?.has_realm_whitelist}
                      charName={char.name}
                    />
                  )}
                  {!realmTimelineLoading && realmTimeline && !realmTimeline.has_realm_whitelist
                    && (realmTimeline.milestones?.length ?? 0) > 0 && (
                    <p className="text-xs text-slate-600">未配置 levels 时，rank 主要依赖复盘/变更记录或境界名子串匹配，建议补全力量体系以便与大纲对齐。</p>
                  )}
                  {!realmTimelineLoading && realmTimeline?.has_realm_whitelist && realmTimeline.chapter_plans_scanned > 0 && realmTimeline.milestones.length === 0 && (
                    <p className="text-xs text-slate-600">
                      已扫描 {realmTimeline.chapter_plans_scanned} 个章节计划，未解析到 {char.name} 的境界提升（请在「人物变化」或「实力里程碑」中写明突破/晋升等，且与该角色姓名共现）。
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
                            {(m.source === 'debrief' || m.source === 'outline' || m.source === 'changelog') && (
                              <span className={clsx(
                                'text-[10px] px-1.5 py-0.5 rounded border font-medium',
                                m.source === 'debrief'
                                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                  : m.source === 'changelog'
                                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                                    : 'bg-slate-100 text-slate-600 border-slate-200',
                              )}>
                                {m.source === 'debrief' ? '复盘' : m.source === 'changelog' ? '变更' : '大纲'}
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
              {debriefMilestones.length > 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-4 space-y-2">
                  <div className="text-xs font-semibold text-emerald-900">
                    复盘突破记录（来自人物列表接口 extra.debrief_realm_milestones）
                  </div>
                  <DebriefRealmTimeline milestones={debriefMilestones} />
                </div>
              )}
              <Field label="人物弧线（整体描述）">
                <TArea value={form.arc ?? ''} onChange={f('arc')} rows={3} placeholder="从开始到结局，这个人物会经历怎样的转变？" />
              </Field>
              <div>
                <div className="text-xs font-medium text-gray-500 mb-3">结构化成长阶段</div>
                <div className="space-y-2 mb-2">
                  {(form.arc_stages ?? []).map((stage: any, idx: number) => {
                    const isDebriefStage = stage.completed === true && stage.chapter_number != null
                    return (
                    <div key={idx} className={clsx(
                      'flex gap-3 p-3 rounded-lg border',
                      isDebriefStage ? 'bg-emerald-50 border-emerald-100' : 'bg-amber-50 border-amber-100',
                    )}>
                      <div className={clsx(
                        'w-5 h-5 rounded-full text-white text-xs flex items-center justify-center shrink-0 mt-0.5 font-bold',
                        isDebriefStage ? 'bg-emerald-500' : 'bg-amber-500',
                      )}>
                        {idx + 1}
                      </div>
                      <div className="flex-1 grid grid-cols-2 gap-2 min-w-0">
                        {isDebriefStage ? (
                          <>
                            <div className="col-span-2 text-sm font-medium text-gray-800">
                              {stage.stage ?? stage.realm ?? '突破'}
                              <span className="text-emerald-700 text-xs ml-2">
                                第{stage.chapter_number}章{stage.chapter_title ? ` · ${stage.chapter_title}` : ''}
                              </span>
                            </div>
                            {stage.realm && (
                              <div className="text-xs text-amber-600 col-span-2">境界：{stage.realm}</div>
                            )}
                            {stage.state && <div className="text-xs text-gray-500 col-span-2">{stage.state}</div>}
                          </>
                        ) : (
                        <>
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
                        </>
                        )}
                      </div>
                      <button onClick={() => setForm(p => ({ ...p, arc_stages: (p.arc_stages ?? []).filter((_: any, i: number) => i !== idx) }))}
                        className="text-gray-300 hover:text-red-400 shrink-0 self-start">✕</button>
                    </div>
                  )})}
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
                const [refreshedList, freshLogs] = await Promise.all([
                  charactersApi.list(projectId),
                  charactersApi.getChangelog(projectId, char.id),
                ])
                const freshChar = refreshedList.data.find((c: Character) => c.id === char.id)
                if (freshChar) onUpdate(freshChar)
                setChangelog(freshLogs.data)
                try {
                  const tl = await charactersApi.growthTimeline(projectId, char.id)
                  setRealmTimeline(tl.data as CharacterGrowthTimelinePayload)
                } catch { /* 时间轴刷新失败不阻断变更记录 */ }
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
