/**
 * useChapterContextUi — 侧栏 Tab / 专注模式 / 状态下拉 UI 状态
 */
import { useEffect, useRef, useState } from 'react'
import type { OutlineNode } from '../../../../types'

export type ChapterContextTab = 'plan' | 'scene' | 'debrief' | 'chindex' | 'warn'

export function useChapterContextUi(
  outlineNode: OutlineNode | undefined,
  onFocusModeChange?: (v: boolean) => void,
) {
  const [contextOpen, setContextOpen] = useState(!!outlineNode)
  const [contextTab, setContextTab] = useState<ChapterContextTab>('plan')
  const [focusMode, setFocusMode] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const statusRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setContextOpen(!!outlineNode) }, [outlineNode?.id])
  useEffect(() => { onFocusModeChange?.(focusMode) }, [focusMode, onFocusModeChange])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) setStatusOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return {
    contextOpen,
    setContextOpen,
    contextTab,
    setContextTab,
    focusMode,
    setFocusMode,
    statusOpen,
    setStatusOpen,
    statusRef,
  }
}
