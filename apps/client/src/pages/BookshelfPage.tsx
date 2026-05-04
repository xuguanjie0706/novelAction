import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, ChevronRight, Feather, Plus, Search, Sparkles } from 'lucide-react'
import { projectsApi } from '../api/client'
import { useAppStore } from '../store'
import type { Project } from '../types'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import {
  CreateProjectDialog,
} from '../components/Home/HomeDashboardSections'
import toast from 'react-hot-toast'

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
function BookCard({ project, onClick }: { project: Project; onClick: () => void }) {
  const g = getGradient(project.genre)
  const updatedAt = project.updated_at ?? project.created_at

  return (
    <button
      type="button"
      onClick={onClick}
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
        <div className="mt-auto flex items-center justify-between pt-2">
          {project.target_words ? (
            <span className="text-[11px] text-gray-400">
              目标 {(project.target_words / 10000).toFixed(0)} 万字
            </span>
          ) : (
            <span />
          )}
          <span className="text-[11px] text-gray-400">{timeAgo(updatedAt)}</span>
        </div>
      </div>
    </button>
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
  const { setCurrentProject } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)
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
    projectsApi.list().then(res => setProjects(res.data)).catch(() => {})
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
    else toast('功能建设中')
  }

  const filtered = projects.filter(p =>
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    (p.genre ?? '').includes(search) ||
    (p.logline ?? '').includes(search)
  )

  const todayWords = 2560

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      {showWizard && <GenerateWizard onClose={onWizardClose} />}
      {showForm && (
        <CreateProjectDialog
          form={form}
          creating={creating}
          onChange={setForm}
          onCreate={create}
          onClose={() => setShowForm(false)}
          onUseAi={() => { setShowForm(false); setShowWizard(true) }}
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
                  onClick={() => setShowWizard(true)}
                  className="flex h-10 items-center gap-2 rounded-lg bg-amber-500 px-4 text-sm font-semibold text-white shadow-md transition-colors hover:bg-amber-600"
                >
                  <Sparkles size={16} />
                  AI 生成
                </button>
              </div>
            </div>

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
              <EmptyShelf onCreate={() => setShowWizard(true)} />
            ) : (
              <div className="grid gap-6 pt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {filtered.map(project => (
                  <BookCard
                    key={project.id}
                    project={project}
                    onClick={() => navigate(`/bookshelf/${project.id}`)}
                  />
                ))}

                {/* 添加占位卡 */}
                <button
                  type="button"
                  onClick={() => setShowWizard(true)}
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
