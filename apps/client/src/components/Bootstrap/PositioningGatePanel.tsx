/**
 * @file PositioningGatePanel — 立项定位内容区（human-in-the-loop Step0）
 *
 * - ``externalActions=true`` 时由 ``BootstrapGateTimelineDetail`` 等外壳统一提供底部主按钮，
 *   本组件通过 ``ref.submitApprove()`` 提交当前（含 JSON 编辑）内容。
 */
import React, { forwardRef, useEffect, useImperativeHandle, useState } from 'react'
import { ChevronDown, ChevronUp, Edit2 } from 'lucide-react'
import clsx from 'clsx'

export type PositioningGatePanelHandle = {
  /** @returns 通过校验的 positioning；JSON 非法时返回 null */
  submitApprove: () => Record<string, any> | null
}

interface Props {
  positioning: Record<string, any>
  /** 为 true 时不渲染底部主按钮区（由外壳统一排版） */
  externalActions?: boolean
}

function paceLabel(v: string) {
  return v === 'fast' ? '快节奏（番茄式爽快）' : v === 'slow' ? '慢节奏（猫腻式文笔）' : '中速（起点标准）'
}

function emotionLabel(v: string) {
  return { none: '无情感线', low: '低（10%）', medium: '中（25%）', high: '高（40%）' }[v] ?? v
}

/**
 * 番茄专属立项定位展示区。
 * 当 ``positioning`` 含 ``genre_archetype`` 字段时由 PositioningGatePanel 调用。
 *
 * @param p - 番茄算法立项定位对象（来自 gen_algo_positioning 输出）
 */
function FanqiePositioningView({ p }: { p: Record<string, any> }) {
  const crp = p.completion_rate_prediction as Record<string, number> | undefined
  return (
    <div className="flex-1 overflow-y-auto py-4 space-y-3 px-1">
      {/* 类型公式 + 算法钩子 */}
      <div className="bg-orange-50 border border-orange-200/90 rounded-xl px-4 py-3">
        <div className="text-xs text-orange-600 font-medium mb-1">🍅 番茄类型公式</div>
        <div className="text-sm font-semibold text-orange-950 leading-relaxed">{p.genre_archetype}</div>
        {p.algo_hook && (
          <div className="mt-2 text-xs text-orange-700 border-t border-orange-200/60 pt-2">
            <span className="font-medium">算法钩子：</span>{p.algo_hook}
          </div>
        )}
      </div>

      {/* 核心爽感 */}
      {p.core_satisfaction && (
        <div className="bg-amber-50 border border-amber-200/90 rounded-xl px-4 py-3">
          <div className="text-xs text-amber-600 font-medium mb-1">核心爽感（唯一卖点）</div>
          <div className="text-sm font-semibold text-amber-950 leading-relaxed">{p.core_satisfaction}</div>
        </div>
      )}

      {/* 差异化卖点 */}
      {p.differentiation && (
        <div className="text-xs text-gray-700 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
          <span className="text-gray-400 mr-1 font-medium">差异化</span>{p.differentiation}
        </div>
      )}

      {/* 平台标签 */}
      {Array.isArray(p.platform_tags) && p.platform_tags.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">平台推荐标签</div>
          <div className="flex flex-wrap gap-1.5">
            {p.platform_tags.map((t: string) => (
              <span key={t} className="px-2.5 py-1 bg-blue-50 border border-blue-200/90 text-blue-800 rounded-full text-xs font-medium">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 竞品参照 */}
      {Array.isArray(p.competitor_works) && p.competitor_works.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">竞品参照</div>
          <div className="flex flex-wrap gap-1.5">
            {p.competitor_works.map((w: string) => (
              <span key={w} className="px-2.5 py-1 bg-gray-100 border border-gray-200 text-gray-700 rounded-full text-xs">
                {w}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 完读率预测 */}
      {crp && (
        <div>
          <div className="text-xs text-gray-500 font-medium mb-1.5">完读率预测</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {([['第1章', crp.ch1], ['第3章', crp.ch3], ['第5章', crp.ch5]] as [string, number | undefined][])
              .filter(([, v]) => v != null)
              .map(([label, val]) => (
                <div key={label} className={clsx(
                  'rounded-lg px-3 py-2 text-center',
                  (val ?? 0) >= 50 ? 'bg-emerald-50 border border-emerald-200' : 'bg-orange-50 border border-orange-200',
                )}>
                  <div className="text-gray-400 mb-0.5">{label}</div>
                  <div className={clsx('font-semibold', (val ?? 0) >= 50 ? 'text-emerald-700' : 'text-orange-700')}>
                    {val}%
                  </div>
                </div>
              ))
            }
          </div>
        </div>
      )}

      {/* 禁忌自查 */}
      {p.taboo_check && typeof p.taboo_check === 'object' && (
        <div className={clsx(
          'text-xs rounded-lg px-3 py-2 leading-relaxed border',
          p.taboo_check.pass ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200',
        )}>
          <span className={clsx('font-medium mr-1', p.taboo_check.pass ? 'text-emerald-700' : 'text-red-700')}>
            {p.taboo_check.pass ? '✓ 禁忌自查通过' : '⚠ 禁忌自查未通过'}
          </span>
          {p.taboo_check.risk_note && (
            <span className="text-gray-600">{p.taboo_check.risk_note}</span>
          )}
        </div>
      )}
    </div>
  )
}

const PositioningGatePanel = forwardRef<PositioningGatePanelHandle, Props>(
  function PositioningGatePanel({ positioning, externalActions }, ref) {
    const [editing, setEditing]       = useState(false)
    const [jsonText, setJsonText]     = useState(() => JSON.stringify(positioning, null, 2))
    const [jsonError, setJsonError]   = useState('')

    useEffect(() => {
      setJsonText(JSON.stringify(positioning, null, 2))
      setJsonError('')
      setEditing(false)
    }, [positioning])

    useImperativeHandle(ref, () => ({
      submitApprove: () => {
        if (editing) {
          try {
            const parsed = JSON.parse(jsonText) as Record<string, any>
            return parsed
          } catch {
            setJsonError('JSON 格式有误，请检查后重试')
            return null
          }
        }
        return positioning
      },
    }), [editing, jsonText, positioning])

    const p = positioning
    /** 番茄专属立项定位：含 genre_archetype 字段时切换到专属视图 */
    const isFanqie = typeof p.genre_archetype === 'string' && p.genre_archetype.length > 0

    return (
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
        {!externalActions && (
          <div className="px-1 pb-3 shrink-0 border-b border-gray-100/90">
            <p className="text-xs text-gray-500 leading-relaxed">
              {isFanqie
                ? 'AI 已根据番茄算法逻辑完成立项定位；确认类型公式与核心爽感后继续生成。'
                : 'AI 从你的创意推导了市场定位；确认无误后可继续生成完整设定。'}
            </p>
          </div>
        )}

        {!editing && isFanqie && <FanqiePositioningView p={p} />}

        {!editing && !isFanqie && (
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
                    <span key={t} className="px-2.5 py-1 bg-blue-50 border border-blue-200/90 text-blue-800 rounded-full text-xs font-medium">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 text-xs">
              {[
                ['受众', p.target_audience],
                ['节奏', paceLabel(p.pace_type)],
                ['情感线', emotionLabel(p.emotional_arc)],
              ].map(([label, val]) => val && (
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
        )}

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
