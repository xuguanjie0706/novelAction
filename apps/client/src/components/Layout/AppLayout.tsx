import React, { Suspense, lazy } from 'react'
import { Outlet, useParams } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import PageSpinner from '../common/PageSpinner'
import { useAppStore } from '../../store'

const AIPanel = lazy(() => import('../AI/AIPanel'))
const GenerationQueuePanel = lazy(() => import('./GenerationQueuePanel'))

export default function AppLayout() {
  const { projectId } = useParams<{ projectId: string }>()
  const aiPanelOpen = useAppStore(s => s.aiPanelOpen)

  return (
    <div className="flex h-screen bg-[#FAF8F4] overflow-hidden">
      {/* 左侧导航栏 */}
      <Sidebar projectId={projectId!} />

      {/* 主内容区 */}
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar projectId={projectId!} />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* 右侧 AI 面板（可收起） */}
      {aiPanelOpen && (
        <Suspense
          fallback={
            <div className="w-80 shrink-0 border-l border-gray-200 bg-white flex items-center justify-center">
              <PageSpinner label="AI 面板加载中…" />
            </div>
          }
        >
          <AIPanel projectId={projectId!} />
        </Suspense>
      )}

      {/* 右下角大纲生成队列（全局悬浮，跨页面保持运行） */}
      <Suspense fallback={null}>
        <GenerationQueuePanel />
      </Suspense>
    </div>
  )
}
