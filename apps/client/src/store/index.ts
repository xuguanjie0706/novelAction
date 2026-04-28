import { create } from 'zustand'
import type { Project, Chapter, OutlineNode, Character, WorldSetting, MemoryChunk, GenTask, GenProgressItem, GenTaskStatus, StoryLine, PowerSystem, Skill, Item, Faction } from '../types'

const AI_ROUTE_STORAGE_KEY = 'novelAction:ai-backend-route'
const LEGACY_AI_MODEL_KEY = 'novelAction:ai-model-profile'
const GEN_QUEUE_STORAGE_KEY = 'novelAction:gen-queue:v1'

/**
 * 全局模型路由：
 * - `local`：本地 Ollama（settings.AI_MODEL）
 * - `remote`：远程默认（DB 默认启用项或 GEMINI_* 环境变量）
 * - `remote:<uuid>`：指定 LlmProvider
 */
function readStoredAiBackendRoute(): string {
  try {
    const v = localStorage.getItem(AI_ROUTE_STORAGE_KEY)
    if (v === 'local' || v === 'remote') return v
    if (v?.startsWith('remote:') && v.length > 8) return v
    const legacy = localStorage.getItem(LEGACY_AI_MODEL_KEY)
    if (legacy === 'gemini') return 'remote'
    if (legacy === 'local') return 'local'
    const draftLegacy = localStorage.getItem('novelAction:draft-model-profile')
    if (draftLegacy === 'gemini') return 'remote'
    if (draftLegacy === 'local') return 'local'
  } catch { /* ignore */ }
  return 'local'
}

export function modelProfileFromRoute(route: string): 'local' | 'gemini' {
  return route === 'local' ? 'local' : 'gemini'
}

/** 仅当 route 为 `remote:<uuid>` 时返回 uuid，否则 undefined（走后端默认远程） */
export function llmProviderIdFromRoute(route: string): string | undefined {
  if (route.startsWith('remote:')) return route.slice('remote:'.length) || undefined
  return undefined
}

/** 写作/质检等用 local|gemini；大纲 ai-expand / full-generate 用 default 表示本地 */
export function toOutlineApiModelProfile(route: string): 'default' | 'gemini' {
  return route === 'local' ? 'default' : 'gemini'
}

/** 请求体中可选字段：指定远程线路时使用 */
export function routeLlmProviderPayload(route: string): { llm_provider_id?: string } {
  const id = llmProviderIdFromRoute(route)
  return id ? { llm_provider_id: id } : {}
}

type StoredGenQueuePayload = {
  queue: GenTask[]
  open: boolean
}

function readStoredGenQueueState(): StoredGenQueuePayload {
  try {
    const raw = localStorage.getItem(GEN_QUEUE_STORAGE_KEY)
    if (!raw) return { queue: [], open: false }
    const parsed = JSON.parse(raw) as Partial<StoredGenQueuePayload>
    if (!Array.isArray(parsed.queue)) return { queue: [], open: false }
    const isValidTaskStatus = (status: unknown): status is GenTaskStatus =>
      status === 'pending' || status === 'running' || status === 'done' || status === 'error' || status === 'cancelled'
    const queue = parsed.queue
      .filter((t): t is GenTask =>
        !!t
        && typeof t === 'object'
        && typeof t.id === 'string'
        && isValidTaskStatus((t as Partial<GenTask>).status)
      )
      .map((task) => {
        // 页面重载后原 running 任务无法延续流连接，恢复为 pending 继续执行
        if (task.status !== 'running') return task
        const resumeProgress: GenProgressItem = {
          step: 'resume',
          label: '已从上次会话恢复，准备继续执行',
          done: false,
          error: false,
        }
        const hasResumeMark = task.progress?.some((p) => p.step === 'resume')
        return {
          ...task,
          status: 'pending' as const,
          progress: hasResumeMark ? (task.progress ?? []) : [resumeProgress, ...(task.progress ?? [])],
        }
      })
    return { queue, open: !!parsed.open }
  } catch {
    return { queue: [], open: false }
  }
}

function writeStoredGenQueueState(queue: GenTask[], open: boolean) {
  try {
    localStorage.setItem(GEN_QUEUE_STORAGE_KEY, JSON.stringify({ queue, open }))
  } catch {
    // ignore localStorage failure
  }
}

interface AppState {
  // 当前项目
  currentProject: Project | null
  setCurrentProject: (p: Project | null) => void

  // 世界观设定
  settings: WorldSetting[]
  setSettings: (s: WorldSetting[]) => void
  upsertSetting: (s: WorldSetting) => void
  removeSetting: (id: string) => void

  // 人物
  characters: Character[]
  setCharacters: (c: Character[]) => void
  upsertCharacter: (c: Character) => void
  removeCharacter: (id: string) => void

  // 大纲树
  outlineTree: OutlineNode[]
  setOutlineTree: (tree: OutlineNode[]) => void

  // 章节列表
  chapters: Chapter[]
  setChapters: (c: Chapter[]) => void
  upsertChapter: (c: Chapter) => void
  removeChapter: (id: string) => void

  // 当前编辑章节
  activeChapterId: string | null
  setActiveChapterId: (id: string | null) => void

  // 记忆库
  memories: MemoryChunk[]
  setMemories: (m: MemoryChunk[]) => void

  // 故事线
  storyLines: StoryLine[]
  setStoryLines: (s: StoryLine[]) => void
  upsertStoryLine: (s: StoryLine) => void
  removeStoryLine: (id: string) => void

  // 境界体系
  powerSystems: PowerSystem[]
  setPowerSystems: (s: PowerSystem[]) => void
  upsertPowerSystem: (s: PowerSystem) => void
  removePowerSystem: (id: string) => void

  // 功法技能
  skills: Skill[]
  setSkills: (s: Skill[]) => void
  upsertSkill: (s: Skill) => void
  removeSkill: (id: string) => void

  // 道具法宝
  items: Item[]
  setItems: (s: Item[]) => void
  upsertItem: (s: Item) => void
  removeItem: (id: string) => void

  // 势力组织
  factions: Faction[]
  setFactions: (s: Faction[]) => void
  upsertFaction: (s: Faction) => void
  removeFaction: (id: string) => void

  // UI 状态
  sidebarTab: 'outline' | 'characters' | 'settings' | 'memory'
  setSidebarTab: (t: AppState['sidebarTab']) => void
  aiPanelOpen: boolean
  setAiPanelOpen: (v: boolean) => void

  /**
   * 全局 AI 线路：`local` | `remote` | `remote:<LlmProvider uuid>`
   * 见 readStoredAiBackendRoute
   */
  aiBackendRoute: string
  setAiBackendRoute: (route: string) => void

  // ── 大纲生成队列 ──────────────────────────────────
  genQueue: GenTask[]
  genQueueOpen: boolean
  setGenQueueOpen: (v: boolean) => void
  /** 添加任务，返回新任务 id */
  addGenTask: (task: Omit<GenTask, 'id' | 'createdAt' | 'status' | 'progress'>) => string
  /** 局部更新某个任务 */
  updateGenTask: (id: string, updates: Partial<GenTask>) => void
  /** 往任务的 progress 数组追加或更新一条进度 */
  pushGenProgress: (id: string, item: GenProgressItem) => void
  /** 删除已完成/出错的任务 */
  removeGenTask: (id: string) => void
  /** 大纲树是否需要刷新（队列任务完成后置 true，OutlinePage 检测到后 reload 并置 false） */
  outlineNeedsReload: boolean
  setOutlineNeedsReload: (v: boolean) => void
}

const _storedQueueState = readStoredGenQueueState()
let _taskIdCounter = _storedQueueState.queue.reduce((max, task) => {
  const matched = task.id.match(/^task-(\d+)-\d+$/)
  if (!matched) return max
  const current = Number(matched[1])
  return Number.isFinite(current) ? Math.max(max, current) : max
}, 0)

export const useAppStore = create<AppState>((set) => ({
  currentProject: null,
  setCurrentProject: (p) => set({ currentProject: p }),

  settings: [],
  setSettings: (s) => set({ settings: s }),
  upsertSetting: (s) => set((state) => ({
    settings: state.settings.find(x => x.id === s.id)
      ? state.settings.map(x => x.id === s.id ? s : x)
      : [...state.settings, s]
  })),
  removeSetting: (id) => set((state) => ({ settings: state.settings.filter(x => x.id !== id) })),

  characters: [],
  setCharacters: (c) => set({ characters: c }),
  upsertCharacter: (c) => set((state) => ({
    characters: state.characters.find(x => x.id === c.id)
      ? state.characters.map(x => x.id === c.id ? c : x)
      : [...state.characters, c]
  })),
  removeCharacter: (id) => set((state) => ({ characters: state.characters.filter(x => x.id !== id) })),

  outlineTree: [],
  setOutlineTree: (tree) => set({ outlineTree: tree }),

  chapters: [],
  setChapters: (c) => set({ chapters: c }),
  upsertChapter: (c) => set((state) => ({
    chapters: state.chapters.find(x => x.id === c.id)
      ? state.chapters.map(x => x.id === c.id ? c : x)
      : [...state.chapters, c]
  })),
  removeChapter: (id) => set((state) => ({ chapters: state.chapters.filter(x => x.id !== id) })),

  activeChapterId: null,
  setActiveChapterId: (id) => set({ activeChapterId: id }),

  memories: [],
  setMemories: (m) => set({ memories: m }),

  storyLines: [],
  setStoryLines: (s) => set({ storyLines: s }),
  upsertStoryLine: (s) => set((state) => ({
    storyLines: state.storyLines.find(x => x.id === s.id)
      ? state.storyLines.map(x => x.id === s.id ? s : x)
      : [...state.storyLines, s]
  })),
  removeStoryLine: (id) => set((state) => ({ storyLines: state.storyLines.filter(x => x.id !== id) })),

  powerSystems: [],
  setPowerSystems: (s) => set({ powerSystems: s }),
  upsertPowerSystem: (s) => set((state) => ({
    powerSystems: state.powerSystems.find(x => x.id === s.id)
      ? state.powerSystems.map(x => x.id === s.id ? s : x)
      : [...state.powerSystems, s]
  })),
  removePowerSystem: (id) => set((state) => ({ powerSystems: state.powerSystems.filter(x => x.id !== id) })),

  skills: [],
  setSkills: (s) => set({ skills: s }),
  upsertSkill: (s) => set((state) => ({
    skills: state.skills.find(x => x.id === s.id)
      ? state.skills.map(x => x.id === s.id ? s : x)
      : [...state.skills, s]
  })),
  removeSkill: (id) => set((state) => ({ skills: state.skills.filter(x => x.id !== id) })),

  items: [],
  setItems: (s) => set({ items: s }),
  upsertItem: (s) => set((state) => ({
    items: state.items.find(x => x.id === s.id)
      ? state.items.map(x => x.id === s.id ? s : x)
      : [...state.items, s]
  })),
  removeItem: (id) => set((state) => ({ items: state.items.filter(x => x.id !== id) })),

  factions: [],
  setFactions: (s) => set({ factions: s }),
  upsertFaction: (s) => set((state) => ({
    factions: state.factions.find(x => x.id === s.id)
      ? state.factions.map(x => x.id === s.id ? s : x)
      : [...state.factions, s]
  })),
  removeFaction: (id) => set((state) => ({ factions: state.factions.filter(x => x.id !== id) })),

  sidebarTab: 'outline',
  setSidebarTab: (t) => set({ sidebarTab: t }),
  aiPanelOpen: false,
  setAiPanelOpen: (v) => set({ aiPanelOpen: v }),

  aiBackendRoute: readStoredAiBackendRoute(),
  setAiBackendRoute: (route) => {
    try {
      localStorage.setItem(AI_ROUTE_STORAGE_KEY, route)
    } catch { /* ignore */ }
    set({ aiBackendRoute: route })
  },

  // ── 生成队列 ─────────────────────────────────────
  genQueue: _storedQueueState.queue,
  genQueueOpen: _storedQueueState.open,
  setGenQueueOpen: (v) => set((state) => {
    writeStoredGenQueueState(state.genQueue, v)
    return { genQueueOpen: v }
  }),

  addGenTask: (task) => {
    const id = `task-${++_taskIdCounter}-${Date.now()}`
    set((state) => {
      const nextTask: GenTask = { ...task, id, status: 'pending', progress: [], createdAt: Date.now() }
      const nextQueue = [
        ...state.genQueue,
        nextTask,
      ]
      writeStoredGenQueueState(nextQueue, true)
      return {
        genQueue: nextQueue,
        genQueueOpen: true,   // 有新任务时自动展开面板
      }
    })
    return id
  },

  updateGenTask: (id, updates) =>
    set((state) => {
      const nextQueue = state.genQueue.map(t => t.id === id ? { ...t, ...updates } : t)
      writeStoredGenQueueState(nextQueue, state.genQueueOpen)
      return { genQueue: nextQueue }
    }),

  pushGenProgress: (id, item) =>
    set((state) => {
      const nextQueue = state.genQueue.map(t => {
        if (t.id !== id) return t
        const idx = t.progress.findIndex(p => p.step === item.step)
        if (idx >= 0) {
          const next = [...t.progress]
          next[idx] = item
          return { ...t, progress: next }
        }
        return { ...t, progress: [...t.progress, item] }
      })
      writeStoredGenQueueState(nextQueue, state.genQueueOpen)
      return { genQueue: nextQueue }
    }),

  removeGenTask: (id) =>
    set((state) => {
      const nextQueue = state.genQueue.filter(t => t.id !== id)
      writeStoredGenQueueState(nextQueue, state.genQueueOpen)
      return { genQueue: nextQueue }
    }),

  outlineNeedsReload: false,
  setOutlineNeedsReload: (v) => set({ outlineNeedsReload: v }),
}))
