/**
 * 人物档案 · 英雄区（通栏头部）：实心头像 + 名字 + 阵营标签 + 一句话本质，
 * 下接 4 格数据条（境界 / 阵营 / 对主角态度 / 持有资产），金手指单独做成绶带。
 * 让作家一眼读到「这是谁、现在什么状态」，无需读完整张档案。
 */
import clsx from 'clsx'
import { Sparkles } from 'lucide-react'
import type { DabaiLabRelation } from '../../../../../types/dabaiLab'
import {
  GROUP_ACCENT, ROLE_GROUPS, classifyRole, attitudeClass,
  charName, field, resolveDisplayRealm, tagline, type DabaiChar,
} from './charMeta'

interface Props {
  character: DabaiChar
  relation: DabaiLabRelation | null
  assetCount: number
  meta?: Record<string, unknown>
}

function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-gray-50 px-3 py-2">
      <div className="truncate text-[11px] text-gray-400">{label}</div>
      <div className={clsx('mt-0.5 truncate text-[15px] font-semibold text-gray-900', valueClass)}>{value}</div>
    </div>
  )
}

export default function DossierHero({ character: c, relation, assetCount, meta }: Props) {
  const name = charName(c)
  const group = classifyRole(field(c, 'role'))
  const accent = GROUP_ACCENT[group]
  const groupLabel = ROLE_GROUPS.find(g => g.key === group)?.label ?? '配角'
  const tag = tagline(c)
  const golden = field(c, 'golden_finger')
  const attitude = relation?.attitude ?? null
  const realm = resolveDisplayRealm(c, meta)
  const startRealm = field(c, 'start_realm')

  return (
    <div>
      <div className="flex items-start gap-4">
        <div className={clsx('flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-2xl font-semibold text-white', accent.solid)}>
          {name.slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold text-gray-900">{name}</h2>
            {field(c, 'role') ? (
              <span className={clsx('rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium', accent.chip)}>
                {field(c, 'role')}
              </span>
            ) : null}
          </div>
          {tag ? <p className="mt-1 text-sm leading-relaxed text-gray-500">{tag}</p> : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="境界" value={realm || '未定'} />
        <Stat label="阵营" value={groupLabel} />
        <Stat
          label="对主角"
          value={attitude ?? '—'}
          valueClass={attitude ? attitudeClass(attitude).split(' ').find(s => s.startsWith('text-')) : undefined}
        />
        <Stat label="持有资产" value={`${assetCount} 件`} />
      </div>

      {startRealm && realm && startRealm !== realm ? (
        <p className="mt-2 text-[11px] text-gray-400">开局 {startRealm} · 写作期已更新</p>
      ) : null}

      {golden ? (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5">
          <Sparkles size={15} className="mt-0.5 shrink-0 text-amber-600" />
          <p className="text-[13px] leading-relaxed text-amber-800">
            <span className="font-semibold">金手指 · </span>{golden}
          </p>
        </div>
      ) : null}
    </div>
  )
}
