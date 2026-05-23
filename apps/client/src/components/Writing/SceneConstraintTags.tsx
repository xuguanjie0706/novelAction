/**
 * @file SceneConstraintTags.tsx — 场景约束标签组件
 *
 * 在场景卡片底部展示由 chapter_ingredients 服务生成的约束标签：
 *   - 故事线推进（MUST/可选）
 *   - 债务标记（红/黄）
 *   - 伏笔操作（LAY/HINT/RESOLVE）
 *   - 势力地盘着色
 *   - 技能/法宝聚光灯
 *   - 写后核验结果（绿/红打勾）
 *   - 结构预警
 *
 * 设计原则：紧凑展示，不撑大卡片；关键信息 tooltip 展开。
 */

import { CheckCircle2, XCircle, AlertTriangle, BookOpen, Swords, Package, Landmark } from 'lucide-react'
import clsx from 'clsx'
import type {
  SceneAssetCard,
  SceneChecklistResult,
  SceneDebtFlag,
  SceneFactionColor,
  SceneForeshadowOp,
  SceneStorylineMove,
  SceneStructuralWarning,
} from '../../types'

interface Props {
  storylineMoves?: SceneStorylineMove[] | null
  debtFlags?: SceneDebtFlag[] | null
  foreshadowOps?: SceneForeshadowOp[] | null
  factionColor?: SceneFactionColor | null
  assetSpotlight?: SceneAssetCard[] | null
  structuralWarnings?: SceneStructuralWarning[] | null
  checklistResult?: SceneChecklistResult | null
}

/** 单个约束标签（小药丸样式）。 */
function Tag({
  label,
  color,
  title,
}: {
  label: string
  color: 'red' | 'yellow' | 'blue' | 'green' | 'purple' | 'gray'
  title?: string
}) {
  const colorCls = {
    red:    'bg-red-50 text-red-600 border-red-200',
    yellow: 'bg-amber-50 text-amber-700 border-amber-200',
    blue:   'bg-blue-50 text-blue-600 border-blue-200',
    green:  'bg-emerald-50 text-emerald-600 border-emerald-200',
    purple: 'bg-purple-50 text-purple-600 border-purple-200',
    gray:   'bg-novel-panel text-novel-ink-faint border-novel-border',
  }[color]

  return (
    <span
      className={clsx('inline-flex items-center text-[9px] px-1.5 py-0.5 rounded border truncate max-w-[120px]', colorCls)}
      title={title}
    >
      {label}
    </span>
  )
}

/**
 * 场景约束标签组——在场景卡片底部展示所有规划时写入的约束标记。
 *
 * @param props 各类约束数组，均为可选；无约束时不渲染。
 */
export function SceneConstraintTags({
  storylineMoves,
  debtFlags,
  foreshadowOps,
  factionColor,
  assetSpotlight,
  structuralWarnings,
  checklistResult,
}: Props) {
  const tags: React.ReactNode[] = []

  // ① 债务标记（最高优先级，红色显示）
  const criticalDebts = debtFlags?.filter(d => d.severity === 'critical') ?? []
  const warnDebts = debtFlags?.filter(d => d.severity === 'warning') ?? []
  criticalDebts.forEach(d => {
    const label = d.debt_type === 'payoff' ? `🔴 还债` :
                  d.debt_type === 'storyline_gap' ? `🔴 线断档` :
                  d.debt_type === 'promise_due' ? `🔴 承诺到期` : `🔴 ${d.debt_type}`
    tags.push(<Tag key={`debt-c-${d.debt_type}`} label={label} color="red" title={d.description} />)
  })
  warnDebts.forEach(d => {
    const label = d.debt_type === 'promise_due' ? `⚠ 承诺临期` : `⚠ ${d.debt_type}`
    tags.push(<Tag key={`debt-w-${d.debt_type}`} label={label} color="yellow" title={d.description} />)
  })

  // ② 故事线推进指令
  storylineMoves?.forEach(m => {
    const prefix = m.must_advance ? '[MUST]' : ''
    const label = `${prefix}${m.name}`
    const color = m.must_advance ? 'red' : 'blue'
    const title = m.suggested_beat
      ? `${m.line_type}，断档${m.gap_chapters}章 → ${m.suggested_beat}`
      : `${m.line_type}，断档${m.gap_chapters}章`
    tags.push(<Tag key={`sl-${m.storyline_id}`} label={label} color={color} title={title} />)
  })

  // ③ 伏笔操作
  foreshadowOps?.forEach(op => {
    const opLabel = { lay: '埋', hint: 'HINT', resolve: '回收' }[op.op] ?? op.op.toUpperCase()
    const label = `${opLabel}「${op.title}」`
    const color = op.op === 'resolve' ? 'green' : op.op === 'lay' ? 'purple' : 'blue'
    const overdue = op.is_overdue ? '【逾期】' : ''
    tags.push(
      <Tag
        key={`fw-${op.foreshadow_id}`}
        label={label}
        color={op.is_overdue ? 'red' : color}
        title={`${overdue}${op.suggested_method}`}
      />
    )
  })

  // ④ 势力/地盘着色
  if (factionColor) {
    tags.push(
      <Tag
        key="faction"
        label={`🏛 ${factionColor.name}`}
        color="gray"
        title={`${factionColor.atmosphere} · NPC态度：${factionColor.npc_default_attitude}`}
      />
    )
  }

  // ⑤ 技能/法宝
  assetSpotlight?.slice(0, 2).forEach(a => {
    const icon = a.asset_type === 'skill' ? '⚔' : '📦'
    tags.push(
      <Tag
        key={`asset-${a.asset_id}`}
        label={`${icon}${a.name}`}
        color="purple"
        title={a.key_effect || a.description}
      />
    )
  })

  // ⑥ 结构预警
  structuralWarnings?.forEach((w, i) => {
    tags.push(
      <Tag key={`warn-${i}`} label={`⚠ ${w.code}`} color="yellow" title={w.msg} />
    )
  })

  // ⑦ 核验结果（写完后回填）
  if (checklistResult) {
    const score = checklistResult.score ?? 0
    const allOk = checklistResult.storyline_ok && checklistResult.foreshadow_ok && checklistResult.debt_cleared
    tags.push(
      <span
        key="checklist"
        className={clsx(
          'inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border',
          allOk ? 'bg-emerald-50 text-emerald-600 border-emerald-200'
                : 'bg-amber-50 text-amber-700 border-amber-200',
        )}
        title={`满足度 ${Math.round(score * 100)}%\n${checklistResult.notes}`}
      >
        {allOk ? <CheckCircle2 size={8} /> : <XCircle size={8} />}
        {allOk ? '约束满足' : `${Math.round(score * 100)}%`}
      </span>
    )
  }

  if (tags.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1 mt-1.5 pt-1.5 border-t border-novel-border/40">
      {tags}
    </div>
  )
}
