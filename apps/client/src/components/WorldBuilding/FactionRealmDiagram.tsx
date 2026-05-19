import type { Faction, PowerSystem } from '../../types'
import FactionRealmFlowGraph from './FactionRealmFlow/FactionRealmFlowGraph'

export interface FactionRealmDiagramProps {
  factions: Faction[]
  powerSystems: PowerSystem[]
  selectedId?: string | null
  onSelectFaction?: (faction: Faction | null) => void
}

/**
 * 势力 · 境界进阶关系图（React Flow，与人物关系图同栈）。
 */
export default function FactionRealmDiagram(props: FactionRealmDiagramProps) {
  if (props.factions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-2">
        <span className="text-3xl opacity-40">🗺️</span>
        <p>暂无势力数据，请先创建或等待 Bootstrap 生成</p>
      </div>
    )
  }

  return <FactionRealmFlowGraph {...props} />
}
