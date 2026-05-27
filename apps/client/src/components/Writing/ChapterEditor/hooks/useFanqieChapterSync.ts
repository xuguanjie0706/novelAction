/**
 * useFanqieChapterSync — 将当前章节同步上传到番茄草稿箱
 *
 * - 同步前写入 DB 的标题 + 正文
 * - chapter.extra 记录 fanqie_item_id，下次走更新而非新建
 */
import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { useAppStore } from '../../../../store'
import { chaptersApi } from '../../../../api/client'
import { getFanqieConfigSummary, publishProjectToFanqie } from '../../../../api/fanqieApi'
import type { Chapter } from '../../../../types'
import {
  mergeFanqieChapterExtra,
  readFanqieChapterSync,
} from '../../../../utils/fanqieChapterSync'

interface Params {
  projectId: string
  chapter: Chapter
  getEditorHtml?: () => string
  onChapterPatched?: (patch: Partial<Chapter>) => void
}

export function useFanqieChapterSync({
  projectId,
  chapter,
  getEditorHtml,
  onChapterPatched,
}: Params) {
  const [syncing, setSyncing] = useState(false)
  const currentProject = useAppStore(s => s.currentProject)

  const fanqieBookId: string = (() => {
    const extra = currentProject?.extra
    if (typeof extra === 'object' && extra !== null && 'fanqie_book_id' in extra) {
      return String((extra as Record<string, unknown>).fanqie_book_id ?? '')
    }
    return ''
  })()

  const syncMeta = useMemo(
    () => readFanqieChapterSync(chapter.extra, fanqieBookId),
    [chapter.extra, fanqieBookId],
  )

  const syncToFanqie = async () => {
    if (!fanqieBookId) {
      toast.error('请先在「小说详情」页绑定番茄书籍', { id: 'fanqie-no-binding' })
      return
    }

    let configured = false
    try {
      const cfg = await getFanqieConfigSummary()
      configured = cfg.configured
      if (configured && (!cfg.has_a_bogus || !cfg.has_ms_token)) {
        toast.error(
          '上传草稿需要完整 cURL（含 msToken、a_bogus），请粘贴 cover_article 请求到「我的番茄」',
          { id: 'fanqie-no-signature', duration: 6000 },
        )
        return
      }
    } catch {
      configured = false
    }
    if (!configured) {
      toast.error('番茄账号未连接，请前往「我的番茄」页面配置凭据', { id: 'fanqie-no-cred' })
      return
    }

    const editorHtml = getEditorHtml?.()?.trim() ?? ''
    const chapterTitle = (chapter.title || '').trim()

    setSyncing(true)
    const tid = toast.loading(syncMeta ? '正在更新番茄草稿…' : '正在同步到番茄草稿箱…')
    try {
      const updatePayload: { content?: string; title?: string } = {}
      if (editorHtml) updatePayload.content = editorHtml
      if (chapterTitle) updatePayload.title = chapterTitle
      if (Object.keys(updatePayload).length > 0) {
        const res = await chaptersApi.update(projectId, chapter.id, updatePayload)
        onChapterPatched?.({
          content: res.data.content ?? chapter.content,
          title: res.data.title ?? chapter.title,
        })
      }

      const res = await publishProjectToFanqie(projectId, {
        mode: 'existing',
        book_id: fanqieBookId,
        chapter_ids: [chapter.id],
        delay_seconds: 0,
        content_html: editorHtml || undefined,
        chapter_title: chapterTitle || undefined,
      })

      toast.dismiss(tid)
      if (res.failed.length === 0 && res.uploaded.length > 0) {
        const row = res.uploaded[0]
        const chars = row.content_chars ?? 0
        const isUpdate = row.sync_mode === 'update'
        if (row.item_id) {
          onChapterPatched?.({
            extra: mergeFanqieChapterExtra(chapter.extra, {
              bookId: fanqieBookId,
              itemId: row.item_id,
              title: row.title,
            }),
          })
        }
        toast.success(
          isUpdate
            ? `已更新番茄草稿「${row.title}」（约 ${chars} 字）`
            : `已同步「${row.title}」到番茄草稿（约 ${chars} 字）`,
          { id: 'fanqie-sync-ok', duration: 5000 },
        )
      } else if (res.failed.length > 0) {
        const msg = res.failed[0]?.message ?? '上传失败'
        toast.error(`同步失败：${msg}`, { id: 'fanqie-sync-fail' })
      } else {
        toast('同步完成（无章节内容可上传）', { id: 'fanqie-sync-empty' })
      }
    } catch (e: unknown) {
      toast.dismiss(tid)
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err?.response?.data?.detail ?? err?.message ?? '同步失败', { id: 'fanqie-sync-err' })
    } finally {
      setSyncing(false)
    }
  }

  return { syncToFanqie, syncing, fanqieBookId, syncMeta }
}
