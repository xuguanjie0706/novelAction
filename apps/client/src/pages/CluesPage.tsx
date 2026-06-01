/**
 * CluesPage — 伏笔 / 情节档案 / 质量债务 三 Tab 页面（薄壳）
 *
 * 子组件已拆分至 pages/Clues/：
 *   constants / ForeshadowForm / ForeshadowCard / ChapterIndexCard / QualityDebtCard
 */
import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Plus, Loader2, BookMarked, ClipboardList, AlertTriangle, Anchor,
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

import { displayChapterNumber, STATUS_LABEL } from './Clues/constants'
import ForeshadowForm from './Clues/ForeshadowForm'
import ForeshadowCard from './Clues/ForeshadowCard'
import ChapterIndexCard from './Clues/ChapterIndexCard'
import QualityDebtCard from './Clues/QualityDebtCard'

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function manuscriptRawSnapshotForContinue(chapterContentHtml: string, accumulatedPlain: string): string {
  const prev = htmlToPlainForSplit(chapterContentHtml || '').trim()
  const acc = accumulatedPlain.trim()
  if (!prev) return acc
  if (!acc) return prev
  return `${prev}\n\n${acc}`
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
        const prevPlain = htmlToPlainForSplit(chapter.content || '').trim()
        manuscript_raw_snapshot = prevPlain
          ? (splitStreamedDraftText(prevPlain).body.trim() || prevPlain)
          : undefined
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
              <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-1 rounded-lg">
                未回收 {openCount}
              </span>
              <span className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-1 rounded-lg">
                已回收 {resolvedCount}
              </span>
            </div>
            <div className="flex items-center gap-2">
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

          {showForm && (
            <ForeshadowForm onSave={handleCreate} onCancel={() => setShowForm(false)} />
          )}

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
