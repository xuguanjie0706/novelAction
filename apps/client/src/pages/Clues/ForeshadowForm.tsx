/**
 * ForeshadowForm — 伏笔新增/编辑表单
 */
import React, { useState } from 'react'
import { Star } from 'lucide-react'
import toast from 'react-hot-toast'
import type { Foreshadow } from '../../types'

export interface ForeshadowFormProps {
  initial?: Partial<Foreshadow>
  onSave: (data: Partial<Foreshadow>) => void
  onCancel: () => void
}

export default function ForeshadowForm({ initial = {}, onSave, onCancel }: ForeshadowFormProps) {
  const [title, setTitle] = useState(initial.title ?? '')
  const [description, setDescription] = useState(initial.description ?? '')
  const [laidNum, setLaidNum] = useState<string>(initial.laid_chapter_number?.toString() ?? '')
  const [resolvedNum, setResolvedNum] = useState<string>(
    initial.resolved_chapter_number?.toString() ?? '',
  )
  const [plannedNum, setPlannedNum] = useState<string>(
    initial.planned_resolve_chapter?.toString() ?? '',
  )
  const [plannedAction, setPlannedAction] = useState<'resolve' | 'develop'>(
    initial.planned_action ?? 'resolve',
  )
  const [status, setStatus] = useState<Foreshadow['status']>(initial.status ?? 'open')
  const [priority, setPriority] = useState(initial.priority ?? 3)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) { toast.error('伏笔标题不能为空'); return }
    onSave({
      title: title.trim(),
      description: description.trim() || undefined,
      laid_chapter_number: laidNum ? Number(laidNum) : undefined,
      resolved_chapter_number: resolvedNum ? Number(resolvedNum) : undefined,
      planned_resolve_chapter: plannedNum ? Number(plannedNum) : undefined,
      planned_action: plannedAction,
      status,
      priority,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm space-y-3">
      <div>
        <label className="block text-xs text-gray-500 mb-1">伏笔标题 *</label>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          placeholder="一句话概括这条伏笔"
          value={title}
          onChange={e => setTitle(e.target.value)}
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">详细描述</label>
        <textarea
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
          rows={2}
          placeholder="伏笔内容、埋设场景、回收方向……"
          value={description}
          onChange={e => setDescription(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">埋设章节号</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={laidNum} onChange={e => setLaidNum(e.target.value)} placeholder="第 N 章" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">计划动作</label>
          <select
            className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={plannedAction}
            onChange={e => setPlannedAction(e.target.value as 'resolve' | 'develop')}
          >
            <option value="resolve">回收</option>
            <option value="develop">铺垫</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">计划章节</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={plannedNum} onChange={e => setPlannedNum(e.target.value)} placeholder="约第 N 章" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">实际回收章节</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={resolvedNum} onChange={e => setResolvedNum(e.target.value)} placeholder="填后自动变更" />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">状态</label>
          <select
            className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={status}
            onChange={e => setStatus(e.target.value as Foreshadow['status'])}
          >
            <option value="open">未回收</option>
            <option value="resolved">已回收</option>
            <option value="dropped">已放弃</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">重要度</label>
          <div className="flex items-center gap-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <button key={i} type="button" onClick={() => setPriority(i + 1)}>
                <Star size={16} className={i < priority ? 'text-amber-400 fill-amber-400' : 'text-gray-200 hover:text-amber-300'} />
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-end pt-1">
        <button type="button" onClick={onCancel}
          className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">
          取消
        </button>
        <button type="submit"
          className="px-4 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors font-medium">
          保存
        </button>
      </div>
    </form>
  )
}
