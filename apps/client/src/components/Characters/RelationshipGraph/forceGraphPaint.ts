import type { Character } from '../../../types'
import { intensityToWidth, roleColor } from './constants'

export interface ForceGraphNode {
  id: string
  name: string
  role: string
  character: Character
  /** 节点半径权重（连接数 + 角色加成） */
  val: number
  x?: number
  y?: number
  z?: number
}

export interface ForceGraphLink {
  source: string | ForceGraphNode
  target: string | ForceGraphNode
  relation_type: string
  intensity: number
  is_dynamic: string
}

export function linkWidthForIntensity(intensity: number) {
  return intensityToWidth(intensity) * 0.75
}

export function linkColorForRole(role: string, alpha = 0.65) {
  const c = roleColor(role)
  return `rgba(${hexToRgb(c.dot)}, ${alpha})`
}

function hexToRgb(hex: string): string {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(x => x + x).join('') : h, 16)
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`
}
