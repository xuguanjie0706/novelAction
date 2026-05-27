import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, BookOpen, ChevronRight, Loader2, Plus, Search, Sparkles, Trash2 } from 'lucide-react'
import { bootstrapRunsApi, projectsApi } from '../api/client'
import { useAppStore } from '../store'
import type { Project } from '../types'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import ActiveBootstrapResumeBar from '../components/Bootstrap/ActiveBootstrapResumeBar'
import { useBootstrapResumeBanner } from '../hooks/useBootstrapResumeBanner'
import {
  CreateProjectDialog,
} from '../components/Home/HomeDashboardSections'
import toast from 'react-hot-toast'
import { clearActiveBootstrapRun, readActiveBootstrapRun } from '../utils/bootstrapActiveRun'

// ── 封面渐变方案（按类型） ──────────────────────────────
const GENRE_GRADIENTS: Record<string, { from: string; to: string; accent: string }> = {
  '玄幻':   { from: '#7c3aed', to: '#4f46e5', accent: '#c4b5fd' },
  '修真':   { from: '#6d28d9', to: '#1e1b4b', accent: '#a78bfa' },
  '仙侠':   { from: '#9333ea', to: '#c026d3', accent: '#f0abfc' },
  '都市':   { from: '#0ea5e9', to: '#2563eb', accent: '#bae6fd' },
  '现代':   { from: '#0284c7', to: '#0f172a', accent: '#7dd3fc' },
  '悬疑':   { from: '#374151', to: '#0f172a', accent: '#9ca3af' },
  '惊悚':   { from: '#1f2937', to: '#450a0a', accent: '#ef4444' },
  '历史':   { from: '#92400e', to: '#78350f', accent: '#fcd34d' },
  '古言':   { from: '#b45309', to: '#92400e', accent: '#fde68a' },
  '言情':   { from: '#db2777', to: '#9d174d', accent: '#fbcfe8' },
  '科幻':   { from: '#0f766e', to: '#134e4a', accent: '#5eead4' },
  '奇幻':   { from: '#059669', to: '#1e3a5f', accent: '#a7f3d0' },
  '武侠':   { from: '#b91c1c', to: '#7f1d1d', accent: '#fca5a5' },
  default:  { from: '#d97706', to: '#92400e', accent: '#fde68a' },
}

function getGradient(genre?: string) {
  if (!genre) return GENRE_GRADIENTS.default
  for (const key of Object.keys(GENRE_GRADIENTS)) {
    if (genre.includes(key)) return GENRE_GRADIENTS[key]
  }
  return GENRE_GRADIENTS.default
}

/** 书架删除：与 TopBar 重置弹窗同一套白卡 + 警示区，替代原生 confirm。 */
function BookshelfDeleteConfirmModal({
  project,
  onConfirm,
  onCancel,
  loading,
}: {
  project: Project
  onConfirm: () => void
  onCancel: () => void
  loading: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [loading, onCancel])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="bookshelf-delete-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-md rounded-2xl border border-gray-100 bg-white p-6 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="shrink-0 rounded-xl bg-red-50 p-2">
            <AlertTriangle size={20} className="text-red-500" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="bookshelf-delete-title" className="text-base font-bold text-gray-900">
              从书架删除作品
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-gray-600">
              确定删除
              <span className="mx-0.5 font-semibold text-gray-900">「{project.title}」</span>
              ？
            </p>
            <div className="mt-3 rounded-xl border border-red-100 bg-red-50/80 px-3 py-2.5 text-xs leading-relaxed text-red-800/90">
              将永久删除该小说及章节、设定等全部数据，且不可恢复。
            </div>
          </div>
        </div>

        <div className="mt-6 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="flex-1 rounded-xl bg-gray-100 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 rounded-xl bg-red-500 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}

function statusLabel(status: Project['status']) {
  return { drafting: '规划中', writing: '连载中', completed: '已完成' }[status] ?? '规划中'
}

function statusColor(status: Project['status']) {
  return {
    drafting:  'bg-amber-100 text-amber-700',
    writing:   'bg-emerald-100 text-emerald-700',
    completed: 'bg-blue-100 text-blue-700',
  }[status] ?? 'bg-gray-100 text-gray-600'
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

// ── 单本书卡片 ─────────────────────────────────────────
function BookCard({
  project,
  onOpen,
  onDelete,
  deleting,
}: {
  project: Project
  onOpen: () => void
  onDelete: (project: Project) => void
  deleting: boolean
}) {
  const g = getGradient(project.genre)
  const updatedAt = project.updated_at ?? project.created_at

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-gray-100 bg-white text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
    >
      {/* 封面 */}
      <div className="relative h-48 w-full overflow-hidden">
        {project.cover_url ? (
          <img
            src={project.cover_url}
            alt={project.title}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div
            className="flex h-full w-full flex-col items-center justify-center px-4 text-center transition-transform duration-300 group-hover:scale-105"
            style={{ background: `linear-gradient(145deg, ${g.from}, ${g.to})` }}
          >
            {/* 装饰线 */}
            <div
              className="absolute left-3 top-0 h-full w-px opacity-20"
              style={{ background: g.accent }}
            />
            <div
              className="absolute left-5 top-0 h-full w-px opacity-10"
              style={{ background: g.accent }}
            />
            {/* 书名 */}
            <span
              className="z-10 line-clamp-3 text-lg font-bold leading-snug drop-shadow"
              style={{ color: g.accent }}
            >
              {project.title}
            </span>
            {project.genre && (
              <span
                className="z-10 mt-2 text-xs font-medium opacity-70"
                style={{ color: g.accent }}
              >
                {project.genre}
              </span>
            )}
          </div>
        )}

        {/* 悬浮进入箭头 */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all duration-200 group-hover:bg-black/20 group-hover:opacity-100">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 shadow-lg">
            <ChevronRight size={20} className="text-gray-800" />
          </div>
        </div>

        {/* 状态角标 */}
        <div className="absolute right-2 top-2">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold shadow-sm ${statusColor(project.status)}`}>
            {statusLabel(project.status)}
          </span>
        </div>
      </div>

      {/* 信息区 */}
      <div className="flex flex-1 flex-col gap-1 px-4 py-3">
        <h3 className="line-clamp-1 text-[15px] font-semibold text-gray-900 group-hover:text-amber-600 transition-colors">
          {project.title}
        </h3>
        {project.logline && (
          <p className="line-clamp-2 text-[12px] leading-relaxed text-gray-500">
            {project.logline}
          </p>
        )}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          {project.target_words ? (
            <span className="text-[11px] text-gray-400">
              目标 {(project.target_words / 10000).toFixed(0)} 万字
            </span>
          ) : (
            <span />
          )}
          <div className="flex shrink-0 items-center gap-1.5">
            <span className="text-[11px] text-gray-400">{timeAgo(updatedAt)}</span>
            <button
              type="button"
              title="从书架删除"
              aria-label={`删除《${project.title}》`}
              disabled={deleting}
              onClick={(e) => {
                e.stopPropagation()
                e.preventDefault()
                onDelete(project)
              }}
              className="rounded p-1 text-gray-400 opacity-100 transition hover:bg-red-50 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 空书架占位 ─────────────────────────────────────────
function EmptyShelf({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-amber-50">
        <BookOpen size={36} className="text-amber-400" />
      </div>
      <h3 className="mt-5 text-xl font-bold text-gray-900">书架还是空的</h3>
      <p className="mt-2 max-w-xs text-sm text-gray-500">
        创建你的第一部小说，从一句话创意开始，AI 帮你构建完整的世界
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-7 flex items-center gap-2 rounded-lg bg-amber-500 px-6 py-3 text-sm font-semibold text-white shadow-md transition-colors hover:bg-amber-600"
      >
        <Sparkles size={16} />
        AI 一键生成小说
      </button>
    </div>
  )
}

// ── 主页面 ─────────────────────────────────────────────
export default function BookshelfPage() {
  const navigate = useNavigate()
  const { setCurrentProject, removeGenTask } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [deleteConfirmProject, setDeleteConfirmProject] = useState<Project | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)
  const [wizardRecoverRunId, setWizardRecoverRunId] = useState<string | null>(null)
  const [resumeBarHidden, setResumeBarHidden] = useState(false)
  const [resumeCancelLoading, setResumeCancelLoading] = useState(false)
  const { snapshot: bootstrapResumeSnapshot, refresh: refreshBootstrapResume } = useBootstrapResumeBanner()
  const [showForm, setShowForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ title: '', genre: '', logline: '', premise: '', target_words: 1200000 })

  useEffect(() => {
    projectsApi.list()
      .then(res => setProjects(res.data))
      .catch(() => {
        setProjects([])
        toast.error('加载书架失败')
      })
      .finally(() => setLoading(false))
  }, [])

  const onWizardClose = () => {
    setShowWizard(false)
    setWizardRecoverRunId(null)
    void refreshBootstrapResume()
    projectsApi.list().then(res => setProjects(res.data)).catch(() => {})
  }

  const handleCancelBootstrapRun = async () => {
    const rid = bootstrapResumeSnapshot?.runId?.trim()
    if (!rid) return
    setResumeCancelLoading(true)
    try {
      await bootstrapRunsApi.cancel(rid)
      clearActiveBootstrapRun()
      toast.success('已终止生成')
      await refreshBootstrapResume()
    } catch {
      toast.error('终止失败，请重试')
    } finally {
      setResumeCancelLoading(false)
    }
  }

  const closeDeleteModal = useCallback(() => setDeleteConfirmProject(null), [])

  const requestDeleteProject = (project: Project) => {
    setDeleteConfirmProject(project)
  }

  const confirmDeleteProject = async () => {
    const project = deleteConfirmProject
    if (!project) return
    setDeletingId(project.id)
    try {
      await projectsApi.delete(project.id)
      const { genQueue, currentProject } = useAppStore.getState()
      genQueue.filter((t) => t.projectId === project.id).forEach((t) => removeGenTask(t.id))
      if (currentProject?.id === project.id) setCurrentProject(null)
      const active = readActiveBootstrapRun()
      if (active?.projectId === project.id) clearActiveBootstrapRun()
      setProjects((prev) => prev.filter((p) => p.id !== project.id))
      setDeleteConfirmProject(null)
      toast.success('已删除')
      void refreshBootstrapResume()
    } catch {
      /* axios 拦截器已 toast */
    } finally {
      setDeletingId(null)
    }
  }

  const create = async () => {
    if (!form.title.trim()) return toast.error('请填写小说名称')
    setCreating(true)
    try {
      const res = await projectsApi.create(form)
      setProjects(prev => [res.data, ...prev])
      setShowForm(false)
      setForm({ title: '', genre: '', logline: '', premise: '', target_words: 1200000 })
      setCurrentProject(res.data)
      navigate(`/project/${res.data.id}/outline`)
    } catch {
      toast.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleSidebarNavigate = (target: string) => {
    if (target === 'home') navigate('/')
    else if (target === 'projects') { /* already here */ }
    else if (target === 'write') {
      const p = projects[0]
      if (p) { setCurrentProject(p); navigate(`/project/${p.id}/write`) }
      else toast('还没有小说，先新建一部吧')
    }
    else if (target === 'coherence') navigate('/coherence-check')
    else if (target === 'memory') {
      const p = projects[0]
      if (p) { setCurrentProject(p); navigate(`/project/${p.id}/memory`) }
    }
    else if (target === 'characters') {
      const p = projects[0]
      if (p) { setCurrentProject(p); navigate(`/project/${p.id}/characters`) }
    }
    else if (target === 'outline') {
      const p = projects[0]
      if (p) { setCurrentProject(p); navigate(`/project/${p.id}/outline`) }
    }
    else if (target === 'fanqie') navigate('/fanqie')
    else toast('功能建设中')
  }

  const filtered = projects.filter(p =>
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    (p.genre ?? '').includes(search) ||
    (p.logline ?? '').includes(search)
  )

  const todayWords = 2560

  /**
   * 有未结束的串行生成时禁止再开「新」向导，避免双 run。
   * 恢复进度只通过顶部条「继续」；若用户曾点「本页不再提示」，再次点「AI 生成」会重新显示该条。
   */
  const guardOpenNewBootstrapWizard = () => {
    const rid = bootstrapResumeSnapshot?.runId?.trim()
    if (rid) {
      setResumeBarHidden(false)
      toast(
        '已有进行中的生成。请先点击上方「继续」回到进度；关闭向导或刷新后也可在此重新进入。',
        { duration: 5200 },
      )
      return false
    }
    return true
  }

  const openNewBootstrapWizard = () => {
    if (!guardOpenNewBootstrapWizard()) return
    setWizardRecoverRunId(null)
    setShowWizard(true)
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      {deleteConfirmProject && (
        <BookshelfDeleteConfirmModal
          project={deleteConfirmProject}
          loading={deletingId === deleteConfirmProject.id}
          onCancel={closeDeleteModal}
          onConfirm={() => void confirmDeleteProject()}
        />
      )}
      {showWizard && (
        <GenerateWizard
          onClose={onWizardClose}
          recoverRunId={wizardRecoverRunId}
          onRecoverConsumed={() => setWizardRecoverRunId(null)}
        />
      )}
      {showForm && (
        <CreateProjectDialog
          form={form}
          creating={creating}
          onChange={setForm}
          onCreate={create}
          onClose={() => setShowForm(false)}
          onUseAi={() => {
            setShowForm(false)
            if (!guardOpenNewBootstrapWizard()) return
            setWizardRecoverRunId(null)
            setShowWizard(true)
          }}
        />
      )}

      <HomeSidebar todayWords={todayWords} onNavigate={handleSidebarNavigate} activeId="projects" />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />

        <main className="min-w-0 flex-1 px-5 py-8 sm:px-10">
          <div className="mx-auto max-w-[1200px]">

            {/* 页头 */}
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-gray-950 sm:text-[28px]">
                  我的书架
                </h1>
                <p className="mt-1 text-sm text-gray-500">
                  共 {projects.length} 部作品
                </p>
              </div>

              <div className="flex items-center gap-3">
                {/* 搜索 */}
                <div className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-gray-400 shadow-sm">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="搜索书名或类型…"
                    className="w-40 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-400"
                  />
                </div>

                {/* 新建 */}
                <button
                  type="button"
                  onClick={() => setShowForm(true)}
                  className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-300 hover:text-amber-600"
                >
                  <Plus size={16} />
                  手动创建
                </button>
                <button
                  type="button"
                  onClick={openNewBootstrapWizard}
                  className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white shadow-md transition-colors hover:bg-amber-600"
                >
                  <Sparkles size={16} />
                  AI 生成
                </button>
              </div>
            </div>

            <ActiveBootstrapResumeBar
              snapshot={bootstrapResumeSnapshot}
              hidden={resumeBarHidden}
              onContinue={() => {
                if (!bootstrapResumeSnapshot?.runId) return
                setWizardRecoverRunId(bootstrapResumeSnapshot.runId)
                setShowWizard(true)
                setResumeBarHidden(false)
              }}
              onHide={() => setResumeBarHidden(true)}
              onCancelRun={handleCancelBootstrapRun}
              cancelLoading={resumeCancelLoading}
            />

            {/* 书架木板分隔 */}
            <div className="mt-6 h-px bg-gradient-to-r from-transparent via-amber-200/60 to-transparent" />

            {/* 内容区 */}
            {loading ? (
              <div className="grid gap-6 pt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-64 animate-pulse rounded-xl bg-gray-100" />
                ))}
              </div>
            ) : filtered.length === 0 && search ? (
              <div className="py-20 text-center text-gray-400">
                <BookOpen size={40} className="mx-auto mb-3 opacity-40" />
                <p>没有找到「{search}」相关的小说</p>
              </div>
            ) : projects.length === 0 ? (
              <EmptyShelf onCreate={openNewBootstrapWizard} />
            ) : (
              <div className="grid gap-6 pt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {filtered.map(project => (
                  <BookCard
                    key={project.id}
                    project={project}
                    onOpen={() => navigate(`/bookshelf/${project.id}`)}
                    onDelete={requestDeleteProject}
                    deleting={deletingId === project.id}
                  />
                ))}

                {/* 添加占位卡 */}
                <button
                  type="button"
                  onClick={openNewBootstrapWizard}
                  className="flex h-48 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-gray-200 bg-white/60 text-gray-400 transition-colors hover:border-amber-300 hover:text-amber-500"
                >
                  <Plus size={28} />
                  <span className="text-sm font-medium">新建小说</span>
                </button>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
