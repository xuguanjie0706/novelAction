/**
 * ContextSidePanel.tsx — 右侧上下文面板（计划/场景/复盘/索引/预警）
 *
 * 该组件只负责渲染与 tab 切换；所有业务数据与操作 handler 由父组件提供。
 */
import React from 'react'
import clsx from 'clsx'
import {
  BookOpen,
  CheckSquare,
  ClipboardList,
  Flag,
  GitBranch,
  ShieldAlert,
  Target,
  TrendingUp,
  Users,
  Zap,
  X,
} from 'lucide-react'
import type { Chapter, Character, OutlineNode, StoryLine, ChapterIndex } from '../../../types'
import type {
  DebriefPanelProps,
  PreWriteWarnHistoryRow,
  PreWriteWarnResult,
  StorylinePreWarnItem,
} from './types'
import PlanCard from './PlanCard'
import WarnPanel from './WarnPanel'
import DebriefPanel from './DebriefPanel'
import ScenePipelinePanel from '../ScenePipelinePanel'
import ChapterIndexEditPanel from '../ChapterIndexEditPanel'
import type { ChapterContextTab } from './TopToolbar'

export default function ContextSidePanel({
  contextOpen,
  focusMode,
  contextTab,
  setContextTab,
  setContextOpen,

  projectId,
  chapter,
  outlineNode,
  characters,
  storyLines,

  hasOutlineContent,
  currentChIndex,
  onChIndexSaved,
  onForeshadowsMayChange,

  onSceneStitchDone,
  debriefPanelProps,

  gatedPreWarnDoneForChapter,
  warnLoading,
  warnResult,
  storylinePreWarns,
  warnHistory,
  selectedWarnRecordId,
  setSelectedWarnRecordId,
  setWarnResult,
  runPreWriteWarning,
}: {
  contextOpen: boolean
  focusMode: boolean
  contextTab: ChapterContextTab
  setContextTab: React.Dispatch<React.SetStateAction<ChapterContextTab>>
  setContextOpen: React.Dispatch<React.SetStateAction<boolean>>

  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
  characters: Character[]
  storyLines: StoryLine[]

  hasOutlineContent: boolean
  currentChIndex: ChapterIndex | null
  onChIndexSaved: React.Dispatch<React.SetStateAction<ChapterIndex | null>>
  onForeshadowsMayChange: () => void

  onSceneStitchDone: () => void | Promise<void>
  debriefPanelProps: DebriefPanelProps

  gatedPreWarnDoneForChapter: boolean
  warnLoading: boolean
  warnResult: PreWriteWarnResult | null
  storylinePreWarns: StorylinePreWarnItem[]
  warnHistory: PreWriteWarnHistoryRow[]
  selectedWarnRecordId: string | null
  setSelectedWarnRecordId: React.Dispatch<React.SetStateAction<string | null>>
  setWarnResult: React.Dispatch<React.SetStateAction<PreWriteWarnResult | null>>
  runPreWriteWarning: () => void | Promise<void>
}) {
  if (!contextOpen || focusMode) return null

  return (
    <div
      className={clsx(
        'shrink-0 border-l border-novel-border bg-novel-panel flex flex-col overflow-hidden',
        contextTab === 'chindex' ? 'w-[24rem]' : contextTab === 'warn' ? 'w-[22rem]' : 'w-80',
      )}
    >
      {/* Tab 导航头 */}
      <div className="flex items-center border-b border-novel-border bg-novel-card/80 shrink-0">
        {(
          [
            { key: 'plan', label: '计划', icon: <BookOpen size={11} /> },
            { key: 'scene', label: '场景', icon: <Users size={11} /> },
            { key: 'debrief', label: '复盘', icon: <CheckSquare size={11} /> },
            { key: 'chindex', label: '索引', icon: <ClipboardList size={11} /> },
            { key: 'warn', label: '预警', icon: <ShieldAlert size={11} /> },
          ] as const
        ).map(tab => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setContextTab(tab.key)}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1 py-2.5 text-[11px] font-medium border-b-2 transition-novel',
              contextTab === tab.key
                ? 'border-novel-accent text-novel-accent'
                : 'border-transparent text-novel-ink-muted hover:text-novel-ink',
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}

        <button
          type="button"
          onClick={() => setContextOpen(false)}
          className="px-2.5 text-novel-ink-faint hover:text-novel-ink"
        >
          <X size={13} />
        </button>
      </div>

      {/* Tab 内容区 */}
      <div className="flex-1 overflow-auto">
        {/* ── 章节计划 Tab ── */}
        {contextTab === 'plan' && (
          <div className="p-4 space-y-3">
            {outlineNode ? (
              <>
                {outlineNode.hook && (
                  <PlanCard
                    icon={<Zap size={12} className="text-amber-500" />}
                    label="开篇钩子"
                    sublabel="第一句话的使命"
                    content={outlineNode.hook}
                    accent="amber"
                  />
                )}
                {outlineNode.summary && (
                  <PlanCard
                    icon={<Target size={12} className="text-blue-500" />}
                    label="核心事件"
                    sublabel="删掉会损失什么"
                    content={outlineNode.summary}
                    accent="blue"
                  />
                )}
                {outlineNode.conflict && (
                  <PlanCard
                    icon={<Users size={12} className="text-purple-500" />}
                    label="人物变化"
                    sublabel="不可逆的认知或处境转变"
                    content={outlineNode.conflict}
                    accent="purple"
                  />
                )}
                {outlineNode.highlight && (
                  <PlanCard
                    icon={<Flag size={12} className="text-red-500" />}
                    label="章末钩子"
                    sublabel="让读者无法放下的最后一句"
                    content={outlineNode.highlight}
                    accent="red"
                  />
                )}

                {(outlineNode.extra as Record<string, string>)?.foreshadow && (
                  <PlanCard
                    icon={<GitBranch size={12} className="text-green-500" />}
                    label="伏笔管理"
                    sublabel="埋[…] 收[…]"
                    content={(outlineNode.extra as Record<string, string>).foreshadow}
                    accent="green"
                  />
                )}

                {outlineNode.power_milestone && (
                  <PlanCard
                    icon={<TrendingUp size={12} className="text-indigo-500" />}
                    label="实力里程碑"
                    sublabel="本章境界突破或技能习得"
                    content={outlineNode.power_milestone}
                    accent="indigo"
                  />
                )}

                {outlineNode.emotional_tone && (
                  <div className="rounded-novel border border-gray-100 bg-gray-50/70 px-3 py-2">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[10px] font-semibold text-gray-500">情感基调</span>
                    </div>
                    <p className="text-xs text-novel-ink">{outlineNode.emotional_tone}</p>
                  </div>
                )}

                {outlineNode.foreshadows_laid && outlineNode.foreshadows_laid.length > 0 && (
                  <div className="rounded-novel border border-green-100 bg-green-50/60 px-3 py-2">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <GitBranch size={12} className="text-green-500" />
                      <span className="text-xs font-semibold text-green-700">本章埋设的伏笔</span>
                    </div>
                    <ul className="space-y-1">
                      {outlineNode.foreshadows_laid.map((f, i) => (
                        <li
                          key={i}
                          className="text-xs text-novel-ink leading-snug before:content-['·'] before:mr-1.5 before:text-green-400"
                        >
                          {typeof f === 'string' ? f : f.description}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {!hasOutlineContent && (
                  <p className="text-xs text-novel-ink-faint text-center py-6 italic leading-relaxed">
                    大纲节点尚未填写计划细节
                    <br />
                    可在「大纲」页选中本章节点后编辑
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-novel-ink-faint text-center py-6 italic">此章节未挂载大纲节点</p>
            )}
          </div>
        )}

        {/* ── 分场写作 Tab ── */}
        {contextTab === 'scene' && (
          <ScenePipelinePanel projectId={projectId} chapter={chapter} outlineNode={outlineNode} onStitchDone={onSceneStitchDone} />
        )}

        {/* ── 复盘 Tab ── */}
        {contextTab === 'debrief' && <DebriefPanel {...debriefPanelProps} />}

        {/* ── 索引 Tab ── */}
        {contextTab === 'chindex' && (
          <ChapterIndexEditPanel
            projectId={projectId}
            chapter={chapter}
            index={currentChIndex}
            onSaved={onChIndexSaved}
            onForeshadowsMayChange={onForeshadowsMayChange}
          />
        )}

        {/* ── 写前预警 Tab ── */}
        {contextTab === 'warn' && (
          <>
            <WarnPanel
            runPreWriteWarning={runPreWriteWarning}
            warnLoading={warnLoading}
            warnResult={warnResult}
            storylinePreWarns={storylinePreWarns}
            warnHistory={warnHistory}
            selectedWarnRecordId={selectedWarnRecordId}
            setSelectedWarnRecordId={setSelectedWarnRecordId}
            setWarnResult={setWarnResult}
            gatedPreWarnDoneForChapter={gatedPreWarnDoneForChapter}
          />
          </>
        )}
      </div>
    </div>
  )
}

