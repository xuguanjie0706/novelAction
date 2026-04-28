import type { OutlineNode } from '../types'

/** 与 OutlineAIPanel / 后端约定一致 */
export interface ExpandChapterCard {
  number: number
  title: string
  opening_hook: string
  core_event: string
  character_change: string
  foreshadow: string
  end_hook: string
  pacing: 'fast' | 'medium' | 'slow'
  word_estimate: number
}

export interface ExpandResult {
  volume_analysis?: {
    emotional_arc: string
    core_question: string
    pacing_rhythm: string
  }
  chapters: ExpandChapterCard[]
}

/** 收集尚未挂「章节计划」子节点的卷/篇（有篇先扩篇，不重复扩卷） */
export function collectExpandableNodes(tree: OutlineNode[]): OutlineNode[] {
  const out: OutlineNode[] = []

  const walk = (n: OutlineNode) => {
    if (n.node_type === 'chapter_plan') return

    const children = n.children ?? []
    const hasDirectChapters = children.some((c) => c.node_type === 'chapter_plan')
    const hasArcs = children.some((c) => c.node_type === 'arc')

    if (n.node_type === 'volume') {
      if (hasArcs) {
        children.forEach(walk)
        return
      }
      if (!hasDirectChapters) out.push(n)
      return
    }

    if (n.node_type === 'arc') {
      if (!hasDirectChapters) out.push(n)
      return
    }
  }

  tree.forEach(walk)
  return out
}

export async function fetchOutlineExpandResult(
  projectId: string,
  nodeId: string,
  chapterCount: number,
  modelProfile: 'default' | 'gemini',
  llmProviderId?: string,
): Promise<ExpandResult> {
  const body: Record<string, unknown> = {
    node_id: nodeId,
    chapter_count: chapterCount,
    model_profile: modelProfile,
  }
  if (llmProviderId) body.llm_provider_id = llmProviderId
  const res = await fetch(`/api/v1/projects/${projectId}/outline/ai-expand`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (!raw) continue
      try {
        const evt = JSON.parse(raw)
        if (evt.event === 'result' && evt.data?.chapters?.length) {
          return evt.data as ExpandResult
        }
        if (evt.event === 'error') {
          throw new Error(evt.message || 'AI 生成失败')
        }
      } catch (e: any) {
        if (e instanceof SyntaxError) continue
        throw e
      }
    }
  }

  throw new Error('未收到完整生成结果')
}

export async function commitOutlineExpand(
  projectId: string,
  parentNodeId: string,
  chapters: ExpandChapterCard[]
): Promise<void> {
  const res = await fetch(`/api/v1/projects/${projectId}/outline/ai-expand/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parent_node_id: parentNodeId,
      chapters,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
}
