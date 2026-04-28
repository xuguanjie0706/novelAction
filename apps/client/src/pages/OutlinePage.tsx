import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronRight, ChevronDown, Plus, Trash2, Pencil, Check, X,
  Sparkles, BookOpen, Users, TrendingUp, GitBranch,
} from 'lucide-react'
import { chaptersApi, outlineApi } from '../api/client'
import { useAppStore, toOutlineApiModelProfile, routeLlmProviderPayload } from '../store'
import type { OutlineNode } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import OutlineAIPanel from '../components/Outline/OutlineAIPanel'
import { collectExpandableNodes } from '../utils/outlineAiExpand'

// ── 全量生成配置弹窗（只收集参数，执行交给队列）──────────────

function FullGenConfigModal({
  projectId,
  hasExistingOutline,
  onClose,
  onDispatch,
}: {
  projectId: string
  hasExistingOutline: boolean
  onClose: () => void
  onDispatch: (params: {
    scale_hint: string
    model_profile: string
    clear_existing: boolean
    llm_provider_id?: string
  }) => void
}) {
  const [scaleHint, setScaleHint] = useState<'auto' | 'short' | 'medium' | 'long'>('auto')
  // 已有大纲时默认勾选「清除重建」，避免重复叠加旧内容
  const [clearExisting, setClearExisting] = useState(hasExistingOutline)

  const handleStart = () => {
    if (clearExisting && !window.confirm('将清除现有全部大纲节点，确定继续？')) return
    const route = useAppStore.getState().aiBackendRoute
    onDispatch({
      scale_hint: scaleHint,
      model_profile: toOutlineApiModelProfile(route),
      clear_existing: clearExisting,
      ...routeLlmProviderPayload(route),
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <BookOpen size={18} className="text-amber-500" />
          <h3 className="font-semibold text-gray-800 flex-1">全量生成大纲</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-gray-500 leading-relaxed">
            AI 读取项目的 logline、类型、世界观、人物，自主决定几卷几章并写入大纲树。
            <span className="block mt-1 text-amber-600 font-medium">
              任务将在右下角队列中后台运行，不影响当前操作。
            </span>
          </p>

          {/* 篇幅倾向 */}
          <div>
            <label className="text-xs text-gray-500 block mb-2">篇幅倾向</label>
            <div className="grid grid-cols-2 gap-2">
              {([
                { value: 'auto',   label: '让 AI 决定', sub: '根据故事自动判断' },
                { value: 'short',  label: '短篇',       sub: '约 30–50 章' },
                { value: 'medium', label: '中篇',       sub: '约 60–120 章' },
                { value: 'long',   label: '长篇',       sub: '约 150 章以上' },
              ] as const).map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setScaleHint(opt.value)}
                  className={clsx(
                    'text-left px-3 py-2.5 rounded-xl border transition-all',
                    scaleHint === opt.value
                      ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-300'
                      : 'border-gray-200 hover:border-gray-300 bg-white'
                  )}
                >
                  <div className={clsx('text-xs font-medium', scaleHint === opt.value ? 'text-indigo-700' : 'text-gray-700')}>
                    {opt.label}
                  </div>
                  <div className="text-[11px] text-gray-400 mt-0.5">{opt.sub}</div>
                </button>
              ))}
            </div>
          </div>

          <p className="text-[11px] text-gray-400 leading-relaxed">
            使用顶部栏当前选择的模型加入队列。
          </p>

          {/* 模式说明 */}
          <div className="rounded-xl border border-gray-100 bg-gray-50 divide-y divide-gray-100 text-xs overflow-hidden">
            <button
              type="button"
              onClick={() => setClearExisting(false)}
              className={`w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-colors ${!clearExisting ? 'bg-green-50 border-l-2 border-green-400' : 'hover:bg-gray-100'}`}
            >
              <span className="mt-0.5 text-base leading-none">✏️</span>
              <div>
                <div className={`font-medium ${!clearExisting ? 'text-green-800' : 'text-gray-700'}`}>
                  续写空卷（推荐）
                </div>
                <div className="text-gray-400 mt-0.5">
                  识别现有大纲中尚无章节计划的卷/篇，直接填充内容。已写章节和已有大纲节点全部保留。
                </div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setClearExisting(true)}
              className={`w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-colors ${clearExisting ? 'bg-red-50 border-l-2 border-red-400' : 'hover:bg-gray-100'}`}
            >
              <span className="mt-0.5 text-base leading-none">🗑️</span>
              <div>
                <div className={`font-medium ${clearExisting ? 'text-red-700' : 'text-gray-700'}`}>
                  清除后重建
                  {clearExisting && <span className="ml-1 font-normal text-red-400">（大纲将被全部删除）</span>}
                </div>
                <div className="text-gray-400 mt-0.5">
                  删除现有全部大纲节点，AI 从零规划新卷结构。章节正文不受影响，但大纲链接会断开。
                </div>
              </div>
            </button>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg bg-white"
          >
            取消
          </button>
          <button
            onClick={handleStart}
            className="flex items-center gap-2 px-4 py-1.5 text-sm font-medium bg-amber-500 hover:bg-amber-600 text-white rounded-lg shadow-sm"
          >
            <Sparkles size={14} />
            加入队列并开始
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 批量展开配置弹窗 ─────────────────────────────────────────

function BatchExpandConfigModal({
  targetCount,
  onClose,
  onDispatch,
}: {
  targetCount: number
  onClose: () => void
  onDispatch: (chapterCount: number) => void
}) {
  const [chapterCount, setChapterCount] = useState(15)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Sparkles size={16} className="text-amber-500" />
          <h3 className="font-semibold text-gray-800 flex-1">批量展开章节计划</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-gray-500 leading-relaxed">
            将对 <span className="font-semibold text-gray-700">{targetCount} 个</span>尚未有章节计划的卷/篇依次展开。
            <span className="block mt-1 text-amber-600 font-medium">任务将在右下角队列中后台运行。</span>
          </p>

          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-500 whitespace-nowrap">每处生成</label>
            <input
              type="number"
              min={1}
              max={200}
              value={chapterCount}
              onChange={e => {
                const v = parseInt(e.target.value, 10)
                if (!isNaN(v) && v >= 1) setChapterCount(v)
              }}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 w-24 focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
            <span className="text-xs text-gray-400">章</span>
          </div>

          <p className="text-[11px] text-gray-400 leading-relaxed">
            使用顶部栏当前选择的模型加入队列。
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg bg-white">
            取消
          </button>
          <button
            onClick={() => { onDispatch(chapterCount); onClose() }}
            className="flex items-center gap-2 px-4 py-1.5 text-sm font-medium bg-amber-500 hover:bg-amber-600 text-white rounded-lg shadow-sm"
          >
            <Sparkles size={14} />
            加入队列
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────

export default function OutlinePage() {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const {
    outlineTree, setOutlineTree, setActiveChapterId,
    addGenTask, outlineNeedsReload, setOutlineNeedsReload,
  } = useAppStore()
  const [selected, setSelected] = useState<OutlineNode | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [showFullGenModal, setShowFullGenModal] = useState(false)
  const [showBatchModal, setShowBatchModal] = useState(false)

  const reload = () => {
    if (!projectId) return
    outlineApi.getTree(projectId).then(res => {
      setOutlineTree(res.data)
      const topIds = new Set<string>(res.data.map((n: OutlineNode) => n.id))
      setExpanded(prev => new Set([...prev, ...topIds]))
    })
  }

  useEffect(() => { reload() }, [projectId])

  // 队列任务完成后自动刷新大纲树
  useEffect(() => {
    if (outlineNeedsReload) {
      reload()
      setOutlineNeedsReload(false)
    }
  }, [outlineNeedsReload])

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  const typeLabel = (t: OutlineNode['node_type']) =>
    ({ volume: '卷', arc: '篇', chapter_plan: '章' }[t])

  const typeColor = (t: OutlineNode['node_type']) =>
    ({ volume: 'bg-amber-100 text-amber-700', arc: 'bg-blue-100 text-blue-700', chapter_plan: 'bg-gray-100 text-gray-600' }[t])

  const openChapterFromNode = async (node: OutlineNode) => {
    if (!projectId || node.node_type !== 'chapter_plan') return
    try {
      const listRes = await chaptersApi.list(projectId)
      const chapters = listRes.data
      let chapter = chapters.find((c: any) => c.outline_node_id === node.id)
      if (!chapter) {
        const createRes = await chaptersApi.create(projectId, {
          title: node.title,
          outline_node_id: node.id,
          sort_order: chapters.length,
        })
        chapter = createRes.data
      }
      setActiveChapterId(chapter.id)
      navigate(`/project/${projectId}/write`)
    } catch {
      toast.error('切换章节失败')
    }
  }

  const handleDelete = async (node: OutlineNode, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!projectId) return
    if (!window.confirm(`确认删除「${node.title}」及其所有子节点？`)) return
    try {
      await outlineApi.delete(projectId, node.id)
      toast.success('已删除')
      if (selected?.id === node.id) setSelected(null)
      reload()
    } catch {
      toast.error('删除失败')
    }
  }

  const handleAddChild = async (parent: OutlineNode, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!projectId) return
    const childType = parent.node_type === 'volume' ? 'arc' : 'chapter_plan'
    const titleMap: Record<string, string> = { arc: '新篇', chapter_plan: '新章节' }
    try {
      const res = await outlineApi.create(projectId, {
        parent_id: parent.id,
        node_type: childType,
        title: titleMap[childType],
        sort_order: parent.children?.length ?? 0,
      })
      setExpanded(prev => new Set([...prev, parent.id]))
      reload()
      setSelected(res.data)
      toast.success('已创建')
    } catch {
      toast.error('创建失败')
    }
  }

  // ── 全量生成 → 派发到队列 ─────────────────────────────────
  const handleDispatchFullGen = (params: {
    scale_hint: string
    model_profile: string
    clear_existing: boolean
    llm_provider_id?: string
  }) => {
    if (!projectId) return
    addGenTask({
      type: 'full_generate',
      projectId,
      label: `全量生成大纲`,
      params,
    })
    toast.success('已加入生成队列，右下角可查看进度')
  }

  // ── 批量展开 → 派发到队列 ────────────────────────────────
  const handleDispatchBatchExpand = (chapterCount: number) => {
    if (!projectId) return
    const targets = collectExpandableNodes(outlineTree)
    if (targets.length === 0) {
      toast.error('没有可展开的卷/篇（可能已全部有章节计划，或大纲为空）')
      return
    }
    const route = useAppStore.getState().aiBackendRoute
    const modelProfile = toOutlineApiModelProfile(route)
    addGenTask({
      type: 'batch_expand',
      projectId,
      label: `批量展开 ${targets.length} 处大纲`,
      params: {
        nodes: targets.map(n => ({ id: n.id, title: n.title })),
        chapterCount,
        modelProfile,
        ...routeLlmProviderPayload(route),
      },
    })
    toast.success('已加入生成队列，右下角可查看进度')
  }

  const expandableCount = collectExpandableNodes(outlineTree).length

  const renderNode = (node: OutlineNode, depth = 0) => {
    const isOpen = expanded.has(node.id)
    const hasChildren = node.children?.length > 0
    const canHaveChildren = node.node_type !== 'chapter_plan'

    return (
      <div key={node.id}>
        <div
          className={clsx(
            'flex items-center gap-1 py-1.5 px-2 cursor-pointer rounded-lg mx-1 group',
            selected?.id === node.id ? 'bg-amber-50' : 'hover:bg-gray-50'
          )}
          style={{ paddingLeft: `${8 + depth * 18}px` }}
          onClick={() => setSelected(node)}
          onDoubleClick={() => openChapterFromNode(node)}
        >
          <button
            className="shrink-0 text-gray-400 w-4 flex justify-center"
            onClick={e => { e.stopPropagation(); toggleExpand(node.id) }}
          >
            {hasChildren
              ? (isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />)
              : <span className="w-3 inline-block" />}
          </button>
          <span className={clsx('text-[10px] px-1 py-0.5 rounded font-medium shrink-0', typeColor(node.node_type))}>
            {typeLabel(node.node_type)}
          </span>
          <span className="text-xs text-gray-800 truncate flex-1 min-w-0">{node.title}</span>
          <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
            {canHaveChildren && (
              <button
                title="添加子节点"
                onClick={e => handleAddChild(node, e)}
                className="p-0.5 rounded text-gray-400 hover:text-blue-500 hover:bg-blue-50"
              >
                <Plus size={11} />
              </button>
            )}
            <button
              title="删除"
              onClick={e => handleDelete(node, e)}
              className="p-0.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50"
            >
              <Trash2 size={11} />
            </button>
          </div>
          {node.node_type === 'chapter_plan' && (
            <span className="text-[10px] text-gray-400 hidden group-hover:inline ml-1 shrink-0">
              双击写作
            </span>
          )}
        </div>
        {isOpen && node.children?.map(child => renderNode(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* 大纲树 */}
      <div className="w-64 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider shrink-0">大纲树</span>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => {
                if (expandableCount === 0) {
                  toast.error('没有可展开的卷/篇')
                  return
                }
                setShowFullGenModal(true)
              }}
              disabled={outlineTree.length === 0}
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-amber-200 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Sparkles size={12} />
              全部生成
              {/* {expandableCount > 0 && (
                <span className="ml-0.5 bg-amber-200 text-amber-800 text-[9px] font-bold px-1 rounded-full">
                  {expandableCount}
                </span>
              )} */}
            </button>
            {/* <button
              onClick={async () => {
                if (!projectId) return
                try {
                  const res = await outlineApi.create(projectId, {
                    node_type: 'volume',
                    title: '新卷',
                    sort_order: outlineTree.length,
                  })
                  reload()
                  setSelected(res.data)
                } catch {
                  toast.error('创建失败')
                }
              }}
              className="text-gray-400 hover:text-amber-500 p-1 rounded hover:bg-amber-50"
              title="新建卷"
            >
              <Plus size={14} />
            </button> */}
          </div>
        </div>
        <div className="flex-1 overflow-auto py-1.5">
          {outlineTree.map(n => renderNode(n))}
          {outlineTree.length === 0 && (
            <div className="text-center py-8">
              <p className="text-xs text-gray-400">暂无大纲</p>
              <p className="text-[11px] text-gray-300 mt-1">点击「全量生成」或右上角 + 新建卷</p>
            </div>
          )}
        </div>
      </div>

      {/* 右侧详情 + AI 面板 */}
      <div className="flex-1 overflow-auto">
        {selected ? (
          <NodeDetailPanel
            key={selected.id}
            node={selected}
            projectId={projectId!}
            onOpenChapter={() => openChapterFromNode(selected)}
            onSaved={updated => { setSelected(updated); reload() }}
            onAICommitDone={() => {
              reload()
              setExpanded(prev => new Set([...prev, selected.id]))
            }}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <span className="text-3xl">📖</span>
            <p className="text-sm">选择左侧节点查看详情</p>
            <p className="text-xs text-gray-300 text-center max-w-sm">
              「<span className="text-indigo-400">全量生成</span>」：AI 从零生成完整大纲（卷+章节）。
              <br />
              「<span className="text-amber-400">全部展开</span>」：对已有卷/篇补全章节计划。
              <br />
              两者均在右下角队列中后台运行。
            </p>
          </div>
        )}
      </div>

      {/* 全量生成配置弹窗 */}
      {showFullGenModal && projectId && (
        <FullGenConfigModal
          projectId={projectId}
          hasExistingOutline={outlineTree.length > 0}
          onClose={() => setShowFullGenModal(false)}
          onDispatch={handleDispatchFullGen}
        />
      )}

      {/* 批量展开配置弹窗 */}
      {showBatchModal && (
        <BatchExpandConfigModal
          targetCount={expandableCount}
          onClose={() => setShowBatchModal(false)}
          onDispatch={handleDispatchBatchExpand}
        />
      )}
    </div>
  )
}

// ── NodeDetailPanel ────────────────────────────────────────

function NodeDetailPanel({
  node, projectId, onOpenChapter, onSaved, onAICommitDone,
}: {
  node: OutlineNode
  projectId: string
  onOpenChapter: () => void
  onSaved: (updated: OutlineNode) => void
  onAICommitDone: () => void
}) {
  const { characters, storyLines } = useAppStore()
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    title: node.title ?? '',
    summary: node.summary ?? '',
    hook: node.hook ?? '',
    highlight: node.highlight ?? '',
    conflict: node.conflict ?? '',
    // v2 新增字段（章节节点）
    power_milestone: node.power_milestone ?? '',
    emotional_tone: node.emotional_tone ?? '',
    involved_character_ids: (node.involved_character_ids ?? []).map(String),
    storyline_ids: (node.storyline_ids ?? []).map(String),
  })

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: Record<string, any> = {
        title: form.title,
        summary: form.summary,
        hook: form.hook,
        highlight: form.highlight,
        conflict: form.conflict,
      }
      // 章节节点才传新字段，避免干扰卷/篇节点
      if (node.node_type === 'chapter_plan') {
        payload.power_milestone = form.power_milestone || null
        payload.emotional_tone = form.emotional_tone || null
        payload.involved_character_ids = form.involved_character_ids
        payload.storyline_ids = form.storyline_ids
      }
      const res = await outlineApi.update(projectId, node.id, payload)
      onSaved(res.data)
      setEditing(false)
      toast.success('保存成功')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const isExpandable = node.node_type === 'volume' || node.node_type === 'arc'

  const toggleCharacter = (id: string) => {
    setForm(f => ({
      ...f,
      involved_character_ids: f.involved_character_ids.includes(id)
        ? f.involved_character_ids.filter(x => x !== id)
        : [...f.involved_character_ids, id],
    }))
  }

  const toggleStoryline = (id: string) => {
    setForm(f => ({
      ...f,
      storyline_ids: f.storyline_ids.includes(id)
        ? f.storyline_ids.filter(x => x !== id)
        : [...f.storyline_ids, id],
    }))
  }

  return (
    <div className="p-6 max-w-2xl">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded font-medium',
            node.node_type === 'volume' ? 'bg-amber-100 text-amber-700' :
            node.node_type === 'arc'    ? 'bg-blue-100 text-blue-700' :
                                          'bg-gray-100 text-gray-600'
          )}>
            {{ volume: '卷', arc: '篇', chapter_plan: '章' }[node.node_type]}
          </span>
          <h3 className="font-semibold text-gray-800 text-base truncate max-w-xs">
            {editing ? '编辑节点' : node.title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button onClick={() => setEditing(false)} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-500 hover:bg-gray-100 border border-gray-200">
                <X size={12} />取消
              </button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-60">
                <Check size={12} />{saving ? '保存中…' : '保存'}
              </button>
            </>
          ) : (
            <button onClick={() => setEditing(true)} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-gray-500 hover:bg-gray-100 border border-gray-200">
              <Pencil size={12} />编辑
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <Field label="标题" value={form.title} editing={editing} onChange={v => setForm(f => ({ ...f, title: v }))} singleLine />
        <Field label="情节摘要" sublabel="删掉会损失什么" value={form.summary} editing={editing} onChange={v => setForm(f => ({ ...f, summary: v }))} />
        <Field label="钩子 / 悬念" sublabel="读者最想知道答案的核心问题" value={form.hook} editing={editing} onChange={v => setForm(f => ({ ...f, hook: v }))} />
        <Field label="燃点 / 高潮" sublabel="情绪最高点" value={form.highlight} editing={editing} onChange={v => setForm(f => ({ ...f, highlight: v }))} />
        <Field label="核心冲突" sublabel="不可调和的矛盾" value={form.conflict} editing={editing} onChange={v => setForm(f => ({ ...f, conflict: v }))} />

        {/* 章节专属字段 */}
        {node.node_type === 'chapter_plan' && (
          <>
            {/* 实力里程碑 */}
            <div>
              <div className="flex items-baseline gap-2 mb-1">
                <TrendingUp size={12} className="text-indigo-400 shrink-0 mt-0.5" />
                <label className="text-xs font-medium text-gray-600">实力里程碑</label>
                <span className="text-[10px] text-gray-400">本章境界突破或关键技能习得</span>
              </div>
              {editing ? (
                <input
                  value={form.power_milestone}
                  onChange={e => setForm(f => ({ ...f, power_milestone: e.target.value }))}
                  placeholder="例：林默突破炼气九层，踏入筑基"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
                />
              ) : (
                <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50">
                  {form.power_milestone || <span className="text-gray-400 italic">—</span>}
                </div>
              )}
            </div>

            {/* 情感基调 */}
            <div>
              <div className="flex items-baseline gap-2 mb-1">
                <label className="text-xs font-medium text-gray-600">情感基调</label>
                <span className="text-[10px] text-gray-400">本章整体氛围</span>
              </div>
              {editing ? (
                <input
                  value={form.emotional_tone}
                  onChange={e => setForm(f => ({ ...f, emotional_tone: e.target.value }))}
                  placeholder="例：压抑→绝地反杀→爽快，或：温情、紧张悬疑……"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
                />
              ) : (
                <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50">
                  {form.emotional_tone || <span className="text-gray-400 italic">—</span>}
                </div>
              )}
            </div>

            {/* 出场人物 */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Users size={12} className="text-blue-400 shrink-0" />
                <label className="text-xs font-medium text-gray-600">出场人物</label>
                <span className="text-[10px] text-gray-400">
                  {editing ? '点击选择/取消' : `${form.involved_character_ids.length} 位`}
                </span>
              </div>
              {characters.length === 0 ? (
                <p className="text-xs text-gray-400 italic">暂无人物数据，请先在「人物」页创建</p>
              ) : editing ? (
                <div className="flex flex-wrap gap-1.5">
                  {characters.map(c => {
                    const selected = form.involved_character_ids.includes(String(c.id))
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => toggleCharacter(String(c.id))}
                        className={clsx(
                          'text-xs px-2.5 py-1 rounded-full border transition-all',
                          selected
                            ? 'bg-blue-500 border-blue-500 text-white'
                            : 'border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-600',
                        )}
                      >
                        {c.name}
                        {c.current_realm && <span className="ml-1 opacity-70 text-[10px]">{c.current_realm}</span>}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {form.involved_character_ids.length === 0 ? (
                    <span className="text-xs text-gray-400 italic">—</span>
                  ) : (
                    form.involved_character_ids.map(id => {
                      const c = characters.find(x => String(x.id) === id)
                      return c ? (
                        <span key={id} className="text-xs px-2.5 py-1 rounded-full bg-blue-50 border border-blue-100 text-blue-700">
                          {c.name}
                          {c.current_realm && <span className="ml-1 opacity-60">{c.current_realm}</span>}
                        </span>
                      ) : null
                    })
                  )}
                </div>
              )}
            </div>

            {/* 关联故事线 */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <GitBranch size={12} className="text-green-500 shrink-0" />
                <label className="text-xs font-medium text-gray-600">关联故事线</label>
                <span className="text-[10px] text-gray-400">
                  {editing ? '本章推进了哪些故事线' : `${form.storyline_ids.length} 条`}
                </span>
              </div>
              {storyLines.length === 0 ? (
                <p className="text-xs text-gray-400 italic">暂无故事线，请先在「世界」→「故事线」中创建</p>
              ) : editing ? (
                <div className="flex flex-wrap gap-1.5">
                  {storyLines.map(sl => {
                    const selected = form.storyline_ids.includes(String(sl.id))
                    return (
                      <button
                        key={sl.id}
                        type="button"
                        onClick={() => toggleStoryline(String(sl.id))}
                        className={clsx(
                          'text-xs px-2.5 py-1 rounded-full border transition-all',
                          selected
                            ? 'bg-green-500 border-green-500 text-white'
                            : 'border-gray-200 text-gray-600 hover:border-green-300 hover:text-green-700',
                        )}
                      >
                        {sl.name}
                        <span className="ml-1 opacity-70 text-[10px]">
                          {sl.line_type === 'main' ? '主线' : sl.line_type === 'romance' ? '感情' : sl.line_type === 'growth' ? '成长' : sl.line_type}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {form.storyline_ids.length === 0 ? (
                    <span className="text-xs text-gray-400 italic">—</span>
                  ) : (
                    form.storyline_ids.map(id => {
                      const sl = storyLines.find(x => String(x.id) === id)
                      return sl ? (
                        <span key={id} className="text-xs px-2.5 py-1 rounded-full bg-green-50 border border-green-100 text-green-700">
                          {sl.name}
                        </span>
                      ) : null
                    })
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {node.node_type === 'chapter_plan' && (
        <button onClick={onOpenChapter} className="mt-5 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm rounded-lg">
          打开并切换到该章节
        </button>
      )}

      {isExpandable && (
        <OutlineAIPanel node={node} projectId={projectId} onCommitDone={onAICommitDone} />
      )}
    </div>
  )
}

// ── Field ──────────────────────────────────────────────────

function Field({
  label, sublabel, value, editing, onChange, singleLine = false,
}: {
  label: string
  sublabel?: string
  value: string
  editing: boolean
  onChange: (v: string) => void
  singleLine?: boolean
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <label className="text-xs font-medium text-gray-600">{label}</label>
        {sublabel && <span className="text-[10px] text-gray-400">{sublabel}</span>}
      </div>
      {editing ? (
        singleLine ? (
          <input value={value} onChange={e => onChange(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
        ) : (
          <textarea value={value} onChange={e => onChange(e.target.value)} rows={3}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300 resize-y" />
        )
      ) : (
        <div className={clsx(
          'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 whitespace-pre-wrap',
          singleLine ? 'text-gray-800' : 'text-gray-700 min-h-[64px]'
        )}>
          {value || <span className="text-gray-400 italic">—</span>}
        </div>
      )}
    </div>
  )
}
