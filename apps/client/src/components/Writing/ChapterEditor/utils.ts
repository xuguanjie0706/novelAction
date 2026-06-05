/**
 * utils.ts — ChapterEditor 包内纯工具函数
 *
 * 职责：无副作用的纯函数，无 React 依赖，无 store 依赖。
 * 可安全在 hooks 和组件中共用。
 */
import type { Chapter, OutlineNode } from '../../../types'
import type { PreWriteWarnResult, PreWriteWarnHistoryRow } from './types'

// ─── 写前预警结果规范化 ────────────────────────────────────────────────────────

/**
 * 接口/DB 历史中的 result 可能缺字段，避免渲染时 .risks.length 抛错。
 *
 * @param raw - 来自 API 或 DB 的原始 result 对象（unknown）
 * @returns 填充了默认值的 PreWriteWarnResult
 */
export function normalizePreWriteWarnResult(raw: unknown): PreWriteWarnResult {
  const r = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const risksRaw = r.risks
  const risks: PreWriteWarnResult['risks'] = Array.isArray(risksRaw)
    ? risksRaw.map((risk: unknown) => {
        const rr = risk && typeof risk === 'object' ? (risk as Record<string, unknown>) : {}
        return {
          type: String(rr.type ?? ''),
          severity: String(rr.severity ?? 'medium'),
          description: String(rr.description ?? ''),
          suggested_fix: String(rr.suggested_fix ?? ''),
        }
      })
    : []
  const remindersRaw = r.reminders
  const reminders: string[] = Array.isArray(remindersRaw)
    ? remindersRaw.map(String).filter(Boolean)
    : []
  const risk_count = typeof r.risk_count === 'number' ? r.risk_count : risks.length
  const ok =
    typeof r.ok === 'boolean' ? r.ok
    : typeof r.ok === 'number' ? r.ok === 1
    : risk_count === 0
  const pfsRaw = r.protagonist_fact_sheet
  const protagonist_fact_sheet: PreWriteWarnResult['protagonist_fact_sheet'] =
    pfsRaw && typeof pfsRaw === 'object'
      ? {
          realm: String((pfsRaw as Record<string, unknown>).realm ?? ''),
          location: String((pfsRaw as Record<string, unknown>).location ?? ''),
          key_skills: Array.isArray((pfsRaw as Record<string, unknown>).key_skills)
            ? ((pfsRaw as Record<string, unknown>).key_skills as unknown[]).map(String)
            : [],
          key_items: Array.isArray((pfsRaw as Record<string, unknown>).key_items)
            ? ((pfsRaw as Record<string, unknown>).key_items as unknown[]).map(String)
            : [],
          forbidden: Array.isArray((pfsRaw as Record<string, unknown>).forbidden)
            ? ((pfsRaw as Record<string, unknown>).forbidden as unknown[]).map(String)
            : [],
        }
      : undefined
  const wbRaw = r.writing_brief
  const writing_brief: PreWriteWarnResult['writing_brief'] =
    wbRaw && typeof wbRaw === 'object'
      ? {
          opening_strategy: String((wbRaw as Record<string, unknown>).opening_strategy ?? ''),
          conflict_structure: String((wbRaw as Record<string, unknown>).conflict_structure ?? ''),
          closing_hook: String((wbRaw as Record<string, unknown>).closing_hook ?? ''),
          word_rhythm: String((wbRaw as Record<string, unknown>).word_rhythm ?? ''),
        }
      : undefined
  const must_events = Array.isArray(r.must_events) ? r.must_events.map(String).filter(Boolean) : []
  const hallucination_traps = Array.isArray(r.hallucination_traps) ? r.hallucination_traps.map(String).filter(Boolean) : []
  const error = typeof r.error === 'string' && r.error.trim() ? r.error.trim() : undefined
  const errorRaw = typeof r.raw === 'string' && r.raw.trim() ? r.raw.trim() : undefined
  const storyline_pre_warns = Array.isArray(r.storyline_pre_warns) ? r.storyline_pre_warns : undefined
  const cltRaw = r.chapter_lock_table
  const chapter_lock_table =
    cltRaw && typeof cltRaw === 'object'
      ? {
          has_prev: Boolean((cltRaw as Record<string, unknown>).has_prev),
          prev_chapter_number: (cltRaw as Record<string, unknown>).prev_chapter_number as
            | number
            | string
            | null
            | undefined,
          current_chapter_number: (cltRaw as Record<string, unknown>).current_chapter_number as
            | number
            | string
            | null
            | undefined,
          locked_beats: Array.isArray((cltRaw as Record<string, unknown>).locked_beats)
            ? ((cltRaw as Record<string, unknown>).locked_beats as unknown[]).map(String)
            : [],
          forbidden_replays: Array.isArray((cltRaw as Record<string, unknown>).forbidden_replays)
            ? ((cltRaw as Record<string, unknown>).forbidden_replays as unknown[]).map(String)
            : [],
          outline_conflicts: Array.isArray((cltRaw as Record<string, unknown>).outline_conflicts)
            ? ((cltRaw as Record<string, unknown>).outline_conflicts as unknown[]).map((c) => {
                const cc = c && typeof c === 'object' ? (c as Record<string, unknown>) : {}
                return {
                  field: String(cc.field ?? ''),
                  outline_text: String(cc.outline_text ?? ''),
                  reason: String(cc.reason ?? ''),
                }
              })
            : [],
          prev_tail_anchor: String((cltRaw as Record<string, unknown>).prev_tail_anchor ?? ''),
        }
      : undefined
  const fslRaw = r.foreshadow_schedule_lock
  const foreshadow_schedule_lock =
    fslRaw && typeof fslRaw === 'object'
      ? {
          has_schedule: Boolean((fslRaw as Record<string, unknown>).has_schedule),
          current_chapter_number: (fslRaw as Record<string, unknown>).current_chapter_number as
            | number
            | string
            | null
            | undefined,
          forbidden_early_plants: Array.isArray((fslRaw as Record<string, unknown>).forbidden_early_plants)
            ? ((fslRaw as Record<string, unknown>).forbidden_early_plants as unknown[]).map((item) => {
                const it = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
                return {
                  name: String(it.name ?? ''),
                  planned_lay_chapter:
                    typeof it.planned_lay_chapter === 'number' ? it.planned_lay_chapter : undefined,
                  reason: String(it.reason ?? ''),
                }
              })
            : [],
          allowed_this_chapter: Array.isArray((fslRaw as Record<string, unknown>).allowed_this_chapter)
            ? ((fslRaw as Record<string, unknown>).allowed_this_chapter as unknown[]).map((item) => {
                const it = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
                return {
                  name: String(it.name ?? ''),
                  op: String(it.op ?? ''),
                  detail: String(it.detail ?? ''),
                }
              })
            : [],
          opening_teases: Array.isArray((fslRaw as Record<string, unknown>).opening_teases)
            ? ((fslRaw as Record<string, unknown>).opening_teases as unknown[]).map((item) => {
                const it = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
                return { label: String(it.label ?? ''), detail: String(it.detail ?? '') }
              })
            : [],
          outline_conflicts: Array.isArray((fslRaw as Record<string, unknown>).outline_conflicts)
            ? ((fslRaw as Record<string, unknown>).outline_conflicts as unknown[]).map((c) => {
                const cc = c && typeof c === 'object' ? (c as Record<string, unknown>) : {}
                return {
                  field: String(cc.field ?? ''),
                  outline_text: String(cc.outline_text ?? ''),
                  reason: String(cc.reason ?? ''),
                }
              })
            : [],
        }
      : undefined
  return {
    ok,
    risk_count,
    risks,
    reminders,
    chapter_lock_table,
    foreshadow_schedule_lock,
    protagonist_fact_sheet,
    writing_brief,
    must_events,
    hallucination_traps,
    error,
    raw: errorRaw,
    storyline_pre_warns,
  }
}

/** 仅含空字段/故事线附带的占位结果，应被历史落库记录覆盖。 */
export function isShellPreWriteWarnResult(r: PreWriteWarnResult | null): boolean {
  if (!r) return false
  if (r.error) return false
  const pfs = r.protagonist_fact_sheet
  const hasPfs =
    Boolean(pfs?.realm?.trim())
    || Boolean(pfs?.location?.trim())
    || (pfs?.key_skills?.length ?? 0) > 0
    || (pfs?.key_items?.length ?? 0) > 0
    || (pfs?.forbidden?.length ?? 0) > 0
  const wb = r.writing_brief
  const hasBrief =
    Boolean(wb?.opening_strategy?.trim())
    || Boolean(wb?.conflict_structure?.trim())
    || Boolean(wb?.closing_hook?.trim())
    || Boolean(wb?.word_rhythm?.trim())
  const hasBody =
    r.risks.length > 0
    || r.reminders.length > 0
    || (r.must_events?.length ?? 0) > 0
    || (r.hallucination_traps?.length ?? 0) > 0
    || hasPfs
    || hasBrief
  if (hasBody) return false
  return true
}

/**
 * 将 API 返回的历史预警列表规范化为 PreWriteWarnHistoryRow[]。
 *
 * @param data - 来自 API 的原始列表（unknown）
 * @returns 过滤并规范化后的历史行数组
 */
export function parsePreWriteWarningHistoryPayload(data: unknown): PreWriteWarnHistoryRow[] {
  if (!Array.isArray(data)) return []
  return data
    .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
    .map((row) => ({
      id: String(row.id ?? ''),
      chapter_number: typeof row.chapter_number === 'number' ? row.chapter_number : 0,
      chapter_plan_summary: typeof row.chapter_plan_summary === 'string' ? row.chapter_plan_summary : '',
      model_profile: typeof row.model_profile === 'string' ? row.model_profile : 'local',
      created_at: row.created_at == null ? null : String(row.created_at),
      result: normalizePreWriteWarnResult(row.result),
    }))
    .filter((row) => row.id.length > 0)
}

// ─── 通用工具 ────────────────────────────────────────────────────────────────

/**
 * 简单 UUID 格式校验。用于判断字符串是否看起来像 UUID，避免误用名称字段当 ID。
 *
 * @param s - 待检测字符串
 * @returns 符合 UUID v1-v5 格式返回 true
 */
export function isUuidLike(s?: string): boolean {
  if (!s) return false
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
}

/**
 * 剥离 HTML 取末尾 N 字作为「上章结尾」预览。
 *
 * @param html - 章节 HTML 正文
 * @param maxChars - 最大保留字符数，默认 200
 * @returns 纯文本尾段，已去除结构化元信息行
 */
export function htmlTail(html: string, maxChars = 200): string {
  const div = document.createElement('div')
  div.innerHTML = html
  const raw = (div.innerText || div.textContent || '').trim()
  const text = stripTailMetaLines(raw).replace(/\s+/g, ' ').trim()
  return text.length <= maxChars ? text : '…' + text.slice(-maxChars)
}

/**
 * 过滤章末常见的结构化元信息，避免当成正文尾段展示/带入。
 *
 * @param text - 原始纯文本（来自 innerText）
 * @returns 去除元信息行后的文本
 */
export function stripTailMetaLines(text: string): string {
  if (!text) return ''
  const skipLine = (line: string): boolean => {
    const t = line.trim()
    if (!t) return false
    if (/^\*{0,2}\s*章末钩子强度/.test(t)) return true
    if (/^\*{0,2}\s*伏笔埋设/.test(t)) return true
    if (/^[-•]\s*F[-_ ]?\d{1,4}\s*[:：\-]/i.test(t)) return true
    if (/\bch[_-]?\d+\s*(?:回收|铺垫)\b/i.test(t)) return true
    return false
  }
  return text
    .split('\n')
    .filter((line) => !skipLine(line))
    .join('\n')
}

/**
 * 检测 HTML 字符串是否含有非空文本内容。
 *
 * @param html - HTML 字符串或 undefined
 * @returns 有可见文本内容返回 true
 */
export function hasHtmlTextContent(html?: string): boolean {
  if (!html) return false
  const div = document.createElement('div')
  div.innerHTML = html
  const text = (div.innerText || div.textContent || '').replace(/\s+/g, ' ').trim()
  return text.length > 0
}

/**
 * 是否全书第 1 章（按大纲/章标题）。
 * 用于 sort_order 前有未写正文的序章、占位章时，不误拦「第一章」的正文生成。
 *
 * @param ch - Chapter ORM 对象
 * @param outlineNode - 可选大纲节点（含更准确的章标题）
 * @returns 章标题符合「第1章/第一章」模式返回 true
 */
export function isBookFirstChapterTitle(ch: Chapter, outlineNode?: OutlineNode): boolean {
  const raw = (outlineNode?.title || ch.title || '').trim()
  if (!raw) return false
  if (/^第\s*0*1\s*章/.test(raw)) return true
  if (/^第一章/.test(raw)) return true
  return false
}
