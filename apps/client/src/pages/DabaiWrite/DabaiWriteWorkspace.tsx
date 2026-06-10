/**
 * DabaiWriteWorkspace — 章节要素 + 工具栏 + 正文编辑区
 */
import { EditorContent } from '@tiptap/react'
import clsx from 'clsx'
import { Loader2, PenLine, ShieldCheck, Sparkles } from 'lucide-react'
import DabaiChapterBeatCard from '../../components/Dabai/DabaiChapterBeatCard'
import DabaiConsistencyBanner from '../../components/Writing/ChapterEditor/DabaiConsistencyBanner'
import type { Chapter, OutlineNode } from '../../types'
import type { DabaiBeatDisplay } from '../../utils/dabaiOutlineDisplay'
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
  const { generateChapter, runConsistencyCheck, chapterBusy } = useDabaiWriteActions(
    projectId,
    chapter,
    writingConfig,
  )

  const consistencyReport = chapter.last_quality_report as {
    consistency_pass?: boolean
    blockers?: { rule_id: string; message: string }[]
    warnings?: { rule_id: string; message: string }[]
  } | null

  return (
    <div className="flex h-full min-w-0 flex-col bg-white">
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
          onClick={() => void runConsistencyCheck()}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
        >
          <ShieldCheck size={14} />
          一致性校验
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-4xl space-y-4 px-4 py-4">
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
  )
}
