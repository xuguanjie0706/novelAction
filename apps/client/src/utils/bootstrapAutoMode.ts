/** Bootstrap 自动模式偏好（localStorage，跨会话记住） */
const STORAGE_KEY = 'novelaction_bootstrap_auto_mode_v1'

export function readBootstrapAutoMode(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function saveBootstrapAutoMode(enabled: boolean): void {
  try {
    if (enabled) localStorage.setItem(STORAGE_KEY, '1')
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 隐私模式等 */
  }
}
