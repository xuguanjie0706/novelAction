/**
 * @file 大纲快照对比操作
 */
import { useCallback } from 'react'
import toast from 'react-hot-toast'
import { outlineApi } from '../../api/client'
import {
  compareSnapshots,
  type RevisionSnapshotNode,
  type OutlineDiffResult,
} from './diffUtils'

export function useOutlineSnapshotCompare(
  projectId: string | undefined,
  compareBaseRevisionId: string | null,
  visibleRevisions: any[],
  setCompareBaseRevisionId: (id: string | null) => void,
  setCompareTargetRevisionId: (id: string | null) => void,
  setCompareResult: (r: OutlineDiffResult | null) => void,
  setCompareFilter: (f: 'all' | 'high' | 'structure' | 'content') => void,
  setIsCompareDrawerOpen: (open: boolean) => void,
  setIsComparing: (v: boolean) => void,
) {
  const handleSelectCompareBase = useCallback((revisionId: string) => {
    setCompareBaseRevisionId(revisionId)
    toast.success('已设置基线版本 A')
  }, [setCompareBaseRevisionId])

  const handleCompareWithBase = useCallback(async (targetRevisionId: string) => {
    if (!projectId) return
    if (!compareBaseRevisionId) {
      toast.error('请先设定一个基线版本 A')
      return
    }
    if (compareBaseRevisionId === targetRevisionId) {
      toast.error('A 与 B 不能是同一版本')
      return
    }
    setIsComparing(true)
    try {
      const [baseRes, targetRes] = await Promise.all([
        outlineApi.getRevision(projectId, compareBaseRevisionId),
        outlineApi.getRevision(projectId, targetRevisionId),
      ])
      const baseNodes = (baseRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[]
      const targetNodes = (targetRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[]
      const diff = compareSnapshots(baseNodes, targetNodes)
      setCompareResult(diff)
      setCompareTargetRevisionId(targetRevisionId)
      setCompareFilter('high')
      setIsCompareDrawerOpen(true)
    } catch {
      toast.error('快照对比失败')
    } finally {
      setIsComparing(false)
    }
  }, [
    projectId, compareBaseRevisionId, setCompareResult, setCompareTargetRevisionId,
    setCompareFilter, setIsCompareDrawerOpen, setIsComparing,
  ])

  const handleCompareLatestTwo = useCallback(async () => {
    if (visibleRevisions.length < 2) {
      toast.error('至少需要 2 个快照才可对比')
      return
    }
    if (!projectId) return
    const latest = visibleRevisions[0]
    const previous = visibleRevisions[1]
    setCompareBaseRevisionId(previous.id)
    setIsComparing(true)
    try {
      const [baseRes, targetRes] = await Promise.all([
        outlineApi.getRevision(projectId, previous.id),
        outlineApi.getRevision(projectId, latest.id),
      ])
      const diff = compareSnapshots(
        (baseRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[],
        (targetRes.data?.snapshot?.nodes || []) as RevisionSnapshotNode[],
      )
      setCompareResult(diff)
      setCompareTargetRevisionId(latest.id)
      setCompareFilter('high')
      setIsCompareDrawerOpen(true)
    } catch {
      toast.error('快照对比失败')
    } finally {
      setIsComparing(false)
    }
  }, [
    projectId, visibleRevisions, setCompareBaseRevisionId, setCompareResult,
    setCompareTargetRevisionId, setCompareFilter, setIsCompareDrawerOpen, setIsComparing,
  ])

  return { handleSelectCompareBase, handleCompareWithBase, handleCompareLatestTwo }
}
