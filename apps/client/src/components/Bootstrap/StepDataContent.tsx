/**
 * @file StepDataContent — Bootstrap 各步骤生成结果的富内容展示
 *
 * 接收 `useBootstrapStepData` 拉取到的真实 API 数据，按步骤 key 渲染对应卡片。
 * 每个渲染函数均有"最多展示 N 条 + 还有 X 条"的截断逻辑，避免面板过长。
 *
 * 命名约定：
 * - `render*Content` — 接收具体类型数据，返回 JSX
 * - `StepDataContent` — 按 stepKey 分发入口，对外唯一导出
 */
import React from 'react'
import type { StepKey } from './hooks/useBootstrapStream'
import { parseVolumeDirector } from '../../utils/volumeBeatsDisplay'

// ── 通用子组件 ────────────────────────────────────────────────────────────────

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      {title && (
        <div className="mb-3 text-[10px] font-bold uppercase tracking-wider text-gray-400">
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="mb-2 flex gap-2 text-sm last:mb-0">
      <span className="w-20 flex-shrink-0 text-xs text-gray-500">{label}</span>
      <span className="min-w-0 flex-1 text-gray-900">{value}</span>
    </div>
  )
}

function Tag({ children, color = 'gray' }: { children: React.ReactNode; color?: 'gray' | 'amber' | 'red' | 'blue' | 'green' | 'purple' }) {
  const cls: Record<string, string> = {
    gray:   'bg-gray-50 border-gray-200 text-gray-600',
    amber:  'bg-amber-50 border-amber-200 text-amber-800',
    red:    'bg-red-50 border-red-100 text-red-700',
    blue:   'bg-blue-50 border-blue-200 text-blue-800',
    green:  'bg-green-50 border-green-200 text-green-800',
    purple: 'bg-purple-50 border-purple-200 text-purple-800',
  }
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls[color]}`}>
      {children}
    </span>
  )
}

function MoreHint({ remaining, noun = '条' }: { remaining: number; noun?: string }) {
  if (remaining <= 0) return null
  return (
    <p className="mt-2 text-[11px] text-gray-400">还有 {remaining} {noun}，进入工作台查看全部…</p>
  )
}

// ── Step 1：项目 ──────────────────────────────────────────────────────────────

function ProjectContent({ data }: { data: any }) {
  const storyCore = data.story_core ?? {}
  return (
    <>
      <Card title="项目基础">
        <Row label="书名" value={<span className="font-bold text-base">{data.title || '—'}</span>} />
        {data.subtitle && <Row label="副标题" value={<span className="text-gray-600">{data.subtitle}</span>} />}
        {data.genre && <Row label="题材" value={<Tag color="blue">{data.genre}</Tag>} />}
        {data.target_words && (
          <Row
            label="目标字数"
            value={`${(data.target_words / 10000).toFixed(0)} 万字`}
          />
        )}
      </Card>
      {(storyCore.core_conflict || storyCore.protagonist_arc || storyCore.hook) && (
        <Card title="故事核">
          {storyCore.core_conflict && <Row label="核心冲突" value={storyCore.core_conflict} />}
          {storyCore.protagonist_arc && <Row label="主角弧线" value={storyCore.protagonist_arc} />}
          {storyCore.hook && <Row label="情感钩子" value={storyCore.hook} />}
        </Card>
      )}
      {data.logline && (
        <Card title="原始创意">
          <p className="text-sm italic leading-relaxed text-gray-700">「{data.logline}」</p>
        </Card>
      )}
    </>
  )
}

// ── Step 2：境界体系 ──────────────────────────────────────────────────────────

function PowerSystemsContent({ data }: { data: any[] }) {
  const SHOW = 2
  const first = data[0]
  if (!first) return <Card><p className="text-sm text-gray-500">暂无境界体系数据</p></Card>

  const levels: any[] = Array.isArray(first.levels) ? first.levels : []
  const LEVEL_SHOW = 4

  const LEVEL_COLORS = ['#f59e0b', '#06b6d4', '#22c55e', '#a78bfa', '#ef4444', '#f97316', '#ec4899', '#14b8a6', '#8b5cf6']

  return (
    <>
      <Card title={`${first.name}（主体系）`}>
        {first.description && (
          <p className="mb-3 text-sm leading-relaxed text-gray-600">{first.description}</p>
        )}
        {levels.length > 0 && (
          <div className="space-y-0">
            {levels.slice(0, LEVEL_SHOW).map((lv: any, i: number) => (
              <div key={i} className="flex items-start gap-2.5 border-b border-gray-50 py-2 last:border-0">
                <span
                  className="mt-0.5 flex h-5 w-14 flex-shrink-0 items-center justify-center rounded text-[10px] font-bold text-white"
                  style={{ background: LEVEL_COLORS[i % LEVEL_COLORS.length] }}
                >
                  {lv.name ?? `L${i + 1}`}
                </span>
                <div className="min-w-0 flex-1">
                  {lv.description && (
                    <p className="text-xs leading-relaxed text-gray-600">{lv.description}</p>
                  )}
                </div>
              </div>
            ))}
            <MoreHint remaining={levels.length - LEVEL_SHOW} noun="层" />
          </div>
        )}
      </Card>
      {data.length > SHOW && (
        <Card title="其他体系">
          <div className="flex flex-wrap gap-2">
            {data.slice(SHOW).map((ps: any, i: number) => (
              <Tag key={i} color="blue">{ps.name}</Tag>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}

// ── Step 3：势力 ──────────────────────────────────────────────────────────────

const FACTION_RELATION_COLOR: Record<string, 'red' | 'green' | 'blue' | 'gray'> = {
  enemy: 'red', antagonist: 'red',
  ally: 'green', protagonist_side: 'green', friendly: 'green',
  neutral: 'blue',
}

function factionRelColor(faction: any): 'red' | 'green' | 'blue' | 'gray' {
  const rel = (faction.relationship_to_protagonist ?? faction.faction_type ?? '').toLowerCase()
  for (const [k, v] of Object.entries(FACTION_RELATION_COLOR)) {
    if (rel.includes(k)) return v
  }
  return 'gray'
}

function FactionsContent({ data }: { data: any[] }) {
  const SHOW = 4
  return (
    <Card title={`势力总览 · ${data.length} 个`}>
      {data.slice(0, SHOW).map((f: any, i: number) => (
        <div key={i} className="flex items-start gap-2 border-b border-gray-50 py-2.5 last:border-0">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900">{f.name}</span>
              <Tag color={factionRelColor(f)}>
                {f.relationship_to_protagonist ?? f.faction_type ?? '未知'}
              </Tag>
            </div>
            {f.description && (
              <p className="line-clamp-2 text-xs leading-relaxed text-gray-500">{f.description}</p>
            )}
          </div>
        </div>
      ))}
      <MoreHint remaining={data.length - SHOW} noun="个势力" />
    </Card>
  )
}

// ── Step 4：故事线 ────────────────────────────────────────────────────────────

function StorylinesContent({ data }: { data: any[] }) {
  const mainLines = data.filter((s: any) => s.storyline_type === 'main' || s.is_main)
  const subLines  = data.filter((s: any) => s.storyline_type !== 'main' && !s.is_main)
  const SHOW_SUB  = 3

  return (
    <>
      {mainLines.length > 0 && (
        <Card title="主线">
          {mainLines.map((s: any, i: number) => (
            <div key={i} className={i > 0 ? 'mt-3 border-t border-gray-50 pt-3' : ''}>
              <p className="text-sm font-semibold text-gray-900">{s.title ?? s.name}</p>
              {s.description && (
                <p className="mt-1 text-xs leading-relaxed text-gray-500">{s.description}</p>
              )}
              {s.hook && (
                <p className="mt-1 text-xs text-amber-700">
                  <span className="font-medium">追读动力：</span>{s.hook}
                </p>
              )}
            </div>
          ))}
        </Card>
      )}
      {subLines.length > 0 && (
        <Card title={`支线 · ${subLines.length} 条`}>
          {subLines.slice(0, SHOW_SUB).map((s: any, i: number) => (
            <div key={i} className="flex items-start gap-2 border-b border-gray-50 py-2 last:border-0">
              <Tag color="purple">{s.storyline_type ?? '支线'}</Tag>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900">{s.title ?? s.name}</p>
                {s.description && (
                  <p className="mt-0.5 line-clamp-1 text-xs text-gray-500">{s.description}</p>
                )}
              </div>
            </div>
          ))}
          <MoreHint remaining={subLines.length - SHOW_SUB} noun="条支线" />
        </Card>
      )}
    </>
  )
}

// ── Step 5：人物 ──────────────────────────────────────────────────────────────

function CharactersContent({ data }: { data: any[] }) {
  const SHOW = 5
  return (
    <Card title={`人物档案 · 共 ${data.length} 人`}>
      {data.slice(0, SHOW).map((c: any, i: number) => (
        <div key={i} className="flex items-start gap-2.5 border-b border-gray-50 py-2.5 last:border-0">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm font-semibold text-gray-900">{c.name}</span>
              {c.role && <Tag color={c.role === 'protagonist' ? 'amber' : c.role === 'antagonist' ? 'red' : 'gray'}>{c.role}</Tag>}
              {c.current_realm && (
                <span className="ml-auto flex-shrink-0 text-[11px] text-gray-400">{c.current_realm}</span>
              )}
            </div>
            {c.background && (
              <p className="line-clamp-2 text-xs leading-relaxed text-gray-500">{c.background}</p>
            )}
          </div>
        </div>
      ))}
      <MoreHint remaining={data.length - SHOW} noun="人" />
    </Card>
  )
}

// ── Step 6：技能 ──────────────────────────────────────────────────────────────

function SkillsContent({ data }: { data: any[] }) {
  const SHOW = 5
  return (
    <Card title={`功法 / 技能 · 共 ${data.length} 条`}>
      {data.slice(0, SHOW).map((s: any, i: number) => (
        <div key={i} className="flex items-start gap-2 border-b border-gray-50 py-2 last:border-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm font-semibold text-gray-900">{s.name}</span>
              {s.skill_type && <Tag color="gray">{s.skill_type}</Tag>}
            </div>
            {s.description && (
              <p className="mt-0.5 line-clamp-1 text-xs text-gray-500">{s.description}</p>
            )}
            {(s.known_by_names ?? s.practitioners ?? []).length > 0 && (
              <p className="mt-0.5 text-[11px] text-blue-600">
                持有者：{(s.known_by_names ?? s.practitioners).slice(0, 3).join(' · ')}
              </p>
            )}
          </div>
        </div>
      ))}
      <MoreHint remaining={data.length - SHOW} noun="条" />
    </Card>
  )
}

// ── Step 7：道具 ──────────────────────────────────────────────────────────────

const RARITY_COLOR: Record<string, 'gray' | 'green' | 'blue' | 'purple' | 'amber' | 'red'> = {
  common: 'gray', uncommon: 'green', rare: 'blue',
  epic: 'purple', legendary: 'amber', mythic: 'red',
  普通: 'gray', 稀有: 'blue', 史诗: 'purple', 传说: 'amber', 神话: 'red',
}

function ItemsContent({ data }: { data: any[] }) {
  const SHOW = 5
  return (
    <Card title={`道具 / 法宝 · 共 ${data.length} 件`}>
      {data.slice(0, SHOW).map((item: any, i: number) => (
        <div key={i} className="flex items-start gap-2 border-b border-gray-50 py-2 last:border-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm font-semibold text-gray-900">{item.name}</span>
              {item.rarity && (
                <Tag color={RARITY_COLOR[item.rarity] ?? 'gray'}>{item.rarity}</Tag>
              )}
            </div>
            {item.description && (
              <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-gray-500">{item.description}</p>
            )}
          </div>
        </div>
      ))}
      <MoreHint remaining={data.length - SHOW} noun="件" />
    </Card>
  )
}

// ── Step 8：世界设定 ──────────────────────────────────────────────────────────

function SettingsContent({ data }: { data: any[] }) {
  // 按 category 分组
  const groups: Record<string, any[]> = {}
  for (const s of data) {
    const cat = s.category ?? s.extra?.category ?? '其他'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(s)
  }
  const entries = Object.entries(groups)
  const SHOW_GROUPS = 3
  const SHOW_ITEMS = 1

  return (
    <>
      <Card title={`世界设定卡 · 共 ${data.length} 张`}>
        <div className="flex flex-wrap gap-2">
          {entries.map(([cat, items]) => (
            <Tag key={cat} color="blue">{cat} ×{items.length}</Tag>
          ))}
        </div>
      </Card>
      {entries.slice(0, SHOW_GROUPS).map(([cat, items]) => (
        <Card key={cat} title={cat}>
          {items.slice(0, SHOW_ITEMS).map((s: any, i: number) => (
            <div key={i}>
              <p className="text-sm font-medium text-gray-900">{s.title ?? s.name}</p>
              {s.content && (
                <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-gray-500">{s.content}</p>
              )}
            </div>
          ))}
          {items.length > SHOW_ITEMS && (
            <p className="mt-2 text-[11px] text-gray-400">还有 {items.length - SHOW_ITEMS} 张…</p>
          )}
        </Card>
      ))}
    </>
  )
}

// ── Step 9：卷级骨架 ──────────────────────────────────────────────────────────

const PHASE_LABEL: Record<string, string> = {
  opening:   '开局期',
  rising:    '起飞期',
  turning:   '转折期',
  dark_hour: '至暗期',
  climax:    '高潮期',
  ending:    '收束期',
}

const PHASE_COLOR: Record<string, string> = {
  opening:   'background:#fef3c7;color:#92400e',
  rising:    'background:#dbeafe;color:#1e40af',
  turning:   'background:#ede9fe;color:#5b21b6',
  dark_hour: 'background:#f3f4f6;color:#374151',
  climax:    'background:#fee2e2;color:#991b1b',
  ending:    'background:#dcfce7;color:#166534',
}

function VolumesContent({ data }: { data: any[] }) {
  const vols = data.filter((n: any) => n.node_type === 'volume' || !n.node_type)
  const SHOW = 3
  return (
    <Card title={`全书骨架 · 共 ${vols.length} 卷`}>
      {vols.slice(0, SHOW).map((v: any, i: number) => {
        const phase = v.phase ?? v.extra?.phase ?? ''
        const phaseStyle = PHASE_COLOR[phase] ?? 'background:#f3f4f6;color:#374151'
        const d = parseVolumeDirector(v)
        return (
          <div key={i} className="mb-3 rounded-lg border border-gray-100 bg-gray-50 p-3 last:mb-0">
            <div className="mb-1.5 flex items-center justify-between gap-2 flex-wrap">
              <span className="text-sm font-bold text-gray-900">{v.title}</span>
              {phase && (
                <span
                  className="flex-shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold"
                  style={Object.fromEntries(phaseStyle.split(';').map((s: string) => s.split(':')))}
                >
                  {PHASE_LABEL[phase] ?? phase}
                </span>
              )}
              {d.beatHighlights.length > 0 && (
                <span className="text-[10px] text-orange-600">{d.beatHighlights.length} 燃点</span>
              )}
            </div>
            {(d.protagonistRealmRange || d.volumeBoss || d.volumeBossRealm) && (
              <p className="mb-1.5 text-[11px] leading-snug text-indigo-800">
                {d.protagonistRealmRange ? <span className="font-medium">主角：{d.protagonistRealmRange}</span> : null}
                {d.protagonistRealmRange && (d.volumeBoss || d.volumeBossRealm) ? (
                  <span className="mx-1 text-gray-400">·</span>
                ) : null}
                {(d.volumeBoss || d.volumeBossRealm) && (
                  <span className="text-gray-600">
                    BOSS：{d.volumeBoss || '—'}
                    {d.volumeBossRealm ? `（${d.volumeBossRealm}）` : ''}
                  </span>
                )}
              </p>
            )}
            {v.summary && (
              <p className="line-clamp-2 text-xs leading-relaxed text-gray-500">{v.summary}</p>
            )}
            {d.climaxSummary && (
              <p className="mt-1 text-[11px] text-red-700 line-clamp-1">
                高潮{d.volumeClimax?.chapter_hint ? `·第${d.volumeClimax.chapter_hint}章` : ''}：{d.climaxSummary}
              </p>
            )}
            {(d.legacyReaderHook || d.nextVolumeHook) && (
              <p className="mt-1 text-[11px] text-violet-700 line-clamp-1">
                {d.legacyReaderHook ? `追读：${d.legacyReaderHook}` : `下卷：${d.nextVolumeHook}`}
              </p>
            )}
          </div>
        )
      })}
      <MoreHint remaining={vols.length - SHOW} noun="卷" />
    </Card>
  )
}

// ── Step 11：人物关系 ─────────────────────────────────────────────────────────

const REL_ICONS: Record<string, string> = {
  romance: '❤️', rival: '⚡', mentor: '🤝', enemy: '⚔️',
  friend: '😊', family: '👨‍👩‍👧', ally: '🛡️',
}

function RelationsContent({ data }: { data: any[] }) {
  const SHOW = 6
  return (
    <Card title={`人物关系 · 共 ${data.length} 对`}>
      {data.slice(0, SHOW).map((r: any, i: number) => {
        const relType = r.relationship_type ?? r.relation_type ?? ''
        const icon = REL_ICONS[relType] ?? '↔'
        return (
          <div key={i} className="flex items-start gap-2 border-b border-gray-50 py-2 last:border-0">
            <span className="mt-0.5 flex-shrink-0 text-base">{icon}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1 text-sm">
                <span className="font-semibold">{r.from_name ?? r.character_a_name ?? '—'}</span>
                <span className="text-gray-400">→</span>
                <span className="font-semibold">{r.to_name ?? r.character_b_name ?? '—'}</span>
                {relType && <Tag color="gray">{relType}</Tag>}
              </div>
              {r.description && (
                <p className="mt-0.5 line-clamp-1 text-xs text-gray-500">{r.description}</p>
              )}
            </div>
          </div>
        )
      })}
      <MoreHint remaining={data.length - SHOW} noun="对" />
    </Card>
  )
}

// ── Step 12.5：第一卷章纲 ─────────────────────────────────────────────────────


// ── 主入口 ────────────────────────────────────────────────────────────────────

interface Props {
  stepKey: StepKey
  data: unknown
}

/**
 * 根据 stepKey 分发到对应的内容渲染函数。
 * 当 data 为 null/undefined 或格式不符时返回 null，由调用方降级到"X 条"摘要。
 */
export default function StepDataContent({ stepKey, data }: Props) {
  if (data == null) return null

  const arr = Array.isArray(data) ? data : null

  switch (stepKey) {
    case 'project':
      return <ProjectContent data={data as any} />

    case 'power_systems':
      return arr && arr.length > 0 ? <PowerSystemsContent data={arr} /> : null

    case 'factions':
      return arr && arr.length > 0 ? <FactionsContent data={arr} /> : null

    case 'storylines':
      return arr && arr.length > 0 ? <StorylinesContent data={arr} /> : null

    case 'characters':
      return arr && arr.length > 0 ? <CharactersContent data={arr} /> : null

    case 'skills':
      return arr && arr.length > 0 ? <SkillsContent data={arr} /> : null

    case 'items':
      return arr && arr.length > 0 ? <ItemsContent data={arr} /> : null

    case 'settings':
      return arr && arr.length > 0 ? <SettingsContent data={arr} /> : null

    case 'volumes':
      return arr && arr.length > 0 ? <VolumesContent data={arr} /> : null

    case 'relations':
      return arr && arr.length > 0 ? <RelationsContent data={arr} /> : null

    default:
      return null
  }
}
