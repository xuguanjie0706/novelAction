import React, { useState } from 'react'
import { ArrowLeft, Sparkles, RotateCcw, AlertTriangle } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAppStore } from '../../store'
import { projectsApi, charactersApi } from '../../api/client'
import clsx from 'clsx'
import LlmAgentMenu from './LlmAgentMenu'
import toast from 'react-hot-toast'

interface Props { projectId: string }

function ResetConfirmModal({
  projectTitle,
  onConfirm,
  onCancel,
  loading,
}: {
  projectTitle: string
  onConfirm: () => void
  onCancel: () => void
  loading: boolean
}) {
  const [inputVal, setInputVal] = useState('')
  const confirmed = inputVal.trim() === projectTitle.trim()

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6 space-y-5">
        {/* 标题 */}
        <div className="flex items-start gap-3">
          <div className="p-2 bg-red-50 rounded-xl shrink-0">
            <AlertTriangle size={20} className="text-red-500" />
          </div>
          <div>
            <div className="font-bold text-gray-900 text-base">重置写作进度</div>
            <p className="text-xs text-gray-500 mt-1">此操作不可撤销，请仔细确认</p>
          </div>
        </div>

        {/* 说明 */}
        <div className="bg-gray-50 rounded-xl p-4 text-xs text-gray-600 space-y-1.5">
          <p className="font-semibold text-gray-700 mb-2">将会清除：</p>
          <p>· 所有章节正文及版本历史</p>
          <p>· 记忆库、伏笔、章节索引、复盘缓存</p>
          <p>· 技能（斗技）、道具（法宝）</p>
          <p>· 人物写作状态（境界 / 位置 / 持有物等）</p>
          <p>· 故事线推进记录</p>
          <div className="border-t border-gray-200 my-2" />
          <p className="font-semibold text-green-700">将会保留：</p>
          <p>· 大纲结构（卷 / 弧 / 章节计划）</p>
          <p>· 境界体系、势力、世界观设定</p>
          <p>· 人物基础档案（姓名 / 性格 / 背景等）</p>
          <p>· 故事线定义（仅清进度，状态归「规划中」）</p>
        </div>

        {/* 输入确认 */}
        <div>
          <p className="text-xs text-gray-500 mb-2">
            输入小说名称 <span className="font-semibold text-gray-800">「{projectTitle}」</span> 以确认：
          </p>
          <input
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            placeholder="在此输入小说名称..."
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-300"
            autoFocus
          />
        </div>

        {/* 按钮 */}
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 py-2 text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-xl transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={!confirmed || loading}
            className="flex-1 py-2 text-sm text-white bg-red-500 hover:bg-red-600 rounded-xl transition-colors disabled:opacity-40 font-medium"
          >
            {loading ? '重置中...' : '确认重置'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function TopBar({ projectId }: Props) {
  const { currentProject, aiPanelOpen, setAiPanelOpen, setChapters, setMemories } = useAppStore()
  const navigate = useNavigate()
  const [showResetModal, setShowResetModal] = useState(false)
  const [resetting, setResetting] = useState(false)

  const handleReset = async () => {
    setResetting(true)
    try {
      const res = await projectsApi.resetWriting(projectId)
      setShowResetModal(false)
      // 清空前端 store 中的写作相关数据
      setChapters([])
      setMemories([])
      // 重新拉取人物（状态已被清除）
      try {
        const chars = await charactersApi.list(projectId)
        chars.data.forEach((c: any) => useAppStore.getState().upsertCharacter(c))
      } catch {}
      toast.success((res.data as any).message ?? '写作进度已重置')
      // 跳回大纲页，从头开始
      navigate(`/project/${projectId}/outline`)
    } catch {
      toast.error('重置失败，请重试')
    } finally {
      setResetting(false)
    }
  }

  return (
    <>
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
            onClick={() => setShowResetModal(true)}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
            title="重置写作进度（保留大纲）"
          >
            <RotateCcw size={13} />
            重置进度
          </button>
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

      {showResetModal && currentProject && (
        <ResetConfirmModal
          projectTitle={currentProject.title}
          onConfirm={handleReset}
          onCancel={() => setShowResetModal(false)}
          loading={resetting}
        />
      )}
    </>
  )
}
