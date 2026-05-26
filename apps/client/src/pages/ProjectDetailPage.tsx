/**
 * ProjectDetailPage — 项目详情主页面（薄壳）
 *
 * 子组件已拆分至 pages/ProjectDetail/：
 *   CoverSvgUtils / CoverModal / GenerateJourneyPanel / WritingConfigPanel
 */
import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BookOpen,
  Calendar,
  ChevronRight,
  Edit3,
  ImagePlus,
  Layers,
  Loader2,
  PenLine,
  Sparkles,
  Star,
  Target,
} from 'lucide-react'
import toast from 'react-hot-toast'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import ActiveBootstrapResumeBar from '../components/Bootstrap/ActiveBootstrapResumeBar'
import { useBootstrapResumeBanner } from '../hooks/useBootstrapResumeBanner'
import { bootstrapRunsApi, projectsApi } from '../api/client'
import { useAppStore } from '../store'
import { clearActiveBootstrapRun } from '../utils/bootstrapActiveRun'
import type { Project } from '../types'

import CoverModal from './ProjectDetail/CoverModal'
import GenerateJourneyPanel from './ProjectDetail/GenerateJourneyPanel'
import WritingConfigPanel from './ProjectDetail/WritingConfigPanel'
import { generateCoverSvg, svgToDataUrl } from './ProjectDetail/CoverSvgUtils'

// ── 小工具函数 ───────────────────────────────────────────────────────────────

function InfoTag({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl bg-gray-50 px-4 py-3">
      <Icon size={17} className="mt-0.5 shrink-0 text-amber-500" />
      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</div>
        <div className="mt-0.5 text-sm font-semibold text-gray-800">{value}</div>
      </div>
    </div>
  )
}

function statusLabel(s: Project['status']) {
  return { drafting: '规划中', writing: '连载中', completed: '已完成' }[s] ?? '规划中'
}
function statusColor(s: Project['status']) {
  return {
    drafting:  'bg-amber-100 text-amber-700 border-amber-200',
    writing:   'bg-emerald-100 text-emerald-700 border-emerald-200',
    completed: 'bg-blue-100 text-blue-700 border-blue-200',
  }[s] ?? 'bg-gray-100 text-gray-600 border-gray-200'
}

// ── 主页面 ─────────────────────────────────────────────────────────────────
export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [showCoverModal, setShowCoverModal] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [wizardRecoverRunId, setWizardRecoverRunId] = useState<string | null>(null)
  const [resumeBarHidden, setResumeBarHidden] = useState(false)
  const [resumeCancelLoading, setResumeCancelLoading] = useState(false)
  const { snapshot: bootstrapResumeSnapshot, refresh: refreshBootstrapResume } = useBootstrapResumeBanner(
    projectId ?? null,
  )

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

  useEffect(() => {
    if (!projectId) return
    projectsApi.get(projectId)
      .then(res => { setProject(res.data); setCurrentProject(res.data) })
      .catch(() => toast.error('加载小说信息失败'))
      .finally(() => setLoading(false))
  }, [projectId])

  const enterWorkbench = (tab: 'outline' | 'write' | 'characters' | 'memory' = 'write') => {
    if (!project) return
    setCurrentProject(project)
    navigate(`/project/${project.id}/${tab}`)
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f8fafc]">
        <Loader2 size={36} className="animate-spin text-amber-400" />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f8fafc]">
        <BookOpen size={48} className="text-gray-300" />
        <p className="text-gray-500">找不到该小说</p>
        <button type="button" onClick={() => navigate('/bookshelf')} className="text-sm text-amber-600 hover:underline">
          返回书架
        </button>
      </div>
    )
  }

  const svgCover = svgToDataUrl(generateCoverSvg(project))
  const coverSrc = project.cover_url ?? svgCover

  return (
    <div className="min-h-screen bg-[#f8fafc]">
      {showCoverModal && (
        <CoverModal
          project={project}
          onSave={url => { setProject(p => p ? { ...p, cover_url: url } : p); setShowCoverModal(false) }}
          onClose={() => setShowCoverModal(false)}
        />
      )}
      {showWizard && (
        <GenerateWizard
          onClose={() => {
            setShowWizard(false)
            setWizardRecoverRunId(null)
            void refreshBootstrapResume()
          }}
          recoverRunId={wizardRecoverRunId}
          onRecoverConsumed={() => setWizardRecoverRunId(null)}
        />
      )}

      {/* 顶部导航 */}
      <header className="sticky top-0 z-30 border-b border-gray-100 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-5 sm:px-8">
          <button
            type="button"
            onClick={() => navigate('/bookshelf')}
            className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-900"
          >
            <ArrowLeft size={17} />书架
          </button>
          <ChevronRight size={14} className="text-gray-300" />
          <span className="flex-1 truncate text-sm font-medium text-gray-800">{project.title}</span>
          <button
            type="button"
            onClick={() => enterWorkbench('write')}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-amber-600"
          >
            <PenLine size={15} />进入创作
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-10 sm:px-8">
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

        {/* Hero：封面 + 基础信息 */}
        <div className="flex flex-col gap-10 sm:flex-row sm:items-start">

          {/* 封面 */}
          <div className="group relative mx-auto shrink-0 sm:mx-0">
            <div className="relative h-[300px] w-[210px] overflow-hidden rounded-xl shadow-[0_12px_48px_rgba(0,0,0,0.18)] ring-1 ring-black/10">
              <img src={coverSrc} alt={project.title} className="h-full w-full object-cover" />
              <div className="pointer-events-none absolute left-0 top-0 h-full w-4 bg-gradient-to-r from-black/30 to-transparent" />
              {/* 悬浮按钮 */}
              <div className="absolute inset-0 flex flex-col items-center justify-end gap-2 bg-black/0 pb-4 opacity-0 transition-all duration-200 group-hover:bg-black/40 group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() => setShowCoverModal(true)}
                  className="flex items-center gap-1.5 rounded-full bg-white/90 px-4 py-2 text-xs font-semibold text-gray-800 shadow-lg backdrop-blur transition-transform hover:scale-105"
                >
                  <Sparkles size={13} className="text-amber-500" />AI 生成封面
                </button>
                <button
                  type="button"
                  onClick={() => setShowCoverModal(true)}
                  className="flex items-center gap-1.5 rounded-full bg-white/70 px-3 py-1.5 text-xs text-gray-600 shadow backdrop-blur transition-transform hover:scale-105"
                >
                  <ImagePlus size={12} />更换封面
                </button>
              </div>
            </div>

            {/* 始终可见的 AI 入口 */}
            <button
              type="button"
              onClick={() => setShowCoverModal(true)}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-amber-300 bg-amber-50 py-2 text-xs font-medium text-amber-600 transition-colors hover:bg-amber-100"
            >
              <Sparkles size={12} />AI 生成封面
            </button>
          </div>

          {/* 右侧信息 */}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-start gap-3">
              <h1 className="text-3xl font-bold leading-tight text-gray-950 sm:text-4xl">{project.title}</h1>
              <span className={`mt-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${statusColor(project.status)}`}>
                {statusLabel(project.status)}
              </span>
            </div>

            {project.genre && (
              <div className="mt-2 flex flex-wrap gap-2">
                {project.genre.split(/[\/、，,]/).map(g => (
                  <span key={g} className="rounded-full bg-gray-100 px-3 py-0.5 text-xs font-medium text-gray-600">{g.trim()}</span>
                ))}
              </div>
            )}

            {project.logline && (
              <p className="mt-5 text-[15px] leading-relaxed text-gray-600">{project.logline}</p>
            )}

            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {project.target_words && (
                <InfoTag icon={Target} label="目标字数" value={`${(project.target_words / 10000).toFixed(0)} 万字`} />
              )}
              <InfoTag
                icon={Calendar}
                label="创建时间"
                value={new Date(project.created_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}
              />
              {project.updated_at && (
                <InfoTag
                  icon={Edit3}
                  label="最后更新"
                  value={new Date(project.updated_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}
                />
              )}
            </div>

            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => enterWorkbench('write')}
                className="flex items-center gap-2 rounded-xl bg-amber-500 px-7 py-3 text-sm font-semibold text-white shadow-[0_6px_20px_rgba(245,158,11,0.3)] transition-all hover:bg-amber-600 active:scale-95"
              >
                <PenLine size={16} />进入创作工作台
              </button>
              <button
                type="button"
                onClick={() => enterWorkbench('outline')}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                查看大纲
              </button>
              <button
                type="button"
                onClick={() => enterWorkbench('characters')}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                角色设定
              </button>
              <button
                type="button"
                onClick={() => navigate(`/bookshelf/${project.id}/recap`)}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-5 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-amber-200 hover:text-amber-600"
              >
                <Layers size={16} />
                结构化纪要
              </button>
            </div>
          </div>
        </div>

        {/* 故事简介 */}
        {project.premise && (
          <section className="mt-12">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
              <Star size={18} className="text-amber-400" fill="currentColor" />故事简介
            </h2>
            <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <p className="text-[15px] leading-8 text-gray-700 whitespace-pre-wrap">{project.premise}</p>
            </div>
          </section>
        )}

        {/* 世界观概述 */}
        {project.world_overview && (
          <section className="mt-8">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-gray-900">
              <BookOpen size={18} className="text-amber-400" />世界观概述
            </h2>
            <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <p className="text-[15px] leading-8 text-gray-700 whitespace-pre-wrap">{project.world_overview}</p>
            </div>
          </section>
        )}

        {/* 生成纪要 */}
        <GenerateJourneyPanel projectId={project.id} />

        {/* 写作质量门控配置 */}
        <WritingConfigPanel projectId={project.id} />

        {/* 底部快速操作 */}
        <div className="mt-12 rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-orange-50 p-6">
          <h3 className="text-sm font-semibold text-gray-800">快速进入</h3>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {([
              { label: '写作', tab: 'write' as const, desc: '继续创作章节' },
              { label: '大纲', tab: 'outline' as const, desc: '查看故事结构' },
              { label: '角色', tab: 'characters' as const, desc: '管理人物设定' },
              { label: '记忆', tab: 'memory' as const, desc: '查看故事记忆' },
            ]).map(({ label, tab, desc }) => (
              <button
                key={tab}
                type="button"
                onClick={() => enterWorkbench(tab)}
                className="flex flex-col items-start rounded-xl border border-white bg-white/80 p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-amber-200 hover:shadow-md"
              >
                <span className="text-sm font-semibold text-gray-800">{label}</span>
                <span className="mt-0.5 text-xs text-gray-500">{desc}</span>
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
