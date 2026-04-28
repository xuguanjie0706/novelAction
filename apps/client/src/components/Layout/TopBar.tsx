import React from 'react'
import { ArrowLeft, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAppStore } from '../../store'
import clsx from 'clsx'
import LlmAgentMenu from './LlmAgentMenu'

interface Props { projectId: string }

export default function TopBar({ projectId }: Props) {
  const { currentProject, aiPanelOpen, setAiPanelOpen } = useAppStore()

  return (
    <header className="h-11 flex items-center justify-between px-4 bg-white border-b border-gray-100 shrink-0">
      <div className="flex items-center gap-2">
        <Link
          to="/"
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-800"
          title="返回首页"
        >
          <ArrowLeft size={12} />
          首页
        </Link>
        <span className="font-semibold text-sm text-gray-800">
          {currentProject?.title ?? '加载中...'}
        </span>
        {currentProject?.genre && (
          <span className="text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full border border-amber-200">
            {currentProject.genre}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <LlmAgentMenu />
        <button
          onClick={() => setAiPanelOpen(!aiPanelOpen)}
          className={clsx(
            'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors',
            aiPanelOpen
              ? 'bg-amber-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-amber-50 hover:text-amber-700'
          )}
        >
          <Sparkles size={14} />
          AI 助手
        </button>
      </div>
    </header>
  )
}
