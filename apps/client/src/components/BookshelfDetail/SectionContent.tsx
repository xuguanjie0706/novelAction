/**
 * @file SectionContent — 生成纪要各区域的富内容渲染器
 *
 * 每个区域从真实数据库数据渲染，不依赖 SSE 临时数据。
 * 数据通过 DetailData bundle 传入，父组件负责 API 拉取。
 *
 * @param sectionId  当前选中区域标识
 * @param data       所有已拉取的项目数据
 */
import React from 'react'
import type {
  Project, Character, CharacterRelationship, Faction, PowerSystem,
  Skill, Item, StoryLine, WorldSetting, OutlineNode,
} from '../../types'
import { VolumeDirectorCard } from '../Outline/VolumeDirectorView'
import OpeningContractSection from './OpeningContractSection'
import { EmotionArcSection, VillainArcSection } from './NarrativeArcSections'
import { resolveEmotionArc, resolveVillainArc } from '../../utils/narrativeArcDisplay'

// ── 数据 bundle ───────────────────────────────────────────────

export interface DetailData {
  project: Project
  insights: {
    consistency_issues: any[]
    opening_contract: Record<string, any>
    positioning: Record<string, any>
  }
  characters: Character[]
  relations: CharacterRelationship[]
  factions: Faction[]
  powerSystems: PowerSystem[]
  skills: Skill[]
  items: Item[]
  storylines: StoryLine[]
  settings: WorldSetting[]
  volumes: OutlineNode[]
}

// ── 通用样式（浅色主题，与 AppLayout #FAF8F4 保持一致）────────

const S = {
  card: {
    background: '#ffffff', border: '1px solid #e5e7eb',
    borderRadius: 10, padding: '12px 14px', marginBottom: 8,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  } as React.CSSProperties,
  label: {
    fontSize: 10, fontWeight: 700, color: '#9ca3af',
    textTransform: 'uppercase' as const, letterSpacing: '0.07em', marginBottom: 6,
  } as React.CSSProperties,
  badge: (color: string): React.CSSProperties => ({
    display: 'inline-block', fontSize: 11, padding: '1px 8px',
    borderRadius: 12, border: `1px solid ${color}40`,
    color, background: `${color}12`, margin: '2px',
  }),
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 } as React.CSSProperties,
  grid3: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 } as React.CSSProperties,
  text: { fontSize: 13, color: '#111827', lineHeight: 1.6 } as React.CSSProperties,
  muted: { fontSize: 12, color: '#6b7280', lineHeight: 1.5 } as React.CSSProperties,
  tiny: { fontSize: 11, color: '#9ca3af' } as React.CSSProperties,
}

// ── 小工具组件 ────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={S.label}>{children}</div>
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div style={{ ...S.card, ...style }}>{children}</div>
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 5, alignItems: 'baseline' }}>
      <span style={{ fontSize: 11, color: '#9ca3af', width: 80, flexShrink: 0 }}>{k}</span>
      <span style={S.text}>{v}</span>
    </div>
  )
}

// ── 区域渲染：立项概览 ────────────────────────────────────────

function OverviewSection({ data }: { data: DetailData }) {
  const pos = data.insights.positioning ?? data.project.extra?.positioning ?? {}
  const tropes: string[] = Array.isArray(pos.tropes) ? pos.tropes : []
  const taboos: string[] = Array.isArray(pos.taboo_lines) ? pos.taboo_lines : []
  const refs: string[] = Array.isArray(pos.reference_works) ? pos.reference_works : []

  return (
    <>
      <Card>
        <KV k="书名" v={<strong>{data.project.title}</strong>} />
        {data.project.genre && <KV k="题材" v={data.project.genre} />}
        {data.project.logline && <KV k="创意" v={<span style={S.muted}>{data.project.logline}</span>} />}
        {data.project.target_words && (
          <KV k="目标字数" v={`${(data.project.target_words / 10000).toFixed(0)} 万字`} />
        )}
      </Card>

      {Object.keys(pos).length > 0 && (
        <>
          <Card>
            <SectionTitle>立项定位</SectionTitle>
            {pos.target_audience && <KV k="目标读者" v={pos.target_audience} />}
            {pos.pace_type && <KV k="节奏类型" v={
              pos.pace_type === 'fast' ? '⚡ fast · 番茄式爽快' :
              pos.pace_type === 'medium' ? '📘 medium · 起点中速' : '🎨 slow · 文笔流'
            } />}
            {pos.emotional_arc && <KV k="感情线" v={
              { none: '无', low: '约 10%', medium: '约 25%', high: '约 40%' }[pos.emotional_arc as string] ?? pos.emotional_arc
            } />}
            {pos.face_slap_pattern && <KV k="打脸频率" v={pos.face_slap_pattern} />}
            {refs.length > 0 && <KV k="参照作品" v={refs.join(' · ')} />}
          </Card>

          {(tropes.length > 0 || taboos.length > 0) && (
            <Card>
              {tropes.length > 0 && (
                <div style={{ marginBottom: taboos.length > 0 ? 10 : 0 }}>
                  <SectionTitle>核心爽点</SectionTitle>
                  {tropes.map((t, i) => <span key={i} style={S.badge('#f59e0b')}>{t}</span>)}
                </div>
              )}
              {taboos.length > 0 && (
                <div>
                  <SectionTitle>禁忌红线</SectionTitle>
                  {taboos.map((t, i) => <span key={i} style={S.badge('#ef4444')}>{t}</span>)}
                </div>
              )}
            </Card>
          )}

          {pos.selling_point && (
            <Card style={{ borderColor: '#f59e0b60', borderLeftWidth: 3, borderLeftColor: '#f59e0b' }}>
              <SectionTitle>封面卖点</SectionTitle>
              <p style={{ ...S.text, fontStyle: 'italic' }}>「{pos.selling_point}」</p>
              {pos.market_risk && (
                <p style={{ ...S.muted, marginTop: 8, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
                  {pos.market_risk}
                </p>
              )}
            </Card>
          )}
        </>
      )}
    </>
  )
}

// ── 区域渲染：境界体系 ────────────────────────────────────────

function PowerSection({ data }: { data: DetailData }) {
  const LEVEL_COLORS = ['#06b6d4','#22c55e','#a78bfa','#f59e0b','#f97316','#ef4444','#ec4899','#8b5cf6','#14b8a6']
  return (
    <>
      {data.powerSystems.length === 0 && <p style={S.muted}>暂无境界体系数据</p>}
      {data.powerSystems.map(ps => (
        <Card key={ps.id}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <strong style={S.text}>{ps.name}</strong>
            <span style={S.badge('#06b6d4')}>{ps.system_type}</span>
            {ps.levels.length > 0 && <span style={{ ...S.tiny, marginLeft: 'auto' }}>{ps.levels.length} 阶</span>}
          </div>
          {ps.description && <p style={{ ...S.muted, marginBottom: 10 }}>{ps.description}</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {ps.levels.map((lv, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '6px 10px', background: '#f9fafb', borderRadius: 6,
                borderLeft: `3px solid ${LEVEL_COLORS[i % LEVEL_COLORS.length]}`,
              }}>
                <span style={{ fontSize: 10, color: '#9ca3af', width: 22, textAlign: 'center', flexShrink: 0 }}>
                  {lv.rank ?? i + 1}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827', minWidth: 80 }}>{lv.name}</span>
                {lv.description && (
                  <span style={{ fontSize: 11, color: '#6b7280', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {lv.description}
                  </span>
                )}
              </div>
            ))}
          </div>
          {(ps.protagonist_current_rank != null || ps.breakthrough_condition) && (
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #f3f4f6' }}>
              {ps.protagonist_current_rank != null && (
                <KV k="主角当前" v={ps.levels[ps.protagonist_current_rank - 1]?.name ?? `第${ps.protagonist_current_rank}阶`} />
              )}
              {ps.breakthrough_condition && <KV k="突破条件" v={ps.breakthrough_condition} />}
            </div>
          )}
        </Card>
      ))}
    </>
  )
}

// ── 区域渲染：势力格局 ────────────────────────────────────────

const ALIGN_CFG = {
  protagonist: { label: '友方', color: '#22c55e' },
  antagonist:  { label: '敌方', color: '#ef4444' },
  neutral:     { label: '中立', color: '#f59e0b' },
  unknown:     { label: '未知', color: '#5a5a78' },
}

function FactionsSection({ data }: { data: DetailData }) {
  return (
    <>
      {data.factions.length === 0 && <p style={S.muted}>暂无势力数据</p>}
      <div style={S.grid2}>
        {data.factions.map(f => {
          const align = ALIGN_CFG[f.alignment] ?? ALIGN_CFG.unknown
          return (
            <Card key={f.id} style={{ borderLeft: `3px solid ${align.color}`, marginBottom: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <strong style={{ ...S.text, fontSize: 14 }}>{f.name}</strong>
                <span style={S.badge(align.color)}>{align.label}</span>
                <span style={{ ...S.tiny, marginLeft: 'auto' }}>{f.faction_type}</span>
              </div>
              {f.strength_level && <KV k="实力" v={f.strength_level} />}
              {f.territory && <KV k="地盘" v={f.territory} />}
              {f.top_power && <KV k="顶战力" v={f.top_power} />}
              {f.description && <p style={{ ...S.muted, marginTop: 6 }}>{f.description}</p>}
              {f.goals && (
                <p style={{ ...S.tiny, marginTop: 6, borderTop: '1px solid #f3f4f6', paddingTop: 6 }}>
                  目标：{f.goals}
                </p>
              )}
            </Card>
          )
        })}
      </div>
    </>
  )
}

// ── 区域渲染：故事线 ──────────────────────────────────────────

const SL_COLORS: Record<string, string> = {
  main: '#a78bfa', romance: '#ec4899', growth: '#22c55e',
  faction: '#06b6d4', mystery: '#f97316', sub: '#8b5cf6', antagonist: '#ef4444',
}

function StorylinesSection({ data }: { data: DetailData }) {
  const charById = Object.fromEntries(data.characters.map(c => [c.id, c.name]))
  return (
    <>
      {data.storylines.length === 0 && <p style={S.muted}>暂无故事线数据</p>}
      {data.storylines.map(sl => {
        const color = SL_COLORS[sl.line_type] ?? '#7c6af7'
        return (
          <Card key={sl.id} style={{ borderLeft: `3px solid ${color}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <strong style={S.text}>{sl.name}</strong>
              <span style={S.badge(color)}>{sl.line_type}</span>
              <span style={S.badge(sl.status === 'active' ? '#22c55e' : '#5a5a78')}>{sl.status}</span>
            </div>
            {sl.description && <p style={S.muted}>{sl.description}</p>}
            {sl.core_conflict && (
              <p style={{ ...S.tiny, marginTop: 6 }}>核心冲突：{sl.core_conflict}</p>
            )}
            {sl.related_character_ids.length > 0 && (
              <p style={{ ...S.tiny, marginTop: 4 }}>
                关联人物：{sl.related_character_ids.map(id => charById[id] ?? id).join('、')}
              </p>
            )}
          </Card>
        )
      })}
    </>
  )
}

// ── 区域渲染：人物库 ──────────────────────────────────────────

const ROLE_COLORS: Record<string, [string, string]> = {
  protagonist: ['#7c6af7', '#a78bfa'],
  antagonist:  ['#ef4444', '#f97316'],
  supporting:  ['#22c55e', '#06b6d4'],
  neutral:     ['#5a5a78', '#9999b8'],
}

function CharactersSection({ data }: { data: DetailData }) {
  return (
    <>
      {data.characters.length === 0 && <p style={S.muted}>暂无人物数据</p>}
      <div style={S.grid2}>
        {data.characters.map(c => {
          const [c1, c2] = ROLE_COLORS[c.role] ?? ROLE_COLORS.neutral
          return (
            <Card key={c.id} style={{ marginBottom: 0 }}>
              <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                  background: `linear-gradient(135deg, ${c1}, ${c2})`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700, color: 'white',
                }}>{c.name[0]}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <strong style={{ ...S.text, fontSize: 14 }}>{c.name}</strong>
                    <span style={S.badge(c1)}>
                      {{ protagonist: '主角', antagonist: '反派', supporting: '配角', neutral: '中立' }[c.role] ?? c.role}
                    </span>
                  </div>
                  {c.current_realm && (
                    <span style={{ ...S.tiny, marginTop: 2, display: 'block' }}>{c.current_realm}</span>
                  )}
                </div>
              </div>
              {c.personality && <p style={{ ...S.muted, fontSize: 12 }}>{c.personality}</p>}
              {(c.strengths.length > 0 || c.special_traits.length > 0) && (
                <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                  {[...c.special_traits.slice(0, 2), ...c.strengths.slice(0, 1)].map((t, i) => (
                    <span key={i} style={{ ...S.tiny, background: '#f3f4f6', color: '#374151', padding: '1px 6px', borderRadius: 4 }}>{t}</span>
                  ))}
                </div>
              )}
              {c.motivation && (
                <p style={{ ...S.tiny, marginTop: 6, paddingTop: 6, borderTop: '1px solid #f3f4f6' }}>
                  动机：{c.motivation}
                </p>
              )}
            </Card>
          )
        })}
      </div>
    </>
  )
}

// ── 区域渲染：技能功法 ────────────────────────────────────────

const GRADE_COLORS: Record<string, string> = {
  divine: '#f59e0b', supreme: '#ef4444', saint: '#a78bfa',
  profound: '#8b5cf6', sky: '#06b6d4', earth: '#22c55e', mortal: '#5a5a78',
}

function SkillsSection({ data }: { data: DetailData }) {
  const charById = Object.fromEntries(data.characters.map(c => [c.id, c.name]))
  return (
    <>
      {data.skills.length === 0 && <p style={S.muted}>暂无技能数据</p>}
      {data.skills.map(sk => {
        const gc = GRADE_COLORS[sk.grade] ?? '#5a5a78'
        return (
          <Card key={sk.id}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <strong style={S.text}>{sk.name}</strong>
              <span style={S.badge(gc)}>{sk.grade}</span>
              <span style={S.badge('#6b7280')}>{sk.skill_type}</span>
              {sk.level_required && <span style={{ ...S.tiny, marginLeft: 'auto' }}>需：{sk.level_required}</span>}
            </div>
            {sk.description && <p style={S.muted}>{sk.description}</p>}
            {sk.effects && <p style={{ ...S.tiny, marginTop: 4 }}>效果：{sk.effects}</p>}
            {sk.mastered_by_character_ids.length > 0 && (
              <p style={{ ...S.tiny, marginTop: 4 }}>
                掌握者：{sk.mastered_by_character_ids.map(id => charById[id] ?? id).join('、')}
              </p>
            )}
          </Card>
        )
      })}
    </>
  )
}

// ── 区域渲染：道具法宝 ────────────────────────────────────────

const RARITY_COLORS: Record<string, string> = {
  mythic: '#f59e0b', legendary: '#ef4444', unique: '#ec4899',
  epic: '#a78bfa', rare: '#06b6d4', uncommon: '#22c55e', common: '#5a5a78',
}

function ItemsSection({ data }: { data: DetailData }) {
  const charById = Object.fromEntries(data.characters.map(c => [c.id, c.name]))
  return (
    <>
      {data.items.length === 0 && <p style={S.muted}>暂无道具数据</p>}
      {data.items.map(item => {
        const rc = RARITY_COLORS[item.rarity] ?? '#5a5a78'
        const owner = item.current_owner_id ? charById[item.current_owner_id] : null
        return (
          <Card key={item.id}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <strong style={S.text}>{item.name}</strong>
              <span style={S.badge(rc)}>{item.rarity}</span>
              <span style={S.badge('#6b7280')}>{item.item_type}</span>
              {owner && <span style={{ ...S.tiny, marginLeft: 'auto' }}>持有：{owner}</span>}
            </div>
            {item.description && <p style={S.muted}>{item.description}</p>}
            {item.effects && <p style={{ ...S.tiny, marginTop: 4 }}>效果：{item.effects}</p>}
            {item.story_significance && (
              <p style={{ ...S.tiny, marginTop: 4, color: '#7c3aed' }}>
                ✦ {item.story_significance}
              </p>
            )}
          </Card>
        )
      })}
    </>
  )
}

// ── 区域渲染：世界设定 ────────────────────────────────────────

function SettingsSection({ data }: { data: DetailData }) {
  const groups = data.settings.reduce((acc, s) => {
    const cat = s.extra?.category ?? '其他'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {} as Record<string, WorldSetting[]>)

  return (
    <>
      {data.settings.length === 0 && <p style={S.muted}>暂无世界设定数据</p>}
      {Object.entries(groups).map(([cat, items]) => (
        <div key={cat} style={{ marginBottom: 16 }}>
          <SectionTitle>{cat}</SectionTitle>
          {items.map(s => (
            <Card key={s.id}>
              <strong style={{ ...S.text, display: 'block', marginBottom: 4 }}>{s.title}</strong>
              {s.content && (
                <p style={S.muted}>{s.content.length > 200 ? s.content.slice(0, 200) + '…' : s.content}</p>
              )}
            </Card>
          ))}
        </div>
      ))}
    </>
  )
}

// ── 区域渲染：卷级结构 ────────────────────────────────────────

function VolumesSection({ data }: { data: DetailData }) {
  const hasProtagonistRealm = data.volumes.some(
    v => Boolean(v.extra?.protagonist_realm_start || v.extra?.protagonist_realm_end),
  )
  return (
    <>
      {data.volumes.length === 0 && <p style={S.muted}>暂无卷级数据</p>}
      {data.volumes.length > 0 && !hasProtagonistRealm && (
        <p style={{ ...S.muted, marginBottom: 12, padding: '10px 12px', background: '#fffbeb', borderRadius: 8, border: '1px solid #fde68a' }}>
          本卷尚未写入主角境界区间。请刷新页面（系统会按境界体系自动补全）；若仍为空，请确认已生成「境界体系」后重新运行 Bootstrap Step 9。
        </p>
      )}
      {data.volumes.map((vol, i) => {
        const chapterCount = vol.children?.filter(n => n.node_type === 'chapter_plan').length
          ?? vol.children?.reduce((s, arc) => s + (arc.children?.length ?? 0), 0) ?? 0
        return (
          <Card key={vol.id}>
            <VolumeDirectorCard vol={vol} index={i} chapterCount={chapterCount} variant="inline" />
          </Card>
        )
      })}
    </>
  )
}

// ── 区域渲染：一致性扫描 ──────────────────────────────────────

const SEV_CFG: Record<string, { label: string; color: string }> = {
  critical: { label: '严重', color: '#ef4444' },
  high:     { label: '严重', color: '#ef4444' },
  medium:   { label: '中等', color: '#f97316' },
  low:      { label: '轻微', color: '#f59e0b' },
}

function ConsistencySection({ data }: { data: DetailData }) {
  const issues = data.insights.consistency_issues ?? []
  return (
    <>
      {issues.length === 0 ? (
        <Card style={{ borderLeftWidth: 3, borderLeftColor: '#16a34a' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#16a34a' }}>
            <span>✓</span>
            <span style={S.text}>未检测到一致性问题，可直接开始写作</span>
          </div>
        </Card>
      ) : (
        <>
          <p style={{ ...S.muted, marginBottom: 10 }}>
            发现 <strong style={{ color: '#f97316' }}>{issues.length}</strong> 处待确认问题
          </p>
          {issues.map((issue: any, i) => {
            const sev = issue.severity ?? (i === 0 ? 'high' : i === 1 ? 'medium' : 'low')
            const { label, color } = SEV_CFG[sev] ?? SEV_CFG.low
            const title = typeof issue === 'object' ? (issue.title ?? issue.category ?? `问题 ${i + 1}`) : `问题 ${i + 1}`
            const desc = typeof issue === 'string' ? issue : (issue.description ?? issue.issue ?? '')
            return (
              <Card key={i} style={{ borderLeft: `3px solid ${color}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <span style={{ ...S.badge(color), fontSize: 10 }}>{label}</span>
                  <strong style={{ ...S.text, fontSize: 13 }}>{title}</strong>
                </div>
                {desc && <p style={S.muted}>{desc}</p>}
                {issue.suggestion && (
                  <p style={{ ...S.tiny, marginTop: 6, color: '#f97316' }}>▸ {issue.suggestion}</p>
                )}
              </Card>
            )
          })}
        </>
      )}
    </>
  )
}

// ── 主导出 ────────────────────────────────────────────────────

interface Props {
  sectionId: string
  data: DetailData
  projectId: string
  onDataRefresh: () => void | Promise<void>
}

/**
 * 根据 sectionId 渲染对应区域的富内容。
 * 所有数据来自真实 API 拉取，无 mock。
 */
export default function SectionContent({ sectionId, data, projectId, onDataRefresh }: Props) {
  const regenBase = { projectId, onSuccess: onDataRefresh }
  switch (sectionId) {
    case 'overview':     return <OverviewSection data={data} />
    case 'power':        return <PowerSection data={data} />
    case 'factions':     return <FactionsSection data={data} />
    case 'storylines':   return <StorylinesSection data={data} />
    case 'characters':   return <CharactersSection data={data} />
    case 'skills':       return <SkillsSection data={data} />
    case 'items':        return <ItemsSection data={data} />
    case 'settings':     return <SettingsSection data={data} />
    case 'volumes':      return <VolumesSection data={data} />
    case 'emotion_arc':  return (
      <EmotionArcSection
        entries={resolveEmotionArc(data.project.extra)}
        emptyHint="暂无情绪节律数据（Bootstrap Step 9.5 未写入或生成结果为空）"
        regen={{ ...regenBase, step: 'emotion_arc' }}
      />
    )
    case 'villain_arc':  return (
      <VillainArcSection
        entries={resolveVillainArc(data.project.extra)}
        emptyHint="暂无反派行动线数据（Bootstrap Step 9.8 未写入或生成结果为空）"
        regen={{ ...regenBase, step: 'villain_arc' }}
      />
    )
    case 'contract':     return (
      <OpeningContractSection data={data} projectId={projectId} onDataRefresh={onDataRefresh} />
    )
    case 'consistency':  return <ConsistencySection data={data} />
    default:             return <p style={S.muted}>选择左侧区域查看内容</p>
  }
}
