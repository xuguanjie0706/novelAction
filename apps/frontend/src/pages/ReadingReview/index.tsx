/**
 * @file 作品质量与修订 — Tab 编排壳
 */
import { App, Space, Tabs } from 'antd'
import { CoherenceApplyModal } from './CoherenceApplyModal'
import { HistoryReportList } from './HistoryReportList'
import { PageHeader } from './PageHeader'
import { RevisionDrawer } from './RevisionDrawer'
import { SnapshotDiffModal } from './SnapshotDiffModal'
import { BodySnapshotsTab } from './tabs/BodySnapshotsTab'
import { ChapterQualityTab } from './tabs/ChapterQualityTab'
import { CoherenceTab } from './tabs/CoherenceTab'
import { OverviewTab } from './tabs/OverviewTab'
import { useReadingReviewPage } from './useReadingReviewPage'

export default function ReadingReviewPage() {
  const { message } = App.useApp()
  const s = useReadingReviewPage()

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <PageHeader
        loading={s.loading}
        projects={s.projects}
        projectId={s.projectId}
        onProjectChange={s.setProjectId}
        llmOverview={s.llmOverview}
        selectedModelOption={s.selectedModelOption}
        onModelChange={s.setSelectedModelOption}
      />

      <Tabs
        items={[
          {
            key: 'overview',
            label: '总览',
            children: (
              <OverviewTab
                chapters={s.chapters}
                chapterColumns={s.chapterColumns}
                overviewAvg={s.overviewAvg}
                lowCount={s.lowCount}
                outlineRiskChapters={s.outlineRiskChapters}
              />
            ),
          },
          {
            key: 'chapter',
            label: '单章评测',
            children: (
              <ChapterQualityTab
                chapterOptions={s.chapterOptions}
                selectedChapterId={s.selectedChapterId}
                onChapterChange={s.setSelectedChapterId}
                qualityLoading={s.qualityLoading}
                onRunQualityCheck={s.runQualityCheck}
                onViewChapter={() => {
                  if (!s.projectId || !s.selectedChapterId) {
                    message.warning('请先选择项目与章节')
                    return
                  }
                  s.goToChapterEditor(s.selectedChapterId)
                }}
                qualityReport={s.qualityReport}
              />
            ),
          },
          {
            key: 'coherence',
            label: '连贯性评测',
            children: (
              <CoherenceTab
                chapters={s.chapters}
                chapterOptions={s.chapterOptions}
                selectedCoherenceChapters={s.selectedCoherenceChapters}
                onSelectedChaptersChange={s.setSelectedCoherenceChapters}
                rangeStartId={s.rangeStartId}
                rangeEndId={s.rangeEndId}
                anchorChapterId={s.anchorChapterId}
                onRangeStartChange={s.setRangeStartId}
                onRangeEndChange={s.setRangeEndId}
                onAnchorChange={s.setAnchorChapterId}
                applyContinuousRange={s.applyContinuousRange}
                applyAnchorWindow={s.applyAnchorWindow}
                selectedRangeHint={s.selectedRangeHint}
                coherenceLoading={s.coherenceLoading}
                onRunCoherenceCheck={s.runCoherenceCheck}
                coherenceResult={s.coherenceResult}
                saveLoading={s.saveLoading}
                lastSavedCoherenceReport={s.lastSavedCoherenceReport}
                onOpenRevisionDrawer={s.openRevisionDrawer}
              />
            ),
          },
          {
            key: 'history',
            label: '报告与修订',
            children: (
              <HistoryReportList
                revisionStepIndex={s.revisionStepIndex}
                applyTimeline={s.applyTimeline}
                chapters={s.chapters}
                formatApplyChapterLine={s.formatApplyChapterLine}
                compareA={s.compareA}
                compareB={s.compareB}
                historyLoading={s.historyLoading}
                historyRows={s.historyRows}
                compareIds={s.compareIds}
                onCompareIdsChange={s.setCompareIds}
                coherenceApplyLoadingId={s.coherenceApplyLoadingId}
                onOpenRevisionDrawer={s.openRevisionDrawer}
              />
            ),
          },
          {
            key: 'body-snapshots',
            label: '正文快照',
            children: (
              <BodySnapshotsTab
                versionTimelineLoading={s.versionTimelineLoading}
                versionTimelineRows={s.versionTimelineRows}
                onOpenSnapshotDiff={s.openSnapshotBeforeAfterPreview}
                onGoToEditor={s.goToChapterEditor}
              />
            ),
          },
        ]}
      />

      <RevisionDrawer
        open={s.revisionDrawerOpen}
        report={s.revisionReport}
        focusIssueIndices={s.focusIssueIndices}
        focusSuggIndices={s.focusSuggIndices}
        focusEvalIndices={s.focusEvalIndices}
        revisionKeywordTags={s.revisionKeywordTags}
        revisionNote={s.revisionNote}
        loading={!!s.revisionReport && s.coherenceApplyLoadingId === s.revisionReport.id}
        onClose={s.closeRevisionDrawer}
        onFocusIssueChange={s.setFocusIssueIndices}
        onFocusSuggChange={s.setFocusSuggIndices}
        onFocusEvalChange={s.setFocusEvalIndices}
        onKeywordTagsChange={s.setRevisionKeywordTags}
        onRevisionNoteChange={s.setRevisionNote}
        onSubmitPreview={s.submitRevisionPreviewFromDrawer}
      />

      <CoherenceApplyModal
        open={s.coherenceApplyModalOpen}
        revisions={s.coherenceApplyRevisions}
        committing={s.coherenceApplyCommitting}
        onCancel={s.cancelCoherenceApplyModal}
        onCommit={s.commitCoherenceApply}
      />

      <SnapshotDiffModal
        title={s.versionPreviewModalTitle}
        open={s.versionPreviewOpen}
        loading={s.versionPreviewLoading}
        panels={s.versionPreviewPanels}
        onClose={s.closeVersionPreview}
      />
    </Space>
  )
}
