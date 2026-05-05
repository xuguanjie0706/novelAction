/**
 * 将流式起草返回的纯文本拆成「正文」与「章节速查索引」Markdown，
 * 并把 Markdown 解析为 chapter-debrief 可用的 chapter_index 载荷。
 */

export type ChapterIndexDebriefPayload = {
  story_day?: string
  core_events?: Array<Record<string, unknown> | string>
  first_appearances?: Array<Record<string, unknown>>
  actual_foreshadows_laid?: Array<Record<string, unknown>>
  actual_foreshadows_resolved?: Array<Record<string, unknown>>
  ending_hook?: string
  hook_strength?: number
  continuity_notes?: Array<Record<string, unknown> | string>
}

/** 正文（无索引尾） + 可选的索引 Markdown（从 ### ch_ 或 【章节速查索引】起） */
export function splitStreamedDraftText(full: string): { body: string; indexMarkdown: string | null } {
  const t = full.replace(/\r\n/g, '\n')
  let split = -1

  const nlHeader = t.search(/\n#{1,6}\s*ch_\d+/i)
  if (nlHeader >= 0) split = nlHeader + 1
  else if (/^#{1,6}\s*ch_\d+/im.test(t.trimStart())) {
    const lead = t.match(/^\s*/)![0].length
    split = lead
  }

  const altNl = t.search(/\n【章节速查索引】/)
  if (altNl >= 0 && (split < 0 || altNl + 1 < split)) split = altNl + 1
  if (t.trimStart().startsWith('【章节速查索引】')) {
    const lead = t.match(/^\s*/)![0].length
    if (split < 0 || lead < split) split = lead
  }

  if (split < 0) return { body: t.trim(), indexMarkdown: null }

  const body = t.slice(0, split).trimEnd().trim()
  const indexMarkdown = t.slice(split).trim()
  if (!indexMarkdown) return { body: t.trim(), indexMarkdown: null }
  return { body, indexMarkdown }
}

const SECTION_RE = /^\s*\*\*([^*]+)\*\*\s*[:：]?\s*(.*)$/
/** 与 SECTION_RE 并列：模型常用 ### 小节标题，仅 **…** 时伏笔回收整段会掉进 other，导致不同步伏笔表 */
const MD_HEADING_RE = /^\s{0,3}#{1,6}\s+(.+?)\s*$/

function countHookStars(s: string): number {
  const m = s.match(/[⭐★]/g)
  if (!m?.length) return 3
  return Math.min(5, Math.max(1, m.length))
}

function hookDescriptionFromLine(line: string): string {
  const inner = /\s*[（(]([^）)]+)[）)]\s*$/.exec(line)
  if (inner) return inner[1].trim()
  return line
    .replace(/[⭐★\s]+/g, ' ')
    .replace(/^章末钩子强度[：:]\s*/i, '')
    .trim()
}

function numberedListItems(lines: string[]): string[] {
  const out: string[] = []
  for (const raw of lines) {
    const m = /^\s*\d+[\.．、]\s*(.+)$/.exec(raw)
    if (m) out.push(m[1].trim())
    else if (raw.trim() && out.length === 0 && !SECTION_RE.test(raw)) out.push(raw.trim())
    else if (raw.trim() && out.length > 0 && !SECTION_RE.test(raw)) {
      out[out.length - 1] = `${out[out.length - 1]} ${raw.trim()}`
    }
  }
  return out.filter(Boolean)
}

/** 去掉行首 Markdown/中文列表前缀，避免「- F-013」按 F 切分时留下单独的 "-" 行 */
function stripForeshadowLinePrefix(s: string): string {
  return s
    .replace(/^\d+[\.．、]\s+/, '')
    .replace(/^[-*•]\s*/, '')
    .trim()
}

function splitForeshadowPieces(s: string): string[] {
  const t = s.trim()
  if (!t || /^无[。]?$/i.test(t)) return []
  const parts = t
    .split(/(?=F[-_ ]?\d+)/i)
    .map((x) => stripForeshadowLinePrefix(x))
    .filter(Boolean)
  if (parts.length) return parts
  const single = stripForeshadowLinePrefix(t)
  return single ? [single] : []
}

/**
 * 模型常把「伏笔回收」写在 **资产变动记录** 下的列表项里，例如：
 * `* **伏笔回收**：F-016（……）。`
 * 整行不会触发独立小节，需从行内抠出 F-xxx 供伏笔表同步。
 */
const INLINE_FS_RESOLVE_BOLD_RE =
  /\*\*(?:伏笔回收|回收伏笔)\*\*\s*[:：]\s*(.+)$/
const INLINE_FS_RESOLVE_PLAIN_RE = /(?:^|[\s*•-])(?:伏笔回收|回收伏笔)\s*[:：]\s*(.+)$/

function extractInlineForeshadowResolveFromLine(line: string): string[] {
  const t = line.trim()
  if (!t) return []
  const bold = INLINE_FS_RESOLVE_BOLD_RE.exec(t)
  if (bold) {
    const chunk = bold[1].trim()
    return splitForeshadowPieces(chunk)
  }
  if (!/\*\*/.test(t)) {
    const plain = INLINE_FS_RESOLVE_PLAIN_RE.exec(t)
    if (plain) {
      const chunk = plain[1].trim()
      return splitForeshadowPieces(chunk)
    }
  }
  return []
}

/**
 * 将模型输出的索引 Markdown 解析为 chapter_index；失败时返回 null（调用方可降级为 continuity_notes）。
 */
export function parseChapterIndexMarkdown(md: string): ChapterIndexDebriefPayload | null {
  const text = md.replace(/\r\n/g, '\n').trim()
  if (!text) return null

  const lines = text.split('\n')
  let i = 0
  while (i < lines.length && /^\s*#{1,6}\s*ch_/i.test(lines[i].trim())) {
    i += 1
  }
  while (i < lines.length && !SECTION_RE.test(lines[i])) {
    if (lines[i].trim().startsWith('---')) {
      i += 1
      continue
    }
    if (!lines[i].trim()) {
      i += 1
      continue
    }
    break
  }

  type Key =
    | 'core_events'
    | 'first_appearances'
    | 'ending_hook'
    | 'foreshadows_laid'
    | 'foreshadows_resolved'
    | 'continuity'
    | 'other'

  let current: Key = 'other'
  const buffers: Record<Key, string[]> = {
    core_events: [],
    first_appearances: [],
    ending_hook: [],
    foreshadows_laid: [],
    foreshadows_resolved: [],
    continuity: [],
    other: [],
  }

  const mapLabel = (label: string): Key => {
    const s = label.replace(/\*+/g, '').trim()
    if (s.includes('核心事件')) return 'core_events'
    if (s.includes('首次出场') || s.includes('首次登场')) return 'first_appearances'
    if (s.includes('章末钩子')) return 'ending_hook'
    if (s.includes('伏笔埋设') || s.includes('埋设伏笔')) return 'foreshadows_laid'
    if (s.includes('伏笔回收') || s.includes('回收伏笔') || /^已回收/.test(s)) {
      return 'foreshadows_resolved'
    }
    if (s.includes('连续性')) return 'continuity'
    return 'other'
  }

  for (; i < lines.length; i++) {
    const line = lines[i]
    const sec = SECTION_RE.exec(line)
    if (sec) {
      current = mapLabel(sec[1])
      const rest = sec[2].trim()
      if (rest) buffers[current].push(rest)
      continue
    }
    const mdHead = MD_HEADING_RE.exec(line)
    if (mdHead) {
      current = mapLabel(mdHead[1])
      continue
    }
    if (!line.trim()) continue
    buffers[current].push(line)
  }

  // 从「资产变动」等 other 区的列表行里抽出 **伏笔回收**：… → 全局伏笔同步
  for (const ol of buffers.other) {
    for (const piece of extractInlineForeshadowResolveFromLine(ol)) {
      buffers.foreshadows_resolved.push(piece)
    }
  }

  const coreLines = buffers.core_events
  const coreEvents = numberedListItems(coreLines)

  let firstText = buffers.first_appearances.join(' ').trim()
  let firstAppearances: Array<Record<string, unknown>> = []
  if (firstText && !/^无[。]?$/i.test(firstText)) {
    firstAppearances = firstText.split(/[；;]/).map((s) => s.trim()).filter(Boolean).map((s) => ({ description: s }))
  }

  const hookLine = buffers.ending_hook.join(' ').trim()
  let ending_hook: string | undefined
  let hook_strength = 3
  if (hookLine) {
    hook_strength = countHookStars(hookLine)
    const desc = hookDescriptionFromLine(hookLine)
    ending_hook = desc || undefined
  }

  const laid: Array<Record<string, unknown>> = []
  for (const piece of buffers.foreshadows_laid.flatMap((l) => splitForeshadowPieces(l))) {
    laid.push({ description: piece })
  }
  const resolved: Array<Record<string, unknown>> = []
  for (const piece of buffers.foreshadows_resolved.flatMap((l) => splitForeshadowPieces(l))) {
    resolved.push({ description: piece })
  }

  const continuity_notes = buffers.continuity
    .map((l) => l.trim())
    .filter(Boolean) as Array<string>

  const hasPayload =
    coreEvents.length > 0
    || firstAppearances.length > 0
    || Boolean(ending_hook)
    || laid.length > 0
    || resolved.length > 0
    || continuity_notes.length > 0

  if (!hasPayload) return null

  return {
    core_events: coreEvents,
    first_appearances: firstAppearances,
    actual_foreshadows_laid: laid,
    actual_foreshadows_resolved: resolved,
    ending_hook,
    hook_strength,
    continuity_notes: continuity_notes.length ? continuity_notes : undefined,
  }
}

export function fallbackChapterIndexFromRawMarkdown(indexMarkdown: string): ChapterIndexDebriefPayload {
  return {
    hook_strength: 3,
    continuity_notes: [indexMarkdown.trim()],
  }
}

/** 从 TipTap HTML 得到可供「稿末索引」切分的纯文本 */
export function htmlToPlainForSplit(html: string): string {
  if (!html?.trim()) return ''
  let t = html
    .replace(/<\/p\s*>/gi, '\n\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/div\s*>/gi, '\n')
    .replace(/<\/h[1-6]\s*>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/\u00a0/g, ' ')
  return t.replace(/\n{3,}/g, '\n\n').trim()
}

function escapeHtmlBlock(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 与起草队列一致的段落 HTML，用于「正文」只读预览 */
export function plainTextBlocksToHtml(plain: string): string {
  const blocks = plain.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean)
  if (blocks.length === 0) {
    return '<p class="text-novel-ink-faint text-sm">（在「### ch_…」或「【章节速查索引】」之前没有检测到叙事段落）</p>'
  }
  return blocks.map((b) => `<p>${escapeHtmlBlock(b).replace(/\n/g, '<br>')}</p>`).join('')
}
