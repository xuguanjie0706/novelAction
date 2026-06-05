/**
 * WarnPanel.tsx — 写前预警 Tab 内容
 *
 * 负责渲染 warnLoading / warnResult / warnHistory 等 UI。
 */
import React from 'react'
import clsx from 'clsx'
import {
  CheckCircle,
  Feather,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Target,
} from 'lucide-react'
import type { PreWriteWarnResult, PreWriteWarnHistoryRow, StorylinePreWarnItem } from './types'
import { normalizePreWriteWarnResult } from './utils'

export default function WarnPanel({
  runPreWriteWarning,
  warnLoading,
  warnResult,
  storylinePreWarns,
  warnHistory,
  selectedWarnRecordId,
  setSelectedWarnRecordId,
  setWarnResult,
  gatedPreWarnDoneForChapter,
}: {
  runPreWriteWarning: () => void | Promise<void>
  warnLoading: boolean
  warnResult: PreWriteWarnResult | null
  storylinePreWarns: StorylinePreWarnItem[]
  warnHistory: PreWriteWarnHistoryRow[]
  selectedWarnRecordId: string | null
  setSelectedWarnRecordId: React.Dispatch<React.SetStateAction<string | null>>
  setWarnResult: React.Dispatch<React.SetStateAction<PreWriteWarnResult | null>>
  gatedPreWarnDoneForChapter: boolean
}) {
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-novel-ink flex items-center gap-1.5">
          <ShieldAlert size={13} className="text-rose-500" />
          写前预警
        </span>
        <button
          type="button"
          onClick={() => void runPreWriteWarning()}
          disabled={warnLoading}
          className="text-xs px-2.5 py-1 rounded-lg border border-novel-border bg-novel-card hover:bg-novel-panel transition-novel disabled:opacity-40 flex items-center gap-1"
        >
          {warnLoading ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          重新检测
        </button>
      </div>

      {warnHistory.length > 0 && (
        <div className="space-y-1">
          <label className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">
            历史记录
          </label>
          <select
            value={selectedWarnRecordId ?? warnHistory[0]?.id ?? ''}
            onChange={e => {
              const id = e.target.value
              const row = warnHistory.find(h => h.id === id)
              if (row) {
                setSelectedWarnRecordId(id)
                setWarnResult(normalizePreWriteWarnResult(row.result))
              }
            }}
            className="w-full text-xs rounded-lg border border-novel-border bg-novel-panel px-2 py-1.5 text-novel-ink"
          >
            {warnHistory.map(h => (
              <option key={h.id} value={h.id}>
                {h.created_at && !Number.isNaN(new Date(h.created_at).getTime())
                  ? new Date(h.created_at).toLocaleString()
                  : '未知时间'}
                {' · '}
                {h.result?.risk_count ?? 0} 条风险 · {h.model_profile || 'local'}
              </option>
            ))}
          </select>
        </div>
      )}

      {warnLoading && (
        <div className="text-xs text-novel-ink-muted text-center py-8">
          <RefreshCw size={16} className="animate-spin mx-auto mb-2 text-rose-400" />
          正在对照记忆库检查矛盾…
        </div>
      )}

      {!warnLoading && !warnResult && (
        <div className="text-xs text-novel-ink-faint text-center py-8 leading-relaxed">
          {gatedPreWarnDoneForChapter ? (
            <>
              门控写作已完成写前预警，正在同步记录…
              <br />
              若仍为空请点「重新检测」
            </>
          ) : (
            <>
              点击工具栏「预警」或门控生成后
              <br />
              可查看连续性、伏笔与写法简报
            </>
          )}
        </div>
      )}

      {(storylinePreWarns.length > 0 || (warnResult?.storyline_pre_warns?.length ?? 0) > 0) && (
        <div className="space-y-1.5 rounded-lg border border-indigo-200 bg-indigo-50/80 p-2.5">
          <p className="text-[10px] font-semibold text-indigo-800 uppercase tracking-wide">
            故事线织网预警
          </p>
          {(storylinePreWarns.length ? storylinePreWarns : warnResult?.storyline_pre_warns ?? []).map(
            (w, i) => (
              <div
                key={w.warn_id || i}
                className={clsx(
                  'text-xs rounded-md px-2 py-1.5 border',
                  w.severity === 'critical' && 'bg-rose-50 border-rose-200 text-rose-900',
                  w.severity === 'warning' && 'bg-amber-50 border-amber-200 text-amber-900',
                  w.severity === 'info' && 'bg-sky-50 border-sky-200 text-sky-900',
                )}
              >
                <p className="font-medium">{w.title}</p>
                {w.detail && <p className="mt-0.5 opacity-90">{w.detail}</p>}
              </div>
            ),
          )}
        </div>
      )}

      {!warnLoading && warnResult && (
        <>
          {/* 总体状态 */}
          <div
            className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium',
              warnResult.error
                ? 'bg-amber-50 border border-amber-200 text-amber-800'
                : warnResult.ok
                  ? 'bg-green-50 border border-green-200 text-green-700'
                  : 'bg-rose-50 border border-rose-200 text-rose-700',
            )}
          >
            {warnResult.error ? (
              <ShieldAlert size={14} />
            ) : warnResult.ok ? (
              <ShieldCheck size={14} />
            ) : (
              <ShieldAlert size={14} />
            )}
            {warnResult.error
              ? '主编审稿未完整解析，请重新检测'
              : warnResult.ok
                ? `未发现高危风险，可以动笔`
                : `发现 ${warnResult.risk_count} 处风险，建议先修正`}
          </div>

          {/* ── 伏笔日程锁定表（第 1 章起即可生效）── */}
          {warnResult.foreshadow_schedule_lock?.has_schedule && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-2.5 space-y-1.5">
              <p className="text-[10px] font-semibold text-amber-900 uppercase tracking-wide flex items-center gap-1">
                <ShieldCheck size={10} />
                伏笔日程锁定表
                {warnResult.foreshadow_schedule_lock.current_chapter_number != null && (
                  <span className="font-normal normal-case text-amber-800">
                    （第{warnResult.foreshadow_schedule_lock.current_chapter_number}章）
                  </span>
                )}
              </p>
              {(warnResult.foreshadow_schedule_lock.opening_teases ?? []).map((t, i) => (
                <p key={`tease-${i}`} className="text-xs text-amber-900 pl-2 leading-relaxed">
                  · 允许预告：{t.label}
                  {t.detail ? ` — ${t.detail.slice(0, 160)}${t.detail.length > 160 ? '…' : ''}` : ''}
                </p>
              ))}
              {(warnResult.foreshadow_schedule_lock.allowed_this_chapter ?? []).map((a, i) => (
                <p key={`allow-${i}`} className="text-xs text-emerald-800 pl-2 leading-relaxed">
                  · 本章应{a.op === 'lay' ? '埋设' : '加热'}：{a.name}
                  {a.detail ? ` — ${a.detail.slice(0, 120)}` : ''}
                </p>
              ))}
              {(warnResult.foreshadow_schedule_lock.forbidden_early_plants ?? []).map((f, i) => (
                <p key={`forbid-fs-${i}`} className="text-xs text-rose-700 pl-2 leading-relaxed">
                  ⛔ 第{f.planned_lay_chapter}章才埋：{f.name}
                </p>
              ))}
              {(warnResult.foreshadow_schedule_lock.outline_conflicts ?? []).map((c, i) => (
                <p key={`fsc-${i}`} className="text-xs text-amber-800 pl-2 leading-relaxed">
                  ⚠️ {c.reason || c.outline_text}
                </p>
              ))}
            </div>
          )}

          {/* ── 情节锁定表（程序生成，先于主编预警）── */}
          {warnResult.chapter_lock_table?.has_prev && (
            <div className="rounded-lg border border-violet-200 bg-violet-50/70 p-2.5 space-y-1.5">
              <p className="text-[10px] font-semibold text-violet-800 uppercase tracking-wide flex items-center gap-1">
                <ShieldCheck size={10} />
                情节锁定表
                {warnResult.chapter_lock_table.prev_chapter_number != null && (
                  <span className="font-normal normal-case text-violet-700">
                    （第{warnResult.chapter_lock_table.prev_chapter_number}章 → 第
                    {warnResult.chapter_lock_table.current_chapter_number}章）
                  </span>
                )}
              </p>
              {(warnResult.chapter_lock_table.locked_beats ?? []).map((b, i) => (
                <p key={i} className="text-xs text-violet-900 pl-2 leading-relaxed">
                  · 已发生：{b}
                </p>
              ))}
              {warnResult.chapter_lock_table.prev_tail_anchor && (
                <p className="text-xs text-violet-800 pl-2 leading-relaxed italic">
                  上章末尾：「{warnResult.chapter_lock_table.prev_tail_anchor.slice(0, 180)}
                  {warnResult.chapter_lock_table.prev_tail_anchor.length > 180 ? '…' : ''}」
                </p>
              )}
              {(warnResult.chapter_lock_table.forbidden_replays ?? []).map((f, i) => (
                <p key={`f-${i}`} className="text-xs text-rose-700 pl-2 leading-relaxed">
                  ⛔ {f}
                </p>
              ))}
              {(warnResult.chapter_lock_table.outline_conflicts ?? []).map((c, i) => (
                <p key={`c-${i}`} className="text-xs text-amber-800 pl-2 leading-relaxed">
                  ⚠️ {c.reason || c.outline_text}
                </p>
              ))}
            </div>
          )}

          {/* ── 主角状态锁定 ── */}
          {warnResult.protagonist_fact_sheet &&
            (warnResult.protagonist_fact_sheet.realm ||
              warnResult.protagonist_fact_sheet.key_skills.length > 0 ||
              warnResult.protagonist_fact_sheet.forbidden.length > 0) && (
              <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-2.5 space-y-1.5">
                <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wide flex items-center gap-1">
                  <Target size={10} />
                  主角状态锁定
                </p>

                {warnResult.protagonist_fact_sheet.realm && (
                  <p className="text-xs text-blue-900">
                    <span className="font-medium">境界：</span>
                    {warnResult.protagonist_fact_sheet.realm}
                    {warnResult.protagonist_fact_sheet.location && (
                      <span className="ml-2 text-blue-700">／位置：{warnResult.protagonist_fact_sheet.location}</span>
                    )}
                  </p>
                )}

                {warnResult.protagonist_fact_sheet.key_skills.length > 0 && (
                  <div className="text-xs text-blue-800 space-y-0.5">
                    <span className="font-medium">可用技能：</span>
                    {warnResult.protagonist_fact_sheet.key_skills.map((s, i) => (
                      <div key={i} className="pl-2 text-blue-700 leading-relaxed">
                        · {s}
                      </div>
                    ))}
                  </div>
                )}

                {warnResult.protagonist_fact_sheet.key_items.length > 0 && (
                  <div className="text-xs text-blue-800 space-y-0.5">
                    <span className="font-medium">持有道具：</span>
                    {warnResult.protagonist_fact_sheet.key_items.map((s, i) => (
                      <div key={i} className="pl-2 text-blue-700 leading-relaxed">
                        · {s}
                      </div>
                    ))}
                  </div>
                )}

                {warnResult.protagonist_fact_sheet.forbidden.length > 0 && (
                  <div className="text-xs space-y-0.5">
                    <span className="font-medium text-rose-700">⛔ 本章禁止：</span>
                    {warnResult.protagonist_fact_sheet.forbidden.map((s, i) => (
                      <div key={i} className="pl-2 text-rose-600 leading-relaxed">
                        · {s}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          {/* ── 本章写作简报 ── */}
          {warnResult.writing_brief &&
          (warnResult.writing_brief.opening_strategy ||
            warnResult.writing_brief.conflict_structure ||
            warnResult.writing_brief.closing_hook) && (
            <div className="rounded-lg border border-purple-200 bg-purple-50/50 p-2.5 space-y-1.5">
              <p className="text-[10px] font-semibold text-purple-700 uppercase tracking-wide flex items-center gap-1">
                <Feather size={10} />
                本章写法简报
              </p>

              {warnResult.writing_brief.opening_strategy && (
                <div className="text-xs">
                  <span className="font-medium text-purple-800">开篇策略：</span>
                  <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.opening_strategy}</span>
                </div>
              )}

              {warnResult.writing_brief.conflict_structure && (
                <div className="text-xs">
                  <span className="font-medium text-purple-800">冲突节拍：</span>
                  <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.conflict_structure}</span>
                </div>
              )}

              {warnResult.writing_brief.closing_hook && (
                <div className="text-xs">
                  <span className="font-medium text-purple-800">章末钩子：</span>
                  <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.closing_hook}</span>
                </div>
              )}

              {warnResult.writing_brief.word_rhythm && (
                <div className="text-xs">
                  <span className="font-medium text-purple-800">字数节奏：</span>
                  <span className="text-purple-700 leading-relaxed">{warnResult.writing_brief.word_rhythm}</span>
                </div>
              )}
            </div>
          )}

          {/* ── 必发事件 ── */}
          {(warnResult.must_events?.length ?? 0) > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide flex items-center gap-1">
                <CheckCircle size={10} className="text-emerald-500" />
                必发事件
              </p>
              {warnResult.must_events!.map((ev, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs text-novel-ink">
                  <span className="text-emerald-500 shrink-0 mt-0.5 font-bold">{i + 1}.</span>
                  <span className="leading-relaxed">{ev}</span>
                </div>
              ))}
            </div>
          )}

          {/* ── 幻觉预防 ── */}
          {(warnResult.hallucination_traps?.length ?? 0) > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide flex items-center gap-1">
                <ShieldAlert size={10} className="text-amber-500" />
                幻觉预防清单
              </p>
              {warnResult.hallucination_traps!.map((trap, i) => (
                <div
                  key={i}
                  className="flex items-start gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5"
                >
                  <span className="shrink-0 mt-0.5">⚠</span>
                  <span className="leading-relaxed">{trap}</span>
                </div>
              ))}
            </div>
          )}

          {/* ── 风险列表 ── */}
          {warnResult.risks.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">风险扫描</p>
              {warnResult.risks.map((risk, i) => (
                <div
                  key={i}
                  className={clsx(
                    'rounded-lg border p-2.5 text-xs space-y-1',
                    risk.severity === 'critical' || risk.severity === 'high'
                      ? 'border-rose-200 bg-rose-50'
                      : 'border-amber-200 bg-amber-50',
                  )}
                >
                  <div className="flex items-center gap-1.5 font-medium">
                    <span
                      className={clsx(
                        'px-1.5 py-0.5 rounded text-[10px]',
                        risk.severity === 'critical' || risk.severity === 'high'
                          ? 'bg-rose-200 text-rose-700'
                          : 'bg-amber-200 text-amber-700',
                      )}
                    >
                      {risk.severity}
                    </span>
                    <span className="text-novel-ink-muted">{risk.type}</span>
                  </div>
                  <p className="text-novel-ink leading-relaxed">{risk.description}</p>
                  {risk.suggested_fix && (
                    <p className="text-novel-ink-muted leading-relaxed border-t border-current/10 pt-1">
                      建议：{risk.suggested_fix}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── 写前提醒 ── */}
          {warnResult.reminders.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold text-novel-ink-muted uppercase tracking-wide">写前提醒</p>
              {warnResult.reminders.map((r, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs text-novel-ink-muted">
                  <span className="text-novel-accent shrink-0 mt-0.5">·</span>
                  <span className="leading-relaxed">{r}</span>
                </div>
              ))}
            </div>
          )}

          {warnResult.error && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-900 leading-relaxed space-y-1">
              <p className="font-medium text-amber-800">主编审稿 JSON 解析失败</p>
              <p className="opacity-90">{warnResult.error}</p>
              {warnResult.raw && (
                <pre className="mt-1 max-h-32 overflow-auto text-[9px] text-amber-800/90 whitespace-pre-wrap break-all bg-amber-100/50 rounded p-1.5">
                  {warnResult.raw}
                </pre>
              )}
              <p className="text-[10px] text-amber-700">
                多为模型推理占满输出预算导致 JSON 被截断；请点「重新检测」（已提高 max_tokens 并自动重试）。
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

