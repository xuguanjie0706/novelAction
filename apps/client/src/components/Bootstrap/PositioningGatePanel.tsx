/**
 * @file PositioningGatePanel — 立项定位确认面板（human-in-the-loop 闸门）
 *
 * 职责：
 * - 在 Bootstrap Step 0 完成后展示 AI 生成的立项定位
 * - 用户可直接「确认继续」或「展开修改」后再继续
 * - 不持有自己的 API 状态；onConfirm 由父组件（GenerateWizard）提供
 *
 * 本文件 < 150 行
 */
import React, { useState } from 'react'
import { CheckCircle, ChevronDown, ChevronUp, Edit2, Loader } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  positioning: Record<string, any>
  /** 用户点击「确认继续」时调用，传入最终（可能已编辑过的）positioning */
  onConfirm: (positioning: Record<string, any>) => void
  /** 是否正在提交 resume（按钮禁用态） */
  loading?: boolean
}

/** 将 pace_type 枚举翻译为中文 */
function paceLabel(v: string) {
  return v === 'fast' ? '快节奏（番茄式爽快）' : v === 'slow' ? '慢节奏（猫腻式文笔）' : '中速（起点标准）'
}

/** 将 emotional_arc 枚举翻译为中文 */
function emotionLabel(v: string) {
  return { none: '无情感线', low: '低（10%）', medium: '中（25%）', high: '高（40%）' }[v] ?? v
}

export default function PositioningGatePanel({ positioning, onConfirm, loading }: Props) {
  const [editing, setEditing]       = useState(false)
  const [jsonText, setJsonText]     = useState(() => JSON.stringify(positioning, null, 2))
  const [jsonError, setJsonError]   = useState('')

  function handleConfirm() {
    if (editing) {
      try {
        const parsed = JSON.parse(jsonText)
        onConfirm(parsed)
      } catch {
        setJsonError('JSON 格式有误，请检查后重试')
      }
    } else {
      onConfirm(positioning)
    }
  }

  const p = positioning

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* 标题 */}
      <div className="px-6 pt-5 pb-3 shrink-0 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-1">
          <CheckCircle size={16} className="text-green-500" />
          <span className="font-semibold text-gray-800 text-sm">立项定位已生成，请确认后继续</span>
        </div>
        <p className="text-xs text-gray-400">AI 从你的创意推导了以下市场定位，确认无误后可继续生成完整设定</p>
      </div>

      {/* 摘要卡（只读展示） */}
      {!editing && (
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {/* 一句话卖点 */}
          {p.selling_point && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              <div className="text-xs text-amber-600 font-medium mb-1">封面卖点</div>
              <div className="text-sm font-semibold text-amber-900 leading-relaxed">{p.selling_point}</div>
            </div>
          )}

          {/* 核心爽点 */}
          {Array.isArray(p.tropes) && p.tropes.length > 0 && (
            <div>
              <div className="text-xs text-gray-500 font-medium mb-1.5">核心爽点</div>
              <div className="flex flex-wrap gap-1.5">
                {p.tropes.map((t: string) => (
                  <span key={t} className="px-2.5 py-1 bg-blue-50 border border-blue-200 text-blue-700 rounded-full text-xs font-medium">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 参数行：受众 / 节奏 / 情感线 */}
          <div className="grid grid-cols-3 gap-2 text-xs">
            {[
              ['受众', p.target_audience],
              ['节奏', paceLabel(p.pace_type)],
              ['情感线', emotionLabel(p.emotional_arc)],
            ].map(([label, val]) => val && (
              <div key={String(label)} className="bg-gray-50 rounded-lg px-3 py-2">
                <div className="text-gray-400 mb-0.5">{label}</div>
                <div className="text-gray-700 font-medium leading-snug">{String(val)}</div>
              </div>
            ))}
          </div>

          {/* 打脸节奏 */}
          {p.face_slap_pattern && (
            <div className="text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
              <span className="text-gray-400 mr-1">打脸节奏</span>{p.face_slap_pattern}
            </div>
          )}

          {/* 市场风险 */}
          {p.market_risk && (
            <div className="text-xs text-gray-500 bg-orange-50 border border-orange-100 rounded-lg px-3 py-2 leading-relaxed">
              <span className="text-orange-600 font-medium">市场风险 · </span>{p.market_risk}
            </div>
          )}
        </div>
      )}

      {/* 编辑区（展开修改） */}
      {editing && (
        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-2">
          <p className="text-xs text-gray-400">直接编辑 JSON，修改后点击「确认继续」</p>
          <textarea
            className={clsx(
              'flex-1 min-h-[240px] font-mono text-xs border rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-amber-400',
              jsonError ? 'border-red-400' : 'border-gray-200'
            )}
            value={jsonText}
            onChange={e => { setJsonText(e.target.value); setJsonError('') }}
          />
          {jsonError && <p className="text-xs text-red-500">{jsonError}</p>}
        </div>
      )}

      {/* 底部按钮 */}
      <div className="px-6 pb-6 pt-3 shrink-0 space-y-2">
        <button
          onClick={handleConfirm}
          disabled={loading}
          className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? <Loader size={15} className="animate-spin" /> : <CheckCircle size={15} />}
          确认继续生成
        </button>
        <button
          onClick={() => setEditing(e => !e)}
          className="w-full py-2 text-sm text-gray-400 hover:text-gray-600 flex items-center justify-center gap-1"
        >
          <Edit2 size={13} />
          {editing ? '收起' : '展开修改立项定位'}
          {editing ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>
    </div>
  )
}
