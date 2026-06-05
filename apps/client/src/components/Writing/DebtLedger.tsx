/**
 * @file DebtLedger.tsx — 债务看板组件
 *
 * 在写前预警面板（或场景面板顶部）展示从 /ai/chapter-ingredients 计算的
 * 结构化债务信息：
 *   - 爽点欠账 / 故事线断档（🔴 critical）
 *   - 读者承诺临期（🟡 warning）
 *   - 必须推进的故事线列表
 *   - 应操作的伏笔列表
 *
 * 数据来源：章节大纲节点 ID → POST /ai/chapter-ingredients
 * 调用时机：分场面板挂载时（与写前预警并行或先行调用）
 *
 * @param projectId    项目 ID
 * @param outlineNodeId 章节大纲节点 ID
 * @param chapterId    章节 ID（可选，用于读取 sort_order）
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, AlertCircle, CheckCircle2, RefreshCw, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { authFetch } from '../../api/authFetch'

// ── 类型 ─────────────────────────────────────────────────────────

interface DebtSummary {
  critical_count: number
  warning_count: number
  total_debt_count: number
  must_advance_storylines: Array<{ name: string; line_type: string; gap_chapters: number }>
  overdue_foreshadows: Array<{ title: string; op: string; is_overdue: boolean }>
  due_promises: Array<{ description: string }>
  debt_flags: Array<{ debt_type: string; description: string; severity: string; overdue_chapters: number }>
}

interface Props {
  projectId: string
  outlineNodeId: string | undefined
  chapterId?: string | undefined
  /** 是否自动加载（默认 true）；为 false 时只在点击刷新时触发 */
  autoLoad?: boolean
}

// ── 工具 ─────────────────────────────────────────────────────────

async function fetchDebtSummary(
  projectId: string,
  outlineNodeId: string,
  chapterId?: string,
): Promise<DebtSummary> {
  const res = await authFetch(`/api/v1/projects/${projectId}/ai/chapter-ingredients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      outline_node_id: outlineNodeId,
      chapter_id: chapterId ?? null,
    }),
  })
  if (!res.ok) throw new Error(`chapter-ingredients ${res.status}`)
  const data = await res.json()
  return data.debt_summary as DebtSummary
}

// ── 组件 ─────────────────────────────────────────────────────────

/**
 * 债务看板——展示本章债务标记，帮助作者/AI 在分场前了解必须解决的欠账。
 *
 * @param props Props
 */
export function DebtLedger({ projectId, outlineNodeId, chapterId, autoLoad = true }: Props) {
  const [summary, setSummary] = useState<DebtSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    if (!outlineNodeId) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDebtSummary(projectId, outlineNodeId, chapterId)
      setSummary(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (autoLoad) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outlineNodeId, chapterId])

  if (!outlineNodeId) return null

  // ── 空状态（无债务）────────────────────────────────────────────
  if (summary && summary.total_debt_count === 0) {
    return (
      <div className="flex items-center gap-1.5 text-emerald-600 text-[10px] px-2 py-1.5 rounded-novel bg-emerald-50/60 border border-emerald-200">
        <CheckCircle2 size={11} />
        本章无债务欠账，可自由创作
      </div>
    )
  }

  return (
    <div className="rounded-novel border border-novel-border bg-novel-card text-[10px] overflow-hidden">
      {/* 标题行 */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-novel-border/60 bg-novel-panel/60">
        <span className="font-medium text-novel-ink text-[11px]">🔴 债务看板</span>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-novel-ink-faint hover:text-novel-accent disabled:opacity-40 transition-novel"
          title="重新计算"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
        </button>
      </div>

      {/* 内容 */}
      <div className="px-2.5 py-1.5 space-y-1">
        {error && (
          <p className="text-red-500 text-[9px]">加载失败：{error}</p>
        )}

        {loading && !summary && (
          <p className="text-novel-ink-faint text-[9px] flex items-center gap-1">
            <Loader2 size={9} className="animate-spin" />计算中…
          </p>
        )}

        {summary && (
          <>
            {/* critical 债务 */}
            {summary.debt_flags.filter(d => d.severity === 'critical').map((d, i) => (
              <div key={i} className="flex items-start gap-1.5 text-red-600">
                <AlertCircle size={10} className="shrink-0 mt-0.5" />
                <span className="leading-tight">{d.description}</span>
              </div>
            ))}

            {/* warning 债务 */}
            {summary.debt_flags.filter(d => d.severity === 'warning').map((d, i) => (
              <div key={i} className="flex items-start gap-1.5 text-amber-600">
                <AlertTriangle size={10} className="shrink-0 mt-0.5" />
                <span className="leading-tight">{d.description}</span>
              </div>
            ))}

            {/* 必须推进的故事线 */}
            {summary.must_advance_storylines.length > 0 && (
              <div className="pt-0.5">
                <p className="text-novel-ink-faint mb-0.5">必须推进：</p>
                {summary.must_advance_storylines.map((s, i) => (
                  <div key={i} className="text-novel-ink-muted pl-2">
                    · 「{s.name}」（{s.line_type}）断档 {s.gap_chapters} 章
                  </div>
                ))}
              </div>
            )}

            {/* 应操作的伏笔 */}
            {summary.overdue_foreshadows.length > 0 && (
              <div className="pt-0.5">
                <p className="text-novel-ink-faint mb-0.5">伏笔应处理：</p>
                {summary.overdue_foreshadows.slice(0, 3).map((f, i) => (
                  <div key={i} className="text-novel-ink-muted pl-2">
                    · {f.op.toUpperCase()} 「{f.title}」{f.is_overdue ? ' ⚠逾期' : ''}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
