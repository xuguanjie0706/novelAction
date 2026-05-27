/**
 * FanqieBookGrid — 已连接后的番茄书籍网格 + 章节抽屉
 */
import React, { useState } from 'react'
import { BookOpen, RefreshCw } from 'lucide-react'
import type { FanqieBook, FanqieChapter } from '../../api/fanqieApi'
import { getFanqieChapters } from '../../api/fanqieApi'
import FanqieBookCard from './FanqieBookCard'
import ChapterDrawer from './ChapterDrawer'

interface Props {
  books: FanqieBook[]
  loading: boolean
  error: string | null
  onRefresh: () => void
  onReconnect: () => void
}

export default function FanqieBookGrid({ books, loading, error, onRefresh, onReconnect }: Props) {
  const [selectedBook, setSelectedBook] = useState<FanqieBook | null>(null)
  const [chapters, setChapters] = useState<FanqieChapter[]>([])
  const [chapterLoading, setChapterLoading] = useState(false)
  const [chapterError, setChapterError] = useState<string | null>(null)

  async function handleOpenBook(book: FanqieBook) {
    setSelectedBook(book)
    setChapters([])
    setChapterError(null)
    setChapterLoading(true)
    try {
      const res = await getFanqieChapters(book.book_id)
      setChapters(res.chapters)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setChapterError(err?.response?.data?.detail ?? err?.message ?? '加载失败')
    } finally {
      setChapterLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-64 animate-pulse rounded-xl bg-gray-100" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 py-20 text-center">
        <p className="max-w-md text-sm text-red-500">{error}</p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            <RefreshCw size={14} /> 重试
          </button>
          <button
            type="button"
            onClick={onReconnect}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
          >
            重新连接
          </button>
        </div>
      </div>
    )
  }

  if (!books.length) {
    return (
      <div className="flex flex-col items-center gap-3 py-20 text-center">
        <BookOpen size={40} className="text-gray-200" />
        <p className="text-sm text-gray-400">暂无番茄作品，或凭据已失效</p>
        <button
          type="button"
          onClick={onReconnect}
          className="text-xs text-amber-500 hover:text-amber-600"
        >
          重新配置凭据
        </button>
      </div>
    )
  }

  return (
    <>
      <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {books.map(book => (
          <FanqieBookCard key={book.book_id} book={book} onOpen={() => handleOpenBook(book)} />
        ))}
      </div>

      {selectedBook && (
        <ChapterDrawer
          book={selectedBook}
          chapters={chapters}
          loading={chapterLoading}
          error={chapterError}
          onClose={() => setSelectedBook(null)}
        />
      )}
    </>
  )
}
