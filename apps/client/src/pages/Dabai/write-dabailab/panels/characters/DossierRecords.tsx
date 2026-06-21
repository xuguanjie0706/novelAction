/**
 * 动态记录区块构建器 —— 成长路线 / 道具功法 / 关系网，随写章复盘增长。
 * 关系网节点可点击跳转到对应人物。供瀑布流铺平展开。
 */
import clsx from 'clsx'
import { ChevronRight, TrendingUp, Package, Users } from 'lucide-react'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../../types/dabaiLab'
import {
  GROUP_ACCENT, classifyRole, attitudeClass, buildGrowth, charName, field,
  isProtagonist, resolveDisplayRealm, resolveRealmChapter,
  KIND_LABELS, KIND_BADGE, STATUS_LABELS, Chip,
  type DabaiChar, type DossierSection,
} from './charMeta'

const DOT: Record<string, string> = { realm: 'bg-rose-400', asset: 'bg-amber-400', relation: 'bg-sky-400' }

interface Args {
  character: DabaiChar
  characters: DabaiChar[]
  assets: DabaiLabAsset[]
  relation: DabaiLabRelation | null
  relations: DabaiLabRelation[]
  onSelect: (name: string) => void
  meta?: Record<string, unknown>
}

function growthBody(character: DabaiChar, assets: DabaiLabAsset[], relation: DabaiLabRelation | null, meta?: Record<string, unknown>) {
  const startRealm = field(character, 'start_realm')
  const currentRealm = isProtagonist(character) ? resolveDisplayRealm(character, meta) : null
  const events = buildGrowth(
    startRealm,
    assets,
    relation,
    currentRealm,
    isProtagonist(character) ? resolveRealmChapter(meta) : null,
  )
  if (events.length === 0) return <p className="py-1 text-sm text-gray-400">暂无 —— 随写章复盘记录境界突破、获得物与关系变化。</p>
  return (
    <ol className="relative ml-1 space-y-3 border-l-2 border-gray-100 pl-4">
      {events.map((g, i) => (
        <li key={i} className="relative">
          <span className={clsx('absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-white', DOT[g.kind])} />
          <div className="flex items-baseline gap-2">
            <span className="shrink-0 text-[11px] font-medium text-gray-400">{g.chapter && g.chapter > 0 ? `第${g.chapter}章` : '开局'}</span>
            <span className="text-[13px] leading-relaxed text-gray-700">{g.text}</span>
          </div>
        </li>
      ))}
    </ol>
  )
}

function itemsBody(assets: DabaiLabAsset[]) {
  if (assets.length === 0) return <p className="py-1 text-sm text-gray-400">暂无 —— 写章复盘后自动记录该角色的获得物。</p>
  return (
    <ul className="space-y-2.5">
      {assets.map(a => (
        <li key={a.id} className="rounded-lg border border-gray-100 p-3">
          <div className="flex items-center gap-2">
            <Chip className={clsx('ring-1', KIND_BADGE[a.kind] ?? 'bg-gray-100 text-gray-500')}>{KIND_LABELS[a.kind] ?? a.kind}</Chip>
            <span className={clsx('text-sm font-semibold', a.status === 'active' ? 'text-gray-900' : 'text-gray-400 line-through')}>{a.name}</span>
            <Chip className={clsx('ml-auto', a.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400')}>{STATUS_LABELS[a.status] ?? a.status}</Chip>
          </div>
          {a.description ? <p className="mt-1.5 text-[13px] leading-relaxed text-gray-600">{a.description}</p> : null}
          <p className="mt-1.5 text-[11px] text-gray-400">
            {a.acquired_chapter ? `第${a.acquired_chapter}章获得` : '开局自带'}
            {a.status !== 'active' && a.status_chapter ? ` · 第${a.status_chapter}章${STATUS_LABELS[a.status] ?? a.status}` : ''}
          </p>
        </li>
      ))}
    </ul>
  )
}

function relationsBody({ character, characters, relations, onSelect }: Args) {
  const name = charName(character)
  const isLead = classifyRole(field(character, 'role')) === 'lead'
  const edges = isLead
    ? relations.filter(r => r.from_name === name).map(r => ({ r, other: r.to_name }))
    : relations.filter(r => r.to_name === name).map(r => ({ r, other: r.from_name }))
  if (edges.length === 0) return <p className="py-1 text-sm text-gray-400">暂无登记的关系 —— 开局自动派生，复盘追踪变化。</p>
  return (
    <ul className="space-y-2">
      {edges.map(({ r, other }) => {
        const linked = characters.find(c => charName(c) === other)
        const accent = GROUP_ACCENT[linked ? classifyRole(field(linked, 'role')) : 'support']
        return (
          <li key={r.id}>
            <button
              type="button"
              disabled={!linked}
              onClick={() => linked && onSelect(other)}
              className={clsx('flex w-full items-center gap-3 rounded-lg border border-gray-100 p-2.5 text-left', linked ? 'hover:border-gray-200 hover:bg-gray-50' : 'cursor-default')}
            >
              <span className={clsx('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-semibold text-white', accent.solid)}>{other.slice(0, 1)}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-gray-900">{other}</span>
                  {r.attitude ? <Chip className={attitudeClass(r.attitude)}>{r.attitude}</Chip> : null}
                </div>
                {r.note ? <p className="mt-0.5 truncate text-xs text-gray-500">{r.note}</p> : null}
              </div>
              {linked ? <ChevronRight size={16} className="shrink-0 text-gray-300" /> : null}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function recordSections(args: Args): DossierSection[] {
  return [
    { key: 'growth', title: '成长路线', icon: <TrendingUp size={13} />, body: growthBody(args.character, args.assets, args.relation, args.meta) },
    { key: 'items', title: '道具 · 功法', icon: <Package size={13} />, body: itemsBody(args.assets) },
    { key: 'rels', title: '关系网', icon: <Users size={13} />, body: relationsBody(args) },
  ]
}
