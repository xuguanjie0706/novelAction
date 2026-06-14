/**
 * @file pages/Dabai/detail/index.tsx — 大白文「我的小说」详情页（编排壳）。
 *
 * 职责：
 * - 从 /api/v1/dabai 拉取单本完整详情（dabaiApi.get）
 * - 顶部展示书名 / 创意 / 卷·章·质检统计，提供「进入写作台」「返回书架」
 * - 左侧 rose 主题分区导航（仅显示有内容的分区），右侧 SectionBody 富内容
 * - 卷纲质检支持就地重检（dabaiApi.relintOutline）
 *
 * 路由：/dabai/:projectId（书架卡片点击进入；写作台入口在本页）
 * 设计取向：与精品文纪要页（棕金 + 通用设定表）刻意区隔——大白文聚焦
 *   爽点流水线（对标 / 金手指 / 反派阶梯 / 谜题排程 / 爽点节拍），rose 视觉。
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Loader2, PenLine, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { dabaiApi } from '../../../api/dabai'
import type { DabaiProjectDetail } from '../../../types/dabai'
import { visibleSections } from './sections'
import SectionBody from './SectionBody'

export default function DabaiDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [detail, setDetail] = useState<DabaiProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('overview')
  const [relinting, setRelinting] = useState(false)

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!projectId) return
    if (!opts?.silent) { setLoading(true); setError('') }
    try {
      const res = await dabaiApi.get(projectId)
      setDetail(res.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败，请稍后重试')
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [projectId])

  useEffect(() => { void load() }, [load])

  const handleRelint = useCallback(async () => {
    if (!projectId) return
    setRelinting(true)
    try {
      const res = await dabaiApi.relintOutline(projectId)
      setDetail(prev => (prev ? { ...prev, linter_report: res.data.linter_report } : prev))
      const score = res.data.linter_report?.score
      toast.success(score != null ? `质检完成 · ${score} 分` : '质检完成')
    } catch {
      toast.error('质检失败，请重试')
    } finally {
      setRelinting(false)
    }
  }, [projectId])

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#fdf2f4]">
        <Loader2 size={30} className="animate-spin text-rose-500" />
        <p className="text-sm text-gray-400">加载小说详情…</p>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#fdf2f4]">
        <AlertCircle size={30} className="text-rose-500" />
        <p className="text-sm text-gray-500">{error || '小说不存在'}</p>
        <button
          type="button"
          onClick={() => navigate('/dabai')}
          className="mt-1 rounded-lg border border-gray-200 bg-white px-5 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          返回书架
        </button>
      </div>
    )
  }

  const sections = visibleSections(detail)
  const active = sections.find(s => s.id === selected) ?? sections[0]
  const title = detail.title || detail.logline
  const chapterCount = detail.chapter_outlines.length

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#fdf2f4]">
      {/* ── 顶部条 ─────────────────────────────────────── */}
      <header className="flex flex-wrap items-center gap-3 border-b border-rose-100 bg-white px-6 py-3.5 shadow-sm">
        <button
          type="button"
          onClick={() => navigate('/dabai')}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          title="返回书架"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-2">
          <Zap size={20} className="text-rose-500" />
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold text-gray-900">{title}</h1>
            <p className="truncate text-xs text-gray-400">
              {detail.volumes.length} 卷 · {chapterCount} 章
              {detail.linter_report?.score != null ? ` · 质检 ${detail.linter_report.score}` : ''}
              {detail.mock ? ' · 样例' : ''}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => navigate(`/dabai/${projectId}/write-dabailab`)}
          className="ml-auto flex h-10 items-center gap-2 rounded-lg bg-rose-500 px-5 text-sm font-semibold text-white shadow-md hover:bg-rose-600"
        >
          <PenLine size={16} />
          进入写作台
        </button>
      </header>

      {/* ── 主体：左导航 + 右内容 ───────────────────────── */}
      <div className="flex min-h-0 flex-1">
        <nav className="w-52 shrink-0 overflow-y-auto border-r border-rose-100 bg-white/70 py-3">
          <div className="px-4 pb-2 text-[10px] font-bold uppercase tracking-wider text-gray-400">
            生成纪要
          </div>
          {sections.map(s => {
            const isActive = s.id === active.id
            const count = s.count(detail)
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setSelected(s.id)}
                className={`flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm transition-colors ${
                  isActive ? 'bg-rose-50 font-semibold text-rose-600' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <span style={{ color: isActive ? s.accent : '#9ca3af' }}>{s.icon}</span>
                <span className="flex-1">{s.label}</span>
                {count > 0 ? (
                  <span className={`rounded-full px-1.5 text-[11px] ${
                    isActive ? 'bg-rose-100 text-rose-600' : 'bg-gray-100 text-gray-400'
                  }`}>
                    {count}
                  </span>
                ) : null}
              </button>
            )
          })}
        </nav>

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-gray-100 bg-white/90 px-6 py-3 backdrop-blur">
            <span style={{ color: active.accent }}>{active.icon}</span>
            <h2 className="text-base font-bold text-gray-900">{active.label}</h2>
          </div>
          <div className="mx-auto max-w-4xl px-6 py-6">
            <SectionBody
              sectionId={active.id}
              projectId={projectId!}
              d={detail}
              onRelint={handleRelint}
              relinting={relinting}
            />
          </div>
        </main>
      </div>
    </div>
  )
}
