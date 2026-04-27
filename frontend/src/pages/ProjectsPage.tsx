import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, BookOpen, Sparkles } from 'lucide-react'
import { projectsApi } from '../api/client'
import { useAppStore } from '../store'
import type { Project } from '../types'
import toast from 'react-hot-toast'
import GenerateWizard from '../components/Bootstrap/GenerateWizard'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [form, setForm] = useState({ title: '', genre: '', logline: '' })

  useEffect(() => {
    projectsApi.list().then(res => setProjects(res.data))
  }, [])

  // 向导完成后刷新列表
  const onWizardClose = () => {
    setShowWizard(false)
    projectsApi.list().then(res => setProjects(res.data))
  }

  const create = async () => {
    if (!form.title.trim()) return toast.error('请填写小说名称')
    setCreating(true)
    try {
      const res = await projectsApi.create(form)
      setProjects(prev => [res.data, ...prev])
      setShowForm(false)
      setForm({ title: '', genre: '', logline: '' })
      navigate(`/project/${res.data.id}/outline`)
    } catch {
      toast.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const open = (p: Project) => {
    setCurrentProject(p)
    navigate(`/project/${p.id}/outline`)
  }

  return (
    <div className="min-h-screen bg-[#FAF8F4] p-8">
      {showWizard && <GenerateWizard onClose={onWizardClose} />}

      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-gray-900">我的小说</h1>
          <div className="flex gap-2">
            <button
              onClick={() => setShowWizard(true)}
              className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm rounded-lg"
            >
              <Sparkles size={15} /> AI 一键生成
            </button>
            <button
              onClick={() => setShowForm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 hover:border-gray-300 text-gray-700 text-sm rounded-lg"
            >
              <Plus size={15} /> 手动新建
            </button>
          </div>
        </div>

        {showForm && (
          <div className="mb-6 p-5 bg-white rounded-xl border border-gray-100 shadow-sm space-y-3">
            <h3 className="font-semibold text-gray-800">新建小说</h3>
            <input
              placeholder="小说名称 *"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <input
              placeholder="类型（玄幻 / 都市 / 科幻...）"
              value={form.genre}
              onChange={e => setForm(f => ({ ...f, genre: e.target.value }))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <textarea
              placeholder="一句话创意（选填）"
              value={form.logline}
              onChange={e => setForm(f => ({ ...f, logline: e.target.value }))}
              rows={2}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={create}
                disabled={creating}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg"
              >
                {creating ? '创建中...' : '创建'}
              </button>
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-600 text-sm rounded-lg"
              >
                取消
              </button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3">
          {projects.map(p => (
            <button
              key={p.id}
              onClick={() => open(p)}
              className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-100 hover:border-amber-200 hover:shadow-sm text-left transition-all"
            >
              <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center shrink-0">
                <BookOpen className="text-amber-600" size={22} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-gray-900">{p.title}</div>
                <div className="text-sm text-gray-400 truncate mt-0.5">
                  {p.logline ?? p.genre ?? '暂无简介'}
                </div>
              </div>
              <div className="text-xs text-gray-300 shrink-0">
                {new Date(p.updated_at ?? p.created_at).toLocaleDateString()}
              </div>
            </button>
          ))}
          {projects.length === 0 && !showForm && (
            <div className="text-center py-16 text-gray-400">
              <BookOpen size={48} className="mx-auto mb-3 opacity-30" />
              <p>还没有小说，点击「新建小说」开始创作</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
