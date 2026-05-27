import { App } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { http, LONG_RUNNING_HTTP_TIMEOUT_MS } from '../../api/http'
import type { LlmOverview } from '../../types/llm'
import type {
  ChapterCoherenceResult,
  CoherenceApplyChapterResult,
  CoherenceReportRecord,
  ModelProfile,
  QualityReport,
  ReviewChapter,
  ReviewProject,
} from '../../types/review'
import { CHECK_TYPES } from './constants'
import { useCoherenceRevision } from './useCoherenceRevision'
import { useVersionSnapshot } from './useVersionSnapshot'
import { formatApplyChapterLine, scoreTag } from './utils'

/** 作品质量与修订页：项目/章节数据、单章与连贯性评测、历史报告 */
export function useReadingReviewPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()

  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState<ReviewProject[]>([])
  const [projectId, setProjectId] = useState<string>()
  const [chapters, setChapters] = useState<ReviewChapter[]>([])
  const [llmOverview, setLlmOverview] = useState<LlmOverview | null>(null)
  const [selectedModelOption, setSelectedModelOption] = useState<string>('local')

  const [selectedChapterId, setSelectedChapterId] = useState<string>()
  const [qualityLoading, setQualityLoading] = useState(false)
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null)

  const [coherenceLoading, setCoherenceLoading] = useState(false)
  const [selectedCoherenceChapters, setSelectedCoherenceChapters] = useState<string[]>([])
  const [rangeStartId, setRangeStartId] = useState<string>()
  const [rangeEndId, setRangeEndId] = useState<string>()
  const [anchorChapterId, setAnchorChapterId] = useState<string>()
  const [coherenceResult, setCoherenceResult] = useState<ChapterCoherenceResult | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)

  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyRows, setHistoryRows] = useState<CoherenceReportRecord[]>([])
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [lastSavedCoherenceReport, setLastSavedCoherenceReport] = useState<CoherenceReportRecord | null>(null)

  const selectedProviderId = selectedModelOption.startsWith('provider:')
    ? selectedModelOption.replace('provider:', '')
    : undefined
  const modelProfile: ModelProfile = selectedProviderId ? 'gemini' : 'local'

  const loadChapters = useCallback(
    async (pid: string) => {
      try {
        const { data } = await http.get<ReviewChapter[]>(`/api/v1/projects/${pid}/chapters/`)
        setChapters(data)
        if (data.length > 0) {
          setSelectedChapterId(data[0].id)
        } else {
          setSelectedChapterId(undefined)
        }
      } catch {
        message.error('加载章节失败')
      }
    },
    [message],
  )

  const loadHistory = useCallback(
    async (pid: string) => {
      setHistoryLoading(true)
      try {
        const { data } = await http.get<CoherenceReportRecord[]>(
          `/api/v1/projects/${pid}/ai/chapter-coherence-reports`,
          { params: { limit: 30 } },
        )
        setHistoryRows(data)
      } catch {
        message.error('加载历史报告失败')
      } finally {
        setHistoryLoading(false)
      }
    },
    [message],
  )

  const {
    versionTimelineLoading,
    versionTimelineRows,
    versionPreviewOpen,
    versionPreviewLoading,
    versionPreviewPanels,
    versionPreviewModalTitle,
    loadVersionTimeline,
    openSnapshotBeforeAfterPreview,
    closeVersionPreview,
  } = useVersionSnapshot(projectId)

  const reloadAfterCommit = useCallback(async () => {
    if (!projectId) return
    await loadChapters(projectId)
    await loadHistory(projectId)
    await loadVersionTimeline(projectId)
  }, [loadChapters, loadHistory, loadVersionTimeline, projectId])

  const revision = useCoherenceRevision(projectId, modelProfile, selectedProviderId, reloadAfterCommit)
  const { closeRevisionDrawer } = revision

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<ReviewProject[]>('/api/v1/projects/')
      setProjects(data)
      if (!projectId && data.length > 0) setProjectId(data[0].id)
    } catch {
      message.error('加载项目失败，请确认后端服务可用')
    } finally {
      setLoading(false)
    }
  }, [message, projectId])

  const loadLlmOverview = useCallback(async () => {
    try {
      const { data } = await http.get<LlmOverview>('/api/v1/llm/overview')
      setLlmOverview(data)
      if (data.remote_providers.length > 0) {
        const defaultProvider = data.remote_providers.find((p) => p.is_default)
        if (!selectedModelOption || selectedModelOption === 'local') {
          setSelectedModelOption(defaultProvider ? `provider:${defaultProvider.id}` : 'local')
        }
      } else {
        setSelectedModelOption('local')
      }
    } catch {
      setSelectedModelOption('local')
      message.warning('模型列表获取失败，已回退为本地模型')
    }
  }, [message, selectedModelOption])

  useEffect(() => {
    void loadProjects()
    void loadLlmOverview()
  }, [loadProjects, loadLlmOverview])

  useEffect(() => {
    if (!projectId) return
    setQualityReport(null)
    setCoherenceResult(null)
    setSelectedCoherenceChapters([])
    setRangeStartId(undefined)
    setRangeEndId(undefined)
    setAnchorChapterId(undefined)
    setCompareIds([])
    setLastSavedCoherenceReport(null)
    closeRevisionDrawer()
    void loadChapters(projectId)
    void loadHistory(projectId)
    void loadVersionTimeline(projectId)
  }, [projectId, loadChapters, loadHistory, loadVersionTimeline, closeRevisionDrawer])

  useEffect(() => {
    if (chapters.length === 0) return
    if (!rangeStartId) setRangeStartId(chapters[0].id)
    if (!rangeEndId) setRangeEndId(chapters[Math.min(chapters.length - 1, 9)].id)
    if (!anchorChapterId) setAnchorChapterId(chapters[Math.min(chapters.length - 1, 9)].id)
    if (selectedCoherenceChapters.length === 0) {
      setSelectedCoherenceChapters(chapters.slice(0, 10).map((c) => c.id))
    }
  }, [anchorChapterId, chapters, rangeEndId, rangeStartId, selectedCoherenceChapters.length])

  const runQualityCheck = async () => {
    if (!projectId || !selectedChapterId) {
      message.warning('请先选择项目与章节')
      return
    }
    setQualityLoading(true)
    try {
      const { data } = await http.post<QualityReport>(
        `/api/v1/projects/${projectId}/ai/quality-check`,
        {
          chapter_id: selectedChapterId,
          model_profile: modelProfile,
          check_types: CHECK_TYPES,
          llm_provider_id: selectedProviderId,
        },
        { timeout: LONG_RUNNING_HTTP_TIMEOUT_MS },
      )
      if (data.error) {
        setQualityReport(null)
        message.error(`单章评测失败：${data.error}`)
        return
      }
      setQualityReport(data)
      message.success('单章评测完成')
      await loadChapters(projectId)
    } catch {
      message.error('单章评测失败')
    } finally {
      setQualityLoading(false)
    }
  }

  const saveCoherenceReport = useCallback(
    async (result: ChapterCoherenceResult) => {
      if (!projectId) return
      setSaveLoading(true)
      try {
        const selectedNos = chapters
          .filter((c) => selectedCoherenceChapters.includes(c.id))
          .map((c) => c.sort_order + 1)
          .sort((a, b) => a - b)
        const chapterRangeText =
          selectedNos.length > 0
            ? selectedNos[0] === selectedNos[selectedNos.length - 1]
              ? `${selectedNos[0]}章`
              : `${selectedNos[0]}-${selectedNos[selectedNos.length - 1]}章`
            : `${selectedCoherenceChapters.length}章`
        const projectTitle = projects.find((p) => p.id === projectId)?.title || '未命名小说'
        const { data: saved } = await http.post<CoherenceReportRecord>(
          `/api/v1/projects/${projectId}/ai/chapter-coherence-reports`,
          {
            name: `${projectTitle}｜${chapterRangeText}`,
            model_profile: modelProfile,
            selected_chapter_ids: selectedCoherenceChapters,
            result,
          },
        )
        setLastSavedCoherenceReport(saved)
        await loadHistory(projectId)
        message.success('连贯性评测完成并已自动保存')
      } catch {
        message.warning('连贯性评测完成，但自动保存失败，可稍后重试')
      } finally {
        setSaveLoading(false)
      }
    },
    [chapters, loadHistory, message, modelProfile, projectId, projects, selectedCoherenceChapters],
  )

  const runCoherenceCheck = async () => {
    if (!projectId) {
      message.warning('请先选择项目')
      return
    }
    if (selectedCoherenceChapters.length < 2) {
      message.warning('至少选择 2 章进行连贯性评测')
      return
    }
    setCoherenceLoading(true)
    setLastSavedCoherenceReport(null)
    try {
      const { data } = await http.post<ChapterCoherenceResult>(
        `/api/v1/projects/${projectId}/ai/chapter-coherence-check`,
        {
          chapter_ids: selectedCoherenceChapters,
          model_profile: modelProfile,
          llm_provider_id: selectedProviderId,
        },
        { timeout: LONG_RUNNING_HTTP_TIMEOUT_MS },
      )
      if (data.error) {
        setCoherenceResult(null)
        message.error(`连贯性评测失败：${data.error}`)
        return
      }
      setCoherenceResult(data)
      await saveCoherenceReport(data)
    } catch {
      message.error('连贯性评测失败')
    } finally {
      setCoherenceLoading(false)
    }
  }

  const applyContinuousRange = useCallback(
    (startId?: string, endId?: string) => {
      if (!startId || !endId) return
      const startIndex = chapters.findIndex((c) => c.id === startId)
      const endIndex = chapters.findIndex((c) => c.id === endId)
      if (startIndex < 0 || endIndex < 0) return
      const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex]
      setSelectedCoherenceChapters(chapters.slice(from, to + 1).map((c) => c.id))
    },
    [chapters],
  )

  const applyAnchorWindow = useCallback(
    (size: number, direction: 'prev' | 'next') => {
      if (!anchorChapterId) return
      const anchorIndex = chapters.findIndex((c) => c.id === anchorChapterId)
      if (anchorIndex < 0) return
      const from = direction === 'prev' ? Math.max(0, anchorIndex - size + 1) : anchorIndex
      const to =
        direction === 'prev' ? anchorIndex : Math.min(chapters.length - 1, anchorIndex + size - 1)
      setRangeStartId(chapters[from]?.id)
      setRangeEndId(chapters[to]?.id)
      setSelectedCoherenceChapters(chapters.slice(from, to + 1).map((c) => c.id))
    },
    [anchorChapterId, chapters],
  )

  const chapterOptions = useMemo(
    () =>
      chapters.map((c) => ({
        label: `第${c.sort_order + 1}章 · ${c.title || '未命名'}${c.last_quality_score != null ? `（${c.last_quality_score}分）` : ''}`,
        value: c.id,
      })),
    [chapters],
  )

  const chapterColumns: ColumnsType<ReviewChapter> = useMemo(
    () => [
      {
        title: '章节',
        dataIndex: 'title',
        render: (_, row) => `第${row.sort_order + 1}章 · ${row.title || '未命名'}`,
      },
      {
        title: '最近评分',
        dataIndex: 'last_quality_score',
        width: 150,
        render: (v: number | undefined) => scoreTag(v),
      },
    ],
    [],
  )

  const overviewScored = chapters.filter((c) => c.last_quality_score != null)
  const overviewAvg = overviewScored.length
    ? Math.round(
        overviewScored.reduce((sum, c) => sum + Number(c.last_quality_score ?? 0), 0) /
          overviewScored.length,
      )
    : undefined
  const lowCount = chapters.filter((c) => Number(c.last_quality_score ?? 100) < 70).length
  const outlineRiskChapters = chapters
    .map((c) => {
      const outlineScore = c.last_quality_report?.dimensions?.outline_alignment?.score
      return {
        id: c.id,
        title: c.title || '未命名',
        chapterNo: c.sort_order + 1,
        score: outlineScore,
      }
    })
    .filter((item) => item.score != null && Number(item.score) < 70)
    .sort((a, b) => Number(a.score) - Number(b.score))

  const compareRows = historyRows.filter((row) => compareIds.includes(row.id))
  const compareA = compareRows[0]
  const compareB = compareRows[1]

  const applyTimeline = useMemo(() => {
    type Row = {
      appliedAt: string
      reportId: string
      reportName: string
      applied: CoherenceApplyChapterResult[]
    }
    const rows: Row[] = []
    for (const r of historyRows) {
      for (const ev of r.apply_events ?? []) {
        if (ev?.applied_at && Array.isArray(ev.applied)) {
          rows.push({
            appliedAt: ev.applied_at,
            reportId: r.id,
            reportName: r.name,
            applied: ev.applied,
          })
        }
      }
    }
    rows.sort((a, b) => new Date(b.appliedAt).getTime() - new Date(a.appliedAt).getTime())
    return rows
  }, [historyRows])

  const selectedCoherenceChapterNos = chapters
    .filter((c) => selectedCoherenceChapters.includes(c.id))
    .map((c) => c.sort_order + 1)
    .sort((a, b) => a - b)
  const selectedRangeHint = selectedCoherenceChapterNos.length
    ? `第${selectedCoherenceChapterNos[0]}章 ~ 第${selectedCoherenceChapterNos[selectedCoherenceChapterNos.length - 1]}章`
    : '尚未选择章节'

  const goToChapterEditor = useCallback(
    (chapterId: string) => {
      if (!projectId) return
      navigate(`/novels?projectId=${projectId}&chapterId=${chapterId}`)
    },
    [navigate, projectId],
  )

  return {
    navigate,
    loading,
    projects,
    projectId,
    setProjectId,
    chapters,
    llmOverview,
    selectedModelOption,
    setSelectedModelOption,
    selectedChapterId,
    setSelectedChapterId,
    qualityLoading,
    qualityReport,
    coherenceLoading,
    selectedCoherenceChapters,
    setSelectedCoherenceChapters,
    rangeStartId,
    setRangeStartId,
    rangeEndId,
    setRangeEndId,
    anchorChapterId,
    setAnchorChapterId,
    coherenceResult,
    saveLoading,
    historyLoading,
    historyRows,
    compareIds,
    setCompareIds,
    lastSavedCoherenceReport,
    chapterOptions,
    chapterColumns,
    overviewAvg,
    lowCount,
    outlineRiskChapters,
    compareA,
    compareB,
    applyTimeline,
    selectedRangeHint,
    runQualityCheck,
    runCoherenceCheck,
    applyContinuousRange,
    applyAnchorWindow,
    formatApplyChapterLine,
    goToChapterEditor,
    versionTimelineLoading,
    versionTimelineRows,
    versionPreviewOpen,
    versionPreviewLoading,
    versionPreviewPanels,
    versionPreviewModalTitle,
    openSnapshotBeforeAfterPreview,
    closeVersionPreview,
    ...revision,
  }
}

export type ReadingReviewPageState = ReturnType<typeof useReadingReviewPage>
