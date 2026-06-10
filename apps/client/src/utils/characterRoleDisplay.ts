/**
 * @file 人物 role 归一化 — 兼容大白文 Bootstrap 写入的中文标签（主角/反派/打脸对象）。
 */
import { ROLE_META, type RoleFilter } from '../pages/Characters/shared/constants'

export type CanonicalRole = Exclude<RoleFilter, 'all'>

const DIRECT: Record<string, CanonicalRole> = {
  protagonist: 'protagonist',
  antagonist: 'antagonist',
  supporting: 'supporting',
  neutral: 'neutral',
  主角: 'protagonist',
  男主: 'protagonist',
  反派: 'antagonist',
  女主: 'supporting',
  配角: 'supporting',
  中立: 'neutral',
}

/** 将任意 role 字符串映射为列表分组用的 canonical role。 */
export function canonicalCharacterRole(role: string | null | undefined): CanonicalRole {
  const raw = (role ?? '').trim()
  if (!raw) return 'supporting'
  if (DIRECT[raw]) return DIRECT[raw]
  const lower = raw.toLowerCase()
  if (raw.includes('打脸') || lower.includes('boss') || raw.includes('压迫')) return 'antagonist'
  if (raw.includes('主角') || raw.includes('男主')) return 'protagonist'
  if (raw.includes('反派')) return 'antagonist'
  return 'supporting'
}

/** 侧栏/详情展示用角色标签（优先 dabai 原始标签，否则 ROLE_META）。 */
export function characterRoleLabel(
  role: string | null | undefined,
  extra?: Record<string, unknown> | null,
): string {
  const dabaiLabel = extra?.dabai_role_label
  if (typeof dabaiLabel === 'string' && dabaiLabel.trim()) return dabaiLabel.trim()
  const raw = (role ?? '').trim()
  if (raw && !DIRECT[raw] && !['protagonist', 'antagonist', 'supporting', 'neutral'].includes(raw)) {
    return raw
  }
  const canon = canonicalCharacterRole(raw)
  return ROLE_META[canon]?.label ?? raw ?? '未知'
}

export function roleMetaForCharacter(
  role: string | null | undefined,
  extra?: Record<string, unknown> | null,
) {
  const canon = canonicalCharacterRole(role)
  const meta = ROLE_META[canon]
  const label = characterRoleLabel(role, extra)
  return { ...meta, label, canonical: canon }
}
