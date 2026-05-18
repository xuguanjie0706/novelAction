/** 角色配色：分层模式用卡片色，星图模式用发光点色 */
export const ROLE_COLOR: Record<string, { bg: string; border: string; text: string; dot: string; glow: string }> = {
  protagonist: { bg: '#fffbeb', border: '#f59e0b', text: '#92400e', dot: '#fbbf24', glow: 'rgba(251,191,36,0.55)' },
  antagonist: { bg: '#fff1f2', border: '#f43f5e', text: '#9f1239', dot: '#fb7185', glow: 'rgba(251,113,133,0.5)' },
  supporting: { bg: '#eff6ff', border: '#3b82f6', text: '#1e40af', dot: '#60a5fa', glow: 'rgba(96,165,250,0.5)' },
  neutral: { bg: '#f9fafb', border: '#9ca3af', text: '#374151', dot: '#9ca3af', glow: 'rgba(156,163,175,0.45)' },
}

export const ROLE_LABEL: Record<string, string> = {
  protagonist: '主角',
  antagonist: '反派',
  supporting: '配角',
  neutral: '中立',
}

export type GraphLayoutMode = 'constellation' | 'tier'

export const DYNAMIC_LABEL: Record<string, string> = {
  stable: '稳定',
  evolving: '演变中',
  deteriorating: '恶化',
  broken: '破裂',
}

export function intensityToWidth(n: number) {
  return 1 + Math.round(((n - 1) / 9) * 3)
}

export function roleColor(role: string) {
  return ROLE_COLOR[role] ?? ROLE_COLOR.neutral
}

/** 3D 星图与侧栏统一暗色主题 */
export const GRAPH_THEME = {
  canvasBg: '#0a0c14',
  sidebarBg: '#0a0c14',
  border: '#1e293b',
  accent: '#4f46e5',
  accentMuted: '#312e81',
  text: '#e2e8f0',
  textMuted: '#64748b',
} as const

/** 将节点/连线颜色压暗（用于非焦点高亮） */
export function dimHexColor(hex: string, factor: number): string {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const n = parseInt(full, 16)
  const r = Math.round(((n >> 16) & 255) * factor)
  const g = Math.round(((n >> 8) & 255) * factor)
  const b = Math.round((n & 255) * factor)
  return `rgb(${r},${g},${b})`
}
