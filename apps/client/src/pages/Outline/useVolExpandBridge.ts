/**
 * @file useVolExpandBridge.ts
 * @description 管理「展开章纲」的跨层状态桥接逻辑。
 *
 * 职责：
 * - 维护 volExpandState（进度、错误、完成）。
 * - 在生成开始时自动选中卷节点、切换到「当前节点」视图。
 * - 在生成完成后记录 linterTabVolumeId，供 NodeDetailPanel 自动跳到「章纲检测」Tab。
 * - 暴露 sidebarCallbacks 供透传给 OutlineTreeSidebar。
 *
 * 依赖：
 * - setSelected / setContentTab 由 OutlinePage 传入（不持有 Zustand 直接引用）。
 */

import { useState, useCallback } from 'react'
import type { OutlineNode } from '../../types'
import type { ProgressLine, ExpandEndResult } from '../../components/Outline/VolumeExpandButton'
import type { VolExpandState } from '../../components/Outline/VolExpandProgressPanel'

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Bridge {
  /** 当前展开进度状态；null 表示无正在进行或最近完成的展开 */
  volExpandState: VolExpandState | null
  /**
   * 若最近一次展开完成后用户还未切换节点，则等于该卷 id；
   * 用于让 NodeDetailPanel 初始显示「章纲检测」Tab。
   */
  linterTabVolumeId: string | null
  /** 关闭进度面板（用户手动关闭） */
  dismissExpand: () => void
  /** 进度面板内「查看检测结果」按钮回调 */
  viewLinter: () => void
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
    })
  }, [setSelected, setContentTab])

  const onVolExpandProgress = useCallback((lines: ProgressLine[]) => {
    setVolExpandState(s => s ? { ...s, progress: lines } : s)
  }, [])

  const onVolExpandEnd = useCallback((v: OutlineNode, r: ExpandEndResult) => {
    setVolExpandState(s => s
      ? { ...s, running: false, error: r.error, done: r.done, chapterCount: r.chapterCount }
      : s
    )
    if (r.done && !r.error) {
      // 生成成功：记录 id，NodeDetailPanel 收到后会自动切到 linter tab
      setLinterTabVolumeId(v.id)
    }
  }, [])

  /** 用户手动关闭进度面板 */
  const dismissExpand = useCallback(() => {
    setVolExpandState(null)
  }, [])

  /**
   * 进度面板内「查看检测结果」—— 面板关闭后 NodeDetailPanel 已在 linter tab，
   * 此处只需关闭进度面板即可（linterTabVolumeId 已设置）。
   */
  const viewLinter = useCallback(() => {
    setVolExpandState(null)
  }, [])

  return {
    volExpandState,
    linterTabVolumeId,
    dismissExpand,
    viewLinter,
    sidebarCallbacks: {
      onVolExpandStart,
      onVolExpandProgress,
      onVolExpandEnd,
    },
  }
}
