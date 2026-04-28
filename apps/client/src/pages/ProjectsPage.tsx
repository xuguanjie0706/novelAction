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
import { projectsApi } from '../api/client'
import { useAppStore } from '../store'
import type { Project } from '../types'
import { HOME_RECENT_FALLBACK } from '../data/homeMock'

const chapterLabels = [
  '第23章 生死一线',
  '第18章 命格觉醒',
  '第15章 夜幕降临',
  '第8章 吞噬之力',
  '第3章 初入都市',
]

const mockNames = ['浮灯照长夜', '山海失序录', '裂星行者', '旧神便利店']

function shortDateLabel(project: Project, index: number) {
  if (index === 0) return '刚刚'
  if (index === 1) return '2 小时前'
  if (index === 2) return '昨天'
  const date = project.updated_at ?? project.created_at
  return new Date(date).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function buildRecentEdits(projects: Project[]): RecentEdit[] {
  return projects.slice(0, 5).map((project, index) => ({
    id: project.id,
    title: project.title,
    chapter: chapterLabels[index] ?? `第${index + 1}章 继续推进`,
    words: [2560, 1872, 1320, 983, 654][index] ?? 800,
    timeLabel: shortDateLabel(project, index),
    project,
  }))
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [form, setForm] = useState({ title: '', genre: '', logline: '', premise: '' })

  useEffect(() => {
    projectsApi.list()
      .then(res => setProjects(res.data))
      .catch(() => {
        setProjects([])
        toast.error('项目数据暂时不可用，已显示示例内容')
      })
  }, [])

  const recentEdits = useMemo(
    () => (projects.length > 0 ? buildRecentEdits(projects) : HOME_RECENT_FALLBACK),
    [projects]
  )
  const firstProject = projects[0]

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
      setForm({ title: '', genre: '', logline: '', premise: '' })
      setCurrentProject(res.data)
      navigate(`/project/${res.data.id}/outline`)
    } catch {
      toast.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const openProject = (project: Project | undefined, tab: 'outline' | 'write' | 'memory' | 'characters' = 'outline') => {
    if (!project || !projects.some(p => p.id === project.id)) {
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
      projects: () => document.getElementById('recent-projects')?.scrollIntoView({ behavior: 'smooth' }),
      write: () => navigateFirstProject('write'),
      memory: () => navigateFirstProject('memory'),
      characters: () => navigateFirstProject('characters'),
      outline: () => navigateFirstProject('outline'),
      coherence: () => navigate('/coherence-check'),
      stats: () => toast('数据统计页正在建设中，当前先展示首页写作数据'),
      trash: () => toast('回收站暂无内容'),
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
      {showWizard && <GenerateWizard onClose={onWizardClose} />}
      {showForm && (
        <CreateProjectDialog
          form={form}
          creating={creating}
          onChange={setForm}
          onCreate={create}
          onClose={() => setShowForm(false)}
          onUseAi={() => {
            setShowForm(false)
            setShowWizard(true)
          }}
        />
      )}

      <HomeSidebar todayWords={HOME_RECENT_FALLBACK[0].words} onNavigate={handleSidebarNavigate} />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />

        <main className="min-w-0 flex-1 px-5 py-7 sm:px-8">
          <div className="mx-auto max-w-[1110px]">
            <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_322px]">
              <section className="min-w-0">
                <div>
                  <h1 className="text-2xl font-bold tracking-normal text-gray-950 sm:text-[28px]">
                    下午好，写作者
                  </h1>
                  <p className="mt-2 text-[15px] text-gray-500">今天也要元气满满地创作哦！</p>
                </div>

                <HeroPanel
                  onCreate={() => setShowForm(true)}
                  onContinue={() => openProject(firstProject, 'write')}
                />

                <QuickActionsGrid onAction={handleQuickAction} />

                <RecentEdits
                  edits={recentEdits}
                  onOpen={project => openProject(project, 'write')}
                />
              </section>

              <aside className="space-y-4">
                <WritingStatsPanel />
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
