/**
 * @file 章节正文行级 diff（对照弹窗用，与创作端 UI 解耦）
 */

export type AlignedDiffRow = {
  left: string
  right: string
  leftChanged: boolean
  rightChanged: boolean
}

function chunkToDisplayLines(value: string): string[] {
  const s = value.replace(/\r\n/g, '\n')
  if (!s) return []
  const hasFinalNl = s.endsWith('\n')
  const core = hasFinalNl ? s.slice(0, -1) : s
  if (core === '') return hasFinalNl ? [''] : []
  return core.split('\n')
}

/** 行级对齐：左右同高、变更行分别高亮 */
export function alignChapterLines(before: string, after: string): AlignedDiffRow[] {
  const parts = diffLinesNormalized(before, after)
  const rows: AlignedDiffRow[] = []

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]
    if (!part.added && !part.removed) {
      for (const line of chunkToDisplayLines(part.value)) {
        rows.push({ left: line, right: line, leftChanged: false, rightChanged: false })
      }
    } else if (part.removed) {
      const next = parts[i + 1]
      if (next?.added) {
        const lLines = chunkToDisplayLines(part.value)
        const rLines = chunkToDisplayLines(next.value)
        const n = Math.max(lLines.length, rLines.length)
        for (let j = 0; j < n; j++) {
          rows.push({
            left: lLines[j] ?? '',
            right: rLines[j] ?? '',
            leftChanged: j < lLines.length,
            rightChanged: j < rLines.length,
          })
        }
        i++
      } else {
        for (const line of chunkToDisplayLines(part.value)) {
          rows.push({ left: line, right: '', leftChanged: true, rightChanged: false })
        }
      }
    } else if (part.added) {
      for (const line of chunkToDisplayLines(part.value)) {
        rows.push({ left: '', right: line, leftChanged: false, rightChanged: true })
      }
    }
  }

  return rows
}

type DiffPart = { value: string; added?: boolean; removed?: boolean }

/** 轻量行 diff（避免额外依赖 diff 包） */
function diffLinesNormalized(before: string, after: string): DiffPart[] {
  const a = before.replace(/\r\n/g, '\n').split('\n')
  const b = after.replace(/\r\n/g, '\n').split('\n')
  const n = a.length
  const m = b.length
  const lcs: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const parts: DiffPart[] = []
  let i = 0
  let j = 0
  const push = (value: string, added?: boolean, removed?: boolean) => {
    if (!value && !added && !removed) return
    const last = parts[parts.length - 1]
    if (last && !!last.added === !!added && !!last.removed === !!removed) {
      last.value += value
      return
    }
    parts.push({ value, added, removed })
  }
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(`${a[i]}\n`)
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      push(`${a[i]}\n`, false, true)
      i++
    } else {
      push(`${b[j]}\n`, true, false)
      j++
    }
  }
  while (i < n) {
    push(`${a[i]}\n`, false, true)
    i++
  }
  while (j < m) {
    push(`${b[j]}\n`, true, false)
    j++
  }
  return parts
}
