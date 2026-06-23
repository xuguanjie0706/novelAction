/**
 * @file dabai 人物境界台账：由面板快照 + 复盘记忆合成逐章境界轨迹。
 */
import type { DabaiLabMemory } from '../../../../../types/dabaiLab'
import type { DabaiPanelSnapshotItem } from '../../../../../types/dabaiLab'
import { charName, field, isProtagonist, type DabaiChar } from './charMeta'

export interface DabaiRealmMilestone {
  chapter_number: number
  chapter_id?: string
  from_realm?: string | null
  realm_name: string
  combat_power?: number | null
  reason?: string | null
  source?: 'panel_snapshot' | 'memory' | 'meta'
}

const REALM_KW = /境|期|突破|修为|层|破境|冲关|渡劫|晋级|升境|重/
const CHANGE_KW = /突破|破境|冲关|升至|提升到|迈入|跨入|暴涨|灌顶|层/
const OTHER_REALM_RE = /(?:拥有|已是|达到|修为达)(?:练气|筑基|金丹|元婴|化神)[一二三四五六七八九十\d]+层.*?的/

/** 同章只保留最新一条面板快照（重跑复盘会产生多条）。 */
export function dedupeLatestPanelSnapshots(
  snapshots: DabaiPanelSnapshotItem[],
): DabaiPanelSnapshotItem[] {
  const byChapter = new Map<number, DabaiPanelSnapshotItem>()
  for (const snap of snapshots) {
    const ch = snap.chapter_number ?? 0
    if (ch <= 0) continue
    const prev = byChapter.get(ch)
    if (!prev) {
      byChapter.set(ch, snap)
      continue
    }
    const prevAt = prev.created_at ?? ''
    const curAt = snap.created_at ?? ''
    if (curAt >= prevAt) byChapter.set(ch, snap)
  }
  return [...byChapter.values()].sort((a, b) => (a.chapter_number ?? 0) - (b.chapter_number ?? 0))
}

function majorStem(label: string): string {
  return label.split('·')[0].replace(/第\d+层$/, '').trim()
}

function subFromLabel(label: string): number | null {
  const m = label.match(/第(\d+)层/)
  return m ? Number(m[1]) : null
}

/** 面板快照 → 展示用境界标签（合并 realm + sub_level，避免裸大境）。 */
export function formatPanelRealmLabel(
  item: {
    realm?: unknown
    sub_level?: number | null
    snapshot?: Record<string, unknown>
  },
  prevLabel = '',
): string {
  const snap = (item.snapshot ?? item) as Record<string, unknown>
  let realm = String(snap.realm ?? item.realm ?? '').trim()
  const sub = snap.sub_level ?? item.sub_level
  if (realm.includes('第') && /层|重/.test(realm)) return realm
  if (sub != null && Number(sub) > 0) return `${realm}·第${sub}层`
  const prevSub = subFromLabel(prevLabel)
  if (prevSub && prevLabel && majorStem(prevLabel) === majorStem(realm)) {
    return `${realm}·第${prevSub}层`
  }
  return realm
}

function realmLabelsEqual(a: string, b: string): boolean {
  const na = a.trim()
  const nb = b.trim()
  if (!na || !nb) return na === nb
  if (na === nb) return true
  return majorStem(na) === majorStem(nb) && (subFromLabel(na) ?? subFromLabel(nb)) === subFromLabel(nb)
}

function scoreProtagonistRealmMemory(
  mem: DabaiLabMemory,
  protagonistName: string,
): number {
  const text = mem.content
  let score = 0
  if (mem.tags?.includes(protagonistName)) score += 12
  if (text.includes(protagonistName)) score += 6
  if (mem.mem_type === 'state') score += 5
  if (CHANGE_KW.test(text) && text.includes(protagonistName)) score += 8
  if (REALM_KW.test(text)) score += 2
  if (OTHER_REALM_RE.test(text) && !text.includes(protagonistName)) score -= 15
  if (/内门弟子|女主|反派|对手|敌人/.test(text) && !text.includes(protagonistName)) score -= 6
  if (mem.mem_type === 'summary' && !CHANGE_KW.test(text)) score -= 4
  return score
}

function findProtagonistRealmReason(
  memories: DabaiLabMemory[],
  chapterNumber: number,
  protagonistName: string,
  snapshotReason?: string | null,
): string | null {
  const fromSnap = snapshotReason?.trim()
  if (fromSnap) return fromSnap

  const pool = memories
    .filter((m) => m.chapter_number === chapterNumber)
    .map((m) => ({ m, score: scoreProtagonistRealmMemory(m, protagonistName) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)

  const best = pool[0]?.m
  if (!best) return null
  if (best.mem_type === 'summary' && !CHANGE_KW.test(best.content) && !best.content.includes(protagonistName)) {
    return '本章复盘未提取到主角境界变化依据（摘要为剧情事件，非修为因果）。'
  }
  return best.content
}

function buildProtagonistLedger(
  protagonistName: string,
  startRealm: string,
  snapshots: DabaiPanelSnapshotItem[],
  memories: DabaiLabMemory[],
  meta?: Record<string, unknown> | null,
): DabaiRealmMilestone[] {
  const sorted = dedupeLatestPanelSnapshots(snapshots)
  const milestones: DabaiRealmMilestone[] = []
  let prev = startRealm.trim()

  for (const snap of sorted) {
    const snapJson = snap.snapshot ?? {}
    const label = formatPanelRealmLabel(snap, prev)
    if (!label) continue
    if (realmLabelsEqual(label, prev) && milestones.length > 0) {
      prev = label
      continue
    }
    const fromRealm = typeof snapJson.from_realm === 'string'
      ? snapJson.from_realm
      : (prev || null)
    milestones.push({
      chapter_number: snap.chapter_number ?? 0,
      chapter_id: snap.chapter_id,
      from_realm: fromRealm,
      realm_name: label,
      combat_power: snap.combat_power ?? (snapJson.combat_power as number | null) ?? null,
      reason: findProtagonistRealmReason(
        memories,
        snap.chapter_number ?? 0,
        protagonistName,
        typeof snapJson.realm_change_reason === 'string' ? snapJson.realm_change_reason : null,
      ),
      source: 'panel_snapshot',
    })
    prev = label
  }

  if (milestones.length === 0 && meta) {
    const cur = String(meta.protagonist_realm ?? '').trim()
    const ch = Number(meta.protagonist_realm_chapter)
    if (cur && !realmLabelsEqual(cur, startRealm) && Number.isFinite(ch) && ch > 0) {
      milestones.push({
        chapter_number: ch,
        from_realm: startRealm || null,
        realm_name: formatPanelRealmLabel({ realm: cur }, startRealm),
        reason: findProtagonistRealmReason(memories, ch, protagonistName, null),
        source: 'meta',
      })
    }
  }

  return milestones
}

function buildSupportingLedger(
  characterName: string,
  startRealm: string,
  memories: DabaiLabMemory[],
): DabaiRealmMilestone[] {
  const relevant = memories.filter((m) => {
    if (!REALM_KW.test(m.content)) return false
    return m.tags?.includes(characterName) || m.content.includes(characterName)
  })
  const byChapter = new Map<number, DabaiLabMemory>()
  for (const m of relevant) {
    const prev = byChapter.get(m.chapter_number)
    if (!prev || m.mem_type === 'state') byChapter.set(m.chapter_number, m)
  }

  const milestones: DabaiRealmMilestone[] = []
  let prev = startRealm.trim()
  for (const ch of [...byChapter.keys()].sort((a, b) => a - b)) {
    const mem = byChapter.get(ch)!
    const hint = mem.content.match(/[\u4e00-\u9fff]{1,12}(?:境|期)(?:[·．][第]?\d+[层重])?/)?.[0]
      ?? mem.content.slice(0, 48)
    milestones.push({
      chapter_number: ch,
      chapter_id: mem.chapter_id,
      from_realm: prev || null,
      realm_name: hint,
      reason: mem.content,
      source: 'memory',
    })
    prev = hint
  }
  return milestones
}

/** 为选中人物合成境界台账（主角优先读面板快照，配角读记忆标签）。 */
export function buildDabaiRealmLedger(
  character: DabaiChar,
  meta: Record<string, unknown> | undefined,
  snapshots: DabaiPanelSnapshotItem[],
  memories: DabaiLabMemory[],
): DabaiRealmMilestone[] {
  const startRealm = field(character, 'start_realm')
  if (isProtagonist(character)) {
    return buildProtagonistLedger(charName(character), startRealm, snapshots, memories, meta)
  }
  return buildSupportingLedger(charName(character), startRealm, memories)
}
