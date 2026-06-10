/**
 * DabaiWriteWorkspace — 章节要素 + 工具栏 + 内联生成进度 + 正文编辑区 + 复盘/记忆侧栏。
 */
import { useState } from 'react'
import { EditorContent } from '@tiptap/react'
import clsx from 'clsx'
import { Brain, Loader2, PenLine, ShieldCheck, Sparkles } from 'lucide-react'
import DabaiChapterBeatCard from '../../components/Dabai/DabaiChapterBeatCard'
import DabaiConsistencyBanner from '../../components/Writing/ChapterEditor/DabaiConsistencyBanner'
import type { Chapter, OutlineNode } from '../../types'
import type { DabaiBeatDisplay } from '../../utils/dabaiOutlineDisplay'
import DabaiDebriefPanel from './DabaiDebriefPanel'
import DabaiInlineProgress from './DabaiInlineProgress'
import { useDabaiTiptapEditor } from './useDabaiTiptapEditor'
import { useDabaiWriteActions } from './useDabaiWriteActions'
import { useWritingConfigHydration } from '../../components/Writing/ChapterEditor/hooks/useWritingConfigHydration'
import { useAppStore } from '../../store'

interface Props {
  projectId: string
  chapter: Chapter
  plan?: OutlineNode
  beat: DabaiBeatDisplay | null
}

export default function DabaiWriteWorkspace({ projectId, chapter, plan, beat }: Props) {
  const upsertChapter = useAppStore(s => s.upsertChapter)
  const writingConfig = useWritingConfigHydration(projectId)
  const { editor, wordCount } = useDabaiTiptapEditor(projectId, chapter, upsertChapter)
  const { generateChapter, runConsistencyCheck, chapterBusy, checking } = useDabaiWriteActions(
    projectId,
    chapter,
    writingConfig,
  )
  const [debriefOpen, setDebriefOpen] = useState(false)

  const consistencyReport = chapter.last_quality_report as Parameters<
    typeof DabaiConsistencyBanner
  >[0]['report']

  return (
    <div className="flex h-full min-w-0">
      <div className="flex h-full min-w-0 flex-1 flex-col bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-4 py-2.5">
          <PenLine size={16} className="text-rose-500 shrink-0" />
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-gray-900">
            {chapter.title}
          </h1>
          <span className="text-xs tabular-nums text-gray-400">{wordCount.toLocaleString()} 字</span>
          {beat?.expectedWords ? (
            <span className="text-[10px] text-gray-400">目标 ~{beat.expectedWords}</span>
          ) : null}
          <button
            type="button"
            disabled={chapterBusy}
            onClick={() => generateChapter()}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white',
              chapterBusy ? 'bg-rose-300' : 'bg-rose-500 hover:bg-rose-600',
            )}
          >
            {chapterBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {chapter.word_count > 0 ? '按要素重写' : '按要素生成'}
          </button>
          <button
            type="button"
            disabled={checking}
            onClick={() => void runConsistencyCheck()}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-60"
          >
            {checking ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
            {checking ? '质检中…' : '质检'}
          </button>
          <button
            type="button"
            onClick={() => setDebriefOpen(v => !v)}
            className={clsx(
              'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs',
              debriefOpen
                ? 'border-rose-300 bg-rose-50 text-rose-700'
                : 'border-gray-200 text-gray-600 hover:bg-gray-50',
            )}
          >
            <Brain size={14} />
            复盘/记忆
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          <div className="mx-auto max-w-4xl space-y-4 px-4 py-4">
            <DabaiInlineProgress projectId={projectId} chapterId={chapter.id} />
            {beat && (
              <DabaiChapterBeatCard beat={beat} variant="embedded" className="rounded-xl border border-rose-100 bg-rose-50/30 p-4" />
            )}
            {!plan && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                本章未关联章纲节点，AI 将无法读取章节要素。
              </p>
            )}
            <DabaiConsistencyBanner report={consistencyReport} />
            {editor && <EditorContent editor={editor} />}
          </div>
        </div>
      </div>

      {debriefOpen && (
        <DabaiDebriefPanel
          projectId={projectId}
          chapter={chapter}
          onClose={() => setDebriefOpen(false)}
        />
      )}
    </div>
  )
}
