/**
 * ChapterHistoryModal.tsx — 正文版本历史弹窗
 */
import React from 'react'
import clsx from 'clsx'
import { History, RefreshCw, X } from 'lucide-react'
import type { ChapterVersion, ChapterVersionDetail } from '../../../types'

export default function ChapterHistoryModal({
  historyOpen,
  setHistoryOpen,
  versionsLoading,
  versionsList,
  historyPreviewLoading,
  historyPreview,
  onSelectVersion,
  onRestoreVersion,
}: {
  historyOpen: boolean
  setHistoryOpen: React.Dispatch<React.SetStateAction<boolean>>
  versionsLoading: boolean
  versionsList: ChapterVersion[]
  historyPreviewLoading: boolean
  historyPreview: ChapterVersionDetail | null
  onSelectVersion: (versionId: string) => void | Promise<void>
  onRestoreVersion: () => void | Promise<void>
}) {
  if (!historyOpen) return null

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/50 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chapter-history-title"
      onMouseDown={e => {
        if (e.target === e.currentTarget) setHistoryOpen(false)
      }}
    >
      <div
        className="w-full max-w-4xl max-h-[min(90vh,720px)] flex flex-col rounded-2xl border border-novel-border bg-novel-card shadow-2xl overflow-hidden"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-novel-border bg-novel-panel shrink-0">
          <h3 id="chapter-history-title" className="text-sm font-semibold text-novel-ink flex items-center gap-2">
            <History size={16} className="text-novel-accent" />
            正文版本历史
          </h3>
          <button
            type="button"
            onClick={() => setHistoryOpen(false)}
            className="p-1.5 rounded-lg text-novel-ink-faint hover:text-novel-ink hover:bg-novel-shell transition-novel"
          >
            <X size={16} />
          </button>
        </div>

        <p className="text-[11px] text-novel-ink-faint px-4 py-2 border-b border-novel-border/80 bg-novel-shell/40">
          含「手动保存」与 AI 续写/重写覆盖前的自动备份。点选一条可预览；恢复会先备份当前正文再替换。
        </p>

        <div className="flex flex-1 min-h-0">
          <div className="w-[13.5rem] shrink-0 border-r border-novel-border overflow-auto bg-novel-shell/30">
            {versionsLoading ? (
              <p className="text-xs text-novel-ink-faint p-3">加载中…</p>
            ) : versionsList.length === 0 ? (
              <p className="text-xs text-novel-ink-faint p-3">
                暂无历史版本
                <br />
                <span className="text-[10px]">保存本章或经 AI 改写后会自动生成</span>
              </p>
            ) : (
              <ul className="p-2 space-y-1">
                {versionsList.map(v => (
                  <li key={v.id}>
                    <button
                      type="button"
                      onClick={() => void onSelectVersion(v.id)}
                      className={clsx(
                        'w-full text-left rounded-lg px-2.5 py-2 text-[11px] transition-novel border',
                        historyPreview?.id === v.id
                          ? 'border-novel-accent bg-novel-panel text-novel-accent'
                          : 'border-transparent hover:bg-novel-card text-novel-ink',
                      )}
                    >
                      <div className="font-medium truncate">
                        {new Date(v.created_at).toLocaleString('zh-CN', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                      <div className="text-[10px] text-novel-ink-faint truncate mt-0.5">
                        {v.is_auto ? '自动' : '手动'}
                        {v.note ? ` · ${v.note}` : ''}
                        {typeof v.word_count === 'number' ? ` · ${v.word_count} 字` : ''}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-white">
            {historyPreviewLoading && (
              <div className="flex-1 flex items-center justify-center text-sm text-novel-ink-faint">
                加载正文…
              </div>
            )}
            {!historyPreviewLoading && !historyPreview && (
              <div className="flex-1 flex items-center justify-center text-sm text-novel-ink-faint px-6 text-center">
                在左侧选择一条版本以预览 HTML 正文
              </div>
            )}
            {!historyPreviewLoading && historyPreview && (
              <>
                <div className="shrink-0 px-3 py-2 border-b border-gray-100 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void onRestoreVersion()}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500"
                  >
                    恢复此版本到编辑器
                  </button>
                  <span className="text-[10px] text-gray-400">当前为只读预览</span>
                </div>
                <div
                  className="flex-1 overflow-auto prose prose-sm max-w-none px-4 py-3 text-novel-ink"
                  dangerouslySetInnerHTML={{
                    __html: historyPreview.content || '<p>（空）</p>',
                  }}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

