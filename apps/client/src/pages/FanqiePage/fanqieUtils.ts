/** 番茄页共享格式化工具 */

export function formatWords(n?: number) {
  if (!n) return '—'
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万字` : `${n} 字`
}

export function formatFanqieTime(ts?: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = Date.now()
  const diff = now - d.getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const days = Math.floor(h / 24)
  if (days < 30) return `${days} 天前`
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function fanqieStatusLabel(status?: number) {
  return status === 0 ? '已完结' : '连载中'
}

export function fanqieStatusColor(status?: number) {
  return status === 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
}

/** 占位卡片用的假书名 */
export const PLACEHOLDER_TITLES = [
  '连接番茄后显示',
  '你的番茄作品',
  '同步章节与草稿',
  '作家后台书籍',
]
