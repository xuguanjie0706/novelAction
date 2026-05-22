import type { QualityReport } from '../types'

/** 从质检报告提取可展示的优化建议文案 */
export function normalizeQualitySuggestions(raw: QualityReport['suggestions']): string[] {
  const lines: string[] = []
  for (const item of raw || []) {
    if (typeof item === 'string' && item.trim()) {
      lines.push(item.trim())
      continue
    }
    if (item && typeof item === 'object') {
      const obj = item as { comment?: string; description?: string; suggestion?: string }
      const text = obj.comment || obj.description || obj.suggestion || ''
      if (text.trim()) lines.push(text.trim())
    }
  }
  return lines
}

/** 从质检报告 issues 提取描述 */
export function normalizeQualityIssues(raw: QualityReport['issues']): string[] {
  const lines: string[] = []
  for (const item of raw || []) {
    const desc = item.description?.trim()
    if (desc) lines.push(desc)
  }
  return lines
}

export function qualityReportHasFixableHints(report: QualityReport | null): boolean {
  if (!report) return false
  const suggestions = normalizeQualitySuggestions(report.suggestions)
  const issues = normalizeQualityIssues(report.issues)
  if (suggestions.length > 0 || issues.length > 0) return true
  return Object.values(report.dimensions || {}).some((dim) => {
    if (!dim) return false
    if (dim.status === 'warning' || dim.status === 'fail') return true
    return dim.score < 7
  })
}
