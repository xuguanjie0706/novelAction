/**
 * @file /dabai — 大白文实验书架（dabai API），同构「我的书架」网格。
 * 写作跳转 /dabai/:id/write-dabailab
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Plus, Search, Zap } from 'lucide-react'
import HomeSidebar from '../../components/Home/HomeSidebar'
import HomeTopBar from '../../components/Home/HomeTopBar'
import { projectsApi } from '../../api/client'
import { useDabaiGenerate } from '../../hooks/useDabaiGenerate'
import { useHomeSidebarNavigate } from '../../hooks/useHomeSidebarNavigate'
import { useAppStore } from '../../store'
import type { Project } from '../../types'
import DabaiCreateDialog from './DabaiCreateDialog'
import DabaiShelfCard from './DabaiShelfCard'

export default function DabaiShelfPage() {
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const {
    list, generating, steps, stepStatus, chapterTotal, generate, remove,
  } = useDabaiGenerate({
    onDone: (id) => {
      setCreateOpen(false)
      navigate(`/dabai/${id}/write-dabailab`)
    },
  })

  useEffect(() => {
    projectsApi.list().then(res => setProjects(res.data)).catch(() => setProjects([]))
  }, [])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return list.filter(p =>
      (p.title ?? '').toLowerCase().includes(q) || p.logline.toLowerCase().includes(q),
    )
  }, [list, search])

  const handleSidebarNavigate = useHomeSidebarNavigate({
    projects,
    activeId: 'dabai',
    navigate,
    setCurrentProject,
  })

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定删除该大白文作品？')) return
    setDeletingId(id)
    try {
      await remove(id)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      <DabaiCreateDialog
        open={createOpen}
        generating={generating}
        steps={steps}
        stepStatus={stepStatus}
        chapterTotal={chapterTotal}
        onClose={() => !generating && setCreateOpen(false)}
        onGenerate={generate}
      />

      <HomeSidebar todayWords={0} onNavigate={handleSidebarNavigate} activeId="dabai" />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />
        <main className="min-w-0 flex-1 px-5 py-8 sm:px-10">
          <div className="mx-auto max-w-[1200px]">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Zap size={22} className="text-rose-500" />
                  <h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">大白文</h1>
                </div>
                <p className="mt-1 text-sm text-gray-500">共 {list.length} 部作品</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 shadow-sm">
                  <Search size={16} className="text-gray-400" />
                  <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="搜索…"
                    className="w-36 bg-transparent text-sm outline-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setCreateOpen(true)}
                  className="flex h-10 items-center gap-2 rounded-lg bg-rose-500 px-4 text-sm font-semibold text-white shadow-md hover:bg-rose-600"
                >
                  <Plus size={16} />
                  新建
                </button>
              </div>
            </div>

            <div className="mt-6 h-px bg-gradient-to-r from-transparent via-rose-200/60 to-transparent" />

            {list.length === 0 && !generating ? (
              <div className="flex flex-col items-center py-24 text-center">
                <BookOpen size={40} className="text-rose-200" />
                <p className="mt-4 text-gray-500">书架为空，点「新建」开始</p>
                <button
                  type="button"
                  onClick={() => setCreateOpen(true)}
                  className="mt-6 rounded-lg bg-rose-500 px-6 py-2.5 text-sm font-semibold text-white"
                >
                  新建大白文
                </button>
              </div>
            ) : (
              <div className="grid gap-6 pt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {filtered.map(item => (
                  <DabaiShelfCard
                    key={item.id}
                    item={item}
                    onOpen={() => navigate(`/dabai/${item.id}`)}
                    onDelete={() => void handleDelete(item.id)}
                    deleting={deletingId === item.id}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setCreateOpen(true)}
                  className="flex h-48 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-rose-200 text-rose-400 hover:border-rose-300 hover:text-rose-500"
                >
                  <Plus size={28} />
                  <span className="text-sm font-medium">新建</span>
                </button>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
