/**
 * @file 复盘 — 人物状态更新表单
 */
import clsx from 'clsx'
import { Users, Bot, MapPin } from 'lucide-react'
import type { Character } from '../../../../types'
import type { DebriefPanelProps } from '../types'
import { STATUS_LABEL } from './constants'

export interface CharUpdateSectionProps {
  displayChars: Character[]
  charUpdates: DebriefPanelProps['charUpdates']
  aiSuggestedCharIds: Set<string>
  onUpdateChar: (id: string, field: string, value: string) => void
}

export function CharUpdateSection({
  displayChars,
  charUpdates,
  aiSuggestedCharIds,
  onUpdateChar,
}: CharUpdateSectionProps) {
  if (displayChars.length === 0) return null

  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2">
        <Users size={11} className="text-novel-ink-muted" />
        <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
          人物状态更新
        </span>
      </div>
      <div className="space-y-3">
        {displayChars.map(c => {
          const upd = charUpdates[c.id] || {}
          const hasChange = Object.values(upd).some(Boolean)
          const isAiSuggested = aiSuggestedCharIds.has(c.id)
          return (
            <div
              key={c.id}
              className={clsx(
                'rounded-novel border px-3 py-2.5 space-y-2',
                isAiSuggested
                  ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                  : hasChange
                    ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
              )}
            >
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-full bg-novel-shell flex items-center justify-center shrink-0">
                  <span className="text-[9px] text-novel-ink-muted font-semibold">{c.name[0]}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs font-medium text-novel-ink">{c.name}</span>
                    {isAiSuggested && (
                      <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium">
                        <Bot size={8} />
                        AI 建议
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {c.current_realm && (
                      <span className="text-[10px] text-novel-accent">{c.current_realm}</span>
                    )}
                    {c.current_location && (
                      <span className="text-[10px] text-novel-ink-faint">
                        <MapPin size={8} className="inline mr-0.5" />
                        {c.current_location}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">新境界</label>
                  <input
                    type="text"
                    value={upd.current_realm || ''}
                    onChange={e => onUpdateChar(c.id, 'current_realm', e.target.value)}
                    placeholder={c.current_realm || '不变'}
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">新位置</label>
                  <input
                    type="text"
                    value={upd.current_location || ''}
                    onChange={e => onUpdateChar(c.id, 'current_location', e.target.value)}
                    placeholder={c.current_location || '不变'}
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">状态</label>
                  <select
                    value={upd.current_status || ''}
                    onChange={e => onUpdateChar(c.id, 'current_status', e.target.value)}
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  >
                    <option value="">
                      不变（{STATUS_LABEL[c.current_status || 'alive'] || c.current_status}）
                    </option>
                    {Object.entries(STATUS_LABEL).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">习得技能</label>
                  <input
                    type="text"
                    value={upd.add_skill_name || ''}
                    onChange={e => onUpdateChar(c.id, 'add_skill_name', e.target.value)}
                    placeholder="技能名称（可空）"
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
