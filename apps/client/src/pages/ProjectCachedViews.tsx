import React, { Suspense, lazy, useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import PageSpinner from '../components/common/PageSpinner'

const OutlinePage = lazy(() => import('./OutlinePage'))
const WritePage = lazy(() => import('./WritePage'))
const DabaiWritePage = lazy(() => import('./DabaiWritePage'))
const CharactersPage = lazy(() => import('./CharactersPage'))
const SettingsPage = lazy(() => import('./SettingsPage'))
const MemoryPage = lazy(() => import('./MemoryPage'))
const WorldBuildingPage = lazy(() => import('./WorldBuildingPage'))
const CluesPage = lazy(() => import('./CluesPage'))
const RhythmMapPage = lazy(() => import('./RhythmMapPage'))
const ReaderPromisesPage = lazy(() => import('./ReaderPromisesPage'))
const GlobalTimelinePage = lazy(() => import('./GlobalTimelinePage'))
const PowerTimelinePage = lazy(() => import('./PowerTimelinePage'))
const StorylineWeavePage = lazy(() => import('./StorylineWeavePage'))
const RelationsGraphPage = lazy(() => import('./RelationsGraphPage'))

const TABS = ['outline', 'write', 'dabai-write', 'characters', 'relations', 'worldbuilding', 'settings', 'timeline', 'powercurve', 'storyweave', 'memory', 'clues', 'rhythmmap', 'promises'] as const
type Tab = (typeof TABS)[number]

const TAB_PAGES: Record<Tab, React.LazyExoticComponent<() => JSX.Element>> = {
  outline: OutlinePage,
  write: WritePage,
  'dabai-write': DabaiWritePage,
  characters: CharactersPage,
  relations: RelationsGraphPage,
  worldbuilding: WorldBuildingPage,
  settings: SettingsPage,
  memory: MemoryPage,
  clues: CluesPage,
  rhythmmap: RhythmMapPage,
  promises: ReaderPromisesPage,
  timeline: GlobalTimelinePage,
  powercurve: PowerTimelinePage,
  storyweave: StorylineWeavePage,
}

function isTab(s: string | undefined): s is Tab {
  return !!s && (TABS as readonly string[]).includes(s)
}

/**
 * 项目内大纲 / 写作等 Tab：切换路由时不卸载已访问过的页面，保留本地状态并避免重复整页加载。
 * 各 Tab 按路由懒加载 chunk，首次进入才下载对应页面（含 TipTap / 关系图等重型依赖）。
 */
export default function ProjectCachedViews() {
  const { projectId, tab } = useParams<{ projectId: string; tab: string }>()
  const [mounted, setMounted] = useState<Partial<Record<Tab, boolean>>>({})

  useEffect(() => {
    setMounted({})
  }, [projectId])

  useEffect(() => {
    if (!isTab(tab)) return
    setMounted(m => (m[tab] ? m : { ...m, [tab]: true }))
  }, [tab, projectId])

  if (!isTab(tab)) {
    return <Navigate to={`/project/${projectId}/outline`} replace />
  }

  const wrap = (key: Tab) => {
    if (!mounted[key]) return null
    const Page = TAB_PAGES[key]
    return (
      <div
        key={key}
        className={clsx('h-full min-h-0', tab !== key && 'hidden')}
        aria-hidden={tab !== key}
      >
        <Suspense fallback={<PageSpinner />}>
          <Page />
        </Suspense>
      </div>
    )
  }

  return (
    <div className="h-full min-h-0">
      {TABS.map(t => wrap(t))}
    </div>
  )
}
