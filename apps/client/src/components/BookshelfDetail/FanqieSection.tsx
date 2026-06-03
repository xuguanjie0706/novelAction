/**
 * @file 番茄爽点区域：聚合展示打脸地图 / 金手指 / 爽点节奏图。
 *
 * 数据来源：Project.extra 中的番茄专线产物（face_slap_map / golden_finger / rhythm_map）。
 * 番茄线不生成通用的故事线/情绪节律/反派行动线，这三样才是番茄写手最常翻的规划物，
 * 故单列一个专属视图（仅番茄书在 BookshelfDetail 侧边栏可见）。
 */
import React from 'react'

import type { DetailData } from './SectionContent'

const S = {
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '16px 0 8px' } as React.CSSProperties,
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14, marginBottom: 10 } as React.CSSProperties,
  text: { fontSize: 13, color: '#111827', lineHeight: 1.6 } as React.CSSProperties,
  muted: { fontSize: 12, color: '#6b7280', lineHeight: 1.5 } as React.CSSProperties,
  tiny: { fontSize: 11, color: '#9ca3af' } as React.CSSProperties,
}

function Title({ children }: { children: React.ReactNode }) {
  return <div style={S.label}>{children}</div>
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 5, alignItems: 'baseline' }}>
      <span style={{ fontSize: 11, color: '#9ca3af', width: 80, flexShrink: 0 }}>{k}</span>
      <span style={S.text}>{v}</span>
    </div>
  )
}

/** 番茄章节爽点标签 → 中文 + 颜色。 */
const FANQIE_TAG_META: Record<string, { label: string; color: string }> = {
  big_win: { label: '大爽点', color: '#ef4444' },
  small_win: { label: '小爽点', color: '#f59e0b' },
  progress: { label: '推进', color: '#3b82f6' },
  transition: { label: '过渡', color: '#9ca3af' },
}

export default function FanqieSection({ data }: { data: DetailData }) {
  const e = (data.project.extra || {}) as Record<string, any>
  const fsm = e.face_slap_map || {}
  const gf = e.golden_finger || {}
  const rhythm = e.rhythm_map || {}
  const tags: any[] = Array.isArray(rhythm.chapter_tags) ? rhythm.chapter_tags : []
  const warnings: any[] = Array.isArray(rhythm.dry_spell_warnings) ? rhythm.dry_spell_warnings : []
  const stages: any[] = Array.isArray(gf.upgrade_stages) ? gf.upgrade_stages : []
  const slaps: any[] = Array.isArray(fsm.slap_targets) ? fsm.slap_targets
    : Array.isArray(fsm.targets) ? fsm.targets : []

  const hasAny = tags.length || stages.length || slaps.length || fsm.slap_rhythm || gf.name
  if (!hasAny) {
    return <p style={S.muted}>暂无番茄爽点数据（番茄立项产物未生成或为空）</p>
  }

  return (
    <>
      {(gf.name || stages.length > 0) && (
        <>
          <Title>金手指</Title>
          <div style={S.card}>
            {gf.name && <KV k="名称" v={gf.name} />}
            {gf.core_mechanism && <KV k="核心机制" v={gf.core_mechanism} />}
            {gf.growth_logic && <KV k="成长逻辑" v={gf.growth_logic} />}
            {stages.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={S.tiny}>升级阶段（{stages.length}）</div>
                {stages.map((st: any, i: number) => (
                  <p key={i} style={{ ...S.muted, marginTop: 4 }}>
                    {i + 1}. {typeof st === 'string' ? st : (st.stage || st.name || st.desc || JSON.stringify(st))}
                  </p>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {(fsm.slap_rhythm || slaps.length > 0 || fsm.escalation_path) && (
        <>
          <Title>打脸地图</Title>
          <div style={S.card}>
            {fsm.slap_rhythm && <KV k="打脸节奏" v={fsm.slap_rhythm} />}
            {fsm.first_slap_chapter && <KV k="首次打脸" v={`第 ${fsm.first_slap_chapter} 章前`} />}
            {fsm.escalation_path && <KV k="升级路径" v={fsm.escalation_path} />}
            {slaps.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={S.tiny}>打脸对象（{slaps.length}）</div>
                {slaps.map((s: any, i: number) => (
                  <p key={i} style={{ ...S.muted, marginTop: 4 }}>
                    {typeof s === 'string' ? s : (s.target || s.name || s.who || JSON.stringify(s))}
                    {s && s.scene && <span style={S.tiny}> — {s.scene}</span>}
                  </p>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {tags.length > 0 && (
        <>
          <Title>爽点节奏图（前 {tags.length} 章）</Title>
          {warnings.length > 0 && (
            <div style={{ ...S.card, borderColor: '#fca5a5', background: '#fef2f2' }}>
              <div style={{ ...S.tiny, color: '#dc2626', marginBottom: 4 }}>⚠️ 节奏预警</div>
              {warnings.map((w: any, i: number) => (
                <p key={i} style={{ ...S.muted, color: '#b91c1c' }}>{String(w)}</p>
              ))}
            </div>
          )}
          <div style={S.card}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {tags.map((t: any, i: number) => {
                const meta = FANQIE_TAG_META[String(t.type)] || { label: String(t.type || '?'), color: '#9ca3af' }
                return (
                  <span
                    key={i}
                    title={`第${t.ch}章 ${meta.label}${t.note ? '：' + t.note : ''}`}
                    style={{
                      fontSize: 10, padding: '2px 6px', borderRadius: 6,
                      background: meta.color + '22', color: meta.color,
                      border: `1px solid ${meta.color}55`, whiteSpace: 'nowrap',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {t.ch}·{meta.label}
                  </span>
                )
              })}
            </div>
          </div>
        </>
      )}
    </>
  )
}
