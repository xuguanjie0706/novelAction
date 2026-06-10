/**
 * 写作工作区 — 对齐 DabaiWriteWorkspace：工具栏 + 节拍卡片 + 正文区，
 * 右侧随章侧栏（预警/质检/记忆，WorkspaceSidePanel）。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Loader2, PenLine, Sparkles } from 'lucide-react'
import DabaiChapterBeatCard from '../../../components/Dabai/DabaiChapterBeatCard'
import WorkspaceSidePanel from './side/WorkspaceSidePanel'
import type { PreWarnLive } from './side/PreWarnCard'
import { dabaiDraftStream } from '../../../api/dabai'
import type { DabaiChapter } from '../../../types/dabai'
import type { DabaiBeatDisplay } from '../../../utils/dabaiOutlineDisplay'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../store'

interface Props {
  projectId: string
  mock: boolean
  chapter: DabaiChapter
  beat: DabaiBeatDisplay
  onSaved: () => void
}

export default function WriteDabailabWorkspace({ projectId, mock, chapter, beat, onSaved }: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [text, setText] = useState(chapter.content ?? '')
  const [busy, setBusy] = useState(false)
  const [preWarnLive, setPreWarnLive] = useState<PreWarnLive | null>(null)
  const [preWarnRefreshKey, setPreWarnRefreshKey] = useState(0)
  const [qualityRefreshKey, setQualityRefreshKey] = useState(0)
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0)

  useEffect(() => {
    setText(chapter.content ?? '')
    setPreWarnLive(null)
  }, [chapter.id, chapter.content])

  const generate = async () => {
    if (!chapter.id) return
    setBusy(true)
    setText('')
    let acc = ''
    try {
      await dabaiDraftStream(
        projectId,
        chapter.id,
        {
          mock,
          model_profile: modelProfileFromRoute(aiBackendRoute),
          ...(llmProviderIdFromRoute(aiBackendRoute)
            ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
            : {}),
        },
        ev => {
          if (ev.event === 'chunk') {
            acc += ev.delta
            setText(acc)
          } else if (ev.event === 'pre_warn_running') {
            setPreWarnLive({ running: true })
          } else if (ev.event === 'pre_warn_done') {
            setPreWarnLive({ running: false, error: ev.error })
            setPreWarnRefreshKey(k => k + 1)
          } else if (ev.event === 'done') {
            toast.success(`已生成 ${ev.word_count} 字`)
            onSaved()
          } else if (ev.event === 'quality_done') {
            setQualityRefreshKey(k => k + 1)
            if (ev.ok) toast.success(`自动质检完成：${ev.overall_score ?? '—'} 分`)
            else toast.error(`自动质检失败：${ev.error ?? ''}`)
          } else if (ev.event === 'debrief_done') {
            setMemoryRefreshKey(k => k + 1)
            if (ev.ok) toast.success(`自动复盘完成：${ev.memory_count ?? 0} 条记忆`)
            else toast.error(`自动复盘失败：${ev.error ?? ''}`)
          } else if (ev.event === 'error') {
            toast.error(ev.message)
          }
        },
      )
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '失败')
    } finally {
      setBusy(false)
    }
  }

  const wordCount = text.length

  return (
    <div className="flex h-full min-w-0 flex-1 bg-white">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-4 py-2.5">
        <PenLine size={16} className="shrink-0 text-rose-500" />
        <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-gray-900">
          第{chapter.chapter_number}章 {chapter.title}
        </h1>
        <span className="text-xs tabular-nums text-gray-400">{wordCount.toLocaleString()} 字</span>
        {beat.expectedWords ? (
          <span className="text-[10px] text-gray-400">目标 ~{beat.expectedWords}</span>
        ) : null}
        <button
          type="button"
          disabled={busy}
          onClick={() => void generate()}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white',
            busy ? 'bg-rose-300' : 'bg-rose-500 hover:bg-rose-600',
          )}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {wordCount > 0 ? '按要素重写' : '按要素生成'}
        </button>
      </div>

        <div className="flex-1 overflow-auto">
          <div className="mx-auto max-w-4xl space-y-4 px-4 py-4">
            <DabaiChapterBeatCard
              beat={beat}
              variant="embedded"
              className="rounded-xl border border-rose-100 bg-rose-50/30 p-4"
            />
            {busy && !text ? (
              <p className="text-sm text-gray-400">生成中…</p>
            ) : (
              <article className="whitespace-pre-wrap text-[15px] leading-8 text-gray-800">
                {text || '（待生成正文）'}
              </article>
            )}
          </div>
        </div>
      </div>

      <WorkspaceSidePanel
        projectId={projectId}
        mock={mock}
        chapter={chapter}
        preWarnLive={preWarnLive}
        preWarnRefreshKey={preWarnRefreshKey}
        qualityRefreshKey={qualityRefreshKey}
        memoryRefreshKey={memoryRefreshKey}
      />
    </div>
  )
}
