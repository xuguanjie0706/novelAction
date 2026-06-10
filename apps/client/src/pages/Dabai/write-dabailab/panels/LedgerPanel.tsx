/**
 * 台账 — 资产（功法/道具/金手指）+ 人物关系 双子页。
 * 数据：GET /dabai/projects/{pid}/assets | /relations（复盘自动维护，种子惰性派生）；
 * 支持手动纠偏（资产状态 / 人物态度）。
 */
import { useCallback, useEffect, useState } from 'react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { Loader2, Package, Users2 } from 'lucide-react'
import { dabaiLabApi } from '../../../../api/dabaiLab'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../types/dabaiLab'

const KIND_LABELS: Record<string, string> = {
  golden_finger: '金手指', skill: '功法', item: '道具',
}
const KIND_BADGE: Record<string, string> = {
  golden_finger: 'bg-amber-50 text-amber-700',
  skill: 'bg-sky-50 text-sky-600',
  item: 'bg-emerald-50 text-emerald-700',
}
const STATUS_LABELS: Record<string, string> = {
  active: '持有', consumed: '已消耗', lost: '已遗失',
}
const ATTITUDES = ['敌对', '轻视', '忌惮', '臣服', '效忠', '盟友', '暧昧', '中立']

function AssetSection({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<DabaiLabAsset[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    setLoading(true)
    dabaiLabApi.listAssets(projectId)
      .then(res => setItems(res.data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const patch = async (a: DabaiLabAsset, status: 'active' | 'consumed' | 'lost') => {
    try { await dabaiLabApi.patchAsset(projectId, a.id, status); refresh() }
    catch (e) { toast.error(e instanceof Error ? e.message : '操作失败') }
  }

  if (loading) return <p className="flex items-center gap-2 text-sm text-gray-400"><Loader2 size={14} className="animate-spin" /> 加载中…</p>
  if (items.length === 0) return <p className="py-8 text-center text-sm text-gray-400">暂无资产——复盘后自动记录新获功法/道具</p>

  return (
    <ul className="space-y-2">
      {items.map(a => (
        <li key={a.id} className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
          <div className="flex items-center gap-2">
            <span className={clsx('rounded px-1.5 py-0.5 text-[10px]', KIND_BADGE[a.kind] ?? 'bg-gray-100 text-gray-500')}>
              {KIND_LABELS[a.kind] ?? a.kind}
            </span>
            <span className={clsx('min-w-0 flex-1 truncate text-sm font-medium', a.status === 'active' ? 'text-gray-900' : 'text-gray-400 line-through')}>
              {a.name}
            </span>
            {a.owner ? <span className="text-[11px] text-gray-400">{a.owner}</span> : null}
            <span className={clsx('rounded-full px-2 py-0.5 text-[10px]', a.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400')}>
              {STATUS_LABELS[a.status] ?? a.status}
            </span>
          </div>
          {a.description ? <p className="mt-1 text-xs text-gray-600">{a.description}</p> : null}
          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-400">
            <span>
              {a.acquired_chapter ? `第${a.acquired_chapter}章获得` : '开局自带'}
              {a.status !== 'active' && a.status_chapter ? ` → 第${a.status_chapter}章${STATUS_LABELS[a.status]}` : ''}
            </span>
            <span className="ml-auto flex gap-1">
              {(['active', 'consumed', 'lost'] as const).filter(s => s !== a.status).map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void patch(a, s)}
                  className="rounded px-1.5 py-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                >
                  标记{STATUS_LABELS[s]}
                </button>
              ))}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}

function RelationSection({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<DabaiLabRelation[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    dabaiLabApi.listRelations(projectId)
      .then(res => setItems(res.data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const patch = async (r: DabaiLabRelation, attitude: string) => {
    try { await dabaiLabApi.patchRelation(projectId, r.id, attitude); refresh() }
    catch (e) { toast.error(e instanceof Error ? e.message : '操作失败') }
  }

  if (loading) return <p className="flex items-center gap-2 text-sm text-gray-400"><Loader2 size={14} className="animate-spin" /> 加载中…</p>
  if (items.length === 0) return <p className="py-8 text-center text-sm text-gray-400">暂无关系——开局自动派生，复盘追踪变化</p>

  return (
    <ul className="space-y-2">
      {items.map(r => (
        <li key={r.id} className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-900">
              {r.from_name} → {r.to_name}
            </span>
            <span className={clsx(
              'rounded-full px-2 py-0.5 text-[10px]',
              r.attitude === '敌对' ? 'bg-rose-50 text-rose-600'
                : ['臣服', '效忠', '盟友'].includes(r.attitude ?? '') ? 'bg-emerald-50 text-emerald-700'
                  : r.attitude === '暧昧' ? 'bg-pink-50 text-pink-600'
                    : 'bg-gray-100 text-gray-500',
            )}>
              {r.attitude ?? '中立'}
            </span>
            {r.last_change_chapter ? (
              <span className="text-[10px] text-gray-400">第{r.last_change_chapter}章起</span>
            ) : null}
          </div>
          {r.note ? <p className="mt-1 text-xs text-gray-600">{r.note}</p> : null}
          <div className="mt-1.5 flex items-center gap-2 text-[11px]">
            <button
              type="button"
              onClick={() => setExpanded(expanded === r.id ? null : r.id)}
              className="text-gray-400 hover:text-gray-600"
            >
              轨迹（{r.history.length}）{expanded === r.id ? '▲' : '▼'}
            </button>
            <select
              value=""
              onChange={e => { if (e.target.value) void patch(r, e.target.value) }}
              className="ml-auto rounded border border-gray-200 px-1 py-0.5 text-[11px] text-gray-500"
            >
              <option value="">改态度…</option>
              {ATTITUDES.filter(a => a !== r.attitude).map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          {expanded === r.id && r.history.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-gray-50 pt-2 text-[11px] text-gray-500">
              {[...r.history].reverse().map((h, i) => (
                <li key={i}>
                  {h.chapter != null ? `第${h.chapter}章` : '手动'} · {h.attitude}
                  {h.reason ? `（${h.reason}）` : ''}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function LedgerPanel({ projectId }: { projectId: string }) {
  const [sub, setSub] = useState<'assets' | 'relations'>('assets')
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Package size={16} className="text-amber-500" />
        <h2 className="text-sm font-semibold text-gray-900">台账</h2>
        <span className="text-xs text-gray-400">复盘自动维护 · 写章/导演单注入约束</span>
      </div>
      <div className="flex gap-1">
        {([['assets', '资产', Package], ['relations', '关系', Users2]] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSub(id)}
            className={clsx(
              'inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs',
              sub === id ? 'bg-amber-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200',
            )}
          >
            <Icon size={12} /> {label}
          </button>
        ))}
      </div>
      {sub === 'assets' ? <AssetSection projectId={projectId} /> : <RelationSection projectId={projectId} />}
    </div>
  )
}
