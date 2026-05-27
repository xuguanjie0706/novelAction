/**
 * useChapterAutosave.ts — 章节自动保存 + 记忆提取 + 故事线同步 hook
 *
 * 职责：
 *   - autoSave：编辑器 onUpdate 节流保存 + 自动触发记忆提取
 *   - manualSave：手动快照 + 记忆 + 故事线同步
 *   - autoExtractMemoryAfterChapter：章节记忆自动提取
 *   - autoSyncStorylinesAfterChapter：章节复盘故事线自动同步
 *   - cleanupChapter：删除章节 + 导航到相邻章节
 *
 * 副作用范围：chaptersApi / aiApi / storylinesApi；更新 store 的 upsertChapter /
 * setMemories / setStoryLines / removeChapter / setActiveChapterId。
 */
import { useCallback, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import type { Editor } from '@tiptap/react'
import { chaptersApi, aiApi, storylinesApi } from '../../../../api/client'
import { useAppStore, modelProfileFromRoute, routeLlmProviderPayload, llmProviderIdFromRoute } from '../../../../store'
import type { Chapter, StoryLine } from '../../../../types'
import { isUuidLike } from '../utils'
import type { AutoDebriefResponse } from '../types'
import { STATUS_OPTIONS } from '../constants'

interface UseChapterAutosaveOptions {
  projectId: string
  chapter: Chapter
  editor: ReturnType<typeof import('@tiptap/react').useEditor> | null
  chapters: Chapter[]
  storyLines: StoryLine[]
  upsertChapter: (ch: Chapter) => void
  setMemories: (memories: any[]) => void
  setStoryLines: (lines: StoryLine[]) => void
  removeChapter: (id: string) => void
  setActiveChapterId: (id: string | null) => void
  /** 与 TipTap onUpdate 共用；由编排壳创建并传入 */
  saveTimerRef?: React.MutableRefObject<ReturnType<typeof setTimeout> | undefined>
}

export interface UseChapterAutosaveReturn {
  /** 编辑器 onUpdate 节流回调，每 2s 触发，自动含记忆提取节流 */
  autoSave: (content: string) => Promise<void>
  /** 手动保存快照，触发记忆提取 + 故事线同步 */
  manualSave: () => Promise<void>
  /**
   * 清空章节正文、删除章节记录、导航到相邻章节。
   * 需要用户二次确认。
   */
  cleanupChapter: () => Promise<void>
  /** 自动提取记忆，showToast=true 时显示结果 toast */
  autoExtractMemoryAfterChapter: (showToast?: boolean) => Promise<void>
  /** 自动同步故事线进度，showToast=true 时显示结果 toast */
  autoSyncStorylinesAfterChapter: (showToast?: boolean) => Promise<void>
  /** 定时器 ref，供编辑器 onUpdate 写入 clearTimeout */
  saveTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | undefined>
  cleaningChapter: boolean
}

/**
 * 章节自动保存与后台同步 hook。
 *
 * @param options - 见 UseChapterAutosaveOptions（所有字段均为必填）
 * @returns 操作函数集合 + saveTimerRef（供调用方 clearTimeout）
 */
export function useChapterAutosave({
  projectId,
  chapter,
  editor,
  chapters,
  storyLines,
  upsertChapter,
  setMemories,
  setStoryLines,
  removeChapter,
  setActiveChapterId,
  saveTimerRef: externalSaveTimerRef,
}: UseChapterAutosaveOptions): UseChapterAutosaveReturn {
  const internalSaveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const saveTimerRef = externalSaveTimerRef ?? internalSaveTimerRef
  const [cleaningChapter, setCleaningChapter] = useState(false)
  const lastMemoryAutoExtractAtRef = useRef(0)
  const storylineAutoSyncingRef = useRef(false)
  const memoryAutoSyncingRef = useRef(false)

  // ── 记忆提取 ─────────────────────────────────────────────────────────────

  /**
   * 后台自动提取章节记忆，带互斥锁避免并发。
   *
   * @param showToast - 提取完成后是否弹 toast（手动保存路径传 true，自动保存传 false）
   */
  const autoExtractMemoryAfterChapter = useCallback(async (showToast = false) => {
    if (memoryAutoSyncingRef.current) return
    memoryAutoSyncingRef.current = true
    try {
      const route = useAppStore.getState().aiBackendRoute
      const extracted = await aiApi.extractMemory(
        projectId,
        chapter.id,
        modelProfileFromRoute(route),
        llmProviderIdFromRoute(route),
      )
      const count = Array.isArray(extracted.data) ? extracted.data.length : 0
      const allMemories = await aiApi.listMemory(projectId)
      setMemories(allMemories.data)
      if (showToast) {
        if (count > 0) toast.success(`已自动提取 ${count} 条记忆`)
        else toast('本章未提取到新记忆', { icon: 'ℹ️' })
      }
    } catch {
      if (showToast) toast.error('自动提取记忆失败，请在 AI 面板手动提取')
    } finally {
      memoryAutoSyncingRef.current = false
    }
  }, [projectId, chapter.id, setMemories])

  // ── 故事线同步 ────────────────────────────────────────────────────────────

  /**
   * 调用 AI 自动复盘提取故事线更新，并提交到服务端。
   * 带互斥锁，避免保存路径并发触发。
   *
   * @param showToast - 同步完成后是否弹 toast
   */
  const autoSyncStorylinesAfterChapter = useCallback(async (showToast = false) => {
    if (storylineAutoSyncingRef.current) return
    storylineAutoSyncingRef.current = true
    try {
      const route = useAppStore.getState().aiBackendRoute
      const auto = await aiApi.autoDebrief(projectId, {
        chapter_id: chapter.id,
        model_profile: modelProfileFromRoute(route),
        ...routeLlmProviderPayload(route),
      })
      const data = auto.data as {
        storyline_updates?: Array<{
          storyline_id?: string
          storyline_name?: string
          status?: string
          beat?: string
          actual_tension?: number
          beat_match_score?: number
          crossover_executed?: boolean
          screen_time_words?: number
        }>
      }
      const storylineUpdates = (data.storyline_updates || [])
        .map((su) => {
          const fields: Record<string, unknown> = {}
          if (su.status) fields.status = su.status
          if (su.beat) fields.append_beat = su.beat
          if (su.actual_tension != null) fields.actual_tension = su.actual_tension
          if (su.beat_match_score != null) fields.beat_match_score = su.beat_match_score
          if (su.crossover_executed != null) fields.crossover_executed = su.crossover_executed
          if (su.screen_time_words != null) fields.screen_time_words = su.screen_time_words
          if (Object.keys(fields).length === 0) return null
          let resolvedId = su.storyline_id || ''
          if (!isUuidLike(resolvedId) && su.storyline_name) {
            const byName = storyLines.find(sl => sl.name === su.storyline_name)
            if (byName?.id && isUuidLike(byName.id)) resolvedId = byName.id
          }
          if (!isUuidLike(resolvedId)) return null
          return { storyline_id: resolvedId, ...fields }
        })
        .filter((x): x is Record<string, unknown> & { storyline_id: string } => !!x)

      if (storylineUpdates.length === 0) return
      await aiApi.chapterDebrief(projectId, {
        chapter_id: chapter.id,
        storyline_updates: storylineUpdates,
      })
      const refreshed = await storylinesApi.list(projectId)
      setStoryLines(refreshed.data)
      if (showToast) toast.success(`已自动推进 ${storylineUpdates.length} 条故事线`)
    } catch {
      if (showToast) toast.error('自动更新故事线失败，请在复盘面板手动提交')
    } finally {
      storylineAutoSyncingRef.current = false
    }
  }, [projectId, chapter.id, storyLines, setStoryLines])

  // ── 自动 / 手动保存 ───────────────────────────────────────────────────────

  /**
   * 编辑器内容变化时节流触发的自动保存。
   * 每 90s 最多触发一次记忆提取（避免高频 AI 调用）。
   *
   * @param content - 编辑器当前 HTML 内容
   */
  const autoSave = useCallback(async (content: string) => {
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
      const now = Date.now()
      const plainLen = (content || '').replace(/<[^>]+>/g, '').trim().length
      if (plainLen >= 120 && now - lastMemoryAutoExtractAtRef.current > 90_000) {
        await autoExtractMemoryAfterChapter(false)
        lastMemoryAutoExtractAtRef.current = now
      }
    } catch { /* 静默失败，避免打扰写作流 */ }
  }, [projectId, chapter.id, upsertChapter, autoExtractMemoryAfterChapter])

  /**
   * 手动保存：写入 content → 生成版本快照 → 提取记忆 → 同步故事线。
   * 用户点击「保存」按钮时调用。
   */
  const manualSave = useCallback(async () => {
    if (!editor) return
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content: editor.getHTML() })
      upsertChapter(res.data)
      await chaptersApi.snapshot(projectId, chapter.id, '手动保存')
      await autoExtractMemoryAfterChapter(true)
      await autoSyncStorylinesAfterChapter(true)
      toast.success('已保存快照')
    } catch { toast.error('保存失败') }
  }, [projectId, chapter.id, editor, upsertChapter, autoExtractMemoryAfterChapter, autoSyncStorylinesAfterChapter])

  // ── 章节清理 ─────────────────────────────────────────────────────────────

  /**
   * 删除本章（正文 + 历史 + 记忆 + ChapterIndex），导航到相邻章节。
   * 会弹 confirm 二次确认。大纲中的 chapter_plan 节点保留。
   */
  const cleanupChapter = useCallback(async () => {
    const ok = window.confirm(
      `确认清理《${chapter.title}》？\n\n这会删除本章正文、版本历史、对应记忆数据和 ChapterIndex。大纲中的章节计划会保留，可稍后重新创建。`,
    )
    if (!ok) return
    setCleaningChapter(true)
    try {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      await chaptersApi.delete(projectId, chapter.id)
      const sorted = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
      const currentIndex = sorted.findIndex(c => c.id === chapter.id)
      const nextChapter = sorted[currentIndex + 1] || sorted[currentIndex - 1]
      removeChapter(chapter.id)
      setActiveChapterId(nextChapter?.id ?? null)
      const memoriesRes = await aiApi.listMemory(projectId)
      setMemories(memoriesRes.data)
      toast.success('章节已清理')
    } catch {
      toast.error('清理章节失败')
    } finally {
      setCleaningChapter(false)
    }
  }, [projectId, chapter, chapters, removeChapter, setActiveChapterId, setMemories])

  return {
    autoSave,
    manualSave,
    cleanupChapter,
    autoExtractMemoryAfterChapter,
    autoSyncStorylinesAfterChapter,
    saveTimerRef,
    cleaningChapter,
  }
}
