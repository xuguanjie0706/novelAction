/**
 * 跨卷全书章号：卷纲节拍存本卷内章号，展示时叠加 chapter_start_global。
 */
import type { OutlineNode } from '../types'

export function normalizePlannedChapters(raw: unknown, defaultVal = 30): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 15) return defaultVal
  return Math.min(Math.floor(n), 80)
}

/** 卷 id → 该卷第 1 章的全书章号（与后端 compute_chapter_starts 一致）。 */
export function computeVolumeChapterStarts(volumes: OutlineNode[]): Map<string, number> {
  const vols = volumes
    .filter(v => v.node_type === 'volume')
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
  const map = new Map<string, number>()
  let cursor = 1
  for (const v of vols) {
    map.set(v.id, cursor)
    const planned = normalizePlannedChapters((v.extra ?? {}).planned_chapters)
    cursor += planned
  }
  return map
}

export function chapterStartForVolume(
  vol: OutlineNode,
  allVolumes?: OutlineNode[],
): number {
  const stored = (vol.extra ?? {}).chapter_start_global
  if (typeof stored === 'number' && stored > 0) return stored
  if (allVolumes?.length) {
    return computeVolumeChapterStarts(allVolumes).get(vol.id) ?? 1
  }
  return 1
}

/** 展示用章号（首卷简写，后续卷双标）。 */
export function formatVolumeChapterLabel(localCh: number, startGlobal: number): string {
  if (!Number.isFinite(localCh) || localCh < 1) return '第 ? 章'
  if (startGlobal <= 1) return `第 ${localCh} 章`
  const globalCh = startGlobal + localCh - 1
  return `全书第 ${globalCh} 章（本卷第 ${localCh} 章）`
}

/** 节奏骨架文案：本卷内章号 → 全书章号（仅展示）。 */
export function shiftPacingSkeletonDisplay(text: string, startGlobal: number): string {
  if (startGlobal <= 1 || !text.trim()) return text
  const off = startGlobal - 1
  return text.replace(/(\d+)(?:-(\d+))?章/g, (_, a: string, b?: string) => {
    const g1 = parseInt(a, 10) + off
    if (b != null && b !== '') return `${g1}-${parseInt(b, 10) + off}章`
    return `${g1}章`
  })
}
