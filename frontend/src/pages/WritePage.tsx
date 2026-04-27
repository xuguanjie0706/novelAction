import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { chaptersApi } from '../api/client'
import { useAppStore } from '../store'
import ChapterEditor from '../components/Writing/ChapterEditor'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { Chapter } from '../types'

export default function WritePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { chapters, setChapters, upsertChapter, activeChapterId, setActiveChapterId } = useAppStore()
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!projectId) return
    chaptersApi.list(projectId).then(res => {
      setChapters(res.data)
      if (!activeChapterId && res.data.length > 0) {
        setActiveChapterId(res.data[0].id)
      }
    })
  }, [projectId])

  const createChapter = async () => {
    if (!projectId) return
    setCreating(true)
    try {
      const res = await chaptersApi.create(projectId, {
        title: `第${chapters.length + 1}章`,
        sort_order: chapters.length,
      })
      upsertChapter(res.data)
      setActiveChapterId(res.data.id)
    } catch {
      toast.error('创建章节失败')
    } finally {
      setCreating(false)
    }
  }

  const activeChapter = chapters.find(c => c.id === activeChapterId)

  const statusColor = (s: Chapter['status']) => ({
    draft: 'bg-gray-200 text-gray-600',
    writing: 'bg-blue-100 text-blue-600',
    done: 'bg-green-100 text-green-600',
    reviewed: 'bg-amber-100 text-amber-600',
  }[s])

  return (
    <div className="flex h-full">
      {/* 章节列表 */}
      <div className="w-52 flex flex-col border-r border-gray-100 bg-white shrink-0">
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">章节</span>
          <button
            onClick={createChapter}
            disabled={creating}
            className="p-1 rounded hover:bg-gray-100 text-gray-500"
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {chapters.map(ch => (
            <button
              key={ch.id}
              onClick={() => setActiveChapterId(ch.id)}
              className={clsx(
                'w-full text-left px-3 py-2.5 border-b border-gray-50 transition-colors',
                ch.id === activeChapterId
                  ? 'bg-amber-50 border-l-2 border-l-amber-500'
                  : 'hover:bg-gray-50'
              )}
            >
              <div className="text-sm font-medium text-gray-800 truncate">{ch.title}</div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-gray-400">{ch.word_count.toLocaleString()}字</span>
                <span className={clsx('text-xs px-1.5 rounded-full', statusColor(ch.status))}>
                  {ch.status}
                </span>
              </div>
            </button>
          ))}
          {chapters.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8">点击 + 新建章节</p>
          )}
        </div>
      </div>

      {/* 编辑区 */}
      <div className="flex-1 min-w-0">
        {activeChapter
          ? <ChapterEditor projectId={projectId!} chapter={activeChapter} />
          : (
            <div className="flex items-center justify-center h-full text-gray-400">
              选择或新建一个章节开始写作
            </div>
          )
        }
      </div>
    </div>
  )
}
