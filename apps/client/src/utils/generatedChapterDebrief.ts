import { aiApi } from '../api/client'

type ModelProfile = 'local' | 'gemini'
type MemoryType = 'event' | 'character_state' | 'foreshadow' | 'setting' | 'conflict'
type AssetUpdates = Record<string, unknown>

interface NewCharacterResult {
  name: string
  role?: string
  gender?: string
  age?: string
  faction?: string
  personality?: string
  motivation?: string
  background?: string
  current_realm?: string
  current_status?: string
  current_location?: string
  arc_scope?: string
  author_notes?: string
}

interface AutoDebriefResult {
  character_updates?: Array<{
    character_id?: string
    current_realm?: string
    current_location?: string
    current_status?: string
    add_skill_name?: string
    add_skill_mastery?: string
  }>
  new_characters?: NewCharacterResult[]
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
  asset_updates?: AssetUpdates
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
  assetCreatedCount: number
  assetUpdatedCount: number
  chapterIndexSaved: boolean
  chapterIndexError?: string
}

export async function autoCommitGeneratedChapterDebrief(
  projectId: string,
  chapterId: string,
  modelProfile: ModelProfile,
  llmProviderId?: string,
  /** 起草入库已从稿末解析并写入 chapter_index 时，避免 auto-debrief 的 chapter_index 覆盖 */
  options?: { omitChapterIndex?: boolean },
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

  // 连续续写链路中必须调用 chapter-debrief：即使 AI 未抽出结构化增量，也要落库并清掉 debrief 缓存，
  // 否则下一章 draft 仍读旧人物/记忆；此前此处直接 return 会跳过整次提交。

  const newCharacters = (data.new_characters || [])
    .filter((nc) => typeof nc.name === 'string' && nc.name.trim())

  const commitPayload: Parameters<typeof aiApi.chapterDebrief>[1] = {
    chapter_id: chapterId,
    character_updates: characterUpdates as any,
    storyline_updates: storylineUpdates as any,
    memory_updates: memoryUpdates,
    asset_updates: data.asset_updates,
    new_characters: newCharacters as any,
    notes: data.summary ? `AI生成自动复盘：${data.summary}` : undefined,
  }
  if (!options?.omitChapterIndex && data.chapter_index) {
    commitPayload.chapter_index = data.chapter_index
  }
  const commitRes = await aiApi.chapterDebrief(projectId, commitPayload)

  const d = commitRes.data as Record<string, unknown> | undefined
  const assetStats = (d?.asset_updates as Record<string, unknown>) || {}
  const assetCreatedCount = Number(assetStats.created_items || 0)
    + Number(assetStats.created_skills || 0)
    + Number(assetStats.created_factions || 0)
  const assetUpdatedCount = Number(assetStats.updated_items || 0)
    + Number(assetStats.updated_skills || 0)
    + Number(assetStats.updated_factions || 0)

  const updatedChars = Array.isArray(d?.updated_characters) ? d.updated_characters.length : characterUpdates.length
  const updatedSls = Array.isArray(d?.updated_storylines) ? d.updated_storylines.length : storylineUpdates.length
  const addedMems = Array.isArray(d?.added_memories) ? d.added_memories.length : memoryUpdates.length

  return {
    characterCount: updatedChars,
    storylineCount: updatedSls,
    memoryCount: addedMems,
    assetCreatedCount,
    assetUpdatedCount,
    chapterIndexSaved: !!d?.chapter_index_saved,
    chapterIndexError: d?.chapter_index_error as string | undefined,
  }
}
