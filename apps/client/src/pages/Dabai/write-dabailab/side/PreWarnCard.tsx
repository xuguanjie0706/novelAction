/**
 * 预警卡片 — 写前导演单展示。
 * 数据来源：写章 SSE 实时事件（live）+ 落库记录（GET pre-warn，切章/生成完成后拉取）。
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, ShieldAlert } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiPreWarnRecord } from '../../../../types/dabaiLab'
import { BEAT_KEYS, BEAT_LABELS } from './labels'

export interface PreWarnLive {
  running: boolean
  error?: string
}

interface Props {
  projectId: string
  chapterId: string
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

export default function PreWarnCard({ projectId, chapterId, live, refreshKey }: Props) {
  const [record, setRecord] = useState<DabaiPreWarnRecord | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    dabaiLabApi.getPreWarn(projectId, chapterId)
      .then(res => { if (!cancelled) setRecord(res.data.record) })
      .catch(() => { if (!cancelled) setRecord(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId, chapterId, refreshKey])

  if (live?.running) {
    return (
      <p className="flex items-center gap-2 text-xs text-amber-600">
        <Loader2 size={14} className="animate-spin" /> 写前导演单生成中…
      </p>
    )
  }

  const r = record?.result
  if (!r) {
    return (
      <div className="space-y-2 text-xs text-gray-400">
        {live?.error ? (
          <p className="flex items-start gap-1.5 text-amber-600">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {live.error}
          </p>
        ) : null}
        <p>{loading ? '加载中…' : '暂无导演单——生成正文时自动产出（裁决章纲 vs 已写事实冲突）'}</p>
      </div>
    )
  }

  const fact = r.fact_lock ?? {}
  const beats = r.beat_execution ?? {}
  const beatRows = BEAT_KEYS.filter(k => (beats[k] ?? '').trim())

  return (
    <div className="space-y-3 text-xs">
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
