/**
 * ChapterDrawer.tsx — 章节列表抽屉
 *
 * 职责：
 *  - 右滑抽屉展示某本书的章节/草稿列表
 *  - 支持按状态筛选（全部 / 已发布 / 草稿）
 *  - 显示字数、更新时间、发布状态标签
 */
import React, { useState } from 'react'
import { X, FileText, Loader2 } from 'lucide-react'
import type { FanqieBook, FanqieChapter } from '../../api/fanqieApi'
import { getFanqieChapters } from '../../api/fanqieApi'

interface Props {
  book: FanqieBook
  chapters: FanqieChapter[]
  loading: boolean
  error: string | null
  onClose: () => void
}

type Filter = 'all' | 'published' | 'draft'

const FILTERS: { key: Filter; label: string; status: string }[] = [
  { key: 'all',       label: '全部',   status: '0' },
  { key: 'published', label: '已发布', status: '1' },
  { key: 'draft',     label: '草稿',   status: '2' },
]

function formatTime(ts?: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function ChapterDrawer({ book, chapters: initialChapters, loading: initLoading, error: initError, onClose }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const [chapters, setChapters] = useState(initialChapters)
  const [loading, setLoading] = useState(initLoading)
  const [error, setError] = useState(initError)

  async function handleFilterChange(f: Filter) {
    setFilter(f)
    const statusMap: Record<Filter, string> = { all: '0', published: '1', draft: '2' }
    setLoading(true)
    setError(null)
    try {
      const res = await getFanqieChapters(book.book_id, statusMap[f])
      setChapters(res.chapters)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? '加载失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* 遮罩 */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* 抽屉 */}
      <div className="fixed right-0 top-0 bottom-0 w-[420px] bg-white z-50 shadow-2xl flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <div className="font-semibold text-gray-900 text-sm truncate max-w-[300px]">{book.book_name}</div>
            <div className="text-xs text-gray-400 mt-0.5">{chapters.length} 条记录</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* 筛选标签 */}
        <div className="flex gap-1 px-5 py-3 border-b border-gray-50">
          {FILTERS.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => handleFilterChange(f.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === f.key
                  ? 'bg-amber-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-32 gap-2 text-gray-400 text-sm">
              <Loader2 size={16} className="animate-spin" /> 加载中…
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-32 text-red-400 text-sm px-6 text-center">
              {error}
            </div>
          ) : chapters.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2 text-gray-400">
              <FileText size={28} className="text-gray-200" />
              <span className="text-sm">暂无章节</span>
            </div>
          ) : (
            <ul className="divide-y divide-gray-50">
              {chapters.map((ch, idx) => (
                <li key={ch.item_id} className="flex items-start gap-3 px-5 py-3 hover:bg-gray-50 transition-colors">
                  {/* 序号 */}
                  <span className="mt-0.5 w-7 shrink-0 text-center text-xs text-gray-300 font-mono">{idx + 1}</span>

                  {/* 主信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-800 truncate">{ch.title || `（无标题）`}</div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-gray-400">
                      {ch.word_count != null && <span>{ch.word_count} 字</span>}
                      {ch.update_time && <span>{formatTime(ch.update_time)}</span>}
                    </div>
                  </div>

                  {/* 状态标签 */}
                  <span
                    className={`shrink-0 mt-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      ch.is_published || ch.status === 1
                        ? 'bg-green-50 text-green-600'
                        : 'bg-amber-50 text-amber-500'
                    }`}
                  >
                    {ch.is_published || ch.status === 1 ? '已发布' : '草稿'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  )
}
