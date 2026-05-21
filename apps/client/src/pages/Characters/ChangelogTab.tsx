/**
 * @file 人物变更记录 Tab
 */
import { useState } from 'react'
import { Eraser, X, RotateCcw, Check, Loader2, History } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { CharacterChangeLog } from '../../types'
import { CHANGE_FIELD_STYLE, SOURCE_META } from './shared/constants'

export function ChangePill({ field, label, before, after }: {
  field: string; label: string; before: string | null; after: string | null
}) {
  const style = CHANGE_FIELD_STYLE[field] ?? { dot: 'bg-gray-400', pill: 'bg-gray-50 text-gray-600 border-gray-200' }
  let text = ''
  if (field === 'created') {
    text = `首次入库 · ${after ?? ''}`
  } else if (before && after) {
    text = `${label} ${before} → ${after}`
  } else if (after) {
    text = `${label}：${after}`
  } else if (before) {
    text = `失去${label}：${before}`
  }
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border font-medium', style.pill)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0', style.dot)} />
      {text}
    </span>
  )
}

type RedebriefState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'result'; updates: Array<{ field: string; label: string; before: string | null; after: string | null }>; chapterId: string }
  | { status: 'submitting' }

export function ChangelogTab({
  logs, loading, onClear, onDelete, onRedebrief, onConfirmRedebrief,
}: {
  logs: CharacterChangeLog[]
  loading: boolean
  charId: string
  onClear: () => void
  onDelete: (logId: string) => void
  onRedebrief: (chapterId: string, charId: string) => Promise<Array<{ field: string; label: string; before: string | null; after: string | null }>>
  onConfirmRedebrief: (chapterId: string, charId: string, updates: Array<{ field: string; after: string | null }>) => Promise<void>
}) {
  // per-entry redebrief state
  const [redebriefStates, setRedebriefStates] = useState<Record<string, RedebriefState>>({})

  const setEntryState = (logId: string, state: RedebriefState) =>
    setRedebriefStates(prev => ({ ...prev, [logId]: state }))

  const handleRedebrief = async (log: CharacterChangeLog) => {
    if (!log.chapter_id) return
    setEntryState(log.id as string, { status: 'loading' })
    try {
      const updates = await onRedebrief(log.chapter_id as string, log.character_id as string)
      setEntryState(log.id as string, { status: 'result', updates, chapterId: log.chapter_id as string })
    } catch {
      setEntryState(log.id as string, { status: 'idle' })
      toast.error('重新复盘失败')
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16 text-gray-400 text-sm">加载中…</div>
  }
  if (logs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center text-gray-400">
        <History size={32} className="mb-3 opacity-30" />
        <p className="text-sm">暂无变更记录</p>
        <p className="text-xs mt-1 text-gray-300">复盘提交或手动保存后会自动记录</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <History size={16} className="text-gray-400" />
          <span className="text-sm font-semibold text-gray-700">变更时间轴</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{logs.length} 条记录</span>
          <button onClick={onClear} className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors" title="清空全部">
            <Eraser size={12} />
            清空全部
          </button>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-3.5 top-2 bottom-2 w-px bg-gray-100" />

        <div className="space-y-0">
          {logs.map((log) => {
            const srcMeta = SOURCE_META[log.source] ?? SOURCE_META.manual
            const firstField = log.changes[0]?.field ?? 'created'
            const dotColor = (CHANGE_FIELD_STYLE[firstField] ?? CHANGE_FIELD_STYLE.created).dot
            const rstate = redebriefStates[log.id as string] ?? { status: 'idle' }

            return (
              <div key={log.id as string} className="flex gap-4 pb-5 relative group">
                {/* 时间轴节点 */}
                <div className="flex-shrink-0 w-7 flex justify-center pt-0.5">
                  <div className={clsx('w-3 h-3 rounded-full border-2 border-white ring-1 ring-gray-200 relative z-10', dotColor)} />
                </div>

                {/* 内容卡片 */}
                <div className="flex-1 min-w-0">
                  <div className="bg-gray-50 rounded-xl p-3.5 border border-gray-100">
                    {/* 头部 */}
                    <div className="flex items-center justify-between gap-2 mb-2.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {log.chapter_number
                          ? <span className="text-xs font-semibold text-gray-700 truncate">{log.chapter_number}{log.chapter_title ? `《${log.chapter_title}》` : ''}</span>
                          : <span className="text-xs font-semibold text-gray-500">无章节关联</span>
                        }
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', srcMeta.color)}>{srcMeta.label}</span>
                        <span className="text-[10px] text-gray-300">
                          {new Date(log.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                        {/* 操作按钮：hover 显示 */}
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {log.chapter_id && rstate.status === 'idle' && (
                            <button
                              onClick={() => handleRedebrief(log)}
                              className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded text-blue-500 hover:bg-blue-50 transition-colors"
                              title="重新复盘该章，补入新记录"
                            >
                              <RotateCcw size={10} />
                              重新复盘
                            </button>
                          )}
                          <button
                            onClick={() => onDelete(log.id as string)}
                            className="p-0.5 rounded text-gray-300 hover:text-red-400 hover:bg-red-50 transition-colors"
                            title="删除此条记录"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* 变更 Pills */}
                    <div className="flex flex-wrap gap-1.5">
                      {log.changes.map((c, i) => (
                        <ChangePill key={i} field={c.field} label={c.label} before={c.before} after={c.after} />
                      ))}
                    </div>
                  </div>

                  {/* 重新复盘内联结果 */}
                  {rstate.status === 'loading' && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-blue-500 pl-2">
                      <Loader2 size={12} className="animate-spin" />
                      AI 正在分析该章节…
                    </div>
                  )}
                  {rstate.status === 'result' && (
                    <div className="mt-2 bg-blue-50 border border-blue-100 rounded-xl p-3.5">
                      <p className="text-xs font-semibold text-blue-700 mb-2">
                        {rstate.updates.length > 0 ? `检测到 ${rstate.updates.length} 项变化` : 'AI 未检测到该章节的人物变化'}
                      </p>
                      {rstate.updates.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {rstate.updates.map((u, i) => (
                            <ChangePill key={i} field={u.field} label={u.label} before={u.before} after={u.after} />
                          ))}
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={() => setEntryState(log.id as string, { status: 'idle' })}
                          className="flex-1 py-1.5 text-xs text-gray-500 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                        >
                          取消
                        </button>
                        {rstate.updates.length > 0 && (
                          <button
                            onClick={async () => {
                              setEntryState(log.id as string, { status: 'submitting' })
                              try {
                                await onConfirmRedebrief(
                                  rstate.chapterId,
                                  log.character_id as string,
                                  rstate.updates.map(u => ({ field: u.field, after: u.after })),
                                )
                                setEntryState(log.id as string, { status: 'idle' })
                                toast.success('已补入新变更记录')
                              } catch {
                                setEntryState(log.id as string, { status: 'result', updates: rstate.updates, chapterId: rstate.chapterId })
                                toast.error('提交失败')
                              }
                            }}
                            className="flex-1 py-1.5 text-xs text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors flex items-center justify-center gap-1"
                          >
                            <Check size={11} />
                            确认补入
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                  {rstate.status === 'submitting' && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-blue-500 pl-2">
                      <Loader2 size={12} className="animate-spin" />
                      提交中…
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
