/**
 * @file ScenePipelinePanel.tsx — 三层调度写作面板（分场 → 逐场起草 → 缝合）
 *
 * 职责：
 *   - 展示当前章节的分场列表及起草进度
 *   - 提供「生成分场」「起草单场」「全部起草」「缝合进章节」操作
 *   - 缝合完成后通知父组件（ChapterEditor）刷新章节正文
 *
 * 数据流：props → useScenePipeline hook → 渲染；无直接 API 调用。
 *
 * @param projectId    项目 ID
 * @param chapter      当前章节（取 id / outline_node_id）
 * @param outlineNode  挂载的大纲节点（无时显示提示）
 * @param modelProfile 模型线路（"local" | "gemini"）
 * @param llmProviderId 指定 LlmProvider（可 null）
 * @param onStitchDone 缝合完成回调，参数为总字数；父组件据此刷新编辑器
 */

import { RefreshCw, Wand2, ChevronRight, CheckCircle2, AlertCircle, Loader2, Layers } from 'lucide-react'
import clsx from 'clsx'
import type { Chapter, OutlineNode } from '../../types'
import { useScenePipeline, type SceneDraftState } from '../../hooks/useScenePipeline'
import { useAppStore, modelProfileFromRoute, llmProviderIdFromRoute } from '../../store'

// ── Props ──────────────────────────────────────────────────────

interface Props {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  onStitchDone?: (wordCount: number) => void
}

// ── 子组件：单场卡片 ───────────────────────────────────────────

interface SceneCardProps {
  order: number
  title?: string | null
  goal?: string | null
  conflict?: string | null
  wordBudget: number
  pacing: string
  status: string
  draftState?: SceneDraftState
  onDraft: () => void
  disabled: boolean
}

/**
 * 单个场景卡片：显示元信息、状态徽章、起草按钮与进度。
 *
 * @param props SceneCardProps
 */
function SceneCard({
  order, title, goal, conflict, wordBudget, pacing, status,
  draftState, onDraft, disabled,
}: SceneCardProps) {
  const isDone      = draftState?.status === 'done'  || status === 'written'
  const isStreaming = draftState?.status === 'streaming'
  const isError     = draftState?.status === 'error'

  const pacingLabel: Record<string, string> = { fast: '快', mid: '中', slow: '慢' }
  const statusBadge = isDone
    ? <span className="flex items-center gap-0.5 text-emerald-600 text-[10px]"><CheckCircle2 size={10} />已写</span>
    : isStreaming
      ? <span className="flex items-center gap-0.5 text-novel-accent text-[10px] animate-pulse"><Loader2 size={10} className="animate-spin" />起草中</span>
      : isError
        ? <span className="flex items-center gap-0.5 text-red-500 text-[10px]"><AlertCircle size={10} />出错</span>
        : <span className="text-[10px] text-novel-ink-faint">待写</span>

  return (
    <div className={clsx(
      'rounded-novel border px-3 py-2.5 transition-novel',
      isDone ? 'border-emerald-200 bg-emerald-50/40' :
      isError ? 'border-red-200 bg-red-50/30' :
      'border-novel-border bg-novel-card',
    )}>
      {/* 场次标题行 */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="shrink-0 text-[10px] font-bold text-novel-ink-muted bg-novel-panel rounded px-1 py-0.5">
            {order}
          </span>
          {title && (
            <span className="text-[11px] font-medium text-novel-ink truncate">{title}</span>
          )}
          <span className="shrink-0 text-[10px] text-novel-ink-faint">
            {pacingLabel[pacing] ?? pacing} · {wordBudget}字
          </span>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          {statusBadge}
          <button
            type="button"
            onClick={onDraft}
            disabled={disabled || isStreaming}
            title={isDone ? '重新起草本场' : '起草本场'}
            className={clsx(
              'text-[10px] px-2 py-0.5 rounded border transition-novel',
              isDone
                ? 'border-novel-border text-novel-ink-faint hover:border-novel-accent hover:text-novel-accent'
                : 'border-novel-accent/60 text-novel-accent hover:bg-novel-accent hover:text-white',
              (disabled || isStreaming) && 'opacity-40 cursor-not-allowed',
            )}
          >
            {isStreaming ? '…' : isDone ? '重写' : '起草'}
          </button>
        </div>
      </div>

      {/* 目标 & 冲突 */}
      {(goal || conflict) && (
        <div className="text-[10px] text-novel-ink-muted space-y-0.5 mb-1.5">
          {goal     && <p className="truncate"><span className="text-novel-ink-faint">目标</span> {goal}</p>}
          {conflict && <p className="truncate"><span className="text-novel-ink-faint">冲突</span> {conflict}</p>}
        </div>
      )}

      {/* 起草进度 */}
      {isStreaming && (
        <div className="mt-1.5">
          <div className="h-1 bg-novel-border rounded-full overflow-hidden">
            <div
              className="h-full bg-novel-accent/60 transition-all duration-300 rounded-full"
              style={{ width: `${Math.min(100, ((draftState?.charCount ?? 0) / wordBudget) * 100)}%` }}
            />
          </div>
          <p className="text-[9px] text-novel-ink-faint mt-0.5 text-right">
            {draftState?.charCount ?? 0} / {wordBudget} 字
          </p>
        </div>
      )}

      {/* 错误信息 */}
      {isError && draftState?.errorMsg && (
        <p className="text-[9px] text-red-500 mt-1 truncate">{draftState.errorMsg}</p>
      )}
    </div>
  )
}

// ── 主面板 ─────────────────────────────────────────────────────

/**
 * 分场写作面板，嵌入 ChapterEditor 的「场景」侧栏 Tab。
 * 通过 useScenePipeline hook 管理所有状态与 API 交互。
 */
export default function ScenePipelinePanel({ projectId, chapter, outlineNode, onStitchDone }: Props) {
  const route      = useAppStore(s => s.aiBackendRoute)
  const modelProfile = modelProfileFromRoute(route)
  const llmProviderId = llmProviderIdFromRoute(route) ?? null

  const pipeline = useScenePipeline({
    projectId,
    outlineNodeId: outlineNode?.id,
    chapterId: chapter.id,
    modelProfile,
    llmProviderId,
  })

  // ── 无大纲节点提示 ──────────────────────────────────────
  if (!outlineNode) {
    return (
      <div className="p-4 text-center text-xs text-novel-ink-faint space-y-1">
        <Layers size={20} className="mx-auto mb-2 opacity-40" />
        <p>分场写作需要章节挂载大纲节点</p>
        <p className="text-[10px]">在「计划」Tab 中为本章关联大纲</p>
      </div>
    )
  }

  const writtenCount = pipeline.scenes.filter(s => s.status === 'written').length
  const totalCount   = pipeline.scenes.length

  return (
    <div className="flex flex-col h-full">
      {/* ── 顶部工具栏 ── */}
      <div className="shrink-0 px-3 pt-3 pb-2 border-b border-novel-border flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Layers size={12} className="text-novel-ink-muted" />
          <span className="text-[11px] font-semibold text-novel-ink-muted uppercase tracking-wider">分场写作</span>
          {totalCount > 0 && (
            <span className="text-[10px] text-novel-ink-faint">
              {writtenCount}/{totalCount} 已写
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={pipeline.reload}
            disabled={pipeline.planLoading}
            title="刷新分场列表"
            className="p-1 rounded text-novel-ink-faint hover:text-novel-ink hover:bg-novel-panel transition-novel"
          >
            <RefreshCw size={11} className={pipeline.planLoading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={pipeline.generatePlan}
            disabled={pipeline.planLoading || pipeline.anyDrafting}
            title={totalCount > 0 ? '重新生成分场计划（会替换旧场景）' : '生成分场计划'}
            className={clsx(
              'flex items-center gap-1 text-[10px] px-2 py-1 rounded border transition-novel',
              pipeline.planLoading
                ? 'border-novel-border text-novel-ink-faint opacity-60 cursor-not-allowed'
                : 'border-novel-accent/60 text-novel-accent hover:bg-novel-accent hover:text-white',
            )}
          >
            {pipeline.planLoading
              ? <Loader2 size={10} className="animate-spin" />
              : <Wand2 size={10} />}
            {totalCount > 0 ? '重新分场' : '生成分场'}
          </button>
        </div>
      </div>

      {/* ── 场景列表 ── */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2 min-h-0">
        {totalCount === 0 ? (
          <div className="pt-6 text-center text-xs text-novel-ink-faint space-y-2">
            <Layers size={28} className="mx-auto opacity-25" />
            <p>还没有分场计划</p>
            <p className="text-[10px]">点击「生成分场」让 AI 将章纲拆解为 4-8 个分场</p>
          </div>
        ) : (
          pipeline.scenes.map(scene => (
            <SceneCard
              key={scene.id}
              order={scene.order}
              title={scene.title}
              goal={scene.goal}
              conflict={scene.conflict}
              wordBudget={scene.word_budget}
              pacing={scene.pacing}
              status={scene.status}
              draftState={pipeline.draftStates[scene.id]}
              onDraft={() => pipeline.draftScene(scene.id)}
              disabled={pipeline.anyDrafting && pipeline.draftStates[scene.id]?.status !== 'streaming'}
            />
          ))
        )}
      </div>

      {/* ── 底部操作栏 ── */}
      {totalCount > 0 && (
        <div className="shrink-0 border-t border-novel-border px-3 py-2 flex items-center gap-2">
          {/* 全部起草 */}
          <button
            type="button"
            onClick={pipeline.draftAll}
            disabled={pipeline.anyDrafting || pipeline.stitching}
            title="顺序起草所有待写分场（已写的跳过）"
            className={clsx(
              'flex-1 flex items-center justify-center gap-1.5 text-[11px] py-1.5 rounded border transition-novel',
              pipeline.anyDrafting
                ? 'border-novel-accent/40 text-novel-accent/60 cursor-not-allowed'
                : 'border-novel-accent text-novel-accent hover:bg-novel-accent hover:text-white',
            )}
          >
            {pipeline.anyDrafting
              ? <Loader2 size={11} className="animate-spin" />
              : <ChevronRight size={11} />}
            {pipeline.anyDrafting ? '起草中…' : '全部起草'}
          </button>

          {/* 缝合进章节 */}
          <button
            type="button"
            onClick={() => pipeline.stitch(onStitchDone)}
            disabled={!pipeline.allWritten || pipeline.stitching || pipeline.anyDrafting}
            title={
              !pipeline.allWritten
                ? `还有 ${totalCount - writtenCount} 场未完成`
                : '将所有已写场景缝合为章节草稿'
            }
            className={clsx(
              'flex-1 flex items-center justify-center gap-1.5 text-[11px] py-1.5 rounded border transition-novel',
              pipeline.allWritten && !pipeline.stitching && !pipeline.anyDrafting
                ? 'border-emerald-500 text-emerald-600 hover:bg-emerald-500 hover:text-white'
                : 'border-novel-border text-novel-ink-faint opacity-50 cursor-not-allowed',
            )}
          >
            {pipeline.stitching
              ? <Loader2 size={11} className="animate-spin" />
              : <CheckCircle2 size={11} />}
            {pipeline.stitching ? '缝合中…' : '缝合进章节'}
          </button>
        </div>
      )}
    </div>
  )
}
