import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Plus, Loader2, RefreshCw, ChevronRight, ChevronDown, PenLine, FileText, BookOpen,
} from 'lucide-react'
import { chaptersApi, outlineApi, storylinesApi } from '../api/client'
import { useAppStore } from '../store'
import ChapterEditor from '../components/Writing/ChapterEditor'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { Chapter, OutlineNode } from '../types'

function findNode(tree: OutlineNode[], id: string): OutlineNode | undefined {
  for (const n of tree) {
    if (n.id === id) return n
    if (n.children?.length) { const f = findNode(n.children, id); if (f) return f }
  }
}

function collectChapterPlans(nodes: OutlineNode[], out: OutlineNode[] = []) {
  for (const n of nodes) {
    if (n.node_type === 'chapter_plan') out.push(n)
    if (n.children?.length) collectChapterPlans(n.children, out)
  }
  return out
}

/** 大纲里 AI 常见的占位标题：无正文时不应在写作侧栏占位，也不参与「从大纲同步」 */
const PLACEHOLDER_CHAPTER_TITLE = /暂缺|预留|代填|占位|TBD|待拟|（预|\(预|待补充|未完/

function isPlaceholderChapterPlan(node: OutlineNode, ch: Chapter | undefined): boolean {
  if (node.node_type !== 'chapter_plan') return false
  if (ch && ch.word_count > 0) return false
  return PLACEHOLDER_CHAPTER_TITLE.test(node.title)
}

/** 根节点中卷在前、其余（含误入根的章计划）在后，避免「第 N 章」插在两卷之间 */
function sortRootNodesForWriteSidebar(nodes: OutlineNode[]): OutlineNode[] {
  if (nodes.length <= 1) return [...nodes].sort((a, b) => a.sort_order - b.sort_order)
  const vols = nodes.filter(n => n.node_type === 'volume')
  const rest = nodes.filter(n => n.node_type !== 'volume')
  if (!vols.length || !rest.length) return [...nodes].sort((a, b) => a.sort_order - b.sort_order)
  return [
    ...vols.sort((a, b) => a.sort_order - b.sort_order),
    ...rest.sort((a, b) => a.sort_order - b.sort_order),
  ]
}

export default function WritePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const {
    chapters, setChapters, upsertChapter,
    activeChapterId, setActiveChapterId,
    outlineTree, setOutlineTree,
    setStoryLines,
  } = useAppStore()

  const [creating, setCreating] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [sidebarHidden, setSidebarHidden] = useState(false)  // 专注模式时收起左侧

  const loadData = useCallback(() => {
    if (!projectId) return
    setLoadState('loading')
    Promise.all([outlineApi.getTree(projectId), chaptersApi.list(projectId), storylinesApi.list(projectId)])
      .then(([oRes, cRes, slRes]) => {
        setOutlineTree(oRes.data)
        setExpanded(new Set<string>(oRes.data.map((n: OutlineNode) => n.id)))
        setChapters(cRes.data)
        setStoryLines(slRes.data)
        if (!activeChapterId && cRes.data.length > 0) setActiveChapterId(cRes.data[0].id)
        setLoadState('ready')
      })
      .catch(() => { setLoadState('error'); toast.error('数据加载失败') })
  }, [projectId])

  useEffect(() => { loadData() }, [loadData])

  const chapterByNodeId = useMemo(() => {
    const m = new Map<string, Chapter>()
    for (const ch of chapters) if (ch.outline_node_id) m.set(ch.outline_node_id, ch)
    return m
  }, [chapters])

  const freeChapters = useMemo(() => chapters.filter(ch => !ch.outline_node_id), [chapters])
  const allPlans = useMemo(() => collectChapterPlans(outlineTree), [outlineTree])
  const syncablePlans = useMemo(
    () => allPlans.filter(n => !isPlaceholderChapterPlan(n, chapterByNodeId.get(n.id))),
    [allPlans, chapterByNodeId],
  )
  const unsyncedCount = syncablePlans.filter(n => !chapterByNodeId.has(n.id)).length
  const outlineRootsOrdered = useMemo(
    () => sortRootNodesForWriteSidebar(outlineTree),
    [outlineTree],
  )

  // 占位章在侧栏已隐藏：若当前仍选中该章，改选第一本非占位章（或独立章）
  useEffect(() => {
    if (!activeChapterId || outlineTree.length === 0) return
    const ch = chapters.find(c => c.id === activeChapterId)
    if (!ch?.outline_node_id) return
    const node = findNode(outlineTree, ch.outline_node_id)
    if (!node || node.node_type !== 'chapter_plan') return
    if (!isPlaceholderChapterPlan(node, ch)) return
    const next = chapters.find(c => {
      if (!c.outline_node_id) return true
      const n = findNode(outlineTree, c.outline_node_id)
      if (n?.node_type === 'chapter_plan') return !isPlaceholderChapterPlan(n, c)
      return true
    })
    if (next && next.id !== activeChapterId) setActiveChapterId(next.id)
    else if (!next) setActiveChapterId(null)
  }, [activeChapterId, chapters, outlineTree, setActiveChapterId])

  const toggleExpand = (id: string) =>
    setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  const openOrCreate = useCallback(async (node: OutlineNode) => {
    if (!projectId || node.node_type !== 'chapter_plan') return
    const existing = chapterByNodeId.get(node.id)
    if (existing) { setActiveChapterId(existing.id); return }
    try {
      const res = await chaptersApi.create(projectId, {
        title: node.title, outline_node_id: node.id, sort_order: chapters.length,
      })
      upsertChapter(res.data)
      setActiveChapterId(res.data.id)
    } catch { toast.error('创建章节失败') }
  }, [projectId, chapterByNodeId, chapters.length])

  const syncFromOutline = async () => {
    if (!projectId) return
    setSyncing(true)
    try {
      let created = 0
      for (const node of syncablePlans) {
        if (!chapterByNodeId.has(node.id)) {
          const res = await chaptersApi.create(projectId, {
            title: node.title, outline_node_id: node.id, sort_order: chapters.length + created,
          })
          upsertChapter(res.data)
          created++
        }
      }
      toast.success(created > 0 ? `已从大纲同步 ${created} 个章节` : '全部章节已同步')
    } catch { toast.error('同步失败') } finally { setSyncing(false) }
  }

  const createFreeChapter = async () => {
    if (!projectId) return
    setCreating(true)
    try {
      const res = await chaptersApi.create(projectId, {
        title: `第${chapters.length + 1}章`, sort_order: chapters.length,
      })
      upsertChapter(res.data)
      setActiveChapterId(res.data.id)
    } catch { toast.error('创建章节失败') } finally { setCreating(false) }
  }

  const activeChapter = chapters.find(c => c.id === activeChapterId)
  const activeOutlineNode = activeChapter?.outline_node_id
    ? findNode(outlineTree, activeChapter.outline_node_id) : undefined
  const hasOutline = outlineTree.length > 0

  /** 上一章：按 sort_order 排序后取前一个 */
  const prevChapter = useMemo(() => {
    if (!activeChapter) return undefined
    const sorted = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
    const idx = sorted.findIndex(c => c.id === activeChapter.id)
    return idx > 0 ? sorted[idx - 1] : undefined
  }, [activeChapter, chapters])

  const statusDot = (s: Chapter['status']) =>
    ({ draft: 'bg-gray-300', writing: 'bg-blue-400', done: 'bg-green-400', reviewed: 'bg-amber-400' }[s])

  const renderNode = (node: OutlineNode, depth = 0): React.ReactNode => {
    if (node.node_type === 'chapter_plan') {
      const ch = chapterByNodeId.get(node.id)
      if (isPlaceholderChapterPlan(node, ch)) return null
      const isActive = ch?.id === activeChapterId
      return (
        <button key={node.id} type="button" onClick={() => openOrCreate(node)}
          style={{ paddingLeft: `${10 + depth * 14}px`, paddingRight: '8px' }}
          className={clsx(
            'w-full text-left flex items-center gap-2 py-1.5 rounded-lg transition-colors mb-0.5 border',
            isActive
              ? 'bg-amber-50 border-amber-200 border-l-2 border-l-amber-500'
              : 'border-transparent hover:bg-gray-50'
          )}>
          {ch
            ? <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', statusDot(ch.status))} />
            : <span className="w-1.5 h-1.5 rounded-full shrink-0 border border-gray-200" />}
          <PenLine size={10} className={clsx('shrink-0', isActive ? 'text-amber-500' : 'text-gray-300')} />
          <span className={clsx('text-xs truncate flex-1 min-w-0',
            isActive ? 'text-amber-800 font-medium' : ch ? 'text-gray-800' : 'text-gray-400')}>
            {node.title}
          </span>
          {ch
            ? <span className="text-[10px] text-gray-400 shrink-0">{ch.word_count.toLocaleString()}字</span>
            : <span className="text-[10px] text-gray-300 shrink-0">待写</span>}
        </button>
      )
    }

    const isOpen = expanded.has(node.id)
    const isVol = node.node_type === 'volume'
    return (
      <div key={node.id} className="mb-0.5">
        <button type="button" onClick={() => toggleExpand(node.id)}
          style={{ paddingLeft: `${6 + depth * 14}px`, paddingRight: '8px' }}
          className="w-full flex items-center gap-1.5 py-1.5 rounded-lg hover:bg-gray-50 transition-colors text-left">
          {isOpen
            ? <ChevronDown size={11} className="text-gray-400 shrink-0" />
            : <ChevronRight size={11} className="text-gray-400 shrink-0" />}
          <span className={clsx('text-[10px] px-1 py-0.5 rounded font-medium shrink-0',
            isVol ? 'bg-amber-100 text-amber-700' : 'bg-blue-50 text-blue-700')}>
            {isVol ? '卷' : '篇'}
          </span>
          <span className="text-xs text-gray-700 font-medium truncate">{node.title}</span>
        </button>
        {isOpen && node.children?.map(child => renderNode(child, depth + 1))}
      </div>
    )
  }

  if (loadState === 'loading') {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-gray-400 text-sm">
        <Loader2 className="animate-spin" size={18} />载入中…
      </div>
    )
  }

  if (loadState === 'error') {
    return (
      <div className="flex h-full items-center justify-center flex-col gap-3 p-8 text-center">
        <p className="text-sm font-medium text-gray-700">数据未能加载</p>
        <p className="text-xs text-gray-400">请确认后端已启动且网络正常</p>
        <button onClick={loadData}
          className="text-sm px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors">
          重新加载
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* 左侧：大纲驱动章节导航（专注模式下隐藏）*/}
      <div className={clsx(
        'flex flex-col border-r border-gray-100 bg-white shrink-0 transition-all duration-200 overflow-hidden',
        sidebarHidden ? 'w-0 border-r-0' : 'w-56',
      )}>
        <div className="px-3 py-2.5 border-b border-gray-100 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">写作</span>
            <button type="button" onClick={createFreeChapter} disabled={creating}
              title="新建独立章节（不挂大纲）"
              className="p-1.5 rounded text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors">
              <Plus size={14} />
            </button>
          </div>
          {hasOutline && unsyncedCount > 0 && (
            <button type="button" onClick={syncFromOutline} disabled={syncing}
              className="w-full flex items-center justify-center gap-1.5 text-[11px] py-1.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors">
              <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
              从大纲同步 {unsyncedCount} 章
            </button>
          )}
        </div>

        <div className="flex-1 overflow-auto py-1.5 px-1.5">
          {hasOutline ? (
            <>
              {outlineRootsOrdered.map(n => renderNode(n))}
              {freeChapters.length > 0 && (
                <div className="mt-3 pt-2 border-t border-gray-100">
                  <div className="text-[10px] text-gray-400 px-2 mb-1">独立章节</div>
                  {freeChapters.map(ch => (
                    <button key={ch.id} type="button" onClick={() => setActiveChapterId(ch.id)}
                      className={clsx('w-full text-left flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors mb-0.5 border',
                        ch.id === activeChapterId
                          ? 'bg-amber-50 border-amber-200 border-l-2 border-l-amber-500'
                          : 'border-transparent hover:bg-gray-50')}>
                      <FileText size={11} className="text-gray-300 shrink-0" />
                      <span className="text-xs text-gray-700 truncate flex-1">{ch.title}</span>
                      <span className="text-[10px] text-gray-400 shrink-0">{ch.word_count.toLocaleString()}字</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center text-center py-8 px-3 gap-3">
              <BookOpen size={28} className="text-gray-200" />
              <div>
                <p className="text-xs font-medium text-gray-600">先规划，再写作</p>
                <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                  到「大纲」页生成章节计划，AI 写作时会带入世界观、人物弧和伏笔
                </p>
              </div>
              <button onClick={() => navigate(`/project/${projectId}/outline`)}
                className="text-xs px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors">
                去大纲页
              </button>
              <button onClick={createFreeChapter}
                className="text-xs text-gray-400 hover:text-gray-600 underline underline-offset-2">
                直接新建章节
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 右侧：编辑区 */}
      <div className="flex-1 min-w-0">
        {activeChapter ? (
          <ChapterEditor
            projectId={projectId!}
            chapter={activeChapter}
            outlineNode={activeOutlineNode}
            prevChapter={prevChapter}
            onFocusModeChange={setSidebarHidden}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 p-8">
            <PenLine size={32} className="text-gray-200" />
            <p className="text-sm text-gray-500">
              {hasOutline && unsyncedCount > 0 ? '点击左侧章节开始写作' : '选择或新建一个章节开始写作'}
            </p>
            {hasOutline && unsyncedCount > 0 && (
              <button onClick={syncFromOutline} disabled={syncing}
                className="text-xs px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors flex items-center gap-1.5">
                <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
                从大纲同步所有章节
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
