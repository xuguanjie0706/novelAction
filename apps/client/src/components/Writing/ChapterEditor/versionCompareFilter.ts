/**
 * 对照 / 版本列表：过滤门控写作内部迭代产生的中间备份。
 */
import type { ChapterVersion } from '../../../types'

const GATE_MID_ROUND = /质量门控第[2-9]\d*轮起笔前自动备份/

/** 用户点一次「门控重写」只需看到「改写前备份 + 当前正文」，隐藏第 2/3 轮中间稿 */
export function filterVersionsForUserCompare(versions: ChapterVersion[]): ChapterVersion[] {
  return versions.filter(v => !GATE_MID_ROUND.test(v.note || ''))
}
