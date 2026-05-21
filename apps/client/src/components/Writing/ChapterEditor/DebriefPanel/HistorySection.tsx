/**
 * @file 复盘落库历史审计列表
 */
import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { chaptersApi } from '../../../../api/client'
import { DEBRIEF_APPLY_SOURCE_LABEL } from './constants'

export interface HistorySectionProps {
  projectId: string
  chapterId: string
  debriefHistoryTick?: number
}

export function HistorySection({ projectId, chapterId, debriefHistoryTick = 0 }: HistorySectionProps) {
  const [applyRecords, setApplyRecords] = useState<Array<{
    id: string
    apply_source: string
    content_hash: string | null
    payload: Record<string, unknown>
    result_message: string | null
    created_at: string | null
  }>>([])
  const [applyRecordsLoading, setApplyRecordsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setApplyRecordsLoading(true)
    chaptersApi.listDebriefApplyRecords(projectId, chapterId, 25)
      .then(r => {
        if (!cancelled) setApplyRecords(r.data)
      })
      .catch(() => {
        if (!cancelled) setApplyRecords([])
      })
      .finally(() => {
        if (!cancelled) setApplyRecordsLoading(false)
      })
    return () => { cancelled = true }
  }, [projectId, chapterId, debriefHistoryTick])

  return (
    <section className="rounded-novel border border-novel-border bg-novel-card/90 px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <History size={11} className="text-novel-ink-muted" />
        <span className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wider">复盘落库记录</span>
        {applyRecordsLoading && <span className="text-[10px] text-novel-ink-faint">加载中…</span>}
      </div>
      <p className="text-[9px] text-novel-ink-faint leading-relaxed">
        每次落库（队列自动或本页提交）都会在服务端留档：时间、来源、摘要与完整填入 JSON，便于回溯本章做过哪些复盘操作。
      </p>
      {!applyRecordsLoading && applyRecords.length === 0 && (
        <p className="text-[10px] text-novel-ink-faint italic">本章尚无落库记录。</p>
      )}
      <div className="space-y-1.5 max-h-56 overflow-y-auto">
        {applyRecords.map(r => {
          const t = r.created_at ? r.created_at.replace('T', ' ').slice(0, 19) : '—'
          const src = DEBRIEF_APPLY_SOURCE_LABEL[r.apply_source] ?? r.apply_source
          return (
            <details
              key={r.id}
              className="rounded border border-novel-border bg-white/70 px-2 py-1.5 text-[10px] text-novel-ink"
            >
              <summary className="cursor-pointer select-none list-none flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-medium text-novel-ink">{t}</span>
                <span className="text-[9px] text-novel-accent">{src}</span>
                {r.content_hash && (
                  <span className="text-[9px] text-novel-ink-faint font-mono truncate max-w-[10rem]" title={r.content_hash}>
                    正文哈希 {r.content_hash.slice(0, 8)}…
                  </span>
                )}
              </summary>
              {r.result_message && (
                <p className="mt-1.5 text-[10px] text-novel-ink-muted leading-relaxed border-t border-novel-border/60 pt-1.5">
                  {r.result_message}
                </p>
              )}
              <pre className="mt-1.5 max-h-36 overflow-auto text-[9px] leading-snug text-novel-ink-faint whitespace-pre-wrap break-words">
                {JSON.stringify(r.payload, null, 2)}
              </pre>
            </details>
          )
        })}
      </div>
    </section>
  )
}
