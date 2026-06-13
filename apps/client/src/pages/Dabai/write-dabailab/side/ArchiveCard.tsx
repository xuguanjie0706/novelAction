/**
 * 档案卡 — 当前章的情节档案（计划五拍 + 复盘实际 + 线索/资产/关系），随章刷新。
 * 数据：GET /dabai/projects/{pid}/chapters/{cid}/archive。
 */
import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiChapterArchive } from '../../../../types/dabaiLab'
import ArchiveSections from '../ArchiveSections'

interface Props {
  projectId: string
  chapterId: string
  /** 写后自动质检/复盘完成后 +1，触发重拉本章档案。 */
  refreshKey: number
}

export default function ArchiveCard({ projectId, chapterId, refreshKey }: Props) {
  const [archive, setArchive] = useState<DabaiChapterArchive | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    setLoading(true)
    dabaiLabApi.getChapterArchive(projectId, chapterId)
      .then(res => setArchive(res.data))
      .catch(() => setArchive(null))
      .finally(() => setLoading(false))
  }, [projectId, chapterId])

  useEffect(() => { refresh() }, [refresh, refreshKey])

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-xs text-gray-400">
        <Loader2 size={13} className="animate-spin" /> 加载档案…
      </p>
    )
  }
  if (!archive) {
    return <p className="text-xs text-gray-400">暂无档案数据</p>
  }
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-gray-400">
        第{archive.chapter_number}章 · {archive.word_count.toLocaleString()} 字
        {archive.debriefed ? ' · 已复盘' : ' · 未复盘'}
      </p>
      <ArchiveSections archive={archive} />
    </div>
  )
}
