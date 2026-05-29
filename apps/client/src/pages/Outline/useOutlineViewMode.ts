/**
 * @file 大纲页视图模式（经典 / 编剧台）与卷聚焦
 */
import { useCallback, useState, type Dispatch, type SetStateAction } from 'react'
import type { OutlineNode } from '../../types'

export type OutlineViewMode = 'classic' | 'intuitive'

function readStoredMode(): OutlineViewMode {
  try {
    return localStorage.getItem('outline-view-mode') === 'intuitive' ? 'intuitive' : 'classic'
  } catch {
    return 'classic'
  }
}

export function useOutlineViewMode(
  outlineTree: OutlineNode[],
  selected: OutlineNode | null,
  selectedVolumeNode: OutlineNode | null | undefined,
  setSelected: (n: OutlineNode) => void,
  setExpanded: Dispatch<SetStateAction<Set<string>>>,
) {
  const [outlineViewMode, setOutlineViewMode] = useState<OutlineViewMode>(readStoredMode)

  const volumeNodes = outlineTree.filter(n => n.node_type === 'volume')
  const intuitiveVolume =
    selectedVolumeNode ??
    (selected?.node_type === 'volume' ? selected : null) ??
    volumeNodes[0] ??
    null

  const persistViewMode = useCallback((mode: OutlineViewMode) => {
    setOutlineViewMode(mode)
    try {
      localStorage.setItem('outline-view-mode', mode)
    } catch { /* ignore */ }
    if (mode === 'intuitive' && intuitiveVolume) {
      setSelected(intuitiveVolume)
      setExpanded(prev => new Set([...prev, intuitiveVolume.id]))
    }
  }, [intuitiveVolume, setSelected, setExpanded])

  return {
    outlineViewMode,
    persistViewMode,
    volumeNodes,
    intuitiveVolume,
  }
}
