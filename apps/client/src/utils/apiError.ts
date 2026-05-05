/** 优先使用 FastAPI 返回的 `detail`，避免 axios 的 “Request failed with status code …” 掩盖原因。 */
export function formatApiError(error: unknown): string {
  if (error && typeof error === 'object') {
    const e = error as {
      response?: { data?: { detail?: unknown } }
      message?: string
    }
    const d = e.response?.data?.detail
    if (typeof d === 'string' && d.trim()) return d.trim()
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: string }
      if (first && typeof first.msg === 'string' && first.msg.trim()) return first.msg.trim()
    }
    const m = e.message?.match(/^Request failed with status code (\d+)$/i)
    if (m) return `请求失败（HTTP ${m[1]}）`
    if (e.message) return e.message
  }
  if (error instanceof Error && error.message) return error.message
  return '未知错误'
}
