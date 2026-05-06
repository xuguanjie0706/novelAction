/**
 * @file RhythmMapPage.tsx
 * @description 节奏地图页：可视化全书章节的追读意愿曲线、钩子强度、故事线悬空警报。
 *
 * 数据来源：
 * - 章节列表：store.chapters（已缓存）+ 页面加载时主动拉取（防止直接跳转时为空）
 * - 分析均值：GET /ai/chapter-analysis-stats（页面加载时批量拉取，无 AI 成本）
 * - 新增分析：POST /ai/chapter-analysis（单次 LLM，写库后返回该章最新均值）
 * - 故事线悬空：GET /ai/storyline-gaps（页面加载时自动拉取，无 AI 成本）
 *
 * 持久化：分析记录存 DB（chapter_analysis_records 表），刷新后自动恢复。
 * 多次分析同一章节可获得更稳定的均值（avg_score / avg_hook_strength）。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  AlertTriangle,
  BarChart2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Play,
  PlayCircle,
  RefreshCw,
  TrendingUp,
} from 'lucide-react'
import clsx from 'clsx'

import { aiApi, chaptersApi } from '../api/client'
import { useAppStore, modelProfileFromRoute, llmProviderIdFromRoute } from '../store'
import type {
  Chapter,
  ChapterAnalysisStats,
  StorylineGapItem,
  StorylineGapsResult,
} from '../types'

// ── 常量 ─────────────────────────────────────────────────────────────────────

const HOOK_TYPE_LABELS: Record<string, string> = {
  cliffhanger: '生死悬念',
  curiosity:   '好奇钩子',
  promise:     '章末预告',
  emotional:   '情感共鸣',
  revelation:  '反转揭秘',
  weak:        '钩子偏弱',
  none:        '无钩子',
}

const HOOK_TYPE_COLOR: Record<string, string> = {
  cliffhanger: 'text-red-600',
  curiosity:   'text-blue-600',
  promise:     'text-amber-600',
  emotional:   'text-pink-600',
  revelation:  'text-purple-600',
  weak:        'text-gray-500',
  none:        'text-gray-400',
}

const DROP_RISK_COLOR: Record<string, string> = {
  low:    'bg-emerald-600',
  medium: 'bg-yellow-600',
  high:   'bg-red-600',
}

const DROP_RISK_LABEL: Record<string, string> = {
  low:    '低',
  medium: '中',
  high:   '高',
}

// ── 追读曲线（SVG） ───────────────────────────────────────────────────────────

/**
 * 全书追读意愿曲线（SVG 折线图）。
 * @param chapters - 有序章节列表
 * @param analysisMap - chapter_id → 均值统计（取 avg_score 作为纵轴）
 */
function ScoreCurve({
  chapters,
  analysisMap,
}: {
  chapters: Chapter[]
  analysisMap: Map<string, ChapterAnalysisStats>
}) {
  const scored = chapters.filter(c => analysisMap.has(c.id))

  if (scored.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 gap-2 text-gray-500 text-sm border border-dashed border-gray-200 rounded-lg bg-gray-50/80">
        <TrendingUp size={16} className="text-gray-400" />
        <span>点击章节行的「分析」按钮，曲线将在此实时更新</span>
      </div>
    )
  }

  if (scored.length === 1) {
    const s = analysisMap.get(scored[0].id)!
    return (
      <div className="flex items-center justify-center h-24 gap-2 text-gray-600 text-sm border border-gray-200 rounded-lg bg-white">
        <span>第{scored[0].sort_order + 1}章均分：</span>
        <span className="text-2xl font-bold text-amber-600">{s.avg_score.toFixed(1)}</span>
        <span className="text-gray-500">/ 10 · 再分析一章即显示曲线</span>
      </div>
    )
  }

  const W = 800
  const H = 96
  const padX = 16
  const padY = 12
  const scores = scored.map(c => analysisMap.get(c.id)!.avg_score)
  const xs = scored.map((_, i) => padX + (i / (scored.length - 1)) * (W - padX * 2))
  const ys = scores.map(s => H - padY - ((s - 1) / 9) * (H - padY * 2))
  const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ')
  const fill = `${path} L ${xs[xs.length - 1].toFixed(1)} ${H} L ${xs[0].toFixed(1)} ${H} Z`
  // 危险线 y 坐标（score=5）
  const dangerY = (H - padY - ((5 - 1) / 9) * (H - padY * 2)).toFixed(1)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-24" preserveAspectRatio="none">
      <defs>
        <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#d97706" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#d97706" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* 危险线 */}
      <line x1={padX} y1={dangerY} x2={W - padX} y2={dangerY}
        stroke="#9ca3af" strokeWidth="1" strokeDasharray="6 4" />
      <text x={W - padX + 2} y={dangerY} fill="#6b7280" fontSize="10" dominantBaseline="middle">5</text>
      {/* 填充 */}
      <path d={fill} fill="url(#scoreGrad)" />
      {/* 折线 */}
      <path d={path} fill="none" stroke="#d97706" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {/* 数据点 */}
      {xs.map((x, i) => (
        <circle key={i} cx={x} cy={ys[i]} r="4"
          fill={scores[i] >= 7 ? '#10b981' : scores[i] >= 5 ? '#eab308' : '#ef4444'}
          stroke="#ffffff" strokeWidth="1.5"
        />
      ))}
    </svg>
  )
}

// ── 单章行 ────────────────────────────────────────────────────────────────────

/**
 * 单章展示行：均值评分条、弃文风险、钩子强度格、运行次数、展开详情。
 *
 * @param chapter - 章节基础信息
 * @param stats - 该章的历史分析均值统计（有则展示，无则显示「—」）
 * @param loading - 是否正在分析
 * @param onRunAnalysis - 触发新一次分析的回调
 */
function ChapterRow({
  chapter,
  stats,
  loading,
  onRunAnalysis,
}: {
  chapter: Chapter
  stats?: ChapterAnalysisStats
  loading: boolean
  onRunAnalysis: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const chapterNum = chapter.sort_order + 1

  const scoreColor = stats
    ? stats.avg_score >= 7 ? 'bg-emerald-500' : stats.avg_score >= 5 ? 'bg-yellow-500' : 'bg-red-500'
    : 'bg-gray-200'

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      {/* 主行 */}
      <div
        className={clsx(
          'flex items-center gap-3 px-3 py-2.5 transition-colors',
          !!stats ? 'cursor-pointer hover:bg-gray-50' : 'hover:bg-gray-50/80',
        )}
        onClick={() => !!stats && setExpanded(e => !e)}
      >
        {/* 展开箭头 */}
        <span className="w-4 shrink-0 text-gray-400">
          {!!stats
            ? expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />
            : <span className="block w-4" />}
        </span>

        {/* 章节序号 */}
        <span className="w-7 text-center text-xs text-gray-500 font-mono shrink-0">{chapterNum}</span>

        {/* 标题 */}
        <span className="flex-1 text-sm text-gray-800 truncate min-w-0" title={chapter.title}>
          {chapter.title}
        </span>

        {/* 字数 */}
        <span className="text-xs text-gray-500 w-12 text-right shrink-0">
          {chapter.word_count ? `${(chapter.word_count / 1000).toFixed(1)}k` : '—'}
        </span>

        {/* 追读均值评分条 */}
        <div className="w-32 shrink-0 flex items-center gap-1.5">
          <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
            {stats && (
              <div
                className={clsx('h-full rounded-full transition-all duration-500', scoreColor)}
                style={{ width: `${stats.avg_score * 10}%` }}
              />
            )}
          </div>
          {stats ? (
            <span className="text-xs font-mono text-gray-700 w-14 text-right leading-none">
              {stats.avg_score.toFixed(1)}
              {stats.run_count > 1 && (
                <span className="text-gray-400 ml-0.5">×{stats.run_count}</span>
              )}
            </span>
          ) : (
            <span className="text-xs text-gray-300 w-14 text-right">—</span>
          )}
        </div>

        {/* 弃文风险 */}
        <div className="w-10 shrink-0 flex justify-center">
          {stats ? (
            <span className={clsx('text-xs px-1.5 py-0.5 rounded text-white font-medium', DROP_RISK_COLOR[stats.drop_risk])}>
              {DROP_RISK_LABEL[stats.drop_risk]}
            </span>
          ) : (
            <span className="text-xs text-gray-300">——</span>
          )}
        </div>

        {/* 钩子强度格（均值） */}
        <div className="w-14 shrink-0 flex gap-0.5 items-center">
          {stats
            ? Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className={clsx(
                  'h-2.5 flex-1 rounded-sm transition-colors',
                  i < Math.round(stats.avg_hook_strength) ? 'bg-amber-500' : 'bg-gray-200',
                )} />
              ))
            : <span className="text-xs text-gray-300 w-full text-center">——</span>
          }
        </div>

        {/* 操作按钮：「分析」/ 「再跑一次」 */}
        <div className="shrink-0">
          <button
            className={clsx(
              'px-3 py-1 rounded text-xs flex items-center gap-1.5 transition-colors font-medium border',
              loading
                ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                : stats
                  ? 'bg-amber-50 border-amber-200 text-amber-800 hover:bg-amber-100'
                  : 'bg-white border-gray-200 text-gray-600 hover:bg-amber-50 hover:border-amber-200 hover:text-amber-800',
            )}
            onClick={e => { e.stopPropagation(); onRunAnalysis() }}
            disabled={loading}
            title={stats ? `再跑一次（当前已有 ${stats.run_count} 次记录）` : '追读模拟 + 钩子检测'}
          >
            {loading
              ? <Loader2 size={11} className="animate-spin" />
              : stats ? <RefreshCw size={11} /> : <Play size={11} />}
            {stats ? '再跑一次' : '分析'}
          </button>
        </div>
      </div>

      {/* 展开详情：显示最新一次的定性分析 */}
      {expanded && !!stats && (
        <div className="px-4 pb-4 pt-2 bg-gray-50 border-t border-gray-100 space-y-3">
          {/* 均值摘要 */}
          {stats.run_count > 1 && (
            <div className="flex items-center gap-3 text-xs text-gray-500 pb-2 border-b border-gray-100">
              <span>共 <strong className="text-gray-700">{stats.run_count}</strong> 次分析</span>
              <span>追读均分 <strong className="text-amber-600">{stats.avg_score.toFixed(1)}</strong></span>
              <span>钩子均强度 <strong className="text-amber-600">{stats.avg_hook_strength.toFixed(1)}</strong></span>
              <span className="text-gray-400">（以下为最新一次定性结论）</span>
            </div>
          )}

          {/* 追读模拟定性 */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-amber-700 tracking-wide">📖 追读模拟</p>
            <p className="text-sm text-gray-700 italic leading-relaxed">"{stats.verdict}"</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="space-y-0.5">
                <span className="text-gray-500">吸引点</span>
                <p className="text-emerald-700">{stats.what_hooked || '—'}</p>
              </div>
              <div className="space-y-0.5">
                <span className="text-gray-500">阻力点</span>
                <p className="text-red-600">{stats.what_repelled || '—'}</p>
              </div>
            </div>
            <details className="text-xs group">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-700 list-none flex items-center gap-1">
                <ChevronRight size={11} className="group-open:rotate-90 transition-transform" />
                章末原文（送入模型的文本）
              </summary>
              <p className="mt-2 text-gray-600 leading-relaxed whitespace-pre-wrap border-l-2 border-gray-200 pl-3">
                {stats.hook_tail}
              </p>
            </details>
          </div>

          {/* 钩子检测定性 */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-emerald-700 tracking-wide">⚡ 钩子检测</p>
            <div className="flex items-center gap-3 text-xs">
              <span className={clsx('font-medium', HOOK_TYPE_COLOR[stats.hook_type])}>
                {HOOK_TYPE_LABELS[stats.hook_type] ?? stats.hook_type}
              </span>
              <span className="text-gray-500">均强度 {stats.avg_hook_strength.toFixed(1)}/5</span>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed">{stats.hook_analysis}</p>
            {stats.hook_suggestions.length > 0 && (
              <ul className="space-y-1">
                {stats.hook_suggestions.map((s, i) => (
                  <li key={i} className="text-xs text-amber-800 flex gap-1.5">
                    <span className="shrink-0">→</span><span>{s}</span>
                  </li>
                ))}
              </ul>
            )}
            {stats.matched_promises.length > 0 && (
              <div className="text-xs space-y-0.5">
                <span className="text-gray-500">关联承诺：</span>
                {stats.matched_promises.map(p => (
                  <span key={p.promise_id} className="text-blue-600 ml-1.5 inline-block">
                    [{p.promise_type}] {p.promise_text}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── 故事线悬空卡片 ────────────────────────────────────────────────────────────

function StorylineGapCard({ gap }: { gap: StorylineGapItem }) {
  return (
    <div className={clsx(
      'flex items-start gap-2.5 p-3 rounded-lg border',
      gap.severity === 'critical'
        ? 'border-red-200 bg-red-50'
        : 'border-amber-200 bg-amber-50/80',
    )}>
      <AlertTriangle size={14} className={clsx(
        'mt-0.5 shrink-0',
        gap.severity === 'critical' ? 'text-red-600' : 'text-amber-600',
      )} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{gap.storyline_name}</p>
        <p className="text-xs text-gray-600 mt-0.5 leading-relaxed">
          {gap.last_seen_chapter_number
            ? `最后出现第 ${gap.last_seen_chapter_number} 章，已缺席 ${gap.gap_size} 章`
            : `从未出现（全书已 ${gap.current_max_chapter} 章）`}
        </p>
        <p className="text-xs text-gray-500">类型：{gap.line_type} · 状态：{gap.status}</p>
      </div>
      <span className={clsx(
        'text-xs px-1.5 py-0.5 rounded font-medium shrink-0 mt-0.5',
        gap.severity === 'critical' ? 'bg-red-600 text-white' : 'bg-amber-500 text-white',
      )}>
        {gap.severity === 'critical' ? '严重' : '警告'}
      </span>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

/**
 * 节奏地图主页面。
 *
 * 布局：左侧（追读曲线 + 章节列表） | 右侧固定 288px（故事线悬空面板）
 * 高度：跟随 AppLayout 的 main 元素，使用 flex 撑满而非依赖 h-full。
 * 持久化：分析记录存 DB（chapter_analysis_records 表），刷新后通过 GET /chapter-analysis-stats 恢复。
 */
export default function RhythmMapPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { chapters, setChapters, aiBackendRoute } = useAppStore()

  const modelProfile = modelProfileFromRoute(aiBackendRoute)
  const llmProviderId = llmProviderIdFromRoute(aiBackendRoute)

  // 页面挂载时主动拉取章节（防止直接跳转时 store 为空）
  useEffect(() => {
    if (!projectId) return
    if (chapters.length === 0) {
      chaptersApi.list(projectId).then(r => setChapters(r.data)).catch(() => {})
    }
  }, [projectId])

  const sortedChapters = [...chapters].sort((a, b) => a.sort_order - b.sort_order)

  // ── DB 均值统计缓存（chapter_id → ChapterAnalysisStats） ──
  const [analysisMap, setAnalysisMap] = useState<Map<string, ChapterAnalysisStats>>(new Map())
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set())
  const [statsLoading, setStatsLoading] = useState(false)

  // 项目切换或页面首次加载时，从 DB 批量拉取均值统计
  useEffect(() => {
    if (!projectId) return
    setAnalysisMap(new Map())
    setStatsLoading(true)
    aiApi.chapterAnalysisStats(projectId)
      .then(r => {
        const m = new Map<string, ChapterAnalysisStats>()
        r.data.forEach(s => m.set(s.chapter_id, s))
        setAnalysisMap(m)
      })
      .catch(() => {})
      .finally(() => setStatsLoading(false))
  }, [projectId])

  // ── 故事线悬空 ──
  const [gapsResult, setGapsResult] = useState<StorylineGapsResult | null>(null)
  const [gapsLoading, setGapsLoading] = useState(false)
  const [gapThreshold, setGapThreshold] = useState(8)

  // ── 批量运行 ──
  const [batchRunning, setBatchRunning] = useState(false)
  const batchCancelRef = useRef(false)

  const fetchGaps = useCallback(async () => {
    if (!projectId) return
    setGapsLoading(true)
    try {
      const res = await aiApi.storylineGaps(projectId, gapThreshold)
      setGapsResult(res.data)
    } catch {
      toast.error('故事线检测失败')
    } finally {
      setGapsLoading(false)
    }
  }, [projectId, gapThreshold])

  useEffect(() => { fetchGaps() }, [fetchGaps])

  /**
   * 单章综合分析：单次 LLM 调用，后端写库后返回该章最新均值统计，更新 analysisMap。
   * 每次调用都会新增一条历史记录，avg_score 会随次数增加而逐渐稳定。
   */
  const runAnalysis = useCallback(async (chapter: Chapter) => {
    if (!projectId) return
    setLoadingIds(s => new Set(s).add(chapter.id))
    try {
      const res = await aiApi.chapterAnalysis(projectId, chapter.id, modelProfile, llmProviderId)
      setAnalysisMap(m => new Map(m).set(chapter.id, res.data))
    } catch {
      toast.error(`分析失败：${chapter.title}`)
    } finally {
      setLoadingIds(s => { const n = new Set(s); n.delete(chapter.id); return n })
    }
  }, [projectId, modelProfile, llmProviderId])

  /** 批量分析全书，章节串行，可随时取消。 */
  const runBatchAnalysis = useCallback(async () => {
    if (!projectId || batchRunning) return
    batchCancelRef.current = false
    setBatchRunning(true)
    const toRun = sortedChapters.filter(c => (c.word_count ?? 0) > 100)
    for (const chapter of toRun) {
      if (batchCancelRef.current) break
      await runAnalysis(chapter)
    }
    setBatchRunning(false)
    if (!batchCancelRef.current) toast.success('全书分析完成')
  }, [projectId, batchRunning, sortedChapters, runAnalysis])

  // ── 统计 ──
  const analyzedCount = analysisMap.size
  const avgScore = analyzedCount > 0
    ? (Array.from(analysisMap.values()).reduce((s, r) => s + r.avg_score, 0) / analyzedCount).toFixed(1)
    : null
  const highRiskCount = Array.from(analysisMap.values()).filter(r => r.drop_risk === 'high').length

  // ── 渲染 ──
  // 不用 h-full，直接 flex 撑满 main 的剩余高度
  return (
    <div className="flex flex-col bg-[#FAF8F4] text-gray-800" style={{ height: '100%' }}>

      {/* ── 顶栏 ── */}
      <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between gap-4 shrink-0 bg-white">
        <div className="flex items-center gap-2">
          <BarChart2 size={17} className="text-amber-600" />
          <h1 className="text-sm font-semibold text-gray-900">节奏地图</h1>
          <span className="text-xs text-gray-500 hidden sm:inline">· 追读曲线 · 钩子强度 · 故事线悬空</span>
        </div>
        <div className="flex items-center gap-3">
          {statsLoading ? (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Loader2 size={11} className="animate-spin" />恢复历史记录中…
            </span>
          ) : avgScore ? (
            <span className="text-xs text-gray-500">
              均分 <span className="text-amber-600 font-mono font-bold">{avgScore}</span>
              {` · ${analyzedCount}/${sortedChapters.length} 章`}
              {highRiskCount > 0 && <span className="ml-2 text-red-600">· {highRiskCount} 章高危</span>}
            </span>
          ) : null}
          <button
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 font-medium transition-colors',
              batchRunning
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-amber-500 hover:bg-amber-600 text-white',
            )}
            onClick={() => {
              if (batchRunning) {
                batchCancelRef.current = true
                setBatchRunning(false)
              } else {
                runBatchAnalysis()
              }
            }}
          >
            {batchRunning
              ? <><Loader2 size={12} className="animate-spin" />停止</>
              : <><PlayCircle size={12} />全书分析</>}
          </button>
        </div>
      </div>

      {/* ── 内容区（左右两栏） ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* 左栏：追读曲线 + 章节列表 */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          {/* 追读曲线 */}
          <div className="px-5 pt-4 pb-3 shrink-0 border-b border-gray-200 bg-white">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-gray-500 font-medium">追读意愿曲线</p>
              {analyzedCount > 0 && (
                <p className="text-xs text-gray-400">{analyzedCount} / {sortedChapters.length} 章已分析</p>
              )}
            </div>
            <ScoreCurve chapters={sortedChapters} analysisMap={analysisMap} />
          </div>

          {/* 表头 */}
          <div className="px-3 py-2 flex items-center gap-3 text-xs text-gray-500 border-b border-gray-200 shrink-0 bg-[#FAF8F4]">
            <span className="w-4" />
            <span className="w-7 text-center">#</span>
            <span className="flex-1">章节标题</span>
            <span className="w-12 text-right">字数</span>
            <span className="w-28 text-center">追读评分</span>
            <span className="w-10 text-center">弃文</span>
            <span className="w-14 text-center">钩子强</span>
            <span className="w-24 text-right">操作</span>
          </div>

          {/* 章节列表（可滚动） */}
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
            {sortedChapters.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-gray-500 text-sm gap-2">
                <BarChart2 size={28} className="text-gray-300" />
                <p>暂无章节 · 请先在写作页创建章节</p>
              </div>
            ) : (
              sortedChapters.map(ch => (
                <ChapterRow
                  key={ch.id}
                  chapter={ch}
                  stats={analysisMap.get(ch.id)}
                  loading={loadingIds.has(ch.id)}
                  onRunAnalysis={() => runAnalysis(ch)}
                />
              ))
            )}
          </div>
        </div>

        {/* 右栏：故事线悬空面板（固定 288px） */}
        <div
          className="shrink-0 border-l border-gray-200 flex flex-col overflow-hidden bg-white"
          style={{ width: 288 }}
        >
          {/* 面板标题 */}
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between shrink-0 bg-white">
            <div>
              <p className="text-sm font-semibold text-gray-900">故事线悬空检测</p>
              {gapsResult && (
                <p className="text-xs text-gray-500 mt-0.5">
                  {gapsResult.checked_storylines} 条活跃线 · {gapsResult.total_chapters} 章
                </p>
              )}
            </div>
            <button
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700 transition-colors"
              onClick={fetchGaps}
              disabled={gapsLoading}
              title="重新检测"
            >
              <RefreshCw size={13} className={gapsLoading ? 'animate-spin' : ''} />
            </button>
          </div>

          {/* 阈值调节 */}
          <div className="px-4 py-2.5 border-b border-gray-100 shrink-0 flex items-center gap-2 bg-[#FAF8F4]/50">
            <span className="text-xs text-gray-500 shrink-0">悬空阈值</span>
            <input
              type="range" min={3} max={20} step={1}
              value={gapThreshold}
              onChange={e => setGapThreshold(Number(e.target.value))}
              className="flex-1 accent-amber-500 cursor-pointer"
            />
            <span className="text-xs font-mono text-amber-600 font-bold w-5 text-right">{gapThreshold}</span>
            <span className="text-xs text-gray-500">章</span>
          </div>

          {/* 悬空列表 */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 bg-[#FAF8F4]/30">
            {gapsLoading ? (
              <div className="flex items-center justify-center h-20 gap-2 text-sm text-gray-500">
                <Loader2 size={14} className="animate-spin text-amber-500" />
                <span>检测中…</span>
              </div>
            ) : !gapsResult ? null
            : gapsResult.checked_storylines === 0 ? (
              <div className="flex flex-col items-center justify-center h-24 text-gray-500 text-xs gap-1 text-center">
                <AlertTriangle size={18} className="text-gray-300" />
                <p>没有活跃的故事线</p>
                <p className="text-gray-400">请先在世界页添加故事线<br/>并将状态设为 active/climax</p>
              </div>
            ) : gapsResult.gaps.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-24 text-gray-600 text-sm gap-1">
                <span className="text-2xl text-emerald-500">✓</span>
                <p>所有活跃故事线均在阈值内</p>
              </div>
            ) : (
              gapsResult.gaps.map(gap => (
                <StorylineGapCard key={gap.storyline_id} gap={gap} />
              ))
            )}
          </div>

          {/* 图例 */}
          <div className="px-4 py-3 border-t border-gray-200 shrink-0 space-y-1.5 bg-white">
            <p className="text-xs text-gray-500 font-medium mb-2">图例</p>
            {[
              { color: 'bg-emerald-500', label: '追读分 7-10（高意愿）' },
              { color: 'bg-yellow-500', label: '追读分 5-6（中等）' },
              { color: 'bg-red-500',    label: '追读分 1-4（高危弃书）' },
            ].map(({ color, label }) => (
              <div key={label} className="flex items-center gap-2">
                <div className={clsx('w-3 h-3 rounded-full shrink-0', color)} />
                <span className="text-xs text-gray-600">{label}</span>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <div className="flex gap-0.5 shrink-0">
                {[1,1,1,0,0].map((on, i) => (
                  <div key={i} className={clsx('w-2 h-2.5 rounded-sm', on ? 'bg-amber-500' : 'bg-gray-200')} />
                ))}
              </div>
              <span className="text-xs text-gray-600">钩子强度（格数/5）</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
