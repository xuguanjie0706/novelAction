/**
 * @file components/Dabai/DabaiWritePanel.tsx — 大白文单章写作面板（模态）。
 * 左侧展示该章爽点节拍章纲，右侧流式生成 / 展示正文。简化写作链路，无质检闭环。
 * 模型/线路由 props 透传（沿用通用分支选择）。
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Loader2, PenLine, X } from 'lucide-react'
import { dabaiDraftStream } from '../../api/dabai'
import type { DabaiChapter } from '../../types/dabai'

interface Props {
  projectId: string
  chapter: DabaiChapter
  modelProfile: 'local' | 'gemini'
  llmProviderId?: string
  onClose: () => void
  onSaved: () => void
}

export default function DabaiWritePanel({
  projectId, chapter, modelProfile, llmProviderId, onClose, onSaved,
}: Props) {
  const [content, setContent] = useState(chapter.content ?? '')
  const [writing, setWriting] = useState(false)

  const onWrite = async () => {
    setWriting(true)
    setContent('')
    let acc = ''
    try {
      await dabaiDraftStream(
        projectId, chapter.id ?? '',
        { model_profile: modelProfile, ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}) },
        (ev) => {
          if (ev.event === 'chunk') { acc += ev.delta; setContent(acc) }
          else if (ev.event === 'done') { toast.success(`已生成 ${ev.word_count} 字`); onSaved() }
          else if (ev.event === 'error') toast.error(ev.message)
        },
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '写作失败')
    } finally {
      setWriting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-3">
          <PenLine size={16} className="text-amber-500" />
          <span className="font-bold text-gray-900">第{chapter.chapter_number}章 {chapter.title}</span>
          <span className="rounded-full bg-rose-50 px-2 py-0.5 text-xs text-rose-600">{chapter.shuang_type}</span>
          <button onClick={onClose} className="ml-auto rounded-lg p-1.5 text-gray-400 hover:bg-gray-100">
            <X size={18} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-0 md:grid-cols-[300px_1fr]">
          {/* 章纲 */}
          <div className="overflow-auto border-r border-gray-100 bg-gray-50/60 p-4 text-sm">
            <div className="mb-2 font-semibold text-gray-700">爽点节拍章纲</div>
            <dl className="space-y-2 text-gray-600">
              <Row k="憋屈" v={chapter.yaqu_setup} />
              <Row k="转折" v={chapter.emotion_turn} />
              <Row k="引爆" v={chapter.yinbao} />
              <Row k="爽点" v={chapter.shuang_payoff} />
              <Row k="见证者" v={(chapter.witnesses ?? []).join('、')} />
              <Row k="钩子" v={chapter.end_hook} />
            </dl>
            <button
              onClick={onWrite}
              disabled={writing}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-60"
            >
              {writing ? <Loader2 size={15} className="animate-spin" /> : <PenLine size={15} />}
              {writing ? '生成中…' : content ? '重新生成' : '生成正文'}
            </button>
            <p className="mt-2 text-xs text-gray-400">
              走所选线路（{modelProfile === 'local' ? '本地' : '远程'}）
            </p>
          </div>

          {/* 正文 */}
          <div className="min-h-0 overflow-auto p-5">
            {content ? (
              <article className="whitespace-pre-wrap text-[15px] leading-7 text-gray-800">{content}</article>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-gray-400">
                点左侧「生成正文」开始写作
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v?: string | null }) {
  if (!v) return null
  return (
    <div className="flex gap-2">
      <dt className="w-12 shrink-0 text-gray-400">{k}</dt>
      <dd>{v}</dd>
    </div>
  )
}
