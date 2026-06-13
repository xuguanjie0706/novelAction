/**
 * 从 lab 质检报告提炼「写作指令」，供按要素重写弹窗预填。
 */
import type { DabaiLabQualityReport } from '../types/dabaiLab'

const REWRITE_SCORE_THRESHOLD = 80

/** 是否展示「填入重写」快捷入口。 */
export function canApplyQualityRewrite(report: DabaiLabQualityReport | null | undefined): boolean {
  if (!report) return false
  const score = report.overall_score ?? 100
  const llm = report.llm
  if (score < REWRITE_SCORE_THRESHOLD && (report.rewrite_prompt?.trim() || llm)) return true
  return Boolean(
    llm?.chapter_suggestions?.length
    || llm?.future_chapter_suggestions?.length
    || llm?.suggestions?.length
    || report.rewrite_prompt?.trim(),
  )
}

/** 将质检报告格式化为重写弹窗的「写作指令」文本。 */
export function formatQualityRewriteInstruction(report: DabaiLabQualityReport): string {
  const score = report.overall_score ?? 0
  const llm = report.llm
  const topRewrite = report.rewrite_prompt?.trim()
  if (score < REWRITE_SCORE_THRESHOLD && topRewrite) return topRewrite

  const lines: string[] = []
  if (score < REWRITE_SCORE_THRESHOLD) {
    lines.push(`【质检 ${score} 分 · 请按下列要点重写本章】`)
  } else {
    lines.push('【按质检建议微调本章】')
  }

  const chapterTips = llm?.chapter_suggestions?.length
    ? llm.chapter_suggestions
    : (llm?.suggestions ?? [])
  if (chapterTips.length) {
    lines.push('', '■ 本章建议')
    chapterTips.forEach(s => lines.push(`· ${s}`))
  }

  const futureTips = llm?.future_chapter_suggestions ?? []
  if (futureTips.length) {
    lines.push('', '■ 后续章节注意（重写时勿破坏衔接）')
    futureTips.forEach(s => lines.push(`· ${s}`))
  }

  const issues = [...(report.blockers ?? []), ...(report.warnings ?? [])]
  if (issues.length) {
    lines.push('', '■ 待修复问题')
    issues.slice(0, 5).forEach(it => {
      lines.push(`· [${it.rule_id}] ${it.message}`)
    })
  }

  if (llm?.continuity_issue?.trim() && (llm.continuity_score ?? 100) < 80) {
    lines.push('', `■ 衔接：${llm.continuity_issue}`)
  }
  if (llm?.hook_issue?.trim() && (llm.hook_score ?? 100) < 80) {
    lines.push(`■ 钩子：${llm.hook_issue}`)
  }
  ;(llm?.beat_issues ?? []).slice(0, 3).forEach(b => lines.push(`· 五拍：${b}`))

  return lines.join('\n').trim()
}
