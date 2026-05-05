/** 消费 /ai/draft-assist/stream 的 SSE 行解析与纯文本稿转 HTML（与 GenerationQueuePanel 行为一致） */

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function plainTextDraftToHtml(s: string) {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

export function parseSseDraftDataLine(line: string): { text?: string; error?: string; done?: boolean } | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try {
    return JSON.parse(raw) as { text?: string; error?: string }
  } catch {
    return null
  }
}

/** 读完流式响应，返回模型输出的纯文本（含可能的索引块，交由 splitStreamedDraftText 拆分） */
export async function accumulateDraftAssistStream(res: Response): Promise<string> {
  if (!res.ok) {
    const errText = (await res.text().catch(() => '')).slice(0, 500)
    throw new Error(errText || `HTTP ${res.status}`)
  }
  if (!res.body) throw new Error('响应无流式内容')
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let accumulated = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const parsed = parseSseDraftDataLine(line)
      if (!parsed) continue
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.text) accumulated += parsed.text
    }
  }
  for (const line of buf.split('\n')) {
    const parsed = parseSseDraftDataLine(line)
    if (parsed?.error) throw new Error(parsed.error)
    if (parsed?.text) accumulated += parsed.text
  }
  return accumulated
}
