/**
 * useDabaiWritePage — 大白文写作页：大纲章纲 + Chapter 同步与选中态
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { chaptersApi, outlineApi, powerSystemsApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Chapter, OutlineNode } from '../../types'
import { buildChapterByNodeId, resolveActiveChapterId } from '../writeChapterUtils'
import { dabaiBeatFromOutlineNode, isDabaiOutlineNode } from '../../utils/dabaiOutlineDisplay'

function findNode(tree: OutlineNode[], id: string): OutlineNode | undefined {
  for (const n of tree) {
    if (n.id === id) return n
    if (n.children?.length) {
      const f = findNode(n.children, id)
      if (f) return f
    }
  }
}

function collectChapterPlans(nodes: OutlineNode[], out: OutlineNode[] = []): OutlineNode[] {
  for (const n of nodes) {
    if (n.node_type === 'chapter_plan' && isDabaiOutlineNode(n)) out.push(n)
    if (n.children?.length) collectChapterPlans(n.children, out)
  }
  return out.sort((a, b) => a.sort_order - b.sort_order)
}

/** 卷分组：volume 节点 → 其子树内的 dabai 章纲；卷外散章归入 volume=null 组。 */
export interface DabaiVolumeGroup {
  volume: OutlineNode | null
  plans: OutlineNode[]
}

function groupPlansByVolume(tree: OutlineNode[]): DabaiVolumeGroup[] {
  const groups: DabaiVolumeGroup[] = []
  const seen = new Set<string>()
  const volumes: OutlineNode[] = []
  const walkVolumes = (nodes: OutlineNode[]) => {
    for (const n of nodes) {
      if (n.node_type === 'volume') volumes.push(n)
      else if (n.children?.length) walkVolumes(n.children)
    }
  }
  walkVolumes(tree)
  for (const vol of volumes.sort((a, b) => a.sort_order - b.sort_order)) {
    const plans = collectChapterPlans(vol.children ?? [])
    plans.forEach(p => seen.add(p.id))
    if (plans.length) groups.push({ volume: vol, plans })
  }
  const orphan = collectChapterPlans(tree).filter(p => !seen.has(p.id))
  if (orphan.length) groups.push({ volume: null, plans: orphan })
  return groups
}

export function useDabaiWritePage(projectId: string | undefined) {
  const {
    chapters, setChapters, upsertChapter,
    activeChapterId, setActiveChapterId,
    outlineTree, setOutlineTree,
  } = useAppStore()

  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [syncing, setSyncing] = useState(false)
  const [realmLevels, setRealmLevels] = useState<Array<{ rank?: number; name?: string }>>([])

  const loadData = useCallback(() => {
    if (!projectId) return
    setLoadState('loading')
    Promise.all([
      outlineApi.getTree(projectId),
      chaptersApi.list(projectId),
      powerSystemsApi.list(projectId).catch(() => ({ data: [] as { levels?: { rank?: number; name?: string }[] }[] })),
    ])
      .then(([oRes, cRes, psRes]) => {
        setOutlineTree(oRes.data)
        setChapters(cRes.data)
        const levels = (psRes.data as { levels?: { rank?: number; name?: string }[] }[]).flatMap(
          (ps: { levels?: { rank?: number; name?: string }[] }) => ps.levels ?? [],
        )
        setRealmLevels(levels)
        const plans = collectChapterPlans(oRes.data)
        const byNode = buildChapterByNodeId(cRes.data)
        const firstWithCh = plans.find(p => byNode.has(p.id))
        const firstPlan = plans[0]
        const defaultCh = firstWithCh ? byNode.get(firstWithCh.id) : firstPlan ? byNode.get(firstPlan.id) : null
        if (defaultCh) setActiveChapterId(defaultCh.id)
        else if (cRes.data.length) setActiveChapterId(cRes.data[0].id)
        setLoadState('ready')
      })
      .catch(() => {
        setLoadState('error')
        toast.error('数据加载失败')
      })
  }, [projectId, setChapters, setOutlineTree, setActiveChapterId])

  useEffect(() => { loadData() }, [loadData])

  const chapterByNodeId = useMemo(() => buildChapterByNodeId(chapters), [chapters])
  const chapterPlans = useMemo(() => collectChapterPlans(outlineTree), [outlineTree])
  const unsyncedCount = useMemo(
    () => chapterPlans.filter(p => !chapterByNodeId.has(p.id)).length,
    [chapterPlans, chapterByNodeId],
  )
  const nextSortOrder = useMemo(
    () => (chapters.length ? Math.max(...chapters.map(ch => ch.sort_order)) + 1 : 0),
    [chapters],
  )

  useEffect(() => {
    if (loadState !== 'ready') return
    const resolved = resolveActiveChapterId(chapters, activeChapterId)
    if (resolved && resolved !== activeChapterId) setActiveChapterId(resolved)
  }, [chapters, activeChapterId, loadState, setActiveChapterId])

  useEffect(() => {
    if (!projectId || !activeChapterId || loadState !== 'ready') return
    chaptersApi.get(projectId, activeChapterId)
      .then(r => upsertChapter(r.data))
      .catch(() => {})
  }, [projectId, activeChapterId, loadState, upsertChapter])

  const openPlan = useCallback(async (plan: OutlineNode) => {
    if (!projectId) return
    const existing = chapterByNodeId.get(plan.id)
    if (existing) {
      setActiveChapterId(existing.id)
      return
    }
    try {
      const res = await chaptersApi.create(projectId, {
        title: plan.title,
        outline_node_id: plan.id,
        sort_order: plan.sort_order ?? nextSortOrder,
      })
      upsertChapter(res.data)
      setActiveChapterId(res.data.id)
    } catch {
      toast.error('创建章节失败')
    }
  }, [projectId, chapterByNodeId, nextSortOrder, upsertChapter, setActiveChapterId])

  const syncAll = useCallback(async () => {
    if (!projectId) return
    setSyncing(true)
    try {
      let created = 0
      for (const plan of chapterPlans) {
        if (chapterByNodeId.has(plan.id)) continue
        const res = await chaptersApi.create(projectId, {
          title: plan.title,
          outline_node_id: plan.id,
          sort_order: plan.sort_order ?? nextSortOrder + created,
        })
        upsertChapter(res.data)
        created++
      }
      toast.success(created > 0 ? `已同步 ${created} 章写作入口` : '全部章节已就绪')
    } catch {
      toast.error('同步失败')
    } finally {
      setSyncing(false)
    }
  }, [projectId, chapterPlans, chapterByNodeId, nextSortOrder, upsertChapter])

  const activeChapter = chapters.find(c => c.id === activeChapterId)
  const activePlan = activeChapter?.outline_node_id
    ? findNode(outlineTree, activeChapter.outline_node_id)
    : undefined
  const activeBeat = activePlan
    ? dabaiBeatFromOutlineNode(activePlan, (activePlan.sort_order ?? 0) + 1, { realmLevels })
    : null

  const planRows = useMemo(
    () => chapterPlans.map(plan => ({
      plan,
      chapter: chapterByNodeId.get(plan.id),
      beat: dabaiBeatFromOutlineNode(plan, (plan.sort_order ?? 0) + 1, { realmLevels }),
    })),
    [chapterPlans, chapterByNodeId, realmLevels],
  )

  /** 卷分组视图（侧栏折叠导航用），行结构与 planRows 一致 */
  const volumeGroups = useMemo(() => {
    const rowByPlanId = new Map(planRows.map(r => [r.plan.id, r]))
    return groupPlansByVolume(outlineTree).map(g => ({
      volume: g.volume,
      rows: g.plans.map(p => rowByPlanId.get(p.id)).filter((r): r is typeof planRows[number] => !!r),
    }))
  }, [outlineTree, planRows])

  return {
    loadState,
    syncing,
    unsyncedCount,
    planRows,
    volumeGroups,
    activeChapter,
    activePlan,
    activeBeat,
    openPlan,
    syncAll,
    reload: loadData,
  }
}
