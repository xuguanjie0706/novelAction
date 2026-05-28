/**
 * FanqiePage — 「我的番茄」
 *
 * 布局与「我的书架」同构：HomeSidebar + HomeTopBar + 书籍网格。
 * 未配置凭据时展示弱态占位书架，点击唤起 ConnectModal；
 * 配置成功后拉取番茄 book_list 并以同款卡片展示。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flame, RefreshCw, Search, Settings2 } from 'lucide-react'
import toast from 'react-hot-toast'
import HomeSidebar from '../../components/Home/HomeSidebar'
import HomeTopBar from '../../components/Home/HomeTopBar'
import { projectsApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Project } from '../../types'
import {
  getFanqieBooks,
  getFanqieConfigSummary,
  saveFanqieConfig,
} from '../../api/fanqieApi'
import type { FanqieBook, FanqieConfig, FanqieConfigSummary } from '../../api/fanqieApi'
import { useHomeSidebarNavigate } from '../../hooks/useHomeSidebarNavigate'
import ConnectModal from './ConnectModal'
import PlaceholderGrid from './PlaceholderGrid'
import FanqieBookGrid from './FanqieBookGrid'

export default function FanqiePage() {
  const navigate = useNavigate()
  const { setCurrentProject } = useAppStore()

  const [projects, setProjects] = useState<Project[]>([])
  const [configSummary, setConfigSummary] = useState<FanqieConfigSummary | null>(null)
  const [configLoading, setConfigLoading] = useState(true)
  const [connectOpen, setConnectOpen] = useState(false)

  const [books, setBooks] = useState<FanqieBook[]>([])
  const [booksLoading, setBooksLoading] = useState(false)
  const [booksError, setBooksError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const configured = configSummary?.configured ?? false

  useEffect(() => {
    projectsApi.list().then(res => setProjects(res.data)).catch(() => setProjects([]))
  }, [])

  useEffect(() => {
    getFanqieConfigSummary()
      .then(setConfigSummary)
      .catch(() => setConfigSummary({ configured: false }))
      .finally(() => setConfigLoading(false))
  }, [])

  const loadBooks = useCallback(async () => {
    setBooksLoading(true)
    setBooksError(null)
    try {
      const res = await getFanqieBooks()
      setBooks(res.books)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setBooksError(err?.response?.data?.detail ?? err?.message ?? '获取书单失败')
    } finally {
      setBooksLoading(false)
    }
  }, [])

  useEffect(() => {
    if (configured) loadBooks()
  }, [configured, loadBooks])

  async function handleSaveConfig(cfg: FanqieConfig) {
    const res = await saveFanqieConfig(cfg)
    if (res.has_ms_token && res.has_a_bogus) {
      toast.success(res.message || '番茄凭据已保存（含上传签名）')
    } else {
      toast.success(res.message || '番茄凭据已保存')
      if (!res.has_a_bogus) {
        toast.error('未检测到 a_bogus，请粘贴 cover_article 完整 cURL', { duration: 6000 })
      }
    }
    const summary = await getFanqieConfigSummary()
    setConfigSummary(summary)
    await loadBooks()
  }

  const handleSidebarNavigate = useHomeSidebarNavigate({
    projects,
    activeId: 'fanqie',
    navigate,
    setCurrentProject,
  })

  const filtered = books.filter(b =>
    b.book_name.toLowerCase().includes(search.toLowerCase()) ||
    (b.abstract ?? '').includes(search),
  )

  return (
    <div className="min-h-screen bg-[#f8fafc] text-gray-950 lg:flex">
      <ConnectModal
        open={connectOpen}
        summary={configSummary}
        onClose={() => setConnectOpen(false)}
        onSave={handleSaveConfig}
      />

      <HomeSidebar todayWords={0} onNavigate={handleSidebarNavigate} activeId="fanqie" />

      <div className="flex min-w-0 flex-1 flex-col">
        <HomeTopBar />

        <main className="min-w-0 flex-1 px-5 py-8 sm:px-10">
          <div className="mx-auto max-w-[1200px]">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Flame size={22} className="text-red-500" fill="currentColor" />
                  <h1 className="text-2xl font-bold tracking-tight text-gray-950 sm:text-[28px]">
                    我的番茄
                  </h1>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  {configured
                    ? `共 ${books.length} 部番茄作品${configSummary?.session_preview ? ` · 已连接 ${configSummary.session_preview}` : ''}`
                    : '连接作家后台后，在此同步番茄作品与章节'}
                </p>
              </div>

              {configured && (
                <div className="flex items-center gap-3">
                  <div className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-gray-400 shadow-sm">
                    <Search size={16} />
                    <input
                      value={search}
                      onChange={e => setSearch(e.target.value)}
                      placeholder="搜索书名…"
                      className="w-36 bg-transparent text-sm text-gray-700 outline-none placeholder:text-gray-400 sm:w-44"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => loadBooks()}
                    disabled={booksLoading}
                    className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 shadow-sm hover:border-amber-300 hover:text-amber-600 disabled:opacity-50"
                  >
                    <RefreshCw size={16} className={booksLoading ? 'animate-spin' : ''} />
                    刷新
                  </button>
                  <button
                    type="button"
                    onClick={() => setConnectOpen(true)}
                    className="flex h-10 items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 shadow-sm hover:border-amber-300 hover:text-amber-600"
                  >
                    <Settings2 size={16} />
                    重新连接
                  </button>
                </div>
              )}
            </div>

            <div className="mt-6 h-px bg-gradient-to-r from-transparent via-red-200/50 to-transparent" />

            <div className="pt-8">
              {configLoading ? (
                <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="h-64 animate-pulse rounded-xl bg-gray-100" />
                  ))}
                </div>
              ) : !configured ? (
                <PlaceholderGrid onConnect={() => setConnectOpen(true)} />
              ) : search && filtered.length === 0 ? (
                <div className="py-20 text-center text-gray-400">
                  <p>没有找到「{search}」相关的番茄作品</p>
                </div>
              ) : (
                <FanqieBookGrid
                  books={search ? filtered : books}
                  loading={booksLoading}
                  error={booksError}
                  onRefresh={loadBooks}
                  onReconnect={() => setConnectOpen(true)}
                />
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
