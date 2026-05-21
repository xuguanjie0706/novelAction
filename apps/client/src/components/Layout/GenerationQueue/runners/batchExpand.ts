/**
 * @file 队列任务：批量展开大纲节点
 */
import type { GenTask, GenProgressItem } from '../../../../types'
import { formatApiError } from '../../../../utils/apiError'
import {
  fetchOutlineExpandResult,
  commitOutlineExpand,
} from '../../../../utils/outlineAiExpand'

export async function runBatchExpand(
  task: GenTask,
  pushProgress: (item: GenProgressItem) => void,
  onComplete: (msg: string) => void,
  onError: (msg: string) => void,
  signal: AbortSignal,
) {
  const { projectId, params } = task
  const nodes: Array<{ id: string; title: string }> = params.nodes ?? []
  const chapterCount: number = params.chapterCount ?? 60
  const modelProfile: 'default' | 'gemini' = params.modelProfile ?? 'default'
  const llmProviderId: string | undefined = params.llm_provider_id

  let successCount = 0
  for (let i = 0; i < nodes.length; i++) {
    if (signal.aborted) {
      onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
      return
    }
    const node = nodes[i]
    const stepLabel = `${node.title}（${i + 1}/${nodes.length}）`
    pushProgress({ step: i + 1, label: `正在展开 ${stepLabel}…`, done: false, error: false })
    try {
      const result = await fetchOutlineExpandResult(
        projectId,
        node.id,
        chapterCount,
        modelProfile,
        llmProviderId,
      )
      await commitOutlineExpand(projectId, node.id, result.chapters)
      pushProgress({ step: i + 1, label: `✓ ${stepLabel}，写入 ${result.chapters.length} 章`, done: true, error: false })
      successCount++
    } catch (e: any) {
      if (signal.aborted) {
        onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
        return
      }
      pushProgress({ step: i + 1, label: `✗ ${stepLabel} 失败：${formatApiError(e)}`, done: true, error: true })
    }
  }

  if (signal.aborted) {
    onComplete(`已取消（已成功 ${successCount}/${nodes.length} 个节点）`)
    return
  }
  onComplete(`批量展开完成：${successCount}/${nodes.length} 个节点成功`)
}

