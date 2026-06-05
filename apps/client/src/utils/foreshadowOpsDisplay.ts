/**
 * 章纲伏笔 ops 展示：优先结构化 foreshadow_ops，回退 legacy 文本与列字段。
 */
import type { OutlineNode } from '../types'

export type ChapterForeshadowOp = {
  op: 'lay' | 'heat' | 'resolve'
  name?: string
  theme?: string
  code?: string
  note?: string
}

const VALID_OPS = new Set(['lay', 'heat', 'resolve'])

function normalizeOp(raw: unknown): ChapterForeshadowOp | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const op = String(r.op || '').toLowerCase()
  if (!VALID_OPS.has(op)) return null
  const out: ChapterForeshadowOp = { op: op as ChapterForeshadowOp['op'] }
  if (typeof r.name === 'string' && r.name.trim()) out.name = r.name.trim()
  if (typeof r.theme === 'string' && r.theme.trim()) out.theme = r.theme.trim()
  if (typeof r.code === 'string' && r.code.trim()) out.code = r.code.trim()
  const note = (r.note ?? r.detail) as unknown
  if (typeof note === 'string' && note.trim()) out.note = note.trim()
  if (op === 'lay' && !out.name) return null
  if (op !== 'lay' && !out.code && !out.note && !out.name) return null
  return out
}

/** 从章纲节点解析伏笔 ops（结构化优先）。 */
export function resolveChapterForeshadowOps(node: OutlineNode): ChapterForeshadowOp[] {
  const extra = node.extra ?? {}
  const rawOps = extra.foreshadow_ops
  if (Array.isArray(rawOps) && rawOps.length > 0) {
    return rawOps.map(normalizeOp).filter((o): o is ChapterForeshadowOp => o != null)
  }

  const fromCols: ChapterForeshadowOp[] = []
  for (const item of node.foreshadows_laid ?? []) {
    if (item?.description) {
      fromCols.push({ op: 'lay', name: item.description, code: item.id })
    }
  }
  for (const item of node.foreshadows_resolved ?? []) {
    const label = item?.description || item?.id || ''
    if (label) {
      fromCols.push({
        op: 'resolve',
        code: item.id,
        note: item.description,
      })
    }
  }
  if (fromCols.length > 0) return fromCols

  const legacy = typeof extra.foreshadow === 'string' ? extra.foreshadow.trim() : ''
  if (legacy) {
    return [{ op: 'lay', name: legacy, note: 'legacy' }]
  }
  return []
}

const OP_META: Record<ChapterForeshadowOp['op'], { label: string; className: string }> = {
  lay: { label: '埋', className: 'bg-emerald-50 text-emerald-800 border-emerald-100' },
  heat: { label: '加热', className: 'bg-orange-50 text-orange-800 border-orange-100' },
  resolve: { label: '收', className: 'bg-sky-50 text-sky-800 border-sky-100' },
}

/** 单条 op 的可读摘要（卡片展示用）。 */
export function formatForeshadowOpSummary(op: ChapterForeshadowOp): string {
  if (op.op === 'lay') {
    const theme = op.theme ? ` · ${op.theme}` : ''
    return `${op.name || '—'}${theme}`
  }
  const ref = op.code || op.name || ''
  const tail = op.note && op.note !== 'legacy' ? `：${op.note}` : ''
  return ref ? `${ref}${tail}` : (op.note || '—')
}

export function foreshadowOpChipMeta(op: ChapterForeshadowOp) {
  return OP_META[op.op]
}
