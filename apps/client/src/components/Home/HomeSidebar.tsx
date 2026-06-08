import React from 'react'
import clsx from 'clsx'
import {
  BarChart3,
  BookOpen,
  Coins,
  Crown,
  Flame,
  Home,
  Link2,
  Trash2,
  Zap,
} from 'lucide-react'
import { HOME_WORD_GOAL } from '../../data/homeMock'

interface HomeSidebarProps {
  todayWords: number
  onNavigate: (target: string) => void
  activeId?: string
}

const NAV_ITEMS = [
  { id: 'home', label: '首页', icon: Home },
  { id: 'projects', label: '我的小说', icon: BookOpen },
  { id: 'coherence', label: '连贯性测试', icon: Link2 },
  { id: 'stats', label: '数据统计', icon: BarChart3 },
  { id: 'wallet', label: '我的钱包', icon: Coins },
  { id: 'trash', label: '回收站', icon: Trash2 },
  { id: 'fanqie', label: '我的番茄', icon: Flame },
  { id: 'dabai', label: '大白文', icon: Zap },
]

export default function HomeSidebar({ todayWords, onNavigate, activeId = 'home' }: HomeSidebarProps) {
  const progress = Math.min(100, Math.round((todayWords / HOME_WORD_GOAL) * 100))

  return (
    <aside className="hidden w-[272px] shrink-0 flex-col border-r border-gray-100 bg-white px-7 py-8 lg:flex">
      <div className="flex items-center gap-3">
        <img
          src="/assets/icon.png"
          alt="书之幻境"
          className="h-10 w-10 rounded-lg object-cover"
        />
        <div>
          <div className="text-lg font-bold leading-tight text-gray-950">书之幻境</div>
          <div className="mt-0.5 text-sm text-gray-400">AI 驱动的小说创作平台</div>
        </div>
      </div>

      <nav className="mt-12 space-y-3">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onNavigate(id)}
            className={clsx(
              'flex h-[52px] w-full items-center gap-4 rounded-lg px-4 text-left text-[15px] font-medium transition-colors',
              id === activeId
                ? 'bg-amber-50 text-amber-500 shadow-[0_12px_32px_rgba(245,158,11,0.12)]'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-950'
            )}
          >
            <Icon size={21} className={id === activeId ? 'text-amber-500' : 'text-gray-500'} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="mt-auto space-y-10 pt-10">
        <div className="rounded-lg border border-amber-100 bg-amber-50/70 p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
            <Crown size={18} className="text-amber-500" fill="currentColor" />
            开通会员
          </div>
          <p className="mt-3 text-sm leading-6 text-gray-500">解锁更多创作功能</p>
          <button
            type="button"
            className="mt-4 h-10 w-full rounded-lg border border-gray-100 bg-white text-sm font-semibold text-amber-500 shadow-sm transition-colors hover:border-amber-200 hover:bg-amber-50"
          >
            立即开通
          </button>
        </div>

        <div className="rounded-lg border border-gray-100 bg-white p-4 shadow-sm">
          <div className="text-sm text-gray-600">今日字数</div>
          <div className="mt-3 flex items-end gap-1 text-2xl font-bold text-gray-950">
            {todayWords.toLocaleString()}
            <span className="pb-1 text-sm font-medium text-gray-600">字</span>
          </div>
          <div className="mt-3 text-sm text-gray-500">目标 {HOME_WORD_GOAL.toLocaleString()} 字</div>
          <div className="mt-4 h-2 rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-amber-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
            <span>进度</span>
            <span>{progress}%</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
