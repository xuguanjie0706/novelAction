/**
 * 人物名册（左栏）—— 按「作家视角」分组（主角/感情线/反派/导师·盟友/配角）的可点击列表。
 * 每行给出快速线索：境界、对主角态度色点、持有资产数；选中态高亮。
 */
import clsx from 'clsx'
import { Package } from 'lucide-react'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../../types/dabaiLab'
import {
  ROLE_GROUPS, GROUP_ACCENT, classifyRole, attitudeClass,
  charName, field, resolveDebutChapter, resolveDisplayRealm, type DabaiChar,
} from './charMeta'

interface Props {
  characters: DabaiChar[]
  assets: DabaiLabAsset[]
  relations: DabaiLabRelation[]
  selected: string
  onSelect: (name: string) => void
  meta?: Record<string, unknown>
}

export default function CharacterRoster({ characters, assets, relations, selected, onSelect, meta }: Props) {
  // 预聚合：每人持有资产数 / 对主角态度。
  const assetCount = (name: string) => assets.filter(a => a.owner === name && a.status === 'active').length
  const attitudeOf = (name: string) => relations.find(r => r.to_name === name)?.attitude ?? null

  // 分组（保留组内原始顺序）。
  const grouped = ROLE_GROUPS.map(g => ({
    ...g,
    members: characters.filter(c => classifyRole(field(c, 'role')) === g.key),
  })).filter(g => g.members.length > 0)

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-gray-100 bg-white/70 sm:w-72">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-bold text-gray-900">人物名册</h3>
        <p className="mt-0.5 text-[11px] text-gray-400">共 {characters.length} 人 · 点击查看人物档案</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {grouped.map(g => {
          const accent = GROUP_ACCENT[g.key]
          return (
            <div key={g.key} className="mb-3">
              <div className="flex items-center gap-1.5 px-2 py-1">
                <span className={clsx('h-1.5 w-1.5 rounded-full', accent.dot)} />
                <span className="text-[11px] font-semibold text-gray-500">{g.label}</span>
                <span className="text-[10px] text-gray-300">{g.members.length}</span>
              </div>
              <ul className="space-y-0.5">
                {g.members.map((c, i) => {
                  const name = charName(c)
                  const active = name === selected
                  const realm = resolveDisplayRealm(c, meta)
                  const debut = resolveDebutChapter(c)
                  const attitude = attitudeOf(name)
                  const owned = assetCount(name)
                  return (
                    <li key={`${name}-${i}`}>
                      <button
                        type="button"
                        onClick={() => onSelect(name)}
                        className={clsx(
                          'group relative flex w-full items-center gap-2 rounded-lg py-1.5 pl-3 pr-2 text-left transition',
                          active ? 'bg-rose-50' : 'hover:bg-gray-50',
                        )}
                      >
                        <span className={clsx(
                          'absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full',
                          active ? accent.bar : 'bg-transparent',
                        )} />
                        <span className={clsx(
                          'truncate text-sm',
                          active ? 'font-semibold text-gray-900' : 'text-gray-700',
                        )}>
                          {name}
                        </span>
                        <span className="ml-auto flex shrink-0 items-center gap-1.5">
                          {debut != null ? (
                            <span className="text-[10px] text-indigo-400/80">第{debut}章</span>
                          ) : null}
                          {realm ? <span className="text-[10px] text-gray-300">{realm}</span> : null}
                          {owned > 0 ? (
                            <span className="flex items-center gap-0.5 text-[10px] text-gray-300">
                              <Package size={10} />{owned}
                            </span>
                          ) : null}
                          {attitude ? (
                            <span className={clsx('h-2 w-2 rounded-full', attitudeClass(attitude))} title={`对主角：${attitude}`} />
                          ) : null}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}
