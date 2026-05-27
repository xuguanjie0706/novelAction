/**
 * FanqieBookCard — 书架风格番茄书籍卡片（与 BookshelfPage BookCard 同构）
 */
import React from 'react'
import { ChevronRight, Flame } from 'lucide-react'
import type { FanqieBook } from '../../api/fanqieApi'
import { fanqieStatusColor, fanqieStatusLabel, formatFanqieTime, formatWords } from './fanqieUtils'

interface Props {
  book: FanqieBook
  onOpen: () => void
}

export default function FanqieBookCard({ book, onOpen }: Props) {
  const [coverFailed, setCoverFailed] = React.useState(false)
  const showCover = Boolean(book.cover) && !coverFailed

  React.useEffect(() => {
    setCoverFailed(false)
  }, [book.book_id, book.cover])

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-gray-100 bg-white text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
    >
      <div className="relative h-48 w-full overflow-hidden">
        {showCover ? (
          <img
            src={book.cover}
            alt={book.book_name}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            onError={() => setCoverFailed(true)}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-red-500 to-orange-600 px-4 text-center">
            <Flame size={32} className="mb-2 text-white/80" fill="currentColor" />
            <span className="line-clamp-3 text-lg font-bold leading-snug text-white drop-shadow">
              {book.book_name}
            </span>
          </div>
        )}

        <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all duration-200 group-hover:bg-black/20 group-hover:opacity-100">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 shadow-lg">
            <ChevronRight size={20} className="text-gray-800" />
          </div>
        </div>

        <div className="absolute right-2 top-2">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold shadow-sm ${fanqieStatusColor(book.status)}`}>
            {fanqieStatusLabel(book.status)}
          </span>
        </div>

        <div className="absolute left-2 top-2">
          <span className="rounded-full bg-black/40 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            番茄
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-1 px-4 py-3">
        <h3 className="line-clamp-1 text-[15px] font-semibold text-gray-900 transition-colors group-hover:text-amber-600">
          {book.book_name}
        </h3>
        {book.abstract && (
          <p className="line-clamp-2 text-[12px] leading-relaxed text-gray-500">{book.abstract}</p>
        )}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <span className="text-[11px] text-gray-400">
            {formatWords(book.word_count)}
            {book.chapter_count != null && ` · ${book.chapter_count} 章`}
          </span>
          {book.update_time ? (
            <span className="text-[11px] text-gray-400">{formatFanqieTime(book.update_time)}</span>
          ) : null}
        </div>
      </div>
    </div>
  )
}
