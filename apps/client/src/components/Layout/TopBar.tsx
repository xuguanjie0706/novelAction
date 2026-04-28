import React from 'react'
import { Sparkles, Cpu } from 'lucide-react'
import { useAppStore } from '../../store'
import clsx from 'clsx'
import LlmAgentMenu from './LlmAgentMenu'

interface Props { projectId: string }

export default function TopBar({ projectId }: Props) {
  const { currentProject, aiPanelOpen, setAiPanelOpen, aiModelProfile, setAiModelProfile } = useAppStore()

  return (
    <header className="h-11 flex items-center justify-between px-4 bg-white border-b border-gray-100 shrink-0">
      <div className="flex items-center gap-2">
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
        <div className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50/80 px-2 py-1">
          <Cpu size={13} className="text-gray-500 shrink-0" aria-hidden />
          <label htmlFor="global-ai-model" className="sr-only">AI 模型</label>
          <select
            id="global-ai-model"
            value={aiModelProfile}
            onChange={e => setAiModelProfile(e.target.value as 'local' | 'gemini')}
            className="max-w-[10rem] sm:max-w-[14rem] text-xs bg-transparent border-0 py-0.5 pl-0 pr-6 text-gray-700 focus:outline-none focus:ring-0 cursor-pointer"
            title="全局模型：正文起笔、AI 助手、大纲展开等均使用此项"
          >
            <option value="local">本地 / 默认</option>
            <option value="gemini">Gemini</option>
          </select>
        </div>
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
