/**
 * 浏览器会话内记录「进行中的 Bootstrap run」，用于刷新后恢复订阅与闸门 UI。
 *
 * 与后端 ``BootstrapRun`` 互补：终态（done / failed / cancelled）必须调用 ``clearActiveBootstrapRun``。
 */
const STORAGE_KEY = 'novelaction_bootstrap_active_v1'

export interface ActiveBootstrapRunPersisted {
  runId: string
  logline?: string
  projectId?: string | null
  savedAt: number
}

export function saveActiveBootstrapRun(data: Omit<ActiveBootstrapRunPersisted, 'savedAt'> & { savedAt?: number }) {
  try {
    const payload: ActiveBootstrapRunPersisted = {
      runId: data.runId,
      logline: data.logline,
      projectId: data.projectId,
      savedAt: data.savedAt ?? Date.now(),
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* 隐私模式等 */
  }
}

export function readActiveBootstrapRun(): ActiveBootstrapRunPersisted | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const o = JSON.parse(raw) as ActiveBootstrapRunPersisted
    if (!o?.runId || typeof o.runId !== 'string') return null
    return o
  } catch {
    return null
  }
}

export function clearActiveBootstrapRun() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
