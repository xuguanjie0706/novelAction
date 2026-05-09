/**
 * 把 ISO 时间字符串转成中文相对时间标签。
 *
 * 规则与 `BookshelfPage.timeAgo` 保持一致：
 * - <1 分钟：「刚刚」
 * - <60 分钟：「N 分钟前」
 * - <24 小时：「N 小时前」
 * - <30 天：「N 天前」
 * - 否则：本地化日期（如「5月7日」）
 *
 * @param dateStr ISO 时间字符串；为 null/undefined/空串时返回「未保存」
 */
export function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return '未保存'
  const t = new Date(dateStr).getTime()
  if (Number.isNaN(t)) return '未保存'
  const diff = Date.now() - t
  if (diff < 0) return '刚刚'

  const m = Math.floor(diff / 60_000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`

  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`

  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`

  return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}
