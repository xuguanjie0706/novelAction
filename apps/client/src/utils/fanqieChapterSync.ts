/**
 * 章节 extra 中的番茄同步记录（与后端 sync_record.py 字段对齐）。
 */
export interface FanqieChapterSyncMeta {
  bookId: string
  itemId: string
  title: string
  syncedAt: string
}

export function readFanqieChapterSync(
  extra: unknown,
  bookId: string,
): FanqieChapterSyncMeta | null {
  if (!bookId || typeof extra !== 'object' || extra === null) return null
  const e = extra as Record<string, unknown>
  if (String(e.fanqie_book_id ?? '') !== bookId) return null
  const itemId = String(e.fanqie_item_id ?? '').trim()
  if (!itemId) return null
  return {
    bookId,
    itemId,
    title: String(e.fanqie_title ?? ''),
    syncedAt: String(e.fanqie_synced_at ?? ''),
  }
}

export function mergeFanqieChapterExtra(
  extra: unknown,
  patch: {
    bookId: string
    itemId: string
    title: string
    syncedAt?: string
  },
): Record<string, unknown> {
  const base = typeof extra === 'object' && extra !== null
    ? { ...(extra as Record<string, unknown>) }
    : {}
  return {
    ...base,
    fanqie_book_id: patch.bookId,
    fanqie_item_id: patch.itemId,
    fanqie_title: patch.title,
    fanqie_synced_at: patch.syncedAt ?? new Date().toISOString(),
  }
}
