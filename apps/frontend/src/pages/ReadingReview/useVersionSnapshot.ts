import { App } from 'antd'
import { useCallback, useMemo, useState } from 'react'
import { http } from '../../api/http'
import type { ChapterVersionDetail, ChapterVersionTimelineItem, ReviewChapter } from '../../types/review'
import type { VersionPreviewPanel } from './types'
import { snapshotSourceTag, stripHtmlToPlain } from './utils'

/** 正文快照时间轴与「改正前后对照」弹窗 */
export function useVersionSnapshot(projectId: string | undefined) {
  const { message } = App.useApp()
  const [versionTimelineLoading, setVersionTimelineLoading] = useState(false)
  const [versionTimelineRows, setVersionTimelineRows] = useState<ChapterVersionTimelineItem[]>([])
  const [versionPreviewOpen, setVersionPreviewOpen] = useState(false)
  const [versionPreviewLoading, setVersionPreviewLoading] = useState(false)
  const [versionPreviewPanels, setVersionPreviewPanels] = useState<VersionPreviewPanel[]>([])

  const loadVersionTimeline = useCallback(
    async (pid: string) => {
      setVersionTimelineLoading(true)
      try {
        const { data } = await http.get<ChapterVersionTimelineItem[]>(
          `/api/v1/projects/${pid}/chapters/version-timeline`,
          { params: { limit: 120 } },
        )
        setVersionTimelineRows(data)
      } catch {
        message.error('加载正文快照列表失败')
      } finally {
        setVersionTimelineLoading(false)
      }
    },
    [message],
  )

  const fetchVersionPanel = useCallback(
    async (pid: string, row: ChapterVersionTimelineItem): Promise<VersionPreviewPanel> => {
      const { data } = await http.get<ChapterVersionDetail>(
        `/api/v1/projects/${pid}/chapters/${row.chapter_id}/versions/${row.id}`,
      )
      const t = snapshotSourceTag(row.note, row.is_auto)
      const meta = `${new Date(row.created_at).toLocaleString('zh-CN')} · ${t.text}`
      return {
        id: row.id,
        chapterId: row.chapter_id,
        title: `第${row.chapter_sort_order + 1}章 · ${row.chapter_title || '未命名'}`,
        meta,
        plain: stripHtmlToPlain(data.content || '', 120_000),
      }
    },
    [],
  )

  const openSnapshotBeforeAfterPreview = useCallback(
    async (row: ChapterVersionTimelineItem) => {
      if (!projectId) return
      setVersionPreviewOpen(true)
      setVersionPreviewLoading(true)
      setVersionPreviewPanels([])
      try {
        const [beforePanel, { data: ch }] = await Promise.all([
          fetchVersionPanel(projectId, row),
          http.get<ReviewChapter>(`/api/v1/projects/${projectId}/chapters/${row.chapter_id}`),
        ])
        const afterMeta =
          ch.updated_at != null
            ? `当前正文（数据库）· 最后更新 ${new Date(ch.updated_at).toLocaleString('zh-CN')}`
            : '当前正文（数据库）'
        const afterPanel: VersionPreviewPanel = {
          id: `current-${row.chapter_id}`,
          chapterId: row.chapter_id,
          title: beforePanel.title,
          meta: afterMeta,
          plain: stripHtmlToPlain(ch.content || '', 120_000),
        }
        setVersionPreviewPanels([beforePanel, afterPanel])
      } catch {
        message.error('加载改正前后对照失败')
        setVersionPreviewOpen(false)
      } finally {
        setVersionPreviewLoading(false)
      }
    },
    [fetchVersionPanel, message, projectId],
  )

  const closeVersionPreview = useCallback(() => {
    setVersionPreviewOpen(false)
    setVersionPreviewPanels([])
  }, [])

  const versionPreviewModalTitle = useMemo(() => {
    if (versionPreviewPanels.length >= 2) return `改正前后对照 · ${versionPreviewPanels[0].title}`
    return '改正前后对照'
  }, [versionPreviewPanels])

  return {
    versionTimelineLoading,
    versionTimelineRows,
    versionPreviewOpen,
    versionPreviewLoading,
    versionPreviewPanels,
    versionPreviewModalTitle,
    loadVersionTimeline,
    openSnapshotBeforeAfterPreview,
    closeVersionPreview,
  }
}
