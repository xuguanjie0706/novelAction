/**
 * ReaderPromisesPage — 读者承诺台账
 *
 * 职责：集中管理作品对读者的所有显式/隐式承诺（章末悬念、卷末钩子、
 * 名字暗示、章评共识、主角宣言），追踪兑现状态。
 *
 * 数据来源：GET /api/v1/projects/{pid}/reader_promises/
 * 操作：新增 / 标记兑现 / 标记破裂 / 删除
 *
 * Bootstrap Step 12 会自动生成开局承诺种子，此页面负责后续的人工维护与状态跟踪。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Plus, Loader2, CheckCircle, XCircle, Circle,
  Star, Eye, BookOpen, ChevronDown, ChevronRight, Trash2, Save, X,
} from 'lucide-react'
import { readerPromisesApi } from '../api/client'
import type { PromiseStatus, PromiseType, ReaderPromise } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// ── 常量 ──────────────────────────────────────────────────

const TYPE_META: Record<PromiseType, { label: string; color: string }> = {
  chapter_ending:            { label: '章末悬念',   color: 'bg-amber-50  text-amber-700  border-amber-200' },
  volume_ending:             { label: '卷末钩子',   color: 'bg-violet-50 text-violet-700 border-violet-200' },
  name_implication:          { label: '名字暗示',   color: 'bg-blue-50   text-blue-700   border-blue-200' },
  chapter_comment_consensus: { label: '章评共识',   color: 'bg-rose-50   text-rose-700   border-rose-200' },
  protagonist_claim:         { label: '主角宣言',   color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
}

const STATUS_META: Record<PromiseStatus, { label: string; icon: React.ReactNode; color: string; dot: string }> = {
  open:      { label: '待兑现', icon: <Circle size={12} />,      color: 'bg-amber-50  text-amber-700',  dot: 'bg-amber-400'  },
  fulfilled: { label: '已兑现', icon: <CheckCircle size={12} />, color: 'bg-green-50  text-green-700',  dot: 'bg-green-400'  },
  broken:    { label: '已破裂', icon: <XCircle size={12} />,     color: 'bg-red-50    text-red-600',    dot: 'bg-red-400'    },
}

const ALL_TYPES = Object.keys(TYPE_META) as PromiseType[]
const PRIORITY_LABELS = ['', '低', '较低', '中', '较高', '高']

// ── 工具 ──────────────────────────────────────────────────

/** 优先级 → 实心星 */
function PriorityDots({ n }: { n: number }) {
  return (
    <span className="flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          size={10}
          className={i < n ? 'text-amber-400 fill-amber-400' : 'text-gray-200 fill-gray-100'}
        />
      ))}
    </span>
  )
}

/** 读者感知度 → 眼睛图标 */
function AwareBar({ n }: { n: number }) {
  return (
    <span className="flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Eye key={i} size={9} className={i < n ? 'text-indigo-400' : 'text-gray-200'} />
      ))}
    </span>
  )
}

// ── 子组件：单条承诺卡片 ──────────────────────────────────

interface PromiseCardProps {
  promise: ReaderPromise
  onUpdate: (updated: ReaderPromise) => void
  onDelete: (id: string) => void
}

/**
 * PromiseCard — 单条承诺展示 + 状态操作。
 * 展开后显示来源章、期望兑现窗口、感知度，并提供「兑现」「破裂」「删除」操作。
 */
function PromiseCard({ promise: p, onUpdate, onDelete }: PromiseCardProps) {
  const [expanded, setExpanded]   = useState(false)
  const [updating, setUpdating]   = useState(false)
  const [deleting, setDeleting]   = useState(false)
  const { projectId }             = useParams<{ projectId: string }>()

  const typeMeta   = TYPE_META[p.promise_type]
  const statusMeta = STATUS_META[p.status]

  const handleStatus = useCallback(async (status: PromiseStatus) => {
    if (updating || !projectId) return
    setUpdating(true)
    try {
      const res = await readerPromisesApi.update(projectId, p.id, { status })
      onUpdate(res.data)
      toast.success(status === 'fulfilled' ? '已标记为兑现' : '已标记为破裂')
    } catch { /* axios 拦截器已 toast */ }
    finally { setUpdating(false) }
  }, [projectId, p.id, updating, onUpdate])

  const handleDelete = useCallback(async () => {
    if (deleting || !projectId || !window.confirm('确认删除这条承诺？')) return
    setDeleting(true)
    try {
      await readerPromisesApi.delete(projectId, p.id)
      onDelete(p.id)
      toast.success('已删除')
    } catch { /* axios 拦截器已 toast */ }
    finally { setDeleting(false) }
  }, [projectId, p.id, deleting, onDelete])

  return (
    <div className={clsx(
      'rounded-xl border bg-white shadow-sm transition-shadow hover:shadow-md overflow-hidden',
      p.status === 'fulfilled' && 'opacity-70',
      p.status === 'broken'    && 'opacity-50',
    )}>
      {/* 卡头 */}
      <div
        className="flex items-start gap-3 px-4 py-3 cursor-pointer select-none"
        onClick={() => setExpanded(v => !v)}
      >
        {/* 状态点 */}
        <span className={clsx('w-2 h-2 rounded-full mt-1.5 shrink-0', statusMeta.dot)} />

        {/* 正文 */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 leading-relaxed">{p.promise_text}</p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium', typeMeta.color)}>
              {typeMeta.label}
            </span>
            {p.source_chapter_number && (
              <span className="text-[10px] text-gray-400">第 {p.source_chapter_number} 章埋</span>
            )}
            {p.expected_chapter_window && (
              <span className="text-[10px] text-gray-400">{p.expected_chapter_window} 章内兑现</span>
            )}
            <PriorityDots n={p.priority} />
          </div>
        </div>

        {/* 折叠箭头 */}
        <span className="text-gray-300 shrink-0 mt-0.5">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-50 pt-3 space-y-3">
          {/* 读者感知度 */}
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>读者感知度</span>
            <AwareBar n={p.audience_aware} />
            <span className="text-gray-400">{p.audience_aware}/5</span>
          </div>

          {/* 兑现信息 */}
          {p.status === 'fulfilled' && p.fulfilled_chapter_number && (
            <div className="flex items-center gap-1.5 text-xs text-green-600">
              <CheckCircle size={12} />
              <span>第 {p.fulfilled_chapter_number} 章已兑现</span>
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex items-center gap-2 pt-1">
            {p.status === 'open' && (
              <>
                <button
                  onClick={() => handleStatus('fulfilled')}
                  disabled={updating}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-green-50 text-green-700 border border-green-200 hover:bg-green-100 disabled:opacity-50 transition-colors"
                >
                  {updating ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle size={11} />}
                  标记兑现
                </button>
                <button
                  onClick={() => handleStatus('broken')}
                  disabled={updating}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors"
                >
                  <XCircle size={11} />破裂
                </button>
              </>
            )}
            {p.status !== 'open' && (
              <button
                onClick={() => handleStatus('open')}
                disabled={updating}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-50 text-gray-500 border border-gray-200 hover:bg-gray-100 disabled:opacity-50"
              >
                <Circle size={11} />恢复待兑现
              </button>
            )}
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="ml-auto flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 disabled:opacity-50 transition-colors"
            >
              <Trash2 size={11} />删除
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 子组件：新增承诺表单 ──────────────────────────────────

interface AddFormProps {
  onSave: (p: ReaderPromise) => void
  onCancel: () => void
}

/**
 * AddForm — 内联新增承诺表单。
 * 必填：promise_text；其余均有默认值。
 */
function AddForm({ onSave, onCancel }: AddFormProps) {
  const { projectId } = useParams<{ projectId: string }>()
  const [text, setText]           = useState('')
  const [type, setType]           = useState<PromiseType>('chapter_ending')
  const [priority, setPriority]   = useState(3)
  const [window_, setWindow]      = useState('')
  const [srcChapter, setSrcChapter] = useState('')
  const [saving, setSaving]       = useState(false)

  const handleSave = async () => {
    if (!text.trim() || !projectId) return
    setSaving(true)
    try {
      const res = await readerPromisesApi.create(projectId, {
        promise_text: text.trim(),
        promise_type: type,
        priority,
        expected_chapter_window: window_ ? Number(window_) : undefined,
        source_chapter_number: srcChapter ? Number(srcChapter) : undefined,
      })
      onSave(res.data)
      toast.success('承诺已添加')
    } catch { /* axios 拦截器已 toast */ }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border-2 border-amber-200 bg-amber-50/30 p-4 space-y-3">
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="承诺内容——写下你对读者的承诺，例如「李明将在十章内突破宗师」"
        rows={3}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-amber-300 resize-none"
        autoFocus
      />
      <div className="flex items-center gap-3 flex-wrap">
        {/* 类型 */}
        <select
          value={type}
          onChange={e => setType(e.target.value as PromiseType)}
          className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-amber-300"
        >
          {ALL_TYPES.map(t => (
            <option key={t} value={t}>{TYPE_META[t].label}</option>
          ))}
        </select>

        {/* 优先级 */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span>优先级</span>
          <select
            value={priority}
            onChange={e => setPriority(Number(e.target.value))}
            className="border border-gray-200 rounded px-1.5 py-1 bg-white text-xs focus:outline-none focus:ring-1 focus:ring-amber-300"
          >
            {[1, 2, 3, 4, 5].map(n => (
              <option key={n} value={n}>{PRIORITY_LABELS[n]}</option>
            ))}
          </select>
        </div>

        {/* 来源章 */}
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <span>来源章</span>
          <input
            type="number" min={1} value={srcChapter} onChange={e => setSrcChapter(e.target.value)}
            placeholder="章号"
            className="w-14 border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-300"
          />
        </div>

        {/* 兑现窗口 */}
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <span>兑现窗口</span>
          <input
            type="number" min={1} value={window_} onChange={e => setWindow(e.target.value)}
            placeholder="章数"
            className="w-14 border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-300"
          />
          <span>章内</span>
        </div>
      </div>

      {/* 操作 */}
      <div className="flex items-center gap-2 justify-end">
        <button onClick={onCancel} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-gray-500 hover:bg-gray-100 border border-gray-200">
          <X size={11} />取消
        </button>
        <button
          onClick={handleSave}
          disabled={!text.trim() || saving}
          className="flex items-center gap-1 text-xs px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
          保存
        </button>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────

type StatusFilter = 'all' | PromiseStatus
type TypeFilter   = 'all' | PromiseType

/**
 * ReaderPromisesPage — 读者承诺台账主页面。
 *
 * 布局：顶部过滤栏 + 承诺列表。
 * 过滤：状态（全部/待兑现/已兑现/已破裂）× 类型（全部/5种）
 */
export default function ReaderPromisesPage() {
  const { projectId }                 = useParams<{ projectId: string }>()
  const [promises, setPromises]       = useState<ReaderPromise[]>([])
  const [loading, setLoading]         = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter]   = useState<TypeFilter>('all')
  const [adding, setAdding]           = useState(false)

  // ── 加载 ──────────────────────────────────────────────
  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    readerPromisesApi.list(projectId)
      .then(res => setPromises(res.data))
      .finally(() => setLoading(false))
  }, [projectId])

  // ── 过滤 ──────────────────────────────────────────────
  const filtered = useMemo(() => {
    return promises.filter(p => {
      if (statusFilter !== 'all' && p.status !== statusFilter) return false
      if (typeFilter   !== 'all' && p.promise_type !== typeFilter) return false
      return true
    })
  }, [promises, statusFilter, typeFilter])

  // ── 统计 ──────────────────────────────────────────────
  const stats = useMemo(() => ({
    all:       promises.length,
    open:      promises.filter(p => p.status === 'open').length,
    fulfilled: promises.filter(p => p.status === 'fulfilled').length,
    broken:    promises.filter(p => p.status === 'broken').length,
  }), [promises])

  const handleAdd    = (p: ReaderPromise) => { setPromises(prev => [p, ...prev]); setAdding(false) }
  const handleUpdate = (updated: ReaderPromise) =>
    setPromises(prev => prev.map(p => p.id === updated.id ? updated : p))
  const handleDelete = (id: string) =>
    setPromises(prev => prev.filter(p => p.id !== id))

  // ── 渲染 ──────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-[#FAF8F4]">
      {/* 顶部工具栏 */}
      <div className="shrink-0 px-6 pt-5 pb-3 bg-white border-b border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-amber-500" />
            <h1 className="text-base font-semibold text-gray-800">读者承诺台账</h1>
            <span className="text-xs text-gray-400">{stats.all} 条</span>
          </div>
          <button
            onClick={() => setAdding(v => !v)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white transition-colors"
          >
            <Plus size={13} />新增承诺
          </button>
        </div>

        {/* 状态过滤 */}
        <div className="flex items-center gap-2 flex-wrap">
          {(['all', 'open', 'fulfilled', 'broken'] as const).map(s => {
            const count = s === 'all' ? stats.all : stats[s]
            const meta  = s === 'all' ? null : STATUS_META[s]
            return (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={clsx(
                  'flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border font-medium transition-colors',
                  statusFilter === s
                    ? 'bg-gray-800 text-white border-gray-800'
                    : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400',
                )}
              >
                {meta && <span className={clsx('w-1.5 h-1.5 rounded-full', meta.dot)} />}
                {s === 'all' ? '全部' : meta!.label}
                <span className={clsx('ml-0.5', statusFilter === s ? 'text-gray-300' : 'text-gray-400')}>
                  {count}
                </span>
              </button>
            )
          })}

          <span className="text-gray-200 mx-1">|</span>

          {/* 类型过滤 */}
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value as TypeFilter)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-amber-300"
          >
            <option value="all">全部类型</option>
            {ALL_TYPES.map(t => (
              <option key={t} value={t}>{TYPE_META[t].label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 列表区 */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {/* 新增表单 */}
        {adding && (
          <AddForm onSave={handleAdd} onCancel={() => setAdding(false)} />
        )}

        {/* 加载 */}
        {loading && (
          <div className="flex items-center justify-center py-16 text-gray-400">
            <Loader2 size={24} className="animate-spin mr-2" />
            <span className="text-sm">加载中…</span>
          </div>
        )}

        {/* 空态 */}
        {!loading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center text-gray-400">
            <BookOpen size={36} className="mb-3 opacity-20" />
            <p className="text-sm font-medium text-gray-500">
              {promises.length === 0 ? '暂无承诺记录' : '没有符合条件的承诺'}
            </p>
            <p className="text-xs mt-1.5 text-gray-400 max-w-[260px] leading-relaxed">
              {promises.length === 0
                ? 'Bootstrap 第 12 步自动生成开局承诺；也可点击「新增承诺」手动添加'
                : '尝试调整过滤条件'}
            </p>
          </div>
        )}

        {/* 承诺列表：按状态分组（open 在前） */}
        {!loading && filtered.length > 0 && (
          <>
            {(['open', 'fulfilled', 'broken'] as PromiseStatus[]).map(s => {
              const group = filtered.filter(p => p.status === s)
              if (group.length === 0) return null
              return (
                <div key={s}>
                  <div className="flex items-center gap-2 mb-2 mt-3 first:mt-0">
                    <span className={clsx('flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full', STATUS_META[s].color)}>
                      {STATUS_META[s].icon}
                      {STATUS_META[s].label}
                    </span>
                    <span className="text-[10px] text-gray-400">{group.length} 条</span>
                  </div>
                  <div className="space-y-2">
                    {group
                      .sort((a, b) => b.priority - a.priority)
                      .map(p => (
                        <PromiseCard
                          key={p.id}
                          promise={p}
                          onUpdate={handleUpdate}
                          onDelete={handleDelete}
                        />
                      ))}
                  </div>
                </div>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}
