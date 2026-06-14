/**
 * 记忆库 — 全书复盘记忆，按章分组倒序，支持类型筛选与检索。
 * 数据：GET /dabai/projects/{pid}/memory（复盘落库，章级幂等）。
 *
 * 检索两档（用户可切换）：
 *  - 精确：前端子串匹配（content/tags 包含关键词），即时、零请求；
 *  - 语义：GET /memory/search 走 pgvector 余弦召回，按相关度排序。
 *    pgvector 不可用 / 存量未向量化时后端降级为子串匹配并回 degraded=true。
 */
import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Brain, Loader2, Search, Sparkles, Type } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabMemory } from '../../../../types/dabaiLab'
import { MEM_TYPE_LABELS } from '../side/labels'

interface Props {
  projectId: string
}

const TYPE_FILTERS = ['all', 'summary', 'fact', 'event', 'state', 'relation'] as const
type SearchMode = 'exact' | 'semantic'

/** 单条记忆渲染（含类型/重要度/标签/正文）。 */
function MemoryItem({ m }: { m: DabaiLabMemory }) {
  return (
    <li className="text-sm">
      <div className="flex items-center gap-1.5">
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
          {MEM_TYPE_LABELS[m.mem_type] ?? m.mem_type}
        </span>
        <span className="text-[10px] text-amber-500">{'★'.repeat(m.importance)}</span>
        {m.tags.map(t => (
          <span key={t} className="text-[10px] text-gray-400">#{t}</span>
        ))}
        {typeof m.score === 'number' && (
          <span className="ml-auto text-[10px] text-violet-400">
            相关度 {(1 - m.score).toFixed(2)}
          </span>
        )}
      </div>
      <p className="mt-0.5 text-gray-700">{m.content}</p>
    </li>
  )
}

export default function MemoryLibraryPanel({ projectId }: Props) {
  const [items, setItems] = useState<DabaiLabMemory[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [keyword, setKeyword] = useState('')
  const [searchMode, setSearchMode] = useState<SearchMode>('exact')

  // 语义检索状态
  const [semanticHits, setSemanticHits] = useState<DabaiLabMemory[] | null>(null)
  const [semanticLoading, setSemanticLoading] = useState(false)
  const [degraded, setDegraded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    dabaiLabApi.listMemory(projectId)
      .then(res => { if (!cancelled) setItems(res.data.items) })
      .catch(() => { if (!cancelled) setItems([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId])

  // 语义模式：防抖调后端；关键词为空则清空结果（回落到全量列表）。
  useEffect(() => {
    if (searchMode !== 'semantic') {
      setSemanticHits(null)
      setDegraded(false)
      return
    }
    const kw = keyword.trim()
    if (!kw) {
      setSemanticHits(null)
      setDegraded(false)
      return
    }
    let cancelled = false
    setSemanticLoading(true)
    const timer = setTimeout(() => {
      dabaiLabApi.searchMemory(projectId, kw, 'semantic', 30)
        .then(res => {
          if (cancelled) return
          setSemanticHits(res.data.items)
          setDegraded(res.data.degraded)
        })
        .catch(() => { if (!cancelled) { setSemanticHits([]); setDegraded(false) } })
        .finally(() => { if (!cancelled) setSemanticLoading(false) })
    }, 350)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [projectId, keyword, searchMode])

  const typeOk = (m: DabaiLabMemory) => typeFilter === 'all' || m.mem_type === typeFilter

  // 精确模式：本地子串过滤后按章分组。
  const groupedExact = useMemo(() => {
    const kw = keyword.trim()
    const filtered = items.filter(m =>
      typeOk(m) && (!kw || m.content.includes(kw) || m.tags.some(t => t.includes(kw))))
    const map = new Map<number, DabaiLabMemory[]>()
    for (const m of filtered) {
      const list = map.get(m.chapter_number) ?? []
      list.push(m)
      map.set(m.chapter_number, list)
    }
    return [...map.entries()].sort((a, b) => b[0] - a[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, typeFilter, keyword])

  // 语义模式有关键词时：展示后端相关度排序的扁平列表（仅按类型再过滤）。
  const semanticList = useMemo(
    () => (semanticHits ?? []).filter(typeOk),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [semanticHits, typeFilter],
  )

  const showSemantic = searchMode === 'semantic' && keyword.trim().length > 0

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Brain size={16} className="text-violet-500" />
        <h2 className="text-sm font-semibold text-gray-900">记忆库</h2>
        <span className="text-xs text-gray-400">{items.length} 条 · 复盘自动提取</span>

        {/* 检索模式切换 */}
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-gray-200 p-0.5">
          <button
            type="button"
            onClick={() => setSearchMode('exact')}
            title="精确：关键词子串匹配"
            className={clsx(
              'flex items-center gap-1 rounded-md px-2 py-0.5 text-xs',
              searchMode === 'exact' ? 'bg-gray-800 text-white' : 'text-gray-500 hover:bg-gray-100',
            )}
          >
            <Type size={11} /> 精确
          </button>
          <button
            type="button"
            onClick={() => setSearchMode('semantic')}
            title="语义：pgvector 余弦召回，按相关度排序"
            className={clsx(
              'flex items-center gap-1 rounded-md px-2 py-0.5 text-xs',
              searchMode === 'semantic' ? 'bg-violet-500 text-white' : 'text-gray-500 hover:bg-gray-100',
            )}
          >
            <Sparkles size={11} /> 语义
          </button>
        </div>

        <div className="flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1">
          {semanticLoading
            ? <Loader2 size={12} className="animate-spin text-violet-400" />
            : <Search size={12} className="text-gray-300" />}
          <input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder={searchMode === 'semantic' ? '描述你要找的情节/事实' : '搜内容/人名'}
            className="w-40 bg-transparent text-xs outline-none placeholder:text-gray-300"
          />
        </div>
      </div>

      {showSemantic && degraded && (
        <p className="rounded-md bg-amber-50 px-3 py-1.5 text-[11px] text-amber-600">
          语义检索暂不可用（pgvector 未启用或存量记忆未向量化），已降级为子串匹配。
          可在后端运行 <code className="font-mono">verify_pgvector.py --reembed-dabai</code> 补向量化。
        </p>
      )}

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
      ) : showSemantic ? (
        semanticLoading && semanticList.length === 0 ? (
          <p className="flex items-center gap-2 py-8 text-sm text-gray-400">
            <Loader2 size={14} className="animate-spin" /> 语义检索中…
          </p>
        ) : semanticList.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-400">无语义相关记忆</p>
        ) : (
          <section className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
            <h3 className="mb-2 text-xs font-semibold text-gray-500">
              语义相关（按相关度排序，共 {semanticList.length} 条）
            </h3>
            <ul className="space-y-2">
              {semanticList.map(m => (
                <li key={m.id}>
                  <span className="text-[10px] text-gray-400">第{m.chapter_number}章</span>
                  <MemoryItem m={m} />
                </li>
              ))}
            </ul>
          </section>
        )
      ) : groupedExact.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          {keyword.trim() ? '无匹配记忆' : '暂无记忆——在写作页右侧「记忆」面板对已写章节执行复盘'}
        </p>
      ) : (
        groupedExact.map(([chapterNumber, mems]) => (
          <section key={chapterNumber} className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
            <h3 className="mb-2 text-xs font-semibold text-gray-500">第{chapterNumber}章</h3>
            <ul className="space-y-2">
              {mems.map(m => <MemoryItem key={m.id} m={m} />)}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}
