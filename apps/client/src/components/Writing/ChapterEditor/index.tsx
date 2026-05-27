/**
 * index.tsx — ChapterEditor 编排壳（硬上限 600 行，见 god-files-chapter-editor.mdc）
 *
 * 禁止：新增 useState/useEffect、>30 行业务函数、内联大块 JSX。
 * 必须：新逻辑进 hooks/*.ts 或 *Toolbar|*Panel|*Area|*Modal.tsx。
 */
import React, { useEffect, useRef } from 'react'
import clsx from 'clsx'
import { foreshadowsApi, chaptersApi } from '../../../api/client'
import { useAppStore } from '../../../store'
import TopToolbar from './TopToolbar'
import StorylinePreWarnBanner from './StorylinePreWarnBanner'
import EditorMainArea from './EditorMainArea'
import ContextSidePanel from './ContextSidePanel'
import ChapterHistoryModal from './ChapterHistoryModal'
import { usePreWriteWarning } from './hooks/usePreWriteWarning'
import { useChapterAutosave } from './hooks/useChapterAutosave'
import { useDebriefRun } from './hooks/useDebriefRun'
import { useWritingConfigHydration } from './hooks/useWritingConfigHydration'
import { useChapterSideData } from './hooks/useChapterSideData'
import { useChapterContextUi } from './hooks/useChapterContextUi'
import { useWritingSession } from './hooks/useWritingSession'
import { useChapterTiptapEditor } from './hooks/useChapterTiptapEditor'
import { useChapterManuscript } from './hooks/useChapterManuscript'
import { useChapterHistory } from './hooks/useChapterHistory'
import { useChapterDraftQueue } from './hooks/useChapterDraftQueue'
import { useQueueDebriefHydrate } from './hooks/useQueueDebriefHydrate'
import { useChapterStatusUpdate } from './hooks/useChapterStatusUpdate'
import { useFanqieChapterSync } from './hooks/useFanqieChapterSync'
import type { ChapterEditorProps as Props, AutoDebriefResponse } from './types'
import { STATUS_OPTIONS } from './constants'

export default function ChapterEditor({
  projectId, chapter, outlineNode, onFocusModeChange,
}: Props) {
  const {
    upsertChapter, removeChapter, setActiveChapterId,
    chapters, characters, storyLines, setStoryLines, setMemories,
  } = useAppStore()

  const writingConfig = useWritingConfigHydration(projectId)
  const genQueue = useAppStore(s => s.genQueue)
  const queueCommittedDebriefIds = useAppStore(s => s.queueCommittedDebriefIds)
  const queueDebriefSnapshot = useAppStore(s => s.queueDebriefUiSnapshotByChapterId[chapter.id])
  const clearQueueDebriefUiSnapshots = useAppStore(s => s.clearQueueDebriefUiSnapshots)

  const prevProjectIdRef = useRef<string | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const onAutoSaveRef = useRef<(html: string) => void | Promise<void>>(async () => {})
  const onWordCountChangeRef = useRef<(n: number) => void>(() => {})

  const ctx = useChapterContextUi(outlineNode, onFocusModeChange)
  const side = useChapterSideData(projectId, chapter.id)

  const tiptap = useChapterTiptapEditor({
    chapter,
    saveTimerRef,
    onAutoSave: html => onAutoSaveRef.current(html),
    onWordCountChange: n => onWordCountChangeRef.current(n),
  })

  const sessionLive = useWritingSession(chapter, tiptap.editor)
  onWordCountChangeRef.current = sessionLive.onEditorWordCountChange

  const manuscript = useChapterManuscript(chapter, tiptap.editor, tiptap.editorHtmlTick)

  const autosave = useChapterAutosave({
    projectId,
    chapter,
    editor: tiptap.editor,
    chapters,
    storyLines,
    upsertChapter,
    setMemories,
    setStoryLines,
    removeChapter,
    setActiveChapterId,
    saveTimerRef,
  })
  onAutoSaveRef.current = autosave.autoSave

  const debrief = useDebriefRun({
    projectId,
    chapterId: chapter.id,
    chapterContent: chapter.content,
    editor: tiptap.editor,
    storyLines,
    upsertChapter,
    setStoryLines,
    setMemories,
    onNavigateToDebriefTab: () => {
      ctx.setContextOpen(true)
      ctx.setContextTab('debrief')
    },
    saveTimerRef,
  })

  const history = useChapterHistory({
    projectId,
    chapter,
    editor: tiptap.editor,
    upsertChapter,
    setManuscriptView: manuscript.setManuscriptView,
  })

  const draft = useChapterDraftQueue({
    projectId,
    chapter,
    chapters,
    outlineNode,
    editor: tiptap.editor,
    writingConfig,
    upsertChapter,
    genQueue,
  })

  const warn = usePreWriteWarning({
    projectId,
    chapterId: chapter.id,
    chapterSortOrder: chapter.sort_order ?? null,
    chapterTitle: chapter.title,
    outlineNode,
    contextTab: ctx.contextTab,
    genQueue: genQueue as Parameters<typeof usePreWriteWarning>[0]['genQueue'],
    onNavigateToWarnTab: () => {
      ctx.setContextOpen(true)
      ctx.setContextTab('warn')
    },
  })

  const fanqieSync = useFanqieChapterSync({
    projectId,
    chapter,
    getEditorHtml: () => tiptap.editor?.getHTML() ?? '',
    onChapterPatched: (patch) => {
      upsertChapter({ ...chapter, ...patch } as typeof chapter)
    },
  })

  const { updateStatus } = useChapterStatusUpdate({
    projectId,
    chapterId: chapter.id,
    upsertChapter,
    setStatusOpen: ctx.setStatusOpen,
    onAfterDoneOrReviewed: async () => {
      await autosave.autoExtractMemoryAfterChapter(true)
      await autosave.autoSyncStorylinesAfterChapter(true)
    },
  })

  const queueHydrate = useQueueDebriefHydrate({
    contextOpen: ctx.contextOpen,
    contextTab: ctx.contextTab,
    chapterId: chapter.id,
    chapterContent: chapter.content,
    chapterUpdatedAt: chapter.updated_at ?? '',
    autoDebriefing: debrief.autoDebriefing,
    debriefSubmitting: debrief.debriefSubmitting,
    queueCommittedDebriefIds,
    queueDebriefSnapshot: queueDebriefSnapshot as AutoDebriefResponse | undefined,
    applyAutoDebriefData: debrief.applyAutoDebriefData,
    setDebriefFromQueueSnapshot: debrief.setDebriefFromQueueSnapshot,
    loadDebriefTabCache: debrief.loadDebriefTabCache,
  })

  useEffect(() => {
    sessionLive.resetSession()
    tiptap.resetSelectionUi()
    debrief.resetDebriefState()
    queueHydrate.resetQueueHydrateRefs()
    manuscript.resetManuscriptViewForChapter()
    history.resetHistoryUi()
    warn.setWarnResult(null)
    warn.setWarnHistory([])
    warn.setSelectedWarnRecordId(null)
  }, [chapter.id])

  useEffect(() => {
    if (prevProjectIdRef.current !== null && prevProjectIdRef.current !== projectId) {
      queueHydrate.clearDebriefToastKeys()
      clearQueueDebriefUiSnapshots()
    }
    prevProjectIdRef.current = projectId
  }, [projectId, clearQueueDebriefUiSnapshots, queueHydrate])

  const hasOutlineContent = Boolean(outlineNode && (
    outlineNode.hook || outlineNode.summary || outlineNode.conflict || outlineNode.highlight
  ))
  const currentStatus = STATUS_OPTIONS.find(o => o.value === chapter.status) ?? STATUS_OPTIONS[0]

  return (
    <div className={clsx(
      'flex flex-col h-full transition-colors duration-200',
      ctx.focusMode ? 'bg-[#fafaf8]' : 'bg-novel-shell/40',
    )}>
      <TopToolbar
        focusMode={ctx.focusMode}
        onToggleFocusMode={() => ctx.setFocusMode(v => !v)}
        chapterTitle={chapter.title}
        chapterStatus={chapter.status}
        currentStatus={currentStatus}
        sessionDelta={sessionLive.sessionDelta}
        elapsedLabel={sessionLive.elapsedLabel}
        wordCount={sessionLive.wordCount}
        contextOpen={ctx.contextOpen}
        contextTab={ctx.contextTab}
        setContextOpen={ctx.setContextOpen}
        setContextTab={ctx.setContextTab}
        outlineNode={outlineNode ?? null}
        statusOpen={ctx.statusOpen}
        statusRef={ctx.statusRef}
        setStatusOpen={ctx.setStatusOpen}
        updateStatus={updateStatus}
        runPreWriteWarning={warn.runPreWriteWarning}
        warnLoading={warn.warnLoading}
        warnResult={warn.warnResult}
        openChapterHistory={() => void history.openChapterHistory()}
        cleanupChapter={() => void autosave.cleanupChapter()}
        cleaningChapter={autosave.cleaningChapter}
        manualSave={() => void autosave.manualSave()}
        syncToFanqie={() => void fanqieSync.syncToFanqie()}
        fanqieSyncing={fanqieSync.syncing}
        fanqieBookId={fanqieSync.fanqieBookId}
        fanqieSyncMeta={fanqieSync.syncMeta}
      />

      <StorylinePreWarnBanner
        items={warn.storylinePreWarns}
        onOpenWarnTab={() => {
          ctx.setContextOpen(true)
          ctx.setContextTab('warn')
        }}
      />

      <div className="flex flex-1 min-h-0">
        <EditorMainArea
          focusMode={ctx.focusMode}
          chapterGenBusy={draft.chapterGenBusy}
          manuscriptView={manuscript.manuscriptView}
          setManuscriptView={manuscript.setManuscriptView}
          hasManuscriptRawSnapshot={manuscript.hasManuscriptRawSnapshot}
          prosePreviewHtml={manuscript.prosePreviewHtml}
          rawSnapshotPreviewHtml={manuscript.rawSnapshotPreviewHtml}
          editor={tiptap.editor}
          showSelectionBar={tiptap.showSelectionBar}
          selectionText={tiptap.selectionText}
          runPromptAction={action => draft.runPromptAction(action, tiptap.setShowSelectionBar, tiptap.selectionText)}
          setShowSelectionBar={tiptap.setShowSelectionBar}
          aiExtraPrompt={draft.aiExtraPrompt}
          setAiExtraPrompt={draft.setAiExtraPrompt}
          continueChapterCount={draft.continueChapterCount}
          setContinueChapterCount={draft.setContinueChapterCount}
          remainingChapterCount={draft.remainingChapterCount}
          normalizedContinueCount={draft.normalizedContinueCount}
          enqueueContinueChapters={draft.enqueueContinueChapters}
          generateDisabled={draft.generateDisabled}
          generateBlockedReason={draft.generateBlockedReason}
          generateDraft={draft.generateDraft}
          wordCount={sessionLive.wordCount}
          sessionDelta={sessionLive.sessionDelta}
          openChapterHistory={history.openChapterHistory}
          manualSave={autosave.manualSave}
          setFocusMode={ctx.setFocusMode}
          openForeshadows={side.openForeshadows}
          bottomPanelOpen={side.bottomPanelOpen}
          setBottomPanelOpen={side.setBottomPanelOpen}
          currentChIndex={side.currentChIndex}
        />

        <ContextSidePanel
          contextOpen={ctx.contextOpen}
          focusMode={ctx.focusMode}
          contextTab={ctx.contextTab}
          setContextTab={ctx.setContextTab}
          setContextOpen={ctx.setContextOpen}
          projectId={projectId}
          chapter={chapter}
          outlineNode={outlineNode ?? undefined}
          characters={characters}
          storyLines={storyLines}
          hasOutlineContent={hasOutlineContent}
          currentChIndex={side.currentChIndex}
          onChIndexSaved={side.setCurrentChIndex}
          onForeshadowsMayChange={() => {
            foreshadowsApi.list(projectId, 'open').then(r => side.setOpenForeshadows(r.data)).catch(() => {})
          }}
          onSceneStitchDone={async () => {
            try {
              upsertChapter((await chaptersApi.get(projectId, chapter.id)).data)
            } catch { /* 静默 */ }
          }}
          debriefPanelProps={{
            projectId,
            chapter,
            outlineNode,
            characters,
            storyLines,
            charUpdates: debrief.charUpdates,
            setCharUpdates: debrief.setCharUpdates,
            storylineBeats: debrief.storylineBeats,
            setStorylineBeats: debrief.setStorylineBeats,
            debriefNotes: debrief.debriefNotes,
            setDebriefNotes: debrief.setDebriefNotes,
            submitting: debrief.debriefSubmitting,
            autoDebriefing: debrief.autoDebriefing,
            cacheHydrating: debrief.debriefCacheHydrating,
            aiSuggestedCharIds: debrief.aiSuggestedCharIds,
            aiSuggestedSlIds: debrief.aiSuggestedSlIds,
            aiSuggestedAssetUpdates: debrief.aiSuggestedAssetUpdates,
            aiNewCharacters: debrief.aiNewCharacters,
            aiNewReaderPromises: debrief.aiNewReaderPromises,
            aiFulfilledPromiseTexts: debrief.aiFulfilledPromiseTexts,
            onRemoveNewPromise: idx => debrief.setAiNewReaderPromises(prev => prev.filter((_, i) => i !== idx)),
            onRemoveFulfilledPromise: idx => debrief.setAiFulfilledPromiseTexts(prev => prev.filter((_, i) => i !== idx)),
            aiSummary: debrief.aiDebriefSummary,
            onAutoDebrief: debrief.runAutoDebrief,
            onSubmit: debrief.submitDebrief,
            fromQueueSnapshot: debrief.debriefFromQueueSnapshot,
            debriefHistoryTick: debrief.debriefHistoryTick,
            debriefContentReady: debrief.debriefContentReady,
          }}
          gatedPreWarnDoneForChapter={warn.gatedPreWarnDoneForChapter}
          warnLoading={warn.warnLoading}
          warnResult={warn.warnResult}
          storylinePreWarns={warn.storylinePreWarns}
          warnHistory={warn.warnHistory}
          selectedWarnRecordId={warn.selectedWarnRecordId}
          setSelectedWarnRecordId={warn.setSelectedWarnRecordId}
          setWarnResult={warn.setWarnResult}
          runPreWriteWarning={warn.runPreWriteWarning}
        />
      </div>

      <ChapterHistoryModal
        historyOpen={history.historyOpen}
        setHistoryOpen={history.setHistoryOpen}
        versionsLoading={history.versionsLoading}
        versionsList={history.versionsList}
        historyPreviewLoading={history.historyPreviewLoading}
        historyPreview={history.historyPreview}
        onSelectVersion={history.loadHistoryPreview}
        onRestoreVersion={history.restoreHistoryVersion}
      />
    </div>
  )
}
