/**
 * 人物面板 —— 作家视角的「人物档案馆」：左栏按角色定位分组的可点击名册，
 * 右栏展示选中人物的完整小传（人设/功能/内核/语言/持有道具功法/与主角关系）。
 * 资产/关系来自 dabai_assets / dabai_relations（按 owner / to_name 人名匹配）。
 */
import { useEffect, useMemo, useState } from 'react'
import { Users } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../types/dabaiLab'
import type { DabaiProjectDetail } from '../../../../types/dabai'
import CharacterRoster from './characters/CharacterRoster'
import CharacterDossier from './characters/CharacterDossier'
import { charName, type DabaiChar } from './characters/charMeta'

interface Props {
  detail: DabaiProjectDetail
  projectId: string
}

export default function CharactersPanel({ detail, projectId }: Props) {
  const [assets, setAssets] = useState<DabaiLabAsset[]>([])
  const [relations, setRelations] = useState<DabaiLabRelation[]>([])
  const characters = detail.characters as DabaiChar[]
  const [selected, setSelected] = useState<string>(() => (characters[0] ? charName(characters[0]) : ''))

  useEffect(() => {
    let cancelled = false
    Promise.all([dabaiLabApi.listAssets(projectId), dabaiLabApi.listRelations(projectId)])
      .then(([a, r]) => {
        if (cancelled) return
        setAssets(a.data.items)
        setRelations(r.data.items)
      })
      .catch(() => { /* 台账缺失不影响人物档案 */ })
    return () => { cancelled = true }
  }, [projectId])

  const active = useMemo(
    () => characters.find(c => charName(c) === selected) ?? characters[0] ?? null,
    [characters, selected],
  )
  const activeName = active ? charName(active) : ''
  const ownedAssets = useMemo(() => assets.filter(a => a.owner === activeName), [assets, activeName])
  const activeRelation = useMemo(
    () => relations.find(r => r.to_name === activeName) ?? null,
    [relations, activeName],
  )

  if (!characters.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-gray-400">
        <Users size={28} className="text-gray-200" />
        <p className="text-sm">暂无人物</p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <CharacterRoster
        characters={characters}
        assets={assets}
        relations={relations}
        selected={activeName}
        onSelect={setSelected}
        meta={detail.meta}
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {active ? (
          <CharacterDossier
            key={activeName}
            character={active}
            characters={characters}
            assets={ownedAssets}
            relation={activeRelation}
            relations={relations}
            onSelect={setSelected}
            meta={detail.meta}
          />
        ) : null}
      </div>
    </div>
  )
}
