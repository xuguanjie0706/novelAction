import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { BookOpen, CheckCircle2, History, Link2, Sparkles } from 'lucide-react'
import { aiApi, chaptersApi, projectsApi } from '../api/client'
import LlmAgentMenu from '../components/Layout/LlmAgentMenu'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload } from '../store'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import { useHomeSidebarNavigate } from '../hooks/useHomeSidebarNavigate'
import type { Chapter, Project } from '../types'

type ModelProfile = 'local' | 'gemini'

interface CoherenceReport {
  title_match_score?: number
  continuity_score?: number
  overall_score?: number
  chapter_evaluations?: Array<{
    chapter_id: string
    chapter_title: string
    title_match_score: number
    title_match_comment: string
    risk_level: string
  }>
  cross_chapter_issues?: Array<{
    type: string
    severity: string
    description: string
  }>
  suggestions?: string[]
  summary?: string
  error?: string
}

interface CoherenceApplyEventRecord {
  applied_at: string
  applied: Array<{ chapter_id: string; skipped: boolean; word_count?: number; reason?: string }>
}

interface CoherenceReportHistoryItem {
  id: string
  name: string
  model_profile: ModelProfile
  selected_chapter_ids: string[]
  result: CoherenceReport
  apply_events?: CoherenceApplyEventRecord[]
  created_at: string
}

interface CoherenceApplyRevisionRow {
  chapter_id: string
  chapter_title: string
  unchanged: boolean
  change_note: string
  revised_content: string
  previous_plain_preview: string
  revised_plain_preview: string
}

export default function ChapterCoherencePage() {
  const navigate = useNavigate()
  const setCurrentProject = useAppStore(s => s.setCurrentProject)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([])
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [loadingChapters, setLoadingChapters] = useState(false)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [report, setReport] = useState<CoherenceReport | null>(null)
  const [history, setHistory] = useState<CoherenceReportHistoryItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const [applyDialogOpen, setApplyDialogOpen] = useState(false)
  const [applyReportId, setApplyReportId] = useState<string | null>(null)
  const [applyPreviewRows, setApplyPreviewRows] = useState<CoherenceApplyRevisionRow[]>([])
  const [applyPreviewLoading, setApplyPreviewLoading] = useState(false)
  const [applyCommitLoading, setApplyCommitLoading] = useState(false)

  useEffect(() => {
    setLoadingProjects(true)
    projectsApi.list()
      .then(res => {
        const list = res.data as Project[]
        setProjects(list)
        if (list[0]) setSelectedProjectId(list[0].id)
      })
      .catch(() => {
        setProjects([])
      })
      .finally(() => setLoadingProjects(false))
  }, [])

  useEffect(() => {
    if (!selectedProjectId) {
      setChapters([])
      setSelectedChapterIds([])
      return
    }
    setLoadingChapters(true)
    chaptersApi.list(selectedProjectId)
      .then(res => setChapters(res.data as Chapter[]))
      .catch(() => setChapters([]))
      .finally(() => setLoadingChapters(false))
    setSelectedChapterIds([])
    setReport(null)
    setHistory([])
    setLoadingHistory(true)
    aiApi.listChapterCoherenceReports(selectedProjectId, 20)
      .then(res => setHistory(res.data as CoherenceReportHistoryItem[]))
      .catch(() => setHistory([]))
      .finally(() => setLoadingHistory(false))
  }, [selectedProjectId])

  const selectedProject = useMemo(
    () => projects.find(p => p.id === selectedProjectId),
    [projects, selectedProjectId]
  )

  const canCheck = selectedProjectId && selectedChapterIds.length >= 2 && !checking

  const handleSidebarNavigate = useHomeSidebarNavigate({
    projects,
    activeId: 'coherence',
    navigate,
    setCurrentProject,
  })

  const persistReport = async (
    result: CoherenceReport,
    options?: { silent?: boolean }
  ) => {
    if (!selectedProjectId) return false
    setSaving(true)
    try {
      const res = await aiApi.saveChapterCoherenceReport(selectedProjectId, {
        model_profile: modelProfileFromRoute(aiBackendRoute),
        selected_chapter_ids: selectedChapterIds,
        result: result as Record<string, any>,
      })
      const newItem = res.data as CoherenceReportHistoryItem
      setHistory(prev => [newItem, ...prev])
      if (!options?.silent) toast.success('评测记录已保存')
      return true
    } catch {
      if (!options?.silent) toast.error('评测记录保存失败')
      return false
    } finally {
      setSaving(false)
    }
  }

  const toggleChapter = (chapterId: string) => {
    setSelectedChapterIds(prev =>
      prev.includes(chapterId) ? prev.filter(id => id !== chapterId) : [...prev, chapterId]
    )
  }

  const check = async () => {
    if (!selectedProjectId) return toast.error('请先选择小说')
    if (selectedChapterIds.length < 2) return toast.error('至少选择2章进行检测')
    setChecking(true)
    setReport(null)
    try {
      const res = await aiApi.chapterCoherenceCheck(selectedProjectId, {
        chapter_ids: selectedChapterIds,
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...routeLlmProviderPayload(aiBackendRoute),
      })
      const result = res.data as CoherenceReport
      if (result.error) {
        setReport(null)
        toast.error(`检测失败：${result.error}`)
        return
      }
      setReport(result)
      const saved = await persistReport(result, { silent: true })
      if (saved) {
        toast.success('检测完成，记录已自动保存')
      } else {
        toast('检测完成，但自动保存失败，可手动重试', { icon: '⚠️' })
      }
    } catch (err: unknown) {
      setReport(null)
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : '检测请求失败，请查看后端日志或更换大模型线路'
      toast.error(msg)
    } finally {
      setChecking(false)
    }
  }

  const saveCurrentReport = async () => {
    if (!report) return
    await persistReport(report)
  }

  const openApplyPreview = async (reportId: string) => {
    if (!selectedProjectId) return toast.error('请先选择小说')
    setApplyPreviewLoading(true)
    setApplyReportId(reportId)
    try {
      const res = await aiApi.chapterCoherenceApplyPreview(selectedProjectId, {
        report_id: reportId,
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...routeLlmProviderPayload(aiBackendRoute),
      })
      const rows = (res.data as { revisions?: CoherenceApplyRevisionRow[] }).revisions ?? []
      setApplyPreviewRows(rows)
      setApplyDialogOpen(true)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join('；') || '修订预览失败'
            : '修订预览失败'
      toast.error(msg)
      setApplyReportId(null)
    } finally {
      setApplyPreviewLoading(false)
    }
  }

  const commitApplyRevisions = async () => {
    if (!selectedProjectId || !applyReportId) return
    const payload = applyPreviewRows.filter(r => !r.unchanged && r.revised_content.trim())
    if (payload.length === 0) {
      toast.error('预览中无可写入的修订（可能模型判定均无需改动）')
      return
    }
    if (
      !window.confirm(
        `将把 ${payload.length} 章的修订写入正文，并在每章自动保存一条修订前快照。是否继续？`
      )
    ) {
      return
    }
    setApplyCommitLoading(true)
    try {
      await aiApi.chapterCoherenceApplyCommit(selectedProjectId, {
        report_id: applyReportId,
        revisions: payload.map(r => ({ chapter_id: r.chapter_id, revised_content: r.revised_content })),
      })
      toast.success('已写入正文')
      setApplyDialogOpen(false)
      setApplyPreviewRows([])
      setApplyReportId(null)
      const chRes = await chaptersApi.list(selectedProjectId)
      setChapters(chRes.data as Chapter[])
      const hRes = await aiApi.listChapterCoherenceReports(selectedProjectId, 20)
      setHistory(hRes.data as CoherenceReportHistoryItem[])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : '写入失败'
      toast.error(msg)
    } finally {
      setApplyCommitLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      <HomeSidebar todayWords={0} onNavigate={handleSidebarNavigate} activeId="coherence" />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />
        <main className="min-w-0 flex-1 overflow-auto px-5 py-6 sm:px-8">
          <div className="mx-auto max-w-6xl space-y-5">
            <header className="rounded-2xl border border-amber-100 bg-white/95 p-5 shadow-[0_10px_30px_rgba(245,158,11,0.08)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
                <Link2 size={14} />
                连贯性工作台
              </div>
              <h1 className="mt-2 text-xl font-bold text-gray-900">章节连贯性检测</h1>
              <p className="mt-1 text-sm text-gray-500">
                流程：选择小说 → 勾选章节 → 检测标题匹配与剧情连贯性
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-amber-700 hover:bg-amber-50"
            >
              返回首页
            </button>
          </div>
            </header>

            <section className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-800">
              <BookOpen size={16} className="text-amber-600" />
              1) 选择小说
            </div>
            <div className="mt-3">
              <select
                value={selectedProjectId}
                onChange={e => setSelectedProjectId(e.target.value)}
                className="w-full rounded-lg border border-amber-100 bg-amber-50/30 px-3 py-2 text-sm outline-none focus:border-amber-400"
                disabled={loadingProjects}
              >
                <option value="">请选择小说</option>
                {projects.map(project => (
                  <option key={project.id} value={project.id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-4 flex items-center gap-2 text-sm font-semibold text-gray-800">
              <Sparkles size={16} className="text-amber-600" />
              2) 模型 / 线路
            </div>
            <div className="mt-2 w-full min-w-0">
              <LlmAgentMenu />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-gray-500">
              与写作页、AI 助手共用全局线路；远程可指定具体 Provider。修订多章正文时远程线路通常一次批量处理，本地线路将逐章调用。
            </p>

            <button
              type="button"
              onClick={check}
              disabled={!canCheck}
              className="mt-4 w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(245,158,11,0.3)] disabled:cursor-not-allowed disabled:bg-gray-300 disabled:shadow-none"
            >
              {checking ? '检测中...' : `3) 开始检测（已选 ${selectedChapterIds.length} 章）`}
            </button>
          </div>

          <div className="space-y-5">
            <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-800">章节列表（可多选）</div>
                {selectedProject && (
                  <div className="text-xs text-gray-500">当前小说：{selectedProject.title}</div>
                )}
              </div>
              <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
                {loadingChapters && (
                  <div className="rounded-lg border border-dashed border-amber-200 p-4 text-sm text-gray-500">
                    正在加载章节...
                  </div>
                )}
                {!loadingChapters && chapters.length === 0 && (
                  <div className="rounded-lg border border-dashed border-amber-200 p-4 text-sm text-gray-500">
                    该小说暂无章节
                  </div>
                )}
                {chapters.map(chapter => (
                  <label
                    key={chapter.id}
                    className="flex cursor-pointer items-center justify-between rounded-lg border border-amber-100 px-3 py-2 hover:bg-amber-50/40"
                  >
                    <div className="min-w-0 pr-3">
                      <div className="truncate text-sm font-medium text-gray-800">{chapter.title}</div>
                      <div className="text-xs text-gray-500">
                        第 {chapter.sort_order + 1} 章 · {chapter.word_count} 字
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={selectedChapterIds.includes(chapter.id)}
                      onChange={() => toggleChapter(chapter.id)}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                  </label>
                ))}
              </div>
            </div>

            {report && (
              <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-gray-800">
                    <CheckCircle2 size={16} className="text-amber-600" />
                    检测结果
                  </div>
                  <button
                    type="button"
                    onClick={saveCurrentReport}
                    disabled={saving || checking}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saving ? '保存中...' : '重新保存本次检测'}
                  </button>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-3 text-sm">
                    <div className="text-gray-500">标题匹配分</div>
                    <div className="mt-1 text-xl font-bold text-gray-900">{report.title_match_score ?? '-'}</div>
                  </div>
                  <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-3 text-sm">
                    <div className="text-gray-500">剧情连贯分</div>
                    <div className="mt-1 text-xl font-bold text-gray-900">{report.continuity_score ?? '-'}</div>
                  </div>
                  <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-3 text-sm">
                    <div className="text-gray-500">综合分</div>
                    <div className="mt-1 text-xl font-bold text-gray-900">{report.overall_score ?? '-'}</div>
                  </div>
                </div>

                {report.summary && (
                  <div className="mt-4 rounded-lg border border-amber-100 bg-amber-50/60 p-3 text-sm text-amber-900">
                    {report.summary}
                  </div>
                )}

                {!!report.cross_chapter_issues?.length && (
                  <div className="mt-4">
                    <div className="mb-2 text-sm font-semibold text-gray-800">跨章节问题</div>
                    <div className="space-y-2">
                      {report.cross_chapter_issues?.map((issue, idx) => (
                        <div key={`${issue.type}-${idx}`} className="rounded-lg border border-amber-100 p-3 text-sm">
                          <div className="font-medium text-gray-800">
                            [{issue.severity}] {issue.type}
                          </div>
                          <div className="mt-1 text-gray-600">{issue.description}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!!report.suggestions?.length && (
                  <div className="mt-4">
                    <div className="mb-2 text-sm font-semibold text-gray-800">修改建议</div>
                    <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">
                      {report.suggestions?.map((item, idx) => (
                        <li key={`suggestion-${idx}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {report.error && (
                  <div className="mt-4 rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-red-700">
                    返回解析失败：{report.error}
                  </div>
                )}
              </div>
            )}

            <div className="rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-800">
                <History size={16} className="text-amber-600" />
                历史记录
              </div>
              {loadingHistory && (
                <div className="rounded-lg border border-dashed border-amber-200 p-3 text-sm text-gray-500">
                  正在加载历史记录...
                </div>
              )}
              {!loadingHistory && history.length === 0 && (
                <div className="rounded-lg border border-dashed border-amber-200 p-3 text-sm text-gray-500">
                  暂无历史记录
                </div>
              )}
              <div className="space-y-2">
                {history.map(item => (
                  <div
                    key={item.id}
                    className="flex gap-2 rounded-lg border border-amber-100 p-2 hover:bg-amber-50/40"
                  >
                    <button
                      type="button"
                      onClick={() => setReport(item.result)}
                      className="min-w-0 flex-1 rounded-md px-2 py-1 text-left"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate text-sm font-medium text-gray-800">{item.name}</div>
                        <div className="shrink-0 text-xs text-gray-500">
                          {new Date(item.created_at).toLocaleString('zh-CN')}
                        </div>
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        {item.model_profile === 'gemini' ? '远程模型' : '本地模型'} ·
                        {' '}
                        {item.selected_chapter_ids.length} 章 · 综合分 {item.result?.overall_score ?? '-'}
                        {item.apply_events?.length ? ` · 已改正文 ${item.apply_events.length} 次` : ''}
                      </div>
                    </button>
                    <button
                      type="button"
                      disabled={applyPreviewLoading || !!item.result?.error}
                      title={item.result?.error ? '该记录解析失败，无法用于修订' : '按本评测结论最小幅度改正文'}
                      onClick={() => void openApplyPreview(item.id)}
                      className="shrink-0 self-center rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {applyPreviewLoading && applyReportId === item.id ? '生成中…' : '按评测改正文'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
            </section>

            {applyDialogOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div
              className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl"
              role="dialog"
              aria-modal="true"
              aria-labelledby="coherence-apply-title"
            >
              <div className="border-b border-gray-100 px-4 py-3">
                <h2 id="coherence-apply-title" className="text-base font-semibold text-gray-900">
                  根据评测修订正文（预览）
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  仅应用模型在预览中给出的修订稿，不会整章重写；写入前会为每章自动保存修订前快照。
                </p>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
                <div className="space-y-3">
                  {applyPreviewRows.map(row => (
                    <div key={row.chapter_id} className="rounded-lg border border-gray-100 p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-gray-800">{row.chapter_title || row.chapter_id}</span>
                        {row.unchanged ? (
                          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">未改动</span>
                        ) : (
                          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">有修订</span>
                        )}
                      </div>
                      {row.change_note && (
                        <p className="mt-2 text-xs text-gray-600">{row.change_note}</p>
                      )}
                      {!row.unchanged && (
                        <div className="mt-2 grid gap-2 text-xs text-gray-600 sm:grid-cols-2">
                          <div>
                            <div className="font-medium text-gray-700">修前摘要</div>
                            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2">
                              {row.previous_plain_preview}
                            </pre>
                          </div>
                          <div>
                            <div className="font-medium text-gray-700">修后摘要</div>
                            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-amber-50/50 p-2">
                              {row.revised_plain_preview}
                            </pre>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-gray-100 px-4 py-3">
                <button
                  type="button"
                  onClick={() => {
                    setApplyDialogOpen(false)
                    setApplyPreviewRows([])
                    setApplyReportId(null)
                  }}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={applyCommitLoading || applyPreviewRows.every(r => r.unchanged || !r.revised_content.trim())}
                  onClick={() => void commitApplyRevisions()}
                  className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  {applyCommitLoading ? '写入中…' : '写入数据库'}
                </button>
              </div>
            </div>
          </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
