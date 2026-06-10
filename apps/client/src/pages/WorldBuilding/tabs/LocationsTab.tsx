/**
 * @file 世界观 — 地点台账（大白文版）
 *
 * 地点分两类：
 *   - 卷级地图位置（extra.dabai_volume 有值）：Bootstrap gen_volumes_map_dabai 生成，按卷分组展示
 *   - 散布地点（无 dabai_volume）：章节复盘后 AI 自动入库（extra.source === "auto_debrief"）或手动添加
 *
 * 数据来源约定：
 *   LocationRecord.extra.dabai_volume  — 卷序号（1 起）
 *   LocationRecord.extra.travel_spine  — 卷内行进线路 string[]（同卷所有地点相同）
 *   LocationRecord.description         — 对应 world_map.map_note（地图背景说明）
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Plus, Trash2, MapPin, ChevronDown, ChevronRight, Sparkles, Map as MapIcon, Globe,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { locationsApi } from '../../../api/client'
import type { Location as LocationRecord } from '../../../types'

// ── 常量 ─────────────────────────────────────────────────────────────────────

const DANGER_LABELS: Record<string, string> = {
  safe: '安全', neutral: '中性', dangerous: '危险', forbidden: '禁区',
}

const DANGER_COLORS: Record<string, string> = {
  safe:      'bg-green-100 text-green-700',
  neutral:   'bg-gray-100 text-gray-600',
  dangerous: 'bg-amber-100 text-amber-700',
  forbidden: 'bg-red-100 text-red-700',
}

const TYPE_LABELS: Record<string, string> = {
  indoor: '室内', outdoor: '野外', ruins: '遗迹', battlefield: '战场',
  wilderness: '荒野', sacred_ground: '圣地', city: '城市', dungeon: '秘境', void: '虚空',
}

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface CreateForm {
  name: string
  location_type: string
  danger_level: string
  controller: string
  sensory_signature: string
  description: string
}

const EMPTY_FORM: CreateForm = {
  name: '',
  location_type: 'outdoor',
  danger_level: 'neutral',
  controller: '',
  sensory_signature: '',
  description: '',
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

function getExtra(loc: LocationRecord): Record<string, unknown> {
  return (loc.extra ?? {}) as Record<string, unknown>
}

// ── 单个地点卡片 ──────────────────────────────────────────────────────────────

function LocationCard({
  loc,
  onDelete,
}: {
  loc: LocationRecord
  onDelete: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const extra = getExtra(loc)
  const isAutoDebrief = extra.source === 'auto_debrief'
  const travelSpine = Array.isArray(extra.travel_spine)
    ? (extra.travel_spine as string[])
    : null

  return (
    <div className="border border-gray-200 rounded-lg bg-white text-sm">
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 select-none"
        onClick={() => setOpen(o => !o)}
      >
        <MapPin size={13} className="text-sky-500 shrink-0" />
        <span className="font-medium flex-1 truncate">{loc.name}</span>

        {isAutoDebrief && (
          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-violet-100 text-violet-600">
            <Sparkles size={9} />复盘自动
          </span>
        )}
        {loc.location_type && TYPE_LABELS[loc.location_type] && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
            {TYPE_LABELS[loc.location_type]}
          </span>
        )}
        {loc.danger_level && (
          <span className={clsx(
            'px-1.5 py-0.5 rounded text-[10px]',
            DANGER_COLORS[loc.danger_level] ?? 'bg-gray-100 text-gray-600',
          )}>
            {DANGER_LABELS[loc.danger_level] ?? loc.danger_level}
          </span>
        )}
        {loc.controller && (
          <span className="text-[10px] text-gray-400 truncate max-w-[80px]" title={loc.controller}>
            {loc.controller}
          </span>
        )}
        <button
          onClick={e => { e.stopPropagation(); onDelete(loc.id) }}
          className="text-gray-300 hover:text-red-500 transition-colors ml-1 shrink-0"
        >
          <Trash2 size={12} />
        </button>
        {open
          ? <ChevronDown size={12} className="text-gray-400 shrink-0" />
          : <ChevronRight size={12} className="text-gray-400 shrink-0" />}
      </div>

      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-gray-100 space-y-1.5 text-xs text-gray-600">
          {loc.sensory_signature && (
            <div>
              <span className="font-medium text-amber-600">感官基准（写章硬约束）：</span>
              <span className="italic">{loc.sensory_signature}</span>
            </div>
          )}
          {loc.controller && <div><span className="font-medium">控制方：</span>{loc.controller}</div>}
          {loc.description && <div className="text-gray-500">{loc.description}</div>}
          {travelSpine && travelSpine.length > 0 && (
            <div className="text-gray-400 text-[11px]">
              行进线路：{travelSpine.join(' → ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 卷地图分组 ────────────────────────────────────────────────────────────────

function VolumeMapGroup({
  volNum,
  locations,
  onDelete,
}: {
  volNum: number
  locations: LocationRecord[]
  onDelete: (id: string) => void
}) {
  const [open, setOpen] = useState(true)

  // travel_spine 和 description(map_note) 同卷相同，取第一个
  const firstExtra = getExtra(locations[0])
  const travelSpine = Array.isArray(firstExtra.travel_spine)
    ? (firstExtra.travel_spine as string[])
    : null
  const mapNote = typeof locations[0]?.description === 'string'
    ? locations[0].description
    : null
  const regionName = typeof firstExtra.region_name === 'string'
    ? firstExtra.region_name
    : null

  return (
    <div className="border border-teal-200 rounded-lg bg-teal-50/30">
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-teal-50/60 text-left rounded-lg"
        onClick={() => setOpen(o => !o)}
      >
        <Globe size={13} className="text-teal-600 shrink-0" />
        <span className="font-semibold text-teal-800 text-sm">
          第 {volNum} 卷地图
          {regionName && <span className="font-normal text-teal-600 ml-1">·{regionName}</span>}
        </span>
        <span className="text-[10px] text-teal-500">{locations.length} 处地点</span>
        {travelSpine && travelSpine.length > 0 && (
          <span className="text-[10px] text-gray-500 truncate flex-1 ml-1">
            {travelSpine.slice(0, 4).join(' → ')}{travelSpine.length > 4 ? '…' : ''}
          </span>
        )}
        {open
          ? <ChevronDown size={12} className="text-teal-400 ml-auto shrink-0" />
          : <ChevronRight size={12} className="text-teal-400 ml-auto shrink-0" />}
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-1.5">
          {mapNote && (
            <p className="text-[11px] text-teal-700 italic border-b border-teal-100 pb-2 mb-2">
              {mapNote}
            </p>
          )}
          {locations.map(loc => (
            <LocationCard key={loc.id} loc={loc} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── 新增表单 ──────────────────────────────────────────────────────────────────

function CreateLocationForm({
  onSave,
  onCancel,
}: {
  onSave: (form: CreateForm) => Promise<void>
  onCancel: () => void
}) {
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const set = (key: keyof CreateForm) => (val: string) =>
    setForm(f => ({ ...f, [key]: val }))

  const handleSave = async () => {
    if (!form.name.trim() || saving) return
    setSaving(true)
    try {
      await onSave(form)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-4 py-3 border-b border-sky-100 bg-sky-50 shrink-0 space-y-2">
      <div className="flex gap-2 flex-wrap">
        <input
          className="flex-1 min-w-0 border rounded px-2 py-1 text-sm"
          placeholder="地点名称 *"
          value={form.name}
          onChange={e => set('name')(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          value={form.location_type}
          onChange={e => set('location_type')(e.target.value)}
        >
          {Object.entries(TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          value={form.danger_level}
          onChange={e => set('danger_level')(e.target.value)}
        >
          {Object.entries(DANGER_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>
      <input
        className="w-full border rounded px-2 py-1 text-sm"
        placeholder="控制方（宗门/势力，可选）"
        value={form.controller}
        onChange={e => set('controller')(e.target.value)}
      />
      <textarea
        className="w-full border rounded px-2 py-1 text-sm resize-none"
        rows={2}
        placeholder="感官基准（1-3句，写章硬约束）：如 古朴木质气息，烛光昏黄，偶有翻页声"
        value={form.sensory_signature}
        onChange={e => set('sensory_signature')(e.target.value)}
      />
      <textarea
        className="w-full border rounded px-2 py-1 text-sm resize-none"
        rows={2}
        placeholder="地点描述（可选）"
        value={form.description}
        onChange={e => set('description')(e.target.value)}
      />
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1 rounded text-xs text-gray-600 hover:bg-gray-100"
        >
          取消
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !form.name.trim()}
          className="px-3 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50"
        >
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

/**
 * 地点台账 Tab。
 *
 * - 卷级地图：Bootstrap gen_volumes_map_dabai 生成，LocationRecord.extra.dabai_volume 标记卷号，按卷分组展示。
 * - 散布地点：复盘自动入库（extra.source === "auto_debrief"）或手动添加。
 */
export default function LocationsTab({ projectId }: { projectId: string }) {
  const [locations, setLocations] = useState<LocationRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await locationsApi.list(projectId)
      setLocations(res.data)
    } catch {
      toast.error('地点加载失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleCreate = async (form: CreateForm) => {
    await locationsApi.create(projectId, {
      name: form.name.trim(),
      location_type: form.location_type as LocationRecord['location_type'],
      danger_level: form.danger_level as LocationRecord['danger_level'],
      controller: form.controller.trim() || undefined,
      sensory_signature: form.sensory_signature.trim() || undefined,
      description: form.description.trim() || undefined,
    })
    setCreating(false)
    await load()
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除此地点？')) return
    try {
      await locationsApi.delete(projectId, id)
      setLocations(prev => prev.filter(l => l.id !== id))
    } catch {
      toast.error('删除失败')
    }
  }

  /** 按 extra.dabai_volume（1 起）分组，无此字段归入散布地点 */
  const { volGroups, orphans } = useMemo(() => {
    const groups = new Map<number, LocationRecord[]>()
    const orph: LocationRecord[] = []
    for (const loc of locations) {
      const vol = getExtra(loc).dabai_volume
      if (typeof vol === 'number' && vol > 0) {
        if (!groups.has(vol)) groups.set(vol, [])
        groups.get(vol)!.push(loc)
      } else {
        orph.push(loc)
      }
    }
    const sorted = [...groups.entries()].sort(([a], [b]) => a - b)
    return { volGroups: sorted, orphans: orph }
  }, [locations])

  const hasVolGroups = volGroups.length > 0

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 shrink-0">
        <span className="text-xs text-gray-400">
          共 {locations.length} 个地点 · 感官基准写章时自动注入
        </span>
        <button
          type="button"
          onClick={() => setCreating(c => !c)}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-sky-600 text-white hover:bg-sky-700"
        >
          <Plus size={12} /> 新增地点
        </button>
      </div>

      {/* 新增表单 */}
      {creating && (
        <CreateLocationForm
          onSave={handleCreate}
          onCancel={() => setCreating(false)}
        />
      )}

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
        {loading && (
          <div className="text-center text-gray-400 text-sm py-8">加载中…</div>
        )}

        {!loading && locations.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">
            <MapPin size={32} className="mx-auto mb-2 opacity-40" />
            <p>暂无地点</p>
            <p className="text-[11px] mt-1 opacity-70">
              Bootstrap 生成卷骨架后自动入库，或章节复盘后 AI 提取
            </p>
          </div>
        )}

        {/* ── 卷级地图分组 ── */}
        {!loading && hasVolGroups && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <MapIcon size={13} className="text-teal-600" />
              <span className="text-xs font-semibold text-teal-700">世界地图台账</span>
              <span className="text-[10px] text-gray-400">· Bootstrap 按卷生成</span>
            </div>
            {volGroups.map(([vol, locs]) => (
              <VolumeMapGroup
                key={vol}
                volNum={vol}
                locations={locs}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

        {/* ── 散布地点 ── */}
        {!loading && orphans.length > 0 && (
          <div className="space-y-1.5">
            {hasVolGroups && (
              <div className="flex items-center gap-2 pt-1">
                <MapPin size={13} className="text-sky-500" />
                <span className="text-xs font-semibold text-gray-600">散布地点</span>
                <span className="text-[10px] text-gray-400">
                  · 复盘自动入库 / 手动添加
                </span>
              </div>
            )}
            {orphans.map(loc => (
              <LocationCard key={loc.id} loc={loc} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
