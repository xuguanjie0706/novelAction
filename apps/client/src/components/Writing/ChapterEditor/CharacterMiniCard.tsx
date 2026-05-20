/**
 * CharacterMiniCard.tsx — 复盘侧栏人物迷你卡片
 *
 * 职责：折叠/展开展示单个人物的境界、位置、状态、动机、技能等信息。
 * 无 store 依赖，纯展示组件（本地 expand 状态除外）。
 */
import React, { useState } from 'react'
import clsx from 'clsx'
import { ChevronDown, MapPin } from 'lucide-react'
import type { Character } from '../../../types'
import { ROLE_BADGE } from './constants'

// ─── InfoRow ─────────────────────────────────────────────────────────────────

/**
 * 单行 label + value 展示，用于人物扩展信息区域。
 *
 * @param label - 标签文字（宽度固定 w-8）
 * @param value - 正文值
 * @param highlight - 为 true 时使用 novel-accent 颜色强调
 */
function InfoRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-[10px] text-novel-ink-faint shrink-0 w-8">{label}</span>
      <span className={clsx(
        'text-[10px] leading-relaxed',
        highlight ? 'text-novel-accent font-medium' : 'text-novel-ink',
      )}>{value}</span>
    </div>
  )
}

// ─── CharacterMiniCard ────────────────────────────────────────────────────────

/**
 * 折叠/展开式人物迷你卡片。
 *
 * 收起时展示头像/首字母、姓名、角色标签、动机摘要；
 * 展开时追加境界、位置、状态、性格、弧线、阵营、技能列表。
 *
 * @param character - Character ORM 对象（需含 role / name / current_realm 等字段）
 */
export default function CharacterMiniCard({ character }: { character: Character }) {
  const [expanded, setExpanded] = useState(false)
  const badge = ROLE_BADGE[character.role]
  return (
    <div className="rounded-novel border border-novel-border bg-novel-card overflow-hidden">
      <button type="button" onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-novel-panel transition-novel text-left">
        {/* 头像 or 首字母 */}
        {character.avatar_url ? (
          <img src={character.avatar_url} alt="" className="w-6 h-6 rounded-full object-cover shrink-0" />
        ) : (
          <div className="w-6 h-6 rounded-full bg-novel-shell flex items-center justify-center shrink-0">
            <span className="text-[10px] text-novel-ink-muted font-semibold">{character.name[0]}</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-xs font-medium text-novel-ink truncate">{character.name}</span>
            <span className={clsx('text-[10px] px-1 py-0.5 rounded font-medium shrink-0', badge.cls)}>
              {badge.label}
            </span>
          </div>
          {character.motivation && !expanded && (
            <p className="text-[10px] text-novel-ink-muted truncate">{character.motivation}</p>
          )}
        </div>
        <ChevronDown size={11} className={clsx(
          'shrink-0 text-novel-ink-faint transition-transform duration-150',
          expanded && 'rotate-180',
        )} />
      </button>

      {expanded && (
        <div className="px-3 pb-2.5 pt-2 border-t border-novel-border space-y-1.5">
          {character.current_realm    && <InfoRow label="境界" value={character.current_realm} highlight />}
          {character.current_location && <InfoRow label="位置" value={character.current_location} highlight />}
          {character.current_status && character.current_status !== 'alive' && (
            <InfoRow label="状态" value={character.current_status} highlight />
          )}
          {character.motivation  && <InfoRow label="动机" value={character.motivation} />}
          {character.personality && <InfoRow label="性格" value={character.personality} />}
          {character.arc         && <InfoRow label="弧线" value={character.arc} />}
          {character.faction     && <InfoRow label="阵营" value={character.faction} />}
          {character.known_skills && (character.known_skills as any[]).length > 0 && (
            <InfoRow label="技能"
              value={(character.known_skills as any[])
                .slice(0, 4)
                .map(s => typeof s === 'string' ? s : s.skill_name || '')
                .filter(Boolean)
                .join('、')} />
          )}
        </div>
      )}
    </div>
  )
}
