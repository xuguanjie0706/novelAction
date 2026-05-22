/**
 * @file useVolExpandBridge.ts
 * @description 管理「展开章纲」的跨层状态桥接逻辑。
 *
 * 职责：
 * - 维护 volExpandState（进度、错误、完成）。
 * - 在生成开始时自动选中卷节点、切换到「当前节点」视图。
 * - 在生成完成后记录 linterTabVolumeId，供 NodeDetailPanel 自动跳到「质检」Tab。
 * - 暴露 sidebarCallbacks 供透传给 OutlineTreeSidebar。
 * - 暴露 forceAccept(volumeNode) 供进度面板与质检面板调用「强制采用」。
 *
 * 依赖：
 * - setSelected / setContentTab 由 OutlinePage 传入（不持有 Zustand 直接引用）。
 */

import { useState, useCallback } from 'react'
import { outlineApi } from '../../api/client'
import type { OutlineNode } from '../../types'
import type { ProgressLine, ExpandEndResult } from '../../components/Outline/VolumeExpandButton'
import type { VolExpandState } from '../../components/Outline/VolExpandProgressPanel'

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Bridge {
  /** 当前展开进度状态；null 表示无正在进行或最近完成的展开 */
  volExpandState: VolExpandState | null
  /**
   * 若最近一次展开完成后用户还未切换节点，则等于该卷 id；
   * 用于让 NodeDetailPanel 初始显示「质检」Tab。
   */
  linterTabVolumeId: string | null
  /** 关闭进度面板（用户手动关闭） */
  dismissExpand: () => void
  /** 进度面板内「查看 & 修复」按钮回调 */
  viewLinter: () => void
  /**
   * 强制采用：清除 linter_blocked 并刷新卷节点。
   * 调用方（OutlinePage）负责在回调里刷新大纲树。
   *
   * @param volumeNode - 被阻断的卷节点（需要其 id 与当前 extra）
   * @param reload     - 刷新大纲树的回调
   */
  forceAccept: (volumeNode: OutlineNode, reload: () => void) => Promise<void>
  /** 传给 OutlineTreeSidebar 的三个回调 */
  sidebarCallbacks: {
    onVolExpandStart: (v: OutlineNode) => void
    onVolExpandProgress: (lines: ProgressLine[]) => void
    onVolExpandEnd: (v: OutlineNode, r: ExpandEndResult) => void
  }
}

interface Options {
  setSelected: (node: OutlineNode) => void
  setContentTab: (tab: 'node' | 'bookQuality' | 'volumeQuality' | 'revisions') => void
  setActiveNodeTab: (tab: 'linter') => void
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * 管理「展开章纲」跨层状态桥接。
 *
 * @param options.setSelected     - OutlinePage 的 setSelected
 * @param options.setContentTab   - OutlinePage 的 setContentTab
 * @param options.setActiveNodeTab - 触发 NodeDetailPanel 切换到指定 tab（通过 linterTabVolumeId 间接实现）
 */
export function useVolExpandBridge({
  setSelected,
  setContentTab,
}: Options): Bridge {
  const [volExpandState, setVolExpandState] = useState<VolExpandState | null>(null)
  const [linterTabVolumeId, setLinterTabVolumeId] = useState<string | null>(null)

  const onVolExpandStart = useCallback((v: OutlineNode) => {
    setSelected(v)
    setContentTab('node')
    setLinterTabVolumeId(null)
    setVolExpandState({
      volumeTitle: v.title ?? '未命名卷',
      running: true,
      progress: [],
      error: null,
      done: false,
      chapterCount: 0,
      linterBlocked: false,
    })
  }, [setSelected, setContentTab])

  const onVolExpandProgress = useCallback((lines: ProgressLine[]) => {
    setVolExpandState(s => s ? { ...s, progress: lines } : s)
  }, [])

  const onVolExpandEnd = useCallback((v: OutlineNode, r: ExpandEndResult) => {
    setVolExpandState(s => s
      ? { ...s, running: false, error: r.error, done: r.done, chapterCount: r.chapterCount, linterBlocked: r.linterBlocked }
      : s
    )
    if ((r.done || r.linterBlocked) && r.chapterCount > 0) {
      // 生成完成（含 linter 阻断）：记录 id，NodeDetailPanel 自动跳到「质检」Tab
      setLinterTabVolumeId(v.id)
    }
  }, [])

  /** 用户手动关闭进度面板 */
  const dismissExpand = useCallback(() => {
    setVolExpandState(null)
  }, [])

  /**
   * 进度面板内「查看 & 修复」——关闭进度面板；
   * NodeDetailPanel 已通过 linterTabVolumeId 切到质检 tab。
   */
  const viewLinter = useCallback(() => {
    setVolExpandState(null)
  }, [])

  /**
   * 强制采用：通过 PATCH outline node extra 清除 linter_blocked，
   * 然后调用 reload() 刷新大纲树使变更生效。
   */
  const forceAccept = useCallback(async (volumeNode: OutlineNode, reload: () => void) => {
    try {
      const newExtra = { ...(volumeNode.extra ?? {}), linter_blocked: false }
      await outlineApi.update(volumeNode.project_id as unknown as string, volumeNode.id, { extra: newExtra })
      setVolExpandState(null)
      setLinterTabVolumeId(null)
      reload()
    } catch {
      // 静默失败；OutlinePage 层可加 toast
      throw new Error('强制采用失败，请重试')
    }
  }, [])

  return {
    volExpandState,
    linterTabVolumeId,
    dismissExpand,
    viewLinter,
    forceAccept,
    sidebarCallbacks: {
      onVolExpandStart,
      onVolExpandProgress,
      onVolExpandEnd,
    },
  }
}
