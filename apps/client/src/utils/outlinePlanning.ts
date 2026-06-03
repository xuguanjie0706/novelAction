/** 与后端 outline_planning.words_to_plan 对齐，用于前端判断卷数是否不足。 */
const MIN_CHAPTERS_PER_VOLUME = 30
const TARGET_CHAPTERS_PER_VOLUME = 60
const TARGET_WORDS_PER_CHAPTER = 2300

export function wordsToPlan(targetWords: number): {
  total_chapters: number
  total_volumes: number
  chapters_last: number
  scale_label: string
} {
  const tw = Math.max(
    Number(targetWords) || 1_200_000,
    MIN_CHAPTERS_PER_VOLUME * TARGET_WORDS_PER_CHAPTER,
  )
  const total_chapters = Math.round(tw / TARGET_WORDS_PER_CHAPTER)
  const full_volumes = Math.floor(total_chapters / TARGET_CHAPTERS_PER_VOLUME)
  const remainder = total_chapters % TARGET_CHAPTERS_PER_VOLUME

  let total_volumes: number
  let chapters_last: number
  if (remainder === 0) {
    total_volumes = full_volumes
    chapters_last = TARGET_CHAPTERS_PER_VOLUME
  } else if (remainder < MIN_CHAPTERS_PER_VOLUME) {
    total_volumes = Math.max(1, full_volumes)
    chapters_last = TARGET_CHAPTERS_PER_VOLUME + remainder
  } else {
    total_volumes = full_volumes + 1
    chapters_last = remainder
  }

  let scale_label = 'epic'
  if (tw <= 500_000) scale_label = 'micro'
  else if (tw <= 900_000) scale_label = 'short'
  else if (tw <= 1_400_000) scale_label = 'medium'
  else if (tw <= 1_700_000) scale_label = 'long'

  return { total_chapters, total_volumes, chapters_last, scale_label }
}
