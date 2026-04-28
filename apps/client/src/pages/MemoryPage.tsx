import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Brain, Filter } from 'lucide-react'
import { aiApi } from '../api/client'
import { useAppStore } from '../store'
import type { MemoryChunk } from '../types'
import clsx from 'clsx'

const MEMORY_TYPES: { key: MemoryChunk['memory_type'] | 'all'; label: string; color: string }[] = [
  { key: 'all',             label: '全部',   color: 'bg-gray-100 text-gray-600' },
  { key: 'event',           label: '事件',   color: 'bg-blue-100 text-blue-700' },
  { key: 'character_state', label: '人物状态', color: 'bg-purple-100 text-purple-700' },
  { key: 'foreshadow',      label: '伏笔',   color: 'bg-amber-100 text-amber-700' },
  { key: 'setting',         label: '设定',   color: 'bg-green-100 text-green-700' },
  { key: 'conflict',        label: '冲突',   color: 'bg-red-100 text-red-700' },
]

function typeColor(t: string) {
  return MEMORY_TYPES.find(m => m.key === t)?.color ?? 'bg-gray-100 text-gray-600'
}

function typeLabel(t: string) {
  return MEMORY_TYPES.find(m => m.key === t)?.label ?? t
}

export default function MemoryPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { memories, setMemories } = useAppStore()
  const [filter, setFilter] = useState<'all' | MemoryChunk['memory_type']>('all')
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!projectId) return
    aiApi.listMemory(projectId).then(res => setMemories(res.data))
  }, [projectId])

  const filtered = memories.filter(m => {
    if (filter !== 'all' && m.memory_type !== filter) return false
    if (search && !m.content.includes(search) && !(m.title?.includes(search))) return false
    return true
  })

  // 按章节分组
  const byChapter = filtered.reduce<Record<number, MemoryChunk[]>>((acc, m) => {
    const ch = m.chapter_number ?? 0
    if (!acc[ch]) acc[ch] = []
    acc[ch].push(m)
    return acc
  }, {})
  const sortedChapters = Object.keys(byChapter).map(Number).sort((a, b) => a - b)

  return (
    <div className="flex h-full">
      {/* 左栏：筛选器 */}
      <div className="w-44 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="px-4 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">记忆类型</span>
        </div>
        <div className="flex-1 overflow-auto py-2">
          {MEMORY_TYPES.map(({ key, label, color }) => {
            const count = key === 'all'
              ? memories.length
              : memories.filter(m => m.memory_type === key).length
            return (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={clsx(
                  'w-full flex items-center justify-between px-4 py-2 text-left text-sm transition-colors border-l-2',
                  filter === key
                    ? 'bg-amber-50 border-l-amber-400'
                    : 'border-l-transparent hover:bg-gray-50'
                )}
              >
                <div className="flex items-center gap-2">
                  <span className={clsx('text-xs px-1.5 py-0.5 rounded-full font-medium', color)}>{label}</span>
                </div>
                <span className="text-xs text-gray-400">{count}</span>
              </button>
            )
          })}
        </div>

        {/* 统计 */}
        <div className="border-t border-gray-100 p-3 space-y-1">
          <div className="text-xs text-gray-400">共 {memories.length} 条记忆</div>
          <div className="text-xs text-gray-400">
            覆盖 {new Set(memories.map(m => m.chapter_number)).size} 章
          </div>
        </div>
      </div>

      {/* 右栏：记忆卡片 */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#FAF8F4]">
        {/* 搜索栏 */}
        <div className="px-5 py-3 bg-white border-b border-gray-100 shrink-0">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索记忆内容..."
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
          />
        </div>

        <div className="flex-1 overflow-auto p-5">
          {filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <Brain size={40} className="mb-3 opacity-30" />
              <p className="text-sm">暂无记忆条目</p>
              <p className="text-xs mt-1">在写作页面使用「AI → 记忆库 → 提取记忆」自动填充</p>
            </div>
          )}

          {sortedChapters.map(ch => (
            <div key={ch} className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-gray-200" />
                <span className="text-xs font-semibold text-gray-400 px-2">
                  {ch === 0 ? '初始设定' : `第 ${ch} 章`}
                </span>
                <div className="h-px flex-1 bg-gray-200" />
              </div>

              <div className="grid grid-cols-1 gap-2">
                {byChapter[ch].map(m => (
                  <div
                    key={m.id}
                    className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', typeColor(m.memory_type))}>
                          {typeLabel(m.memory_type)}
                        </span>
                        {m.title && <span className="text-sm font-semibold text-gray-800">{m.title}</span>}
                      </div>
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed">{m.content}</p>
                    {m.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {m.tags.map(t => (
                          <span key={t} className="text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded-full border border-gray-100">
                            #{t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
