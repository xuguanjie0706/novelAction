import { aiApi } from '../api/client'

type ModelProfile = 'local' | 'gemini'
type MemoryType = 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict'

interface AutoDebriefResult {
  character_updates?: Array<{
    character_id?: string
    current_realm?: string
    current_location?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>
  storyline_updates?: Array<{
    storyline_id?: string
    storyline_name?: string
    status?: string
    beat?: string
  }>
  memory_updates?: Array<{
    memory_type?: MemoryType
    title?: string
    content?: string
    tags?: string[]
  }>
  chapter_index?: {
    story_day?: string
    core_events?: Array<Record<string, unknown> | string>
    first_appearances?: Array<Record<string, unknown>>
    actual_foreshadows_laid?: Array<Record<string, unknown>>
    actual_foreshadows_resolved?: Array<Record<string, unknown>>
    ending_hook?: string
    hook_strength?: number
    continuity_notes?: Array<Record<string, unknown> | string>
  }
  summary?: string
  error?: string
}

export interface GeneratedChapterDebriefStats {
  characterCount: number
  storylineCount: number
  memoryCount: number
}

export async function autoCommitGeneratedChapterDebrief(
  projectId: string,
  chapterId: string,
  modelProfile: ModelProfile,
  llmProviderId?: string,
): Promise<GeneratedChapterDebriefStats> {
  const debriefRes = await aiApi.autoDebrief(projectId, {
    chapter_id: chapterId,
    model_profile: modelProfile,
    ...(llmProviderId ? { llm_provider_id: llmProviderId } : {}),
  })
  const data = debriefRes.data as AutoDebriefResult

  if (data.error) throw new Error(data.error)

  const characterUpdates = (data.character_updates || [])
    .map((update) => {
      const entry: Record<string, unknown> = { character_id: update.character_id }
      if (update.current_realm) entry.current_realm = update.current_realm
      if (update.current_location) entry.current_location = update.current_location
      if (update.current_status) entry.current_status = update.current_status
      if (update.add_skill_name) {
        entry.add_skill = {
          skill_name: update.add_skill_name,
          mastery: update.add_skill_mastery || '初学',
        }
      }
      return entry
    })
    .filter((entry) => typeof entry.character_id === 'string' && Object.keys(entry).length > 1)

  const storylineUpdates = (data.storyline_updates || [])
    .map((update) => {
      const entry: Record<string, unknown> = {
        storyline_id: update.storyline_id || '',
        storyline_name: update.storyline_name,
      }
      if (update.status) entry.status = update.status
      if (update.beat) entry.append_beat = update.beat
      return entry
    })
    .filter((entry) => (
      (entry.storyline_id || entry.storyline_name)
      && Object.keys(entry).some(k => !['storyline_id', 'storyline_name'].includes(k))
    ))

  const memoryUpdates = (data.memory_updates || [])
    .filter((update) => typeof update.content === 'string' && update.content.trim())
    .map((update) => ({
      memory_type: update.memory_type || 'event',
      title: update.title,
      content: update.content!.trim(),
      tags: Array.isArray(update.tags) ? update.tags.slice(0, 8) : [],
    }))

  const hasChapterIndex = Boolean(data.chapter_index && Object.keys(data.chapter_index).length > 0)

  if (characterUpdates.length === 0 && storylineUpdates.length === 0 && memoryUpdates.length === 0 && !hasChapterIndex && !data.summary) {
    return { characterCount: 0, storylineCount: 0, memoryCount: 0 }
  }

  await aiApi.chapterDebrief(projectId, {
    chapter_id: chapterId,
    character_updates: characterUpdates as any,
    storyline_updates: storylineUpdates as any,
    memory_updates: memoryUpdates,
    chapter_index: data.chapter_index,
    notes: data.summary ? `AI生成自动复盘：${data.summary}` : undefined,
  })

  return {
    characterCount: characterUpdates.length,
    storylineCount: storylineUpdates.length,
    memoryCount: memoryUpdates.length,
  }
}
