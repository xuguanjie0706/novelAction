import React, { useEffect, useState } from 'react'
import { ClipboardList, Loader2, RefreshCw, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { aiApi, chapterIndexesApi } from '../../api/client'
import type { Chapter, ChapterIndex } from '../../types'
import { displayChapterNumber } from '../../utils/chapterNumbering'

function dictLine(d: Record<string, unknown>): string {
  const v = d.description ?? d.name ?? d.content ?? d.note ?? d.title
  if (v != null && String(v).trim()) return String(v).trim()
  try {
    return JSON.stringify(d)
  } catch {
    return ''
  }
}

function coreEventsToText(events: Array<Record<string, unknown> | string> | undefined): string {
  if (!events?.length) return ''
  return events
    .map((ev) => (typeof ev === 'string' ? ev : dictLine(ev as Record<string, unknown>)))
    .filter(Boolean)
    .join('\n')
}

function linesToStrings(text: string): string[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
}

function firstAppearancesToText(items: Array<Record<string, unknown>> | undefined): string {
  if (!items?.length) return ''
  return items.map((d) => dictLine(d)).filter(Boolean).join('\n')
}

function linesToDicts(text: string): Array<Record<string, unknown>> {
  return linesToStrings(text).map((line) => ({ description: line }))
}

function foreshadowsToText(items: Array<Record<string, unknown>> | undefined): string {
  if (!items?.length) return ''
  return items
    .map((d) => {
      const code = d.code != null ? String(d.code).trim() : ''
      const body = dictLine(d)
      if (code && body && !body.toUpperCase().includes(code.toUpperCase())) return `${code} ${body}`
      return body
    })
    .filter(Boolean)
    .join('\n')
}

function continuityToText(notes: Array<Record<string, unknown> | string> | undefined): string {
  if (!notes?.length) return ''
  return notes
    .map((n) => (typeof n === 'string' ? n : dictLine(n as Record<string, unknown>)))
    .filter(Boolean)
    .join('\n')
}

function linesToContinuity(text: string): Array<string> {
  return linesToStrings(text)
}

interface Props {
  projectId: string
  chapter: Chapter
  index: ChapterIndex | null
  onSaved: (next: ChapterIndex | null) => void
  onForeshadowsMayChange?: () => void
}

const LABEL = 'text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider'
const INPUT =
  'w-full rounded-novel border border-novel-border bg-novel-card px-2.5 py-2 text-xs text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus:ring-2 focus:ring-novel-accent/30'

export default function ChapterIndexEditPanel({
  projectId,
  chapter,
  index,
  onSaved,
  onForeshadowsMayChange,
}: Props) {
  const chNum = displayChapterNumber(chapter.title, chapter.sort_order)

  const [storyDay, setStoryDay] = useState('')
  const [coreEvents, setCoreEvents] = useState('')
  const [firstAppearances, setFirstAppearances] = useState('')
  const [foreshadowsLaid, setForeshadowsLaid] = useState('')
  const [foreshadowsResolved, setForeshadowsResolved] = useState('')
  const [endingHook, setEndingHook] = useState('')
  const [hookStrength, setHookStrength] = useState(3)
  const [continuity, setContinuity] = useState('')

  const [saving, setSaving] = useState(false)
  const [reloading, setReloading] = useState(false)

  useEffect(() => {
    setStoryDay(index?.story_day ?? '')
    setCoreEvents(coreEventsToText(index?.core_events))
    setFirstAppearances(firstAppearancesToText(index?.first_appearances))
    setForeshadowsLaid(foreshadowsToText(index?.actual_foreshadows_laid))
    setForeshadowsResolved(foreshadowsToText(index?.actual_foreshadows_resolved))
    setEndingHook(index?.ending_hook ?? '')
    setHookStrength(
      typeof index?.hook_strength === 'number' && index.hook_strength >= 1 && index.hook_strength <= 5
        ? index.hook_strength
        : 3,
    )
    setContinuity(continuityToText(index?.continuity_notes))
  }, [chapter.id, index?.id, index?.updated_at])

  const reloadFromServer = async () => {
    setReloading(true)
    try {
      const res = await chapterIndexesApi.getByChapter(projectId, chapter.id)
      const next = res.data
      if (next) {
        onSaved(next)
        toast.success('已从服务器刷新情节索引')
      } else {
        onSaved(null)
        setStoryDay('')
        setCoreEvents('')
        setFirstAppearances('')
        setForeshadowsLaid('')
        setForeshadowsResolved('')
        setEndingHook('')
        setHookStrength(3)
        setContinuity('')
        toast('本章尚无已保存的索引', { icon: 'ℹ️' })
      }
    } catch {
      toast.error('刷新失败')
    } finally {
      setReloading(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      const chapter_index = {
        story_day: storyDay.trim() || undefined,
        core_events: linesToStrings(coreEvents),
        first_appearances: linesToDicts(firstAppearances),
        actual_foreshadows_laid: linesToDicts(foreshadowsLaid),
        actual_foreshadows_resolved: linesToDicts(foreshadowsResolved),
        ending_hook: endingHook.trim() || undefined,
        hook_strength: Math.min(5, Math.max(1, hookStrength)),
        continuity_notes: linesToContinuity(continuity),
      }

      await aiApi.chapterDebrief(projectId, {
        chapter_id: chapter.id,
        chapter_index,
      })

      const refreshed = await chapterIndexesApi.getByChapter(projectId, chapter.id)
      if (refreshed.data) {
        onSaved(refreshed.data)
        toast.success('情节索引已保存（伏笔表已按条目同步）')
      } else {
        toast.error('保存成功但未读到索引，请点刷新')
      }
      onForeshadowsMayChange?.()
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-start gap-2 rounded-novel border border-blue-100 bg-blue-50/50 px-3 py-2">
        <ClipboardList size={14} className="text-blue-500 shrink-0 mt-0.5" />
        <p className="text-[11px] text-novel-ink leading-relaxed">
          编辑本章「速查索引」并保存后，会写入数据库并同步「本章埋设/回收」到线索页的伏笔表（与 AI 自动复盘提交同一路径）。正文编辑器可只保留故事。
        </p>
      </div>

      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-novel-ink">
          第 {chNum} 章 · {chapter.title}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => void reloadFromServer()}
            disabled={reloading}
            className="inline-flex items-center gap-1 rounded-novel border border-novel-border bg-novel-card px-2 py-1 text-[10px] font-medium text-novel-ink-muted hover:bg-novel-panel disabled:opacity-50"
          >
            {reloading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            重载
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-novel border border-novel-accent bg-novel-accent px-2.5 py-1 text-[10px] font-medium text-white hover:bg-novel-accent-hover disabled:opacity-50"
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
            保存索引
          </button>
        </div>
      </div>

      <div>
        <label className={LABEL}>故事日</label>
        <input
          className={`${INPUT} mt-1`}
          value={storyDay}
          onChange={(e) => setStoryDay(e.target.value)}
          placeholder="例：第8日"
        />
      </div>

      <div>
        <label className={LABEL}>核心事件（每行一条）</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[72px] resize-y font-mono leading-snug`}
          value={coreEvents}
          onChange={(e) => setCoreEvents(e.target.value)}
          placeholder="1. …&#10;2. …"
        />
      </div>

      <div>
        <label className={LABEL}>首次出场（每行一条）</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[56px] resize-y`}
          value={firstAppearances}
          onChange={(e) => setFirstAppearances(e.target.value)}
          placeholder="无则留空；或：角色名（身份）…"
        />
      </div>

      <div>
        <label className={LABEL}>章末钩子</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[48px] resize-y`}
          value={endingHook}
          onChange={(e) => setEndingHook(e.target.value)}
          placeholder="一句话概括悬念"
        />
      </div>

      <div>
        <label className={LABEL}>钩子强度（1–5）</label>
        <select
          className={`${INPUT} mt-1`}
          value={hookStrength}
          onChange={(e) => setHookStrength(Number(e.target.value))}
        >
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {n} 星
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL}>本章埋设伏笔（每行一条，可含 F-032、ch_060回收）</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[64px] resize-y font-mono leading-snug`}
          value={foreshadowsLaid}
          onChange={(e) => setForeshadowsLaid(e.target.value)}
        />
      </div>

      <div>
        <label className={LABEL}>本章回收伏笔</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[48px] resize-y font-mono leading-snug`}
          value={foreshadowsResolved}
          onChange={(e) => setForeshadowsResolved(e.target.value)}
        />
      </div>

      <div>
        <label className={LABEL}>连续性复盘（每行一条）</label>
        <textarea
          className={`${INPUT} mt-1 min-h-[72px] resize-y`}
          value={continuity}
          onChange={(e) => setContinuity(e.target.value)}
          placeholder="境界校验、状态更新、道具状态…"
        />
      </div>
    </div>
  )
}
