/**
 * ScenePanel — 章节分场蓝图面板
 *
 * 职责：为 OutlinePage 中选中的 chapter_plan 节点，展示其下所有
 * Scene（分场）记录，支持按 order 排列的只读卡片视图。
 *
 * 数据来源：GET /api/v1/projects/{pid}/scenes/?outline_node_id=xxx
 * 约束：仅做展示，不含编辑逻辑（编写流程在写作页完成）。
 *
 * @see SceneRead schema（apps/backend/app/schemas/scene.py）
 */
import React, { useEffect, useState } from 'react'
import { scenesApi } from '../../api/client'
import type { Scene, ScenePacing, SceneStatus } from '../../types'
import clsx from 'clsx'
import { Loader2, MapPin, Clock, User, Target, Swords, Zap, Anchor, Gauge, BookOpen, AlertCircle } from 'lucide-react'

// ── 常量映射 ──────────────────────────────────────────────

const PACING_META: Record<ScenePacing, { label: string; color: string }> = {
  fast: { label: '快',  color: 'bg-red-50 text-red-600 border-red-200' },
  mid:  { label: '中',  color: 'bg-amber-50 text-amber-600 border-amber-200' },
  slow: { label: '慢',  color: 'bg-blue-50 text-blue-600 border-blue-200' },
}

const STATUS_META: Record<SceneStatus, { label: string; dot: string; ring: string }> = {
  planned:  { label: '待写',   dot: 'bg-gray-300',   ring: 'ring-gray-200' },
  written:  { label: '已写',   dot: 'bg-green-400',  ring: 'ring-green-200' },
  reviewed: { label: '已审',   dot: 'bg-violet-400', ring: 'ring-violet-200' },
}

const HOOK_STARS = (n: number) =>
  Array.from({ length: 5 }, (_, i) => (
    <span key={i} className={i < n ? 'text-amber-400' : 'text-gray-200'}>★</span>
  ))

// ── 子组件：单条场景卡片 ───────────────────────────────────

interface SceneCardProps {
  scene: Scene
  index: number
}

/**
 * 单场场景卡片（只读）。
 * 展示：地点/时间、POV（仅有 ID 时用缩略显示）、目标、冲突、转折、钩子、字数预算、节奏、状态。
 */
function SceneCard({ scene, index }: SceneCardProps) {
  const pacing = PACING_META[scene.pacing] ?? PACING_META.mid
  const status = STATUS_META[scene.status] ?? STATUS_META.planned

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* 卡头：序号 + 状态 + 节奏 */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-gray-400 w-5 text-center">#{index + 1}</span>
          {scene.title && (
            <span className="text-xs font-semibold text-gray-700 truncate max-w-[200px]">{scene.title}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* 字数预算 */}
          <span className="text-[10px] text-gray-400 font-mono">{scene.word_budget}字</span>
          {/* 节奏 */}
          <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium', pacing.color)}>
            {pacing.label}节奏
          </span>
          {/* 状态 */}
          <span className={clsx('flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full ring-1', status.ring)}>
            <span className={clsx('w-1.5 h-1.5 rounded-full', status.dot)} />
            {status.label}
          </span>
        </div>
      </div>

      {/* 卡体：结构要素 */}
      <div className="px-4 py-3 space-y-2.5">
        {/* 地点 & 时间 */}
        {(scene.location_name || scene.time) && (
          <div className="flex items-start gap-4 flex-wrap">
            {scene.location_name && (
              <MetaRow icon={<MapPin size={11} className="text-gray-400 mt-0.5" />} label="地点" value={scene.location_name} />
            )}
            {scene.time && (
              <MetaRow icon={<Clock size={11} className="text-gray-400 mt-0.5" />} label="时间" value={scene.time} />
            )}
          </div>
        )}

        {/* 目标 */}
        {scene.goal && (
          <MetaRow icon={<Target size={11} className="text-emerald-500 mt-0.5" />} label="目标" value={scene.goal} />
        )}

        {/* 冲突 */}
        {scene.conflict && (
          <MetaRow icon={<Swords size={11} className="text-red-400 mt-0.5" />} label="冲突" value={scene.conflict} />
        )}

        {/* 转折 */}
        {scene.turn && (
          <MetaRow icon={<Zap size={11} className="text-amber-400 mt-0.5" />} label="转折" value={scene.turn} />
        )}

        {/* 钩子 */}
        {scene.hook && (
          <div>
            <MetaRow icon={<Anchor size={11} className="text-indigo-400 mt-0.5" />} label="出场钩子" value={scene.hook} />
            <div className="flex items-center gap-0.5 mt-1 ml-3.5 pl-1">
              {HOOK_STARS(scene.hook_strength)}
              <span className="text-[10px] text-gray-400 ml-1">强度 {scene.hook_strength}/5</span>
            </div>
          </div>
        )}

        {/* 感官焦点 */}
        {scene.sensory_focus && scene.sensory_focus !== 'mixed' && (
          <MetaRow icon={<Gauge size={11} className="text-purple-400 mt-0.5" />} label="感官" value={scene.sensory_focus} />
        )}
      </div>
    </div>
  )
}

// ── 子组件：元信息行 ──────────────────────────────────────

function MetaRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5 text-xs min-w-0">
      <span className="shrink-0 mt-0.5">{icon}</span>
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className="text-gray-700 leading-relaxed min-w-0 break-words">{value}</span>
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────

interface ScenePanelProps {
  /** 所属项目 ID */
  projectId: string
  /** chapter_plan 大纲节点 ID */
  outlineNodeId: string
}

/**
 * ScenePanel — 展示某 chapter_plan 下的所有分场蓝图。
 *
 * 加载策略：outlineNodeId 变化时重新拉取；空态时展示提示。
 * 副作用：仅发起 GET 请求，无写库操作。
 */
export default function ScenePanel({ projectId, outlineNodeId }: ScenePanelProps) {
  const [scenes, setScenes]   = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || !outlineNodeId) return
    setLoading(true)
    setError(null)
    scenesApi.list(projectId, { outline_node_id: outlineNodeId })
      .then(res => setScenes(res.data))
      .catch(() => setError('加载分场数据失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [projectId, outlineNodeId])

  // ── 加载中 ────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <Loader2 size={24} className="animate-spin mb-3" />
        <span className="text-sm">加载分场数据…</span>
      </div>
    )
  }

  // ── 错误 ───────────────────────────────────────────────

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <AlertCircle size={24} className="text-red-400 mb-3" />
        <p className="text-sm text-red-500">{error}</p>
      </div>
    )
  }

  // ── 空态 ───────────────────────────────────────────────

  if (scenes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center text-gray-400">
        <BookOpen size={32} className="mb-3 opacity-30" />
        <p className="text-sm font-medium">暂无分场蓝图</p>
        <p className="text-xs mt-1.5 text-gray-300 max-w-[220px] leading-relaxed">
          Bootstrap 第 13 步会自动为第 1 章生成分场；<br />
          后续章节可通过写作页「生成分场」按钮创建
        </p>
      </div>
    )
  }

  // ── 摘要栏 ─────────────────────────────────────────────

  const totalBudget = scenes.reduce((s, sc) => s + sc.word_budget, 0)
  const writtenCount = scenes.filter(sc => sc.status !== 'planned').length

  return (
    <div className="space-y-4">
      {/* 汇总信息栏 */}
      <div className="flex items-center gap-4 px-1">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <User size={11} />
          <span>{scenes.length} 场</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <BookOpen size={11} />
          <span>合计约 {totalBudget.toLocaleString()} 字</span>
        </div>
        {writtenCount > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-green-600">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span>已写 {writtenCount}/{scenes.length}</span>
          </div>
        )}
      </div>

      {/* 场景卡片列表 */}
      <div className="space-y-3">
        {scenes.map((scene, i) => (
          <SceneCard key={scene.id} scene={scene} index={i} />
        ))}
      </div>
    </div>
  )
}
