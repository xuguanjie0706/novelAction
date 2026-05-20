import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDownUp,
  Brain,
  Filter,
  Flame,
  ScanLine,
  ShieldAlert,
  Star,
} from 'lucide-react'
import { aiApi } from '../api/client'
import { useAppStore } from '../store'
import type { MemoryChunk, MemoryConflictItem, MemoryConflictReport } from '../types'
import clsx from 'clsx'
import { memoryDisplayChapter } from '../utils/chapterNumber'
import MemoryRagPanel from '../components/Memory/MemoryRagPanel'

// ── 常量 ────────────────────────────────────────────────────────────────────

const MEMORY_TYPES: { key: MemoryChunk['memory_type'] | 'all'; label: string; color: string }[] = [
  { key: 'all',             label: '全部',     color: 'bg-gray-100 text-gray-600' },
  { key: 'event',           label: '事件',     color: 'bg-blue-100 text-blue-700' },
  { key: 'character_state', label: '人物状态', color: 'bg-purple-100 text-purple-700' },
  { key: 'foreshadow',      label: '伏笔',     color: 'bg-amber-100 text-amber-700' },
  { key: 'setting',         label: '设定',     color: 'bg-green-100 text-green-700' },
  { key: 'conflict',        label: '冲突',     color: 'bg-red-100 text-red-700' },
]

type SortKey = 'chapter' | 'importance' | 'access_count'
const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'chapter',      label: '按章节顺序' },
  { key: 'importance',   label: '按重要度' },
  { key: 'access_count', label: '按召回热度' },
]

// ── 辅助函数 ────────────────────────────────────────────────────────────────

function typeColor(t: string) {
  return MEMORY_TYPES.find(m => m.key === t)?.color ?? 'bg-gray-100 text-gray-600'
}
function typeLabel(t: string) {
  return MEMORY_TYPES.find(m => m.key === t)?.label ?? t
}

/**
 * 将 importance_score 映射为徽章样式。
 * ≥0.7 高；≥0.4 中；< 0.4 低
 */
function importanceBadge(score: number): { label: string; cls: string; icon?: React.ReactNode } {
  if (score >= 0.7) return { label: '高', cls: 'bg-rose-100 text-rose-700',   icon: <Star size={10} className="inline mr-0.5" /> }
  if (score >= 0.4) return { label: '中', cls: 'bg-yellow-100 text-yellow-700' }
  return              { label: '低', cls: 'bg-gray-100 text-gray-400' }
}

function severityBadge(s: MemoryConflictItem['severity']) {
  if (s === 'high')   return 'bg-red-100 text-red-700 border-red-200'
  if (s === 'medium') return 'bg-orange-100 text-orange-700 border-orange-200'
  return                     'bg-gray-100 text-gray-500 border-gray-200'
}
function severityLabel(s: MemoryConflictItem['severity']) {
  if (s === 'high')   return '严重'
  if (s === 'medium') return '疑似'
  return '轻微'
}
function conflictTypeLabel(t: string) {
  const m: Record<string, string> = {
    character_state: '角色状态',
    timeline:        '时间线',
    attribute:       '属性矛盾',
    foreshadow:      '伏笔管理',
  }
  return m[t] ?? t
}

// ── 冲突面板 ────────────────────────────────────────────────────────────────

interface ConflictPanelProps {
  projectId: string
  /** 从 Project.extra.memory_conflicts 预加载的报告（可能为 null） */
  cached?: MemoryConflictReport | null
}

/**
 * 记忆冲突扫描面板：展示上次检测结果 + 手动触发重新扫描。
 *
 * 数据来源：先展示 cached（来自项目 extra），点击「重新扫描」后调 detect-conflicts API。
 */
function ConflictPanel({ projectId, cached }: ConflictPanelProps) {
  const [report, setReport] = useState<MemoryConflictReport | null>(cached ?? null)
  const [scanning, setScanning] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  const scan = async () => {
    setScanning(true)
    try {
      const res = await aiApi.detectConflicts(projectId)
      setReport(res.data)
    } catch {
      // 静默失败，保持原报告
    } finally {
      setScanning(false)
    }
  }

  const high   = report?.conflicts.filter(c => c.severity === 'high')   ?? []
  const medium = report?.conflicts.filter(c => c.severity === 'medium') ?? []
  const low    = report?.conflicts.filter(c => c.severity === 'low')    ?? []

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 space-y-3">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-red-500" />
          <span className="text-sm font-semibold text-gray-800">记忆冲突检测</span>
          {report && (
            <span className="text-xs text-gray-400">
              · 已扫 {report.total_chunks_scanned} 条
              {report.conflicts.length > 0 && (
                <> · <span className="text-red-500 font-medium">{report.conflicts.length} 处冲突</span></>
              )}
            </span>
          )}
        </div>
        <button
          type="button"
          disabled={scanning}
          onClick={() => void scan()}
          className={clsx(
            'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors',
            scanning
              ? 'bg-gray-100 text-gray-400 cursor-wait'
              : 'bg-red-50 text-red-700 hover:bg-red-100',
          )}
        >
          <ScanLine size={12} className={scanning ? 'animate-pulse' : ''} />
          {scanning ? '扫描中…' : '重新扫描'}
        </button>
      </div>

      {/* 无报告提示 */}
      {!report && !scanning && (
        <p className="text-xs text-gray-400 text-center py-3">
          点击「重新扫描」分析全量记忆库中的前后矛盾
        </p>
      )}

      {/* 冲突摘要 */}
      {report && report.conflicts.length === 0 && (
        <div className="flex items-center gap-2 text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2">
          <span>✓</span> 未发现冲突
        </div>
      )}

      {/* 冲突列表（严重度分组） */}
      {([['high', high], ['medium', medium], ['low', low]] as const).map(([sev, items]) => {
        if (items.length === 0) return null
        return (
          <div key={sev}>
            <div className="text-xs font-medium text-gray-500 mb-1.5">
              {severityLabel(sev as MemoryConflictItem['severity'])}（{items.length}）
            </div>
            <div className="space-y-1.5">
              {items.map((c, i) => {
                const key = `${sev}-${i}`
                const isOpen = expanded === key
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : key)}
                    className={clsx(
                      'w-full text-left rounded-lg border px-3 py-2 text-xs transition-colors',
                      severityBadge(c.severity),
                      isOpen ? 'shadow-sm' : 'hover:shadow-sm',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span className="shrink-0 font-medium">{conflictTypeLabel(c.conflict_type)}</span>
                      <span className="text-[10px] opacity-70">
                        {c.chapter_refs.length > 0 && `第 ${c.chapter_refs.join('、')} 章`}
                      </span>
                    </div>
                    <p className="mt-0.5 leading-snug">{c.description}</p>
                    {isOpen && c.chunk_ids.length > 0 && (
                      <p className="mt-1 text-[10px] opacity-60 font-mono">
                        涉及记忆：{c.chunk_ids.map(id => id.slice(0, 8)).join(' · ')}
                      </p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}

      {report?.detected_at && (
        <p className="text-[10px] text-gray-300 text-right">
          上次扫描：{new Date(report.detected_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}

// ── 记忆卡片 ────────────────────────────────────────────────────────────────

function MemoryCard({ m }: { m: MemoryChunk }) {
  const imp = importanceBadge(m.importance_score ?? 0.5)

  return (
    <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', typeColor(m.memory_type))}>
            {typeLabel(m.memory_type)}
          </span>
          {m.title && <span className="text-sm font-semibold text-gray-800">{m.title}</span>}
        </div>
        {/* 重要度 + 热度指标 */}
        <div className="flex items-center gap-1.5 shrink-0">
          {(m.access_count ?? 0) >= 5 && (
            <span className="flex items-center gap-0.5 text-[10px] text-orange-500 font-medium">
              <Flame size={10} />
              {m.access_count}
            </span>
          )}
          <span
            className={clsx('text-[10px] px-1.5 py-0.5 rounded-full font-medium border', imp.cls)}
            title={`重要度 ${((m.importance_score ?? 0.5) * 100).toFixed(0)}%`}
          >
            {imp.icon}{imp.label}
          </span>
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
  )
}

// ── 主页面 ──────────────────────────────────────────────────────────────────

export default function MemoryPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { activeChapterId, memories, setMemories, chapters } = useAppStore()
  const [filter, setFilter]   = useState<'all' | MemoryChunk['memory_type']>('all')
  const [search, setSearch]   = useState('')
  const [sortBy, setSortBy]   = useState<SortKey>('chapter')
  const [showSort, setShowSort] = useState(false)
  const [showConflict, setShowConflict] = useState(false)

  // 加载记忆库（排序变化时重新请求后端）
  const loadMemories = useCallback(async () => {
    if (!projectId) return
    const sortParam = sortBy !== 'chapter' ? sortBy : undefined
    const res = await aiApi.listMemory(projectId, { sort_by: sortParam })
    setMemories(res.data)
  }, [projectId, sortBy, setMemories])

  useEffect(() => { loadMemories().catch(() => {}) }, [loadMemories, activeChapterId])

  const chapterById = useMemo(() => {
    const m = new Map<string, { title: string; sort_order: number }>()
    for (const c of chapters) m.set(c.id, { title: c.title, sort_order: c.sort_order })
    return m
  }, [chapters])

  const filtered = memories.filter(m => {
    if (filter !== 'all' && m.memory_type !== filter) return false
    if (search && !m.content.includes(search) && !(m.title?.includes(search))) return false
    return true
  })

  // 章节视图（仅章节顺序模式分组；其他排序直接平铺）
  const byChapter = useMemo(() => {
    if (sortBy !== 'chapter') return null
    return filtered.reduce<Record<number, MemoryChunk[]>>((acc, m) => {
      const ch = memoryDisplayChapter(m, chapterById)
      if (!acc[ch]) acc[ch] = []
      acc[ch].push(m)
      return acc
    }, {})
  }, [filtered, sortBy, chapterById])

  const sortedChapters = byChapter
    ? Object.keys(byChapter).map(Number).sort((a, b) => a - b)
    : []

  const maxChapter = chapters.length
    ? Math.max(...chapters.map(c => c.sort_order))
    : undefined

  const currentSortLabel = SORT_OPTIONS.find(o => o.key === sortBy)?.label ?? '排序'

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
                    : 'border-l-transparent hover:bg-gray-50',
                )}
              >
                <span className={clsx('text-xs px-1.5 py-0.5 rounded-full font-medium', color)}>{label}</span>
                <span className="text-xs text-gray-400">{count}</span>
              </button>
            )
          })}
        </div>

        {/* 统计 */}
        <div className="border-t border-gray-100 p-3 space-y-1">
          <div className="text-xs text-gray-400">共 {memories.length} 条记忆</div>
          <div className="text-xs text-gray-400">
            覆盖 {new Set(memories.map(m => memoryDisplayChapter(m, chapterById))).size} 章
          </div>
        </div>
      </div>

      {/* 中栏：记忆卡片 */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#FAF8F4]">
        {/* 工具栏 */}
        <div className="px-5 py-3 bg-white border-b border-gray-100 shrink-0 flex items-center gap-3">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索记忆内容..."
            className="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
          />
          {/* 排序切换 */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowSort(v => !v)}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
            >
              <ArrowDownUp size={12} />
              {currentSortLabel}
            </button>
            {showSort && (
              <div className="absolute right-0 top-full mt-1 z-10 bg-white border border-gray-100 rounded-lg shadow-md py-1 min-w-[120px]">
                {SORT_OPTIONS.map(o => (
                  <button
                    key={o.key}
                    type="button"
                    onClick={() => { setSortBy(o.key); setShowSort(false) }}
                    className={clsx(
                      'w-full text-left text-xs px-3 py-1.5 hover:bg-gray-50',
                      sortBy === o.key ? 'text-amber-700 font-medium' : 'text-gray-700',
                    )}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {/* 冲突扫描开关 */}
          <button
            type="button"
            onClick={() => setShowConflict(v => !v)}
            className={clsx(
              'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors',
              showConflict
                ? 'bg-red-100 text-red-700'
                : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
            )}
          >
            <AlertTriangle size={12} />
            冲突检测
          </button>
        </div>

        <div className="flex-1 overflow-auto p-5 space-y-4">
          {/* 冲突面板（展开时显示） */}
          {showConflict && projectId && (
            <ConflictPanel projectId={projectId} />
          )}

          {filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <Brain size={40} className="mb-3 opacity-30" />
              <p className="text-sm">暂无记忆条目</p>
              <p className="text-xs mt-1">在写作页面使用「AI → 记忆库 → 提取记忆」自动填充</p>
            </div>
          )}

          {/* 章节顺序模式：分组显示 */}
          {byChapter && sortedChapters.map(ch => (
            <div key={ch}>
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-gray-200" />
                <span className="text-xs font-semibold text-gray-400 px-2">
                  {ch === 0 ? '初始设定' : `第 ${ch} 章`}
                </span>
                <div className="h-px flex-1 bg-gray-200" />
              </div>
              <div className="grid grid-cols-1 gap-2">
                {byChapter[ch].map(m => <MemoryCard key={m.id} m={m} />)}
              </div>
            </div>
          ))}

          {/* 其他排序模式：平铺显示 */}
          {!byChapter && (
            <div className="grid grid-cols-1 gap-2">
              {filtered.map(m => <MemoryCard key={m.id} m={m} />)}
            </div>
          )}
        </div>
      </div>

      {projectId ? <MemoryRagPanel projectId={projectId} maxChapter={maxChapter} /> : null}
    </div>
  )
}
