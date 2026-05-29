/**
 * @file 从卷节点聚合章纲行 + 诊脉时间轴
 */
import type { LinterIssueRow } from '../../../components/Outline/VolumeLinterPanel'
import { linterIssueHeading } from '../../../components/Outline/linterDisplay'
import type { OutlineNode, OutlinePlanQualityReport } from '../../../types'
import type {
  InsightSeverity,
  InsightTimelineEntry,
  IntuitiveChapterRow,
  IntuitiveVolumeBundle,
  IntuitiveVolumeStats,
} from './intuitiveTypes'

const SEV_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

function sevRank(s: string): number {
  return SEV_ORDER[s] ?? 5
}

function mapQualitySeverity(s?: string): InsightSeverity {
  const v = (s || '').toLowerCase()
  if (v === 'critical' || v === 'fatal') return 'critical'
  if (v === 'high') return 'high'
  if (v === 'medium' || v === 'warn' || v === 'warning') return 'medium'
  if (v === 'low') return 'low'
  return 'info'
}

function buildTimeline(
  volume: OutlineNode,
  linterIssues: LinterIssueRow[],
  quality: OutlinePlanQualityReport | undefined,
): InsightTimelineEntry[] {
  const entries: InsightTimelineEntry[] = []

  linterIssues.forEach((issue, index) => {
    entries.push({
      id: `lint-${index}`,
      kind: 'linter',
      chapterNumber: issue.chapter_number_in_volume ?? null,
      severity: (issue.severity as InsightSeverity) || 'medium',
      title: linterIssueHeading(issue),
      message: issue.message,
      suggestion: issue.suggestion,
      ruleId: issue.rule_id,
      linterIndex: index,
    })
  })

  if (quality?.summary) {
    entries.push({
      id: 'quality-summary',
      kind: 'quality',
      chapterNumber: null,
      severity: mapQualitySeverity(quality.status),
      title: 'AI 叙事质检 · 总评',
      message: quality.summary,
    })
  }

  for (const issue of quality?.issues ?? []) {
    const ch = issue.chapter_numbers?.[0] ?? null
    entries.push({
      id: `quality-${entries.length}`,
      kind: 'quality',
      chapterNumber: ch,
      severity: mapQualitySeverity(issue.severity),
      title: issue.type ? `AI · ${issue.type}` : 'AI 叙事问题',
      message: issue.description || '—',
      suggestion: issue.suggested_patch?.replacement,
    })
  }

  for (const s of quality?.strengths ?? []) {
    entries.push({
      id: `strength-${entries.length}`,
      kind: 'strength',
      chapterNumber: null,
      severity: 'info',
      title: '亮点',
      message: s,
    })
  }

  const extra = volume.extra ?? {}
  if (extra.pacing_skeleton && typeof extra.pacing_skeleton === 'string') {
    entries.push({
      id: 'volume-pacing',
      kind: 'volume_meta',
      chapterNumber: null,
      severity: 'info',
      title: '卷节奏骨架',
      message: extra.pacing_skeleton as string,
    })
  }

  entries.sort((a, b) => {
    const ca = a.chapterNumber ?? 9999
    const cb = b.chapterNumber ?? 9999
    if (ca !== cb) return ca - cb
    return sevRank(a.severity) - sevRank(b.severity)
  })

  return entries
}

export function buildIntuitiveBundle(volume: OutlineNode): IntuitiveVolumeBundle {
  const children = [...(volume.children ?? [])].sort((a, b) => a.sort_order - b.sort_order)
  const linterIssues = (volume.extra?.linter_issues as LinterIssueRow[] | undefined) ?? []
  const summary = (volume.extra?.linter_summary as Record<string, number> | undefined) ?? {}
  const quality = volume.extra?.outline_quality as OutlinePlanQualityReport | undefined

  const byChapter = new Map<number, LinterIssueRow[]>()
  for (const issue of linterIssues) {
    const ch = issue.chapter_number_in_volume
    if (!ch) continue
    const list = byChapter.get(ch) ?? []
    list.push(issue)
    byChapter.set(ch, list)
  }

  const chapters: IntuitiveChapterRow[] = children.map((node, idx) => {
    const chapterNumber = idx + 1
    const issues = byChapter.get(chapterNumber) ?? []
    return {
      chapterNumber,
      node,
      issues,
      issueCount: issues.length,
      hasCritical: issues.some(i => i.severity === 'critical' || i.severity === 'high'),
    }
  })

  const stats: IntuitiveVolumeStats = {
    chapterCount: chapters.length,
    issueCount: summary.issue_count ?? linterIssues.length,
    criticalCount: summary.critical_count ?? linterIssues.filter(i => i.severity === 'critical').length,
    highCount: summary.high_count ?? linterIssues.filter(i => i.severity === 'high').length,
    linterStatus: (volume.extra?.linter_status as string) || 'unknown',
    draftBlocked: Boolean(volume.extra?.linter_blocked),
    qualityScore: quality?.overall_score != null ? Number(quality.overall_score) : null,
    qualityStatus: quality?.status ?? null,
  }

  return {
    volume,
    chapters,
    timeline: buildTimeline(volume, linterIssues, quality),
    stats,
    qualityReport: quality,
  }
}
