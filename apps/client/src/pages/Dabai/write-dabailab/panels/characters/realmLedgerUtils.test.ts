import { describe, expect, it } from 'vitest'
import {
  buildDabaiRealmLedger,
  dedupeLatestPanelSnapshots,
  formatPanelRealmLabel,
} from './realmLedgerUtils'
import type { DabaiLabMemory } from '../../../../../types/dabaiLab'

describe('formatPanelRealmLabel', () => {
  it('backfills sub_level from previous chapter when snapshot omits it', () => {
    expect(formatPanelRealmLabel({ realm: '练气期', sub_level: null }, '练气期·第3层')).toBe('练气期·第3层')
  })
})

describe('dedupeLatestPanelSnapshots', () => {
  it('keeps only the newest snapshot per chapter', () => {
    const items = dedupeLatestPanelSnapshots([
      { id: 'a', chapter_id: '1', chapter_number: 9, realm: '练气期', sub_level: 2, created_at: '2026-01-01' },
      { id: 'b', chapter_id: '1', chapter_number: 9, realm: '练气期', sub_level: 3, created_at: '2026-01-02' },
    ])
    expect(items).toHaveLength(1)
    expect(items[0].sub_level).toBe(3)
  })
})

describe('buildDabaiRealmLedger', () => {
  it('skips false realm downgrade when major realm unchanged and sub_level missing', () => {
    const protagonist = { name: '李夜', role: '主角', start_realm: '练气期·第1层' }
    const memories: DabaiLabMemory[] = [
      {
        id: '1', chapter_id: 'c11', chapter_number: 11, mem_type: 'event',
        content: '拥有练气八层修为的内门弟子柳如烟突然现身', importance: 4, tags: ['柳如烟'],
      },
      {
        id: '2', chapter_id: 'c11', chapter_number: 11, mem_type: 'event',
        content: '李夜施展大圆满境阴风步隐匿身形', importance: 3, tags: ['李夜'],
      },
    ]
    const milestones = buildDabaiRealmLedger(
      protagonist,
      {},
      [
        {
          id: 's10', chapter_id: 'c10', chapter_number: 10,
          realm: '练气期', sub_level: 3, created_at: '2026-01-01',
        },
        {
          id: 's11', chapter_id: 'c11', chapter_number: 11,
          realm: '练气期', sub_level: null, combat_power: 150, created_at: '2026-01-02',
        },
      ],
      memories,
    )
    expect(milestones.some((m) => m.chapter_number === 11)).toBe(false)
    const last = milestones[milestones.length - 1]
    expect(last?.realm_name).toBe('练气期·第3层')
  })
})
