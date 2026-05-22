/**
 * @file 世界观 — 地点 CRUD
 *
 * 地点来源说明：
 *   - extra.source === "auto_debrief"：章节复盘后 AI 自动入库，显示「复盘自动」徽章
 *   - 无 source 标记：作者手动录入
 */
import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2, MapPin, ChevronRight, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { locationsApi } from '../../../api/client'
import type { Location } from '../../../types'
import { Field, TextArea, TextInput } from '../shared/components'

const DANGER_LABELS: Record<string, string> = {
  safe: '安全',
  neutral: '中性',
  dangerous: '危险',
  forbidden: '禁区',
}

const DANGER_COLORS: Record<string, string> = {
  safe:      'bg-green-100 text-green-700',
  neutral:   'bg-gray-100 text-gray-600',
  dangerous: 'bg-amber-100 text-amber-700',
  forbidden: 'bg-red-100 text-red-700',
}

export default function LocationsTab({ projectId }: { projectId: string }) {
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', danger_level: 'neutral', sensory_signature: '', description: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await locationsApi.list(projectId)
      setLocations(res.data)
    } catch { toast.error('地点加载失败') }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.name.trim()) return
    try {
      await locationsApi.create(projectId, {
        name: form.name.trim(),
        danger_level: form.danger_level as Location['danger_level'],
        sensory_signature: form.sensory_signature.trim() || undefined,
        description: form.description.trim() || undefined,
      })
      setForm({ name: '', danger_level: 'neutral', sensory_signature: '', description: '' })
      setCreating(false)
      await load()
    } catch { toast.error('创建失败') }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return
    try {
      await locationsApi.delete(projectId, id)
      setLocations(prev => prev.filter(l => l.id !== id))
    } catch { toast.error('删除失败') }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 shrink-0">
        <span className="text-xs text-gray-400">共 {locations.length} 个地点 · 感官基准写章时自动注入</span>
        <button onClick={() => setCreating(c => !c)} className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700">
          <Plus size={12} /> 新增地点
        </button>
      </div>

      {creating && (
        <div className="px-4 py-3 border-b border-sky-100 bg-sky-50 shrink-0 space-y-2">
          <div className="flex gap-2">
            <input className="flex-1 border rounded px-2 py-1 text-sm" placeholder="地点名称*" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <select className="border rounded px-2 py-1 text-sm" value={form.danger_level} onChange={e => setForm(f => ({ ...f, danger_level: e.target.value }))}>
              {Object.entries(DANGER_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <textarea className="w-full border rounded px-2 py-1 text-sm resize-none" rows={2} placeholder="感官基准（1-3句）：如 古朴木质气息，烛光昏黄，偶有翻页声" value={form.sensory_signature} onChange={e => setForm(f => ({ ...f, sensory_signature: e.target.value }))} />
          <textarea className="w-full border rounded px-2 py-1 text-sm resize-none" rows={2} placeholder="地点描述（可选）" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <div className="flex gap-2 justify-end">
            <button onClick={() => setCreating(false)} className="px-3 py-1 rounded text-xs text-gray-600 hover:bg-gray-100">取消</button>
            <button onClick={handleCreate} className="px-3 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700">保存</button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
        {loading && <div className="text-center text-gray-400 text-sm py-8">加载中…</div>}
        {!loading && locations.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">
            <MapPin size={32} className="mx-auto mb-2 opacity-40" />
            暂无地点，章节复盘后自动生成或手动添加
          </div>
        )}
        {locations.map(loc => (
          <div key={loc.id} className="border border-gray-200 rounded-lg bg-white">
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50" onClick={() => setExpanded(e => e === loc.id ? null : loc.id)}>
              <MapPin size={14} className="text-sky-500 shrink-0" />
              <span className="font-medium text-sm flex-1">{loc.name}</span>
              {(loc.extra as Record<string, unknown>)?.source === 'auto_debrief' && (
                <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs bg-violet-100 text-violet-600">
                  <Sparkles size={10} />复盘自动
                </span>
              )}
              {loc.danger_level && (
                <span className={clsx('px-1.5 py-0.5 rounded text-xs', DANGER_COLORS[loc.danger_level] ?? 'bg-gray-100 text-gray-600')}>
                  {DANGER_LABELS[loc.danger_level] ?? loc.danger_level}
                </span>
              )}
              <button onClick={e => { e.stopPropagation(); handleDelete(loc.id) }} className="text-gray-300 hover:text-red-500 transition-colors ml-1"><Trash2 size={13} /></button>
              <ChevronRight size={13} className={clsx('text-gray-300 transition-transform', expanded === loc.id && 'rotate-90')} />
            </div>
            {expanded === loc.id && (
              <div className="px-3 pb-3 pt-1 border-t border-gray-100 space-y-1.5 text-xs text-gray-600">
                {loc.sensory_signature && (
                  <div><span className="font-medium text-amber-600">感官基准（写章硬约束）：</span><span className="italic">{loc.sensory_signature}</span></div>
                )}
                {loc.controller && <div><span className="font-medium">控制方：</span>{loc.controller}</div>}
                {loc.description && <div className="text-gray-500">{loc.description}</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
