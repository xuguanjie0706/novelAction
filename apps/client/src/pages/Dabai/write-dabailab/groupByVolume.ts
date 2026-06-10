import type { DabaiChapter, DabaiVolume } from '../../../types/dabai'

export interface VolumeGroup {
  volume: DabaiVolume
  chapters: DabaiChapter[]
}

export function groupByVolume(volumes: DabaiVolume[], chapters: DabaiChapter[]): VolumeGroup[] {
  const vols = [...volumes].sort((a, b) => a.volume_number - b.volume_number)
  const chs = [...chapters].sort((a, b) => a.chapter_number - b.chapter_number)
  let start = 1
  return vols.map(vol => {
    const end = start + Math.max(vol.planned_chapters, 1) - 1
    const slice = chs.filter(c => c.chapter_number >= start && c.chapter_number <= end)
    start = end + 1
    return { volume: vol, chapters: slice }
  })
}
