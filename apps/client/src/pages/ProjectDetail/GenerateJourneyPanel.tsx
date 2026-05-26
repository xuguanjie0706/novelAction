/**
 * GenerateJourneyPanel — Bootstrap 生成纪要面板
 *
 * 展示当前项目所有 Bootstrap Run 历史，SSE 实时更新进行中任务。
 */
import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, Loader2, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { authFetch } from '../../api/authFetch'
import { bootstrapRunsApi, type BootstrapRunHistoryItem } from '../../api/client'

// ── 事件文本格式化 ──────────────────────────────────────────────────────────
function runStatusLabel(status: string) {
  return {
    pending: '排队中',
    running: '生成中',
    awaiting_gate: '等待确认',
    done: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] ?? status
}

function runStatusColor(status: string) {
  return {
    pending: 'bg-gray-100 text-gray-600',
    running: 'bg-amber-100 text-amber-700',
    awaiting_gate: 'bg-indigo-100 text-indigo-700',
    done: 'bg-emerald-100 text-emerald-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-slate-100 text-slate-600',
  }[status] ?? 'bg-gray-100 text-gray-600'
}

function eventText(ev: Record<string, any>) {
  if (ev.event === 'step_start') return `开始：${ev.label || ev.step || '步骤'}`
  if (ev.event === 'step_done') {
    const detail = [ev.count != null ? `${ev.count} 条` : '', ev.preview || '']
      .filter(Boolean).join(' · ')
    return `完成：${ev.step || '步骤'}${detail ? `（${detail}）` : ''}`
  }
  if (ev.event === 'error') return `异常：${ev.message || ev.step || '未知错误'}`
  if (ev.event === 'gate_pending') {
    const st = ev.step ? String(ev.step) : ''
    const labels: Record<string, string> = {
      positioning: '等待你确认立项定位',
      power_systems: '等待你确认境界体系',
      characters: '等待你确认人物库',
      volumes: '等待你确认卷级骨架',
    }
    return labels[st] || '等待你确认后继续生成'
  }
  if (ev.event === 'gate_passed') return '已确认定位，继续生成'
  if (ev.event === 'cancelled') return ev.message || '生成已取消'
  if (ev.event === 'complete') return '整套流程已完成'
  return ev.event || '事件'
}

// ── 面板组件 ─────────────────────────────────────────────────────────────────
export default function GenerateJourneyPanel({ projectId }: { projectId: string }) {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<BootstrapRunHistoryItem[]>([])
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [cancellingRunId, setCancellingRunId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const aborters: AbortController[] = []

    const applyEvent = (runId: string, ev: Record<string, any>) => {
      setRuns((prev) => prev.map((r) => {
        if (r.run_id !== runId) return r
        const nextEvents = [...(r.events || []), ev]
        let nextStatus = r.status
        if (ev.event === 'complete') nextStatus = 'done'
        if (ev.event === 'gate_pending') nextStatus = 'awaiting_gate'
        if (ev.event === 'gate_passed') nextStatus = 'running'
        if (ev.event === 'error' && !ev.step) nextStatus = 'failed'
        return { ...r, status: nextStatus, events: nextEvents }
      }))
    }

    const subscribeRun = async (run: BootstrapRunHistoryItem) => {
      const controller = new AbortController()
      aborters.push(controller)
      try {
        const res = await authFetch(`/api/v1/bootstrap/runs/${run.run_id}/events`, { signal: controller.signal })
        if (!res.ok || !res.body) return
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (!raw || raw === '[DONE]') continue
            try {
              const ev = JSON.parse(raw)
              applyEvent(run.run_id, ev)
            } catch {
              // ignore malformed chunks
            }
          }
        }
      } catch {
        // keep silent; panel is best-effort
      }
    }

    const load = async () => {
      try {
        const res = await bootstrapRunsApi.listByProject(projectId)
        if (cancelled) return
        const items = res.data || []
        setRuns(items)
        items
          .filter((r) => r.status === 'running' || r.status === 'awaiting_gate')
          .forEach((r) => { void subscribeRun(r) })
      } finally {
        if (!cancelled) setLoadingRuns(false)
      }
    }

    void load()
    return () => {
      cancelled = true
      aborters.forEach((a) => a.abort())
    }
  }, [projectId])

  const cancelRun = async (runId: string) => {
    setCancellingRunId(runId)
    try {
      await bootstrapRunsApi.cancel(runId)
      setRuns((prev) =>
        prev.map((r) =>
          r.run_id === runId
            ? {
                ...r,
                status: 'cancelled',
                events: [...(r.events || []), { event: 'cancelled', message: '用户已取消生成' }],
              }
            : r
        )
      )
      toast.success('已请求停止生成')
    } catch {
      toast.error('停止生成失败')
    } finally {
      setCancellingRunId(null)
    }
  }

  return (
    <section className="mt-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900">
          <RefreshCw size={18} className="text-amber-400" />
          生成纪要
        </h2>
        <button
          type="button"
          onClick={() => navigate(`/bookshelf/${projectId}/recap`)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 transition-colors hover:bg-amber-100"
        >
          <Layers size={14} />
          结构化分区浏览
        </button>
      </div>
      <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        {loadingRuns ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 size={14} className="animate-spin" />载入生成记录...
          </div>
        ) : runs.length === 0 ? (
          <p className="text-sm text-gray-500">暂无一键生成记录。后续每次 AI 生成都会在这里保留完整流程日志。</p>
        ) : (
          <div className="space-y-4">
            {runs.map((run) => (
              <div key={run.run_id} className="rounded-xl border border-gray-100 p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs text-gray-400">
                    Run #{run.run_id.slice(0, 8)}
                    {run.created_at ? ` · ${new Date(run.created_at).toLocaleString('zh-CN')}` : ''}
                  </div>
                  <div className="flex items-center gap-2">
                    {(run.status === 'running' || run.status === 'awaiting_gate') && (
                      <button
                        type="button"
                        onClick={() => void cancelRun(run.run_id)}
                        disabled={cancellingRunId === run.run_id}
                        className="rounded-md border border-red-200 px-2 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        {cancellingRunId === run.run_id ? '停止中...' : '停止生成'}
                      </button>
                    )}
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${runStatusColor(run.status)}`}>
                      {runStatusLabel(run.status)}
                    </span>
                  </div>
                </div>
                {run.error_message && (
                  <div className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{run.error_message}</div>
                )}
                <div className="max-h-48 space-y-1 overflow-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                  {(run.events || []).length === 0 ? (
                    <div className="text-gray-400">暂无事件</div>
                  ) : (
                    (run.events || []).map((ev, idx) => (
                      <div key={`${run.run_id}-${idx}`}>- {eventText(ev)}</div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
