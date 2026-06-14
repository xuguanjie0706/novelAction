/**
 * 写作工作区右侧栏 — 预警 / 分场 / 质检 / 记忆 / 档案 随章面板（可折叠）。
 * 数据均为章级：切章自动刷新；预警与分场另接收写章 SSE 实时状态。
 */
import { useState } from 'react'
import clsx from 'clsx'
import { AlertTriangle, Brain, ChevronsLeft, ChevronsRight, Clapperboard, FileText, ShieldCheck } from 'lucide-react'
import PreWarnCard, { type PreWarnLive } from './PreWarnCard'
import ScenePlanCard, { type ScenePlanLive } from './ScenePlanCard'
import QualityCard from './QualityCard'
import MemoryCard from './MemoryCard'
import ArchiveCard from './ArchiveCard'
import type { DabaiChapter } from '../../../../types/dabai'

type SideTab = 'prewarn' | 'sceneplan' | 'quality' | 'memory' | 'archive'

const TABS: { id: SideTab; icon: typeof Brain; label: string }[] = [
  { id: 'prewarn', icon: AlertTriangle, label: '预警' },
  { id: 'sceneplan', icon: Clapperboard, label: '分场' },
  { id: 'quality', icon: ShieldCheck, label: '质检' },
  { id: 'memory', icon: Brain, label: '记忆' },
  { id: 'archive', icon: FileText, label: '档案' },
]

interface Props {
  projectId: string
  chapter: DabaiChapter
  preWarnLive: PreWarnLive | null
  preWarnRefreshKey: number
  scenePlanLive: ScenePlanLive | null
  /** 分场完成后 +1，触发分场面板重拉。 */
  scenePlanRefreshKey: number
  /** 写后自动质检完成后 +1，触发质检面板重拉。 */
  qualityRefreshKey: number
  /** 写后自动复盘完成后 +1，触发记忆面板重拉。 */
  memoryRefreshKey: number
  /** 质检侧栏「填入重写指令」→ 打开重写弹窗。 */
  onApplyRewriteFromQuality?: (instruction: string) => void
  /** 质检侧栏「按本章建议重写」→ 轻量修订。 */
  onQcPatchRewrite?: () => void
  qcPatchRunning?: boolean
}

export default function WorkspaceSidePanel({
  projectId, chapter, preWarnLive, preWarnRefreshKey,
  scenePlanLive, scenePlanRefreshKey,
  qualityRefreshKey, memoryRefreshKey, onApplyRewriteFromQuality,
  onQcPatchRewrite, qcPatchRunning,
}: Props) {
  const [open, setOpen] = useState(true)
  const [tab, setTab] = useState<SideTab>('prewarn')
  const hasContent = (chapter.content?.trim().length ?? 0) > 0

  const activeLabel = TABS.find(t => t.id === tab)?.label ?? ''

  const tabButtonClass = (active: boolean) => clsx(
    'relative flex w-full items-center justify-center rounded-md p-2 transition-colors',
    active
      ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-200/80'
      : 'text-gray-400 hover:bg-gray-100/80 hover:text-gray-600',
  )

  if (!open) {
    return (
      <aside className="flex w-10 shrink-0 flex-col items-stretch gap-0.5 border-l border-gray-100 bg-gray-50/60 px-1 py-2">
        <button
          type="button"
          title="展开侧栏"
          onClick={() => setOpen(true)}
          className="mb-1 flex items-center justify-center rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <ChevronsLeft size={15} />
        </button>
        {TABS.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            title={label}
            aria-label={label}
            aria-current={tab === id ? 'page' : undefined}
            onClick={() => { setTab(id); setOpen(true) }}
            className={tabButtonClass(tab === id)}
          >
            <Icon size={16} strokeWidth={tab === id ? 2.25 : 1.75} />
          </button>
        ))}
      </aside>
    )
  }

  return (
    <aside className="flex w-80 shrink-0 border-l border-gray-100 bg-white">
      <nav
        aria-label="章级工具"
        className="flex w-11 shrink-0 flex-col items-stretch gap-0.5 border-r border-gray-100 bg-gray-50/70 px-1 py-2"
      >
        {TABS.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            title={label}
            aria-label={label}
            aria-current={tab === id ? 'page' : undefined}
            onClick={() => setTab(id)}
            className={tabButtonClass(tab === id)}
          >
            <Icon size={16} strokeWidth={tab === id ? 2.25 : 1.75} />
          </button>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5">
          <h3 className="text-sm font-semibold text-gray-900">{activeLabel}</h3>
          <button
            type="button"
            title="收起侧栏"
            onClick={() => setOpen(false)}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <ChevronsRight size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          {tab === 'prewarn' && chapter.id && (
            <PreWarnCard
              projectId={projectId}
              chapterId={chapter.id}
              chapterNumber={chapter.chapter_number}
              live={preWarnLive}
              refreshKey={preWarnRefreshKey}
            />
          )}
          {tab === 'sceneplan' && chapter.id && (
            <ScenePlanCard
              projectId={projectId}
              chapterId={chapter.id}
              live={scenePlanLive}
              refreshKey={scenePlanRefreshKey}
            />
          )}
          {tab === 'quality' && chapter.id && (
            <QualityCard
              projectId={projectId}
              chapterId={chapter.id}
              hasContent={hasContent}
              refreshKey={qualityRefreshKey}
              onApplyRewrite={onApplyRewriteFromQuality}
              onQcPatchRewrite={onQcPatchRewrite}
              qcPatchRunning={qcPatchRunning}
            />
          )}
          {tab === 'memory' && chapter.id && (
            <MemoryCard
              projectId={projectId}
              chapterId={chapter.id}
              hasContent={hasContent}
              refreshKey={memoryRefreshKey}
            />
          )}
          {tab === 'archive' && chapter.id && (
            <ArchiveCard
              projectId={projectId}
              chapterId={chapter.id}
              refreshKey={qualityRefreshKey + memoryRefreshKey}
            />
          )}
        </div>
      </div>
    </aside>
  )
}
