function formatApiDetail(d: unknown): string | null {
  if (typeof d === 'string' && d.trim()) return d.trim()
  if (Array.isArray(d) && d.length) {
    const first = d[0] as { msg?: string }
    if (first && typeof first.msg === 'string' && first.msg.trim()) return first.msg.trim()
  }
  if (d && typeof d === 'object') {
    const obj = d as { message?: string; rationale?: string }
    if (typeof obj.message === 'string' && obj.message.trim()) {
      const why = (obj.rationale || '').trim()
      if (why.length > 0) {
        const clipped = why.length > 80 ? `${why.slice(0, 80)}…` : why
        return `${obj.message.trim()}（${clipped}）`
      }
      return obj.message.trim()
    }
  }
  return null
}

/** 优先使用 FastAPI 返回的 `detail`，避免 axios 的 “Request failed with status code …” 掩盖原因。 */
export function formatApiError(error: unknown): string {
  if (error && typeof error === 'object') {
    const e = error as {
      response?: { data?: { detail?: unknown } }
      message?: string
    }
    const fromDetail = formatApiDetail(e.response?.data?.detail)
    if (fromDetail) return fromDetail
    const m = e.message?.match(/^Request failed with status code (\d+)$/i)
    if (m) return `请求失败（HTTP ${m[1]}）`
    if (e.message) return e.message
  }
  if (error instanceof Error && error.message) return error.message
  return '未知错误'
}
