import type { DabaiProjectDetail } from '../../../types/dabai'

export function makeRealmLabel(detail: DabaiProjectDetail) {
  const levels = detail.power_ladder?.levels ?? []
  return (rank?: number | null) => {
    if (!rank) return ''
    const lv = levels.find(l => l.rank === rank)
    return lv?.name ?? `第${rank}档`
  }
}
