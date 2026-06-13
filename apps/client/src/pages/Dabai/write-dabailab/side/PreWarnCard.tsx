/**
 * 预警卡片 — 写前导演单展示。
 * 数据来源：侧栏手动生成/重跑 + 写章 SSE（首次生成）+ 落库记录 GET。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { AlertTriangle, Loader2, ShieldAlert } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiPreWarnRecord } from '../../../../types/dabaiLab'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../../store'
import { BEAT_KEYS, BEAT_LABELS } from './labels'

export interface PreWarnLive {
  running: boolean
  error?: string
}

interface Props {
  projectId: string
  chapterId: string
  /** 全书章号：第 1 章开写时 conflict 文案与后续章不同。 */
  chapterNumber: number
  live: PreWarnLive | null
  /** 自增信号：pre_warn_done 后 +1，触发重拉落库记录。 */
  refreshKey: number
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold text-gray-500">{title}</p>
      {children}
    </div>
  )
}

export default function PreWarnCard({ projectId, chapterId, chapterNumber, live, refreshKey }: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [record, setRecord] = useState<DabaiPreWarnRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    dabaiLabApi.getPreWarn(projectId, chapterId)
      .then(res => { if (!cancelled) setRecord(res.data.record) })
      .catch(() => { if (!cancelled) setRecord(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId, chapterId, refreshKey])

  const run = async () => {
    const hadRecord = !!record
    setRunning(true)
    try {
      const res = await dabaiLabApi.runPreWarn(projectId, chapterId, {
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...(llmProviderIdFromRoute(aiBackendRoute)
          ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
          : {}),
      })
      setRecord(res.data.record)
      if (res.data.error) toast(res.data.error, { icon: '⚠️' })
      else toast.success(hadRecord ? '导演单已重新生成' : '导演单已生成')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '导演单生成失败')
    } finally {
      setRunning(false)
    }
  }

  const showRunning = live?.running || running

  if (showRunning) {
    return (
      <button
        type="button"
        disabled
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-300 px-3 py-1.5 text-xs font-semibold text-white"
      >
        <Loader2 size={13} className="animate-spin" /> 导演单生成中…
      </button>
    )
  }

  const r = record?.result
  if (!r) {
    return (
      <div className="space-y-2 text-xs">
        <button
          type="button"
          onClick={() => void run()}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 font-semibold text-white hover:bg-amber-600"
        >
          <AlertTriangle size={13} />
          生成导演单
        </button>
        {live?.error ? (
          <p className="flex items-start gap-1.5 text-amber-600">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {live.error}
          </p>
        ) : null}
        <p className="text-gray-400">
          {loading ? '加载中…' : chapterNumber <= 1
            ? '开篇章：对齐章纲与开局台账；首次写章会自动生成'
            : '裁决章纲 vs 已写事实；首次写章会自动生成，也可在此手动生成'}
        </p>
      </div>
    )
  }

  const fact = r.fact_lock ?? {}
  const beats = r.beat_execution ?? {}
  const beatRows = BEAT_KEYS.filter(k => (beats[k] ?? '').trim())

  return (
    <div className="space-y-3 text-xs">
      <button
        type="button"
        onClick={() => void run()}
        className={clsx(
          'inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold text-white',
          'bg-amber-500 hover:bg-amber-600',
        )}
      >
        <AlertTriangle size={13} />
        重新生成导演单
      </button>

      <Section title="开笔事实锁定">
        <div className="flex flex-wrap gap-1">
          {fact.realm ? <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">境界·{fact.realm}</span> : null}
          {fact.location ? <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">位置·{fact.location}</span> : null}
          {(fact.on_stage ?? []).map(n => (
            <span key={n} className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">{n}</span>
          ))}
        </div>
        {(fact.forbidden?.length ?? 0) > 0 && (
          <p className="mt-1 flex items-start gap-1 text-rose-600">
            <ShieldAlert size={13} className="mt-0.5 shrink-0" />
            禁止：{fact.forbidden!.join('；')}
          </p>
        )}
      </Section>

      {(r.setup_alignment?.length ?? 0) > 0 && (
        <Section title="开局写法对齐（章纲按台账微调）">
          <ul className="space-y-1 text-gray-600">
            {r.setup_alignment!.map((n, i) => <li key={i}>· {n}</li>)}
          </ul>
          <p className="mt-1 text-[10px] text-gray-400">非报错：Bootstrap 台账与章纲表述不一致时的落法说明。</p>
        </Section>
      )}

      {(r.conflict_notes?.length ?? 0) > 0 && (
        <Section title="冲突裁决（章纲 vs 已写事实）">
          <ul className="space-y-1 text-amber-700">
            {r.conflict_notes!.map((n, i) => <li key={i}>· {n}</li>)}
          </ul>
        </Section>
      )}

      {r.opening_directive ? (
        <Section title="开头写法">
          <p className="text-gray-700">{r.opening_directive}</p>
        </Section>
      ) : null}

      {beatRows.length > 0 && (
        <Section title="五拍执行">
          <ul className="space-y-1">
            {beatRows.map(k => (
              <li key={k} className="text-gray-700">
                <span className="font-medium text-gray-500">{BEAT_LABELS[k]}</span>：{beats[k]}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(r.bridge_directives?.length ?? 0) > 0 && (
        <Section title="衔接交代">
          <ul className="space-y-1 text-gray-700">
            {r.bridge_directives!.map((n, i) => <li key={i}>· {n}</li>)}
          </ul>
        </Section>
      )}

      {(r.reminders?.length ?? 0) > 0 && (
        <Section title="提醒">
          <ul className="space-y-1 text-gray-500">
            {r.reminders!.map((n, i) => <li key={i}>· {n}</li>)}
          </ul>
        </Section>
      )}

      {record?.created_at ? (
        <p className="text-[10px] text-gray-300">{new Date(record.created_at).toLocaleString()}</p>
      ) : null}
    </div>
  )
}
