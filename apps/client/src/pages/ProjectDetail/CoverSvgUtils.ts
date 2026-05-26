/**
 * CoverSvgUtils — SVG 占位封面生成（无图片提供者时的预览）
 *
 * 纯工具函数，无 React / API 依赖。
 */
import type { Project } from '../../types'

// ── 流派色彩主题 ──────────────────────────────────────────────────────────────
export const GENRE_THEMES: Record<string, {
  bg1: string; bg2: string; bg3: string; accent: string; symbol: string
}> = {
  '玄幻':  { bg1: '#1e0a3c', bg2: '#4a1d96', bg3: '#7c3aed', accent: '#c4b5fd', symbol: '⚡' },
  '修真':  { bg1: '#0f0522', bg2: '#2e1065', bg3: '#6d28d9', accent: '#a78bfa', symbol: '☯' },
  '仙侠':  { bg1: '#1a0533', bg2: '#701a75', bg3: '#a21caf', accent: '#f0abfc', symbol: '✦' },
  '都市':  { bg1: '#0c1a2e', bg2: '#1e3a8a', bg3: '#1d4ed8', accent: '#93c5fd', symbol: '◈' },
  '悬疑':  { bg1: '#0a0a0a', bg2: '#1c1917', bg3: '#292524', accent: '#a8a29e', symbol: '?' },
  '历史':  { bg1: '#1c0f00', bg2: '#451a03', bg3: '#92400e', accent: '#fcd34d', symbol: '⚔' },
  '言情':  { bg1: '#1f0515', bg2: '#500724', bg3: '#9d174d', accent: '#fbcfe8', symbol: '♡' },
  '科幻':  { bg1: '#001a19', bg2: '#064e3b', bg3: '#0f766e', accent: '#5eead4', symbol: '◉' },
  '武侠':  { bg1: '#1a0000', bg2: '#450a0a', bg3: '#b91c1c', accent: '#fca5a5', symbol: '刀' },
  default: { bg1: '#1c0a00', bg2: '#451a03', bg3: '#b45309', accent: '#fde68a', symbol: '✦' },
}

export function getTheme(genre?: string) {
  if (!genre) return GENRE_THEMES.default
  for (const key of Object.keys(GENRE_THEMES)) {
    if (genre.includes(key)) return GENRE_THEMES[key]
  }
  return GENRE_THEMES.default
}

export function wrapTitle(title: string, maxLen = 6): string[] {
  if (title.length <= maxLen) return [title]
  const lines: string[] = []
  for (let i = 0; i < title.length; i += maxLen) lines.push(title.slice(i, i + maxLen))
  return lines.slice(0, 3)
}

/** 根据项目信息生成 SVG 占位封面字符串 */
export function generateCoverSvg(project: Project): string {
  const t = getTheme(project.genre)
  const lines = wrapTitle(project.title)
  const lineHeight = 52
  const titleY = 200 - ((lines.length - 1) * lineHeight) / 2
  const stars = Array.from({ length: 18 }, (_, i) => ({
    cx: ((i * 137) % 280) + 10, cy: ((i * 97) % 300) + 10,
    r: ((i * 13) % 3) + 1, opacity: ((i % 5) + 3) / 10,
  }))
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 420" width="300" height="420">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${t.bg1}"/>
      <stop offset="45%" stop-color="${t.bg2}"/>
      <stop offset="100%" stop-color="${t.bg3}"/>
    </linearGradient>
    <linearGradient id="spine" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${t.bg1}" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="${t.bg1}" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <radialGradient id="center" cx="50%" cy="50%">
      <stop offset="0%" stop-color="${t.bg3}" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="${t.bg1}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="300" height="420" fill="url(#bg)"/>
  <ellipse cx="150" cy="210" rx="160" ry="200" fill="url(#center)"/>
  ${stars.map(s => `<circle cx="${s.cx}" cy="${s.cy}" r="${s.r}" fill="${t.accent}" opacity="${s.opacity}"/>`).join('')}
  <circle cx="150" cy="210" r="120" fill="none" stroke="${t.accent}" stroke-width="0.5" opacity="0.2"/>
  <text x="150" y="80" text-anchor="middle" font-size="40" fill="${t.accent}" opacity="0.3" filter="url(#glow)">${t.symbol}</text>
  ${lines.map((line, i) => `<text x="150" y="${titleY + i * lineHeight}" text-anchor="middle" font-family="'PingFang SC','Microsoft YaHei',serif" font-size="38" font-weight="700" fill="${t.accent}" filter="url(#glow)">${line}</text>`).join('')}
  ${project.genre ? `<text x="150" y="${titleY + lines.length * lineHeight + 22}" text-anchor="middle" font-family="'PingFang SC','Microsoft YaHei',serif" font-size="15" fill="${t.accent}" opacity="0.7">${project.genre}</text>` : ''}
  <rect width="18" height="420" fill="url(#spine)"/>
  <line x1="60" y1="380" x2="240" y2="380" stroke="${t.accent}" stroke-width="0.8" opacity="0.4"/>
</svg>`
}

/** 将 SVG 字符串转为 data URL */
export function svgToDataUrl(svg: string): string {
  return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)))
}
