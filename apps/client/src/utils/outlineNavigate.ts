import type { OutlineNode } from '../types'

export function flattenChapterPlans(nodes: OutlineNode[]): OutlineNode[] {
  const out: OutlineNode[] = []
  function walk(ns: OutlineNode[]) {
    for (const n of ns) {
      if (n.node_type === 'chapter_plan') out.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

export function parseChapterNumberFromPlanTitle(title: string): number | undefined {
  const m = /^第(\d+)章/.exec((title || '').trim())
  return m ? parseInt(m[1], 10) : undefined
}

/** 在大纲树中按「第 N 章」标题查找章纲节点（全书连续编号） */
export function findChapterPlanByNumber(roots: OutlineNode[], num: number): OutlineNode | undefined {
  return flattenChapterPlans(roots).find(n => parseChapterNumberFromPlanTitle(n.title || '') === num)
}

export function collectAncestorIds(roots: OutlineNode[], targetId: string): string[] {
  function walk(ns: OutlineNode[], ancestors: string[]): string[] | null {
    for (const n of ns) {
      if (n.id === targetId) return ancestors
      if (n.children?.length) {
        const found = walk(n.children, [...ancestors, n.id])
        if (found) return found
      }
    }
    return null
  }
  return walk(roots, []) ?? []
}
