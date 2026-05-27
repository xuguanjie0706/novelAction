/**
 * 写前 SSE `storyline_pre_warn` → ChapterEditor 预警 UI
 */
import type { StorylinePreWarnItem } from '../components/Writing/ChapterEditor/types'

export function toStorylinePreWarnItem(obj: Record<string, unknown>): StorylinePreWarnItem {
  return {
    warn_id: String(obj.warn_id ?? ''),
    severity: (obj.severity as StorylinePreWarnItem['severity']) ?? 'warning',
    title: String(obj.title ?? ''),
    detail: obj.detail != null ? String(obj.detail) : undefined,
    suggested_action: obj.suggested_action != null ? String(obj.suggested_action) : undefined,
    storyline_id: obj.storyline_id != null ? String(obj.storyline_id) : undefined,
    storyline_name: obj.storyline_name != null ? String(obj.storyline_name) : undefined,
  }
}

export function dispatchStorylinePreWarn(chapterId: string, items: StorylinePreWarnItem[]) {
  if (!chapterId || items.length === 0) return
  window.dispatchEvent(
    new CustomEvent('novelaction:storyline-pre-warn', {
      detail: { chapterId, items },
    }),
  )
}

/** 收集 SSE 中的 storyline_pre_warn，在 pre_warn_done 时一次性推送给写作页。 */
export function createStorylinePreWarnCollector(chapterId: string) {
  const pending: StorylinePreWarnItem[] = []
  return {
    handle(obj: Record<string, unknown>) {
      const ev = obj.event
      if (ev === 'storyline_pre_warn') {
        pending.push(toStorylinePreWarnItem(obj))
        return
      }
      if (ev === 'pre_warn_done' && pending.length > 0) {
        dispatchStorylinePreWarn(chapterId, [...pending])
        pending.length = 0
      }
    },
  }
}
