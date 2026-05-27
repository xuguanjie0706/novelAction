import { App } from 'antd'
import axios from 'axios'
import { useCallback, useState } from 'react'
import { http, LONG_RUNNING_HTTP_TIMEOUT_MS } from '../../api/http'
import type {
  CoherenceApplyPreviewResponse,
  CoherenceApplyRevisionPreview,
  CoherenceReportRecord,
  ModelProfile,
} from '../../types/review'

type RevisionFocusSelection = {
  cross_chapter_issue_indices: number[]
  suggestion_indices: number[]
  chapter_evaluation_indices: number[]
}

/** 连贯性报告定向修订：抽屉勾选 → 预览 → 写入数据库 */
export function useCoherenceRevision(
  projectId: string | undefined,
  modelProfile: ModelProfile,
  selectedProviderId: string | undefined,
  onCommitted: () => Promise<void>,
) {
  const { message } = App.useApp()
  const [coherenceApplyModalOpen, setCoherenceApplyModalOpen] = useState(false)
  const [coherenceApplyReportId, setCoherenceApplyReportId] = useState<string | null>(null)
  const [coherenceApplyRevisions, setCoherenceApplyRevisions] = useState<CoherenceApplyRevisionPreview[]>([])
  const [coherenceApplyLoadingId, setCoherenceApplyLoadingId] = useState<string | null>(null)
  const [coherenceApplyCommitting, setCoherenceApplyCommitting] = useState(false)

  const [revisionDrawerOpen, setRevisionDrawerOpen] = useState(false)
  const [revisionReport, setRevisionReport] = useState<CoherenceReportRecord | null>(null)
  const [focusIssueIndices, setFocusIssueIndices] = useState<number[]>([])
  const [focusSuggIndices, setFocusSuggIndices] = useState<number[]>([])
  const [focusEvalIndices, setFocusEvalIndices] = useState<number[]>([])
  const [revisionKeywordTags, setRevisionKeywordTags] = useState<string[]>([])
  const [revisionNote, setRevisionNote] = useState('')

  const openRevisionDrawer = useCallback((row: CoherenceReportRecord) => {
    const res = row.result
    const nIssues = (res.cross_chapter_issues ?? []).length
    const nSugg = (res.suggestions ?? []).length
    const nEval = (res.chapter_evaluations ?? []).length
    setRevisionReport(row)
    setFocusIssueIndices(Array.from({ length: nIssues }, (_, i) => i))
    setFocusSuggIndices(Array.from({ length: nSugg }, (_, i) => i))
    setFocusEvalIndices(Array.from({ length: nEval }, (_, i) => i))
    setRevisionKeywordTags([])
    setRevisionNote('')
    setRevisionDrawerOpen(true)
  }, [])

  const closeRevisionDrawer = useCallback(() => {
    setRevisionDrawerOpen(false)
    setRevisionReport(null)
  }, [])

  const runCoherenceApplyPreviewRequest = useCallback(
    async (
      body: {
        report_id: string
        model_profile: ModelProfile
        llm_provider_id?: string
        focus_keywords?: string[]
        revision_note?: string
        focus_selection?: RevisionFocusSelection
      },
      loadingKey?: string,
    ) => {
      if (!projectId) return
      if (loadingKey) setCoherenceApplyLoadingId(loadingKey)
      try {
        const { data } = await http.post<CoherenceApplyPreviewResponse>(
          `/api/v1/projects/${projectId}/ai/chapter-coherence-apply/preview`,
          body,
          { timeout: LONG_RUNNING_HTTP_TIMEOUT_MS },
        )
        setCoherenceApplyReportId(data.report_id)
        setCoherenceApplyRevisions(data.revisions ?? [])
        setCoherenceApplyModalOpen(true)
        setRevisionDrawerOpen(false)
      } catch (e) {
        const extra = axios.isAxiosError(e)
          ? e.code === 'ECONNABORTED'
            ? '（客户端等待超时；已延长至 15 分钟，若仍失败请缩小评测章节数）'
            : `: ${String((e.response?.data as { detail?: unknown } | undefined)?.detail ?? e.message)}`
          : ''
        message.error(`修订预览生成失败${extra}`)
      } finally {
        if (loadingKey) setCoherenceApplyLoadingId(null)
      }
    },
    [message, projectId],
  )

  const submitRevisionPreviewFromDrawer = useCallback(() => {
    if (!revisionReport || !projectId) return
    const n = focusIssueIndices.length + focusSuggIndices.length + focusEvalIndices.length
    if (n === 0) {
      message.warning('请至少勾选一项评测条目（跨章风险、建议或章节点评）')
      return
    }
    void runCoherenceApplyPreviewRequest(
      {
        report_id: revisionReport.id,
        model_profile: modelProfile,
        llm_provider_id: selectedProviderId,
        focus_keywords: revisionKeywordTags.length ? revisionKeywordTags : undefined,
        revision_note: revisionNote.trim() || undefined,
        focus_selection: {
          cross_chapter_issue_indices: focusIssueIndices,
          suggestion_indices: focusSuggIndices,
          chapter_evaluation_indices: focusEvalIndices,
        },
      },
      revisionReport.id,
    )
  }, [
    focusEvalIndices,
    focusIssueIndices,
    focusSuggIndices,
    message,
    modelProfile,
    projectId,
    revisionKeywordTags,
    revisionNote,
    revisionReport,
    runCoherenceApplyPreviewRequest,
    selectedProviderId,
  ])

  const commitCoherenceApply = useCallback(async () => {
    if (!projectId || !coherenceApplyReportId) return
    const payload = coherenceApplyRevisions.filter((r) => !r.unchanged && r.revised_content.trim())
    if (payload.length === 0) {
      message.warning('预览中无可写入的修订')
      return
    }
    setCoherenceApplyCommitting(true)
    try {
      await http.post(
        `/api/v1/projects/${projectId}/ai/chapter-coherence-apply/commit`,
        {
          report_id: coherenceApplyReportId,
          revisions: payload.map((r) => ({ chapter_id: r.chapter_id, revised_content: r.revised_content })),
        },
        { timeout: LONG_RUNNING_HTTP_TIMEOUT_MS },
      )
      message.success('已写入正文。改正记录已保存，在「报告与修订」中可随时查看')
      setCoherenceApplyModalOpen(false)
      setCoherenceApplyRevisions([])
      setCoherenceApplyReportId(null)
      setRevisionDrawerOpen(false)
      setRevisionReport(null)
      await onCommitted()
    } catch {
      message.error('写入失败')
    } finally {
      setCoherenceApplyCommitting(false)
    }
  }, [coherenceApplyReportId, coherenceApplyRevisions, message, onCommitted, projectId])

  const cancelCoherenceApplyModal = useCallback(() => {
    setCoherenceApplyModalOpen(false)
    setCoherenceApplyRevisions([])
    setCoherenceApplyReportId(null)
    if (revisionReport) setRevisionDrawerOpen(true)
  }, [revisionReport])

  const revisionStepIndex = coherenceApplyModalOpen ? 2 : revisionDrawerOpen ? 1 : 0

  return {
    coherenceApplyModalOpen,
    coherenceApplyRevisions,
    coherenceApplyLoadingId,
    coherenceApplyCommitting,
    revisionDrawerOpen,
    revisionReport,
    focusIssueIndices,
    focusSuggIndices,
    focusEvalIndices,
    revisionKeywordTags,
    revisionNote,
    revisionStepIndex,
    setFocusIssueIndices,
    setFocusSuggIndices,
    setFocusEvalIndices,
    setRevisionKeywordTags,
    setRevisionNote,
    openRevisionDrawer,
    closeRevisionDrawer,
    submitRevisionPreviewFromDrawer,
    commitCoherenceApply,
    cancelCoherenceApplyModal,
  }
}
