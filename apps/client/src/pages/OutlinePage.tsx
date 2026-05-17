import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronRight, ChevronDown, Plus, Trash2, Pencil, Check, X,
  Sparkles, BookOpen, Users, TrendingUp, GitBranch, Target,
} from 'lucide-react'
import { chaptersApi, outlineApi, projectsApi } from '../api/client'
import { useAppStore, toOutlineApiModelProfile, routeLlmProviderPayload } from '../store'
import type { OutlineNode, OutlinePlanQualityReport } from '../types'
import OutlinePlanQualityView from '../components/Outline/OutlinePlanQualityView'
import { collectAncestorIds, findChapterPlanByNumber } from '../utils/outlineNavigate'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import OutlineAIPanel from '../components/Outline/OutlineAIPanel'
import ScenePanel from '../components/Outline/ScenePanel'
import VolumeExpandButton from '../components/Outline/VolumeExpandButton'
import { TargetWordsInput } from '../components/TargetWordsInput'
import { collectExpandableNodes } from '../utils/outlineAiExpand'
import RepairConfirmModal, { clampMaxRounds, clampMinScore } from '../components/Outline/RepairConfirmModal'
import type { RepairConfig } from '../components/Outline/RepairConfirmModal'

type RevisionSnapshotNode = {
  id: string
  parent_id?: string | null
  node_type?: string
  title?: string
  summary?: string
  hook?: string
  highlight?: string
  conflict?: string
  sort_order?: number
  expected_words?: number
  reader_hook_score?: number
  storyline_ids?: string[]
  involved_character_ids?: string[]
  key_item_ids?: string[]
  key_skill_ids?: string[]
  emotional_tone?: string
  pacing?: string
  power_milestone?: string
  foreshadows_laid?: Array<{ id?: string; description?: string }>
  foreshadows_resolved?: Array<{ id?: string; description?: string }>
}

type OutlineDiffField = {
  field: string
  before: string
  after: string
}

type OutlineDiffItem = {
  changeType: 'added' | 'removed' | 'updated'
  severity: 'high' | 'medium' | 'low'
  nodeId: string
  nodeType: string
  title: string
  path: string
  fields?: OutlineDiffField[]
}

type OutlineDiffResult = {
  summary: {
    added: number
    removed: number
    updated: number
    high: number
  }
  changes: OutlineDiffItem[]
}

const DIFF_FIELDS: Array<keyof RevisionSnapshotNode> = [
  'title',
  'summary',
  'hook',
  'highlight',
  'conflict',
  'sort_order',
  'expected_words',
  'reader_hook_score',
  'storyline_ids',
  'involved_character_ids',
  'key_item_ids',
  'key_skill_ids',
  'emotional_tone',
  'pacing',
  'power_milestone',
  'foreshadows_laid',
  'foreshadows_resolved',
]

const FIELD_LABEL: Record<string, string> = {
  title: '标题',
  summary: '核心事件',
  hook: '开篇钩子',
  highlight: '高光',
  conflict: '人物变化/冲突',
  sort_order: '排序',
  expected_words: '预期字数',
  reader_hook_score: '钩子分',
  storyline_ids: '故事线',
  involved_character_ids: '出场人物',
  key_item_ids: '关键道具',
  key_skill_ids: '关键技能',
  emotional_tone: '情感基调',
  pacing: '节奏',
  power_milestone: '实力里程碑',
  foreshadows_laid: '铺设伏笔',
  foreshadows_resolved: '回收伏笔',
}

const toDisplayText = (value: unknown) => {
  if (value === null || value === undefined) return '（空）'
  if (typeof value === 'string') return value.trim() || '（空）'
  if (Array.isArray(value)) return value.length ? JSON.stringify(value) : '（空）'
  return String(value)
}

const buildPath = (node: RevisionSnapshotNode, nodeMap: Map<string, RevisionSnapshotNode>) => {
  const parts: string[] = []
  let cur: RevisionSnapshotNode | undefined = node
  let safeGuard = 0
  while (cur && safeGuard < 12) {
    parts.unshift(cur.title || '未命名节点')
    const pid: string | undefined = cur.parent_id || undefined
    cur = pid ? nodeMap.get(pid) : undefined
    safeGuard += 1
  }
  return parts.join(' > ')
}

const calcSeverity = (changeType: OutlineDiffItem['changeType'], fields?: OutlineDiffField[]) => {
  if (changeType === 'added' || changeType === 'removed') return 'high' as const
  const f = new Set((fields || []).map(item => item.field))
  if (f.has('hook') || f.has('conflict') || f.has('sort_order') || f.has('foreshadows_resolved')) return 'high' as const
  if (f.has('summary') || f.has('title') || f.has('involved_character_ids') || f.has('power_milestone')) return 'medium' as const
  return 'low' as const
}

const compareSnapshots = (baseNodes: RevisionSnapshotNode[], targetNodes: RevisionSnapshotNode[]): OutlineDiffResult => {
  const baseMap = new Map(baseNodes.map(node => [node.id, node]))
  const targetMap = new Map(targetNodes.map(node => [node.id, node]))
  const changes: OutlineDiffItem[] = []

  baseNodes.forEach(baseNode => {
    const targetNode = targetMap.get(baseNode.id)
    if (!targetNode) {
      const severity = calcSeverity('removed')
      changes.push({
        changeType: 'removed',
        severity,
        nodeId: baseNode.id,
        nodeType: baseNode.node_type || 'unknown',
        title: baseNode.title || '未命名节点',
        path: buildPath(baseNode, baseMap),
      })
      return
    }
    const fields: OutlineDiffField[] = []
    DIFF_FIELDS.forEach(field => {
      const before = toDisplayText(baseNode[field])
      const after = toDisplayText(targetNode[field])
      if (before !== after) {
        fields.push({ field: String(field), before, after })
      }
    })
    if (fields.length) {
      const severity = calcSeverity('updated', fields)
      changes.push({
        changeType: 'updated',
        severity,
        nodeId: baseNode.id,
        nodeType: targetNode.node_type || 'unknown',
        title: targetNode.title || '未命名节点',
        path: buildPath(targetNode, targetMap),
        fields,
      })
    }
  })

  targetNodes.forEach(targetNode => {
    if (baseMap.has(targetNode.id)) return
    const severity = calcSeverity('added')
    changes.push({
      changeType: 'added',
      severity,
      nodeId: targetNode.id,
      nodeType: targetNode.node_type || 'unknown',
      title: targetNode.title || '未命名节点',
      path: buildPath(targetNode, targetMap),
    })
  })

  const summary = {
    added: changes.filter(item => item.changeType === 'added').length,
    removed: changes.filter(item => item.changeType === 'removed').length,
    updated: changes.filter(item => item.changeType === 'updated').length,
    high: changes.filter(item => item.severity === 'high').length,
  }
  return {
    summary,
    changes: changes.sort((a, b) => {
      const rank = { high: 0, medium: 1, low: 2 }
      if (rank[a.severity] !== rank[b.severity]) return rank[a.severity] - rank[b.severity]
      return a.path.localeCompare(b.path)
    }),
  }
}

// ── 全量生成配置弹窗（只收集参数，执行交给队列）──────────────

const OUTLINE_WORD_OPTIONS = [
  { label: '短篇',   value: 800000  },
  { label: '标准',   value: 1200000 },
  { label: '长篇',   value: 1500000 },
  { label: '超长篇', value: 2000000 },
] as const

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
    theme_statement?: string
    model_profile: string
    clear_existing: boolean
    llm_provider_id?: string
  }) => void
}) {
  const { currentProject, setCurrentProject } = useAppStore()
  const initWords = Number(currentProject?.target_words) || 1200000
  const [targetWords, setTargetWords] = useState(initWords)
  const [customMode, setCustomMode] = useState(false)
  const [themeStatement, setThemeStatement] = useState('')
  const [clearExisting, setClearExisting] = useState(hasExistingOutline)
  const [saving, setSaving] = useState(false)

  const estChapters = Math.round(targetWords / 2300)
  const estVols = Math.ceil(estChapters / 60)

  // target_words 转为 scale_hint 标签（兼容后端旧字段）
  const toScaleHint = (w: number) => {
    if (w <= 500000) return 'micro'
    if (w <= 900000) return 'short'
    if (w <= 1400000) return 'medium'
    if (w <= 1700000) return 'long'
    return 'epic'
  }

  const handleStart = async () => {
    if (clearExisting && !window.confirm('将清除现有全部大纲节点，确定继续？')) return
    // 若字数有变化，先 PATCH 保存到项目
    if (targetWords !== initWords && currentProject) {
      setSaving(true)
      try {
        const res = await projectsApi.update(currentProject.id, { target_words: targetWords })
        setCurrentProject(res.data)
      } catch {
        // 静默失败：即使保存失败也继续生成，后端会用传入参数
      } finally {
        setSaving(false)
      }
    }
    const route = useAppStore.getState().aiBackendRoute
    onDispatch({
      scale_hint: toScaleHint(targetWords),
      theme_statement: themeStatement.trim() || undefined,
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
            AI 读取项目的 logline、类型、世界观、人物生成大纲；后端会按字数目标推算卷数并写入大纲树。
            <span className="block mt-1 text-amber-600 font-medium">
              任务将在右下角队列中后台运行，不影响当前操作。
            </span>
          </p>

          {/* 字数目标（单一数据源） */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500">全书字数目标</label>
              <button
                type="button"
                onClick={() => setCustomMode(m => !m)}
                className="text-xs text-amber-500 hover:text-amber-600"
              >
                {customMode ? '快捷选择' : '自定义'}
              </button>
            </div>

            {customMode ? (
              <TargetWordsInput value={targetWords} onChange={setTargetWords} />
            ) : (
              <div className="grid grid-cols-4 gap-1.5">
                {OUTLINE_WORD_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTargetWords(opt.value)}
                    className={clsx(
                      'rounded-xl border py-2 text-center transition-all',
                      targetWords === opt.value
                        ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-300'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    )}
                  >
                    <div className={clsx('text-xs font-medium', targetWords === opt.value ? 'text-indigo-700' : 'text-gray-700')}>
                      {opt.label}
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">{(opt.value / 10000).toFixed(0)}万字</div>
                  </button>
                ))}
              </div>
            )}

            {/* 实时预览 */}
            <div className="mt-2 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-xs text-amber-700">
              约 <span className="font-semibold">{estChapters}</span> 章 ·
              约 <span className="font-semibold">{estVols}</span> 卷 ·
              每章均约 2300 字
              {targetWords !== initWords && (
                <span className="ml-2 text-amber-500">（修改后将保存到项目）</span>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-2">全书立意</label>
            <textarea
              value={themeStatement}
              onChange={e => setThemeStatement(e.target.value)}
              placeholder="例如：人在被命运压低时，仍能靠选择重塑自身价值。"
              className="w-full min-h-[64px] text-sm border border-gray-200 rounded-xl px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-amber-300 placeholder:text-gray-300"
            />
            <p className="mt-1 text-[11px] text-gray-400 leading-relaxed">
              留空时后端会从项目故事核中读取主题。
            </p>
          </div>

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
                  识别现有大纲中尚无章节计划的卷，直接填充内容。已写章节和已有大纲节点全部保留。
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
            disabled={saving}
            className="flex items-center gap-2 px-4 py-1.5 text-sm font-medium bg-amber-500 hover:bg-amber-600 text-white rounded-lg shadow-sm disabled:opacity-50"
          >
            <Sparkles size={14} />
            {saving ? '保存中...' : '加入队列并开始'}
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
  const [chapterCount, setChapterCount] = useState(60)

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
            将对 <span className="font-semibold text-gray-700">{targetCount} 个</span>尚未有章节计划的卷依次展开，默认每卷 60 章。
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
    currentProject, setCurrentProject,
    aiBackendRoute,
  } = useAppStore()
  const [selected, setSelected] = useState<OutlineNode | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [showFullGenModal, setShowFullGenModal] = useState(false)
  const [showBatchModal, setShowBatchModal] = useState(false)
  const [contentTab, setContentTab] = useState<'node' | 'bookQuality' | 'volumeQuality' | 'revisions'>('node')
  const [outlineRevisions, setOutlineRevisions] = useState<any[]>([])
  const [compareBaseRevisionId, setCompareBaseRevisionId] = useState<string | null>(null)
  const [compareTargetRevisionId, setCompareTargetRevisionId] = useState<string | null>(null)
  const [isCompareDrawerOpen, setIsCompareDrawerOpen] = useState(false)
  const [isComparing, setIsComparing] = useState(false)
  const [compareResult, setCompareResult] = useState<OutlineDiffResult | null>(null)
  const [compareFilter, setCompareFilter] = useState<'all' | 'high' | 'structure' | 'content'>('high')
  const [selectedBookQualityRevisionId, setSelectedBookQualityRevisionId] = useState<string | null>(null)
  const [selectedVolumeQualityRevisionId, setSelectedVolumeQualityRevisionId] = useState<string | null>(null)
  /**
   * 修复弹窗状态：scope 与目标卷节点。
   * 打开弹窗后，用户在弹窗里确认配置；配置同步回 repairConfig。
   */
  const [repairModalOpen, setRepairModalOpen] = useState(false)
  const [repairModalScope, setRepairModalScope] = useState<'volume' | 'book'>('volume')
  const [repairModalVolumeNode, setRepairModalVolumeNode] = useState<OutlineNode | undefined>()

  /**
   * 单卷修复配置，与质检报告总分同刻度（0–100）。
   * 弹窗关闭后保留上次配置，方便连续操作。
   */
  const [repairConfig, setRepairConfig] = useState<RepairConfig>({
    continuous: true,
    maxRounds: 5,
    minScore: 80,
  })

  const reload = () => {
    if (!projectId) return
    outlineApi.getTree(projectId).then(res => {
      setOutlineTree(res.data)
      const topIds = new Set<string>(res.data.map((n: OutlineNode) => n.id))
      setExpanded(prev => new Set([...prev, ...topIds]))
    })
  }

  const reloadRevisions = () => {
    if (!projectId) return
    outlineApi.listRevisions(projectId).then(res => setOutlineRevisions(res.data)).catch(() => {})
  }

  useEffect(() => { reload(); reloadRevisions() }, [projectId])

  useEffect(() => {
    if (!projectId) return
    projectsApi.get(projectId).then(res => setCurrentProject(res.data)).catch(() => {})
  }, [projectId, setCurrentProject])

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('queue-drawer-avoid', { detail: isCompareDrawerOpen }))
    return () => {
      window.dispatchEvent(new CustomEvent('queue-drawer-avoid', { detail: false }))
    }
  }, [isCompareDrawerOpen])

  // 队列任务完成后自动刷新大纲树与项目（含 story_core 大纲质检）
  useEffect(() => {
    if (outlineNeedsReload) {
      reload()
      reloadRevisions()
      if (projectId) projectsApi.get(projectId).then(res => setCurrentProject(res.data)).catch(() => {})
      setOutlineNeedsReload(false)
    }
  }, [outlineNeedsReload, projectId, setCurrentProject, setOutlineNeedsReload])

  const bookOutlineQuality = (currentProject?.story_core as Record<string, unknown> | undefined)?.outline_quality as
    | OutlinePlanQualityReport
    | undefined

  const jumpToChapterPlan = (num: number) => {
    const node = findChapterPlanByNumber(outlineTree, num)
    if (!node) {
      toast.error(`未在大纲树中找到第 ${num} 章`)
      return
    }
    setSelected(node)
    const anc = collectAncestorIds(outlineTree, node.id)
    setExpanded(prev => new Set([...prev, ...anc]))
  }

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  const typeLabel = (t: OutlineNode['node_type']) =>
    ({ volume: '卷', arc: '旧篇', chapter_plan: '章' }[t])

  const typeColor = (t: OutlineNode['node_type']) =>
    ({ volume: 'bg-amber-100 text-amber-700', arc: 'bg-blue-100 text-blue-700', chapter_plan: 'bg-gray-100 text-gray-600' }[t])

  const openChapterFromNode = async (node: OutlineNode) => {
    if (!projectId || node.node_type !== 'chapter_plan') return
    try {
      const listRes = await chaptersApi.list(projectId)
      const chapters = listRes.data
      const nextSortOrder = chapters.length
        ? Math.max(...chapters.map((c: any) => Number(c.sort_order) || 0)) + 1
        : 0
      let chapter = chapters.find((c: any) => c.outline_node_id === node.id)
      if (!chapter) {
        const createRes = await chaptersApi.create(projectId, {
          title: node.title,
          outline_node_id: node.id,
          sort_order: nextSortOrder,
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
    const childType = 'chapter_plan'
    const titleMap: Record<string, string> = { chapter_plan: '新章节' }
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
    theme_statement?: string
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
      toast.error('没有可展开的卷（可能已全部有章节计划，或大纲为空）')
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

  const handleDispatchOutlineQuality = (scope: 'all' | 'volume' | 'book', volumeNode?: OutlineNode) => {
    if (!projectId) return
    if (scope === 'volume' && !volumeNode) {
      toast.error('请先选择要质检的卷')
      return
    }
    const route = useAppStore.getState().aiBackendRoute
    const modelProfile = toOutlineApiModelProfile(route)
    addGenTask({
      type: 'outline_quality',
      projectId,
      label: scope === 'volume'
        ? `单卷大纲质检：${volumeNode?.title ?? ''}`
        : scope === 'book'
          ? '全书大纲质检'
          : '大纲质检：单卷 + 全书',
      params: {
        scope,
        ...(volumeNode ? { volume_node_id: volumeNode.id } : {}),
        model_profile: modelProfile,
        ...routeLlmProviderPayload(route),
      },
    })
    if (scope === 'book') setContentTab('bookQuality')
    if (scope === 'volume') setContentTab('volumeQuality')
    toast.success('已加入质检队列，右下角可查看进度')
  }

  /**
   * 打开修复确认弹窗。
   *
   * scope='volume' 时需传入 volumeNode；弹窗关闭（取消或确认）后由弹窗回调处理后续。
   *
   * @param scope 修复范围：'volume' 单卷 | 'book' 全书 | 'all' 单卷+全书
   * @param volumeNode scope='volume' 时目标卷节点（缺失时 toast 报错）
   */
  const handleDispatchOutlineRepair = (scope: 'all' | 'volume' | 'book', volumeNode?: OutlineNode) => {
    if (!projectId) return
    if (scope === 'volume' && !volumeNode) {
      toast.error('请先选择要修复的卷')
      return
    }
    // 全书修复不需要弹窗配置连续修复参数，直接走确认弹窗展示说明即可
    setRepairModalScope(scope === 'all' ? 'book' : scope)
    setRepairModalVolumeNode(volumeNode)
    setRepairModalOpen(true)
  }

  /**
   * 用户在弹窗中点击「开始修复」后的回调。
   * 将配置写回 state（保留下次打开时的默认值），并派发队列任务。
   *
   * @param config 用户在弹窗中确定的修复配置
   */
  const handleRepairConfirm = (config: RepairConfig) => {
    if (!projectId) return
    setRepairConfig(config)   // 保留配置供下次打开使用
    const route = useAppStore.getState().aiBackendRoute
    const modelProfile = toOutlineApiModelProfile(route)
    const rounds = clampMaxRounds(config.maxRounds)
    const minScore = clampMinScore(config.minScore)
    addGenTask({
      type: 'outline_repair',
      projectId,
      label: repairModalScope === 'volume'
        ? config.continuous
          ? `单卷连续大纲修复（≤${rounds}轮·总分≥${minScore}或pass）：${repairModalVolumeNode?.title ?? ''}`
          : `单卷大纲修复：${repairModalVolumeNode?.title ?? ''}`
        : '全书大纲修复',
      params: {
        scope: repairModalScope,
        ...(repairModalVolumeNode ? { volume_node_id: repairModalVolumeNode.id } : {}),
        ...(repairModalScope === 'volume'
          ? config.continuous
            ? {
              continuous_repair: true,
              continuous_max_rounds: rounds,
              continuous_min_score: minScore,
            }
            : { continuous_repair: false }
          : {}),
        model_profile: modelProfile,
        ...routeLlmProviderPayload(route),
      },
    })
    toast.success('已加入修复队列，右下角可查看进度')
  }

  const handleCreateManualSnapshot = async () => {
    if (!projectId) return
    try {
      await outlineApi.createRevision(projectId, {
        label: '手动大纲快照',
        source: 'manual',
        scope: 'book',
      })
      toast.success('已保存当前大纲快照')
      reloadRevisions()
    } catch {
      toast.error('保存快照失败')
    }
  }

  const handleSelectCompareBase = (revisionId: string) => {
    setCompareBaseRevisionId(revisionId)
    toast.success('已设置基线版本 A')
  }

  const handleCompareWithBase = async (targetRevisionId: string) => {
    if (!projectId) return
    if (!compareBaseRevisionId) {
      toast.error('请先设定一个基线版本 A')
      return
    }
    if (compareBaseRevisionId === targetRevisionId) {
      toast.error('A 与 B 不能是同一版本')
      return
    }
    setIsComparing(true)
    try {
      const [baseRes, targetRes] = await Promise.all([
        outlineApi.getRevision(projectId, compareBaseRevisionId),
        outlineApi.getRevision(projectId, targetRevisionId),
      ])
      const baseNodes = (baseRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[]
      const targetNodes = (targetRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[]
      const diff = compareSnapshots(baseNodes, targetNodes)
      setCompareResult(diff)
      setCompareTargetRevisionId(targetRevisionId)
      setCompareFilter('high')
      setIsCompareDrawerOpen(true)
    } catch {
      toast.error('快照对比失败')
    } finally {
      setIsComparing(false)
    }
  }

  const handleCompareLatestTwo = async () => {
    if (visibleRevisions.length < 2) {
      toast.error('至少需要 2 个快照才可对比')
      return
    }
    const latest = visibleRevisions[0]
    const previous = visibleRevisions[1]
    setCompareBaseRevisionId(previous.id)
    setIsComparing(true)
    try {
      const [baseRes, targetRes] = await Promise.all([
        outlineApi.getRevision(projectId!, previous.id),
        outlineApi.getRevision(projectId!, latest.id),
      ])
      const diff = compareSnapshots(
        (baseRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[],
        (targetRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[],
      )
      setCompareResult(diff)
      setCompareTargetRevisionId(latest.id)
      setCompareFilter('high')
      setIsCompareDrawerOpen(true)
    } catch {
      toast.error('快照对比失败')
    } finally {
      setIsComparing(false)
    }
  }

  const expandableCount = collectExpandableNodes(outlineTree).length

  const renderNode = (node: OutlineNode, depth = 0) => {
    const isOpen = expanded.has(node.id)
    const hasChildren = node.children?.length > 0
    const canHaveChildren = node.node_type !== 'chapter_plan'

    return (
      <div key={node.id} className={node.node_type === 'volume' ? 'relative' : undefined}>
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
          {node.node_type === 'volume' && projectId && (
            <VolumeExpandButton
              volumeNode={node}
              projectId={projectId}
              aiBackendRoute={aiBackendRoute}
              onExpanded={reload}
            />
          )}
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

  const filteredCompareChanges = (compareResult?.changes || []).filter(change => {
    if (compareFilter === 'all') return true
    if (compareFilter === 'high') return change.severity === 'high'
    if (compareFilter === 'structure') return change.changeType === 'added' || change.changeType === 'removed'
    return change.changeType === 'updated'
  })

  const buildParentMap = (nodes: OutlineNode[]) => {
    const parentMap = new Map<string, string | undefined>()
    const walk = (node: OutlineNode, parentId?: string) => {
      parentMap.set(node.id, parentId)
      node.children?.forEach(child => walk(child, node.id))
    }
    nodes.forEach(root => walk(root, undefined))
    return parentMap
  }

  const findSelectedVolumeId = () => {
    if (!selected) return null
    if (selected.node_type === 'volume') return selected.id
    const nodeMap = new Map<string, OutlineNode>()
    const walk = (node: OutlineNode) => {
      nodeMap.set(node.id, node)
      node.children?.forEach(walk)
    }
    outlineTree.forEach(walk)
    const parentMap = buildParentMap(outlineTree)
    let curId: string | undefined = selected.id
    let safeGuard = 0
    while (curId && safeGuard < 20) {
      const node = nodeMap.get(curId)
      if (node?.node_type === 'volume') return node.id
      curId = parentMap.get(curId)
      safeGuard += 1
    }
    return null
  }

  const selectedVolumeId = findSelectedVolumeId()
  const outlineNodeMap = new Map<string, OutlineNode>()
  const walkOutlineNode = (node: OutlineNode) => {
    outlineNodeMap.set(node.id, node)
    node.children?.forEach(walkOutlineNode)
  }
  outlineTree.forEach(walkOutlineNode)
  const selectedVolumeNode = selectedVolumeId ? outlineNodeMap.get(selectedVolumeId) : null
  const selectedVolumeQuality = selectedVolumeNode?.extra?.outline_quality as OutlinePlanQualityReport | undefined
  const getQualityReportFromRevision = (rev: any): OutlinePlanQualityReport | undefined => {
    const report = rev?.meta?.quality_report
    return report && typeof report === 'object' ? report as OutlinePlanQualityReport : undefined
  }
  const qualityRevisions = outlineRevisions.filter(rev => rev.source === 'quality')
  const bookQualityRevisions = qualityRevisions.filter(rev => rev.scope === 'book')
  const volumeQualityRevisions = selectedVolumeId
    ? qualityRevisions.filter(rev => rev.scope === 'volume' && rev.volume_node_id === selectedVolumeId)
    : []
  const selectedBookQualityRevision = selectedBookQualityRevisionId
    ? bookQualityRevisions.find(rev => rev.id === selectedBookQualityRevisionId)
    : null
  const selectedVolumeQualityRevision = selectedVolumeQualityRevisionId
    ? volumeQualityRevisions.find(rev => rev.id === selectedVolumeQualityRevisionId)
    : null
  const displayedBookQuality = getQualityReportFromRevision(selectedBookQualityRevision) || bookOutlineQuality
  const displayedVolumeQuality = getQualityReportFromRevision(selectedVolumeQualityRevision) || selectedVolumeQuality
  useEffect(() => {
    setSelectedVolumeQualityRevisionId(null)
  }, [selectedVolumeId])
  const snapshotRevisions = outlineRevisions.filter(rev =>
    ['manual', 'pre_repair', 'post_repair'].includes(rev.source),
  )
  const visibleRevisions = selectedVolumeId
    ? snapshotRevisions.filter(rev => rev.scope === 'volume' && rev.volume_node_id === selectedVolumeId)
    : snapshotRevisions

  const compareBaseRevision = outlineRevisions.find(r => r.id === compareBaseRevisionId)
  const compareTargetRevision = outlineRevisions.find(r => r.id === compareTargetRevisionId)

  return (
    <div className="flex h-full">
      {/* 大纲树 */}
      <div className="w-64 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider shrink-0">大纲树</span>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              title="删除全部章节计划，保留卷与篇；正文保留并解除关联"
              onClick={async () => {
                if (!projectId) return
                const ok = window.confirm(
                  '确定清空大纲中的全部「章节计划」？\n\n'
                  + '· 卷、篇节点会保留\n'
                  + '· 写作端的章节正文不会删除，仅解除与大纲计划的绑定',
                )
                if (!ok) return
                try {
                  const res = await outlineApi.clearChapterPlans(projectId)
                  const n = res.data?.deleted ?? 0
                  toast.success(n > 0 ? `已清空 ${n} 个章节计划` : '当前没有章节计划')
                  setSelected(null)
                  reload()
                } catch {
                  toast.error('清空章节计划失败')
                }
              }}
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-gray-200 text-gray-600 bg-gray-50 hover:bg-gray-100 hover:border-gray-300"
            >
              <Trash2 size={12} />
              清空章节
            </button>
            <button
              type="button"
              onClick={() => setShowFullGenModal(true)}
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-amber-200 text-amber-700 bg-amber-50 hover:bg-amber-100"
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
      <div className="flex-1 overflow-auto flex flex-col">
        <div className="shrink-0 border-b border-gray-100 bg-white px-6 pt-4">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setContentTab('node')}
              className={clsx(
                'px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors',
                contentTab === 'node'
                  ? 'border-amber-500 text-amber-700'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
              )}
            >
              当前节点
            </button>
            <button
              type="button"
              onClick={() => setContentTab('bookQuality')}
              className={clsx(
                'px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors',
                contentTab === 'bookQuality'
                  ? 'border-indigo-500 text-indigo-700'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
              )}
            >
              全书质检
            </button>
            <button
              type="button"
              onClick={() => setContentTab('volumeQuality')}
              className={clsx(
                'px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors',
                contentTab === 'volumeQuality'
                  ? 'border-cyan-500 text-cyan-700'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
              )}
            >
              单卷质检
            </button>
            <button
              type="button"
              onClick={() => setContentTab('revisions')}
              className={clsx(
                'px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors',
                contentTab === 'revisions'
                  ? 'border-slate-500 text-slate-700'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
              )}
            >
              大纲快照
            </button>
          </div>
        </div>

        {contentTab === 'bookQuality' ? (
          <div className="p-6 w-full">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-semibold text-gray-900">全书大纲质检</h3>
                <p className="text-xs text-gray-400 mt-1">跨卷承接、全书镜像重复、主题兑现和世界观冲突</p>
              </div>
              <button
                type="button"
                onClick={() => handleDispatchOutlineQuality('book')}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200"
              >
                <Check size={12} />
                重新全书质检
              </button>
              <button
                type="button"
                onClick={() => handleDispatchOutlineRepair('book')}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200"
              >
                <Sparkles size={12} />
                Graph 修复全书
              </button>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
              <div className="min-w-0">
                {displayedBookQuality && typeof displayedBookQuality === 'object' ? (
                  <OutlinePlanQualityView report={displayedBookQuality} onChapterClick={jumpToChapterPlan} />
                ) : (
                  <div className="border border-dashed border-indigo-200 bg-indigo-50/40 rounded-lg px-4 py-8 text-sm text-indigo-700">
                    当前还没有全书大纲质检报告。
                  </div>
                )}
              </div>
              <div className="xl:sticky xl:top-4">
                <div className="rounded-lg border border-gray-100 bg-white">
                  <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-100">
                    <h4 className="text-xs font-semibold text-gray-700">全书质检时间线</h4>
                    <span className="text-[11px] text-gray-400">共 {bookQualityRevisions.length} 条</span>
                  </div>
                  {bookQualityRevisions.length > 0 ? (
                    <div className="max-h-[70vh] overflow-auto divide-y divide-gray-100">
                      {bookQualityRevisions.slice(0, 24).map(rev => (
                        <button
                          key={rev.id}
                          type="button"
                          onClick={() => setSelectedBookQualityRevisionId(rev.id)}
                          className={clsx(
                            'w-full text-left px-3 py-2 hover:bg-gray-50',
                            selectedBookQualityRevisionId === rev.id && 'bg-indigo-50',
                          )}
                        >
                          <div className="flex items-center justify-between gap-3 text-xs">
                            <div className="min-w-0">
                              <div className="font-medium text-gray-800 truncate">{rev.label}</div>
                              <div className="text-gray-400 mt-0.5">
                                score {rev.meta?.quality_score ?? '-'} · {rev.meta?.quality_status ?? '-'} · {rev.created_at ? new Date(rev.created_at).toLocaleString() : ''}
                              </div>
                            </div>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                              {String(rev.id).slice(0, 8)}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="px-3 py-4 text-xs text-gray-400">
                      还没有全书质检历史记录。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : contentTab === 'volumeQuality' ? (
          <div className="p-6 w-full">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-semibold text-gray-900">单卷大纲质检</h3>
                <p className="text-xs text-gray-400 mt-1">
                  {selectedVolumeNode
                    ? `当前卷：${selectedVolumeNode.title}`
                    : '请先在左侧选择一个卷（或该卷下的篇/章）'}
                </p>
              </div>
              <div className="flex max-w-[min(100vw-2rem,52rem)] flex-nowrap items-center justify-end gap-x-1.5 gap-y-0 overflow-x-auto pb-0.5 sm:max-w-none sm:gap-x-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedVolumeNode) {
                      toast.error('请先选择一个卷')
                      return
                    }
                    handleDispatchOutlineRepair('volume', selectedVolumeNode)
                  }}
                  disabled={!selectedVolumeNode}
                  className="flex shrink-0 items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 disabled:opacity-50 disabled:cursor-not-allowed sm:px-3"
                >
                  <Sparkles size={12} />
                  修复本卷
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedVolumeNode) {
                      toast.error('请先选择一个卷')
                      return
                    }
                    handleDispatchOutlineQuality('volume', selectedVolumeNode)
                  }}
                  disabled={!selectedVolumeNode}
                  className="flex shrink-0 items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg text-cyan-700 bg-cyan-50 hover:bg-cyan-100 border border-cyan-200 disabled:opacity-50 disabled:cursor-not-allowed sm:px-3"
                >
                  <Check size={12} />
                  重新单卷质检
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
              <div className="min-w-0">
                {selectedVolumeNode ? (
                  displayedVolumeQuality && typeof displayedVolumeQuality === 'object' ? (
                    <OutlinePlanQualityView report={displayedVolumeQuality} onChapterClick={jumpToChapterPlan} />
                  ) : (
                    <div className="border border-dashed border-cyan-200 bg-cyan-50/40 rounded-lg px-4 py-8 text-sm text-cyan-700">
                      当前卷还没有质检报告。可点击右上角重新质检。
                    </div>
                  )
                ) : (
                  <div className="border border-dashed border-gray-200 rounded-lg px-4 py-8 text-sm text-gray-500">
                    未选中卷：请先在左侧点击一个卷，或点击某卷下的篇/章后再查看本页。
                  </div>
                )}
              </div>
              <div className="xl:sticky xl:top-4">
                <div className="rounded-lg border border-gray-100 bg-white">
                  <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-100">
                    <h4 className="text-xs font-semibold text-gray-700">单卷质检时间线</h4>
                    <span className="text-[11px] text-gray-400">共 {volumeQualityRevisions.length} 条</span>
                  </div>
                  {selectedVolumeNode ? (
                    volumeQualityRevisions.length > 0 ? (
                      <div className="max-h-[70vh] overflow-auto divide-y divide-gray-100">
                        {volumeQualityRevisions.slice(0, 24).map(rev => (
                          <button
                            key={rev.id}
                            type="button"
                            onClick={() => setSelectedVolumeQualityRevisionId(rev.id)}
                            className={clsx(
                              'w-full text-left px-3 py-2 hover:bg-gray-50',
                              selectedVolumeQualityRevisionId === rev.id && 'bg-cyan-50',
                            )}
                          >
                            <div className="flex items-center justify-between gap-3 text-xs">
                              <div className="min-w-0">
                                <div className="font-medium text-gray-800 truncate">{rev.label}</div>
                                <div className="text-gray-400 mt-0.5">
                                  score {rev.meta?.quality_score ?? '-'} · {rev.meta?.quality_status ?? '-'} · {rev.created_at ? new Date(rev.created_at).toLocaleString() : ''}
                                </div>
                              </div>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                                {String(rev.id).slice(0, 8)}
                              </span>
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="px-3 py-4 text-xs text-gray-400">
                        当前卷还没有质检历史记录。
                      </div>
                    )
                  ) : (
                    <div className="px-3 py-4 text-xs text-gray-400">
                      选中卷后显示对应时间线。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : contentTab === 'revisions' ? (
          <div className="p-6 max-w-5xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-semibold text-gray-900">大纲历史快照</h3>
                <p className="text-xs text-gray-400 mt-1">保存版本、设置 A/B 基线并快速对比结构化变化</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCompareLatestTwo}
                  disabled={visibleRevisions.length < 2 || isComparing}
                  className="text-[11px] px-2 py-1 rounded border border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  最近两版对比
                </button>
                <button
                  type="button"
                  onClick={handleCreateManualSnapshot}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200"
                >
                  <BookOpen size={12} />
                  保存快照
                </button>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <h4 className="text-xs font-semibold text-gray-700">大纲历史快照</h4>
                <span className="text-[11px] text-gray-400">
                  {selectedVolumeId ? '当前卷' : '全书'} · 共 {visibleRevisions.length} 条
                </span>
              </div>
              {visibleRevisions.length > 0 ? (
                <div className="border border-gray-100 rounded-lg divide-y divide-gray-100 overflow-hidden">
                  {visibleRevisions.slice(0, 12).map(rev => (
                    <div key={rev.id} className="px-3 py-2 flex items-center justify-between gap-3 text-xs">
                      <div className="min-w-0">
                        <div className="font-medium text-gray-800 truncate">{rev.label}</div>
                        <div className="text-gray-400 mt-0.5">
                          {rev.source} · {rev.scope} · {rev.node_count ?? 0} 节点 · {rev.created_at ? new Date(rev.created_at).toLocaleString() : ''}
                        </div>
                      </div>
                      <div className="shrink-0 flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleSelectCompareBase(rev.id)}
                          className={clsx(
                            'text-[10px] px-1.5 py-0.5 rounded border',
                            compareBaseRevisionId === rev.id
                              ? 'bg-indigo-100 text-indigo-700 border-indigo-200'
                              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50',
                          )}
                        >
                          设 A
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCompareWithBase(rev.id)}
                          disabled={!compareBaseRevisionId || compareBaseRevisionId === rev.id || isComparing}
                          className="text-[10px] px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          与 A 对比
                        </button>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                          {String(rev.id).slice(0, 8)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border border-dashed border-gray-200 rounded-lg px-4 py-5 text-xs text-gray-400">
                  暂无快照。Graph 修复会自动保存修复前/后快照。
                </div>
              )}
            </div>
          </div>
        ) : selected ? (
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
            onJumpToChapterPlan={jumpToChapterPlan}
            onQualityCheck={() => handleDispatchOutlineQuality('volume', selected)}
          />
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 text-gray-400 gap-2 min-h-[200px]">
            <span className="text-3xl">📖</span>
            <p className="text-sm">选择左侧节点查看详情</p>
            <p className="text-xs text-gray-300 text-center max-w-sm">
              「<span className="text-indigo-400">全量生成</span>」：AI 从零生成完整大纲（卷+章节）。
              <br />
              「<span className="text-amber-400">全部展开</span>」：对已有卷补全章节计划。
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

      {isCompareDrawerOpen && compareResult && (
        <>
          <div
            className="fixed inset-0 bg-black/20 z-40"
            onClick={() => setIsCompareDrawerOpen(false)}
          />
          <div className="fixed top-0 right-0 h-full w-full max-w-xl bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col">
            <div className="px-4 py-3 border-b border-gray-100 flex items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-gray-900">快照快速比对</h4>
                <p className="text-[11px] text-gray-500 mt-1">
                  A：{compareBaseRevision?.label || String(compareBaseRevisionId).slice(0, 8)} · B：{compareTargetRevision?.label || String(compareTargetRevisionId).slice(0, 8)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsCompareDrawerOpen(false)}
                className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              >
                <X size={14} />
              </button>
            </div>

            <div className="px-4 py-3 border-b border-gray-100 grid grid-cols-4 gap-2 text-xs">
              <div className="rounded border border-green-100 bg-green-50 px-2 py-1.5">
                <div className="text-green-700 font-semibold">{compareResult.summary.added}</div>
                <div className="text-green-600/90">新增</div>
              </div>
              <div className="rounded border border-red-100 bg-red-50 px-2 py-1.5">
                <div className="text-red-700 font-semibold">{compareResult.summary.removed}</div>
                <div className="text-red-600/90">删除</div>
              </div>
              <div className="rounded border border-amber-100 bg-amber-50 px-2 py-1.5">
                <div className="text-amber-700 font-semibold">{compareResult.summary.updated}</div>
                <div className="text-amber-600/90">修改</div>
              </div>
              <div className="rounded border border-indigo-100 bg-indigo-50 px-2 py-1.5">
                <div className="text-indigo-700 font-semibold">{compareResult.summary.high}</div>
                <div className="text-indigo-600/90">高风险</div>
              </div>
            </div>

            <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1 text-xs">
              {([
                ['high', '仅高风险'],
                ['structure', '结构变更'],
                ['content', '内容修改'],
                ['all', '全部'],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setCompareFilter(key)}
                  className={clsx(
                    'px-2 py-1 rounded border',
                    compareFilter === key
                      ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-auto px-4 py-3 space-y-2">
              {filteredCompareChanges.length === 0 ? (
                <div className="text-xs text-gray-400 border border-dashed border-gray-200 rounded-lg p-4 text-center">
                  当前筛选下没有变化。
                </div>
              ) : (
                filteredCompareChanges.map(change => (
                  <div key={`${change.changeType}-${change.nodeId}`} className="border border-gray-100 rounded-lg p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-gray-800 truncate">{change.title}</div>
                        <div className="text-[11px] text-gray-400 truncate mt-0.5">{change.path}</div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className={clsx(
                          'text-[10px] px-1.5 py-0.5 rounded',
                          change.changeType === 'added'
                            ? 'bg-green-100 text-green-700'
                            : change.changeType === 'removed'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-amber-100 text-amber-700',
                        )}>
                          {change.changeType === 'added' ? '新增' : change.changeType === 'removed' ? '删除' : '修改'}
                        </span>
                        <span className={clsx(
                          'text-[10px] px-1.5 py-0.5 rounded',
                          change.severity === 'high'
                            ? 'bg-rose-100 text-rose-700'
                            : change.severity === 'medium'
                              ? 'bg-orange-100 text-orange-700'
                              : 'bg-gray-100 text-gray-600',
                        )}>
                          {change.severity}
                        </span>
                      </div>
                    </div>
                    {change.fields && change.fields.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {change.fields.slice(0, 4).map(field => (
                          <div key={field.field} className="text-[11px] rounded bg-gray-50 border border-gray-100 p-2">
                            <div className="text-gray-500">{FIELD_LABEL[field.field] || field.field}</div>
                            <div className="text-red-500 mt-0.5 line-clamp-2">- {field.before}</div>
                            <div className="text-green-600 mt-0.5 line-clamp-2">+ {field.after}</div>
                          </div>
                        ))}
                        {change.fields.length > 4 && (
                          <div className="text-[10px] text-gray-400">
                            还有 {change.fields.length - 4} 项字段变化...
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

      {/* 修复确认弹窗：替代 window.confirm，展示质检摘要 + 修复配置 */}
      <RepairConfirmModal
        open={repairModalOpen}
        onClose={() => setRepairModalOpen(false)}
        onConfirm={handleRepairConfirm}
        scope={repairModalScope}
        volumeTitle={repairModalVolumeNode?.title}
        qualityReport={
          repairModalScope === 'volume'
            ? (displayedVolumeQuality ?? undefined)
            : (displayedBookQuality ?? undefined)
        }
        value={repairConfig}
        onChange={setRepairConfig}
      />
    </div>
  )
}

// ── NodeDetailPanel ────────────────────────────────────────

function NodeDetailPanel({
  node, projectId, onOpenChapter, onSaved, onAICommitDone, onJumpToChapterPlan, onQualityCheck,
}: {
  node: OutlineNode
  projectId: string
  onOpenChapter: () => void
  onSaved: (updated: OutlineNode) => void
  onAICommitDone: () => void
  onJumpToChapterPlan: (chapterNumber: number) => void
  onQualityCheck: () => void
}) {
  const { characters, storyLines } = useAppStore()
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'chapter' | 'scene' | 'quality' | 'ai'>('overview')
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
    // P2 新增
    pov_character_id: node.pov_character_id ?? undefined,
    character_screen_time: node.character_screen_time ?? {},
  })

  useEffect(() => {
    setActiveTab('overview')
    // 重置表单（包含 P2 新字段）
    setForm({
      title: node.title ?? '',
      summary: node.summary ?? '',
      hook: node.hook ?? '',
      highlight: node.highlight ?? '',
      conflict: node.conflict ?? '',
      power_milestone: node.power_milestone ?? '',
      emotional_tone: node.emotional_tone ?? '',
      involved_character_ids: (node.involved_character_ids ?? []).map(String),
      storyline_ids: (node.storyline_ids ?? []).map(String),
      pov_character_id: node.pov_character_id ?? undefined,
      character_screen_time: node.character_screen_time ?? {},
    })
  }, [node.id])

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
      // 章节节点才传新字段，避免干扰卷节点
      if (node.node_type === 'chapter_plan') {
        payload.power_milestone = form.power_milestone || null
        payload.emotional_tone = form.emotional_tone || null
        payload.involved_character_ids = form.involved_character_ids
        payload.storyline_ids = form.storyline_ids
        // P2 新增
        payload.pov_character_id = form.pov_character_id || null
        payload.character_screen_time = form.character_screen_time || {}
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

  const volumeOutlineQuality = isExpandable
    ? (node.extra?.outline_quality as OutlinePlanQualityReport | undefined)
    : undefined

  const tabs = [
    { key: 'overview' as const, label: '基础' },
    ...(node.node_type === 'chapter_plan' ? [{ key: 'chapter' as const, label: '章节要素' }] : []),
    ...(node.node_type === 'chapter_plan' ? [{ key: 'scene' as const, label: '分场蓝图' }] : []),
    ...(isExpandable ? [{ key: 'quality' as const, label: '单卷质检' }] : []),
    ...(isExpandable ? [{ key: 'ai' as const, label: 'AI 展开' }] : []),
  ]

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
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded font-medium',
            node.node_type === 'volume' ? 'bg-amber-100 text-amber-700' :
            node.node_type === 'arc'    ? 'bg-blue-100 text-blue-700' :
                                          'bg-gray-100 text-gray-600'
          )}>
            {{ volume: '卷', arc: '旧篇', chapter_plan: '章' }[node.node_type]}
          </span>
          <h3 className="font-semibold text-gray-800 text-base truncate max-w-xs">
            {editing ? '编辑节点' : node.title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {!editing && isExpandable && (
            <button onClick={onQualityCheck} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 border border-indigo-100">
              <Check size={12} />单卷质检
            </button>
          )}
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

      <div className="flex items-center gap-1 border-b border-gray-100 mb-5 overflow-x-auto">
        {tabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'px-3 py-2 text-xs font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              activeTab === tab.key
                ? 'border-amber-500 text-amber-700'
                : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-200',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
      <div className="space-y-4">
        <Field label="标题" value={form.title} editing={editing} onChange={v => setForm(f => ({ ...f, title: v }))} singleLine />
        <Field label="情节摘要" sublabel="删掉会损失什么" value={form.summary} editing={editing} onChange={v => setForm(f => ({ ...f, summary: v }))} />
        <Field label="钩子 / 悬念" sublabel="读者最想知道答案的核心问题" value={form.hook} editing={editing} onChange={v => setForm(f => ({ ...f, hook: v }))} />
        <Field label="燃点 / 高潮" sublabel="情绪最高点" value={form.highlight} editing={editing} onChange={v => setForm(f => ({ ...f, highlight: v }))} />
        <Field label="核心冲突" sublabel="不可调和的矛盾" value={form.conflict} editing={editing} onChange={v => setForm(f => ({ ...f, conflict: v }))} />
      </div>
      )}

      {activeTab === 'chapter' && node.node_type === 'chapter_plan' && (
        <div className="space-y-4">
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

          {/* P2 新增：主要 POV */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Users size={12} className="text-purple-500 shrink-0" />
              <label className="text-xs font-medium text-gray-600">主要 POV</label>
              <span className="text-[10px] text-gray-400">本章强制视点角色</span>
            </div>
            {editing ? (
              <div className="flex flex-wrap gap-1.5">
                {characters.map(c => {
                  const selected = form.pov_character_id === String(c.id)
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setForm(f => ({ ...f, pov_character_id: selected ? undefined : String(c.id) }))}
                      className={clsx(
                        'text-xs px-2.5 py-1 rounded-full border transition-all',
                        selected
                          ? 'bg-purple-500 border-purple-500 text-white'
                          : 'border-gray-200 text-gray-600 hover:border-purple-300 hover:text-purple-600',
                      )}
                    >
                      {c.name}
                      {c.current_realm && <span className="ml-1 opacity-70 text-[10px]">{c.current_realm}</span>}
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm">
                {form.pov_character_id ? (
                  (() => {
                    const povChar = characters.find(x => String(x.id) === form.pov_character_id)
                    return povChar ? (
                      <span className="px-2.5 py-1 rounded-full bg-purple-50 border border-purple-200 text-purple-700 text-xs">
                        {povChar.name}
                      </span>
                    ) : <span className="text-gray-400 italic">—</span>
                  })()
                ) : (
                  <span className="text-xs text-gray-400 italic">未指定（默认全知）</span>
                )}
              </div>
            )}
          </div>

          {/* P2 新增：戏份预算 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Target size={12} className="text-orange-500 shrink-0" />
              <label className="text-xs font-medium text-gray-600">戏份预算</label>
              <span className="text-[10px] text-gray-400">各角色本章出镜占比</span>
            </div>
            {editing ? (
              <div className="space-y-2 text-sm">
                {characters.map(c => {
                  const pct = (form.character_screen_time as any)?.[String(c.id)] ?? 0
                  return (
                    <div key={c.id} className="flex items-center gap-3">
                      <div className="w-20 truncate text-gray-600">{c.name}</div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={5}
                        value={pct}
                        onChange={e => {
                          const val = parseInt(e.target.value)
                          setForm(f => ({
                            ...f,
                            character_screen_time: {
                              ...(f.character_screen_time as any),
                              [String(c.id)]: val
                            }
                          }))
                        }}
                        className="flex-1"
                      />
                      <div className="w-10 text-right text-gray-600">{pct}%</div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm space-y-1">
                {form.character_screen_time && Object.keys(form.character_screen_time).length > 0 ? (
                  Object.entries(form.character_screen_time as Record<string, number>).map(([id, pct]) => {
                    const c = characters.find(x => String(x.id) === id)
                    return c ? (
                      <div key={id} className="flex items-center gap-2 text-xs">
                        <span className="text-gray-600 w-16 truncate">{c.name}</span>
                        <div className="flex-1 h-1.5 bg-gray-200 rounded">
                          <div className="h-1.5 bg-orange-400 rounded" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="w-8 text-right text-gray-600">{pct}%</span>
                      </div>
                    ) : null
                  })
                ) : (
                  <span className="text-xs text-gray-400 italic">未设置戏份预算</span>
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
        </div>
      )}

      {activeTab === 'quality' && isExpandable && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold text-indigo-900">本卷 / 本篇大纲质检</h4>
            <button onClick={onQualityCheck} className="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 border border-indigo-100">
              <Check size={12} />重新质检
            </button>
          </div>
          {volumeOutlineQuality && typeof volumeOutlineQuality === 'object' ? (
            <OutlinePlanQualityView report={volumeOutlineQuality} onChapterClick={onJumpToChapterPlan} />
          ) : (
            <div className="border border-dashed border-indigo-200 bg-indigo-50/40 rounded-lg px-4 py-6 text-sm text-indigo-700">
              当前节点还没有单卷质检报告。
            </div>
          )}
        </div>
      )}

      {activeTab === 'ai' && isExpandable && (
        <OutlineAIPanel node={node} projectId={projectId} onCommitDone={onAICommitDone} />
      )}

      {activeTab === 'scene' && node.node_type === 'chapter_plan' && (
        <ScenePanel
          projectId={projectId}
          outlineNodeId={node.id}
          nodeTitle={node.title ?? ''}
          nodeSummary={node.summary ?? ''}
        />
      )}

      {activeTab === 'overview' && node.node_type === 'chapter_plan' && (
        <button onClick={onOpenChapter} className="mt-5 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm rounded-lg">
          打开并切换到该章节
        </button>
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
