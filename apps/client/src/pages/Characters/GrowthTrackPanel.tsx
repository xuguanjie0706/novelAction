/**
 * @file 成长轨迹 Tab：左列弧线规划（arc_stages）· 右列境界实证（growth-timeline + 复盘）
 */
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import clsx from 'clsx'
import { Compass, TrendingUp } from 'lucide-react'
import type { Character } from '../../types'
import { Field, TArea, type CharacterGrowthTimelinePayload } from './shared/components'
import type { DebriefRealmMilestone } from './shared/debriefMilestones'
import { DebriefRealmTimeline, GrowthTimelineEmptyState } from './shared/DebriefRealmTimeline'
import {
  EMPTY_PLANNED_STAGE,
  mergeArcStages,
  splitArcStages,
  type ArcStageItem,
} from './shared/arcStageUtils'

function RealmMilestoneList({
  milestones,
}: {
  milestones: Array<{
    chapter_number: number
    chapter_title?: string
    realm_name: string
    realm_rank?: number
    character_change?: string
    source?: string
  }>
}) {
  if (milestones.length === 0) return null
  return (
    <ul className="space-y-2 max-h-[min(420px,50vh)] overflow-y-auto pr-0.5">
      {milestones.map((m, i) => (
        <li
          key={`${m.chapter_number}-${m.realm_name}-${i}`}
          className="text-xs border border-slate-200 rounded-md bg-white p-2.5"
        >
          <div className="font-medium text-slate-800 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>
              第{m.chapter_number}章
              {m.chapter_title ? `《${m.chapter_title}》` : ''}
              <span className="text-violet-700 ml-1">→ {m.realm_name}</span>
              {m.realm_rank != null && (
                <span className="text-slate-400 font-normal ml-1">(rank {m.realm_rank})</span>
              )}
            </span>
            {(m.source === 'debrief' || m.source === 'outline' || m.source === 'changelog') && (
              <span
                className={clsx(
                  'text-[10px] px-1.5 py-0.5 rounded border font-medium',
                  m.source === 'debrief'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                    : m.source === 'changelog'
                      ? 'bg-amber-50 text-amber-800 border-amber-200'
                      : 'bg-slate-100 text-slate-600 border-slate-200',
                )}
              >
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
  )
}

function PlannedStageCard({
  stage,
  idx,
  onChange,
  onRemove,
}: {
  stage: ArcStageItem
  idx: number
  onChange: (next: ArcStageItem) => void
  onRemove: () => void
}) {
  return (
    <div className="flex gap-3 p-3 rounded-lg border bg-amber-50 border-amber-100">
      <div className="w-5 h-5 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center shrink-0 mt-0.5 font-bold">
        {idx + 1}
      </div>
      <div className="flex-1 grid grid-cols-2 gap-2 min-w-0">
        <input
          value={stage.stage ?? ''}
          placeholder="阶段名（如：蛰伏期）"
          onChange={(e) => onChange({ ...stage, stage: e.target.value })}
          className="col-span-2 text-sm font-medium bg-transparent border-0 focus:outline-none text-gray-800 border-b border-amber-200 pb-1"
        />
        <input
          value={stage.realm ?? ''}
          placeholder="目标境界（规划）"
          onChange={(e) => onChange({ ...stage, realm: e.target.value })}
          className="text-xs text-amber-700 bg-transparent border-0 focus:outline-none"
        />
        <input
          value={stage.chapter_range ?? ''}
          placeholder="章节范围 (如 1-30)"
          onChange={(e) => onChange({ ...stage, chapter_range: e.target.value })}
          className="text-xs text-gray-400 bg-transparent border-0 focus:outline-none"
        />
        <input
          value={stage.state ?? ''}
          placeholder="人物状态 / 弧线要点"
          onChange={(e) => onChange({ ...stage, state: e.target.value })}
          className="col-span-2 text-xs text-gray-500 bg-transparent border-0 focus:outline-none"
        />
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="text-gray-300 hover:text-red-400 shrink-0 self-start"
        aria-label="删除阶段"
      >
        ✕
      </button>
    </div>
  )
}

export function GrowthTrackPanel({
  charName,
  currentRealm,
  form,
  setForm,
  realmTimeline,
  realmTimelineLoading,
  debriefMilestones,
  saveBtn,
}: {
  charName: string
  currentRealm?: string | null
  form: Character
  setForm: Dispatch<SetStateAction<Character>>
  realmTimeline: CharacterGrowthTimelinePayload | null
  realmTimelineLoading: boolean
  debriefMilestones: DebriefRealmMilestone[]
  saveBtn: ReactNode
}) {
  const { planned, completed } = splitArcStages(form.arc_stages)
  const setPlanned = (next: ArcStageItem[]) => {
    setForm((p) => ({ ...p, arc_stages: mergeArcStages(next, completed) }))
  }

  const apiMilestones = realmTimeline?.milestones ?? []
  const seenChapters = new Set(apiMilestones.map((m) => m.chapter_number))
  const extraDebrief = debriefMilestones.filter((m) => !seenChapters.has(m.chapter_number))
  const ladderItems = [
    ...apiMilestones.map((m) => ({
      chapter_number: m.chapter_number,
      chapter_title: m.chapter_title,
      realm_name: m.realm_name,
      realm_rank: m.realm_rank,
      character_change: m.character_change,
      source: m.source,
    })),
    ...extraDebrief.map((m) => ({
      chapter_number: m.chapter_number,
      chapter_title: m.chapter_title,
      realm_name: m.realm_name,
      realm_rank: m.realm_rank ?? undefined,
      source: 'debrief' as const,
    })),
  ].sort((a, b) => a.chapter_number - b.chapter_number)

  const ladderEmpty =
    !realmTimelineLoading
    && ladderItems.length === 0
    && (realmTimeline?.chapter_plans_scanned ?? 0) === 0
    && (realmTimeline?.debrief_snapshots ?? 0) === 0
    && (realmTimeline?.changelog_entries ?? 0) === 0
    && debriefMilestones.length === 0

  return (
    <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
      <div>
        <div className="text-sm font-semibold text-gray-800">成长轨迹</div>
        <p className="text-[11px] text-slate-500 mt-1">
          左列为 Bootstrap/人工规划的弧线阶段；右列为大纲、复盘与变更记录汇总的<strong>真实境界阶梯</strong>（只读）。
        </p>
      </div>

      <Field label="人物弧线（整体描述）">
        <TArea
          value={form.arc ?? ''}
          onChange={(v) => setForm((p) => ({ ...p, arc: v }))}
          rows={2}
          placeholder="从开始到结局，这个人物会经历怎样的转变？"
        />
      </Field>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {/* 左列：结构化成长阶段 */}
        <section className="rounded-xl border border-amber-200/80 bg-amber-50/30 flex flex-col min-h-[280px]">
          <header className="px-4 py-3 border-b border-amber-100 flex items-start gap-2">
            <Compass size={16} className="text-amber-600 shrink-0 mt-0.5" />
            <div>
              <div className="text-xs font-semibold text-amber-900">结构化成长阶段</div>
              <div className="text-[10px] text-amber-700/90 mt-0.5">弧线规划 · 可编辑 · Bootstrap 生成</div>
            </div>
          </header>
          <div className="p-4 flex-1 flex flex-col gap-2">
            {planned.length === 0 ? (
              <p className="text-xs text-amber-800/70">暂无规划阶段；点击下方添加，或在全书生成时由 Step 5 写入。</p>
            ) : (
              planned.map((stage, idx) => (
                <PlannedStageCard
                  key={idx}
                  stage={stage}
                  idx={idx}
                  onChange={(next) => {
                    const copy = [...planned]
                    copy[idx] = next
                    setPlanned(copy)
                  }}
                  onRemove={() => setPlanned(planned.filter((_, i) => i !== idx))}
                />
              ))
            )}
            <button
              type="button"
              onClick={() => setPlanned([...planned, { ...EMPTY_PLANNED_STAGE }])}
              className="w-full py-2 border border-dashed border-amber-300 text-amber-600 text-xs rounded-lg hover:bg-amber-50/80 transition-colors mt-1"
            >
              + 添加规划阶段
            </button>
            {completed.length > 0 && (
              <p className="text-[10px] text-slate-500 mt-2 pt-2 border-t border-amber-100">
                另有 {completed.length} 条复盘实证已归入右列「境界阶梯」，不在此编辑。
              </p>
            )}
          </div>
        </section>

        {/* 右列：真实成长阶梯 */}
        <section className="rounded-xl border border-violet-200/80 bg-violet-50/20 flex flex-col min-h-[280px]">
          <header className="px-4 py-3 border-b border-violet-100 flex items-start justify-between gap-2">
            <div className="flex items-start gap-2 min-w-0">
              <TrendingUp size={16} className="text-violet-600 shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-semibold text-violet-900">境界成长阶梯</div>
                <div className="text-[10px] text-violet-700/90 mt-0.5">实证时间轴 · 只读</div>
              </div>
            </div>
            {currentRealm && (
              <span className="text-[10px] font-medium text-violet-800 bg-white/80 border border-violet-200 px-2 py-0.5 rounded-full shrink-0">
                当前：{currentRealm}
              </span>
            )}
          </header>
          <div className="p-4 flex-1 flex flex-col gap-2 text-xs">
            <p className="text-[10px] text-slate-500">
              大纲人物变化 / 实力里程碑 + 复盘 + 变更记录
              {typeof realmTimeline?.debrief_snapshots === 'number' && realmTimeline.debrief_snapshots > 0
                ? ` · 复盘 ${realmTimeline.debrief_snapshots}`
                : ''}
              {typeof realmTimeline?.changelog_entries === 'number' && realmTimeline.changelog_entries > 0
                ? ` · 变更 ${realmTimeline.changelog_entries}`
                : ''}
            </p>

            {realmTimelineLoading && <p className="text-slate-500">加载中…</p>}

            {!realmTimelineLoading && ladderEmpty && (
              <GrowthTimelineEmptyState
                debriefCount={debriefMilestones.length}
                hasWhitelist={realmTimeline?.has_realm_whitelist}
                charName={charName}
              />
            )}

            {!realmTimelineLoading && !ladderEmpty && ladderItems.length === 0 && debriefMilestones.length > 0 && (
              <>
                <GrowthTimelineEmptyState
                  debriefCount={debriefMilestones.length}
                  hasWhitelist={realmTimeline?.has_realm_whitelist}
                  charName={charName}
                />
                <DebriefRealmTimeline milestones={debriefMilestones} />
              </>
            )}

            {!realmTimelineLoading && realmTimeline && !realmTimeline.has_realm_whitelist && apiMilestones.length > 0 && (
              <p className="text-slate-600">
                未配置 levels 时 rank 主要依赖复盘/变更或境界名匹配；建议补全力量体系以便与大纲对齐。
              </p>
            )}

            {!realmTimelineLoading
              && realmTimeline?.has_realm_whitelist
              && realmTimeline.chapter_plans_scanned > 0
              && apiMilestones.length === 0
              && extraDebrief.length === 0 && (
              <p className="text-slate-600">
                已扫描 {realmTimeline.chapter_plans_scanned} 个章节计划，未解析到 {charName} 的境界提升（请在章纲「人物变化」或「实力里程碑」中写明突破且姓名共现）。
              </p>
            )}

            {!realmTimelineLoading && ladderItems.length > 0 && (
              <RealmMilestoneList milestones={ladderItems} />
            )}
          </div>
        </section>
      </div>

      {saveBtn}
    </div>
  )
}
