import { create } from 'zustand'
import type { Project, Chapter, OutlineNode, Character, WorldSetting, MemoryChunk, GenTask, GenProgressItem } from '../types'

const AI_ROUTE_STORAGE_KEY = 'novelAction:ai-backend-route'
const LEGACY_AI_MODEL_KEY = 'novelAction:ai-model-profile'

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

let _taskIdCounter = 0

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
  genQueue: [],
  genQueueOpen: false,
  setGenQueueOpen: (v) => set({ genQueueOpen: v }),

  addGenTask: (task) => {
    const id = `task-${++_taskIdCounter}-${Date.now()}`
    set((state) => ({
      genQueue: [
        ...state.genQueue,
        { ...task, id, status: 'pending', progress: [], createdAt: Date.now() },
      ],
      genQueueOpen: true,   // 有新任务时自动展开面板
    }))
    return id
  },

  updateGenTask: (id, updates) =>
    set((state) => ({
      genQueue: state.genQueue.map(t => t.id === id ? { ...t, ...updates } : t),
    })),

  pushGenProgress: (id, item) =>
    set((state) => ({
      genQueue: state.genQueue.map(t => {
        if (t.id !== id) return t
        const idx = t.progress.findIndex(p => p.step === item.step)
        if (idx >= 0) {
          const next = [...t.progress]
          next[idx] = item
          return { ...t, progress: next }
        }
        return { ...t, progress: [...t.progress, item] }
      }),
    })),

  removeGenTask: (id) =>
    set((state) => ({ genQueue: state.genQueue.filter(t => t.id !== id) })),

  outlineNeedsReload: false,
  setOutlineNeedsReload: (v) => set({ outlineNeedsReload: v }),
}))
