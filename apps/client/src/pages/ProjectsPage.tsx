import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import {
  CreateProjectDialog,
  HeroPanel,
  InspirationPanel,
  QuickActionsGrid,
  RecentEdits,
  RecommendationsPanel,
  WritingStatsPanel,
  type RecentEdit,
} from '../components/Home/HomeDashboardSections'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'
import ActiveBootstrapResumeBar from '../components/Bootstrap/ActiveBootstrapResumeBar'
import { useBootstrapResumeBanner } from '../hooks/useBootstrapResumeBanner'
import { bootstrapRunsApi, dashboardApi, projectsApi } from '../api/client'
import { useAppStore } from '../store'
import type { DashboardHome, DashboardRecentChapter, Project } from '../types'
import { HOME_RECENT_FALLBACK } from '../data/homeMock'
import { timeAgo } from '../utils/timeAgo'
import { clearActiveBootstrapRun } from '../utils/bootstrapActiveRun'

// TODO(homepage-data): 后续接 AI 取名服务；当前为静态占位列表
const mockNames = ['浮灯照长夜', '山海失序录', '裂星行者', '旧神便利店']

/**
 * 时段问候：与系统时区对齐的「早上好/上午好/中午好/下午好/晚上好」。
 * 与后端 greeting_name 拼接，问候到具体作者。
 */
function timeOfDayGreeting(now: Date = new Date()): string {
  const h = now.getHours()
  if (h < 6) return '夜深了'
  if (h < 9) return '早上好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
}

/** 把后端 recent_chapters 映射成现有 RecentEdits 组件期望的形状 */
function mapRecentChapters(rows: DashboardRecentChapter[]): RecentEdit[] {
  return rows.map(r => ({
    id: r.id,
    title: r.project.title,
    chapter: r.chapter_label,
    words: r.word_count,
    timeLabel: timeAgo(r.updated_at),
    project: r.project,
  }))
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [dashboard, setDashboard] = useState<DashboardHome | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [wizardRecoverRunId, setWizardRecoverRunId] = useState<string | null>(null)
  const [resumeBarHidden, setResumeBarHidden] = useState(false)
  const [resumeCancelLoading, setResumeCancelLoading] = useState(false)
  const { snapshot: bootstrapResumeSnapshot, refresh: refreshBootstrapResume } = useBootstrapResumeBanner()
  const [form, setForm] = useState({ title: '', genre: '', logline: '', premise: '', target_words: 1200000 })

  // 项目列表（仅用于「继续写作」按钮 / 快捷跳转）
  useEffect(() => {
    projectsApi.list()
      .then(res => setProjects(res.data))
      .catch(() => {
        setProjects([])
      })
  }, [])

  // 首页聚合数据（写作统计 + 最近章节 + 问候语）
  const refreshDashboard = () => {
    setDashboardLoading(true)
    dashboardApi.home()
      .then(res => setDashboard(res.data))
      .catch(() => {
        setDashboard(null)
        toast.error('首页数据暂时不可用，已显示示例内容')
      })
      .finally(() => setDashboardLoading(false))
  }
  useEffect(refreshDashboard, [])

  const recentEdits = useMemo<RecentEdit[]>(() => {
    if (dashboard && dashboard.recent_chapters.length > 0) {
      return mapRecentChapters(dashboard.recent_chapters)
    }
    // 已登录但无章节：返回空数组让 RecentEdits 显示「先开个头」占位
    if (dashboard) return []
    // 数据加载失败：兜底 mock，保持版面非空
    return HOME_RECENT_FALLBACK
  }, [dashboard])

  const firstProject = projects[0]

  const greeting = useMemo(() => {
    const name = (dashboard?.greeting_name ?? '').trim() || '写作者'
    return `${timeOfDayGreeting()}，${name}`
  }, [dashboard])

  const todayWords = dashboard?.today_words ?? 0

  /** 有未结束的串行生成时禁止再开新向导；恢复请点横幅「继续」 */
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

  const onWizardClose = () => {
    setShowWizard(false)
    setWizardRecoverRunId(null)
    void refreshBootstrapResume()
    projectsApi.list().then(res => setProjects(res.data)).catch(() => {})
    refreshDashboard()
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

  const openProject = (project: Project | undefined, tab: 'outline' | 'write' | 'memory' | 'characters' = 'outline') => {
    if (!project) {
      toast('这是示例内容，先新建一部小说即可开始创作')
      return
    }
    // 兜底数据带的 project 可能不在当前用户列表里（mock）
    if (!projects.some(p => p.id === project.id)) {
      toast('这是示例内容，先新建一部小说即可开始创作')
      return
    }
    setCurrentProject(project)
    navigate(`/project/${project.id}/${tab}`)
  }

  const navigateFirstProject = (tab: 'outline' | 'write' | 'memory' | 'characters') => {
    openProject(firstProject, tab)
  }

  const handleSidebarNavigate = (target: string) => {
    const targetMap: Record<string, () => void> = {
      home: () => window.scrollTo({ top: 0, behavior: 'smooth' }),
      projects: () => navigate('/bookshelf'),
      write: () => navigateFirstProject('write'),
      memory: () => navigateFirstProject('memory'),
      characters: () => navigateFirstProject('characters'),
      outline: () => navigateFirstProject('outline'),
      coherence: () => navigate('/coherence-check'),
      stats: () => toast('数据统计页正在建设中，当前先展示首页写作数据'),
      wallet: () => navigate('/wallet'),
      trash: () => toast('回收站暂无内容'),
      fanqie: () => navigate('/fanqie'),
    }
    targetMap[target]?.()
  }

  const handleQuickAction = (actionId: string) => {
    if (actionId === 'chapter') {
      navigateFirstProject('write')
      return
    }
    if (actionId === 'inspiration') {
      navigateFirstProject('memory')
      return
    }
    if (actionId === 'name') {
      const nextName = mockNames[Math.floor(Math.random() * mockNames.length)]
      toast.success(`灵感书名：${nextName}`)
      return
    }
    toast('计时器功能正在建设中')
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
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

      <HomeSidebar todayWords={todayWords} onNavigate={handleSidebarNavigate} />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />

        <main className="min-w-0 flex-1 px-5 py-7 sm:px-8">
          <div className="mx-auto max-w-[1110px]">
            <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_322px]">
              <section className="min-w-0">
                <div>
                  <h1 className="text-2xl font-bold tracking-normal text-gray-950 sm:text-[28px]">
                    {greeting}
                  </h1>
                  <p className="mt-2 text-[15px] text-gray-500">今天也要元气满满地创作哦！</p>
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

                <HeroPanel
                  onCreate={() => setShowForm(true)}
                  onContinue={() => openProject(firstProject, 'write')}
                />

                <QuickActionsGrid onAction={handleQuickAction} />

                <RecentEdits
                  edits={recentEdits}
                  onOpen={project => openProject(project, 'write')}
                  onViewAll={() => navigate('/bookshelf')}
                />
              </section>

              <aside className="space-y-4">
                <WritingStatsPanel data={dashboard} loading={dashboardLoading && !dashboard} />
                <InspirationPanel />
                <RecommendationsPanel />
              </aside>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
