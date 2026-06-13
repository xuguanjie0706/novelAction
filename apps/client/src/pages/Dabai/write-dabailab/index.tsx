import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Loader2, PenLine } from 'lucide-react'
import DabaiLabShellSidebar from './DabaiLabShellSidebar'
import DabaiLabTopBar from './DabaiLabTopBar'
import WriteDabailabSidebar from './WriteDabailabSidebar'
import WriteDabailabWorkspace from './WriteDabailabWorkspace'
import DabaiExportPanel from './DabaiExportPanel'
import VolumesPanel from './panels/VolumesPanel'
import CharactersPanel from './panels/CharactersPanel'
import WorldPanel from './panels/WorldPanel'
import LinterPanel from './panels/LinterPanel'
import MemoryLibraryPanel from './panels/MemoryLibraryPanel'
import CluesPanel from './panels/CluesPanel'
import LedgerPanel from './panels/LedgerPanel'
import ArchivePanel from './panels/ArchivePanel'
import { useWriteDabailab } from './useWriteDabailab'
import { makeRealmLabel } from './realmLabel'
import { parseWorkspaceTab } from './workspaceTab'
import { dabaiBeatFromChapter } from '../../../utils/dabaiOutlineDisplay'
import { dabaiChapterGenerateBlockReason } from './chapterGenerateGate'
import type { DabaiChapter } from '../../../types/dabai'

export default function WriteDabailabPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const [exportOpen, setExportOpen] = useState(false)
  const tab = parseWorkspaceTab(searchParams.get('tab'))
  const { loadState, detail, groups, activeChapter, activeId, setActiveId, reload, afterSave } =
    useWriteDabailab(projectId)

  const jumpToChapter = (ch: DabaiChapter) => {
    if (ch.id) setActiveId(ch.id)
    setSearchParams({}, { replace: true })
  }

  if (loadState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center gap-2 bg-[#FAF8F4] text-gray-400">
        <Loader2 className="animate-spin" size={18} />
        载入中…
      </div>
    )
  }

  if (loadState === 'error' || !detail) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[#FAF8F4]">
        <p className="text-gray-600">加载失败</p>
        <button type="button" onClick={reload} className="text-sm text-rose-600">重试</button>
        <Link to="/dabai" className="text-xs text-gray-400">返回书架</Link>
      </div>
    )
  }

  const title = detail.title || detail.logline
  const realmName = makeRealmLabel(detail)
  const chapterOutlines = detail.chapter_outlines ?? []
  const generateBlockReason = activeChapter
    ? dabaiChapterGenerateBlockReason(activeChapter, chapterOutlines)
    : null

  return (
    <>
    <div className="flex h-screen overflow-hidden bg-[#FAF8F4]">
      <DabaiLabShellSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <DabaiLabTopBar title={title} />
        <main className="min-h-0 flex-1 overflow-hidden">
          {tab === 'write' ? (
            <div className="flex h-full min-h-0">
              <WriteDabailabSidebar
                groups={groups}
                activeId={activeId}
                realmName={realmName}
                onSelect={ch => ch.id && setActiveId(ch.id)}
                projectId={projectId!}
                onExpanded={() => { activeId ? void afterSave(activeId) : reload() }}
                onExport={() => setExportOpen(true)}
              />
              {activeChapter ? (
                <WriteDabailabWorkspace
                  projectId={projectId!}
                  chapter={activeChapter}
                  beat={dabaiBeatFromChapter(activeChapter, realmName)}
                  generateBlockReason={generateBlockReason}
                  onSaved={() => void afterSave(activeChapter.id!)}
                />
              ) : (
                <div className="flex h-full flex-1 flex-col items-center justify-center gap-3 text-center text-gray-400">
                  <PenLine size={32} className="text-rose-200" />
                  <p className="text-sm">从左侧选择一章，按「章节要素」开始写作</p>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full overflow-auto">
              {tab === 'volumes' && (
                <VolumesPanel
                  detail={detail}
                  groups={groups}
                  activeId={activeId}
                  onSelectChapter={jumpToChapter}
                />
              )}
              {tab === 'characters' && <CharactersPanel detail={detail} projectId={projectId!} />}
              {tab === 'world' && <WorldPanel detail={detail} />}
              {tab === 'quality' && (
                <LinterPanel
                  report={detail.linter_report}
                  projectId={projectId!}
                  onRelinted={reload}
                />
              )}
              {tab === 'memory' && <MemoryLibraryPanel projectId={projectId!} />}
              {tab === 'clues' && <CluesPanel projectId={projectId!} />}
              {tab === 'ledger' && <LedgerPanel projectId={projectId!} />}
              {tab === 'archive' && <ArchivePanel projectId={projectId!} />}
            </div>
          )}
        </main>
      </div>
    </div>

    {exportOpen && projectId ? (
      <DabaiExportPanel projectId={projectId} onClose={() => setExportOpen(false)} />
    ) : null}
    </>
  )
}
