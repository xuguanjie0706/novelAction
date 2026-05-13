/**
 * ScenePanel — 章节分场蓝图面板
 *
 * 职责：
 *   1. 展示 chapter_plan 节点下已有的所有 Scene（分场）记录
 *   2. 提供「AI 生成分场」按钮——调用 /ai/scene-plan 生成计划，
 *      再通过 /scenes/batch 批量入库（replace_existing=true 保证幂等）
 *
 * 数据来源：
 *   - 读：GET /api/v1/projects/{pid}/scenes/?outline_node_id=xxx
 *   - 生成：POST /api/v1/projects/{pid}/ai/scene-plan
 *   - 写库：POST /api/v1/projects/{pid}/scenes/batch
 *
 * 约束：生成后不支持在此处编辑，编辑逻辑在写作页完成。
 *
 * @see SceneRead schema（apps/backend/app/schemas/scene.py）
 * @see /ai/scene-plan 端点（apps/backend/app/routers/ai/draft_routes.py）
 */
import React, { useEffect, useState, useCallback } from 'react'
import { aiApi, scenesApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Scene, ScenePacing, SceneStatus } from '../../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import {
  Loader2, MapPin, Clock, Target, Swords, Zap, Anchor,
  Gauge, BookOpen, AlertCircle, Sparkles, RefreshCw,
} from 'lucide-react'

// ── 辅助：从 store 取模型配置 ─────────────────────────────

function useModelConfig() {
  const route = useAppStore.getState().aiBackendRoute
  // 与 OutlinePage 保持一致的工具函数
  const profile = route === 'gemini' ? 'gemini' : 'local'
  const providerId: string | undefined =
    route && route !== 'local' && route !== 'gemini' ? route : undefined
  return { profile, providerId } as const
}

// ── 常量映射 ──────────────────────────────────────────────

const PACING_META: Record<ScenePacing, { label: string; color: string }> = {
  fast: { label: '快节奏', color: 'bg-red-50 text-red-600 border-red-200' },
  mid:  { label: '中节奏', color: 'bg-amber-50 text-amber-600 border-amber-200' },
  slow: { label: '慢节奏', color: 'bg-blue-50 text-blue-600 border-blue-200' },
}

const STATUS_META: Record<SceneStatus, { label: string; dot: string; ring: string }> = {
  planned:  { label: '待写', dot: 'bg-gray-300',   ring: 'ring-gray-200' },
  written:  { label: '已写', dot: 'bg-green-400',  ring: 'ring-green-200' },
  reviewed: { label: '已审', dot: 'bg-violet-400', ring: 'ring-violet-200' },
}

// ── 子组件：星级钩子强度 ──────────────────────────────────

function HookStars({ n }: { n: number }) {
  return (
    <span className="flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < n ? 'text-amber-400' : 'text-gray-200'} style={{ fontSize: 10 }}>★</span>
      ))}
    </span>
  )
}

// ── 子组件：元信息行 ──────────────────────────────────────

function MetaRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5 text-xs min-w-0">
      <span className="shrink-0">{icon}</span>
      <span className="text-gray-400 shrink-0 whitespace-nowrap">{label}</span>
      <span className="text-gray-700 leading-relaxed min-w-0 break-words">{value}</span>
    </div>
  )
}

// ── 子组件：单条场景卡片 ──────────────────────────────────

function SceneCard({ scene, index }: { scene: Scene; index: number }) {
  const pacing = PACING_META[scene.pacing] ?? PACING_META.mid
  const status = STATUS_META[scene.status] ?? STATUS_META.planned

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      {/* 卡头 */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-100">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-bold text-gray-400 shrink-0">#{index + 1}</span>
          {scene.title && (
            <span className="text-xs font-semibold text-gray-700 truncate">{scene.title}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] text-gray-400 font-mono">{scene.word_budget}字</span>
          <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium', pacing.color)}>
            {pacing.label}
          </span>
          <span className={clsx('flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full ring-1', status.ring)}>
            <span className={clsx('w-1.5 h-1.5 rounded-full', status.dot)} />
            {status.label}
          </span>
        </div>
      </div>

      {/* 卡体 */}
      <div className="px-4 py-3 space-y-2">
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
        {scene.goal && (
          <MetaRow icon={<Target size={11} className="text-emerald-500 mt-0.5" />} label="目标" value={scene.goal} />
        )}
        {scene.conflict && (
          <MetaRow icon={<Swords size={11} className="text-red-400 mt-0.5" />} label="冲突" value={scene.conflict} />
        )}
        {scene.turn && (
          <MetaRow icon={<Zap size={11} className="text-amber-400 mt-0.5" />} label="转折" value={scene.turn} />
        )}
        {scene.hook && (
          <div>
            <MetaRow icon={<Anchor size={11} className="text-indigo-400 mt-0.5" />} label="钩子" value={scene.hook} />
            <div className="flex items-center gap-1.5 mt-1 pl-4">
              <HookStars n={scene.hook_strength} />
              <span className="text-[10px] text-gray-400">强度 {scene.hook_strength}/5</span>
            </div>
          </div>
        )}
        {scene.sensory_focus && scene.sensory_focus !== 'mixed' && (
          <MetaRow icon={<Gauge size={11} className="text-purple-400 mt-0.5" />} label="感官" value={scene.sensory_focus} />
        )}
      </div>
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────

interface ScenePanelProps {
  /** 所属项目 ID */
  projectId: string
  /** chapter_plan 大纲节点 ID */
  outlineNodeId: string
  /** 章节标题——用于 AI 生成分场的 prompt */
  nodeTitle: string
  /** 章节摘要——用于 AI 生成分场的 prompt */
  nodeSummary: string
}

/**
 * ScenePanel — 分场蓝图展示 + AI 生成入口。
 *
 * 状态机：
 *   idle → 展示场景列表（或空态）
 *   generating → 调用 AI 生成 + 批量入库
 *   error → 展示错误，允许重试
 *
 * 副作用：
 *   - 读：GET /scenes/ （outlineNodeId 变化时触发）
 *   - 写：POST /ai/scene-plan + POST /scenes/batch （点击生成时触发）
 */
export default function ScenePanel({ projectId, outlineNodeId, nodeTitle, nodeSummary }: ScenePanelProps) {
  const [scenes, setScenes]       = useState<Scene[]>([])
  const [loading, setLoading]     = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError]         = useState<string | null>(null)

  // ── 读取已有分场 ───────────────────────────────────────

  const fetchScenes = useCallback(() => {
    if (!projectId || !outlineNodeId) return
    setLoading(true)
    setError(null)
    scenesApi.list(projectId, { outline_node_id: outlineNodeId })
      .then(res => setScenes(res.data))
      .catch(() => setError('加载分场数据失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [projectId, outlineNodeId])

  useEffect(() => { fetchScenes() }, [fetchScenes])

  // ── AI 生成分场 ────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    if (generating) return
    const { profile, providerId } = useModelConfig()
    setGenerating(true)
    try {
      // Step 1: AI 生成分场计划
      const planRes = await aiApi.scenePlan(
        projectId,
        outlineNodeId,
        nodeTitle || '未命名章节',
        nodeSummary || '',
        profile as 'local' | 'gemini',
        providerId,
      )
      const rawScenes = planRes.data.scenes
      if (!rawScenes?.length) {
        toast.error('AI 返回的分场计划为空，请重试')
        return
      }

      // Step 2: 批量入库（replace_existing=true 会先清空旧场景）
      const saveRes = await scenesApi.batchCreate(projectId, outlineNodeId, rawScenes)
      setScenes(saveRes.data)
      toast.success(`已生成 ${saveRes.data.length} 个分场`)
    } catch {
      toast.error('生成分场失败，请检查模型配置后重试')
    } finally {
      setGenerating(false)
    }
  }, [projectId, outlineNodeId, nodeTitle, nodeSummary, generating])

  // ── 渲染：加载中 ───────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <Loader2 size={24} className="animate-spin mb-3" />
        <span className="text-sm">加载分场数据…</span>
      </div>
    )
  }

  // ── 渲染：错误 ─────────────────────────────────────────

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <AlertCircle size={24} className="text-red-400 mb-3" />
        <p className="text-sm text-red-500 mb-3">{error}</p>
        <button
          onClick={fetchScenes}
          className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50"
        >
          重试
        </button>
      </div>
    )
  }

  // ── 渲染：空态 ─────────────────────────────────────────

  if (scenes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center text-gray-400">
        <BookOpen size={32} className="mb-3 opacity-30" />
        <p className="text-sm font-medium text-gray-600">暂无分场蓝图</p>
        <p className="text-xs mt-1.5 text-gray-400 max-w-[220px] leading-relaxed">
          Bootstrap 第 13 步自动为第 1 章生成；<br />
          其他章节点击下方按钮即可生成
        </p>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="mt-5 flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm rounded-lg transition-colors"
        >
          {generating
            ? <><Loader2 size={14} className="animate-spin" />生成中…</>
            : <><Sparkles size={14} />AI 生成分场</>
          }
        </button>
      </div>
    )
  }

  // ── 渲染：场景列表 ─────────────────────────────────────

  const totalBudget  = scenes.reduce((s, sc) => s + sc.word_budget, 0)
  const writtenCount = scenes.filter(sc => sc.status !== 'planned').length

  return (
    <div className="space-y-4">
      {/* 汇总 + 重新生成按钮 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{scenes.length} 场</span>
          <span className="text-gray-300">·</span>
          <span>合计约 {totalBudget.toLocaleString()} 字</span>
          {writtenCount > 0 && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-green-600 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                已写 {writtenCount}/{scenes.length}
              </span>
            </>
          )}
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          title="重新生成（将覆盖现有分场）"
          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-amber-600 hover:border-amber-200 disabled:opacity-50 transition-colors"
        >
          {generating
            ? <Loader2 size={12} className="animate-spin" />
            : <RefreshCw size={12} />
          }
          {generating ? '生成中…' : '重新生成'}
        </button>
      </div>

      {/* 场景卡片 */}
      <div className="space-y-3">
        {scenes.map((scene, i) => (
          <SceneCard key={scene.id} scene={scene} index={i} />
        ))}
      </div>
    </div>
  )
}
