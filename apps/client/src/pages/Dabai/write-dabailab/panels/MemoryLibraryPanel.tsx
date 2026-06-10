/**
 * 记忆库 — 全书复盘记忆，按章分组倒序，支持类型筛选与关键词过滤。
 * 数据：GET /dabai/projects/{pid}/memory（复盘落库，章级幂等）。
 */
import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Brain, Loader2, Search } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabMemory } from '../../../../types/dabaiLab'
import { MEM_TYPE_LABELS } from '../side/labels'

interface Props {
  projectId: string
}

const TYPE_FILTERS = ['all', 'summary', 'fact', 'event', 'state', 'relation'] as const

export default function MemoryLibraryPanel({ projectId }: Props) {
  const [items, setItems] = useState<DabaiLabMemory[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    dabaiLabApi.listMemory(projectId)
      .then(res => { if (!cancelled) setItems(res.data.items) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId])

  const grouped = useMemo(() => {
    const kw = keyword.trim()
    const filtered = items.filter(m =>
      (typeFilter === 'all' || m.mem_type === typeFilter)
      && (!kw || m.content.includes(kw) || m.tags.some(t => t.includes(kw))))
    const map = new Map<number, DabaiLabMemory[]>()
    for (const m of filtered) {
      const list = map.get(m.chapter_number) ?? []
      list.push(m)
      map.set(m.chapter_number, list)
    }
    return [...map.entries()].sort((a, b) => b[0] - a[0])
  }, [items, typeFilter, keyword])

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Brain size={16} className="text-violet-500" />
        <h2 className="text-sm font-semibold text-gray-900">记忆库</h2>
        <span className="text-xs text-gray-400">{items.length} 条 · 复盘自动提取</span>
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1">
          <Search size={12} className="text-gray-300" />
          <input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="搜内容/人名"
            className="w-28 bg-transparent text-xs outline-none placeholder:text-gray-300"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {TYPE_FILTERS.map(t => (
          <button
            key={t}
            type="button"
            onClick={() => setTypeFilter(t)}
            className={clsx(
              'rounded-full px-2.5 py-0.5 text-xs',
              typeFilter === t ? 'bg-violet-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200',
            )}
          >
            {t === 'all' ? '全部' : MEM_TYPE_LABELS[t] ?? t}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 size={14} className="animate-spin" /> 加载中…
        </p>
      ) : grouped.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          暂无记忆——在写作页右侧「记忆」面板对已写章节执行复盘
        </p>
      ) : (
        grouped.map(([chapterNumber, mems]) => (
          <section key={chapterNumber} className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
            <h3 className="mb-2 text-xs font-semibold text-gray-500">第{chapterNumber}章</h3>
            <ul className="space-y-2">
              {mems.map(m => (
                <li key={m.id} className="text-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                      {MEM_TYPE_LABELS[m.mem_type] ?? m.mem_type}
                    </span>
                    <span className="text-[10px] text-amber-500">{'★'.repeat(m.importance)}</span>
                    {m.tags.map(t => (
                      <span key={t} className="text-[10px] text-gray-400">#{t}</span>
                    ))}
                  </div>
                  <p className="mt-0.5 text-gray-700">{m.content}</p>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}
