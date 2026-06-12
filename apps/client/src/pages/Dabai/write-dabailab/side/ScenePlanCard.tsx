/**
 * 分场卡片 — 章前场面调度单展示。
 * 数据来源：侧栏手动生成/重跑 + 写章 SSE（首次生成）+ 落库记录 GET。
 */
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { AlertTriangle, Clapperboard, Loader2 } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiScenePlanItem, DabaiScenePlanRecord } from '../../../../types/dabaiLab'
import { llmProviderIdFromRoute, modelProfileFromRoute, useAppStore } from '../../../../store'

export interface ScenePlanLive {
  running: boolean
  error?: string
}

interface Props {
  projectId: string
  chapterId: string
  live: ScenePlanLive | null
  /** 自增信号：scene_plan_done 后 +1，触发重拉落库记录。 */
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

function SceneBlock({ scene, index }: { scene: DabaiScenePlanItem; index: number }) {
  const cast = (scene.characters_on_stage ?? []).filter(Boolean)
  const ammo = (scene.dialogue_ammo ?? []).filter(Boolean)

  return (
    <div className="rounded-lg border border-violet-100 bg-violet-50/40 p-2.5">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-semibold text-violet-800">
          场{scene.order ?? index + 1}·{scene.name || '未命名'}
        </span>
        {scene.location ? (
          <span className="text-[10px] text-sky-700">{scene.location}</span>
        ) : null}
        {scene.word_budget ? (
          <span className="ml-auto text-[10px] tabular-nums text-gray-400">~{scene.word_budget}字</span>
        ) : null}
      </div>

      {scene.goal ? (
        <p className="mb-1 text-[10px] text-violet-600">节拍：{scene.goal}</p>
      ) : null}

      {cast.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-1">
          {cast.map(n => (
            <span key={n} className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] text-gray-600">{n}</span>
          ))}
        </div>
      )}

      {scene.event ? <p className="text-gray-700">{scene.event}</p> : null}

      {ammo.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-gray-600">
          {ammo.map((line, i) => (
            <li key={i}>「{line}」</li>
          ))}
        </ul>
      )}

      {scene.sensory_anchor ? (
        <p className="mt-1 text-[10px] text-amber-700">感官：{scene.sensory_anchor}</p>
      ) : null}

      {scene.end_turn ? (
        <p className="mt-1 text-[10px] text-gray-500">场末：{scene.end_turn}</p>
      ) : null}
    </div>
  )
}

export default function ScenePlanCard({ projectId, chapterId, live, refreshKey }: Props) {
  const aiBackendRoute = useAppStore(s => s.aiBackendRoute)
  const [record, setRecord] = useState<DabaiScenePlanRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    dabaiLabApi.getScenePlan(projectId, chapterId)
      .then(res => { if (!cancelled) setRecord(res.data.record) })
      .catch(() => { if (!cancelled) setRecord(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId, chapterId, refreshKey])

  const run = async () => {
    const hadRecord = !!record?.scenes?.length
    setRunning(true)
    try {
      const res = await dabaiLabApi.runScenePlan(projectId, chapterId, {
        model_profile: modelProfileFromRoute(aiBackendRoute),
        ...(llmProviderIdFromRoute(aiBackendRoute)
          ? { llm_provider_id: llmProviderIdFromRoute(aiBackendRoute) }
          : {}),
      })
      setRecord(res.data.record)
      if (res.data.error) toast(res.data.error, { icon: '⚠️' })
      else if ((res.data.scene_count ?? 0) > 0) {
        toast.success(`分场就绪：${res.data.scene_count} 场（${(res.data.scene_names ?? []).join('→')}）`)
      } else toast.success(hadRecord ? '分场已重新生成' : '分场已生成')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '分场生成失败')
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
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-300 px-3 py-1.5 text-xs font-semibold text-white"
      >
        <Loader2 size={13} className="animate-spin" /> 分场调度生成中…
      </button>
    )
  }

  const scenes = (record?.scenes ?? []).filter(s => s && typeof s === 'object')
  if (scenes.length === 0) {
    return (
      <div className="space-y-2 text-xs">
        <button
          type="button"
          onClick={() => void run()}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-1.5 font-semibold text-white hover:bg-violet-600"
        >
          <Clapperboard size={13} />
          生成分场
        </button>
        {live?.error ? (
          <p className="flex items-start gap-1.5 text-amber-600">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {live.error}
          </p>
        ) : null}
        <p className="text-gray-400">
          {loading ? '加载中…' : '五拍拆 2-4 场；须先有导演单，首次写章会自动生成，也可在此手动生成'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3 text-xs">
      <button
        type="button"
        onClick={() => void run()}
        className={clsx(
          'inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold text-white',
          'bg-violet-500 hover:bg-violet-600',
        )}
      >
        <Clapperboard size={13} />
        重新生成分场
      </button>

      {record?.opening_line ? (
        <Section title="开篇指令">
          <p className="rounded bg-amber-50 px-2 py-1.5 text-amber-800">{record.opening_line}</p>
        </Section>
      ) : null}

      <Section title={`分场调度（${scenes.length} 场）`}>
        <div className="space-y-2">
          {scenes.map((sc, i) => (
            <SceneBlock key={`${sc.order ?? i}-${sc.name ?? i}`} scene={sc} index={i} />
          ))}
        </div>
      </Section>

      {live?.error ? (
        <p className="flex items-start gap-1.5 text-amber-600">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {live.error}
        </p>
      ) : null}

      {record?.created_at ? (
        <p className="text-[10px] text-gray-300">{new Date(record.created_at).toLocaleString()}</p>
      ) : null}
    </div>
  )
}
