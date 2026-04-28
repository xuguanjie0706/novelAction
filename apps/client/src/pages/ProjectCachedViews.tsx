import React, { useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import OutlinePage from './OutlinePage'
import WritePage from './WritePage'
import CharactersPage from './CharactersPage'
import SettingsPage from './SettingsPage'
import MemoryPage from './MemoryPage'

const TABS = ['outline', 'write', 'characters', 'settings', 'memory'] as const
type Tab = (typeof TABS)[number]

function isTab(s: string | undefined): s is Tab {
  return !!s && (TABS as readonly string[]).includes(s)
}

/**
 * 项目内大纲 / 写作等 Tab：切换路由时不卸载已访问过的页面，保留本地状态并避免重复整页加载。
 * 切换项目时清空缓存，避免旧项目 UI 残留。
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

  const wrap = (key: Tab, node: React.ReactNode) =>
    mounted[key] ? (
      <div
        key={key}
        className={clsx('h-full min-h-0', tab !== key && 'hidden')}
        aria-hidden={tab !== key}
      >
        {node}
      </div>
    ) : null

  return (
    <div className="h-full min-h-0">
      {wrap('outline', <OutlinePage />)}
      {wrap('write', <WritePage />)}
      {wrap('characters', <CharactersPage />)}
      {wrap('settings', <SettingsPage />)}
      {wrap('memory', <MemoryPage />)}
    </div>
  )
}
