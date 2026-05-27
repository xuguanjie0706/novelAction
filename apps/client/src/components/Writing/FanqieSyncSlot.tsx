/**
 * 写作树章行前导指示：已同步番茄时在原状态圆点位置显示角标，否则保留状态圆点。
 */
import clsx from 'clsx'
import type { Chapter } from '../../types'
import { readFanqieChapterSync } from '../../utils/fanqieChapterSync'
import FanqieSyncedBadge from './FanqieSyncedBadge'

export interface ChapterTreeLeadingIndicatorProps {
  chapter?: Chapter
  /** 项目绑定的番茄 book_id；空则始终显示状态圆点 */
  fanqieBookId: string
  statusDotClass: string
}

/** 章行首列：番茄已同步则替换状态圆点，否则显示原状态/占位圆点 */
export function ChapterTreeLeadingIndicator({
  chapter,
  fanqieBookId,
  statusDotClass,
}: ChapterTreeLeadingIndicatorProps) {
  const syncMeta = chapter && fanqieBookId
    ? readFanqieChapterSync(chapter.extra, fanqieBookId)
    : null

  if (syncMeta) {
    const tooltip = syncMeta.title
      ? `已同步番茄：${syncMeta.title}`
      : '已同步到番茄作家后台'
    return <FanqieSyncedBadge title={tooltip} compact />
  }

  if (chapter) {
    return (
      <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', statusDotClass)} />
    )
  }

  return <span className="w-1.5 h-1.5 rounded-full shrink-0 border border-gray-200" />
}
