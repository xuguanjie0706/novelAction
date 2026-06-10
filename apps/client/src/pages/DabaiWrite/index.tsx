/**
 * 大白文专用写作页 — 章纲五拍 → 正文 → 设定一致性
 */
import { useEffect } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router-dom'
import { Loader2, PenLine } from 'lucide-react'
import { useAppStore } from '../../store'
import { isDabaiProject } from '../../utils/dabaiOutlineDisplay'
import DabaiWriteSidebar from './DabaiWriteSidebar'
import DabaiWriteWorkspace from './DabaiWriteWorkspace'
import { useDabaiWritePage } from './useDabaiWritePage'

export default function DabaiWritePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams] = useSearchParams()
  const currentProject = useAppStore(s => s.currentProject)

  const {
    loadState,
    syncing,
    unsyncedCount,
    planRows,
    activeChapter,
    activePlan,
    activeBeat,
    openPlan,
    syncAll,
    reload,
  } = useDabaiWritePage(projectId)

  const activeChapterId = useAppStore(s => s.activeChapterId)
  const setActiveChapterId = useAppStore(s => s.setActiveChapterId)
  const chapters = useAppStore(s => s.chapters)

  useEffect(() => {
    const cid = searchParams.get('chapter')
    if (!cid || loadState !== 'ready') return
    if (chapters.some(c => c.id === cid)) setActiveChapterId(cid)
  }, [searchParams, loadState, chapters, setActiveChapterId])

  if (currentProject && !isDabaiProject(currentProject.extra as Record<string, unknown>)) {
    const qs = searchParams.toString()
    return <Navigate to={`/project/${projectId}/write${qs ? `?${qs}` : ''}`} replace />
  }

  if (loadState === 'loading') {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-gray-400">
        <Loader2 className="animate-spin" size={18} />
        载入大白文写作台…
      </div>
    )
  }

  if (loadState === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-sm font-medium text-gray-700">写作台加载失败</p>
        <button
          type="button"
          onClick={reload}
          className="rounded-lg bg-rose-500 px-4 py-2 text-sm text-white hover:bg-rose-600"
        >
          重新加载
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <DabaiWriteSidebar
        planRows={planRows}
        activeChapterId={activeChapterId}
        unsyncedCount={unsyncedCount}
        syncing={syncing}
        onSelect={openPlan}
        onSyncAll={syncAll}
      />
      <div className="min-w-0 flex-1">
        {activeChapter ? (
          <DabaiWriteWorkspace
            projectId={projectId!}
            chapter={activeChapter}
            plan={activePlan}
            beat={activeBeat}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-gray-400">
            <PenLine size={32} className="text-rose-200" />
            <p className="text-sm">从左侧选择一章，按「章节要素」开始写作</p>
          </div>
        )}
      </div>
    </div>
  )
}
