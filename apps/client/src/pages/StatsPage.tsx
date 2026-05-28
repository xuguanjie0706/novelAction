/**
 * @file StatsPage.tsx — 数据统计页
 * 数据来源：GET /api/v1/stats/summary
 * 样式约定：白卡 + amber 强调色 + gray 中性，与 BookshelfPage 一致
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  BookMarked,
  BookOpen,
  Brain,
  Calendar,
  ChevronLeft,
  Feather,
  FileText,
  Flame,
  Loader2,
  PenLine,
  Star,
  TrendingUp,
  Zap,
} from 'lucide-react'
import HomeSidebar from '../components/Home/HomeSidebar'
import HomeTopBar from '../components/Home/HomeTopBar'
import { statsApi, type StatsSummary } from '../api/projects'

// ─── 题材颜色表 ──────────────────────────────────────────────
const GENRE_COLORS: Record<string, string> = {
  '玄幻': '#7c3aed',
  '修真': '#6d28d9',
  '仙侠': '#9333ea',
  '都市': '#0ea5e9',
  '现代': '#0284c7',
  '悬疑': '#374151',
  '惊悚': '#1f2937',
  '历史': '#92400e',
  '古言': '#b45309',
  '言情': '#db2777',
  '科幻': '#0f766e',
  '奇幻': '#059669',
  '武侠': '#b91c1c',
  '其他': '#6b7280',
}

function getGenreColor(genre: string): string {
  for (const key of Object.keys(GENRE_COLORS)) {
    if (genre.includes(key)) return GENRE_COLORS[key]
  }
  return GENRE_COLORS['其他']
}

// ─── 状态中文映射 ────────────────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  drafting: '规划中',
  writing: '连载中',
  completed: '已完结',
}
const STATUS_COLORS: Record<string, string> = {
  drafting: '#f59e0b',
  writing: '#10b981',
  completed: '#6366f1',
}

// ─── 数字格式化工具 ──────────────────────────────────────
function formatWords(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toLocaleString()
}

// ─── KPI 卡片 ────────────────────────────────────────────
interface KpiCardProps {
  icon: React.ReactNode
  label: string
  value: string | number
  sub?: string
  accent?: string
}

function KpiCard({ icon, label, value, sub, accent = 'text-amber-500' }: KpiCardProps) {
  return (
    <div className="flex items-start gap-4 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gray-50 ${accent}`}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm text-gray-500">{label}</div>
        <div className="mt-1 text-2xl font-bold text-gray-950 leading-tight">{value}</div>
        {sub && <div className="mt-0.5 text-xs text-gray-400">{sub}</div>}
      </div>
    </div>
  )
}

// ─── 30 天趋势柱图 ───────────────────────────────────────
function TrendChart({ data }: { data: StatsSummary['trend_30'] }) {
  const maxWords = Math.max(...data.map(d => d.words), 1)
  const totalWords = data.reduce((s, d) => s + d.words, 0)
  const activeDays = data.filter(d => d.words > 0).length

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp size={18} className="text-amber-500" />
          <span className="font-semibold text-gray-900">近 30 天字数趋势</span>
        </div>
        <div className="flex gap-4 text-sm text-gray-500">
          <span>累计 <span className="font-bold text-gray-900">{formatWords(totalWords)}</span> 字</span>
          <span>活跃 <span className="font-bold text-gray-900">{activeDays}</span> 天</span>
        </div>
      </div>

      {/* 柱状图区域 */}
      <div className="mt-5 flex items-end gap-[2px] h-[80px]">
        {data.map((item, i) => {
          const height = Math.max(item.words > 0 ? Math.round((item.words / maxWords) * 76) : 0, item.words > 0 ? 4 : 0)
          const isToday = i === data.length - 1
          const isWeekend = new Date(item.date).getDay() === 0 || new Date(item.date).getDay() === 6
          return (
            <div
              key={item.date}
              className="group relative flex-1 flex flex-col items-center justify-end"
              title={`${item.date} (周${item.weekday_label}): ${item.words.toLocaleString()} 字`}
            >
              <div
                className={`w-full rounded-t transition-all ${
                  isToday
                    ? 'bg-amber-500'
                    : isWeekend
                    ? 'bg-violet-300'
                    : item.words > 0
                    ? 'bg-amber-200 group-hover:bg-amber-400'
                    : 'bg-gray-100'
                }`}
                style={{ height: `${height}px` }}
              />
              {/* Tooltip */}
              {item.words > 0 && (
                <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10 whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white shadow">
                  {item.words.toLocaleString()} 字
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 日期轴标注：只显示每5天的日期 */}
      <div className="mt-1 flex text-[10px] text-gray-400">
        {data.map((item, i) => (
          <div key={item.date} className="flex-1 text-center">
            {i === 0 || i === 14 || i === 29 ? item.date.slice(5) : ''}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── 题材分布 ────────────────────────────────────────────
function GenreChart({ data, total }: { data: StatsSummary['genre_distribution']; total: number }) {
  if (data.length === 0) return null

  // 构建 conic-gradient 饼图
  let accPct = 0
  const segments = data.map(({ genre, count }) => {
    const pct = total > 0 ? (count / total) * 100 : 0
    const color = getGenreColor(genre)
    const from = accPct
    const to = accPct + pct
    accPct = to
    return { genre, count, pct, color, from, to }
  })

  const gradientStops = segments
    .map(s => `${s.color} ${s.from.toFixed(1)}% ${s.to.toFixed(1)}%`)
    .join(', ')

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <BookMarked size={18} className="text-violet-500" />
        <span className="font-semibold text-gray-900">题材分布</span>
      </div>
      <div className="flex items-center gap-6">
        {/* 饼图 */}
        <div
          className="shrink-0 h-[100px] w-[100px] rounded-full"
          style={{ background: `conic-gradient(${gradientStops})` }}
        />
        {/* 图例 */}
        <div className="flex flex-col gap-2 min-w-0 flex-1">
          {segments.map(s => (
            <div key={s.genre} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.color }} />
              <span className="text-gray-700 truncate">{s.genre}</span>
              <span className="ml-auto font-medium text-gray-900 shrink-0">{s.count} 部</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── 状态分布 ────────────────────────────────────────────
function StatusChart({ data, total }: { data: StatsSummary['status_distribution']; total: number }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Activity size={18} className="text-emerald-500" />
        <span className="font-semibold text-gray-900">作品状态</span>
      </div>
      <div className="space-y-3">
        {data.map(({ status, count }) => {
          const label = STATUS_LABELS[status] || status
          const color = STATUS_COLORS[status] || '#6b7280'
          const pct = total > 0 ? Math.round((count / total) * 100) : 0
          return (
            <div key={status}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-700">{label}</span>
                <span className="font-medium text-gray-900">{count} 部 · {pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── 写作习惯（星期分布） ────────────────────────────────
function WeekdayChart({ data }: { data: StatsSummary['weekday_distribution'] }) {
  const maxPct = Math.max(...data.map(d => d.pct), 1)
  const bestDay = data.reduce((a, b) => (a.pct > b.pct ? a : b), data[0])

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-blue-500" />
          <span className="font-semibold text-gray-900">写作习惯（近 90 天）</span>
        </div>
        {bestDay && bestDay.words > 0 && (
          <span className="text-xs text-gray-500">
            最勤奋：<span className="font-semibold text-gray-800">周{bestDay.label}</span>
          </span>
        )}
      </div>
      <div className="flex items-end gap-3 h-[70px]">
        {data.map(item => {
          const height = maxPct > 0 ? Math.max(item.pct > 0 ? Math.round((item.pct / maxPct) * 62) : 0, item.pct > 0 ? 4 : 0) : 0
          const isWeekend = item.weekday >= 5
          const isBest = item.weekday === bestDay?.weekday
          return (
            <div key={item.weekday} className="flex-1 flex flex-col items-center gap-1.5">
              <div
                className={`w-full rounded-t transition-all ${
                  isBest ? 'bg-blue-500' : isWeekend ? 'bg-violet-300' : 'bg-blue-200'
                }`}
                style={{ height: `${height}px` }}
              />
              <span className="text-xs text-gray-500">周{item.label}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex gap-3">
        {data.map(item => (
          <div key={item.weekday} className="flex-1 text-center text-[11px] text-gray-400">
            {item.pct > 0 ? `${item.pct}%` : '—'}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── 作品进度表格 ────────────────────────────────────────
function ProjectsTable({ data }: { data: StatsSummary['projects_progress'] }) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <BookOpen size={36} className="mx-auto text-gray-300" />
        <p className="mt-3 text-sm text-gray-500">暂无作品数据</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <FileText size={18} className="text-amber-500" />
        <span className="font-semibold text-gray-900">作品进度一览</span>
        <span className="ml-auto text-xs text-gray-400">最近更新的 10 部</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500">
              <th className="px-5 py-3 font-medium">书名</th>
              <th className="px-3 py-3 font-medium">题材</th>
              <th className="px-3 py-3 font-medium">状态</th>
              <th className="px-3 py-3 font-medium">章节</th>
              <th className="px-3 py-3 font-medium w-40">字数进度</th>
              <th className="px-3 py-3 font-medium text-right">质检分</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {data.map(p => {
              const color = getGenreColor(p.genre)
              const statusColor = STATUS_COLORS[p.status] || '#6b7280'
              const statusLabel = STATUS_LABELS[p.status] || p.status
              const qualityColor = p.avg_quality >= 8 ? 'text-emerald-600' : p.avg_quality >= 6 ? 'text-amber-600' : p.avg_quality > 0 ? 'text-red-500' : 'text-gray-400'
              return (
                <tr key={p.id} className="hover:bg-gray-50/70 transition-colors">
                  <td className="px-5 py-3.5">
                    <span className="font-medium text-gray-900 line-clamp-1">{p.title}</span>
                  </td>
                  <td className="px-3 py-3.5">
                    <span
                      className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                      style={{ background: color }}
                    >
                      {p.genre}
                    </span>
                  </td>
                  <td className="px-3 py-3.5">
                    <span
                      className="inline-flex items-center gap-1 text-xs font-medium"
                      style={{ color: statusColor }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: statusColor }} />
                      {statusLabel}
                    </span>
                  </td>
                  <td className="px-3 py-3.5 text-gray-600">{p.chapter_count} 章</td>
                  <td className="px-3 py-3.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-gray-100">
                        <div
                          className="h-full rounded-full bg-amber-400"
                          style={{ width: `${Math.min(p.progress_pct, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 shrink-0">
                        {formatWords(p.actual_words)}
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">
                      目标 {formatWords(p.target_words)} · {p.progress_pct.toFixed(1)}%
                    </div>
                  </td>
                  <td className="px-3 py-3.5 text-right">
                    <span className={`font-semibold ${qualityColor}`}>
                      {p.avg_quality > 0 ? p.avg_quality.toFixed(1) : '—'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── AI 生成统计卡片 ─────────────────────────────────────
function AiStatsCards({ data }: { data: Pick<StatsSummary, 'bootstrap_count' | 'ai_call_count_30' | 'total_quality_debts' | 'debt_by_severity'> }) {
  const highDebt = data.debt_by_severity?.high || 0
  const medDebt = data.debt_by_severity?.medium || 0
  const lowDebt = data.debt_by_severity?.low || 0

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50">
            <Zap size={20} className="text-violet-500" />
          </div>
          <span className="font-semibold text-gray-900">AI 一键生成</span>
        </div>
        <div className="text-3xl font-bold text-gray-950">{data.bootstrap_count}</div>
        <div className="mt-1 text-xs text-gray-400">次完整世界观生成</div>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50">
            <Brain size={20} className="text-blue-500" />
          </div>
          <span className="font-semibold text-gray-900">AI 调用次数</span>
        </div>
        <div className="text-3xl font-bold text-gray-950">{data.ai_call_count_30.toLocaleString()}</div>
        <div className="mt-1 text-xs text-gray-400">近 30 天 API 调用</div>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50">
            <Star size={20} className="text-red-400" />
          </div>
          <span className="font-semibold text-gray-900">质检欠债</span>
        </div>
        <div className="text-3xl font-bold text-gray-950">{data.total_quality_debts}</div>
        <div className="mt-2 flex gap-3 text-xs">
          {highDebt > 0 && <span className="text-red-500">高 {highDebt}</span>}
          {medDebt > 0 && <span className="text-amber-500">中 {medDebt}</span>}
          {lowDebt > 0 && <span className="text-gray-400">低 {lowDebt}</span>}
          {data.total_quality_debts === 0 && <span className="text-emerald-500">暂无待处理欠债</span>}
        </div>
      </div>
    </div>
  )
}

// ─── 主页面 ──────────────────────────────────────────────
export default function StatsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<StatsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    statsApi
      .summary()
      .then(res => setData(res.data))
      .catch(() => setError('统计数据加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [])

  /** 导航处理：复用 HomeSidebar 的路由约定 */
  const handleNavigate = (target: string) => {
    const routes: Record<string, string> = {
      home: '/',
      projects: '/bookshelf',
      write: '/bookshelf',
      wallet: '/wallet',
      fanqie: '/fanqie',
      coherence: '/coherence-check',
    }
    if (routes[target]) navigate(routes[target])
  }

  const todayWords = data?.today_words ?? 0

  // 作品状态合计（用于百分比）
  const totalProjects = data?.total_projects ?? 0

  // 30 天趋势数据最大值（用于空状态判断）
  const hasTrendData = useMemo(
    () => (data?.trend_30 ?? []).some(d => d.words > 0),
    [data],
  )

  return (
    <div className="flex min-h-screen bg-gray-50">
      <HomeSidebar todayWords={todayWords} onNavigate={handleNavigate} activeId="stats" />

      <div className="flex flex-1 flex-col min-w-0">
        <HomeTopBar />

        <main className="flex-1 overflow-auto px-6 py-8">
          {/* 页面标题 */}
          <div className="mb-6 flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-white hover:text-gray-700 transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
            <div className="flex items-center gap-2">
              <BarChart3 size={22} className="text-amber-500" />
              <h1 className="text-xl font-bold text-gray-950">数据统计</h1>
            </div>
          </div>

          {/* 加载态 */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-32">
              <Loader2 size={36} className="animate-spin text-amber-400" />
              <p className="mt-4 text-sm text-gray-400">正在统计创作数据…</p>
            </div>
          )}

          {/* 错误态 */}
          {!loading && error && (
            <div className="flex flex-col items-center justify-center py-32">
              <div className="rounded-xl border border-red-100 bg-red-50 px-8 py-6 text-center">
                <p className="text-red-500">{error}</p>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="mt-4 rounded-lg bg-red-500 px-4 py-2 text-sm text-white hover:bg-red-600"
                >
                  重新加载
                </button>
              </div>
            </div>
          )}

          {/* 数据展示 */}
          {!loading && !error && data && (
            <div className="max-w-[1200px] space-y-6">
              {/* ── KPI 卡片行 ── */}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
                <KpiCard
                  icon={<PenLine size={22} />}
                  label="累计字数"
                  value={formatWords(data.total_words)}
                  sub="全部作品合计"
                  accent="text-amber-500"
                />
                <KpiCard
                  icon={<BookOpen size={22} />}
                  label="总作品数"
                  value={data.total_projects}
                  sub={`目标累计 ${formatWords(data.projects_progress.reduce((s, p) => s + p.target_words, 0))}`}
                  accent="text-violet-500"
                />
                <KpiCard
                  icon={<FileText size={22} />}
                  label="总章节数"
                  value={data.total_chapters}
                  sub="未删除章节"
                  accent="text-blue-500"
                />
                <KpiCard
                  icon={<Flame size={22} />}
                  label="连续创作"
                  value={`${data.streak_days} 天`}
                  sub={data.streak_days > 0 ? '继续保持！' : '今天开始写吧'}
                  accent={data.streak_days > 0 ? 'text-orange-500' : 'text-gray-400'}
                />
                <KpiCard
                  icon={<Feather size={22} />}
                  label="今日字数"
                  value={formatWords(data.today_words)}
                  sub={`本月活跃 ${data.writing_days_30} 天`}
                  accent="text-emerald-500"
                />
                <KpiCard
                  icon={<Star size={22} />}
                  label="平均质检分"
                  value={data.avg_quality_score > 0 ? data.avg_quality_score.toFixed(1) : '—'}
                  sub={data.avg_quality_score >= 8 ? '优秀水准 🎉' : data.avg_quality_score >= 6 ? '良好水准' : data.avg_quality_score > 0 ? '待提升' : '暂无质检记录'}
                  accent={data.avg_quality_score >= 8 ? 'text-emerald-500' : data.avg_quality_score >= 6 ? 'text-amber-500' : 'text-gray-400'}
                />
              </div>

              {/* ── 趋势图 ── */}
              {hasTrendData ? (
                <TrendChart data={data.trend_30} />
              ) : (
                <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-center">
                  <Activity size={32} className="mx-auto text-gray-300" />
                  <p className="mt-3 text-sm text-gray-400">近 30 天暂无写作记录，开始创作就能看到趋势图！</p>
                </div>
              )}

              {/* ── 分布 + 习惯 ── */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <GenreChart data={data.genre_distribution} total={totalProjects} />
                <StatusChart data={data.status_distribution} total={totalProjects} />
                <WeekdayChart data={data.weekday_distribution} />
              </div>

              {/* ── AI 统计 ── */}
              <AiStatsCards
                data={{
                  bootstrap_count: data.bootstrap_count,
                  ai_call_count_30: data.ai_call_count_30,
                  total_quality_debts: data.total_quality_debts,
                  debt_by_severity: data.debt_by_severity,
                }}
              />

              {/* ── 作品进度表格 ── */}
              <ProjectsTable data={data.projects_progress} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
