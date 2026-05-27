/**
 * FanqieBookPickerModal — 从番茄书单选择一本书绑定到当前项目
 *
 * 调用 getFanqieBooks() 拉取书单，渲染卡片列表，
 * 用户点击某本书后回调 onSelect(book)，父组件负责持久化。
 */
import React, { useEffect, useState } from 'react'
import { Flame, Loader2, RefreshCw, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { getFanqieBooks } from '../../api/fanqieApi'
import type { FanqieBook } from '../../api/fanqieApi'

interface Props {
  open: boolean
  currentBookId?: string
  onSelect: (book: FanqieBook) => void
  onClose: () => void
}

function wordLabel(n?: number) {
  if (!n) return ''
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万字` : `${n} 字`
}

export default function FanqieBookPickerModal({ open, currentBookId, onSelect, onClose }: Props) {
  const [books, setBooks] = useState<FanqieBook[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getFanqieBooks()
      setBooks(res.books)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      const msg = err?.response?.data?.detail ?? err?.message ?? '获取书单失败'
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) void load()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="flex h-[560px] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div className="flex items-center gap-2">
            <Flame size={18} className="text-red-500" fill="currentColor" />
            <h2 className="text-base font-bold text-gray-900">选择番茄书籍绑定</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-600 hover:border-amber-300 hover:text-amber-600 disabled:opacity-50"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              刷新
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-3 text-gray-400">
              <Loader2 size={22} className="animate-spin" />
              <span className="text-sm">拉取书单中…</span>
            </div>
          ) : error ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-gray-400">
              <p className="text-sm">{error}</p>
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-600 hover:border-red-200 hover:text-red-600"
              >
                重试
              </button>
            </div>
          ) : books.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-400">
              暂无番茄作品，请先在番茄作家后台创建小说
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {books.map(book => {
                const isSelected = book.book_id === currentBookId
                return (
                  <button
                    key={book.book_id}
                    type="button"
                    onClick={() => { onSelect(book); onClose() }}
                    className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-all hover:shadow-sm ${
                      isSelected
                        ? 'border-red-300 bg-red-50 shadow-sm'
                        : 'border-gray-200 bg-white hover:border-red-200'
                    }`}
                  >
                    {/* 封面占位 */}
                    <div className="relative h-16 w-12 shrink-0 overflow-hidden rounded-lg bg-gradient-to-b from-red-400 to-orange-500">
                      {book.cover && (
                        <img
                          src={book.cover}
                          alt={book.book_name}
                          className="h-full w-full object-cover"
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                        />
                      )}
                      {isSelected && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                          <span className="text-[10px] font-bold text-white">已绑定</span>
                        </div>
                      )}
                    </div>

                    {/* 书籍信息 */}
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-sm font-semibold ${isSelected ? 'text-red-700' : 'text-gray-800'}`}>
                        {book.book_name}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-400">
                        {book.word_count ? <span>{wordLabel(book.word_count)}</span> : null}
                        {book.chapter_count ? <span>{book.chapter_count} 章</span> : null}
                        {book.status === 1 && (
                          <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600">
                            连载中
                          </span>
                        )}
                        {book.status === 0 && (
                          <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                            已完结
                          </span>
                        )}
                      </div>
                      {book.last_chapter_title && (
                        <p className="mt-1 truncate text-[11px] text-gray-400">
                          最新：{book.last_chapter_title}
                        </p>
                      )}
                      <p className="mt-1 font-mono text-[10px] text-gray-300">ID: {book.book_id}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* 底部说明 */}
        <div className="border-t border-gray-100 px-6 py-3">
          <p className="text-xs text-gray-400">
            选择后将把番茄书籍 ID 绑定到当前项目，写作页「同步」按钮将上传当前章节到该书的草稿箱。
          </p>
        </div>
      </div>
    </div>
  )
}
