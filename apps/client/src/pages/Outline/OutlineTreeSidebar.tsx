/**
 * @file 大纲树侧栏
 */
import {
  ChevronRight, ChevronDown, Plus, Trash2, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { outlineApi } from '../../api/client'
import type { OutlineNode } from '../../types'
import VolumeExpandButton from '../../components/Outline/VolumeExpandButton'
import type { ProgressLine, ExpandEndResult } from '../../components/Outline/VolumeExpandButton'
import { outlineTypeColor, outlineTypeLabel } from './outlineTreeHelpers'

export interface OutlineTreeSidebarProps {
  projectId: string | undefined
  outlineTree: OutlineNode[]
  expanded: Set<string>
  selected: OutlineNode | null
  aiBackendRoute: string
  onToggleExpand: (id: string) => void
  onSelect: (node: OutlineNode) => void
  onOpenChapter: (node: OutlineNode) => void
  onAddChild: (parent: OutlineNode, e: React.MouseEvent) => void
  onDelete: (node: OutlineNode, e: React.MouseEvent) => void
  onReload: () => void
  onClearSelection: () => void
  onShowFullGenModal: () => void
  /** 展开开始，父层可自动选中卷节点并显示进度面板 */
  onVolExpandStart?: (volumeNode: OutlineNode) => void
  /** SSE 每步进度更新 */
  onVolExpandProgress?: (lines: ProgressLine[]) => void
  /** SSE 流结束 */
  onVolExpandEnd?: (volumeNode: OutlineNode, result: ExpandEndResult) => void
}

export default function OutlineTreeSidebar({
  projectId,
  outlineTree,
  expanded,
  selected,
  aiBackendRoute,
  onToggleExpand,
  onSelect,
  onOpenChapter,
  onAddChild,
  onDelete,
  onReload,
  onClearSelection,
  onShowFullGenModal,
  onVolExpandStart,
  onVolExpandProgress,
  onVolExpandEnd,
}: OutlineTreeSidebarProps) {
  const renderNode = (node: OutlineNode, depth = 0) => {
    const isOpen = expanded.has(node.id)
    const hasChildren = node.children?.length > 0
    const canHaveChildren = node.node_type !== 'chapter_plan'

    return (
      <div key={node.id} className={node.node_type === 'volume' ? 'relative' : undefined}>
        <div
          className={clsx(
            'flex items-center gap-1 py-1.5 px-2 cursor-pointer rounded-lg mx-1 group',
            selected?.id === node.id ? 'bg-amber-50' : 'hover:bg-gray-50',
          )}
          style={{ paddingLeft: `${8 + depth * 18}px` }}
          onClick={() => onSelect(node)}
          onDoubleClick={() => onOpenChapter(node)}
        >
          <button
            className="shrink-0 text-gray-400 w-4 flex justify-center"
            onClick={e => { e.stopPropagation(); onToggleExpand(node.id) }}
          >
            {hasChildren
              ? (isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />)
              : <span className="w-3 inline-block" />}
          </button>
          <span className={clsx('text-[10px] px-1 py-0.5 rounded font-medium shrink-0', outlineTypeColor(node.node_type))}>
            {outlineTypeLabel(node.node_type)}
          </span>
          <span className="text-xs text-gray-800 truncate flex-1 min-w-0">{node.title}</span>
          {node.node_type === 'volume' && projectId && (
            <VolumeExpandButton
              volumeNode={node}
              projectId={projectId}
              aiBackendRoute={aiBackendRoute}
              onExpanded={onReload}
              onExpandStart={onVolExpandStart}
              onExpandProgress={onVolExpandProgress}
              onExpandEnd={onVolExpandEnd}
            />
          )}
          <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
            {canHaveChildren && (
              <button
                title="添加子节点"
                onClick={e => onAddChild(node, e)}
                className="p-0.5 rounded text-gray-400 hover:text-blue-500 hover:bg-blue-50"
              >
                <Plus size={11} />
              </button>
            )}
            <button
              title="删除"
              onClick={e => onDelete(node, e)}
              className="p-0.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50"
            >
              <Trash2 size={11} />
            </button>
          </div>
          {node.node_type === 'chapter_plan' && (
            <span className="text-[10px] text-gray-400 hidden group-hover:inline ml-1 shrink-0">
              双击写作
            </span>
          )}
        </div>
        {isOpen && node.children?.map(child => renderNode(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="w-64 border-r border-gray-100 bg-white flex flex-col shrink-0">
      <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-gray-100">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider shrink-0">大纲树</span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            title="删除全部章节计划，保留卷与篇；正文保留并解除关联"
            onClick={async () => {
              if (!projectId) return
              const ok = window.confirm(
                '确定清空大纲中的全部「章节计划」？\n\n'
                + '· 卷、篇节点会保留\n'
                + '· 写作端的章节正文不会删除，仅解除与大纲计划的绑定',
              )
              if (!ok) return
              try {
                const res = await outlineApi.clearChapterPlans(projectId)
                const n = res.data?.deleted ?? 0
                toast.success(n > 0 ? `已清空 ${n} 个章节计划` : '当前没有章节计划')
                onClearSelection()
                onReload()
              } catch {
                toast.error('清空章节计划失败')
              }
            }}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-gray-200 text-gray-600 bg-gray-50 hover:bg-gray-100 hover:border-gray-300"
          >
            <Trash2 size={12} />
            清空章节
          </button>
          <button
            type="button"
            onClick={onShowFullGenModal}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-amber-200 text-amber-700 bg-amber-50 hover:bg-amber-100"
          >
            <Sparkles size={12} />
            全部生成
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto py-1.5">
        {outlineTree.map(n => renderNode(n))}
        {outlineTree.length === 0 && (
          <div className="text-center py-8">
            <p className="text-xs text-gray-400">暂无大纲</p>
            <p className="text-[11px] text-gray-300 mt-1">点击「全量生成」或右上角 + 新建卷</p>
          </div>
        )}
      </div>
    </div>
  )
}
