/**
 * @file 复盘境界里程碑列表（读 Character.extra，不依赖 growth-timeline 接口）
 */
import clsx from 'clsx'
import type { DebriefRealmMilestone } from './debriefMilestones'

export function DebriefRealmTimeline({
  milestones,
  emptyHint,
}: {
  milestones: DebriefRealmMilestone[]
  emptyHint?: string
}) {
  if (milestones.length === 0) {
    return (
      <p className="text-xs text-slate-500">
        {emptyHint ?? '暂无复盘记录的境界变更；写作页提交章节复盘后会写入 extra.debrief_realm_milestones。'}
      </p>
    )
  }
  return (
    <ul className="space-y-2 max-h-56 overflow-y-auto">
      {milestones.map((m) => (
        <li
          key={`${m.chapter_number}-${m.realm_name}`}
          className="text-xs border border-emerald-200 rounded-md bg-emerald-50/50 p-2.5"
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
            <span className="text-[10px] px-1.5 py-0.5 rounded border font-medium bg-emerald-100 text-emerald-800 border-emerald-200">
              复盘
            </span>
          </div>
          {m.reason && (
            <p className="mt-1.5 text-[11px] leading-5 text-slate-600">
              正文依据：{m.reason}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

/** 合并 growth-timeline 与 extra 复盘记录，按章号去重（优先保留 growth-timeline 条目） */
export function mergeGrowthMilestones(
  apiMilestones: Array<{ chapter_number: number; realm_name: string; source?: string }>,
  debriefExtra: DebriefRealmMilestone[],
) {
  const seen = new Set(apiMilestones.map((m) => m.chapter_number))
  const extraOnly = debriefExtra.filter((m) => !seen.has(m.chapter_number))
  return { apiMilestones, extraOnly, total: apiMilestones.length + extraOnly.length }
}

export function GrowthTimelineEmptyState({
  debriefCount,
  hasWhitelist,
  charName,
}: {
  debriefCount: number
  hasWhitelist?: boolean
  charName: string
}) {
  if (debriefCount > 0) {
    return (
      <p className="text-xs text-slate-600">
        已检测到 {debriefCount} 条复盘境界记录（见下方「复盘突破」）；合并时间轴接口未返回节点时仍可从列表接口
        extra 中读取。
      </p>
    )
  }
  return (
    <p className={clsx('text-xs', hasWhitelist ? 'text-slate-600' : 'text-amber-700')}>
      {hasWhitelist
        ? `尚无大纲章节计划，也未记录 ${charName} 的境界变更；在大纲「人物变化/实力里程碑」中写明其突破，或写作复盘提交后会自动累积。`
        : '尚未配置力量体系 levels；配置体系、在大纲写明境界变化或提交复盘后可在此查看。'}
    </p>
  )
}
