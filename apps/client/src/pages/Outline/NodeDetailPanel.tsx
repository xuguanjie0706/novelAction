/**
 * @file 大纲节点详情侧栏
 */
import { useEffect, useState, useMemo } from 'react'
import {
  Pencil, Check, X, Users, TrendingUp, GitBranch, Target,
  Zap, Clock,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { outlineApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { OutlineNode, OutlinePlanQualityReport } from '../../types'
import OutlinePlanQualityView from '../../components/Outline/OutlinePlanQualityView'
import OutlineAIPanel from '../../components/Outline/OutlineAIPanel'
import ScenePanel from '../../components/Outline/ScenePanel'
import VolumeLinterPanel, { type LinterIssueRow } from '../../components/Outline/VolumeLinterPanel'
import {
  ChapterLinterBadgeTrigger,
  ChapterLinterIssuePanel,
} from '../../components/Outline/ChapterLinterBadge'
import { Field } from './shared/Field'
import {
  VolumeDirectorPanel,
  volumeDirectorFormFromNode,
  buildVolumeDirectorSavePayload,
  type VolumeDirectorForm,
} from '../../components/Outline/VolumeDirectorView'

export default function NodeDetailPanel({
  node, projectId, onOpenChapter, onSaved, onAICommitDone, onJumpToChapterPlan, onQualityCheck,
  onRelintDone, onRequestRepairFromLinter, onForceAccept, initialTab,
}: {
  node: OutlineNode
  projectId: string
  onOpenChapter: () => void
  onSaved: (updated: OutlineNode) => void
  onAICommitDone: () => void
  onJumpToChapterPlan: (chapterNumber: number) => void
  onQualityCheck: () => void
  onRelintDone?: () => void
  onRequestRepairFromLinter?: (mustFixChapters: number[]) => void
  /**
   * 绕过质量门控直接采用草稿。
   * 由父层（OutlinePage）调用 API 清除 linter_blocked 并刷新。
   */
  onForceAccept?: () => void
  /**
   * 节点切换后自动激活的初始 Tab（默认 'overview'）。
   * 展开章纲完成后父层传 'quality' 可直接跳到质检结果。
   */
  initialTab?: 'overview' | 'quality' | 'chapters' | 'chapter' | 'scene' | 'ai'
}) {
  const { characters, storyLines } = useAppStore()
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'quality' | 'chapters' | 'chapter' | 'scene' | 'ai'>('overview')
  /** 章节清单 Tab 中展开 linter 详情的章号（1-based） */
  const [expandedLintChapter, setExpandedLintChapter] = useState<number | null>(null)
  const [volumeForm, setVolumeForm] = useState<VolumeDirectorForm>(() => volumeDirectorFormFromNode(node))
  const [form, setForm] = useState({
    title: node.title ?? '',
    summary: node.summary ?? '',
    hook: node.hook ?? '',
    highlight: node.highlight ?? '',
    conflict: node.conflict ?? '',
    // v2 新增字段（章节节点）
    power_milestone: node.power_milestone ?? '',
    emotional_tone: node.emotional_tone ?? '',
    involved_character_ids: (node.involved_character_ids ?? []).map(String),
    storyline_ids: (node.storyline_ids ?? []).map(String),
    // P2 新增
    pov_character_id: node.pov_character_id ?? undefined,
    character_screen_time: node.character_screen_time ?? {},
  })

  useEffect(() => {
    // 兼容旧的 'linter' initialTab 值：统一映射到合并后的 'quality' tab
    const resolved = (initialTab === ('linter' as string)) ? 'quality' : (initialTab ?? 'overview')
    setActiveTab(resolved as 'overview' | 'quality' | 'chapters' | 'chapter' | 'scene' | 'ai')
    // 重置表单（包含 P2 新字段）
    setVolumeForm(volumeDirectorFormFromNode(node))
    setForm({
      title: node.title ?? '',
      summary: node.summary ?? '',
      hook: node.hook ?? '',
      highlight: node.highlight ?? '',
      conflict: node.conflict ?? '',
      power_milestone: node.power_milestone ?? '',
      emotional_tone: node.emotional_tone ?? '',
      involved_character_ids: (node.involved_character_ids ?? []).map(String),
      storyline_ids: (node.storyline_ids ?? []).map(String),
      pov_character_id: node.pov_character_id ?? undefined,
      character_screen_time: node.character_screen_time ?? {},
    })
  }, [node.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      let payload: Record<string, any>
      if (node.node_type === 'volume') {
        payload = buildVolumeDirectorSavePayload(node, volumeForm)
      } else {
        payload = {
          title: form.title,
          summary: form.summary,
          hook: form.hook,
          highlight: form.highlight,
          conflict: form.conflict,
        }
      }
      // 章节节点才传新字段，避免干扰卷节点
      if (node.node_type === 'chapter_plan') {
        payload.power_milestone = form.power_milestone || null
        payload.emotional_tone = form.emotional_tone || null
        payload.involved_character_ids = form.involved_character_ids
        payload.storyline_ids = form.storyline_ids
        // P2 新增
        payload.pov_character_id = form.pov_character_id || null
        payload.character_screen_time = form.character_screen_time || {}
      }
      const res = await outlineApi.update(projectId, node.id, payload)
      onSaved(res.data)
      setEditing(false)
      toast.success('保存成功')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const isExpandable = node.node_type === 'volume' || node.node_type === 'arc'

  const volumeOutlineQuality = isExpandable
    ? (node.extra?.outline_quality as OutlinePlanQualityReport | undefined)
    : undefined

  // 卷节点的直属章节计划子节点（已按 sort_order 排序）
  const chapterChildren = useMemo(() =>
    isExpandable
      ? [...(node.children ?? [])].sort((a, b) => a.sort_order - b.sort_order)
      : [],
    [node.id, node.children, isExpandable],
  )

  // 按章节编号索引 linter issues（章节清单徽章悬停/展开）
  const linterIssuesByChapter = useMemo(() => {
    const issues = (node.extra?.linter_issues as LinterIssueRow[] | undefined) ?? []
    const map = new Map<number, LinterIssueRow[]>()
    for (const issue of issues) {
      const ch = issue.chapter_number_in_volume
      if (!ch) continue
      const list = map.get(ch) ?? []
      list.push(issue)
      map.set(ch, list)
    }
    return map
  }, [node.extra?.linter_issues])

  useEffect(() => {
    setExpandedLintChapter(null)
  }, [node.id])

  const tabs = [
    { key: 'overview' as const, label: '基础' },
    ...(node.node_type === 'chapter_plan' ? [{ key: 'chapter' as const, label: '章节要素' }] : []),
    ...(node.node_type === 'chapter_plan' ? [{ key: 'scene' as const, label: '分场蓝图' }] : []),
    // 卷节点：章节清单 + 合并质检
    ...(isExpandable && chapterChildren.length > 0
      ? [{ key: 'chapters' as const, label: `章节（${chapterChildren.length}）` }]
      : []),
    ...(isExpandable ? [{ key: 'quality' as const, label: '质检' }] : []),
    ...(isExpandable ? [{ key: 'ai' as const, label: 'AI 展开' }] : []),
  ]

  const toggleCharacter = (id: string) => {
    setForm(f => ({
      ...f,
      involved_character_ids: f.involved_character_ids.includes(id)
        ? f.involved_character_ids.filter(x => x !== id)
        : [...f.involved_character_ids, id],
    }))
  }

  const toggleStoryline = (id: string) => {
    setForm(f => ({
      ...f,
      storyline_ids: f.storyline_ids.includes(id)
        ? f.storyline_ids.filter(x => x !== id)
        : [...f.storyline_ids, id],
    }))
  }

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded font-medium',
            node.node_type === 'volume' ? 'bg-amber-100 text-amber-700' :
            node.node_type === 'arc'    ? 'bg-blue-100 text-blue-700' :
                                          'bg-gray-100 text-gray-600'
          )}>
            {{ volume: '卷', arc: '旧篇', chapter_plan: '章' }[node.node_type]}
          </span>
          <h3 className="font-semibold text-gray-800 text-base truncate max-w-xs">
            {editing ? '编辑节点' : node.title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {!editing && isExpandable && Boolean(node.extra?.linter_blocked) && (
            <span className="text-[10px] px-2 py-1 rounded border border-amber-200 bg-amber-50 text-amber-700">
              草稿待确认
            </span>
          )}
          {editing ? (
            <>
              <button onClick={() => setEditing(false)} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-500 hover:bg-gray-100 border border-gray-200">
                <X size={12} />取消
              </button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-60">
                <Check size={12} />{saving ? '保存中…' : '保存'}
              </button>
            </>
          ) : (
            <button onClick={() => setEditing(true)} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-500 hover:bg-gray-100 border border-gray-200">
              <Pencil size={12} />编辑
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 border-b border-gray-100 mb-5 overflow-x-auto">
        {tabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'px-3 py-2 text-xs font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              activeTab === tab.key
                ? 'border-amber-500 text-amber-700'
                : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── 章节清单 Tab ── */}
      {activeTab === 'chapters' && isExpandable && (
        <div className="space-y-1.5">
          {chapterChildren.length === 0 ? (
            <div className="border border-dashed border-gray-200 rounded-lg px-4 py-8 text-sm text-gray-400 text-center">
              该卷还没有章节计划。点击「AI 展开」生成章节大纲。
            </div>
          ) : (
            <div className="space-y-1 max-h-[calc(100vh-280px)] overflow-y-auto pr-0.5">
              {chapterChildren.map((ch, idx) => {
                const chNum = idx + 1
                const chapterLintIssues = linterIssuesByChapter.get(chNum) ?? []
                const extra = ch.extra ?? {}
                const hasFaceSlap = Boolean(extra.has_face_slap)
                const pacing = extra.pacing as string | undefined
                const choiceCost = (extra.choice_cost as string | undefined) ?? ''
                const lintExpanded = expandedLintChapter === chNum
                return (
                  <button
                    key={ch.id}
                    type="button"
                    onClick={() => onJumpToChapterPlan(chNum)}
                    className="w-full text-left rounded-lg border border-gray-100 bg-white hover:bg-amber-50/50 hover:border-amber-200 transition-colors px-3 py-2.5 group"
                  >
                    <div className="flex gap-2.5">
                      <span className="flex h-5 w-7 shrink-0 items-center justify-center text-[10px] font-mono tabular-nums text-gray-400 leading-none">
                        {String(chNum).padStart(2, '0')}
                      </span>

                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="flex-1 min-w-0 text-xs font-medium text-gray-800 group-hover:text-amber-800 truncate leading-5">
                            {ch.title || `第${chNum}章`}
                          </span>
                          <div className="flex shrink-0 items-center gap-1.5">
                            {pacing && pacing !== 'normal' && (
                              <span className={clsx(
                                'inline-flex h-[1.125rem] items-center text-[10px] px-1.5 rounded border whitespace-nowrap',
                                pacing === 'climax' ? 'border-red-200 text-red-600 bg-red-50' :
                                pacing === 'fast'   ? 'border-orange-200 text-orange-600 bg-orange-50' :
                                pacing === 'slow'   ? 'border-blue-200 text-blue-600 bg-blue-50' :
                                                      'border-gray-200 text-gray-500',
                              )}>
                                {pacing}
                              </span>
                            )}
                            {hasFaceSlap && (
                              <span className="inline-flex h-[1.125rem] items-center gap-0.5 text-[10px] px-1.5 rounded border border-amber-200 text-amber-600 bg-amber-50 whitespace-nowrap">
                                <Zap size={8} />爽
                              </span>
                            )}
                            {chapterLintIssues.length > 0 && (
                              <ChapterLinterBadgeTrigger
                                issues={chapterLintIssues}
                                expanded={lintExpanded}
                                onToggle={() => setExpandedLintChapter(
                                  lintExpanded ? null : chNum,
                                )}
                              />
                            )}
                            {ch.expected_words != null && ch.expected_words > 0 && (
                              <span className="inline-flex h-[1.125rem] items-center gap-0.5 text-[10px] text-gray-400 whitespace-nowrap tabular-nums">
                                <Clock size={9} className="shrink-0" />
                                {ch.expected_words}字
                              </span>
                            )}
                          </div>
                        </div>

                        {lintExpanded && chapterLintIssues.length > 0 && (
                          <ChapterLinterIssuePanel issues={chapterLintIssues} />
                        )}
                        {ch.summary && (
                          <p className="text-[11px] text-gray-500 leading-snug line-clamp-2">
                            {ch.summary}
                          </p>
                        )}
                        {choiceCost && (
                          <p className="text-[10px] text-indigo-500 leading-snug truncate">
                            ↳ 代价：{choiceCost}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* 「质检」Tab：linter 规则检测（上） + AI 叙事质检（下），合并展示避免重复 */}

      {activeTab === 'overview' && node.node_type === 'volume' && (
        <VolumeDirectorPanel
          node={node}
          editing={editing}
          form={volumeForm}
          setForm={setVolumeForm}
        />
      )}

      {activeTab === 'overview' && node.node_type !== 'volume' && (
      <div className="space-y-4">
        <Field label="标题" value={form.title} editing={editing} onChange={v => setForm(f => ({ ...f, title: v }))} singleLine />
        <Field label="情节摘要" sublabel="删掉会损失什么" value={form.summary} editing={editing} onChange={v => setForm(f => ({ ...f, summary: v }))} />
        <Field label="钩子 / 悬念" sublabel="读者最想知道答案的核心问题" value={form.hook} editing={editing} onChange={v => setForm(f => ({ ...f, hook: v }))} />
        <Field label="燃点 / 高潮" sublabel="情绪最高点" value={form.highlight} editing={editing} onChange={v => setForm(f => ({ ...f, highlight: v }))} />
        <Field label="核心冲突" sublabel="不可调和的矛盾" value={form.conflict} editing={editing} onChange={v => setForm(f => ({ ...f, conflict: v }))} />
      </div>
      )}

      {activeTab === 'chapter' && node.node_type === 'chapter_plan' && (
        <div className="space-y-4">
          {/* 实力里程碑 */}
            <div>
              <div className="flex items-baseline gap-2 mb-1">
                <TrendingUp size={12} className="text-indigo-400 shrink-0 mt-0.5" />
                <label className="text-xs font-medium text-gray-600">实力里程碑</label>
                <span className="text-[10px] text-gray-400">本章境界突破或关键技能习得</span>
              </div>
              {editing ? (
                <input
                  value={form.power_milestone}
                  onChange={e => setForm(f => ({ ...f, power_milestone: e.target.value }))}
                  placeholder="例：林默突破炼气九层，踏入筑基"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
                />
              ) : (
                <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50">
                  {form.power_milestone || <span className="text-gray-400 italic">—</span>}
                </div>
              )}
            </div>

          {/* 情感基调 */}
            <div>
              <div className="flex items-baseline gap-2 mb-1">
                <label className="text-xs font-medium text-gray-600">情感基调</label>
                <span className="text-[10px] text-gray-400">本章整体氛围</span>
              </div>
              {editing ? (
                <input
                  value={form.emotional_tone}
                  onChange={e => setForm(f => ({ ...f, emotional_tone: e.target.value }))}
                  placeholder="例：压抑→绝地反杀→爽快，或：温情、紧张悬疑……"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
                />
              ) : (
                <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50">
                  {form.emotional_tone || <span className="text-gray-400 italic">—</span>}
                </div>
              )}
            </div>

          {/* 出场人物 */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Users size={12} className="text-blue-400 shrink-0" />
                <label className="text-xs font-medium text-gray-600">出场人物</label>
                <span className="text-[10px] text-gray-400">
                  {editing ? '点击选择/取消' : `${form.involved_character_ids.length} 位`}
                </span>
              </div>
              {characters.length === 0 ? (
                <p className="text-xs text-gray-400 italic">暂无人物数据，请先在「人物」页创建</p>
              ) : editing ? (
                <div className="flex flex-wrap gap-1.5">
                  {characters.map(c => {
                    const selected = form.involved_character_ids.includes(String(c.id))
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => toggleCharacter(String(c.id))}
                        className={clsx(
                          'text-xs px-2.5 py-1 rounded-full border transition-all',
                          selected
                            ? 'bg-blue-500 border-blue-500 text-white'
                            : 'border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-600',
                        )}
                      >
                        {c.name}
                        {c.current_realm && <span className="ml-1 opacity-70 text-[10px]">{c.current_realm}</span>}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {form.involved_character_ids.length === 0 ? (
                    <span className="text-xs text-gray-400 italic">—</span>
                  ) : (
                    form.involved_character_ids.map(id => {
                      const c = characters.find(x => String(x.id) === id)
                      return c ? (
                        <span key={id} className="text-xs px-2.5 py-1 rounded-full bg-blue-50 border border-blue-100 text-blue-700">
                          {c.name}
                          {c.current_realm && <span className="ml-1 opacity-60">{c.current_realm}</span>}
                        </span>
                      ) : null
                    })
                  )}
                </div>
              )}
            </div>

          {/* P2 新增：主要 POV */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Users size={12} className="text-purple-500 shrink-0" />
              <label className="text-xs font-medium text-gray-600">主要 POV</label>
              <span className="text-[10px] text-gray-400">本章强制视点角色</span>
            </div>
            {editing ? (
              <div className="flex flex-wrap gap-1.5">
                {characters.map(c => {
                  const selected = form.pov_character_id === String(c.id)
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, pov_character_id: selected ? undefined : String(c.id) }))}
                      className={clsx(
                        'text-xs px-2.5 py-1 rounded-full border transition-all',
                        selected
                          ? 'bg-purple-500 border-purple-500 text-white'
                          : 'border-gray-200 text-gray-600 hover:border-purple-300 hover:text-purple-600',
                      )}
                    >
                      {c.name}
                      {c.current_realm && <span className="ml-1 opacity-70 text-[10px]">{c.current_realm}</span>}
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm">
                {form.pov_character_id ? (
                  (() => {
                    const povChar = characters.find(x => String(x.id) === form.pov_character_id)
                    return povChar ? (
                      <span className="px-2.5 py-1 rounded-full bg-purple-50 border border-purple-200 text-purple-700 text-xs">
                        {povChar.name}
                      </span>
                    ) : <span className="text-gray-400 italic">—</span>
                  })()
                ) : (
                  <span className="text-xs text-gray-400 italic">未指定（默认全知）</span>
                )}
              </div>
            )}
          </div>

          {/* P2 新增：戏份预算 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Target size={12} className="text-orange-500 shrink-0" />
              <label className="text-xs font-medium text-gray-600">戏份预算</label>
              <span className="text-[10px] text-gray-400">各角色本章出镜占比</span>
            </div>
            {editing ? (
              <div className="space-y-2 text-sm">
                {characters.map(c => {
                  const pct = (form.character_screen_time as any)?.[String(c.id)] ?? 0
                  return (
                    <div key={c.id} className="flex items-center gap-3">
                      <div className="w-20 truncate text-gray-600">{c.name}</div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={5}
                        value={pct}
                        onChange={e => {
                          const val = parseInt(e.target.value)
                          setForm(f => ({
                            ...f,
                            character_screen_time: {
                              ...(f.character_screen_time as any),
                              [String(c.id)]: val
                            }
                          }))
                        }}
                        className="flex-1"
                      />
                      <div className="w-10 text-right text-gray-600">{pct}%</div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm space-y-1">
                {form.character_screen_time && Object.keys(form.character_screen_time).length > 0 ? (
                  Object.entries(form.character_screen_time as Record<string, number>).map(([id, pct]) => {
                    const c = characters.find(x => String(x.id) === id)
                    return c ? (
                      <div key={id} className="flex items-center gap-2 text-xs">
                        <span className="text-gray-600 w-16 truncate">{c.name}</span>
                        <div className="flex-1 h-1.5 bg-gray-200 rounded">
                          <div className="h-1.5 bg-orange-400 rounded" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="w-8 text-right text-gray-600">{pct}%</span>
                      </div>
                    ) : null
                  })
                ) : (
                  <span className="text-xs text-gray-400 italic">未设置戏份预算</span>
                )}
              </div>
            )}
          </div>

          {/* 关联故事线 */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <GitBranch size={12} className="text-green-500 shrink-0" />
                <label className="text-xs font-medium text-gray-600">关联故事线</label>
                <span className="text-[10px] text-gray-400">
                  {editing ? '本章推进了哪些故事线' : `${form.storyline_ids.length} 条`}
                </span>
              </div>
              {storyLines.length === 0 ? (
                <p className="text-xs text-gray-400 italic">暂无故事线，请先在「世界」→「故事线」中创建</p>
              ) : editing ? (
                <div className="flex flex-wrap gap-1.5">
                  {storyLines.map(sl => {
                    const selected = form.storyline_ids.includes(String(sl.id))
                    return (
                      <button
                        key={sl.id}
                        type="button"
                        onClick={() => toggleStoryline(String(sl.id))}
                        className={clsx(
                          'text-xs px-2.5 py-1 rounded-full border transition-all',
                          selected
                            ? 'bg-green-500 border-green-500 text-white'
                            : 'border-gray-200 text-gray-600 hover:border-green-300 hover:text-green-700',
                        )}
                      >
                        {sl.name}
                        <span className="ml-1 opacity-70 text-[10px]">
                          {sl.line_type === 'main' ? '主线' : sl.line_type === 'romance' ? '感情' : sl.line_type === 'growth' ? '成长' : sl.line_type}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {form.storyline_ids.length === 0 ? (
                    <span className="text-xs text-gray-400 italic">—</span>
                  ) : (
                    form.storyline_ids.map(id => {
                      const sl = storyLines.find(x => String(x.id) === id)
                      return sl ? (
                        <span key={id} className="text-xs px-2.5 py-1 rounded-full bg-green-50 border border-green-100 text-green-700">
                          {sl.name}
                        </span>
                      ) : null
                    })
                  )}
                </div>
              )}
            </div>
        </div>
      )}

      {activeTab === 'quality' && isExpandable && (
        <div className="space-y-5">
          {/* ── 规则检测（linter）—— 快速、确定性 ── */}
          <section>
            <h4 className="text-xs font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              规则检测（Linter）
            </h4>
            <VolumeLinterPanel
              volumeNode={node}
              projectId={projectId}
              onRelintDone={onRelintDone}
              onRequestRepair={onRequestRepairFromLinter}
              onForceAccept={onForceAccept}
            />
          </section>

          {/* ── AI 叙事质检 —— 深度评分 ── */}
          <section className="border-t border-gray-100 pt-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block" />
                AI 叙事质检
              </h4>
              <button
                onClick={onQualityCheck}
                className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 border border-indigo-100"
              >
                <Check size={12} />运行质检
              </button>
            </div>
            {volumeOutlineQuality && typeof volumeOutlineQuality === 'object' ? (
              <OutlinePlanQualityView report={volumeOutlineQuality} onChapterClick={onJumpToChapterPlan} />
            ) : (
              <div className="border border-dashed border-indigo-200 bg-indigo-50/40 rounded-lg px-4 py-5 text-xs text-indigo-700">
                尚无 AI 质检报告。点击「运行质检」生成深度叙事评分。
              </div>
            )}
          </section>
        </div>
      )}

      {activeTab === 'ai' && isExpandable && (
        <OutlineAIPanel node={node} projectId={projectId} onCommitDone={onAICommitDone} />
      )}

      {activeTab === 'scene' && node.node_type === 'chapter_plan' && (
        <ScenePanel
          projectId={projectId}
          outlineNodeId={node.id}
          nodeTitle={node.title ?? ''}
          nodeSummary={node.summary ?? ''}
        />
      )}

      {activeTab === 'overview' && node.node_type === 'chapter_plan' && (
        <button onClick={onOpenChapter} className="mt-5 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm rounded-lg">
          打开并切换到该章节
        </button>
      )}
    </div>
  )
}
