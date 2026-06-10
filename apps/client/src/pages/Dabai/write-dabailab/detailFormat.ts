/** 设定块展示用格式化 */
export function fmtVal(v: unknown): string {
  if (v == null || v === '') return ''
  if (Array.isArray(v)) return v.map(x => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join('、')
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function pickFields(data: Record<string, unknown>, labels: Record<string, string>) {
  return Object.entries(labels)
    .filter(([k]) => {
      const v = data[k]
      return v != null && v !== '' && !(Array.isArray(v) && v.length === 0)
    })
    .map(([k, label]) => ({ label, value: fmtVal(data[k]) }))
}
