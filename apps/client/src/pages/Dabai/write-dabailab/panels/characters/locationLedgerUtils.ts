/**
 * @file dabai 人物位置台账：由面板快照 location + 复盘记忆合成逐章行踪。
 */
import type { DabaiLabMemory } from '../../../../../types/dabaiLab'
import type { DabaiPanelSnapshotItem } from '../../../../../types/dabaiLab'
import { charName, field, isProtagonist, type DabaiChar } from './charMeta'
import { dedupeLatestPanelSnapshots } from './realmLedgerUtils'

export interface DabaiLocationMilestone {
  chapter_number: number
  chapter_id?: string
  from_location?: string | null
  location_name: string
  map_name?: string | null
  place_name?: string | null
  reason?: string | null
  source?: 'panel_snapshot' | 'memory'
}

const MOVE_KW = /前往|赶往|踏入|进入|离开|走出|抵达|隐匿|跟踪|矿道|传送|阵|位移|潜入|躲入|藏身/
const OTHER_MOVE_RE = /(?:拥有|已是).*?(?:的|在)/

/** 解析「地图名·具体地点」；无分隔符时整段作为具体地点。 */
export function splitLocationLabel(location: string): { map: string; place: string } {
  const text = location.trim()
  if (!text) return { map: '', place: '' }
  const idx = text.indexOf('·')
  if (idx >= 0) {
    return { map: text.slice(0, idx).trim(), place: text.slice(idx + 1).trim() }
  }
  return { map: '', place: text }
}

export function formatLocationDisplay(location: string): string {
  const { map, place } = splitLocationLabel(location)
  if (map && place) return `${map} · ${place}`
  return place || map || location
}

/** 与后端 normalize_ledger_location 对齐：细地点补全区域前缀。 */
export function normalizeLedgerLocation(raw: string, prev = ''): string {
  const text = raw.trim()
  if (!text) return ''
  if (text.includes('·')) return text
  const region = prev.split('·')[0]?.trim()
  if (region && region.length >= 2 && !text.includes(region)) {
    return `${region}·${text}`
  }
  return text
}

function locationsEquivalent(a: string, b: string): boolean {
  const prev = a.trim()
  const curr = b.trim()
  if (!prev || !curr) return prev === curr
  if (prev === curr) return true
  const prevKey = prev.split('·')[0].slice(0, 6)
  const currKey = curr.split('·')[0].slice(0, 6)
  if (!prevKey || !currKey) return false
  if (prevKey === currKey) return true
  if (prev.includes(curr) || curr.includes(prev)) return true
  return false
}

function scoreLocationMemory(mem: DabaiLabMemory, protagonistName: string): number {
  const text = mem.content
  let score = 0
  if (mem.tags?.includes(protagonistName)) score += 10
  if (text.includes(protagonistName)) score += 5
  if (MOVE_KW.test(text)) score += 6
  if (mem.mem_type === 'event') score += 3
  if (mem.mem_type === 'fact' && MOVE_KW.test(text)) score += 2
  if (OTHER_MOVE_RE.test(text) && !text.includes(protagonistName)) score -= 8
  if (mem.mem_type === 'summary' && !MOVE_KW.test(text)) score -= 3
  return score
}

function findLocationReason(
  memories: DabaiLabMemory[],
  chapterNumber: number,
  protagonistName: string,
  snapshotReason?: string | null,
): string | null {
  const fromSnap = snapshotReason?.trim()
  if (fromSnap) return fromSnap

  const pool = memories
    .filter((m) => m.chapter_number === chapterNumber)
    .map((m) => ({ m, score: scoreLocationMemory(m, protagonistName) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
  return pool[0]?.m.content ?? null
}

function buildProtagonistLocationLedger(
  protagonistName: string,
  snapshots: DabaiPanelSnapshotItem[],
  memories: DabaiLabMemory[],
): DabaiLocationMilestone[] {
  const sorted = dedupeLatestPanelSnapshots(snapshots)
  const milestones: DabaiLocationMilestone[] = []
  let prev = ''

  for (const snap of sorted) {
    const snapJson = snap.snapshot ?? {}
    const rawLoc = String(snapJson.location ?? '').trim()
    if (!rawLoc) continue
    const loc = normalizeLedgerLocation(rawLoc, prev)
    if (locationsEquivalent(loc, prev) && milestones.length > 0) {
      prev = loc
      continue
    }
    const fromLoc = typeof snapJson.from_location === 'string'
      ? snapJson.from_location
      : (prev || null)
    const { map, place } = splitLocationLabel(loc)
    milestones.push({
      chapter_number: snap.chapter_number ?? 0,
      chapter_id: snap.chapter_id,
      from_location: fromLoc,
      location_name: loc,
      map_name: map || null,
      place_name: place || null,
      reason: findLocationReason(
        memories,
        snap.chapter_number ?? 0,
        protagonistName,
        typeof snapJson.location_change_reason === 'string' ? snapJson.location_change_reason : null,
      ),
      source: 'panel_snapshot',
    })
    prev = loc
  }
  return milestones
}

function buildSupportingLocationLedger(
  characterName: string,
  memories: DabaiLabMemory[],
): DabaiLocationMilestone[] {
  const relevant = memories.filter((m) => {
    if (!MOVE_KW.test(m.content)) return false
    return m.tags?.includes(characterName) || m.content.includes(characterName)
  })
  const byChapter = new Map<number, DabaiLabMemory>()
  for (const m of relevant) {
    if (!byChapter.has(m.chapter_number)) byChapter.set(m.chapter_number, m)
  }

  const milestones: DabaiLocationMilestone[] = []
  let prev = ''
  for (const ch of [...byChapter.keys()].sort((a, b) => a - b)) {
    const mem = byChapter.get(ch)!
    const hint = mem.content.slice(0, 60)
    milestones.push({
      chapter_number: ch,
      chapter_id: mem.chapter_id,
      from_location: prev || null,
      location_name: hint,
      reason: mem.content,
      source: 'memory',
    })
    prev = hint
  }
  return milestones
}

export function resolveCurrentLocation(
  snapshots: DabaiPanelSnapshotItem[],
): string {
  const sorted = dedupeLatestPanelSnapshots(snapshots)
  const last = sorted[sorted.length - 1]
  const loc = String(last?.snapshot?.location ?? '').trim()
  return loc ? formatLocationDisplay(loc) : ''
}

export function buildDabaiLocationLedger(
  character: DabaiChar,
  snapshots: DabaiPanelSnapshotItem[],
  memories: DabaiLabMemory[],
): DabaiLocationMilestone[] {
  if (isProtagonist(character)) {
    return buildProtagonistLocationLedger(charName(character), snapshots, memories)
  }
  return buildSupportingLocationLedger(charName(character), memories)
}
