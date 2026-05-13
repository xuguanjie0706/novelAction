import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Plus, Loader2, Trash2, CheckCircle, XCircle, Circle,
  ChevronDown, ChevronRight, BookMarked, ClipboardList,
  AlertTriangle, Star, Anchor, Wand2, ExternalLink, Save,
} from 'lucide-react'
import { foreshadowsApi, chapterIndexesApi, qualityDebtsApi, chaptersApi, aiApi } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { Foreshadow, ChapterIndex, QualityDebt } from '../types'
import { useAppStore, modelProfileFromRoute, llmProviderIdFromRoute } from '../store'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import {
  splitStreamedDraftText,
  parseChapterIndexMarkdown,
  fallbackChapterIndexFromRawMarkdown,
  htmlToPlainForSplit,
} from '../utils/draftChapterIndexSplit'
import { plainTextDraftToHtml } from '../utils/draftAssistSse'
import { postDraftAssistAccumulatedWithPrewriteRetry } from '../utils/draftPrewriteBlocked'

// ── 工具 ─────────────────────────────────────────────────────────────────────
const CHAPTER_NUM_PREFIX = /^\s*第\s*0*(\d+)\s*章/

function displayChapterNumber(title?: string, sortOrder?: number): number {
  const raw = (title || '').trim()
  const m = CHAPTER_NUM_PREFIX.exec(raw)
  if (m) return Math.max(1, Number(m[1]))
  const so = Number.isFinite(sortOrder as number) ? Number(sortOrder) : 0
  return Math.max(1, so + 1)
}

function manuscriptRawSnapshotForContinue(chapterContentHtml: string, accumulatedPlain: string): string {
  const prev = htmlToPlainForSplit(chapterContentHtml || '').trim()
  const acc = accumulatedPlain.trim()
  if (!prev) return acc
  if (!acc) return prev
  return `${prev}\n\n${acc}`
}

const STATUS_LABEL: Record<string, string> = { open: '未回收', resolved: '已回收', dropped: '已放弃' }
const STATUS_COLOR: Record<string, string> = {
  open: 'bg-amber-100 text-amber-700 border-amber-200',
  resolved: 'bg-green-100 text-green-700 border-green-200',
  dropped: 'bg-gray-100 text-gray-400 border-gray-200',
}
const STATUS_ICON: Record<string, React.ReactNode> = {
  open: <Circle size={12} />,
  resolved: <CheckCircle size={12} />,
  dropped: <XCircle size={12} />,
}
const PLANNED_ACTION_LABEL: Record<'resolve' | 'develop', string> = {
  resolve: '预计回收',
  develop: '预计铺垫',
}
const PLANNED_ACTION_COLOR: Record<'resolve' | 'develop', string> = {
  resolve: 'bg-amber-50 text-amber-600',
  develop: 'bg-indigo-50 text-indigo-600',
}
const QUALITY_DEBT_STATUS_LABEL: Record<QualityDebt['status'], string> = {
  pending: '未解决',
  resolved: '已修复',
  dismissed: '已忽略',
}
const QUALITY_DEBT_STATUS_COLOR: Record<QualityDebt['status'], string> = {
  pending: 'bg-red-50 text-red-700 border-red-100',
  resolved: 'bg-green-50 text-green-700 border-green-100',
  dismissed: 'bg-gray-50 text-gray-500 border-gray-100',
}
const QUALITY_DEBT_SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-gray-100 text-gray-500',
}
const PRIORITY_STARS = (p: number) =>
  Array.from({ length: 5 }).map((_, i) => (
    <Star key={i} size={10} className={i < p ? 'text-amber-400 fill-amber-400' : 'text-gray-200'} />
  ))

// ── 伏笔表单 ──────────────────────────────────────────────────────────────────

interface ForeshadowFormProps {
  initial?: Partial<Foreshadow>
  onSave: (data: Partial<Foreshadow>) => void
  onCancel: () => void
}

function ForeshadowForm({ initial = {}, onSave, onCancel }: ForeshadowFormProps) {
  const [title, setTitle] = useState(initial.title ?? '')
  const [description, setDescription] = useState(initial.description ?? '')
  const [laidNum, setLaidNum] = useState<string>(initial.laid_chapter_number?.toString() ?? '')
  const [resolvedNum, setResolvedNum] = useState<string>(
    initial.resolved_chapter_number?.toString() ?? '',
  )
  const [plannedNum, setPlannedNum] = useState<string>(
    initial.planned_resolve_chapter?.toString() ?? '',
  )
  const [plannedAction, setPlannedAction] = useState<'resolve' | 'develop'>(
    initial.planned_action ?? 'resolve',
  )
  const [status, setStatus] = useState<Foreshadow['status']>(initial.status ?? 'open')
  const [priority, setPriority] = useState(initial.priority ?? 3)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) { toast.error('伏笔标题不能为空'); return }
    onSave({
      title: title.trim(),
      description: description.trim() || undefined,
      laid_chapter_number: laidNum ? Number(laidNum) : undefined,
      resolved_chapter_number: resolvedNum ? Number(resolvedNum) : undefined,
      planned_resolve_chapter: plannedNum ? Number(plannedNum) : undefined,
      planned_action: plannedAction,
      status,
      priority,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm space-y-3">
      <div>
        <label className="block text-xs text-gray-500 mb-1">伏笔标题 *</label>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          placeholder="一句话概括这条伏笔"
          value={title}
          onChange={e => setTitle(e.target.value)}
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">详细描述</label>
        <textarea
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
          rows={2}
          placeholder="伏笔内容、埋设场景、回收方向……"
          value={description}
          onChange={e => setDescription(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">埋设章节号</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={laidNum} onChange={e => setLaidNum(e.target.value)} placeholder="第 N 章" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">计划动作</label>
          <select
            className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={plannedAction}
            onChange={e => setPlannedAction(e.target.value as 'resolve' | 'develop')}
          >
            <option value="resolve">回收</option>
            <option value="develop">铺垫</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">计划章节</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={plannedNum} onChange={e => setPlannedNum(e.target.value)} placeholder="约第 N 章" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">实际回收章节</label>
          <input type="number" min={1} className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={resolvedNum} onChange={e => setResolvedNum(e.target.value)} placeholder="填后自动变更" />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">状态</label>
          <select
            className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            value={status}
            onChange={e => setStatus(e.target.value as Foreshadow['status'])}
          >
            <option value="open">未回收</option>
            <option value="resolved">已回收</option>
            <option value="dropped">已放弃</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">重要度</label>
          <div className="flex items-center gap-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <button key={i} type="button" onClick={() => setPriority(i + 1)}>
                <Star size={16} className={i < priority ? 'text-amber-400 fill-amber-400' : 'text-gray-200 hover:text-amber-300'} />
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="flex gap-2 justify-end pt-1">
        <button type="button" onClick={onCancel}
          className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">
          取消
        </button>
        <button type="submit"
          className="px-4 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors font-medium">
          保存
        </button>
      </div>
    </form>
  )
}

// ── 伏笔卡片 ──────────────────────────────────────────────────────────────────

interface ForeshadowCardProps {
  item: Foreshadow
  onEdit: () => void
  onDelete: () => void
  onStatusChange: (s: Foreshadow['status']) => void
}

function ForeshadowCard({ item, onEdit, onDelete, onStatusChange }: ForeshadowCardProps) {
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

// ── 情节档案卡片 ──────────────────────────────────────────────────────────────

function ChapterIndexCard({ index, chapterTitle }: { index: ChapterIndex; chapterTitle?: string }) {
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

// ── 质量债务卡片 ──────────────────────────────────────────────────────────────

function QualityDebtCard({
  debt,
  chapterTitle,
  isAiFixing,
  onStatusChange,
  onSaveAuthorNotes,
  onAiFix,
  onOpenWrite,
}: {
  debt: QualityDebt
  chapterTitle?: string
  isAiFixing: boolean
  onStatusChange: (status: QualityDebt['status']) => void
  onSaveAuthorNotes: (id: string, notes: string) => Promise<void>
  onAiFix: (debt: QualityDebt, mode: 'micro' | 'rewrite' | 'continue') => Promise<void>
  onOpenWrite: (debt: QualityDebt) => void
}) {
  const [notesDraft, setNotesDraft] = useState(debt.author_notes ?? '')
  const [savingNotes, setSavingNotes] = useState(false)
  const [fixMode, setFixMode] = useState<'micro' | 'rewrite' | 'continue'>('micro')

  useEffect(() => {
    setNotesDraft(debt.author_notes ?? '')
  }, [debt.id, debt.author_notes])

  const saveNotes = async () => {
    setSavingNotes(true)
    try {
      await onSaveAuthorNotes(debt.id, notesDraft)
    } finally {
      setSavingNotes(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-mono text-red-600 bg-red-50 px-1.5 py-0.5 rounded">
              Ch.{debt.source_chapter_number.toString().padStart(3, '0')}
            </span>
            <span className={clsx(
              'text-[10px] px-1.5 py-0.5 rounded font-medium',
              QUALITY_DEBT_SEVERITY_COLOR[debt.severity] || QUALITY_DEBT_SEVERITY_COLOR.medium,
            )}>
              {debt.severity}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
              {debt.issue_type}
            </span>
            <span className={clsx(
              'text-[10px] px-1.5 py-0.5 rounded border',
              QUALITY_DEBT_STATUS_COLOR[debt.status],
            )}>
              {QUALITY_DEBT_STATUS_LABEL[debt.status]}
            </span>
          </div>
          <div className="text-sm font-medium text-gray-800">
            {chapterTitle || `第 ${debt.source_chapter_number} 章`}
          </div>
        </div>
        {debt.status === 'pending' && (
          <AlertTriangle size={16} className="text-red-400 shrink-0 mt-1" />
        )}
      </div>

      <p className="text-sm text-gray-700 leading-6">{debt.summary}</p>
      {debt.suggested_fix && (
        <p className="text-xs text-gray-500 leading-5 bg-gray-50 rounded-lg px-2 py-1.5">
          修正方向：{debt.suggested_fix}
        </p>
      )}

      <div className="space-y-1.5 rounded-lg border border-amber-100 bg-amber-50/40 px-2 py-2">
        <div className="text-[10px] font-medium text-amber-800">手动修复</div>
        <textarea
          value={notesDraft}
          onChange={e => setNotesDraft(e.target.value)}
          placeholder="记录你打算怎么改、改了哪里（可选，会一并交给定向 AI 修复）"
          rows={2}
          className="w-full text-xs border border-amber-100 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-amber-300 bg-white"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void saveNotes()}
            disabled={savingNotes}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-amber-200 text-amber-900 hover:bg-amber-100/80 disabled:opacity-50"
          >
            {savingNotes ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            保存备注
          </button>
          <button
            type="button"
            onClick={() => onOpenWrite(debt)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-200 text-gray-700 hover:bg-white"
          >
            <ExternalLink size={12} />去写作页改稿
          </button>
        </div>
      </div>

      {debt.status === 'pending' && (
        <div className="space-y-1.5 rounded-lg border border-violet-100 bg-violet-50/30 px-2 py-2">
          <div className="text-[10px] font-medium text-violet-800">AI 修复（定向注入本条债务）</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={fixMode}
              onChange={e => setFixMode(e.target.value as 'micro' | 'rewrite' | 'continue')}
              className="text-xs border border-violet-100 rounded-lg px-2 py-1 bg-white max-w-[220px]"
            >
              <option value="micro">局部微调（摘录替换，改动最小）</option>
              <option value="rewrite">整章重写</option>
              <option value="continue">续写追加（文末补改）</option>
            </select>
            <button
              type="button"
              onClick={() => void onAiFix(debt, fixMode)}
              disabled={isAiFixing}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
            >
              {isAiFixing ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
              {isAiFixing ? '生成中…' : 'AI 修复本章'}
            </button>
          </div>
          <p className="text-[10px] text-violet-700/90 leading-relaxed">
            「局部微调」由模型标出一段原文并替换，适合句式/事实级问题；若提示无法唯一定位或失败，请改选整章重写。流式模式会尝试解析稿末索引。
          </p>
        </div>
      )}

      <div className="flex items-center gap-2 pt-1 flex-wrap">
        <button
          type="button"
          onClick={() => onStatusChange('resolved')}
          disabled={debt.status === 'resolved'}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-green-100 text-green-700 hover:bg-green-50 disabled:opacity-50"
        >
          <CheckCircle size={12} />已修复
        </button>
        <button
          type="button"
          onClick={() => onStatusChange('dismissed')}
          disabled={debt.status === 'dismissed'}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-100 text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          <XCircle size={12} />忽略
        </button>
        {debt.status !== 'pending' && (
          <button
            type="button"
            onClick={() => onStatusChange('pending')}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-red-100 text-red-600 hover:bg-red-50"
          >
            <Circle size={12} />重开
          </button>
        )}
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

type TabKey = 'foreshadow' | 'plotarchive' | 'qualitydebt'

export default function CluesPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { chapters, upsertChapter, aiBackendRoute } = useAppStore()

  const [activeTab, setActiveTab] = useState<TabKey>('foreshadow')
  const [foreshadows, setForeshadows] = useState<Foreshadow[]>([])
  const [chapterIndexes, setChapterIndexes] = useState<ChapterIndex[]>([])
  const [qualityDebts, setQualityDebts] = useState<QualityDebt[]>([])
  const [aiFixingDebtId, setAiFixingDebtId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState<string>('all')

  const chapterById = useCallback(
    (chapterId: string) => chapters.find(c => c.id === chapterId),
    [chapters],
  )
  const chapterTitleByDisplayNumber = useCallback(
    (num: number) => chapters.find(c => displayChapterNumber(c.title, c.sort_order) === num)?.title,
    [chapters],
  )

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const [fsRes, ciRes, qdRes] = await Promise.all([
        foreshadowsApi.list(projectId),
        chapterIndexesApi.list(projectId),
        qualityDebtsApi.list(projectId),
      ])
      setForeshadows(fsRes.data)
      setChapterIndexes(ciRes.data)
      setQualityDebts(qdRes.data)
    } catch {
      toast.error('数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleCreate = async (data: Partial<Foreshadow>) => {
    if (!projectId) return
    try {
      const res = await foreshadowsApi.create(projectId, data)
      setForeshadows(prev => [res.data, ...prev])
      setShowForm(false)
      toast.success('伏笔已添加')
    } catch { toast.error('创建失败') }
  }

  const handleUpdate = async (id: string, data: Partial<Foreshadow>) => {
    if (!projectId) return
    try {
      const res = await foreshadowsApi.update(projectId, id, data)
      setForeshadows(prev => prev.map(f => f.id === id ? res.data : f))
      setEditingId(null)
      toast.success('已更新')
    } catch { toast.error('更新失败') }
  }

  const handleDelete = async (id: string) => {
    if (!projectId || !window.confirm('确认删除这条伏笔？')) return
    try {
      await foreshadowsApi.delete(projectId, id)
      setForeshadows(prev => prev.filter(f => f.id !== id))
      toast.success('已删除')
    } catch { toast.error('删除失败') }
  }

  const filteredForeshadows = filterStatus === 'all'
    ? foreshadows
    : foreshadows.filter(f => f.status === filterStatus)

  const openCount = foreshadows.filter(f => f.status === 'open').length
  const resolvedCount = foreshadows.filter(f => f.status === 'resolved').length
  const pendingDebtCount = qualityDebts.filter(d => d.status === 'pending').length

  const handleQualityDebtStatus = async (id: string, status: QualityDebt['status']) => {
    if (!projectId) return
    try {
      const res = await qualityDebtsApi.update(projectId, id, { status })
      setQualityDebts(prev => prev.map(d => d.id === id ? res.data : d))
      toast.success('质量债务已更新')
    } catch {
      toast.error('更新失败')
    }
  }

  const handleSaveDebtAuthorNotes = async (id: string, notes: string) => {
    if (!projectId) return
    try {
      const trimmed = notes.trim()
      const res = await qualityDebtsApi.update(projectId, id, {
        author_notes: trimmed.length ? trimmed : '',
      })
      setQualityDebts(prev => prev.map(d => d.id === id ? res.data : d))
      toast.success('备注已保存')
    } catch {
      toast.error('保存失败')
    }
  }

  const openWriteForDebt = useCallback(
    (debt: QualityDebt) => {
      if (!projectId) return
      const cid =
        debt.chapter_id
        || chapters.find(c => displayChapterNumber(c.title, c.sort_order) === debt.source_chapter_number)?.id
      if (!cid) {
        toast.error('找不到对应章节（可能已删章），请从目录进入写作页')
        return
      }
      navigate(`/project/${projectId}/write?chapter=${cid}`)
    },
    [projectId, chapters, navigate],
  )

  const handleAiFixDebt = async (debt: QualityDebt, mode: 'micro' | 'rewrite' | 'continue') => {
    if (!projectId) return
    const modelProfile = modelProfileFromRoute(aiBackendRoute)
    const llmProviderId = llmProviderIdFromRoute(aiBackendRoute)
    setAiFixingDebtId(debt.id)
    try {
      if (mode === 'micro') {
        const res = await aiApi.qualityDebtMicroFix(projectId, {
          quality_debt_id: debt.id,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
        })
        upsertChapter(res.data.chapter)
        setQualityDebts(prev => prev.map(d => (d.id === debt.id ? { ...d, status: 'resolved' as const } : d)))
        const why = (res.data.rationale || '').trim()
        toast.success(
          why.length > 0
            ? `局部微调已应用：${why.length > 100 ? `${why.slice(0, 100)}…` : why}`
            : '局部微调已应用，该债务已标为已修复',
        )
        return
      }

      const replaceExisting = mode === 'rewrite'
      const chapterId =
        debt.chapter_id
        || chapters.find(c => displayChapterNumber(c.title, c.sort_order) === debt.source_chapter_number)?.id
      if (!chapterId) {
        toast.error('无法定位章节，请确认该章仍在目录中')
        return
      }
      const chapterRes = await chaptersApi.get(projectId, chapterId)
      const chapter = chapterRes.data
      if ((chapter.content || '').trim()) {
        try {
          await chaptersApi.snapshot(projectId, chapterId, 'AI质量债务修复前自动备份', true)
        } catch {
          /* 快照失败不阻断 */
        }
      }
      const accumulated = await postDraftAssistAccumulatedWithPrewriteRetry(
        authFetch,
        `/api/v1/projects/${projectId}/ai/draft-assist/stream`,
        {
          chapter_id: chapterId,
          model_profile: modelProfile,
          ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
          user_prompt: null,
          replace_existing: replaceExisting,
          focus_quality_debt_id: debt.id,
        },
      )
      if (!accumulated.trim()) throw new Error('未收到正文内容')
      const { body: draftBody, indexMarkdown } = splitStreamedDraftText(accumulated.trim())
      if (!draftBody.trim()) throw new Error('未收到叙事正文（可能只有索引块）')
      const html = plainTextDraftToHtml(draftBody.trim())
      let nextContent: string
      let manuscript_raw_snapshot: string | undefined
      if (replaceExisting) {
        nextContent = html
        manuscript_raw_snapshot = accumulated.trim()
      } else {
        nextContent = `${chapter.content || ''}${chapter.content ? '\n' : ''}${html}`
        manuscript_raw_snapshot = manuscriptRawSnapshotForContinue(chapter.content || '', accumulated.trim())
      }
      const updateRes = await chaptersApi.update(projectId, chapterId, {
        content: nextContent,
        manuscript_raw_snapshot,
      })
      upsertChapter(updateRes.data)
      if (indexMarkdown) {
        try {
          const parsed = parseChapterIndexMarkdown(indexMarkdown)
          const chapter_index = parsed ?? fallbackChapterIndexFromRawMarkdown(indexMarkdown)
          await aiApi.chapterDebrief(projectId, { chapter_id: chapterId, chapter_index })
        } catch {
          toast.error('稿末索引写入失败，可在写作页手动复盘')
        }
      }
      try {
        const u = await qualityDebtsApi.update(projectId, debt.id, { status: 'resolved' })
        setQualityDebts(prev => prev.map(d => (d.id === debt.id ? u.data : d)))
      } catch {
        /* 正文已保存；债务状态可手动标记 */
      }
      toast.success('AI 修复稿已保存，该债务已标为已修复')
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: unknown } } }
      const d = ax.response?.data?.detail
      let msg = 'AI 修复失败'
      if (typeof d === 'string') msg = d
      else if (d && typeof d === 'object' && d !== null && 'message' in d) {
        const o = d as { message?: string; rationale?: string }
        msg = [o.message, o.rationale].filter(Boolean).join(' — ') || msg
      } else if (e instanceof Error) msg = e.message
      toast.error(msg)
    } finally {
      setAiFixingDebtId(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab 栏 */}
      <div className="border-b border-gray-100 bg-white px-4 flex items-center gap-0">
        {([
          { key: 'foreshadow' as TabKey, label: '伏笔管理', icon: Anchor },
          { key: 'plotarchive' as TabKey, label: '情节档案', icon: ClipboardList },
          { key: 'qualitydebt' as TabKey, label: '质量债务', icon: AlertTriangle },
        ]).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-3 text-sm border-b-2 transition-colors',
              activeTab === key
                ? 'border-amber-500 text-amber-700 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
          >
            <Icon size={14} />
            {label}
            {key === 'foreshadow' && openCount > 0 && (
              <span className="ml-1 text-[10px] bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded-full font-medium">
                {openCount}
              </span>
            )}
            {key === 'qualitydebt' && pendingDebtCount > 0 && (
              <span className="ml-1 text-[10px] bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full font-medium">
                {pendingDebtCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center gap-2 text-gray-400 text-sm">
          <Loader2 className="animate-spin" size={18} />载入中…
        </div>
      ) : activeTab === 'foreshadow' ? (
        /* ── 伏笔管理 Tab ── */
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {/* 工具栏 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {/* 统计胶囊 */}
              <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-1 rounded-lg">
                未回收 {openCount}
              </span>
              <span className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-1 rounded-lg">
                已回收 {resolvedCount}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {/* 筛选 */}
              <select
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400"
                value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
              >
                <option value="all">全部</option>
                <option value="open">未回收</option>
                <option value="resolved">已回收</option>
                <option value="dropped">已放弃</option>
              </select>
              <button
                onClick={() => { setShowForm(v => !v); setEditingId(null) }}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors"
              >
                <Plus size={13} />新增伏笔
              </button>
            </div>
          </div>

          {/* 新增表单 */}
          {showForm && (
            <ForeshadowForm
              onSave={handleCreate}
              onCancel={() => setShowForm(false)}
            />
          )}

          {/* 列表 */}
          {filteredForeshadows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <BookMarked size={32} className="text-gray-200" />
              <p className="text-sm text-gray-500">
                {filterStatus === 'all' ? '还没有伏笔记录' : `没有「${STATUS_LABEL[filterStatus]}」的伏笔`}
              </p>
              <p className="text-xs text-gray-400">
                点击「新增伏笔」手动添加，或在 AI 生成章节后自动从情节档案提取
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredForeshadows.map(item =>
                editingId === item.id ? (
                  <ForeshadowForm
                    key={item.id}
                    initial={item}
                    onSave={data => handleUpdate(item.id, data)}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <ForeshadowCard
                    key={item.id}
                    item={item}
                    onEdit={() => { setEditingId(item.id); setShowForm(false) }}
                    onDelete={() => handleDelete(item.id)}
                    onStatusChange={s => handleUpdate(item.id, { status: s })}
                  />
                ),
              )}
            </div>
          )}
        </div>
      ) : activeTab === 'plotarchive' ? (
        /* ── 情节档案 Tab ── */
        <div className="flex-1 overflow-auto p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              共 {chapterIndexes.length} 条档案 · 由「章节复盘」自动生成
            </p>
          </div>
          {chapterIndexes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <ClipboardList size={32} className="text-gray-200" />
              <p className="text-sm text-gray-500">暂无情节档案</p>
              <p className="text-xs text-gray-400">写完章节后点击「一键复盘」，AI 会自动生成每章的情节档案</p>
            </div>
          ) : (
            <div className="space-y-2">
              {[...chapterIndexes]
                .sort((a, b) => a.chapter_number - b.chapter_number)
                .map(idx => (
                  <ChapterIndexCard
                    key={idx.id}
                    index={idx}
                    chapterTitle={chapterById(String(idx.chapter_id))?.title}
                  />
                ))}
            </div>
          )}
        </div>
      ) : (
        /* ── 质量债务 Tab ── */
        <div className="flex-1 overflow-auto p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              共 {qualityDebts.length} 条债务 · {pendingDebtCount} 条未解决 · 由章节质检自动生成
            </p>
          </div>
          {qualityDebts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <AlertTriangle size={32} className="text-gray-200" />
              <p className="text-sm text-gray-500">暂无质量债务</p>
              <p className="text-xs text-gray-400">章节质检发现的硬性连续性问题会沉淀到这里</p>
            </div>
          ) : (
            <div className="space-y-2">
              {[...qualityDebts]
                .sort((a, b) => a.source_chapter_number - b.source_chapter_number)
                .map(debt => (
                  <QualityDebtCard
                    key={debt.id}
                    debt={debt}
                    chapterTitle={chapterTitleByDisplayNumber(debt.source_chapter_number)}
                    isAiFixing={aiFixingDebtId === debt.id}
                    onStatusChange={status => handleQualityDebtStatus(debt.id, status)}
                    onSaveAuthorNotes={handleSaveDebtAuthorNotes}
                    onAiFix={handleAiFixDebt}
                    onOpenWrite={openWriteForDebt}
                  />
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
