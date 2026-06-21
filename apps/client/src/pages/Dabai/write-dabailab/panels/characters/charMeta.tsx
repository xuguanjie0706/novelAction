/**
 * 人物面板共享元数据与展示组件。
 * 职责：把自由文本的 role 归类为「作家视角」的人物组（主角/感情线/反派/导师·盟友/配角），
 * 提供配色、态度色、资产徽标，以及 Chip / SectionCard / FieldRow 三个表现层小组件。
 * 禁止在此文件写数据请求或业务副作用——纯展示与纯函数。
 */
import type { ReactNode } from 'react'
import clsx from 'clsx'
import { fmtVal } from '../../detailFormat'
import type { DabaiLabAsset, DabaiLabRelation } from '../../../../../types/dabaiLab'

export type DabaiChar = Record<string, unknown>

/** 人物组定义（顺序即左栏分组展示顺序）。 */
export interface RoleGroup {
  key: string
  /** 分组标题（作家熟悉的说法）。 */
  label: string
  /** 一句话说明这组人在故事里的位置。 */
  hint: string
}

export const ROLE_GROUPS: RoleGroup[] = [
  { key: 'lead', label: '主角', hint: '故事的视角与命运中心' },
  { key: 'love', label: '感情线', hint: '情感锚点 · 关系推进' },
  { key: 'foe', label: '反派 · 宿敌', hint: '压迫与打脸的来源' },
  { key: 'ally', label: '导师 · 盟友', hint: '助力 · 资源 · 引路人' },
  { key: 'support', label: '配角 · 工具人', hint: '推动情节的次要角色' },
]

/** 每组的强调色（色条 / 圆点 / 实心头像 / 标签）。tailwind 需要字面量，故整段映射。 */
export const GROUP_ACCENT: Record<string, { bar: string; dot: string; solid: string; chip: string; quote: string }> = {
  lead: { bar: 'bg-rose-400', dot: 'bg-rose-400', solid: 'bg-rose-500', chip: 'text-rose-600', quote: 'border-rose-400' },
  love: { bar: 'bg-pink-300', dot: 'bg-pink-400', solid: 'bg-pink-500', chip: 'text-pink-600', quote: 'border-pink-400' },
  foe: { bar: 'bg-red-400', dot: 'bg-red-500', solid: 'bg-red-500', chip: 'text-red-600', quote: 'border-red-400' },
  ally: { bar: 'bg-emerald-300', dot: 'bg-emerald-400', solid: 'bg-emerald-500', chip: 'text-emerald-700', quote: 'border-emerald-400' },
  support: { bar: 'bg-slate-300', dot: 'bg-slate-300', solid: 'bg-slate-400', chip: 'text-slate-500', quote: 'border-slate-300' },
}

/** 自由文本 role → 人物组。优先级有意为先反派、再感情、再导师，避免「女主/师妹」错分。 */
export function classifyRole(role: string): string {
  const r = role || ''
  if (/反派|宿敌|打脸|魔头|魔门|大?boss/i.test(r)) return 'foe'
  if (/(^|[^男])主(角|公)|男主/.test(r) && !/对手|敌/.test(r)) return 'lead'
  if (/女主|感情|红颜|恋|情人|道侣|师妹/.test(r)) return 'love'
  if (/导师|师父|师傅|掌门|长老|盟友|贵人|引路|师姐|师兄|宗主/.test(r)) return 'ally'
  if (/敌|对手/.test(r)) return 'foe'
  return 'support'
}

/** 对主角的态度配色。 */
export function attitudeClass(attitude: string | null | undefined): string {
  const a = attitude ?? ''
  if (/敌对|仇|宿敌/.test(a)) return 'bg-rose-50 text-rose-600'
  if (/臣服|效忠|盟友|追随/.test(a)) return 'bg-emerald-50 text-emerald-700'
  if (/暧昧|爱慕|倾心/.test(a)) return 'bg-pink-50 text-pink-600'
  if (/忌惮|提防|轻视/.test(a)) return 'bg-amber-50 text-amber-700'
  return 'bg-gray-100 text-gray-500'
}

export const KIND_LABELS: Record<string, string> = {
  golden_finger: '金手指', skill: '功法', item: '道具',
}
export const KIND_BADGE: Record<string, string> = {
  golden_finger: 'bg-amber-50 text-amber-700 ring-amber-200/60',
  skill: 'bg-sky-50 text-sky-600 ring-sky-200/60',
  item: 'bg-emerald-50 text-emerald-700 ring-emerald-200/60',
}
export const STATUS_LABELS: Record<string, string> = {
  active: '持有中', consumed: '已消耗', lost: '已遗失',
}

/** 取人物字段并格式化为字符串（空值返回空串）。 */
export function field(c: DabaiChar, key: string): string {
  return fmtVal(c[key])
}

/** 取人物展示名。 */
export function charName(c: DabaiChar): string {
  return field(c, 'name') || '未命名'
}

/** 是否主角（作家视角 lead 组）。 */
export function isProtagonist(c: DabaiChar): boolean {
  return classifyRole(field(c, 'role')) === 'lead'
}

/** 写作期当前境界章号（复盘回写 project.meta）。 */
export function resolveRealmChapter(meta?: Record<string, unknown> | null): number | null {
  if (!meta) return null
  const ch = meta.protagonist_realm_chapter
  if (typeof ch === 'number' && Number.isFinite(ch)) return ch
  if (typeof ch === 'string' && ch.trim()) {
    const n = Number(ch)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/**
 * 人物档案展示用境界：主角优先读复盘回写的 meta/extra.current_realm，
 * 非主角仍用 bootstrap 的 start_realm。
 */
export function resolveDisplayRealm(
  c: DabaiChar,
  meta?: Record<string, unknown> | null,
): string {
  const start = field(c, 'start_realm')
  if (!isProtagonist(c)) return start
  const fromMeta = meta ? field(meta as DabaiChar, 'protagonist_realm') : ''
  const extra = (c.extra && typeof c.extra === 'object' ? c.extra : null) as Record<string, unknown> | null
  const fromExtra = extra ? fmtVal(extra.current_realm) : ''
  return fromMeta || fromExtra || start
}

// ── 成长路线（按章聚合的变化轨迹）─────────────────────────────

export interface GrowthEvent {
  /** 章号；null 表示开局 / 手动。 */
  chapter: number | null
  kind: 'realm' | 'asset' | 'relation'
  text: string
}

/**
 * 由资产获得/状态变化 + 关系态度轨迹 + 起始境界，合成一条按章排序的成长路线。
 * 这是写作期可核对的「这个人一路怎么变强/变心」的连续性账本。
 */
export function buildGrowth(
  startRealm: string,
  assets: DabaiLabAsset[],
  relation: DabaiLabRelation | null,
  currentRealm?: string | null,
  currentRealmChapter?: number | null,
): GrowthEvent[] {
  const ev: GrowthEvent[] = []
  if (startRealm) ev.push({ chapter: 0, kind: 'realm', text: `起始境界 · ${startRealm}` })
  if (currentRealm && currentRealm !== startRealm) {
    ev.push({
      chapter: currentRealmChapter ?? null,
      kind: 'realm',
      text: `当前境界 · ${currentRealm}`,
    })
  }
  for (const a of assets) {
    const k = KIND_LABELS[a.kind] ?? a.kind
    ev.push({ chapter: a.acquired_chapter, kind: 'asset', text: `获得${k} · ${a.name}` })
    if (a.status !== 'active' && a.status_chapter != null) {
      ev.push({ chapter: a.status_chapter, kind: 'asset', text: `${a.name} ${STATUS_LABELS[a.status] ?? a.status}` })
    }
  }
  for (const h of relation?.history ?? []) {
    if (h.chapter == null) continue
    ev.push({ chapter: h.chapter, kind: 'relation', text: `态度转为「${h.attitude}」${h.reason ? `（${h.reason}）` : ''}` })
  }
  return ev.sort((a, b) => (a.chapter ?? -1) - (b.chapter ?? -1))
}

// ── 表现层小组件 ───────────────────────────────────────────────

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium', className)}>
      {children}
    </span>
  )
}

/** 一个可在瀑布流中独立流动的档案区块（铺平展开，不再藏在标签后）。 */
export interface DossierSection {
  key: string
  title: string
  icon?: ReactNode
  body: ReactNode
}

/** 轻量区块卡：小标题（可带图标）+ 内容，用于瀑布流分列铺排。 */
export function SectionCard({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <h4 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-gray-400">
        {icon}{title}
      </h4>
      {children}
    </section>
  )
}

/** 轻量区块：小标题 + 内容，无卡片边框（编辑器式留白分区，替代厚重卡片）。 */
export function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 text-[11px] font-medium tracking-wide text-gray-400">{title}</div>
      {children}
    </div>
  )
}

/** 取人设/功能首句作为一句话「本质」标语（避免编造，仅截取已有文本）。 */
export function tagline(c: DabaiChar): string {
  const src = field(c, 'persona') || field(c, 'function')
  if (!src) return ''
  const head = src.split(/[。；，;,]/)[0]
  return head.length > 28 ? `${head.slice(0, 28)}…` : head
}

/** 「标签 + 值」横排；值为空时返回 null。 */
export function FieldRow({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className="flex gap-3 text-sm leading-relaxed">
      <dt className="w-14 shrink-0 text-gray-400">{label}</dt>
      <dd className="flex-1 text-gray-700">{value}</dd>
    </div>
  )
}
