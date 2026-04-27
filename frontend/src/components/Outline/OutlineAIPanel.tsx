/**
 * OutlineAIPanel — AI 五要素大纲展开面板
 *
 * 职业作家的章节计划包含五个要素：
 *  ① 开篇钩子   ② 核心事件   ③ 人物变化   ④ 伏笔管理   ⑤ 章末钩子
 *
 * 新手只写 ①②，忽略 ③④⑤ ——这就是为什么他们的书掉追读。
 * 本面板强制展示全部五要素，让 ③④⑤ 不再被忽视。
 */

import React, { useState } from 'react'
import {
  Sparkles, ChevronDown, ChevronUp, Loader2,
  CheckCircle2, AlertCircle, BookOpen, Zap, GitBranch,
  Eye, Anchor, ArrowRight,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import type { OutlineNode } from '../../types'

// ── Types ─────────────────────────────────────────────

interface ChapterCard {
  number: number
  title: string
  opening_hook: string    // ① 开篇钩子
  core_event: string      // ② 核心事件
  character_change: string // ③ 人物变化（新手最常忽略）
  foreshadow: string      // ④ 伏笔管理（新手最常忽略）
  end_hook: string        // ⑤ 章末钩子（新手最常忽略，最关键）
  pacing: 'fast' | 'medium' | 'slow'
  word_estimate: number
}

interface VolumeAnalysis {
  emotional_arc: string
  core_question: string
  pacing_rhythm: string
}

interface ExpandResult {
  volume_analysis?: VolumeAnalysis
  chapters: ChapterCard[]
}

interface Props {
  node: OutlineNode
  projectId: string
  onCommitDone?: () => void
}

// ── Constants ─────────────────────────────────────────

const PACING_CONFIG = {
  fast:   { label: '快节奏', color: 'bg-red-100 text-red-700 border-red-200' },
  medium: { label: '中节奏', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  slow:   { label: '慢节奏', color: 'bg-blue-100 text-blue-700 border-blue-200' },
}

// 五要素配置 — ③④⑤ 标注"新手忽略"提醒
const ELEMENTS = [
  {
    key: 'opening_hook' as const,
    num: '①',
    label: '开篇钩子',
    sublabel: '前500字抓住读者的手段',
    icon: Zap,
    color: 'border-blue-200 bg-blue-50',
    headerColor: 'bg-blue-100 text-blue-800',
    iconColor: 'text-blue-500',
    pro: false,
  },
  {
    key: 'core_event' as const,
    num: '②',
    label: '核心事件',
    sublabel: '删掉会损失什么',
    icon: BookOpen,
    color: 'border-green-200 bg-green-50',
    headerColor: 'bg-green-100 text-green-800',
    iconColor: 'text-green-500',
    pro: false,
  },
  {
    key: 'character_change' as const,
    num: '③',
    label: '人物变化',
    sublabel: '不可逆的认知/处境/关系变化',
    icon: GitBranch,
    color: 'border-purple-200 bg-purple-50',
    headerColor: 'bg-purple-100 text-purple-800',
    iconColor: 'text-purple-500',
    pro: true,  // 新手常忽略
  },
  {
    key: 'foreshadow' as const,
    num: '④',
    label: '伏笔管理',
    sublabel: '新埋的伏笔 / 回收的旧伏笔',
    icon: Eye,
    color: 'border-orange-200 bg-orange-50',
    headerColor: 'bg-orange-100 text-orange-800',
    iconColor: 'text-orange-500',
    pro: true,  // 新手常忽略
  },
  {
    key: 'end_hook' as const,
    num: '⑤',
    label: '章末钩子',
    sublabel: '读者无法放下手机的最后一句',
    icon: Anchor,
    color: 'border-red-200 bg-red-50',
    headerColor: 'bg-red-100 text-red-800',
    iconColor: 'text-red-500',
    pro: true,  // 最关键，新手最常忽略
    highlight: true, // 特别高亮
  },
]

// ── Sub-components ─────────────────────────────────────

function VolumeAnalysisCard({ analysis }: { analysis: VolumeAnalysis }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-amber-200 rounded-xl overflow-hidden mb-4">
      <button
        className="w-full flex items-center justify-between px-4 py-2.5 bg-amber-50 hover:bg-amber-100 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-amber-600" />
          <span className="text-sm font-semibold text-amber-800">卷级情节分析</span>
        </div>
        {open ? <ChevronUp size={14} className="text-amber-600" /> : <ChevronDown size={14} className="text-amber-600" />}
      </button>
      {open && (
        <div className="px-4 py-3 space-y-2.5 bg-white">
          <AnalysisRow label="情绪弧线" value={analysis.emotional_arc} />
          <AnalysisRow label="核心悬念" value={analysis.core_question} />
          <AnalysisRow label="节奏规划" value={analysis.pacing_rhythm} />
        </div>
      )}
    </div>
  )
}

function AnalysisRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs font-medium text-gray-500">{label}</span>
      <p className="text-sm text-gray-700 mt-0.5">{value}</p>
    </div>
  )
}

function ElementBadge({ pro, highlight }: { pro: boolean; highlight?: boolean }) {
  if (highlight) return (
    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-red-500 text-white animate-pulse">
      最关键
    </span>
  )
  if (pro) return (
    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-gray-200 text-gray-600">
      新手常忽略
    </span>
  )
  return null
}

function ChapterCardView({
  card,
  index,
}: {
  card: ChapterCard
  index: number
}) {
  const [collapsed, setCollapsed] = useState(true)
  const pacing = PACING_CONFIG[card.pacing] ?? PACING_CONFIG.medium

  return (
    <div className={clsx(
      'border rounded-xl overflow-hidden transition-shadow',
      collapsed ? 'border-gray-200' : 'border-gray-300 shadow-sm'
    )}>
      {/* 卡片头 */}
      <button
        className="w-full flex items-center gap-2 px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
        onClick={() => setCollapsed(v => !v)}
      >
        <span className="shrink-0 w-7 h-7 rounded-full bg-gray-800 text-white text-xs font-bold flex items-center justify-center">
          {card.number}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-800 truncate">{card.title}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className={clsx('text-[11px] px-2 py-0.5 rounded-full border', pacing.color)}>
            {pacing.label}
          </span>
          <span className="text-[11px] text-gray-400">{card.word_estimate?.toLocaleString()}字</span>
          {collapsed
            ? <ChevronDown size={14} className="text-gray-400" />
            : <ChevronUp size={14} className="text-gray-400" />}
        </div>
      </button>

      {/* 五要素 */}
      {!collapsed && (
        <div className="border-t border-gray-100 divide-y divide-gray-100">
          {ELEMENTS.map(el => {
            const Icon = el.icon
            const value = card[el.key]
            return (
              <div
                key={el.key}
                className={clsx(
                  'px-4 py-3',
                  el.highlight ? 'bg-red-50/60' : 'bg-white'
                )}
              >
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className={clsx('text-xs font-bold', el.iconColor)}>{el.num}</span>
                  <Icon size={12} className={el.iconColor} />
                  <span className="text-xs font-semibold text-gray-700">{el.label}</span>
                  <span className="text-[10px] text-gray-400 hidden sm:inline">— {el.sublabel}</span>
                  <ElementBadge pro={el.pro} highlight={el.highlight} />
                </div>
                <p className={clsx(
                  'text-sm leading-relaxed',
                  el.highlight ? 'text-red-800 font-medium' : 'text-gray-700'
                )}>
                  {value || <span className="text-gray-400 italic">（未生成）</span>}
                </p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────

export default function OutlineAIPanel({ node, projectId, onCommitDone }: Props) {
  const [chapterCount, setChapterCount] = useState(10)
  const [modelProfile, setModelProfile] = useState<'default' | 'gemini'>('default')
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [result, setResult] = useState<ExpandResult | null>(null)
  const [committing, setCommitting] = useState(false)
  const [expandAll, setExpandAll] = useState(false)

  const nodeLabel = node.node_type === 'volume' ? '卷' : '篇'

  const handleGenerate = async () => {
    setStatus('loading')
    setResult(null)

    try {
      const url = `/api/v1/projects/${projectId}/outline/ai-expand`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: node.id,
          chapter_count: chapterCount,
          model_profile: modelProfile,
        }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw)
            if (evt.event === 'result') {
              const data = evt.data as ExpandResult
              if (data.chapters?.length) {
                setResult(data)
                setStatus('done')
              } else {
                throw new Error('AI 返回的章节列表为空')
              }
            } else if (evt.event === 'error') {
              throw new Error(evt.message || 'AI 生成失败')
            }
          } catch (parseErr) {
            // ignore partial lines
          }
        }
      }

      if (status !== 'done') setStatus('done')
    } catch (err: any) {
      setStatus('error')
      toast.error(err.message || '生成失败，请重试')
    }
  }

  const handleCommit = async () => {
    if (!result) return
    setCommitting(true)
    try {
      const res = await fetch(`/api/v1/projects/${projectId}/outline/ai-expand/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          parent_node_id: node.id,
          chapters: result.chapters,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      toast.success(`✅ 已将 ${result.chapters.length} 章写入大纲树`)
      onCommitDone?.()
      setStatus('idle')
      setResult(null)
    } catch (err: any) {
      toast.error(err.message || '存入失败')
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div className="mt-6 border-t border-gray-100 pt-6">

      {/* 区域标题 */}
      <div className="flex items-center gap-2 mb-4">
        <Sparkles size={16} className="text-amber-500" />
        <h4 className="text-sm font-semibold text-gray-700">AI 展开本{nodeLabel}大纲</h4>
        <div className="flex-1 h-px bg-gray-100" />
      </div>

      {/* 新手提示 */}
      <div className="mb-4 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5">
        <p className="text-xs text-amber-800 leading-relaxed">
          <span className="font-bold">职业提醒：</span>
          新手的大纲只写 <span className="font-semibold">①核心事件</span> 和 <span className="font-semibold">②开篇钩子</span>，
          忽略 <span className="font-semibold text-red-700">③人物变化 · ④伏笔管理 · ⑤章末钩子</span>——这就是追读断崖的根本原因。
          AI 将为每一章强制生成五要素。
        </p>
      </div>

      {/* 配置行 */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">章节数</label>
          <input
            type="number"
            min={1}
            max={200}
            value={chapterCount}
            onChange={e => {
              const v = parseInt(e.target.value, 10)
              if (!isNaN(v) && v >= 1) setChapterCount(v)
            }}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1 w-20 focus:outline-none focus:ring-2 focus:ring-amber-300"
            disabled={status === 'loading'}
          />
          <span className="text-xs text-gray-400">章</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 whitespace-nowrap">模型</label>
          <select
            value={modelProfile}
            onChange={e => setModelProfile(e.target.value as 'default' | 'gemini')}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-amber-300"
            disabled={status === 'loading'}
          >
            <option value="default">本地 (qwen3)</option>
            <option value="gemini">Gemini</option>
          </select>
        </div>
        <button
          onClick={handleGenerate}
          disabled={status === 'loading'}
          className={clsx(
            'ml-auto flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            status === 'loading'
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-amber-500 hover:bg-amber-600 text-white shadow-sm hover:shadow'
          )}
        >
          {status === 'loading' ? (
            <><Loader2 size={14} className="animate-spin" />生成中…</>
          ) : (
            <><Sparkles size={14} />生成五要素大纲</>
          )}
        </button>
      </div>

      {/* 加载态 */}
      {status === 'loading' && (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Loader2 size={32} className="animate-spin text-amber-400" />
          <p className="text-sm text-gray-500">AI 正在规划 {chapterCount} 章的情节弧线…</p>
          <p className="text-xs text-gray-400">这需要 15–60 秒，请耐心等待</p>
        </div>
      )}

      {/* 错误态 */}
      {status === 'error' && (
        <div className="flex items-center gap-2 p-4 rounded-xl bg-red-50 border border-red-200">
          <AlertCircle size={16} className="text-red-500 shrink-0" />
          <p className="text-sm text-red-700">生成失败，请检查模型配置后重试</p>
          <button
            onClick={() => setStatus('idle')}
            className="ml-auto text-xs text-red-500 hover:underline"
          >
            重置
          </button>
        </div>
      )}

      {/* 结果：卷级分析 + 章节卡片 */}
      {status === 'done' && result && (
        <div>
          {/* 卷级分析 */}
          {result.volume_analysis && (
            <VolumeAnalysisCard analysis={result.volume_analysis} />
          )}

          {/* 章节数统计 + 展开/折叠全部 */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-green-500" />
              <span className="text-xs text-gray-600 font-medium">
                已生成 <span className="text-gray-900 font-bold">{result.chapters.length}</span> 章节计划
              </span>
            </div>
            <button
              onClick={() => setExpandAll(v => !v)}
              className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
              title="展开或折叠所有卡片，查看五要素详情"
            >
              {expandAll ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {expandAll ? '折叠卡片' : '展开卡片'}
            </button>
          </div>

          {/* 章节卡片列表 */}
          <div className="space-y-2 mb-4">
            {result.chapters.map((ch, i) => (
              <ExpandableChapterCard
                key={ch.number ?? i}
                card={ch}
                index={i}
                forceExpand={expandAll}
              />
            ))}
          </div>

          {/* 提交区 */}
          <div className="sticky bottom-0 bg-white pt-3 pb-1 border-t border-gray-100">
            <div className="flex items-center gap-3">
              <div className="flex-1 text-xs text-gray-400">
                确认无误后存入大纲树，之后可在树形视图中逐章编辑
              </div>
              <button
                onClick={() => { setStatus('idle'); setResult(null) }}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg"
                disabled={committing}
              >
                丢弃
              </button>
              <button
                onClick={handleCommit}
                disabled={committing}
                className={clsx(
                  'flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
                  committing
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-gray-900 hover:bg-gray-800 text-white shadow-sm'
                )}
              >
                {committing ? (
                  <><Loader2 size={13} className="animate-spin" />存入中…</>
                ) : (
                  <><ArrowRight size={13} />全部存入大纲树</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── ExpandableChapterCard（支持 forceExpand 外部控制）─────

function ExpandableChapterCard({
  card,
  index,
  forceExpand,
}: {
  card: ChapterCard
  index: number
  forceExpand: boolean
}) {
  const [localOpen, setLocalOpen] = useState(false)
  const isOpen = forceExpand || localOpen
  const pacing = PACING_CONFIG[card.pacing] ?? PACING_CONFIG.medium

  return (
    <div className={clsx(
      'border rounded-xl overflow-hidden transition-shadow',
      isOpen ? 'border-gray-300 shadow-sm' : 'border-gray-200'
    )}>
      {/* 卡片头 */}
      <button
        className="w-full flex items-center gap-2 px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
        onClick={() => setLocalOpen(v => !v)}
      >
        <span className="shrink-0 w-7 h-7 rounded-full bg-gray-800 text-white text-xs font-bold flex items-center justify-center">
          {card.number ?? index + 1}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-800 line-clamp-1">{card.title}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className={clsx('text-[11px] px-2 py-0.5 rounded-full border', pacing.color)}>
            {pacing.label}
          </span>
          <span className="text-[11px] text-gray-400">{(card.word_estimate ?? 3000).toLocaleString()}字</span>
          {isOpen
            ? <ChevronUp size={14} className="text-gray-400" />
            : <ChevronDown size={14} className="text-gray-400" />}
        </div>
      </button>

      {/* 五要素 */}
      {isOpen && (
        <div className="border-t border-gray-100 divide-y divide-gray-100">
          {ELEMENTS.map(el => {
            const Icon = el.icon
            const value = card[el.key]
            return (
              <div
                key={el.key}
                className={clsx(
                  'px-4 py-3',
                  el.highlight ? 'bg-red-50/60' : 'bg-white'
                )}
              >
                <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                  <span className={clsx('text-xs font-bold', el.iconColor)}>{el.num}</span>
                  <Icon size={12} className={el.iconColor} />
                  <span className="text-xs font-semibold text-gray-700">{el.label}</span>
                  <span className="text-[10px] text-gray-400">— {el.sublabel}</span>
                  <ElementBadge pro={el.pro} highlight={el.highlight} />
                </div>
                <p className={clsx(
                  'text-sm leading-relaxed',
                  el.highlight ? 'text-red-800 font-medium' : 'text-gray-700'
                )}>
                  {value || <span className="text-gray-400 italic">（未生成）</span>}
                </p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
