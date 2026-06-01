/**
 * @file 任务队列 SSE / 草稿文本工具
 */
import type { GenProgressItem } from '../../../../types'
import { authQueryString } from '../../../../api/authFetch'
import { formatRagContextProgressLabel } from '../../../../utils/draftAssistSse'
import { htmlToPlainForSplit, splitStreamedDraftText } from '../../../../utils/draftChapterIndexSplit'
import { createStorylinePreWarnCollector } from '../../../../utils/storylinePreWarnEvents'

/** 续写：旧叙事 plain + 本次流式全文，便于与入库正文对照 */
export function ragContextSideEventHandler(
  pushProgress: (item: GenProgressItem) => void,
  step: number | string = 'rag_context',
) {
  return (obj: Record<string, unknown>) => {
    if (obj.event !== 'rag_context') return
    pushProgress({
      step,
      label: formatRagContextProgressLabel(obj),
      done: true,
      error: false,
    })
  }
}

/** 普通 draft-assist：RAG 快照 + 写前预警（简报注入正文 prompt） */
export function draftAssistSideEventHandler(
  pushProgress: (item: GenProgressItem) => void,
  phaseStep: (phase: string) => string,
  chapterId?: string,
) {
  const storylineCollector = chapterId ? createStorylinePreWarnCollector(chapterId) : null
  return (obj: Record<string, unknown>) => {
    storylineCollector?.handle(obj)
    const ev = obj.event
    if (ev === 'rag_context') {
      pushProgress({
        step: phaseStep('rag'),
        label: formatRagContextProgressLabel(obj),
        done: true,
        error: false,
      })
      return
    }
    if (ev === 'pre_warn_running') {
      pushProgress({
        step: phaseStep('pre_warn'),
        label: '写前预警：主编审稿中（结果将注入本章正文 prompt）…',
        done: false,
        error: false,
      })
      return
    }
    if (ev === 'pre_warn_done') {
      const ok = obj.ok !== false
      const riskCount = typeof obj.risk_count === 'number' ? obj.risk_count : 0
      const errMsg = typeof obj.error === 'string' ? obj.error : null
      const reused = obj.reused === true
      pushProgress({
        step: phaseStep('pre_warn'),
        label: errMsg
          ? `写前预警：${errMsg}`
          : reused
            ? `写前预警：复用本章已有记录（${riskCount} 处风险；已跳过主编审稿）`
            : ok
              ? `写前预警完成（${riskCount} 处风险；简报已注入正文生成）`
              : `写前预警：${riskCount} 处风险；简报已注入正文生成`,
        done: true,
        error: !!errMsg,
      })
    }
  }
}

/** 重写前将章节 HTML 转为「改写前快照」纯文本（供 manuscript_raw_snapshot 对照） */
export function manuscriptSnapshotBeforeRewrite(chapterContentHtml: string): string | null {
  const prev = htmlToPlainForSplit(chapterContentHtml || '').trim()
  if (!prev) return null
  const { body } = splitStreamedDraftText(prev)
  return (body || prev).trim() || null
}

export function manuscriptRawSnapshotForContinue(chapterContentHtml: string, accumulatedPlain: string): string {
  const prev = htmlToPlainForSplit(chapterContentHtml || '').trim()
  const acc = accumulatedPlain.trim()
  if (!prev) return acc
  if (!acc) return prev
  return `${prev}\n\n${acc}`
}

export function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function plainTextDraftToHtml(s: string) {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

export function parseSseDataLine(line: string): { text?: string; error?: string; done?: boolean } | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try { return JSON.parse(raw) } catch { return null }
}

export function toWsUrl(path: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // 浏览器 WebSocket 无法设自定义 header，把 JWT 拼到 query string 让后端自行鉴权。
  const sep = path.includes('?') ? '&' : '?'
  const auth = authQueryString().replace(/^\?/, '')
  const suffix = auth ? `${sep}${auth}` : ''
  return `${protocol}//${window.location.host}${path}${suffix}`
}
