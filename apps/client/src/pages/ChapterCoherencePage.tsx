import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Link } from 'react-router-dom'
import { aiApi, chaptersApi, projectsApi } from '../api/client'
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

interface CoherenceReportHistoryItem {
  id: string
  name: string
  model_profile: ModelProfile
  selected_chapter_ids: string[]
  result: CoherenceReport
  created_at: string
}

export default function ChapterCoherencePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([])
  const [modelProfile, setModelProfile] = useState<ModelProfile>('local')
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [loadingChapters, setLoadingChapters] = useState(false)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [report, setReport] = useState<CoherenceReport | null>(null)
  const [history, setHistory] = useState<CoherenceReportHistoryItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

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
        model_profile: modelProfile,
      })
      setReport(res.data as CoherenceReport)
      toast.success('检测完成')
    } catch {
      setReport(null)
    } finally {
      setChecking(false)
    }
  }

  const saveCurrentReport = async () => {
    if (!selectedProjectId || !report) return
    setSaving(true)
    try {
      const res = await aiApi.saveChapterCoherenceReport(selectedProjectId, {
        model_profile: modelProfile,
        selected_chapter_ids: selectedChapterIds,
        result: report as Record<string, any>,
      })
      const newItem = res.data as CoherenceReportHistoryItem
      setHistory(prev => [newItem, ...prev])
      toast.success('已保存到检测历史')
    } catch {
      // noop
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] px-5 py-6 sm:px-8">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="rounded-xl border border-gray-100 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold text-gray-900">章节连贯性检测</h1>
              <p className="mt-1 text-sm text-gray-500">
                流程：选择小说 → 勾选章节 → 检测标题匹配与剧情连贯性
              </p>
            </div>
            <Link
              to="/"
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              返回首页
            </Link>
          </div>
        </header>

        <section className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <div className="rounded-xl border border-gray-100 bg-white p-4">
            <div className="text-sm font-semibold text-gray-800">1) 选择小说</div>
            <div className="mt-3">
              <select
                value={selectedProjectId}
                onChange={e => setSelectedProjectId(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-amber-400"
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

            <div className="mt-4 text-sm font-semibold text-gray-800">2) 选择模型</div>
            <div className="mt-2">
              <select
                value={modelProfile}
                onChange={e => setModelProfile(e.target.value as ModelProfile)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-amber-400"
              >
                <option value="local">本地模型</option>
                <option value="gemini">远程模型（Gemini）</option>
              </select>
            </div>

            <button
              type="button"
              onClick={check}
              disabled={!canCheck}
              className="mt-4 w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {checking ? '检测中...' : `3) 开始检测（已选 ${selectedChapterIds.length} 章）`}
            </button>
          </div>

          <div className="space-y-5">
            <div className="rounded-xl border border-gray-100 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-800">章节列表（可多选）</div>
                {selectedProject && (
                  <div className="text-xs text-gray-500">当前小说：{selectedProject.title}</div>
                )}
              </div>
              <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
                {loadingChapters && (
                  <div className="rounded-lg border border-dashed border-gray-200 p-4 text-sm text-gray-500">
                    正在加载章节...
                  </div>
                )}
                {!loadingChapters && chapters.length === 0 && (
                  <div className="rounded-lg border border-dashed border-gray-200 p-4 text-sm text-gray-500">
                    该小说暂无章节
                  </div>
                )}
                {chapters.map(chapter => (
                  <label
                    key={chapter.id}
                    className="flex cursor-pointer items-center justify-between rounded-lg border border-gray-100 px-3 py-2 hover:bg-gray-50"
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
              <div className="rounded-xl border border-gray-100 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-gray-800">检测结果</div>
                  <button
                    type="button"
                    onClick={saveCurrentReport}
                    disabled={saving || checking}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saving ? '保存中...' : '保存本次检测'}
                  </button>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg bg-gray-50 p-3 text-sm">
                    <div className="text-gray-500">标题匹配分</div>
                    <div className="mt-1 text-xl font-bold text-gray-900">{report.title_match_score ?? '-'}</div>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 text-sm">
                    <div className="text-gray-500">剧情连贯分</div>
                    <div className="mt-1 text-xl font-bold text-gray-900">{report.continuity_score ?? '-'}</div>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 text-sm">
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
                        <div key={`${issue.type}-${idx}`} className="rounded-lg border border-gray-100 p-3 text-sm">
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

            <div className="rounded-xl border border-gray-100 bg-white p-4">
              <div className="mb-2 text-sm font-semibold text-gray-800">历史记录</div>
              {loadingHistory && (
                <div className="rounded-lg border border-dashed border-gray-200 p-3 text-sm text-gray-500">
                  正在加载历史记录...
                </div>
              )}
              {!loadingHistory && history.length === 0 && (
                <div className="rounded-lg border border-dashed border-gray-200 p-3 text-sm text-gray-500">
                  暂无历史记录
                </div>
              )}
              <div className="space-y-2">
                {history.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setReport(item.result)}
                    className="w-full rounded-lg border border-gray-100 px-3 py-2 text-left hover:bg-gray-50"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="truncate text-sm font-medium text-gray-800">{item.name}</div>
                      <div className="shrink-0 text-xs text-gray-500">
                        {new Date(item.created_at).toLocaleString('zh-CN')}
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {item.model_profile === 'gemini' ? '远程模型' : '本地模型'} ·
                      {' '} {item.selected_chapter_ids.length} 章 ·
                      {' '} 综合分 {item.result?.overall_score ?? '-'}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
