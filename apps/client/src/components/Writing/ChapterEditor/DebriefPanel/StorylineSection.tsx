/**
 * @file 复盘 — 故事线推进表单（含织网 volume_beats / actual_beats）
 */
import clsx from 'clsx'
import { Swords, Bot } from 'lucide-react'
import type { StoryLine } from '../../../../types'
import type { DebriefPanelProps, StorylineBeatFormFields } from '../types'
import { STORYLINE_STATUS_LABEL } from './constants'
import { formatPlannedBeatHint } from '../../../../utils/storylineWeaveUtils'

export interface StorylineSectionProps {
  chapterNumber: number
  activeStorylines: StoryLine[]
  storylineBeats: DebriefPanelProps['storylineBeats']
  aiSuggestedSlIds: Set<string>
  onUpdateStoryline: (
    id: string,
    field: keyof StorylineBeatFormFields,
    value: string | number | boolean,
  ) => void
}

export function StorylineSection({
  chapterNumber,
  activeStorylines,
  storylineBeats,
  aiSuggestedSlIds,
  onUpdateStoryline,
}: StorylineSectionProps) {
  if (activeStorylines.length === 0) return null

  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2">
        <Swords size={11} className="text-novel-ink-muted" />
        <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">
          故事线推进
        </span>
      </div>
      <div className="space-y-2">
        {activeStorylines.map(sl => {
          const upd = storylineBeats[sl.id] || {}
          const hasChange = Object.values(upd).some(v => v !== undefined && v !== '' && v !== false)
          const isAiSuggested = aiSuggestedSlIds.has(sl.id)
          const plannedHint = formatPlannedBeatHint(sl, chapterNumber)
          return (
            <div
              key={sl.id}
              className={clsx(
                'rounded-novel border px-3 py-2.5 space-y-1.5',
                isAiSuggested
                  ? 'border-amber-300 bg-amber-50/60 ring-1 ring-amber-200'
                  : hasChange
                    ? 'border-novel-accent/40 bg-amber-50/40'
                    : 'border-novel-border bg-novel-card',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-xs font-medium text-novel-ink truncate">{sl.name}</span>
                  {isAiSuggested && (
                    <span className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-700 font-medium shrink-0">
                      <Bot size={8} />
                      AI
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-novel-ink-faint shrink-0">
                  {STORYLINE_STATUS_LABEL[sl.status] || sl.status}
                </span>
              </div>
              {plannedHint && (
                <p className="text-[10px] text-indigo-700/90 bg-indigo-50/80 rounded px-2 py-1">
                  {plannedHint}
                </p>
              )}
              <div className="grid grid-cols-2 gap-1.5">
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">更新状态</label>
                  <select
                    value={upd.status || ''}
                    onChange={e => onUpdateStoryline(sl.id, 'status', e.target.value)}
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  >
                    <option value="">不变</option>
                    {Object.entries(STORYLINE_STATUS_LABEL).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">本章节拍</label>
                  <input
                    type="text"
                    value={upd.beat || ''}
                    onChange={e => onUpdateStoryline(sl.id, 'beat', e.target.value)}
                    placeholder="发生了什么（可空）"
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">实际张力 0–100</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={upd.actual_tension === '' || upd.actual_tension == null ? '' : upd.actual_tension}
                    onChange={e => onUpdateStoryline(
                      sl.id,
                      'actual_tension',
                      e.target.value === '' ? '' : Number(e.target.value),
                    )}
                    placeholder="—"
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">节拍匹配 0–1</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={upd.beat_match_score === '' || upd.beat_match_score == null ? '' : upd.beat_match_score}
                    onChange={e => onUpdateStoryline(
                      sl.id,
                      'beat_match_score',
                      e.target.value === '' ? '' : Number(e.target.value),
                    )}
                    placeholder="AI 可填"
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-novel-ink-faint block mb-0.5">戏份字数</label>
                  <input
                    type="number"
                    min={0}
                    value={upd.screen_time_words === '' || upd.screen_time_words == null ? '' : upd.screen_time_words}
                    onChange={e => onUpdateStoryline(
                      sl.id,
                      'screen_time_words',
                      e.target.value === '' ? '' : Number(e.target.value),
                    )}
                    placeholder="约多少字"
                    className="w-full text-[11px] border border-novel-border rounded px-2 py-1 bg-white"
                  />
                </div>
                <div className="flex items-end pb-1">
                  <label className="flex items-center gap-1.5 text-[11px] text-novel-ink cursor-pointer">
                    <input
                      type="checkbox"
                      checked={upd.crossover_executed === true}
                      onChange={e => onUpdateStoryline(sl.id, 'crossover_executed', e.target.checked)}
                      className="rounded border-novel-border"
                    />
                    本章已执行交叉线
                  </label>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
