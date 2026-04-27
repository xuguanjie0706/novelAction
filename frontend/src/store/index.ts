import { create } from 'zustand'
import type { Project, Chapter, OutlineNode, Character, WorldSetting, MemoryChunk, GenTask, GenProgressItem } from '../types'

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
