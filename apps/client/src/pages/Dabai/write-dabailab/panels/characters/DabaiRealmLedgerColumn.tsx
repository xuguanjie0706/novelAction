/**
 * @file dabai 人物页 · 状态中栏：境界台账 + 位置台账，点击条目查看正文依据。
 */
import { useMemo, useState, type ReactNode } from 'react'
import clsx from 'clsx'
import { ChevronDown, MapPin, Mountain } from 'lucide-react'
import type { DabaiLabMemory } from '../../../../../types/dabaiLab'
import type { DabaiPanelSnapshotItem } from '../../../../../types/dabaiLab'
import { charName, field, resolveDisplayRealm, type DabaiChar } from './charMeta'
import { buildDabaiRealmLedger, type DabaiRealmMilestone } from './realmLedgerUtils'
import {
  buildDabaiLocationLedger,
  formatLocationDisplay,
  resolveCurrentLocation,
  splitLocationLabel,
  type DabaiLocationMilestone,
} from './locationLedgerUtils'

type LedgerEntry = {
  key: string
  chapter_number: number
  from_label: string
  to_label: string
  sub_label?: string
  reason?: string | null
  source?: string
  map_name?: string | null
  place_name?: string | null
}

function sourceLabel(source?: string) {
  if (source === 'panel_snapshot') return '面板快照'
  if (source === 'memory') return '复盘记忆'
  if (source === 'meta') return '写作回写'
  return '复盘'
}

function LedgerRow({
  entry,
  tone,
  expanded,
  onToggle,
}: {
  entry: LedgerEntry
  tone: 'violet' | 'sky'
  expanded: boolean
  onToggle: () => void
}) {
  const hasReason = Boolean(entry.reason?.trim())
  const border = tone === 'violet' ? 'border-violet-100' : 'border-sky-100'
  const hover = tone === 'violet' ? 'hover:bg-violet-50/50' : 'hover:bg-sky-50/50'
  const active = tone === 'violet' ? 'bg-violet-50/70' : 'bg-sky-50/70'
  const badge = tone === 'violet'
    ? 'border-violet-200 bg-violet-50 text-violet-700'
    : 'border-sky-200 bg-sky-50 text-sky-700'
  const text = tone === 'violet' ? 'text-violet-900' : 'text-sky-900'
  const chevron = tone === 'violet' ? 'text-violet-400' : 'text-sky-400'

  return (
    <li className={clsx('overflow-hidden rounded-lg border bg-white', border)}>
      <button
        type="button"
        onClick={onToggle}
        className={clsx('flex w-full items-start gap-2 px-3 py-2.5 text-left transition-colors', expanded ? active : hover)}
      >
        <ChevronDown
          size={14}
          className={clsx('mt-0.5 shrink-0 transition-transform', chevron, expanded ? 'rotate-0' : '-rotate-90')}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-800">第{entry.chapter_number}章</span>
            <span className={clsx('rounded border px-1.5 py-0.5 text-[9px] font-medium', badge)}>
              {sourceLabel(entry.source)}
            </span>
          </div>
          <p className={clsx('text-[12px] leading-snug', text)}>
            <span className="text-slate-500">{entry.from_label}</span>
            <span className="mx-1 text-slate-300">→</span>
            <span className="font-medium">{entry.to_label}</span>
          </p>
          {entry.map_name && entry.place_name ? (
            <p className="text-[10px] text-slate-500">
              地图 {entry.map_name} · 地点 {entry.place_name}
            </p>
          ) : null}
          {entry.sub_label ? <p className="text-[10px] text-slate-400">{entry.sub_label}</p> : null}
          {!expanded && hasReason ? (
            <p className="truncate text-[10px] text-slate-400">点击查看移动依据</p>
          ) : null}
        </div>
      </button>
      {expanded && (
        <div className={clsx('border-t px-3 pb-3 pt-2 ml-5', border)}>
          <p className="text-[10px] font-medium text-slate-500">正文依据</p>
          <p className="mt-1 text-[12px] leading-5 text-slate-700 whitespace-pre-wrap">
            {hasReason ? entry.reason : '本章暂无复盘记忆中的位置/移动依据。'}
          </p>
        </div>
      )}
    </li>
  )
}

function LedgerSection({
  title,
  icon,
  tone,
  summaryLabel,
  summaryValue,
  summaryHint,
  entries,
  emptyHint,
  expandedKey,
  onToggle,
}: {
  title: string
  icon: ReactNode
  tone: 'violet' | 'sky'
  summaryLabel: string
  summaryValue: string
  summaryHint?: string
  entries: LedgerEntry[]
  emptyHint: string
  expandedKey: string | null
  onToggle: (key: string) => void
}) {
  const border = tone === 'violet' ? 'border-violet-200/60' : 'border-sky-200/60'
  const valueColor = tone === 'violet' ? 'text-violet-900' : 'text-sky-900'

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-1.5">
        {icon}
        <h4 className="text-xs font-bold text-gray-800">{title}</h4>
      </div>
      <div className={clsx('rounded-lg border bg-white/80 px-3 py-2', border)}>
        <p className="text-[10px] text-gray-400">{summaryLabel}</p>
        <p className={clsx('mt-0.5 text-sm font-semibold', valueColor)}>{summaryValue || '未定'}</p>
        {summaryHint ? <p className="mt-1 text-[10px] text-gray-400">{summaryHint}</p> : null}
      </div>
      {entries.length === 0 ? (
        <p className="rounded-lg border border-dashed border-gray-200 bg-white/60 px-3 py-3 text-center text-[11px] leading-5 text-gray-500">
          {emptyHint}
        </p>
      ) : (
        <ul className="space-y-2">
          {entries.map((entry) => (
            <LedgerRow
              key={entry.key}
              entry={entry}
              tone={tone}
              expanded={expandedKey === entry.key}
              onToggle={() => onToggle(entry.key)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function toRealmEntries(milestones: DabaiRealmMilestone[]): LedgerEntry[] {
  return milestones.map((m) => ({
    key: `realm-${m.chapter_number}-${m.chapter_id ?? ''}-${m.realm_name}`,
    chapter_number: m.chapter_number,
    from_label: m.from_realm?.trim() || '未记录',
    to_label: m.realm_name,
    sub_label: m.combat_power != null ? `战力 ${m.combat_power}` : undefined,
    reason: m.reason,
    source: m.source,
  }))
}

function toLocationEntries(milestones: DabaiLocationMilestone[]): LedgerEntry[] {
  return milestones.map((m) => {
    const to = formatLocationDisplay(m.location_name)
    const from = m.from_location ? formatLocationDisplay(m.from_location) : '未记录'
    return {
      key: `loc-${m.chapter_number}-${m.chapter_id ?? ''}-${m.location_name}`,
      chapter_number: m.chapter_number,
      from_label: from,
      to_label: to,
      map_name: m.map_name,
      place_name: m.place_name,
      reason: m.reason,
      source: m.source,
    }
  })
}

export default function DabaiRealmLedgerColumn({
  character,
  meta,
  panelSnapshots,
  memories,
  loading,
}: {
  character: DabaiChar | null
  meta?: Record<string, unknown>
  panelSnapshots: DabaiPanelSnapshotItem[]
  memories: DabaiLabMemory[]
  loading?: boolean
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const realmMilestones = useMemo(() => {
    if (!character) return []
    return buildDabaiRealmLedger(character, meta, panelSnapshots, memories)
  }, [character, meta, panelSnapshots, memories])

  const locationMilestones = useMemo(() => {
    if (!character) return []
    return buildDabaiLocationLedger(character, panelSnapshots, memories)
  }, [character, panelSnapshots, memories])

  const currentRealm = character ? resolveDisplayRealm(character, meta) : ''
  const startRealm = character ? field(character, 'start_realm') : ''
  const currentLocation = resolveCurrentLocation(panelSnapshots)
  const currentLocParts = splitLocationLabel(currentLocation)
  const name = character ? charName(character) : ''

  const toggle = (key: string) => setExpandedKey((prev) => (prev === key ? null : key))

  return (
    <div className="flex h-full w-56 shrink-0 flex-col border-r border-gray-100 bg-slate-50/40 sm:w-64">
      <div className="border-b border-gray-100 px-3 py-3">
        <h3 className="text-sm font-bold text-gray-900">状态台账</h3>
        <p className="mt-0.5 text-[10px] text-gray-500">
          {name ? `${name} · 境界 / 位置` : '选中人物后展示'}
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-2 py-2">
        {!character ? (
          <p className="px-2 py-4 text-center text-xs text-gray-400">请从左侧选择人物</p>
        ) : loading ? (
          <p className="px-2 py-4 text-center text-xs text-gray-400">加载复盘数据…</p>
        ) : (
          <>
            <LedgerSection
              title="境界"
              icon={<Mountain size={14} className="text-violet-600" />}
              tone="violet"
              summaryLabel="当前境界"
              summaryValue={currentRealm}
              summaryHint={startRealm && startRealm !== currentRealm ? `开局 ${startRealm}` : undefined}
              entries={toRealmEntries(realmMilestones)}
              emptyHint="暂无逐章境界记录；章节复盘后写入面板快照。"
              expandedKey={expandedKey}
              onToggle={toggle}
            />
            <LedgerSection
              title="位置"
              icon={<MapPin size={14} className="text-sky-600" />}
              tone="sky"
              summaryLabel="当前位置"
              summaryValue={currentLocation}
              summaryHint={
                currentLocParts.map && currentLocParts.place
                  ? `地图 ${currentLocParts.map} · 地点 ${currentLocParts.place}`
                  : undefined
              }
              entries={toLocationEntries(locationMilestones)}
              emptyHint="暂无逐章位置记录；复盘写入章末 location 后自动累积。"
              expandedKey={expandedKey}
              onToggle={toggle}
            />
          </>
        )}
      </div>
    </div>
  )
}
