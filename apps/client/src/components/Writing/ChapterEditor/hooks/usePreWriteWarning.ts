/**
 * usePreWriteWarning.ts — 写前预警 hook
 *
 * 职责：封装写前预警的全部状态（warnLoading / warnResult / warnHistory /
 * selectedWarnRecordId）、数据加载、门控队列同步与 API 调用。
 *
 * 依赖外部：aiApi、aiBackendRoute、parsePreWriteWarningHistoryPayload、
 * normalizePreWriteWarnResult（均从父包导入）。
 * 不依赖 store —— 只读取 aiBackendRoute 通过 useAppStore.getState()。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { aiApi } from '../../../../api/client'
import { useAppStore, modelProfileFromRoute, llmProviderIdFromRoute } from '../../../../store'
import type { OutlineNode } from '../../../../types'
import type { PreWriteWarnResult, PreWriteWarnHistoryRow } from '../types'
import { parsePreWriteWarningHistoryPayload, normalizePreWriteWarnResult } from '../utils'

// GenTask 最小接口（避免循环依赖 store 完整类型）
interface GenTaskLike {
  projectId: string
  type: string
  params?: { chapterId?: string }
  progress?: Array<{ step: string; done?: boolean; error?: boolean }>
}

interface UsePreWriteWarningOptions {
  projectId: string
  chapterId: string
  chapterSortOrder: number | null
  chapterTitle: string
  outlineNode?: OutlineNode
  /** 当前侧栏 tab（用于判断是否需要拉取历史） */
  contextTab: string
  /** 全局生成队列（用于检测门控写前预警完成事件） */
  genQueue: GenTaskLike[]
  /** 写前预警触发后需要打开侧栏并切换到 warn Tab */
  onNavigateToWarnTab: () => void
}

export interface UsePreWriteWarningReturn {
  warnLoading: boolean
  warnResult: PreWriteWarnResult | null
  setWarnResult: React.Dispatch<React.SetStateAction<PreWriteWarnResult | null>>
  warnHistory: PreWriteWarnHistoryRow[]
  setWarnHistory: React.Dispatch<React.SetStateAction<PreWriteWarnHistoryRow[]>>
  selectedWarnRecordId: string | null
  setSelectedWarnRecordId: React.Dispatch<React.SetStateAction<string | null>>
  /** 主动调用 AI 写前预警 API，写入 warnResult 并追加 warnHistory */
  runPreWriteWarning: () => Promise<void>
  /** 从服务端拉取本章预警历史列表 */
  refreshWarnHistoryFromServer: () => void
}

/**
 * 写前预警数据管理 hook。
 *
 * @param options - 见 UsePreWriteWarningOptions
 * @returns 预警状态 + 操作函数，供 ChapterEditor/index.tsx 解构使用
 */
export function usePreWriteWarning({
  projectId,
  chapterId,
  chapterSortOrder,
  chapterTitle,
  outlineNode,
  contextTab,
  genQueue,
  onNavigateToWarnTab,
}: UsePreWriteWarningOptions): UsePreWriteWarningReturn {
  const [warnLoading, setWarnLoading] = useState(false)
  const [warnResult, setWarnResult] = useState<PreWriteWarnResult | null>(null)
  const [warnHistory, setWarnHistory] = useState<PreWriteWarnHistoryRow[]>([])
  const [selectedWarnRecordId, setSelectedWarnRecordId] = useState<string | null>(null)

  // ── 门控队列：检测写前预警步骤完成 ────────────────────────────────────────

  /**
   * 门控写作任务中「pre_warn」步骤是否已完成。
   * 用于在用户停留在写前预警 Tab 时自动刷新历史。
   */
  const gatedPreWarnDoneForChapter = useMemo(
    () =>
      genQueue.some(
        t =>
          t.projectId === projectId
          && t.type === 'gated_rewrite_chapter'
          && t.params?.chapterId === chapterId
          && (t.progress ?? []).some(p => p.step === 'pre_warn' && p.done && !p.error),
      ),
    [genQueue, projectId, chapterId],
  )
  const gatedPreWarnSyncedRef = useRef(false)

  // ── 数据加载 ─────────────────────────────────────────────────────────────

  /**
   * 从服务端拉取本章写前预警历史，写入 warnHistory。
   * 响应非数组时安全降级为空列表。
   */
  const refreshWarnHistoryFromServer = useCallback(() => {
    if (!chapterId || !projectId) return
    void aiApi.preWriteWarningHistory(projectId, chapterId).then((r) => {
      setWarnHistory(parsePreWriteWarningHistoryPayload(r.data))
    }).catch(() => {
      setWarnHistory([])
    })
  }, [chapterId, projectId])

  /** 打开 warn Tab 时自动拉取历史 */
  useEffect(() => {
    if (contextTab !== 'warn' || !chapterId || !projectId) return
    refreshWarnHistoryFromServer()
  }, [contextTab, chapterId, projectId, refreshWarnHistoryFromServer])

  /** 门控写前预警完成后自动刷新（用户可能已停在「预警」Tab） */
  useEffect(() => {
    if (!gatedPreWarnDoneForChapter) {
      gatedPreWarnSyncedRef.current = false
      return
    }
    if (gatedPreWarnSyncedRef.current) return
    gatedPreWarnSyncedRef.current = true
    refreshWarnHistoryFromServer()
  }, [gatedPreWarnDoneForChapter, refreshWarnHistoryFromServer])

  /** 有历史且当前无展示结果时，默认显示最新一条 */
  useEffect(() => {
    if (contextTab !== 'warn') return
    if (warnResult !== null) return
    const first = warnHistory[0]
    if (!first?.id) return
    setWarnResult(normalizePreWriteWarnResult(first.result))
    setSelectedWarnRecordId(first.id)
  }, [contextTab, warnHistory, warnResult])

  // ── 操作 ─────────────────────────────────────────────────────────────────

  /**
   * 调用写前预警 API。
   * 优先从 outlineNode 拼接本章计划摘要，降级用章节标题。
   * 成功后更新 warnResult + 刷新 warnHistory。
   */
  const runPreWriteWarning = async () => {
    setWarnLoading(true)
    onNavigateToWarnTab()
    const planSummary = outlineNode
      ? [
          outlineNode.summary && `概述：${outlineNode.summary}`,
          outlineNode.hook && `开篇钩子：${outlineNode.hook}`,
          outlineNode.conflict && `核心事件：${outlineNode.conflict}`,
          outlineNode.highlight && `章末方向：${outlineNode.highlight}`,
        ].filter(Boolean).join('\n')
      : `第${chapterSortOrder ?? '?'}章《${chapterTitle}》`
    try {
      const route = useAppStore.getState().aiBackendRoute
      const { data } = await aiApi.preWriteWarning(projectId, {
        chapter_id: chapterId,
        chapter_plan_summary: planSummary,
        chapter_number: chapterSortOrder ?? 0,
        model_profile: modelProfileFromRoute(route),
        llm_provider_id: llmProviderIdFromRoute(route),
      })
      setWarnResult(normalizePreWriteWarnResult(data))
      if (data.record_id) setSelectedWarnRecordId(data.record_id)
      void aiApi.preWriteWarningHistory(projectId, chapterId).then((r) => {
        setWarnHistory(parsePreWriteWarningHistoryPayload(r.data))
      }).catch(() => {})
    } catch {
      toast.error('写前预警请求失败')
    } finally {
      setWarnLoading(false)
    }
  }

  return {
    warnLoading,
    warnResult,
    setWarnResult,
    warnHistory,
    setWarnHistory,
    selectedWarnRecordId,
    setSelectedWarnRecordId,
    runPreWriteWarning,
    refreshWarnHistoryFromServer,
  }
}
