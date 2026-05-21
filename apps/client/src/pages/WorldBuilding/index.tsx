/**
 * @file 世界观页 — Tab 切换壳
 */
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import clsx from 'clsx'
import { SUB_TABS, type SubTab } from './config'
import StoryLinesTab from './tabs/StoryLinesTab'
import PowerSystemTab from './tabs/PowerSystemTab'
import SkillsTab from './tabs/SkillsTab'
import ItemsTab from './tabs/ItemsTab'
import FactionsTab from './tabs/FactionsTab'
import LocationsTab from './tabs/LocationsTab'

export default function WorldBuildingPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [activeTab, setActiveTab] = useState<SubTab>('storylines')

  if (!projectId) return <></>

  return (
    <div className="flex flex-col h-full">
      {/* 顶部子导航 */}
      <div className="flex items-center gap-1 px-4 py-2 bg-white border-b border-gray-100 shrink-0">
        {SUB_TABS.map(({ key, label, icon: Icon, color }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              activeTab === key
                ? 'bg-amber-50 text-amber-700 ring-1 ring-amber-200'
                : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
            )}
          >
            <Icon size={15} className={activeTab === key ? 'text-amber-600' : color} />
            {label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="flex-1 min-h-0">
        {activeTab === 'storylines' && <StoryLinesTab projectId={projectId} />}
        {activeTab === 'power'      && <PowerSystemTab projectId={projectId} />}
        {activeTab === 'skills'     && <SkillsTab projectId={projectId} />}
        {activeTab === 'items'      && <ItemsTab projectId={projectId} />}
        {activeTab === 'factions'   && <FactionsTab projectId={projectId} />}
        {activeTab === 'locations'  && <LocationsTab projectId={projectId} />}
      </div>
    </div>
  )
}
