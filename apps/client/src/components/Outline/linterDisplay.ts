/**
 * 章纲 linter 问题展示文案（中文、面向作者）。
 * 与后端 `outline_linter/user_facing.py` 的 RULE_LABELS 保持语义一致。
 */

import type { LinterIssueRow } from './VolumeLinterPanel'

/** 规则编号 → 中文简称 */
export const LINTER_RULE_LABELS: Record<string, string> = {
  'CH-01': '章纲·主角欲望过短',
  'CH-02': '章纲·障碍过短',
  'CH-03': '章纲·关键选择过短',
  'CH-04': '章纲·选择代价为空',
  'CH-05': '章纲·开篇钩子过短',
  'CH-06': '章纲·章末钩子过短',
  'CH-07': '章纲·章末钩子空泛',
  'CH-08': '章纲·核心事件为空',
  'CH-09': '章纲·反派行动无效',
  'CH-10': '章纲·无出场人物',
  'CH-11': '章纲·未挂故事线',
  'CH-12': '章纲·节奏标记非法',
  'CH-15': '章纲·字数预期偏离',
  'CH-18': '章纲·实力里程碑过泛',
  'SEQ-01': '章间衔接·代价未承接',
  'SEQ-02': '章间衔接·故事线独占',
  'SEQ-03': '章间衔接·至暗期过快',
  'SEQ-04': '章间衔接·至暗期情感不足',
  'SEQ-05': '章间衔接·梗概雷同',
  'SEQ-07': '章间衔接·分批断档',
  'VL-01': '卷纲·章数与配额不符',
  'VL-02': '卷纲·章节排序断裂',
  'VL-03': '卷纲·全卷无爽点章',
  'VL-04': '卷纲·打脸节奏',
  'VL-05': '卷纲·长线伏笔不足',
  'VL-06': '卷纲·无伏笔回收',
  'VL-07': '卷纲·故事线单一',
  'VL-09': '卷间衔接·开篇未接悬念',
  'VL-10': '卷间衔接·首章无后遗症',
  'RP-01': '读者承诺·超窗未兑现',
  'RP-02': '读者承诺·窗口未填兑现',
  'RP-03': '读者承诺·关键词不符',
  'OC-01': '开局·第1章钩子',
  'OC-02': '开局·前3章无爽点',
  'OC-03': '开局·第5章未埋长线',
  'OC-04': '开局·第10章钩子偏弱',
  'CM-01': '核心谜题·埋设章缺失',
  'CM-02': '核心谜题·加热章缺失',
  'CM-03': '核心谜题·揭晓过早',
  'CM-04': '核心谜题·揭晓章未收束',
  'CM-05': '核心谜题·缺身份之谜',
  'CM-06': '核心谜题·揭晓过密',
  'GEN-01': '生成·章数与要求不符',
}

export const LINTER_SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  high: '较高',
  medium: '中等',
  low: '轻微',
}

export function linterRuleLabel(ruleId: string): string {
  return LINTER_RULE_LABELS[ruleId] ?? ruleId
}

export function linterSeverityLabel(severity: string): string {
  return LINTER_SEVERITY_LABELS[severity] ?? severity
}

export function linterIssueHeading(issue: LinterIssueRow): string {
  return `${linterRuleLabel(issue.rule_id)} · ${linterSeverityLabel(issue.severity)}`
}
