/**
 * @file 复盘 — 下一章 patch 指令与语风指纹预览
 */
import { DIRECTIVE_PATCH_LABEL, PACING_LABEL } from './constants'
import type { DebriefPanelProps } from '../types'

export interface DirectivesSpeechKitSectionProps {
  aiNextChapterDirectives: NonNullable<DebriefPanelProps['aiNextChapterDirectives']>
  aiSpeechKitUpdates: NonNullable<DebriefPanelProps['aiSpeechKitUpdates']>
  fromQueueSnapshot?: boolean
  onRemoveNextChapterDirective?: DebriefPanelProps['onRemoveNextChapterDirective']
  onRemoveSpeechKitUpdate?: DebriefPanelProps['onRemoveSpeechKitUpdate']
}

/** 将 patch 对象格式化为可读摘要行
 *
 * 对于 AI 可能输出带实际数字的 key（如 must_resolve_promise_in_next_3_chapters），
 * 先精确查 DIRECTIVE_PATCH_LABEL，查不到则做前缀模糊匹配，最终 fallback 到 raw key。
 */
function resolvePatchLabel(key: string): string {
  if (DIRECTIVE_PATCH_LABEL[key]) return DIRECTIVE_PATCH_LABEL[key]
  const prefixMatch = Object.keys(DIRECTIVE_PATCH_LABEL).find(
    (k) => k.endsWith('_N') && key.startsWith(k.slice(0, -1)),
  )
  return prefixMatch ? DIRECTIVE_PATCH_LABEL[prefixMatch] : key
}

function formatPatchLines(patch: Record<string, unknown>): string[] {
  return Object.entries(patch)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([key, value]) => {
      const label = resolvePatchLabel(key)
      if (key === 'adjust_pacing' && typeof value === 'string') {
        return `${label}：${PACING_LABEL[value] || value}`
      }
      if (Array.isArray(value)) {
        return `${label}：${value.join('、')}`
      }
      return `${label}：${String(value)}`
    })
}

export function DirectivesSpeechKitSection({
  aiNextChapterDirectives,
  aiSpeechKitUpdates,
  fromQueueSnapshot = false,
  onRemoveNextChapterDirective,
  onRemoveSpeechKitUpdate,
}: DirectivesSpeechKitSectionProps) {
  if (aiNextChapterDirectives.length === 0 && aiSpeechKitUpdates.length === 0) return null

  return (
    <section className="rounded-novel border border-sky-200 bg-sky-50/50 px-3 py-2.5 space-y-3">
      <span className="text-[10px] font-semibold text-sky-800 uppercase tracking-wider block">
        续写闭环（下一章指令 / 语风）
      </span>

      {aiNextChapterDirectives.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[9px] text-sky-700/80">下一章 patch 指令（提交后写入章纲 extra）</p>
          {aiNextChapterDirectives.map((d, idx) => {
            const lines = formatPatchLines(d.patch || {})
            if (lines.length === 0) return null
            // key 用 outline_node_id + patch 字段名拼合，移除中间项时不会因下标错位导致 diff 混乱
            const directiveKey = `directive-${d.outline_node_id || 'auto'}-${Object.keys(d.patch || {}).join('_')}-${idx}`
            return (
              <div
                key={directiveKey}
                className="flex items-start gap-2 text-[11px] text-sky-950 bg-white/80 rounded border border-sky-100 px-2 py-1.5"
              >
                <div className="flex-1 leading-relaxed space-y-0.5">
                  {lines.map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                  {d.reason && (
                    <p className="text-[10px] text-sky-600/90 italic mt-0.5">理由：{d.reason}</p>
                  )}
                </div>
                {onRemoveNextChapterDirective && !fromQueueSnapshot && (
                  <button
                    type="button"
                    onClick={() => onRemoveNextChapterDirective(idx)}
                    className="text-[9px] text-sky-500 hover:text-sky-800 shrink-0"
                  >
                    移除
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {aiSpeechKitUpdates.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[9px] text-sky-700/80">语风指纹增量（提交后合并进人物 speech_kit）</p>
          {aiSpeechKitUpdates.map((sku, idx) => (
            <div
              // key 用 character_id，同一人物不会重复出现；fallback 到 idx 仅在 id 缺失时
              key={sku.character_id ? `speech-kit-${sku.character_id}` : `speech-kit-idx-${idx}`}
              className="flex items-start gap-2 text-[11px] text-sky-950 bg-white/80 rounded border border-sky-100 px-2 py-1.5"
            >
              <div className="flex-1 leading-relaxed space-y-0.5">
                <span className="font-semibold">{sku.character_name || sku.character_id}</span>
                {(sku.new_signature_words?.length ?? 0) > 0 && (
                  <p className="text-[10px]">
                    口头禅：{sku.new_signature_words!.join('、')}
                  </p>
                )}
                {(sku.new_sample_dialogues?.length ?? 0) > 0 && (
                  <p className="text-[10px] text-sky-800/90">
                    台词样本：{sku.new_sample_dialogues!.slice(0, 2).join(' / ')}
                  </p>
                )}
                {sku.evolution_note && (
                  <p className="text-[10px] text-sky-600/90 italic">{sku.evolution_note}</p>
                )}
              </div>
              {onRemoveSpeechKitUpdate && !fromQueueSnapshot && (
                <button
                  type="button"
                  onClick={() => onRemoveSpeechKitUpdate(idx)}
                  className="text-[9px] text-sky-500 hover:text-sky-800 shrink-0"
                >
                  移除
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
