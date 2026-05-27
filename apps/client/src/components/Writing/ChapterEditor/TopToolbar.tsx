/**
 * TopToolbar.tsx — 顶部章节工具栏
 *
 * 纯展示/事件分发组件：不涉及章节正文业务逻辑（生成/复盘等由父组件提供 handler）。
 */
import React from 'react'
import clsx from 'clsx'
import { BookOpen, CheckSquare, ClipboardList, Clock, History, Layers, Minimize2, PenLine, RefreshCw, Save, ShieldAlert, Trash2, ChevronDown, Maximize2 } from 'lucide-react'
import type { Chapter, OutlineNode } from '../../../types'
import { STATUS_OPTIONS, TOP_TOOL_BUTTON_ACTIVE, TOP_TOOL_BUTTON_BASE, TOP_TOOL_BUTTON_IDLE, TOP_TOOL_DEBRIEF_BUTTON_IDLE, TOP_TOOL_ICON_BUTTON, TOP_TOOL_PRIMARY_BUTTON } from './constants'
import type { PreWriteWarnResult } from './types'

export type ChapterContextTab = 'plan' | 'scene' | 'debrief' | 'chindex' | 'warn'

export default function TopToolbar({
  focusMode,
  onToggleFocusMode,

  chapterTitle,
  chapterStatus,
  currentStatus,

  sessionDelta,
  elapsedLabel,
  wordCount,

  contextOpen,
  contextTab,
  setContextOpen,
  setContextTab,
  outlineNode,

  statusOpen,
  statusRef,
  setStatusOpen,
  updateStatus,

  runPreWriteWarning,
  warnLoading,
  warnResult,

  openChapterHistory,
  cleanupChapter,
  cleaningChapter,

  manualSave,
}: {
  focusMode: boolean
  onToggleFocusMode: () => void

  chapterTitle: string
  chapterStatus: Chapter['status']
  currentStatus: (typeof STATUS_OPTIONS)[number]

  sessionDelta: number
  elapsedLabel: string
  wordCount: number

  contextOpen: boolean
  contextTab: ChapterContextTab
  setContextOpen: React.Dispatch<React.SetStateAction<boolean>>
  setContextTab: React.Dispatch<React.SetStateAction<ChapterContextTab>>
  outlineNode: OutlineNode | null

  statusOpen: boolean
  statusRef: React.RefObject<HTMLDivElement>
  setStatusOpen: React.Dispatch<React.SetStateAction<boolean>>
  updateStatus: (status: Chapter['status']) => Promise<void> | void

  runPreWriteWarning: () => void | Promise<void>
  warnLoading: boolean
  warnResult: PreWriteWarnResult | null

  openChapterHistory: () => void | Promise<void>
  cleanupChapter: () => void | Promise<void>
  cleaningChapter: boolean

  manualSave: () => void | Promise<void>
}) {
  return (
    <div
      className={clsx(
        'flex items-center justify-between px-5 py-2.5 border-b shrink-0 transition-all duration-200',
        focusMode ? 'border-transparent bg-transparent' : 'border-novel-border bg-novel-raised/95',
      )}
    >
      {/* 左侧：章名 + 状态 */}
      <div className="flex items-center gap-3 min-w-0">
        <h2
          className={clsx(
            'font-semibold truncate max-w-xs lg:max-w-lg transition-colors',
            focusMode ? 'text-gray-400 text-sm font-normal' : 'text-novel-ink',
          )}
        >
          {chapterTitle}
        </h2>

        {/* 状态下拉（专注模式隐藏）*/}
        {!focusMode && (
          <div className="relative" ref={statusRef}>
            <button
              type="button"
              onClick={() => setStatusOpen(v => !v)}
              className="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border border-novel-border bg-novel-card hover:bg-novel-panel transition-novel"
            >
              <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', currentStatus.dotCls)} />
              <span className={currentStatus.textCls}>{currentStatus.label}</span>
              <ChevronDown size={10} className="text-novel-ink-faint" />
            </button>

            {statusOpen && (
              <div className="absolute top-full left-0 mt-1 bg-white border border-novel-border rounded-novel shadow-lg z-50 py-1 min-w-[96px]">
                {STATUS_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => void updateStatus(opt.value)}
                    className={clsx(
                      'w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-novel-panel transition-novel',
                      chapterStatus === opt.value && 'bg-novel-panel',
                    )}
                  >
                    <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', opt.dotCls)} />
                    <span className={opt.textCls}>{opt.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 右侧：统计 + 工具按钮 */}
      <div className="flex items-center gap-2 shrink-0">
        {/* 本次写作统计 */}
        {sessionDelta !== 0 && !focusMode && (
          <div className="hidden sm:flex items-center gap-2 text-[11px]">
            <span
              className={clsx(
                'flex items-center gap-1 font-medium',
                sessionDelta > 0 ? 'text-green-600' : 'text-red-500',
              )}
            >
              <PenLine size={11} className="opacity-70" />
              {sessionDelta > 0 ? '+' : ''}
              {sessionDelta.toLocaleString()} 字
            </span>
            {elapsedLabel && (
              <span className="flex items-center gap-0.5 text-novel-ink-faint">
                <Clock size={10} />
                {elapsedLabel}
              </span>
            )}
          </div>
        )}

        {/* 总字数 */}
        <span className={clsx('text-sm', focusMode ? 'text-gray-400' : 'text-novel-ink-muted')}>
          {wordCount.toLocaleString()} 字
        </span>

        {/* 分场写作入口（三层调度：章纲→分场→正文→缝合） */}
        {!focusMode && (
          <button
            type="button"
            onClick={() => {
              setContextOpen(v => !(v && contextTab === 'scene'))
              setContextTab('scene')
            }}
            title="分场写作（推荐）：生成分场 → 逐场起草 → 缝合进章节"
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              contextOpen && contextTab === 'scene' ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_BUTTON_IDLE,
            )}
          >
            <Layers size={14} />
            分场
          </button>
        )}

        {/* 章节计划 */}
        {!focusMode && outlineNode && (
          <button
            type="button"
            onClick={() => {
              setContextOpen(v => !(v && contextTab === 'plan'))
              setContextTab('plan')
            }}
            title="章节计划"
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              contextOpen && contextTab === 'plan' ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_BUTTON_IDLE,
            )}
          >
            <BookOpen size={14} />
            计划
          </button>
        )}

        {/* 复盘（暖色强调，与灰底工具区分） */}
        {!focusMode && (
          <button
            type="button"
            onClick={() => {
              setContextOpen(v => !(v && contextTab === 'debrief'))
              setContextTab('debrief')
            }}
            title="章节复盘（更新人物状态/故事线）"
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              contextOpen && contextTab === 'debrief' ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_DEBRIEF_BUTTON_IDLE,
            )}
          >
            <CheckSquare size={15} strokeWidth={2.25} className="shrink-0" />
            复盘
          </button>
        )}

        {!focusMode && (
          <button
            type="button"
            onClick={() => {
              setContextOpen(v => !(v && contextTab === 'chindex'))
              setContextTab('chindex')
            }}
            title="情节索引（核心事件、钩子、伏笔、连续性 — 可编辑保存）"
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              contextOpen && contextTab === 'chindex' ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_BUTTON_IDLE,
            )}
          >
            <ClipboardList size={14} />
            索引
          </button>
        )}

        {/* 写前预警 */}
        {!focusMode && (
          <button
            type="button"
            onClick={() => void runPreWriteWarning()}
            disabled={warnLoading}
            title="写前预警：对照记忆/伏笔台账检查本章计划的潜在矛盾"
            className={clsx(
              TOP_TOOL_BUTTON_BASE,
              contextOpen && contextTab === 'warn'
                ? 'border-rose-300 bg-rose-50 text-rose-600'
                : warnResult && !warnResult.ok
                  ? 'border-rose-300 bg-rose-50 text-rose-500'
                  : TOP_TOOL_BUTTON_IDLE,
            )}
          >
            {warnLoading ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : warnResult && !warnResult.ok ? (
              <ShieldAlert size={14} />
            ) : (
              <ShieldAlert size={14} />
            )}
            预警
          </button>
        )}

        {!focusMode && (
          <button
            type="button"
            onClick={() => void openChapterHistory()}
            title="正文版本历史：查看、对比此前保存或 AI 覆盖前的快照"
            className={clsx(TOP_TOOL_BUTTON_BASE, TOP_TOOL_BUTTON_IDLE)}
          >
            <History size={14} />
            版本
          </button>
        )}

        {!focusMode && (
          <button
            type="button"
            onClick={() => void cleanupChapter()}
            disabled={cleaningChapter}
            title="清理章节"
            className={TOP_TOOL_ICON_BUTTON}
          >
            {cleaningChapter ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        )}

        {/* 专注模式切换 */}
        <button
          type="button"
          onClick={onToggleFocusMode}
          title={focusMode ? '退出专注模式' : '专注写作模式（隐藏工具栏）'}
          className={clsx(
            TOP_TOOL_BUTTON_BASE,
            focusMode ? TOP_TOOL_BUTTON_ACTIVE : TOP_TOOL_BUTTON_IDLE,
          )}
        >
          {focusMode ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {focusMode ? '退出专注' : '专注'}
        </button>

        {/* 保存（与左侧工具组视觉分隔） */}
        <div className="hidden sm:block h-6 w-px bg-novel-border shrink-0 mx-0.5" aria-hidden />
        <button type="button" onClick={() => void manualSave()} className={TOP_TOOL_PRIMARY_BUTTON}>
          <Save size={16} strokeWidth={2.25} className="shrink-0" />
          保存
        </button>
      </div>
    </div>
  )
}

