/**
 * @file 大纲快照结构化 diff
 */
export type RevisionSnapshotNode = {
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

export type OutlineDiffField = {
  field: string
  before: string
  after: string
}

export type OutlineDiffItem = {
  changeType: 'added' | 'removed' | 'updated'
  severity: 'high' | 'medium' | 'low'
  nodeId: string
  nodeType: string
  title: string
  path: string
  fields?: OutlineDiffField[]
}

export type OutlineDiffResult = {
  summary: {
    added: number
    removed: number
    updated: number
    high: number
  }
  changes: OutlineDiffItem[]
}

export const DIFF_FIELDS: Array<keyof RevisionSnapshotNode> = [
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

export const FIELD_LABEL: Record<string, string> = {
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

export const compareSnapshots = (baseNodes: RevisionSnapshotNode[], targetNodes: RevisionSnapshotNode[]): OutlineDiffResult => {
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
