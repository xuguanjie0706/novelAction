/**
 * @file 大纲质检与快照派生数据
 */
import { useEffect, useMemo } from 'react'
import type { OutlineNode, OutlinePlanQualityReport } from '../../types'
import { findVolumeIdForNode } from './outlineTreeHelpers'

export function useOutlineQualityDerived(
  selected: OutlineNode | null,
  outlineTree: OutlineNode[],
  outlineRevisions: any[],
  bookOutlineQuality: OutlinePlanQualityReport | undefined,
  selectedBookQualityRevisionId: string | null,
  selectedVolumeQualityRevisionId: string | null,
  setSelectedVolumeQualityRevisionId: (id: string | null) => void,
) {
  const selectedVolumeId = findVolumeIdForNode(selected, outlineTree)

  const selectedVolumeNode = useMemo(() => {
    const map = new Map<string, OutlineNode>()
    const walk = (node: OutlineNode) => {
      map.set(node.id, node)
      node.children?.forEach(walk)
    }
    outlineTree.forEach(walk)
    return selectedVolumeId ? map.get(selectedVolumeId) : null
  }, [outlineTree, selectedVolumeId])

  const getQualityReportFromRevision = (rev: any): OutlinePlanQualityReport | undefined => {
    const report = rev?.meta?.quality_report
    return report && typeof report === 'object' ? report as OutlinePlanQualityReport : undefined
  }

  const qualityRevisions = outlineRevisions.filter(rev => rev.source === 'quality')
  const bookQualityRevisions = qualityRevisions.filter(rev => rev.scope === 'book')
  const volumeQualityRevisions = selectedVolumeId
    ? qualityRevisions.filter(rev => rev.scope === 'volume' && rev.volume_node_id === selectedVolumeId)
    : []

  const selectedBookQualityRevision = selectedBookQualityRevisionId
    ? bookQualityRevisions.find(rev => rev.id === selectedBookQualityRevisionId)
    : null
  const selectedVolumeQualityRevision = selectedVolumeQualityRevisionId
    ? volumeQualityRevisions.find(rev => rev.id === selectedVolumeQualityRevisionId)
    : null

  const selectedVolumeQuality = selectedVolumeNode?.extra?.outline_quality as OutlinePlanQualityReport | undefined
  const displayedBookQuality = getQualityReportFromRevision(selectedBookQualityRevision) || bookOutlineQuality
  const displayedVolumeQuality = getQualityReportFromRevision(selectedVolumeQualityRevision) || selectedVolumeQuality

  useEffect(() => {
    setSelectedVolumeQualityRevisionId(null)
  }, [selectedVolumeId, setSelectedVolumeQualityRevisionId])

  const snapshotRevisions = outlineRevisions.filter(rev =>
    ['manual', 'pre_repair', 'post_repair'].includes(rev.source),
  )
  const visibleRevisions = selectedVolumeId
    ? snapshotRevisions.filter(rev => rev.scope === 'volume' && rev.volume_node_id === selectedVolumeId)
    : snapshotRevisions

  return {
    selectedVolumeId,
    selectedVolumeNode,
    bookQualityRevisions,
    volumeQualityRevisions,
    displayedBookQuality,
    displayedVolumeQuality,
    visibleRevisions,
  }
}
