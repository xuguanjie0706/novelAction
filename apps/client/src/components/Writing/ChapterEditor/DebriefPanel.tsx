/**
 * DebriefPanel.tsx — 章节复盘面板
 *
 * 职责：展示并收集本章复盘信息（人物状态更新、故事线推进、资产变化、
 * 读者承诺台账、AI 建议新配角），并提供提交入口。
 * 数据来源全部通过 props 传入，AI 调用由父组件（index.tsx）驱动。
 */
import React, { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import {
  History, Users, Flag, Bot, Swords, UserPlus, CheckSquare, MapPin,
} from 'lucide-react'
import { chaptersApi } from '../../../api/client'
import type { DebriefPanelProps } from './types'

// ─── 内部常量 ────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<string, string> = {
  alive: '存活', dead: '死亡', missing: '失踪', sealed: '封印', transformed: '变异',
}

const STORYLINE_STATUS_LABEL: Record<string, string> = {
  planned: '规划中', active: '进行中', climax: '高潮', resolved: '已结局', dropped: '已废弃',
}

const DEBRIEF_APPLY_SOURCE_LABEL: Record<string, string> = {
  queue_auto: '生成队列 · 自动落库',
  manual_tab: '复盘 Tab · 手动提交',
}

const ASSET_UPDATE_LABELS: Record<string, string> = {
  new_items: '新增道具/法宝',
  item_updates: '更新道具/法宝',
  new_skills: '新增功法/技能',
  skill_updates: '更新功法/技能',
  new_factions: '新增势力',
  faction_updates: '更新势力',
}

const PROMISE_TYPE_LABEL: Record<string, string> = {
  chapter_ending: '章末悬念',
  volume_ending: '卷末钩子',
  name_implication: '名字/开篇暗示',
  chapter_comment_consensus: '章评共识',
  protagonist_claim: '主角宣言',
}

// ─── DebriefPanel ─────────────────────────────────────────────────────────────

/**
 * 章节复盘面板主组件。
 *
 * 包含：落库历史审计列表、AI 建议摘要、人物状态更新表单、
 * 故事线推进表单、资产变化勾选、读者承诺台账、新配角入库预览、
 * 操作按钮区（AI 分析 + 提交）。
 *
 * @see DebriefPanelProps 完整 props 说明
 */
export default function DebriefPanel({
  projectId,
  chapter, outlineNode, characters, storyLines,
  charUpdates, setCharUpdates,
  storylineBeats, setStorylineBeats,
  debriefNotes, setDebriefNotes,
  submitting, autoDebriefing,
  cacheHydrating = false,
  aiSuggestedCharIds = new Set(),
  aiSuggestedSlIds = new Set(),
  aiSuggestedAssetUpdates = null,
  aiNewCharacters = [],
  aiNewReaderPromises = [],
  aiFulfilledPromiseTexts = [],
  onRemoveNewPromise,
  onRemoveFulfilledPromise,
  aiSummary,
  onAutoDebrief,
  onSubmit,
  fromQueueSnapshot = false,
  debriefHistoryTick = 0,
  debriefContentReady = true,
}: DebriefPanelProps) {
  // ── 落库历史审计 ─────────────────────────────────────────────────────────

  const [applyRecords, setApplyRecords] = useState<Array<{
    id: string
    apply_source: string
    content_hash: string | null
    payload: Record<string, unknown>
    result_message: string | null
    created_at: string | null
  }>>([])
  const [applyRecordsLoading, setApplyRecordsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setApplyRecordsLoading(true)
    chaptersApi.listDebriefApplyRecords(projectId, chapter.id, 25)
      .then((r) => {
        if (!cancelled) setApplyRecords(r.data)
      })
      .catch(() => {
        if (!cancelled) setApplyRecords([])
      })
      .finally(() => {
        if (!cancelled) setApplyRecordsLoading(false)
      })
    return () => { cancelled = true }
  }, [projectId, chapter.id, debriefHistoryTick])

  // ── 出场人物 / 活跃故事线过滤 ────────────────────────────────────────────

  /** 本章出场人物：优先从大纲节点 involved_character_ids 取，否则取前 8 名 */
  const involvedIds = new Set(outlineNode?.involved_character_ids?.map(String) || [])
  const displayChars = involvedIds.size > 0
    ? characters.filter(c => involvedIds.has(String(c.id)))
    : characters.slice(0, 8)

  /** 活跃故事线（只展示 active / climax / planned） */
  const activeStorylines = storyLines.filter(s =>
    ['active', 'climax', 'planned'].includes(s.status)
  )

  // ── 表单更新 helpers ──────────────────────────────────────────────────────

  /**
   * 更新单个人物的某字段（境界/位置/状态/习得技能）。
   *
   * @param id - Character.id
   * @param field - charUpdates 的字段名
   * @param value - 新值字符串
   */
  const updateChar = (id: string, field: string, value: string) => {
    setCharUpdates(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  /**
   * 更新单条故事线的某字段（status / beat）。
   *
   * @param id - StoryLine.id
   * @param field - storylineBeats 的字段名
   * @param value - 新值字符串
   */
  const updateStoryline = (id: string, field: string, value: string) => {
    setStorylineBeats(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  // ── 资产变化勾选 ─────────────────────────────────────────────────────────

  const assetSections = useMemo(() => {
    const source = aiSuggestedAssetUpdates || {}
    return Object.entries(ASSET_UPDATE_LABELS)
      .map(([key, label]) => {
        const list = source[key]
        return {
          key,
          label,
          items: Array.isArray(list) ? list.filter(item => typeof item === 'object' && item !== null) : [],
        }
      })
      .filter(section => section.items.length > 0)
  }, [aiSuggestedAssetUpdates])

  const [assetSelections, setAssetSelections] = useState<Record<string, boolean[]>>({})

  useEffect(() => {
    const nextSelections: Record<string, boolean[]> = {}
    for (const section of assetSections) {
      nextSelections[section.key] = section.items.map(() => true)
    }
    setAssetSelections(nextSelections)
  }, [assetSections])

  const totalAssetCount = assetSections.reduce((sum, section) => sum + section.items.length, 0)
  const selectedAssetCount = assetSections.reduce((sum, section) => {
    const flags = assetSelections[section.key] || []
    return sum + flags.filter(Boolean).length
  }, 0)

  const hasAiSuggestions = aiSuggestedCharIds.size > 0 || aiSuggestedSlIds.size > 0 || totalAssetCount > 0
    || aiNewReaderPromises.length > 0 || aiFulfilledPromiseTexts.length > 0

  /**
   * 从当前勾选状态构建最终提交的 selectedAssetUpdates。
   * 只含被勾选的条目，全部未选时返回 undefined。
   */
  const buildSelectedAssetUpdates = (): Record<string, unknown> | undefined => {
    const picked: Record<string, unknown> = {}
    for (const section of assetSections) {
      const flags = assetSelections[section.key] || []
      const selectedItems = section.items.filter((_, idx) => flags[idx])
      if (selectedItems.length > 0) picked[section.key] = selectedItems
    }
    return Object.keys(picked).length > 0 ? picked : undefined
  }

  // ── 渲染 ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-4 space-y-4">

      {fromQueueSnapshot && (
        <div className="rounded-novel border border-amber-200 bg-amber-50/90 px-3 py-2 text-[10px] text-amber-900 leading-relaxed">
          <span className="font-semibold">生成队列已自动复盘并写入数据库。</span>
          以下为当时的 AI 提取快照（黄标与预填一致），便于对照；若再改正文可点「重新分析」刷新。
        </div>
      )}

      {/* 落库历史审计 */}
      <section className="rounded-novel border border-novel-border bg-novel-card/90 px-3 py-2.5 space-y-2">
        <div className="flex items-center gap-1.5">
          <History size={11} className="text-novel-ink-muted" />
          <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">复盘落库记录</span>
          {applyRecordsLoading && <span className="text-[10px] text-novel-ink-faint">加载中…</span>}
        </div>
        <p className="text-[9px] text-novel-ink-faint leading-relaxed">
          每次落库（队列自动或本页提交）都会在服务端留档：时间、来源、摘要与完整填入 JSON，便于回溯本章做过哪些复盘操作。
        </p>
        {!applyRecordsLoading && applyRecords.length === 0 && (
          <p className="text-[10px] text-novel-ink-faint italic">本章尚无落库记录。</p>
        )}
        <div className="space-y-1.5 max-h-56 overflow-y-auto">
          {applyRecords.map((r) => {
            const t = r.created_at ? r.created_at.replace('T', ' ').slice(0, 19) : '—'
            const src = DEBRIEF_APPLY_SOURCE_LABEL[r.apply_source] ?? r.apply_source
            return (
              <details
                key={r.id}
                className="rounded border border-novel-border bg-white/70 px-2 py-1.5 text-[10px] text-novel-ink"
              >
                <summary className="cursor-pointer select-none list-none flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="font-medium text-novel-ink">{t}</span>
                  <span className="text-[9px] text-novel-accent">{src}</span>
                  {r.content_hash && (
                    <span className="text-[9px] text-novel-ink-faint font-mono truncate max-w-[10rem]" title={r.content_hash}>
                      正文哈希 {r.content_hash.slice(0, 8)}…
                    </span>
                  )}
                </summary>
                {r.result_message && (
                  <p className="mt-1.5 text-[10px] text-novel-ink-muted leading-relaxed border-t border-novel-border/60 pt-1.5">
                    {r.result_message}
                  </p>
                )}
                <pre className="mt-1.5 max-h-36 overflow-auto text-[9px] leading-snug text-novel-ink-faint whitespace-pre-wrap break-words">
                  {JSON.stringify(r.payload, null, 2)}
                </pre>
              </details>
            )
          })}
        </div>
      </section>

      {!debriefContentReady && (
        <div className="rounded-novel border border-rose-200 bg-rose-50/90 px-3 py-2.5 text-[11px] text-rose-800 leading-relaxed">
          <span className="font-semibold">本章尚无已保存正文。</span>
          {' '}复盘只读取数据库中的章节内容。请先在左侧撰写并等待自动保存，或用 AI 队列生成本章后再分析。
          <span className="block mt-1 text-rose-700/90">若刚写完的是上一章（例如第22章），请切换到该章再点「AI 自动复盘」。</span>
        </div>
      )}

      {/* AI 自动分析区 */}
      {hasAiSuggestions && aiSummary ? (
        <div className="rounded-novel border border-amber-200 bg-amber-50/80 px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <Bot size={12} className="text-amber-500" />
            <span className="text-[11px] font-semibold text-amber-700">AI 已自动分析本章</span>
          </div>
          <p className="text-[11px] text-amber-800 leading-relaxed">{aiSummary}</p>
          <p className="text-[10px] text-amber-500 mt-1">
            已预填 {aiSuggestedCharIds.size} 个人物、{aiSuggestedSlIds.size} 条故事线、{totalAssetCount} 条资产变化{aiNewCharacters.length > 0 ? `、${aiNewCharacters.length} 个新配角` : ''}{aiNewReaderPromises.length > 0 ? `、${aiNewReaderPromises.length} 条新承诺` : ''}{aiFulfilledPromiseTexts.length > 0 ? `、${aiFulfilledPromiseTexts.length} 条待兑现` : ''}，请检查后提交
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-novel-ink-faint leading-relaxed">
            点击下方「AI 分析」提取变化（若此前分析过且正文未改，打开本页会自动载入缓存）；也可纯手动填写后提交
          </p>
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || !debriefContentReady}
              className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-novel border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={11} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中…' : 'AI 自动复盘'}
            </button>
          )}
        </div>
      )}

      {/* 加载中：区分「读缓存」与「AI 分析」 */}
      {cacheHydrating && (
        <div className="flex items-center justify-center gap-2 py-2 text-slate-500">
          <span className="text-xs">正在载入已保存的复盘建议…</span>
        </div>
      )}
      {autoDebriefing && (
        <div className="flex items-center justify-center gap-2 py-3 text-amber-600">
          <Bot size={14} className="animate-pulse" />
          <span className="text-xs">AI 正在读取章节并提取变化…</span>
        </div>
      )}

      {/* 人物状态更新 */}
      {displayChars.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <Users size={11} className="text-novel-ink-muted" />
            <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
              人物状态更新
            </span>
          </div>
          <div className="space-y-3">
            {displayChars.map(c => {
              const upd = charUpdates[c.id] || {}
              const hasChange = Object.values(upd).some(Boolean)
              const isAiSuggested = aiSuggestedCharIds.has(c.id)
              return (
                <div key={c.id} className={clsx(
                  'rounded-novel border px-3 py-2.5 space-y-2',
                  isAiSuggested ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                    : hasChange ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
                )}>
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full bg-novel-shell flex items-center justify-center shrink-0">
                      <span className="text-[9px] text-novel-ink-muted font-semibold">{c.name[0]}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-medium text-novel-ink">{c.name}</span>
                        {isAiSuggested && (
                          <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium">
                            <Bot size={8} />AI 建议
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {c.current_realm && (
                          <span className="text-[10px] text-novel-accent">{c.current_realm}</span>
                        )}
                        {c.current_location && (
                          <span className="text-[10px] text-novel-ink-faint">
                            <MapPin size={8} className="inline mr-0.5" />{c.current_location}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">新境界</label>
                      <input
                        type="text"
                        value={upd.current_realm || ''}
                        onChange={e => updateChar(c.id, 'current_realm', e.target.value)}
                        placeholder={c.current_realm || '不变'}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">新位置</label>
                      <input
                        type="text"
                        value={upd.current_location || ''}
                        onChange={e => updateChar(c.id, 'current_location', e.target.value)}
                        placeholder={c.current_location || '不变'}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">状态</label>
                      <select
                        value={upd.current_status || ''}
                        onChange={e => updateChar(c.id, 'current_status', e.target.value)}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      >
                        <option value="">不变（{STATUS_LABEL[c.current_status || 'alive'] || c.current_status}）</option>
                        {Object.entries(STATUS_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">习得技能</label>
                      <input
                        type="text"
                        value={upd.add_skill_name || ''}
                        onChange={e => updateChar(c.id, 'add_skill_name', e.target.value)}
                        placeholder="技能名称（可空）"
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 故事线推进 */}
      {activeStorylines.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <Swords size={11} className="text-novel-ink-muted" />
            <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
              故事线推进
            </span>
          </div>
          <div className="space-y-2">
            {activeStorylines.map(sl => {
              const upd = storylineBeats[sl.id] || {}
              const hasChange = Object.values(upd).some(Boolean)
              const isAiSuggested = aiSuggestedSlIds.has(sl.id)
              return (
                <div key={sl.id} className={clsx(
                  'rounded-novel border px-3 py-2.5 space-y-1.5',
                  isAiSuggested ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                    : hasChange ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
                )}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-medium text-novel-ink truncate">{sl.name}</span>
                      {isAiSuggested && (
                        <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium shrink-0">
                          <Bot size={8} />AI
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-novel-ink-faint shrink-0">
                      {STORYLINE_STATUS_LABEL[sl.status] || sl.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">更新状态</label>
                      <select
                        value={upd.status || ''}
                        onChange={e => updateStoryline(sl.id, 'status', e.target.value)}
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      >
                        <option value="">不变</option>
                        {Object.entries(STORYLINE_STATUS_LABEL).map(([v, l]) => (
                          <option key={v} value={v}>{l}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[9px] text-novel-ink-faint block mb-0.5">本章节拍</label>
                      <input
                        type="text"
                        value={upd.beat || ''}
                        onChange={e => updateStoryline(sl.id, 'beat', e.target.value)}
                        placeholder="发生了什么（可空）"
                        className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 资产变化（AI 建议，可勾选） */}
      {assetSections.length > 0 && (
        <section>
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-1.5">
              <Flag size={11} className="text-novel-ink-muted" />
              <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
                资产变化（可勾选提交）
              </span>
              <span className="text-[10px] text-novel-ink-faint">
                {selectedAssetCount}/{totalAssetCount}
              </span>
            </div>
            <button
              type="button"
              onClick={() => {
                const allSelected = selectedAssetCount === totalAssetCount && totalAssetCount > 0
                setAssetSelections(prev => {
                  const next = { ...prev }
                  for (const section of assetSections) {
                    next[section.key] = section.items.map(() => !allSelected)
                  }
                  return next
                })
              }}
              className="text-[10px] px-2 py-1 rounded border border-novel-border bg-white text-novel-ink-muted hover:bg-novel-panel transition-novel"
            >
              {selectedAssetCount === totalAssetCount && totalAssetCount > 0 ? '全部取消' : '全部勾选'}
            </button>
          </div>

          <div className="space-y-2.5">
            {assetSections.map(section => (
              <div key={section.key} className="rounded-novel border border-novel-border bg-novel-card px-3 py-2.5">
                <div className="text-[10px] font-semibold text-novel-ink-muted mb-1.5">{section.label}</div>
                <div className="space-y-1">
                  {section.items.map((item, idx) => {
                    const row = item as Record<string, unknown>
                    const name = String(
                      row.name
                      || row.item_name
                      || row.skill_name
                      || row.faction_name
                      || `${section.label}#${idx + 1}`,
                    )
                    const note = String(
                      row.reason_to_store
                      || row.event_note
                      || row.story_significance
                      || row.effects
                      || row.goals
                      || '',
                    )
                    const checked = assetSelections[section.key]?.[idx] ?? false
                    return (
                      <label key={`${section.key}-${idx}`} className="flex items-start gap-2 text-[11px] text-novel-ink">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={e => {
                            const { checked: nextChecked } = e.target
                            setAssetSelections(prev => {
                              const sectionFlags = [...(prev[section.key] || section.items.map(() => true))]
                              sectionFlags[idx] = nextChecked
                              return { ...prev, [section.key]: sectionFlags }
                            })
                          }}
                          className="mt-0.5"
                        />
                        <span className="leading-relaxed">
                          <span className="font-medium">{name}</span>
                          {note && <span className="text-novel-ink-faint"> · {note}</span>}
                        </span>
                      </label>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 读者承诺台账 */}
      {(aiNewReaderPromises.length > 0 || aiFulfilledPromiseTexts.length > 0) && (
        <section className="rounded-novel border border-violet-200 bg-violet-50/50 px-3 py-2.5 space-y-2">
          <span className="text-[10px] font-semibold text-violet-800 uppercase tracking-wider block">
            读者承诺台账
          </span>
          {aiNewReaderPromises.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[9px] text-violet-700/80">本章新承诺（提交后写入台账）</p>
              {aiNewReaderPromises.map((p, idx) => (
                <div
                  key={`new-promise-${idx}`}
                  className="flex items-start gap-2 text-[11px] text-violet-950 bg-white/80 rounded border border-violet-100 px-2 py-1.5"
                >
                  <span className="flex-1 leading-relaxed">
                    <span className="text-[9px] text-violet-600 mr-1">
                      {PROMISE_TYPE_LABEL[p.promise_type || ''] || p.promise_type || '承诺'}
                    </span>
                    {p.promise_text}
                    {typeof p.expected_within_chapters === 'number' && p.expected_within_chapters > 0 && (
                      <span className="text-[9px] text-violet-500 ml-1">
                        · {p.expected_within_chapters} 章内
                      </span>
                    )}
                  </span>
                  {onRemoveNewPromise && !fromQueueSnapshot && (
                    <button
                      type="button"
                      onClick={() => onRemoveNewPromise(idx)}
                      className="text-[9px] text-violet-500 hover:text-violet-800 shrink-0"
                    >
                      移除
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {aiFulfilledPromiseTexts.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[9px] text-violet-700/80">本章已兑现（提交后匹配 open 台账标 fulfilled）</p>
              {aiFulfilledPromiseTexts.map((text, idx) => (
                <div
                  key={`fulfilled-${idx}`}
                  className="flex items-start gap-2 text-[11px] text-emerald-900 bg-emerald-50/90 rounded border border-emerald-100 px-2 py-1.5"
                >
                  <span className="flex-1 leading-relaxed">{text}</span>
                  {onRemoveFulfilledPromise && !fromQueueSnapshot && (
                    <button
                      type="button"
                      onClick={() => onRemoveFulfilledPromise(idx)}
                      className="text-[9px] text-emerald-600 hover:text-emerald-900 shrink-0"
                    >
                      移除
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 作者备注 */}
      <section>
        <label className="text-[10px] font-semibold text-novel-ink-muted block mb-1.5">作者备注（可选）</label>
        <textarea
          value={debriefNotes}
          onChange={e => setDebriefNotes(e.target.value)}
          rows={2}
          placeholder="本章写作感受、待调整之处……"
          className="w-full text-[11px] border border-novel-border rounded-novel px-3 py-2 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-none"
        />
      </section>

      {/* AI 建议新配角入库 */}
      {aiNewCharacters.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <UserPlus size={11} className="text-emerald-600" />
            <span className="text-[11px] font-semibold text-novel-ink">本章新配角入库</span>
            <span className="ml-auto text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">AI 建议</span>
          </div>
          <div className="space-y-1.5">
            {aiNewCharacters.map((nc, i) => (
              <div key={i} className="rounded-novel border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-novel-ink">{nc.name}</span>
                  {nc.faction && <span className="text-emerald-700 bg-emerald-100 rounded px-1">{nc.faction}</span>}
                  {nc.current_realm && <span className="text-novel-ink-muted">{nc.current_realm}</span>}
                </div>
                {nc.personality && <p className="text-novel-ink-muted mt-0.5 leading-relaxed">{nc.personality}</p>}
                {nc.motivation && <p className="text-novel-ink-faint mt-0.5">动机：{nc.motivation}</p>}
                {nc.author_notes && <p className="text-amber-700 mt-0.5 italic">{nc.author_notes}</p>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-novel-ink-faint mt-1.5">提交后自动写入人物库</p>
        </section>
      )}

      {/* 空状态提示 */}
      {displayChars.length === 0 && activeStorylines.length === 0 && (
        <p className="text-xs text-novel-ink-faint italic text-center py-4">
          暂无人物或活跃故事线<br />
          <span className="text-[10px]">请先在「人物」和「世界」页创建数据，<br />并在大纲节点上标注本章出场人物</span>
        </p>
      )}

      {/* 操作按钮区：吸底 + 主按钮加粗阴影 */}
      <div
        className={clsx(
          'sticky bottom-0 z-10 -mx-4 mt-2 border-t border-novel-border/90 bg-novel-panel/95 backdrop-blur-sm px-4 pb-4 pt-3 shadow-[0_-8px_24px_-4px_rgba(0,0,0,0.06)]',
          hasAiSuggestions && 'ring-1 ring-inset ring-amber-200/80',
        )}
      >
        <p className="text-[10px] text-novel-ink-faint mb-2 text-center">
          {hasAiSuggestions ? '核对预填项后点击下方按钮写入数据库' : '填写或 AI 分析后，提交以同步人物 / 故事线 / 资产'}
        </p>
        <div className="flex gap-2">
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || submitting || !debriefContentReady}
              className="flex items-center justify-center gap-1.5 text-xs py-2.5 px-3 border border-amber-300 text-amber-800 bg-amber-50 hover:bg-amber-100 rounded-xl font-semibold disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={13} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中' : hasAiSuggestions ? '重新分析' : 'AI 分析'}
            </button>
          )}
          <button
            type="button"
            onClick={() => onSubmit(buildSelectedAssetUpdates())}
            disabled={submitting || autoDebriefing || cacheHydrating}
            className={clsx(
              'flex-1 flex items-center justify-center gap-2 min-h-[3rem] rounded-xl text-[15px] font-semibold text-white shadow-lg transition-all disabled:opacity-55 disabled:shadow-none active:scale-[0.99]',
              hasAiSuggestions
                ? 'bg-gradient-to-b from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 ring-2 ring-amber-300/70 shadow-amber-900/25'
                : 'bg-novel-accent hover:bg-novel-accent-hover ring-2 ring-black/10 shadow-stone-900/20',
            )}
          >
            <CheckSquare size={18} strokeWidth={2.25} className={submitting ? 'animate-pulse' : ''} />
            {submitting ? '提交中…' : hasAiSuggestions ? '确认并提交' : '提交复盘'}
          </button>
        </div>
      </div>
    </div>
  )
}
