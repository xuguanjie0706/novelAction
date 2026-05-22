/**
 * @file PositioningGatePanel — 立项定位内容区（human-in-the-loop Step0）
 *
 * 多候选模式（positioning.candidates 存在时）：
 *   - 展示 2-3 个竞品方案卡；auto_selected_index 方案高亮
 *   - 每张卡显示：方案名 / selling_point / tropes / hook_text / 读者评分 / 风险级别
 *   - 用户可切换选中方案；"确认并继续"提交含 candidates 元数据的完整 dict
 *
 * 单方案兼容模式（旧版 / 番茄专属）：保持原始渲染逻辑不变。
 *
 * ``externalActions=true`` 时底部主按钮由外壳（BootstrapGateTimelineDetail）统一提供；
 * 本组件通过 ``ref.submitApprove()`` 暴露当前选中 positioning。
 */
import React, { forwardRef, useEffect, useImperativeHandle, useState } from 'react'
import { ChevronDown, ChevronUp, Edit2, CheckCircle2, Star } from 'lucide-react'
import clsx from 'clsx'

export type PositioningGatePanelHandle = {
  /** @returns 通过校验的 positioning（含 candidates 元数据）；JSON 非法时返回 null */
  submitApprove: () => Record<string, any> | null
}

interface Props {
  positioning: Record<string, any>
  /** 为 true 时不渲染底部主按钮区（由外壳统一排版） */
  externalActions?: boolean
}

function paceLabel(v: string) {
  return v === 'fast' ? '快节奏（番茄爽快）' : v === 'slow' ? '慢节奏（猫腻文笔）' : '中速（起点标准）'
}

function emotionLabel(v: string) {
  return { none: '无情感线', low: '低（10%）', medium: '中（25%）', high: '高（40%）' }[v] ?? v
}

function riskColor(level: string) {
  if (level === '低') return 'text-emerald-700 bg-emerald-50 border-emerald-200'
  if (level === '高') return 'text-red-700 bg-red-50 border-red-200'
  return 'text-amber-700 bg-amber-50 border-amber-200'
}

function scoreColor(score: number) {
  if (score >= 8) return 'text-emerald-700'
  if (score >= 6) return 'text-amber-700'
  return 'text-red-600'
}

// ──────────────────────────────────────────────────────
// 番茄专属立项定位视图（含 genre_archetype 字段时使用）
// ──────────────────────────────────────────────────────

function FanqiePositioningView({ p }: { p: Record<string, any> }) {
  const crp = p.completion_rate_prediction as Record<string, number> | undefined
  return (
    <div className="flex-1 overflow-y-auto py-4 space-y-3 px-1">
      <div className="bg-orange-50 border border-orange-200/90 rounded-xl px-4 py-3">
        <div className="text-xs text-orange-600 font-medium mb-1">🍅 番茄类型公式</div>
        <div className="text-sm font-semibold text-orange-950 leading-relaxed">{p.genre_archetype}</div>
        {p.algo_hook && (
          <div className="mt-2 text-xs text-orange-700 border-t border-orange-200/60 pt-2">
            <span className="font-medium">算法钩子：</span>{p.algo_hook}
          </div>
        )}
      </div>
      {p.core_satisfaction && (
        <div className="bg-amber-50 border border-amber-200/90 rounded-xl px-4 py-3">
          <div className="text-xs text-amber-600 font-medium mb-1">核心爽感（唯一卖点）</div>
          <div className="text-sm font-semibold text-amber-950 leading-relaxed">{p.core_satisfaction}</div>
        </div>
      )}
      {p.differentiation && (
        <div className="text-xs text-gray-700 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
          <span className="text-gray-400 mr-1 font-medium">差异化</span>{p.differentiation}
        </div>
      )}
      {Array.isArray(p.platform_tags) && p.platform_tags.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">平台推荐标签</div>
          <div className="flex flex-wrap gap-1.5">
            {p.platform_tags.map((t: string) => (
              <span key={t} className="px-2.5 py-1 bg-blue-50 border border-blue-200/90 text-blue-800 rounded-full text-xs font-medium">{t}</span>
            ))}
          </div>
        </div>
      )}
      {crp && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">完读率预测</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {([['第1章', crp.ch1], ['第3章', crp.ch3], ['第5章', crp.ch5]] as [string, number | undefined][])
              .filter(([, v]) => v != null)
              .map(([label, val]) => (
                <div key={label} className={clsx('rounded-lg px-3 py-2 text-center',
                  (val ?? 0) >= 50 ? 'bg-emerald-50 border border-emerald-200' : 'bg-orange-50 border border-orange-200')}>
                  <div className="text-gray-400 mb-0.5">{label}</div>
                  <div className={clsx('font-semibold', (val ?? 0) >= 50 ? 'text-emerald-700' : 'text-orange-700')}>{val}%</div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 单候选方案卡片
// ──────────────────────────────────────────────────────

interface CandidateCardProps {
  candidate: Record<string, any>
  index: number
  isSelected: boolean
  isAutoSelected: boolean
  onSelect: (idx: number) => void
}

function CandidateCard({ candidate: c, index, isSelected, isAutoSelected, onSelect }: CandidateCardProps) {
  const readerScore = typeof c.reader_score === 'number' ? c.reader_score : 0
  return (
    <button
      type="button"
      onClick={() => onSelect(index)}
      className={clsx(
        'w-full text-left rounded-xl border-2 p-4 transition-all duration-150 focus:outline-none',
        isSelected
          ? 'border-amber-400 bg-amber-50/60 shadow-sm'
          : 'border-gray-200 bg-white hover:border-amber-200 hover:shadow-sm',
      )}
    >
      {/* 卡头：方案名 + 自动择优徽章 + 选中图标 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={clsx(
            'shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded-full border',
            isSelected ? 'bg-amber-400 text-white border-amber-400' : 'bg-gray-100 text-gray-500 border-gray-200',
          )}>方案{index + 1}</span>
          <span className="text-sm font-semibold text-gray-900 truncate">
            {c.name || `定位方案 ${index + 1}`}
          </span>
          {isAutoSelected && (
            <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] bg-blue-50 border border-blue-200 text-blue-700 rounded-full px-1.5 py-0.5 font-medium">
              <Star size={9} className="fill-blue-500 text-blue-500" />AI推荐
            </span>
          )}
        </div>
        {isSelected && <CheckCircle2 size={16} className="shrink-0 text-amber-500 mt-0.5" />}
      </div>

      {/* 卖点钩子 */}
      {c.selling_point && (
        <div className="text-xs font-medium text-gray-800 mb-2 leading-relaxed bg-white rounded-lg px-2.5 py-1.5 border border-gray-100">
          {c.selling_point}
        </div>
      )}

      {/* 钩子文本 + 读者评分 */}
      {c.hook_text && (
        <div className="text-[11px] text-gray-600 italic mb-2 leading-relaxed border-l-2 border-gray-200 pl-2">
          「{c.hook_text}」
        </div>
      )}

      {/* 元信息行：读者分 / 签约率 / 天花板 / 风险 */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {readerScore > 0 && (
          <span className={clsx('text-[11px] font-semibold rounded-full px-2 py-0.5 border', scoreColor(readerScore),
            readerScore >= 8 ? 'bg-emerald-50 border-emerald-200' : readerScore >= 6 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200')}>
            读者 {readerScore}/10
          </span>
        )}
        {c.expected_sign_rate && (
          <span className="text-[11px] text-gray-600 bg-gray-50 border border-gray-200 rounded-full px-2 py-0.5">
            签约率 {c.expected_sign_rate}
          </span>
        )}
        {c.ceiling && (
          <span className="text-[11px] text-gray-600 bg-gray-50 border border-gray-200 rounded-full px-2 py-0.5 max-w-[140px] truncate" title={c.ceiling}>
            {c.ceiling}
          </span>
        )}
        {c.risk_level && (
          <span className={clsx('text-[11px] rounded-full px-2 py-0.5 border', riskColor(c.risk_level))}>
            风险{c.risk_level}
          </span>
        )}
      </div>

      {/* 爽点标签 */}
      {Array.isArray(c.tropes) && c.tropes.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {c.tropes.slice(0, 4).map((t: string) => (
            <span key={t} className="text-[10px] px-1.5 py-0.5 bg-blue-50 border border-blue-100 text-blue-700 rounded-full">
              {t}
            </span>
          ))}
          {c.tropes.length > 4 && (
            <span className="text-[10px] text-gray-400">+{c.tropes.length - 4}</span>
          )}
        </div>
      )}

      {/* 读者理由（选中时展示） */}
      {isSelected && c.reader_reason && (
        <div className="mt-2 text-[11px] text-gray-500 italic border-t border-gray-100 pt-2">
          读者视角：{c.reader_reason}
        </div>
      )}
    </button>
  )
}

// ──────────────────────────────────────────────────────
// 多候选方案视图
// ──────────────────────────────────────────────────────

interface CandidatesViewProps {
  positioning: Record<string, any>
  selectedIdx: number
  onSelect: (idx: number) => void
}

function CandidatesView({ positioning, selectedIdx, onSelect }: CandidatesViewProps) {
  const candidates: Record<string, any>[] = positioning.candidates ?? []
  const autoIdx: number = typeof positioning.auto_selected_index === 'number'
    ? positioning.auto_selected_index : 0
  const comparison: string = positioning.auto_selection_comparison ?? ''
  const reason: string = positioning.auto_selection_reason ?? ''

  return (
    <div className="flex-1 overflow-y-auto py-3 space-y-3 px-1">
      {/* AI 择优摘要 */}
      {comparison && (
        <div className="rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-2.5">
          <div className="text-[10px] text-blue-500 font-semibold mb-1 uppercase tracking-wide">AI 编辑对比意见</div>
          <p className="text-xs text-blue-900 leading-relaxed">{comparison}</p>
          {reason && (
            <p className="mt-1 text-[11px] text-blue-700 font-medium">
              推荐理由：{reason}
            </p>
          )}
        </div>
      )}

      {/* 候选方案卡片列表 */}
      <div className="space-y-2.5">
        {candidates.map((c, i) => (
          <CandidateCard
            key={i}
            candidate={c}
            index={i}
            isSelected={selectedIdx === i}
            isAutoSelected={autoIdx === i}
            onSelect={onSelect}
          />
        ))}
      </div>

      {/* 选中方案的市场风险详情 */}
      {selectedIdx < candidates.length && candidates[selectedIdx]?.market_risk && (
        <div className="text-xs text-gray-600 bg-orange-50/80 border border-orange-100 rounded-lg px-3 py-2 leading-relaxed">
          <span className="text-orange-700 font-medium">市场风险分析 · </span>
          {candidates[selectedIdx].market_risk}
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 单方案默认视图（旧版兼容）
// ──────────────────────────────────────────────────────

function SinglePositioningView({ p }: { p: Record<string, any> }) {
  return (
    <div className="flex-1 overflow-y-auto py-4 space-y-3 px-1">
      {p.selling_point && (
        <div className="bg-amber-50 border border-amber-200/90 rounded-xl px-4 py-3">
          <div className="text-xs text-amber-600 font-medium mb-1">封面卖点</div>
          <div className="text-sm font-semibold text-amber-950 leading-relaxed">{p.selling_point}</div>
        </div>
      )}
      {Array.isArray(p.tropes) && p.tropes.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">核心爽点</div>
          <div className="flex flex-wrap gap-1.5">
            {p.tropes.map((t: string) => (
              <span key={t} className="px-2.5 py-1 bg-blue-50 border border-blue-200/90 text-blue-800 rounded-full text-xs font-medium">{t}</span>
            ))}
          </div>
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {[['受众', p.target_audience], ['节奏', paceLabel(p.pace_type)], ['情感线', emotionLabel(p.emotional_arc)]]
          .map(([label, val]) => val && (
            <div key={String(label)} className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-gray-400 mb-0.5">{label}</div>
              <div className="text-gray-800 font-medium leading-snug">{String(val)}</div>
            </div>
          ))}
      </div>
      {p.face_slap_pattern && (
        <div className="text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
          <span className="text-gray-400 mr-1">打脸节奏</span>{p.face_slap_pattern}
        </div>
      )}
      {p.market_risk && (
        <div className="text-xs text-gray-600 bg-orange-50/80 border border-orange-100 rounded-lg px-3 py-2 leading-relaxed">
          <span className="text-orange-700 font-medium">市场风险 · </span>{p.market_risk}
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// 主组件
// ──────────────────────────────────────────────────────

const PositioningGatePanel = forwardRef<PositioningGatePanelHandle, Props>(
  function PositioningGatePanel({ positioning, externalActions }, ref) {
    const hasCandidates = Array.isArray(positioning.candidates) && positioning.candidates.length > 0
    const initialIdx = typeof positioning.auto_selected_index === 'number'
      ? positioning.auto_selected_index : 0
    const [selectedIdx, setSelectedIdx] = useState(initialIdx)
    const [editing, setEditing]         = useState(false)
    const [jsonText, setJsonText]       = useState(() => JSON.stringify(positioning, null, 2))
    const [jsonError, setJsonError]     = useState('')

    useEffect(() => {
      setJsonText(JSON.stringify(positioning, null, 2))
      setJsonError('')
      setEditing(false)
      setSelectedIdx(
        typeof positioning.auto_selected_index === 'number' ? positioning.auto_selected_index : 0,
      )
    }, [positioning])

    useImperativeHandle(ref, () => ({
      submitApprove: () => {
        if (editing) {
          try {
            return JSON.parse(jsonText) as Record<string, any>
          } catch {
            setJsonError('JSON 格式有误，请检查后重试')
            return null
          }
        }
        if (hasCandidates) {
          // 用户已选中某候选：把选中候选的扁平字段 + 完整 candidates 元数据一起返回
          const candidates: Record<string, any>[] = positioning.candidates
          const selected = candidates[selectedIdx] ?? candidates[0]
          return {
            ...selected,
            candidates,
            auto_selected_index: positioning.auto_selected_index ?? 0,
            auto_selection_reason: positioning.auto_selection_reason ?? '',
            auto_selection_comparison: positioning.auto_selection_comparison ?? '',
          }
        }
        return positioning
      },
    }), [editing, jsonText, positioning, hasCandidates, selectedIdx])

    const isFanqie = typeof positioning.genre_archetype === 'string' && positioning.genre_archetype.length > 0

    return (
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
        {!externalActions && (
          <div className="px-1 pb-3 shrink-0 border-b border-gray-100/90">
            <p className="text-xs text-gray-500 leading-relaxed">
              {hasCandidates
                ? 'AI 已生成 3 个互竞定位方案并由读者模拟器评分；选择最符合你意图的方案后继续生成。'
                : isFanqie
                  ? 'AI 已根据番茄算法逻辑完成立项定位；确认类型公式与核心爽感后继续生成。'
                  : 'AI 从你的创意推导了市场定位；确认无误后可继续生成完整设定。'}
            </p>
          </div>
        )}

        {/* 多候选方案 */}
        {!editing && hasCandidates && (
          <CandidatesView positioning={positioning} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />
        )}

        {/* 番茄专属 */}
        {!editing && !hasCandidates && isFanqie && <FanqiePositioningView p={positioning} />}

        {/* 旧版单方案 */}
        {!editing && !hasCandidates && !isFanqie && <SinglePositioningView p={positioning} />}

        {/* JSON 编辑区 */}
        {editing && (
          <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-2 px-1 min-h-[200px]">
            <p className="text-xs text-gray-500">直接编辑 JSON，确认时将由后端做 schema 校验</p>
            <textarea
              className={clsx(
                'flex-1 min-h-[220px] font-mono text-xs border rounded-xl p-3 resize-none focus:outline-none focus:ring-2 focus:ring-amber-400/80',
                jsonError ? 'border-red-400' : 'border-gray-200',
              )}
              value={jsonText}
              onChange={e => { setJsonText(e.target.value); setJsonError('') }}
            />
            {jsonError && <p className="text-xs text-red-500">{jsonError}</p>}
          </div>
        )}

        <div className={externalActions ? 'pt-2 shrink-0' : 'px-1 pt-3 pb-1 shrink-0 space-y-2'}>
          <button
            type="button"
            onClick={() => setEditing(e => !e)}
            className="w-full py-2 text-sm text-gray-500 hover:text-gray-800 flex items-center justify-center gap-1 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Edit2 size={13} />
            {editing ? '收起 JSON 编辑' : '展开修改（JSON）'}
            {editing ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        </div>
      </div>
    )
  },
)

export default PositioningGatePanel
