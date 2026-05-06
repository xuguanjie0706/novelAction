import React from 'react'
import { Bell, LogOut, Search, Sun } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

export default function HomeTopBar() {
  const { logout, user } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  /** 头像首字母：优先 username，回退邮箱首字符，再回退 "写" */
  const avatarLetter = user
    ? (user.username?.[0] ?? user.email?.[0] ?? '写').toUpperCase()
    : '写'

  const displayName = user?.username || user?.email || '写作者'

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

        {/* 用户头像 + 名称 */}
        <div className="flex items-center gap-2">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-100 text-base font-semibold text-amber-700 shadow-sm select-none">
            {avatarLetter}
          </div>
          <span
            className="hidden text-sm font-semibold text-gray-800 sm:inline max-w-[100px] truncate"
            title={user?.email}
          >
            {displayName}
          </span>
        </div>

        {/* 登出按钮 */}
        <button
          type="button"
          onClick={handleLogout}
          aria-label="退出登录"
          title="退出登录"
          className="flex h-10 w-10 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-500"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  )
}
