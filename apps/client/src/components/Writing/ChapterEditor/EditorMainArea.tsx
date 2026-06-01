/**
 * EditorMainArea.tsx — 主编辑区（左侧：正文编辑器 + 工具栏按钮区 + 线索面板）
 *
 * 注意：右侧上下文面板（plan/scene/debrief/chindex/warn）不在此处，交由 ContextSidePanel 负责。
 */
import React from 'react'
import clsx from 'clsx'
import { Anchor, ChevronDown, ChevronRight, Circle, Feather, GitCompare, History, ListPlus, Minimize2, RefreshCw, Save, Sparkles, X } from 'lucide-react'
import { ManuscriptCompareModal } from './ManuscriptCompareModal'
import ChapterVersionComparePicker from './ChapterVersionComparePicker'
import { EditorContent } from '@tiptap/react'
import type { Editor } from '@tiptap/react'
import type { ChapterIndex, ChapterVersion, Foreshadow } from '../../../types'
import { TOP_TOOL_PRIMARY_BUTTON } from './constants'

export default function EditorMainArea({
  focusMode,

  chapterGenBusy,

  chapterTitle,
  showCompareEntry,
  versionCompare,
  editor,

  showSelectionBar,
  selectionText,
  runPromptAction,
  setShowSelectionBar,

  aiExtraPrompt,
  setAiExtraPrompt,
  continueChapterCount,
  setContinueChapterCount,
  remainingChapterCount,
  normalizedContinueCount,
  enqueueContinueChapters,
  generateDisabled,
  generateBlockedReason,
  generateDraft,

  wordCount,
  sessionDelta,
  openChapterHistory,
  manualSave,

  setFocusMode,

  openForeshadows,
  bottomPanelOpen,
  setBottomPanelOpen,
  currentChIndex,
}: {
  focusMode: boolean
  chapterGenBusy: boolean

  chapterTitle: string
  showCompareEntry: boolean
  versionCompare: {
    pickerOpen: boolean
    setPickerOpen: (v: boolean) => void
    compareOpen: boolean
    setCompareOpen: (v: boolean) => void
    versionsLoading: boolean
    versionsList: ChapterVersion[]
    baseId: string
    setBaseId: (id: string) => void
    assignBase: (id: string) => void
    targetId: string
    setTargetId: (id: string) => void
    assignTarget: (id: string) => void
    beforePlain: string
    afterPlain: string
    beforeLabel: string
    afterLabel: string
    runningCompare: boolean
    openComparePicker: () => void | Promise<void>
    runCompare: () => void | Promise<void>
    canCompare: boolean
    formatVersionLabel: (v: ChapterVersion) => string
    currentWordCount: number | null
  }
  editor: Editor | null

  showSelectionBar: boolean
  selectionText: string
  runPromptAction: (action: 'rewrite' | 'expand') => void
  setShowSelectionBar: React.Dispatch<React.SetStateAction<boolean>>

  aiExtraPrompt: string
  setAiExtraPrompt: React.Dispatch<React.SetStateAction<string>>
  continueChapterCount: number
  setContinueChapterCount: React.Dispatch<React.SetStateAction<number>>
  remainingChapterCount: number
  normalizedContinueCount: number
  enqueueContinueChapters: () => void | Promise<void>
  generateDisabled: boolean
  generateBlockedReason: string | null | undefined
  generateDraft: (opts?: { replaceExisting?: boolean; overridePrompt?: string }) => void

  wordCount: number
  sessionDelta: number
  openChapterHistory: () => void | Promise<void>
  manualSave: () => void | Promise<void>

  setFocusMode: React.Dispatch<React.SetStateAction<boolean>>

  openForeshadows: Foreshadow[]
  bottomPanelOpen: boolean
  setBottomPanelOpen: React.Dispatch<React.SetStateAction<boolean>>
  currentChIndex: ChapterIndex | null
}) {
  const vc = versionCompare

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 正文编辑器 */}
      <div className={clsx('flex-1 overflow-auto', focusMode && 'flex justify-center')}>
        <div className={clsx(focusMode && 'w-full max-w-2xl', 'relative w-full min-h-[50vh]')}>
          {showCompareEntry && (
            <div className="sticky top-2 z-30 flex justify-end pointer-events-none px-4 sm:px-10 pt-1">
              <button
                type="button"
                onClick={() => void vc.openComparePicker()}
                className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-amber-200/90 bg-novel-card/95 backdrop-blur-sm px-3.5 py-1.5 text-[11px] font-medium text-amber-900 shadow-sm hover:bg-amber-50/90 transition-novel"
                title="从版本历史选择两版正文进行对照"
              >
                <GitCompare size={14} className="text-amber-600 shrink-0" />
                对比
              </button>
            </div>
          )}

          <EditorContent editor={editor} className="h-full" />
        </div>
      </div>

      <ChapterVersionComparePicker
        open={vc.pickerOpen}
        onClose={() => vc.setPickerOpen(false)}
        versionsLoading={vc.versionsLoading}
        versionsList={vc.versionsList}
        baseId={vc.baseId}
        targetId={vc.targetId}
        onAssignBase={vc.assignBase}
        onAssignTarget={vc.assignTarget}
        onRunCompare={vc.runCompare}
        runningCompare={vc.runningCompare}
        canCompare={vc.canCompare}
        formatVersionLabel={vc.formatVersionLabel}
        currentWordCount={vc.currentWordCount}
      />

      <ManuscriptCompareModal
        open={vc.compareOpen}
        chapterTitle={chapterTitle}
        beforePlain={vc.beforePlain}
        afterPlain={vc.afterPlain}
        beforeLabel={vc.beforeLabel}
        afterLabel={vc.afterLabel}
        onClose={() => vc.setCompareOpen(false)}
      />

      {/* 选中文字快捷操作栏（专注模式下隐藏）*/}
      {showSelectionBar && !focusMode && (
        <div className="border-t border-violet-100 bg-violet-50/80 px-5 py-2.5 shrink-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-violet-600 font-medium flex items-center gap-1 mr-1 shrink-0">
              <Sparkles size={11} />
              已选 {selectionText.length} 字
            </span>
            <button
              type="button"
              disabled={chapterGenBusy}
              onClick={() => runPromptAction('rewrite')}
              className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50"
            >
              <RefreshCw size={11} />
              改写
            </button>
            <button
              type="button"
              disabled={chapterGenBusy}
              onClick={() => runPromptAction('expand')}
              className="flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white border border-violet-200 text-violet-700 rounded-novel hover:bg-violet-100 transition-novel disabled:opacity-50"
            >
              <Feather size={11} />
              扩写
            </button>
            <button
              type="button"
              onClick={() => setShowSelectionBar(false)}
              className="ml-auto text-violet-300 hover:text-violet-500 p-0.5 shrink-0"
            >
              <X size={12} />
            </button>
          </div>
        </div>
      )}

      {/* AI 输入工具区（专注模式下隐藏）*/}
      {!focusMode && (
        <div className="border-t border-gray-100 bg-[#fbfaf7] px-5 py-4 shrink-0">
          <div className="rounded-lg border border-gray-200 bg-white px-3 py-3 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
              <label className="flex-1 min-w-0">
                <span className="mb-1.5 block text-[11px] font-semibold text-gray-500">AI 续写要求</span>
                <input
                  type="text"
                  value={aiExtraPrompt}
                  onChange={e => setAiExtraPrompt(e.target.value)}
                  disabled={chapterGenBusy}
                  placeholder="输入风格、情节走向或禁忌；留空则按大纲和上下文续写"
                  className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-amber-400 focus:ring-2 focus:ring-amber-100 disabled:opacity-60"
                />
              </label>

              <div className="flex flex-wrap items-end gap-2 lg:self-end">
                <label className="w-28">
                  <span className="mb-1.5 block text-[11px] font-semibold text-gray-500">连续章节</span>
                  <input
                    type="number"
                    min={1}
                    max={remainingChapterCount}
                    value={normalizedContinueCount}
                    disabled={chapterGenBusy}
                    onChange={e => {
                      const next = Number(e.target.value)
                      setContinueChapterCount(Number.isFinite(next) ? next : 1)
                    }}
                    className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-800 outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100 disabled:opacity-60"
                  />
                </label>

                <div className="flex flex-col gap-1.5">
                  <span className="block text-[11px] font-semibold text-transparent select-none">操作</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={enqueueContinueChapters}
                      disabled={generateDisabled}
                      title={generateBlockedReason ?? undefined}
                      className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-60"
                    >
                      {normalizedContinueCount > 1 ? <ListPlus size={15} /> : <Sparkles size={15} className={chapterGenBusy ? 'animate-pulse' : ''} />}
                      {normalizedContinueCount > 1 ? '加入队列' : chapterGenBusy ? '队列中…' : '生成'}
                    </button>

                    {wordCount > 0 && (
                      <button
                        type="button"
                        onClick={() => generateDraft({ replaceExisting: true })}
                        disabled={chapterGenBusy}
                        className="flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:opacity-60"
                      >
                        <RefreshCw size={14} />
                        重写本章
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 底部伏笔快查面板（专注模式隐藏）── */}
      {!focusMode && (openForeshadows.length > 0 || currentChIndex) && (
        <div className="border-t border-amber-100 bg-amber-50/40 shrink-0">
          {/* 折叠头 */}
          <button
            type="button"
            onClick={() => setBottomPanelOpen(v => !v)}
            className="w-full flex items-center justify-between px-4 py-2 text-xs text-amber-700 hover:bg-amber-50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Anchor size={12} />
              <span className="font-medium">线索面板</span>
              {openForeshadows.length > 0 && (
                <span className="bg-amber-200 text-amber-800 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
                  {openForeshadows.length} 条未回收伏笔
                </span>
              )}
              {currentChIndex && (
                <span className="bg-blue-100 text-blue-600 text-[10px] px-1.5 py-0.5 rounded-full font-medium">
                  情节档案已生成
                </span>
              )}
            </div>
            {bottomPanelOpen ? <ChevronDown size={12} className="text-amber-400" /> : <ChevronRight size={12} className="text-amber-400" />}
          </button>

          {/* 展开内容 */}
          {bottomPanelOpen && (
            <div className="px-4 pb-3 space-y-3 max-h-52 overflow-auto">
              {/* 未回收伏笔列表 */}
              {openForeshadows.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold text-amber-600 uppercase tracking-wider mb-1.5">
                    未回收伏笔 · {openForeshadows.length} 条
                  </div>
                  <div className="space-y-1">
                    {openForeshadows.map(f => (
                      <div key={f.id} className="flex items-start gap-2 text-xs">
                        <Circle size={8} className="text-amber-400 shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <span className="font-medium text-gray-700">{f.title}</span>
                          {f.code && <span className="ml-1.5 font-mono text-[10px] text-gray-400">{f.code}</span>}
                          {f.planned_resolve_chapter && (
                            <span className="ml-1.5 text-[10px] text-amber-500">
                              预计第 {f.planned_resolve_chapter} 章{f.planned_action === 'develop' ? '铺垫' : '回收'}
                            </span>
                          )}
                          {f.description && <p className="text-[11px] text-gray-400 mt-0.5 truncate">{f.description}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 当前章情节档案摘要 */}
              {currentChIndex && (
                <div>
                  <div className="text-[10px] font-semibold text-blue-500 uppercase tracking-wider mb-1.5">
                    情节档案 · 第 {currentChIndex.chapter_number} 章
                  </div>
                  {currentChIndex.core_events?.length ? (
                    <div className="space-y-0.5">
                      {currentChIndex.core_events.slice(0, 3).map((ev, i) => (
                        <div key={i} className="text-[11px] text-gray-600 flex gap-1.5">
                          <span className="text-blue-300 shrink-0">•</span>
                          <span>{typeof ev === 'string' ? ev : JSON.stringify(ev)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {currentChIndex.ending_hook && (
                    <p className="text-[11px] text-gray-400 italic mt-1">钩子："{currentChIndex.ending_hook}"</p>
                  )}
                  {currentChIndex.actual_foreshadows_laid?.length ? (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {currentChIndex.actual_foreshadows_laid.map((f, i) => (
                        <span key={i} className="text-[10px] bg-amber-50 text-amber-600 border border-amber-100 px-1.5 py-0.5 rounded">
                          埋：{typeof f === 'string' ? f : (f.description as string)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 专注模式浮动状态栏 */}
      {focusMode && (
        <div className="flex justify-center pb-5 shrink-0 pointer-events-none px-3">
          <div className="flex flex-wrap items-center justify-center gap-3 bg-white/90 backdrop-blur-md border border-gray-200/90 rounded-2xl px-4 py-2.5 shadow-md pointer-events-auto max-w-full">
            <span className="text-xs text-gray-500 font-medium">{wordCount.toLocaleString()} 字</span>
            {sessionDelta !== 0 && (
              <span className={clsx('text-xs font-semibold', sessionDelta > 0 ? 'text-green-600' : 'text-red-400')}>
                {sessionDelta > 0 ? '+' : ''}
                {sessionDelta}
              </span>
            )}
            <div className="hidden sm:block h-5 w-px bg-gray-200 shrink-0" aria-hidden />
            <button
              type="button"
              onClick={() => void manualSave()}
              className={`${TOP_TOOL_PRIMARY_BUTTON} h-8 min-w-[5rem] px-3 text-[13px]`}
            >
              <Save size={14} strokeWidth={2.25} className="shrink-0" />
              保存
            </button>
            <button
              type="button"
              onClick={() => void openChapterHistory()}
              className="text-xs font-medium text-gray-600 hover:text-gray-900 flex items-center gap-1 rounded-lg px-2 py-1 border border-gray-200 bg-white hover:bg-gray-50"
            >
              <History size={12} />
              版本
            </button>
            <button
              type="button"
              onClick={() => setFocusMode(false)}
              className="text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-gray-100"
            >
              <Minimize2 size={11} />
              退出专注
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

