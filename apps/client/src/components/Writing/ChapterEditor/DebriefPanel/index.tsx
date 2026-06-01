/**
 * DebriefPanel — 章节复盘面板（编排壳）
 *
 * 子块：HistorySection / CharUpdateSection / StorylineSection / AssetUpdatesSection 等。
 * 数据来源通过 props；AI 调用由父组件 index.tsx 驱动。
 */
import clsx from 'clsx'
import { Bot, UserPlus, CheckSquare } from 'lucide-react'
import type { DebriefPanelProps } from '../types'
import { HistorySection } from './HistorySection'
import { CharUpdateSection } from './CharUpdateSection'
import { StorylineSection } from './StorylineSection'
import { AssetUpdatesSection } from './AssetUpdatesSection'
import { ReaderPromisesSection } from './ReaderPromisesSection'
import { DirectivesSpeechKitSection } from './DirectivesSpeechKitSection'
import { useDebriefAssets } from './useDebriefAssets'

export default function DebriefPanel({
  projectId,
  chapter,
  outlineNode,
  characters,
  storyLines,
  charUpdates,
  setCharUpdates,
  storylineBeats,
  setStorylineBeats,
  debriefNotes,
  setDebriefNotes,
  submitting,
  autoDebriefing,
  cacheHydrating = false,
  aiSuggestedCharIds = new Set(),
  aiSuggestedSlIds = new Set(),
  aiSuggestedAssetUpdates = null,
  aiNewCharacters = [],
  aiNewReaderPromises = [],
  aiFulfilledPromiseTexts = [],
  aiNextChapterDirectives = [],
  aiSpeechKitUpdates = [],
  onRemoveNewPromise,
  onRemoveFulfilledPromise,
  onRemoveNextChapterDirective,
  onRemoveSpeechKitUpdate,
  aiSummary,
  onAutoDebrief,
  onSubmit,
  fromQueueSnapshot = false,
  debriefHistoryTick = 0,
  debriefContentReady = true,
}: DebriefPanelProps) {
  const involvedIds = new Set(outlineNode?.involved_character_ids?.map(String) || [])
  const displayChars = involvedIds.size > 0
    ? characters.filter(c => involvedIds.has(String(c.id)))
    : characters.slice(0, 8)

  const activeStorylines = storyLines.filter(s =>
    ['active', 'climax', 'planned'].includes(s.status),
  )

  const updateChar = (id: string, field: string, value: string) => {
    setCharUpdates(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  const updateStoryline = (
    id: string,
    field: keyof import('../types').StorylineBeatFormFields,
    value: string | number | boolean,
  ) => {
    setStorylineBeats(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  const {
    assetSections,
    assetSelections,
    setAssetSelections,
    totalAssetCount,
    selectedAssetCount,
    buildSelectedAssetUpdates,
  } = useDebriefAssets(aiSuggestedAssetUpdates)

  const hasAiSuggestions = aiSuggestedCharIds.size > 0
    || aiSuggestedSlIds.size > 0
    || totalAssetCount > 0
    || aiNewReaderPromises.length > 0
    || aiFulfilledPromiseTexts.length > 0
    || aiNextChapterDirectives.length > 0
    || aiSpeechKitUpdates.length > 0

  return (
    <div className="p-4 space-y-4">
      {fromQueueSnapshot && (
        <div className="rounded-novel border border-amber-200 bg-amber-50/90 px-3 py-2 text-[10px] text-amber-900 leading-relaxed">
          <span className="font-semibold">生成队列已自动复盘并写入数据库。</span>
          以下为当时的 AI 提取快照（黄标与预填一致），便于对照；若再改正文可点「重新分析」刷新。
        </div>
      )}

      <HistorySection
        projectId={projectId}
        chapterId={chapter.id}
        debriefHistoryTick={debriefHistoryTick}
      />

      {!debriefContentReady && (
        <div className="rounded-novel border border-rose-200 bg-rose-50/90 px-3 py-2.5 text-[11px] text-rose-800 leading-relaxed">
          <span className="font-semibold">本章尚无已保存正文。</span>
          {' '}
          复盘只读取数据库中的章节内容。请先在左侧撰写并等待自动保存，或用 AI 队列生成本章后再分析。
          <span className="block mt-1 text-rose-700/90">
            若刚写完的是上一章（例如第22章），请切换到该章再点「AI 自动复盘」。
          </span>
        </div>
      )}

      {hasAiSuggestions && aiSummary ? (
        <div className="rounded-novel border border-amber-200 bg-amber-50/80 px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <Bot size={12} className="text-amber-500" />
            <span className="text-[11px] font-semibold text-amber-700">AI 已自动分析本章</span>
          </div>
          <p className="text-[11px] text-amber-800 leading-relaxed">{aiSummary}</p>
          <p className="text-[10px] text-amber-500 mt-1">
            已预填 {aiSuggestedCharIds.size} 个人物、{aiSuggestedSlIds.size} 条故事线、{totalAssetCount} 条资产变化
            {aiNewCharacters.length > 0 ? `、${aiNewCharacters.length} 个新配角` : ''}
            {aiNewReaderPromises.length > 0 ? `、${aiNewReaderPromises.length} 条新承诺` : ''}
            {aiFulfilledPromiseTexts.length > 0 ? `、${aiFulfilledPromiseTexts.length} 条待兑现` : ''}
            {aiNextChapterDirectives.length > 0 ? `、${aiNextChapterDirectives.length} 条下一章指令` : ''}
            {aiSpeechKitUpdates.length > 0 ? `、${aiSpeechKitUpdates.length} 条语风` : ''}
            ，请检查后提交
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-novel-ink-faint leading-relaxed">
            点击下方「AI 分析」提取变化（若此前分析过且正文未改，打开本页会自动载入缓存）；也可纯手动填写后提交
          </p>
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || !debriefContentReady}
              className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-novel border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={11} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中…' : 'AI 自动复盘'}
            </button>
          )}
        </div>
      )}

      {cacheHydrating && (
        <div className="flex items-center justify-center gap-2 py-2 text-slate-500">
          <span className="text-xs">正在载入已保存的复盘建议…</span>
        </div>
      )}
      {autoDebriefing && (
        <div className="flex items-center justify-center gap-2 py-3 text-amber-600">
          <Bot size={14} className="animate-pulse" />
          <span className="text-xs">AI 正在读取章节并提取变化…</span>
        </div>
      )}

      <CharUpdateSection
        displayChars={displayChars}
        charUpdates={charUpdates}
        aiSuggestedCharIds={aiSuggestedCharIds}
        onUpdateChar={updateChar}
      />

      <StorylineSection
        chapterNumber={chapter.sort_order ?? 1}
        activeStorylines={activeStorylines}
        storylineBeats={storylineBeats}
        aiSuggestedSlIds={aiSuggestedSlIds}
        onUpdateStoryline={updateStoryline}
      />

      <AssetUpdatesSection
        assetSections={assetSections}
        assetSelections={assetSelections}
        setAssetSelections={setAssetSelections}
        selectedAssetCount={selectedAssetCount}
        totalAssetCount={totalAssetCount}
      />

      <ReaderPromisesSection
        aiNewReaderPromises={aiNewReaderPromises}
        aiFulfilledPromiseTexts={aiFulfilledPromiseTexts}
        fromQueueSnapshot={fromQueueSnapshot}
        onRemoveNewPromise={onRemoveNewPromise}
        onRemoveFulfilledPromise={onRemoveFulfilledPromise}
      />

      <DirectivesSpeechKitSection
        aiNextChapterDirectives={aiNextChapterDirectives}
        aiSpeechKitUpdates={aiSpeechKitUpdates}
        fromQueueSnapshot={fromQueueSnapshot}
        onRemoveNextChapterDirective={onRemoveNextChapterDirective}
        onRemoveSpeechKitUpdate={onRemoveSpeechKitUpdate}
      />

      <section>
        <label className="text-[10px] font-semibold text-novel-ink-muted block mb-1.5">作者备注（可选）</label>
        <textarea
          value={debriefNotes}
          onChange={e => setDebriefNotes(e.target.value)}
          rows={2}
          placeholder="本章写作感受、待调整之处……"
          className="w-full text-[11px] border border-novel-border rounded-novel px-3 py-2 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-none"
        />
      </section>

      {aiNewCharacters.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <UserPlus size={11} className="text-emerald-600" />
            <span className="text-[11px] font-semibold text-novel-ink">本章新配角入库</span>
            <span className="ml-auto text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">
              AI 建议
            </span>
          </div>
          <div className="space-y-1.5">
            {aiNewCharacters.map((nc, i) => (
              <div key={i} className="rounded-novel border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-novel-ink">{nc.name}</span>
                  {nc.faction && (
                    <span className="text-emerald-700 bg-emerald-100 rounded px-1">{nc.faction}</span>
                  )}
                  {nc.current_realm && <span className="text-novel-ink-muted">{nc.current_realm}</span>}
                </div>
                {nc.personality && (
                  <p className="text-novel-ink-muted mt-0.5 leading-relaxed">{nc.personality}</p>
                )}
                {nc.motivation && <p className="text-novel-ink-faint mt-0.5">动机：{nc.motivation}</p>}
                {nc.author_notes && <p className="text-amber-700 mt-0.5 italic">{nc.author_notes}</p>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-novel-ink-faint mt-1.5">提交后自动写入人物库</p>
        </section>
      )}

      {displayChars.length === 0 && activeStorylines.length === 0 && (
        <p className="text-xs text-novel-ink-faint italic text-center py-4">
          暂无人物或活跃故事线
          <br />
          <span className="text-[10px]">
            请先在「人物」和「世界」页创建数据，
            <br />
            并在大纲节点上标注本章出场人物
          </span>
        </p>
      )}

      <div
        className={clsx(
          'sticky bottom-0 z-10 -mx-4 mt-2 border-t border-novel-border/90 bg-novel-panel/95 backdrop-blur-sm px-4 pb-4 pt-3 shadow-[0_-8px_24px_-4px_rgba(0,0,0,0.06)]',
          hasAiSuggestions && 'ring-1 ring-inset ring-amber-200/80',
        )}
      >
        <p className="text-[10px] text-novel-ink-faint mb-2 text-center">
          {hasAiSuggestions
            ? '核对预填项后点击下方按钮写入数据库'
            : '填写或 AI 分析后，提交以同步人物 / 故事线 / 资产'}
        </p>
        <div className="flex gap-2">
          {onAutoDebrief && (
            <button
              type="button"
              onClick={() => onAutoDebrief(hasAiSuggestions)}
              disabled={autoDebriefing || cacheHydrating || submitting || !debriefContentReady}
              className="flex items-center justify-center gap-1.5 text-xs py-2.5 px-3 border border-amber-300 text-amber-800 bg-amber-50 hover:bg-amber-100 rounded-xl font-semibold disabled:opacity-50 transition-novel shrink-0"
            >
              <Bot size={13} className={autoDebriefing ? 'animate-pulse' : ''} />
              {autoDebriefing ? '分析中' : hasAiSuggestions ? '重新分析' : 'AI 分析'}
            </button>
          )}
          <button
            type="button"
            onClick={() => onSubmit(buildSelectedAssetUpdates())}
            disabled={submitting || autoDebriefing || cacheHydrating}
            className={clsx(
              'flex-1 flex items-center justify-center gap-2 min-h-[3rem] rounded-xl text-[15px] font-semibold text-white shadow-lg transition-all disabled:opacity-55 disabled:shadow-none active:scale-[0.99]',
              hasAiSuggestions
                ? 'bg-gradient-to-b from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 ring-2 ring-amber-300/70 shadow-amber-900/25'
                : 'bg-novel-accent hover:bg-novel-accent-hover ring-2 ring-black/10 shadow-stone-900/20',
            )}
          >
            <CheckSquare size={18} strokeWidth={2.25} className={submitting ? 'animate-pulse' : ''} />
            {submitting ? '提交中…' : hasAiSuggestions ? '确认并提交' : '提交复盘'}
          </button>
        </div>
      </div>
    </div>
  )
}
