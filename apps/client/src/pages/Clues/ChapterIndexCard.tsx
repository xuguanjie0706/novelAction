/**
 * ChapterIndexCard — 情节档案单条卡片（展开/折叠详情）
 */
import React, { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import type { ChapterIndex } from '../../types'

export default function ChapterIndexCard({ index, chapterTitle }: { index: ChapterIndex; chapterTitle?: string }) {
  const [expanded, setExpanded] = useState(false)
  const hookIcons = ['', '⭐', '⭐⭐', '⭐⭐⭐', '⭐⭐⭐⭐', '⭐⭐⭐⭐⭐']

  return (
    <div className="rounded-xl border border-gray-100 bg-white hover:shadow-md transition-shadow">
      <button type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between p-3 text-left">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-mono text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded shrink-0">
            Ch.{index.chapter_number.toString().padStart(3, '0')}
          </span>
          <span className="text-sm font-medium text-gray-800 truncate">
            {chapterTitle || `第 ${index.chapter_number} 章`}
          </span>
          {index.story_day && (
            <span className="text-[10px] text-gray-400 shrink-0">{index.story_day}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {index.hook_strength > 0 && (
            <span className="text-[11px]" title={`章末钩子强度 ${index.hook_strength}`}>
              {hookIcons[Math.min(index.hook_strength, 5)]}
            </span>
          )}
          {expanded ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-gray-50 pt-2">
          {/* 核心事件 */}
          {index.core_events?.length > 0 && (
            <div>
              <div className="text-[10px] text-gray-400 uppercase font-medium mb-1">核心事件</div>
              <ul className="space-y-0.5">
                {index.core_events.map((ev, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-1.5">
                    <span className="text-gray-300 shrink-0">•</span>
                    <span>{typeof ev === 'string' ? ev : JSON.stringify(ev)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 伏笔埋设 */}
          {index.actual_foreshadows_laid?.length > 0 && (
            <div>
              <div className="text-[10px] text-amber-500 uppercase font-medium mb-1">埋下伏笔</div>
              {index.actual_foreshadows_laid.map((f, i) => (
                <div key={i} className="text-xs text-gray-600 bg-amber-50 rounded px-2 py-1 mb-0.5">
                  {typeof f === 'string' ? f : (f.description as string)}
                </div>
              ))}
            </div>
          )}

          {/* 伏笔回收 */}
          {index.actual_foreshadows_resolved?.length > 0 && (
            <div>
              <div className="text-[10px] text-green-500 uppercase font-medium mb-1">回收伏笔</div>
              {index.actual_foreshadows_resolved.map((f, i) => (
                <div key={i} className="text-xs text-gray-600 bg-green-50 rounded px-2 py-1 mb-0.5">
                  {typeof f === 'string' ? f : (f.description as string)}
                </div>
              ))}
            </div>
          )}

          {/* 章末钩子 */}
          {index.ending_hook && (
            <div>
              <div className="text-[10px] text-blue-400 uppercase font-medium mb-1">章末钩子</div>
              <p className="text-xs text-gray-600 italic">"{index.ending_hook}"</p>
            </div>
          )}

          {/* 连续性风险 */}
          {index.continuity_notes?.length > 0 && (
            <div>
              <div className="text-[10px] text-red-400 uppercase font-medium mb-1 flex items-center gap-1">
                <AlertTriangle size={9} />连续性风险
              </div>
              {index.continuity_notes.map((n, i) => (
                <div key={i} className="text-xs text-gray-600 bg-red-50 rounded px-2 py-1 mb-0.5">
                  {typeof n === 'string' ? n : JSON.stringify(n)}
                </div>
              ))}
            </div>
          )}

          {/* 首次出场 */}
          {index.first_appearances?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-[10px] text-gray-400">首次出场：</span>
              {index.first_appearances.map((f, i) => (
                <span key={i} className="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded">
                  {(f as any).name || JSON.stringify(f)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
