import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Check } from 'lucide-react'
import { chaptersApi, outlineApi, projectsApi } from '../../api/client'
import { useAppStore, toOutlineApiModelProfile, routeLlmProviderPayload } from '../../store'
import type { OutlineNode, OutlinePlanQualityReport } from '../../types'
import { collectAncestorIds, findChapterPlanByNumber } from '../../utils/outlineNavigate'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import RepairConfirmModal, { clampMaxRounds, clampMinScore } from '../../components/Outline/RepairConfirmModal'
import type { RepairConfig } from '../../components/Outline/RepairConfirmModal'
import { collectExpandableNodes } from '../../utils/outlineAiExpand'
import type { OutlineDiffResult } from './diffUtils'
import { useOutlineSnapshotCompare } from './useOutlineSnapshotCompare'
import { useOutlineQualityDerived } from './useOutlineQualityDerived'
import FullGenConfigModal from './FullGenConfigModal'
import BatchExpandConfigModal from './BatchExpandConfigModal'
import NodeDetailPanel from './NodeDetailPanel'
import OutlineCompareDrawer from './OutlineCompareDrawer'
import OutlineTreeSidebar from './OutlineTreeSidebar'
import BookQualityTab from './tabs/BookQualityTab'
import VolumeQualityTab from './tabs/VolumeQualityTab'
import RevisionsTab from './tabs/RevisionsTab'


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
  const [repairUseLinterSeed, setRepairUseLinterSeed] = useState(false)
  const [repairLinterMustFix, setRepairLinterMustFix] = useState<number[]>([])
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
    setRepairUseLinterSeed(false)
    setRepairLinterMustFix([])
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
        use_linter_seed: repairUseLinterSeed,
        ...(repairLinterMustFix.length
          ? { linter_must_fix_chapter_numbers: repairLinterMustFix }
          : {}),
      },
    })
    setRepairUseLinterSeed(false)
    setRepairLinterMustFix([])
    toast.success('已加入修复队列，右下角可查看进度')
  }

  const expandableCount = collectExpandableNodes(outlineTree).length

  const {
    selectedVolumeId,
    selectedVolumeNode,
    bookQualityRevisions,
    volumeQualityRevisions,
    displayedBookQuality,
    displayedVolumeQuality,
    visibleRevisions,
  } = useOutlineQualityDerived(
    selected,
    outlineTree,
    outlineRevisions,
    bookOutlineQuality,
    selectedBookQualityRevisionId,
    selectedVolumeQualityRevisionId,
    setSelectedVolumeQualityRevisionId,
  )

  const {
    handleSelectCompareBase,
    handleCompareWithBase,
    handleCompareLatestTwo,
  } = useOutlineSnapshotCompare(
    projectId,
    compareBaseRevisionId,
    visibleRevisions,
    setCompareBaseRevisionId,
    setCompareTargetRevisionId,
    setCompareResult,
    setCompareFilter,
    setIsCompareDrawerOpen,
    setIsComparing,
  )

  const filteredCompareChanges = (compareResult?.changes || []).filter(change => {
    if (compareFilter === 'all') return true
    if (compareFilter === 'high') return change.severity === 'high'
    if (compareFilter === 'structure') return change.changeType === 'added' || change.changeType === 'removed'
    return change.changeType === 'updated'
  })

  const compareBaseRevision = outlineRevisions.find(r => r.id === compareBaseRevisionId)
  const compareTargetRevision = outlineRevisions.find(r => r.id === compareTargetRevisionId)

  return (
    <div className="flex h-full">
      <OutlineTreeSidebar
        projectId={projectId}
        outlineTree={outlineTree}
        expanded={expanded}
        selected={selected}
        aiBackendRoute={aiBackendRoute}
        onToggleExpand={toggleExpand}
        onSelect={setSelected}
        onOpenChapter={openChapterFromNode}
        onAddChild={handleAddChild}
        onDelete={handleDelete}
        onReload={reload}
        onClearSelection={() => setSelected(null)}
        onShowFullGenModal={() => setShowFullGenModal(true)}
      />

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
          <BookQualityTab
            displayedBookQuality={displayedBookQuality}
            bookQualityRevisions={bookQualityRevisions}
            selectedBookQualityRevisionId={selectedBookQualityRevisionId}
            onSelectRevision={setSelectedBookQualityRevisionId}
            onDispatchQuality={() => handleDispatchOutlineQuality('book')}
            onDispatchRepair={() => handleDispatchOutlineRepair('book')}
            onChapterClick={jumpToChapterPlan}
          />
        ) : contentTab === 'volumeQuality' ? (
          <VolumeQualityTab
            selectedVolumeNode={selectedVolumeNode}
            displayedVolumeQuality={displayedVolumeQuality}
            volumeQualityRevisions={volumeQualityRevisions}
            selectedVolumeQualityRevisionId={selectedVolumeQualityRevisionId}
            onSelectRevision={setSelectedVolumeQualityRevisionId}
            onDispatchQuality={node => handleDispatchOutlineQuality('volume', node)}
            onDispatchRepair={node => handleDispatchOutlineRepair('volume', node)}
            onChapterClick={jumpToChapterPlan}
          />
        ) : contentTab === 'revisions' ? (
          projectId ? (
            <RevisionsTab
              projectId={projectId}
              selectedVolumeId={selectedVolumeId}
              visibleRevisions={visibleRevisions}
              compareBaseRevisionId={compareBaseRevisionId}
              isComparing={isComparing}
              onCompareLatestTwo={handleCompareLatestTwo}
              onSelectCompareBase={handleSelectCompareBase}
              onCompareWithBase={handleCompareWithBase}
              onReloadRevisions={reloadRevisions}
            />
          ) : null
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
            onRelintDone={reload}
            onRequestRepairFromLinter={(chapters) => {
              setRepairUseLinterSeed(true)
              setRepairLinterMustFix(chapters)
              handleDispatchOutlineRepair('volume', selected)
            }}
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

      <OutlineCompareDrawer
        open={isCompareDrawerOpen}
        compareResult={compareResult}
        compareFilter={compareFilter}
        onFilterChange={setCompareFilter}
        onClose={() => setIsCompareDrawerOpen(false)}
        compareBaseRevisionId={compareBaseRevisionId}
        compareTargetRevisionId={compareTargetRevisionId}
        compareBaseRevision={compareBaseRevision}
        compareTargetRevision={compareTargetRevision}
        filteredChanges={filteredCompareChanges}
      />

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

