/**
 * 情节档案（全书）— 按章可展开卡片，回看每章「实际写了什么」。
 * 计划五拍 + 复盘核心事件 + 线索埋设·回收 + 资产/关系变更 + 首次出场。
 * 数据：GET /dabai/projects/{pid}/archive。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { BookOpen, ChevronDown, ChevronRight, Loader2, Sparkles } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiChapterArchive } from '../../../../types/dabaiLab'
import ArchiveSections from '../ArchiveSections'

const FILTERS = ['all', 'written', 'debriefed'] as const
type Filter = (typeof FILTERS)[number]
const FILTER_LABELS: Record<Filter, string> = {
  all: '全部', written: '已写', debriefed: '已复盘',
}

export default function ArchivePanel({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<DabaiChapterArchive[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')
  const [openId, setOpenId] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    dabaiLabApi.listArchive(projectId)
      .then(res => setItems(res.data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const filtered = useMemo(() => items.filter(a => (
    filter === 'all' ? true
      : filter === 'debriefed' ? a.debriefed
        : a.word_count > 0
  )), [items, filter])

  const writtenCount = items.filter(a => a.word_count > 0).length

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BookOpen size={16} className="text-amber-500" />
        <h2 className="text-sm font-semibold text-gray-900">情节档案</h2>
        <span className="text-xs text-gray-400">
          共 {items.length} 章 · 已写 {writtenCount} 章 · 计划+实际逐章回看
        </span>
      </div>

      <div className="flex flex-wrap gap-1">
        {FILTERS.map(f => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={clsx(
              'rounded-full px-2.5 py-0.5 text-xs',
              filter === f ? 'bg-amber-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200',
            )}
          >
            {FILTER_LABELS[f]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 size={14} className="animate-spin" /> 加载中…
        </p>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">暂无章节档案</p>
      ) : (
        <ul className="space-y-2">
          {filtered.map(a => {
            const expanded = openId === a.chapter_id
            return (
              <li key={a.chapter_id} className="rounded-xl border border-gray-100 bg-white shadow-sm">
                <button
                  type="button"
                  onClick={() => setOpenId(expanded ? null : a.chapter_id)}
                  className="flex w-full items-center gap-2 p-3 text-left"
                >
                  <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[11px] text-amber-600">
                    Ch.{String(a.chapter_number).padStart(3, '0')}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-800">
                    {a.title || `第 ${a.chapter_number} 章`}
                  </span>
                  {a.plan.is_big_beat ? <Sparkles size={12} className="shrink-0 text-amber-400" /> : null}
                  {!a.debriefed ? (
                    <span className="shrink-0 text-[10px] text-gray-300">未复盘</span>
                  ) : null}
                  {expanded
                    ? <ChevronDown size={14} className="shrink-0 text-gray-400" />
                    : <ChevronRight size={14} className="shrink-0 text-gray-400" />}
                </button>
                {expanded ? (
                  <div className="border-t border-gray-50 px-3 pb-3 pt-2">
                    <ArchiveSections archive={a} />
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
