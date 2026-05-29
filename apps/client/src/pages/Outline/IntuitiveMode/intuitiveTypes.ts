/**
 * @file 直观模式（编剧台）共享类型
 */
import type { LinterIssueRow } from '../../../components/Outline/VolumeLinterPanel'
import type { OutlineNode, OutlinePlanQualityReport } from '../../../types'

export type InsightKind = 'linter' | 'quality' | 'strength' | 'volume_meta'

export type InsightSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info'

/** 右侧诊脉轨单条记录（规则 linter + AI 质检 + 卷级摘要） */
export interface InsightTimelineEntry {
  id: string
  kind: InsightKind
  chapterNumber: number | null
  severity: InsightSeverity
  title: string
  message: string
  suggestion?: string
  ruleId?: string
  /** 对应 volume.extra.linter_issues 下标，供修复勾选 */
  linterIndex?: number
}

export interface IntuitiveChapterRow {
  chapterNumber: number
  node: OutlineNode
  issues: LinterIssueRow[]
  issueCount: number
  hasCritical: boolean
}

export interface IntuitiveVolumeStats {
  chapterCount: number
  issueCount: number
  criticalCount: number
  highCount: number
  linterStatus: string
  draftBlocked: boolean
  qualityScore: number | null
  qualityStatus: string | null
}

export interface IntuitiveVolumeBundle {
  volume: OutlineNode
  chapters: IntuitiveChapterRow[]
  timeline: InsightTimelineEntry[]
  stats: IntuitiveVolumeStats
  qualityReport: OutlinePlanQualityReport | undefined
}
