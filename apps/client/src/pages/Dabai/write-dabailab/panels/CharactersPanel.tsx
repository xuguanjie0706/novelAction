/**
 * 人物面板 —— 左栏名册 · 中栏状态台账（境界+位置）· 右栏人物小传。
 */
import { useEffect, useMemo, useState } from 'react'
import { Users } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabAsset, DabaiLabMemory, DabaiLabRelation, DabaiPanelSnapshotItem } from '../../../../types/dabaiLab'
import type { DabaiProjectDetail } from '../../../../types/dabai'
import CharacterRoster from './characters/CharacterRoster'
import CharacterDossier from './characters/CharacterDossier'
import DabaiRealmLedgerColumn from './characters/DabaiRealmLedgerColumn'
import { charName, type DabaiChar } from './characters/charMeta'

interface Props {
  detail: DabaiProjectDetail
  projectId: string
}

export default function CharactersPanel({ detail, projectId }: Props) {
  const [assets, setAssets] = useState<DabaiLabAsset[]>([])
  const [relations, setRelations] = useState<DabaiLabRelation[]>([])
  const [memories, setMemories] = useState<DabaiLabMemory[]>([])
  const [panelSnapshots, setPanelSnapshots] = useState<DabaiPanelSnapshotItem[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(true)
  const characters = detail.characters as DabaiChar[]
  const [selected, setSelected] = useState<string>(() => (characters[0] ? charName(characters[0]) : ''))

  useEffect(() => {
    let cancelled = false
    setLedgerLoading(true)
    Promise.all([
      dabaiLabApi.listAssets(projectId),
      dabaiLabApi.listRelations(projectId),
      dabaiLabApi.listMemory(projectId),
      dabaiLabApi.listPanelSnapshots(projectId),
    ])
      .then(([a, r, m, p]) => {
        if (cancelled) return
        setAssets(a.data.items)
        setRelations(r.data.items)
        setMemories(m.data.items)
        setPanelSnapshots(p.data.items)
      })
      .catch(() => { /* 台账缺失不影响人物档案 */ })
      .finally(() => {
        if (!cancelled) setLedgerLoading(false)
      })
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
      <DabaiRealmLedgerColumn
        character={active}
        meta={detail.meta}
        panelSnapshots={panelSnapshots}
        memories={memories}
        loading={ledgerLoading}
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
