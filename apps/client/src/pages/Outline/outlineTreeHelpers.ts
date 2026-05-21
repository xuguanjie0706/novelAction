/**
 * @file 大纲树展示辅助
 */
import type { OutlineNode } from '../../types'

export const outlineTypeLabel = (t: OutlineNode['node_type']) =>
  ({ volume: '卷', arc: '旧篇', chapter_plan: '章' }[t])

export const outlineTypeColor = (t: OutlineNode['node_type']) =>
  ({
    volume: 'bg-amber-100 text-amber-700',
    arc: 'bg-blue-100 text-blue-700',
    chapter_plan: 'bg-gray-100 text-gray-600',
  }[t])

export function buildOutlineParentMap(nodes: OutlineNode[]) {
  const parentMap = new Map<string, string | undefined>()
  const walk = (node: OutlineNode, parentId?: string) => {
    parentMap.set(node.id, parentId)
    node.children?.forEach(child => walk(child, node.id))
  }
  nodes.forEach(root => walk(root, undefined))
  return parentMap
}

export function findVolumeIdForNode(
  selected: OutlineNode | null,
  outlineTree: OutlineNode[],
): string | null {
  if (!selected) return null
  if (selected.node_type === 'volume') return selected.id
  const nodeMap = new Map<string, OutlineNode>()
  const walk = (node: OutlineNode) => {
    nodeMap.set(node.id, node)
    node.children?.forEach(walk)
  }
  outlineTree.forEach(walk)
  const parentMap = buildOutlineParentMap(outlineTree)
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
