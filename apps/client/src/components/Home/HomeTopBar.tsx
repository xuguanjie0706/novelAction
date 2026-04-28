import React from 'react'
import { Bell, ChevronDown, Search, Sun } from 'lucide-react'

export default function HomeTopBar() {
  return (
    <header className="flex h-[94px] shrink-0 items-center justify-between border-b border-gray-100 bg-white px-6 sm:px-8">
      <div className="flex h-12 w-full max-w-[468px] items-center gap-3 rounded-full border border-gray-200 bg-gray-50 px-5 text-gray-400 shadow-inner">
        <Search size={20} />
        <input
          aria-label="搜索小说、章节或灵感"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400"
          placeholder="搜索小说、章节或灵感"
        />
      </div>

      <div className="ml-5 flex items-center gap-5">
        <button
          type="button"
          aria-label="切换主题"
          className="hidden h-10 w-10 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900 sm:flex"
        >
          <Sun size={21} />
        </button>
        <button
          type="button"
          aria-label="通知"
          className="hidden h-10 w-10 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900 sm:flex"
        >
          <Bell size={21} />
        </button>
        <button
          type="button"
          className="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-gray-50"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-100 text-lg shadow-sm">
            写
          </div>
          <span className="hidden text-sm font-semibold text-gray-800 sm:inline">写作者</span>
          <ChevronDown size={16} className="hidden text-gray-500 sm:block" />
        </button>
      </div>
    </header>
  )
}
