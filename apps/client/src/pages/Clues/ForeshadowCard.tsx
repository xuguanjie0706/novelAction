/**
 * ForeshadowCard — 单条伏笔卡片（展开/折叠、状态切换、编辑/删除）
 */
import React, { useState } from 'react'
import { CheckCircle, XCircle, Circle, ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import type { Foreshadow } from '../../types'
import {
  STATUS_LABEL, STATUS_COLOR, STATUS_ICON,
  PLANNED_ACTION_LABEL, PLANNED_ACTION_COLOR, PRIORITY_STARS,
} from './constants'

export interface ForeshadowCardProps {
  item: Foreshadow
  onEdit: () => void
  onDelete: () => void
  onStatusChange: (s: Foreshadow['status']) => void
}

export default function ForeshadowCard({ item, onEdit, onDelete, onStatusChange }: ForeshadowCardProps) {
  const [expanded, setExpanded] = useState(false)
  const plannedAction = item.planned_action ?? 'resolve'

  return (
    <div className={clsx(
      'rounded-xl border transition-shadow hover:shadow-md',
      item.status === 'resolved' ? 'border-green-100 bg-green-50/30' :
      item.status === 'dropped' ? 'border-gray-100 bg-gray-50/50 opacity-60' :
      'border-amber-100 bg-white',
    )}>
      <div className="p-3">
        <div className="flex items-start gap-2">
          {/* 编号 + 重要度 */}
          <div className="flex flex-col items-center gap-1 pt-0.5 shrink-0">
            {item.code && (
              <span className="text-[10px] font-mono text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                {item.code}
              </span>
            )}
            <div className="flex gap-0.5">{PRIORITY_STARS(item.priority)}</div>
          </div>

          {/* 主体 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm text-gray-800">{item.title}</span>
              <span className={clsx('inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-medium', STATUS_COLOR[item.status])}>
                {STATUS_ICON[item.status]}{STATUS_LABEL[item.status]}
              </span>
            </div>

            {/* 章节标签 */}
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {item.laid_chapter_number != null && (
                <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                  埋设：第 {item.laid_chapter_number} 章
                </span>
              )}
              {item.planned_resolve_chapter != null && item.status === 'open' && (
                <span className={clsx('text-[10px] px-1.5 py-0.5 rounded', PLANNED_ACTION_COLOR[plannedAction])}>
                  {PLANNED_ACTION_LABEL[plannedAction]}：第 {item.planned_resolve_chapter} 章
                </span>
              )}
              {item.resolved_chapter_number != null && (
                <span className="text-[10px] bg-green-50 text-green-600 px-1.5 py-0.5 rounded">
                  回收：第 {item.resolved_chapter_number} 章
                </span>
              )}
            </div>

            {/* 描述展开 */}
            {item.description && (
              <button type="button"
                onClick={() => setExpanded(v => !v)}
                className="flex items-center gap-1 mt-1.5 text-[11px] text-gray-400 hover:text-gray-600 transition-colors">
                {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                {expanded ? '收起' : '展开描述'}
              </button>
            )}
            {expanded && item.description && (
              <p className="mt-1.5 text-xs text-gray-600 leading-relaxed bg-gray-50 rounded-lg p-2">
                {item.description}
              </p>
            )}
          </div>

          {/* 操作 */}
          <div className="flex items-center gap-1 shrink-0">
            {item.status !== 'resolved' && (
              <button type="button" title="标记已回收"
                onClick={() => onStatusChange('resolved')}
                className="p-1 rounded text-gray-300 hover:text-green-500 transition-colors">
                <CheckCircle size={14} />
              </button>
            )}
            {item.status === 'open' && (
              <button type="button" title="放弃此伏笔"
                onClick={() => onStatusChange('dropped')}
                className="p-1 rounded text-gray-300 hover:text-gray-500 transition-colors">
                <XCircle size={14} />
              </button>
            )}
            {item.status !== 'open' && (
              <button type="button" title="重新激活"
                onClick={() => onStatusChange('open')}
                className="p-1 rounded text-gray-300 hover:text-amber-500 transition-colors">
                <Circle size={14} />
              </button>
            )}
            <button type="button" title="编辑" onClick={onEdit}
              className="p-1 rounded text-gray-300 hover:text-blue-500 transition-colors text-xs font-medium">
              编辑
            </button>
            <button type="button" title="删除" onClick={onDelete}
              className="p-1 rounded text-gray-300 hover:text-red-500 transition-colors">
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
