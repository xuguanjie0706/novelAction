/**
 * 写作工作区 — 对齐 DabaiWriteWorkspace：工具栏 + 节拍卡片 + 正文区，
 * 右侧随章侧栏（预警/分场/质检/记忆，WorkspaceSidePanel）。
 */
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Loader2, PenLine, Save, Sparkles, Trash2 } from 'lucide-react'
import DabaiChapterBeatCard from '../../../components/Dabai/DabaiChapterBeatCard'
import DraftLaunchModal, { type DraftLaunchOptions } from './DraftLaunchModal'
import WorkspaceSidePanel from './side/WorkspaceSidePanel'
import type { PreWarnLive } from './side/PreWarnCard'
import type { ScenePlanLive } from './side/ScenePlanCard'
import { dabaiApi, dabaiDraftStream, type DabaiDraftRequest } from '../../../api/dabai'
import type { DabaiChapter } from '../../../types/dabai'
import type { DabaiBeatDisplay } from '../../../utils/dabaiOutlineDisplay'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../store'

interface Props {
  projectId: string
  chapter: DabaiChapter
  beat: DabaiBeatDisplay
  /** 首写被顺序门控阻断时的提示（重写不受限）。 */
  generateBlockReason?: string | null
  onSaved: () => void
  /** 清空本章写作产物后刷新详情。 */
  onCleared: () => void
}

export default function WriteDabailabWorkspace({
  projectId, chapter, beat, generateBlockReason, onSaved, onCleared,
}: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [text, setText] = useState(chapter.content ?? '')
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [preWarnLive, setPreWarnLive] = useState<PreWarnLive | null>(null)
  const [preWarnRefreshKey, setPreWarnRefreshKey] = useState(0)
  const [scenePlanLive, setScenePlanLive] = useState<ScenePlanLive | null>(null)
  const [scenePlanRefreshKey, setScenePlanRefreshKey] = useState(0)
  const [qualityRefreshKey, setQualityRefreshKey] = useState(0)
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0)
  const [draftModalOpen, setDraftModalOpen] = useState(false)
  const [rewritePrefill, setRewritePrefill] = useState('')
  const [draftMode, setDraftMode] = useState<'full' | 'qc_patch' | null>(null)
  const [clearing, setClearing] = useState(false)
  const regenSnapshot = useRef('')

  useEffect(() => {
    setText(chapter.content ?? '')
    setDirty(false)
    setPreWarnLive(null)
    setScenePlanLive(null)
  }, [chapter.id, chapter.content])

  const saveContent = async () => {
    if (!chapter.id || busy) return
    setSaving(true)
    try {
      const res = await dabaiApi.patchChapterContent(projectId, chapter.id, text)
      toast.success(`已保存 ${res.data.word_count} 字`)
      setDirty(false)
      onSaved()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const runStreamDraft = async (payload: DabaiDraftRequest, opts?: { skipBlockCheck?: boolean }) => {
    if (!chapter.id) return
    if (!opts?.skipBlockCheck && generateBlockReason) {
      toast.error(generateBlockReason)
      return
    }
    setDraftModalOpen(false)
    regenSnapshot.current = text
    setBusy(true)
    setDraftMode(payload.rewrite_mode === 'qc_patch' ? 'qc_patch' : 'full')
    const isQcPatch = payload.rewrite_mode === 'qc_patch'
    let acc = ''
    let gotChunk = false
    try {
      await dabaiDraftStream(
        projectId,
        chapter.id,
        {
          model_profile: modelProfileFromRoute(aiBackendRoute),
          ...(llmProviderIdFromRoute(aiBackendRoute)
            ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
            : {}),
          ...payload,
        },
        ev => {
          if (ev.event === 'chunk') {
            if (!gotChunk) {
              gotChunk = true
              setText('')
            }
            acc += ev.delta
            setText(acc)
          } else if (ev.event === 'qc_patch_running') {
            toast('按质检建议修订正文…', { icon: '✏️' })
          } else if (ev.event === 'quality_running') {
            toast('修订完成，正在重新质检…', { icon: '🔍' })
          } else if (ev.event === 'pre_warn_running') {
            setPreWarnLive({ running: true })
          } else if (ev.event === 'pre_warn_done') {
            setPreWarnLive({ running: false, error: ev.error })
            setPreWarnRefreshKey(k => k + 1)
          } else if (ev.event === 'scene_plan_running') {
            setScenePlanLive({ running: true })
          } else if (ev.event === 'scene_plan_done') {
            setScenePlanLive({ running: false, error: ev.error })
            setScenePlanRefreshKey(k => k + 1)
            if (ev.error) toast(`分场降级：${ev.error}`, { icon: '⚠️' })
            else if (ev.scene_count > 0)
              toast.success(`分场就绪：${ev.scene_count} 场（${(ev.scene_names ?? []).join('→')}）`)
          } else if (ev.event === 'done') {
            setDirty(false)
            toast.success(
              isQcPatch ? `修订完成 ${ev.word_count} 字` : `已生成 ${ev.word_count} 字`,
            )
            onSaved()
          } else if (ev.event === 'quality_done') {
            setQualityRefreshKey(k => k + 1)
            if (ev.ok && ev.status === 'blocked' && ev.raw_score != null)
              toast.error(`自动质检未通过：质量 ${ev.raw_score} 分，存在硬伤`)
            else if (ev.ok && ev.status === 'unverified')
              toast.error('自动质检未完成，请重新质检')
            else if (ev.ok && ev.overall_score != null)
              toast.success(`自动质检完成：${ev.overall_score} 分`)
            else if (!ev.ok) toast.error(`自动质检失败：${ev.error ?? ''}`)
          } else if (ev.event === 'debrief_done') {
            setMemoryRefreshKey(k => k + 1)
            if (ev.ok && ev.memory_count != null)
              toast.success(`自动复盘完成：${ev.memory_count} 条记忆`)
            else if (!ev.ok) toast.error(`自动复盘失败：${ev.error ?? ''}`)
          } else if (ev.event === 'error') {
            toast.error(ev.message)
          }
        },
      )
    } catch (e) {
      if (!gotChunk) setText(regenSnapshot.current)
      toast.error(e instanceof Error ? e.message : '失败')
    } finally {
      setBusy(false)
      setDraftMode(null)
    }
  }

  const runDraft = async (opts: DraftLaunchOptions) => {
    const isRewrite = Boolean(chapter.content?.trim())
    await runStreamDraft({
      user_instruction: opts.userInstruction.trim() || undefined,
      rewrite_mode: 'full',
      rerun_pre_warn: isRewrite ? opts.rerunPreWarn : false,
      rerun_scene_plan: isRewrite ? opts.rerunScenePlan : false,
      rerun_quality: isRewrite ? opts.rerunQuality : true,
      rerun_debrief: isRewrite ? opts.rerunDebrief : true,
    })
  }

  const runQcPatchRewrite = async () => {
    if (!text.trim()) {
      toast.error('本章尚无正文')
      return
    }
    const ok = window.confirm(
      '将根据本章正文与最新质检报告调用一次 LLM 做定点修订，'
      + '完成后自动重新跑质检。\n\n'
      + '不重新跑预警/分场/复盘。继续？',
    )
    if (!ok) return
    await runStreamDraft({
      rewrite_mode: 'qc_patch',
      rerun_pre_warn: false,
      rerun_scene_plan: false,
      rerun_quality: true,
      rerun_debrief: false,
    }, { skipBlockCheck: true })
  }

  const wordCount = text.length
  const canSave = dirty && !busy && !saving && wordCount > 0
  const isRewriteChapter = Boolean(chapter.content?.trim())
  const generateBlocked = Boolean(generateBlockReason) && !isRewriteChapter

  const openDraftModal = () => {
    if (generateBlocked) {
      toast.error(generateBlockReason!)
      return
    }
    setRewritePrefill('')
    setDraftModalOpen(true)
  }

  const openRewriteFromQuality = (instruction: string) => {
    setRewritePrefill(instruction)
    setDraftModalOpen(true)
  }

  const clearChapterWriting = async () => {
    if (!chapter.id || busy || clearing) return
    const hasWritten = Boolean(chapter.content?.trim()) || chapter.status === 'written'
    if (!hasWritten) {
      toast.error('本章尚无生成内容')
      return
    }
    const ok = window.confirm(
      `确定清空第 ${chapter.chapter_number} 章的全部写作产物？\n\n`
      + '将删除：正文、写前预警、分场、质检报告、复盘记忆，并撤销本章台账/线索变更。\n'
      + '章纲五拍保留，可重新生成。\n\n'
      + '若后续章节已有正文，须先从高章号开始清空。',
    )
    if (!ok) return
    setClearing(true)
    try {
      await dabaiApi.clearChapterWriting(projectId, chapter.id)
      toast.success(`第 ${chapter.chapter_number} 章写作产物已清空`)
      setText('')
      setDirty(false)
      setPreWarnLive(null)
      setScenePlanLive(null)
      setPreWarnRefreshKey(k => k + 1)
      setScenePlanRefreshKey(k => k + 1)
      setQualityRefreshKey(k => k + 1)
      setMemoryRefreshKey(k => k + 1)
      onCleared()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '清空失败')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-1 bg-white">
      <DraftLaunchModal
        open={draftModalOpen}
        mode={wordCount > 0 || isRewriteChapter ? 'rewrite' : 'generate'}
        initialInstruction={rewritePrefill}
        onClose={() => {
          setDraftModalOpen(false)
          setRewritePrefill('')
        }}
        onConfirm={opts => void runDraft(opts)}
      />

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
        {dirty ? (
          <span className="text-[10px] text-amber-600">未保存</span>
        ) : null}
        <button
          type="button"
          disabled={!canSave}
          onClick={() => void saveContent()}
          className={clsx(
            'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium',
            canSave
              ? 'border-gray-300 text-gray-700 hover:bg-gray-50'
              : 'cursor-not-allowed border-gray-100 text-gray-300',
          )}
        >
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          保存
        </button>
        <button
          type="button"
          disabled={busy || clearing || !(wordCount > 0 || chapter.status === 'written')}
          onClick={() => void clearChapterWriting()}
          title="清空正文及预警/分场/质检/记忆等写作产物"
          className={clsx(
            'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium',
            busy || clearing || !(wordCount > 0 || chapter.status === 'written')
              ? 'cursor-not-allowed border-gray-100 text-gray-300'
              : 'border-red-200 text-red-600 hover:bg-red-50',
          )}
        >
          {clearing ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
          清空本章
        </button>
        <button
          type="button"
          disabled={busy || generateBlocked}
          onClick={openDraftModal}
          title={generateBlocked ? generateBlockReason ?? undefined : undefined}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white',
            busy || generateBlocked ? 'bg-rose-300' : 'bg-rose-500 hover:bg-rose-600',
          )}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {wordCount > 0 ? '按要素重写' : '按要素生成'}
        </button>
        {generateBlocked ? (
          <span className="w-full basis-full text-[10px] text-amber-600">{generateBlockReason}</span>
        ) : null}
      </div>

        <div className="flex-1 overflow-auto">
          <div className="mx-auto max-w-4xl space-y-4 px-4 py-4">
            <DabaiChapterBeatCard
              beat={beat}
              variant="embedded"
              className="rounded-xl border border-rose-100 bg-rose-50/30 p-4"
            />
            {busy && !text ? (
              <p className="text-sm text-gray-400">
                {draftMode === 'qc_patch'
                  ? '按质检建议修订中（修订 → 自动质检）…'
                  : isRewriteChapter
                    ? '正文重写中…'
                    : '生成中（预警→分场→正文）…'}
              </p>
            ) : (
              <textarea
                value={text}
                disabled={busy}
                onChange={e => {
                  setText(e.target.value)
                  setDirty(true)
                }}
                placeholder="（待生成正文，或可在此直接撰写/微调后点保存）"
                className={clsx(
                  'min-h-[420px] w-full resize-y rounded-lg border border-transparent',
                  'bg-transparent text-[15px] leading-8 text-gray-800',
                  'focus:border-rose-200 focus:bg-rose-50/20 focus:outline-none',
                  busy && 'opacity-60',
                )}
              />
            )}
          </div>
        </div>
      </div>

      <WorkspaceSidePanel
        projectId={projectId}
        chapter={chapter}
        preWarnLive={preWarnLive}
        preWarnRefreshKey={preWarnRefreshKey}
        scenePlanLive={scenePlanLive}
        scenePlanRefreshKey={scenePlanRefreshKey}
        qualityRefreshKey={qualityRefreshKey}
        memoryRefreshKey={memoryRefreshKey}
        onApplyRewriteFromQuality={openRewriteFromQuality}
        onQcPatchRewrite={() => void runQcPatchRewrite()}
        qcPatchRunning={busy && draftMode === 'qc_patch'}
      />
    </div>
  )
}
