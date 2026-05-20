/**
 * constants.tsx — ChapterEditor 包内 UI 常量
 *
 * 职责：模块级常量声明，无副作用。
 * .tsx 扩展名：INLINE_ACTIONS 含 JSX，需要 React 上下文。
 */
import React from 'react'
import { RefreshCw, Feather } from 'lucide-react'
import type { Chapter, Character } from '../../../types'

// ─── 章节状态选项 ─────────────────────────────────────────────────────────────

export const STATUS_OPTIONS: { value: Chapter['status']; label: string; dotCls: string; textCls: string }[] = [
  { value: 'draft',    label: '初稿',  dotCls: 'bg-gray-300',   textCls: 'text-gray-500' },
  { value: 'writing',  label: '修改中', dotCls: 'bg-blue-400',   textCls: 'text-blue-600' },
  { value: 'done',     label: '完稿',  dotCls: 'bg-green-400',  textCls: 'text-green-600' },
  { value: 'reviewed', label: '已审',  dotCls: 'bg-amber-400',  textCls: 'text-amber-600' },
]

// ─── 人物角色标签 ─────────────────────────────────────────────────────────────

export const ROLE_BADGE: Record<Character['role'], { label: string; cls: string }> = {
  protagonist: { label: '主角', cls: 'bg-amber-100 text-amber-700' },
  supporting:  { label: '配角', cls: 'bg-blue-50 text-blue-600' },
  antagonist:  { label: '反派', cls: 'bg-red-50 text-red-600' },
  neutral:     { label: '中立', cls: 'bg-gray-100 text-gray-600' },
}

// ─── 划词内联动作 ─────────────────────────────────────────────────────────────

export const INLINE_ACTIONS = [
  {
    key: 'rewrite',
    label: '改写',
    icon: <RefreshCw size={11} />,
    buildPrompt: (t: string) =>
      `请将以下选中段落改写，保持语义不变但改变表达方式，只返回改写后的文字，不要任何解释：\n\n「${t}」`,
  },
  {
    key: 'expand',
    label: '扩写',
    icon: <Feather size={11} />,
    buildPrompt: (t: string) =>
      `请将以下段落扩写，增加细节和描写，只返回扩写后的文字，不要任何解释：\n\n「${t}」`,
  },
] as const

// ─── 顶部工具栏按钮样式 ───────────────────────────────────────────────────────

export const TOP_TOOL_BUTTON_BASE =
  'inline-flex h-8 items-center justify-center gap-1.5 rounded-novel border px-3 text-sm font-medium leading-none transition-novel focus:outline-none focus-visible:ring-2 focus-visible:ring-novel-accent focus-visible:ring-offset-2'
export const TOP_TOOL_BUTTON_IDLE =
  'border-novel-border bg-novel-card text-novel-ink-muted hover:bg-novel-panel hover:text-novel-ink'
export const TOP_TOOL_BUTTON_ACTIVE =
  'border-novel-accent/35 bg-novel-panel text-novel-accent'
export const TOP_TOOL_ICON_BUTTON =
  'inline-flex h-8 w-8 items-center justify-center rounded-novel border border-red-100 bg-novel-card text-red-400 transition-novel hover:bg-red-50 hover:text-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
/** 写作页主操作：保存（与次要工具按钮区分） */
export const TOP_TOOL_PRIMARY_BUTTON =
  'inline-flex h-9 min-w-[5.75rem] items-center justify-center gap-2 rounded-xl border-2 border-emerald-700/25 bg-emerald-600 px-4 text-sm font-semibold leading-none text-white shadow-md shadow-emerald-900/20 transition-novel hover:bg-emerald-500 hover:shadow-lg hover:border-emerald-600/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 active:scale-[0.98]'
export const TOP_TOOL_DEBRIEF_BUTTON_IDLE =
  'border-amber-200 bg-amber-50/90 text-amber-900 hover:bg-amber-100 hover:border-amber-300'
