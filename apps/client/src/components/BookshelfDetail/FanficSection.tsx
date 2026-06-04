/**
 * @file 同人设定区域：原著结构化 / 魔改边界 / 切入点。
 */
import React from 'react'

import type { DetailData } from './SectionContent'

const S = {
  label: { fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '16px 0 8px' } as React.CSSProperties,
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14, marginBottom: 10 } as React.CSSProperties,
  text: { fontSize: 13, color: '#111827', lineHeight: 1.6 } as React.CSSProperties,
  muted: { fontSize: 12, color: '#6b7280', lineHeight: 1.5 } as React.CSSProperties,
}

function Title({ children }: { children: React.ReactNode }) {
  return <div style={S.label}>{children}</div>
}

export default function FanficSection({ data }: { data: DetailData }) {
  const e = (data.project.extra || {}) as Record<string, any>
  const fp = e.fanfic_positioning || {}
  const canon = e.fanfic_canon || {}
  const dev = e.fanfic_deviation || {}
  const entry = e.fanfic_entry || {}
  const audit = e.fanfic_audit || {}

  const hasAny = fp.source_work_title || canon.world_summary || dev.divergence_point
  if (!hasAny) {
    return <p style={S.muted}>暂无同人设定数据</p>
  }

  return (
    <>
      <Title>立项</Title>
      <div style={S.card}>
        <p style={S.text}>
          《{fp.source_work_title || '—'}》· {fp.fanfic_trope_label || '—'}
        </p>
        <p style={S.muted}>核心爽感：{fp.core_satisfaction || '—'}</p>
        <p style={S.muted}>读者期待：{fp.fan_expectation || '—'}</p>
        <p style={S.muted}>贴合档位：{fp.canon_fidelity || 'medium'}</p>
      </div>

      {canon.world_summary && (
        <>
          <Title>原著结构化</Title>
          <div style={S.card}>
            <p style={S.text}>{canon.world_summary}</p>
            {(canon.immutable_facts || []).slice(0, 6).map((f: string, i: number) => (
              <p key={i} style={S.muted}>· {f}</p>
            ))}
          </div>
        </>
      )}

      {dev.divergence_point && (
        <>
          <Title>魔改边界</Title>
          <div style={S.card}>
            <p style={S.text}>分歧点：{dev.divergence_point}</p>
            {dev.cp_promise && <p style={S.muted}>CP：{dev.cp_promise}</p>}
            {(dev.forbidden_changes || []).slice(0, 4).map((f: string, i: number) => (
              <p key={i} style={S.muted}>禁改：{f}</p>
            ))}
          </div>
        </>
      )}

      {entry.initial_state_headline && (
        <>
          <Title>切入点</Title>
          <div style={S.card}>
            <p style={S.text}>{entry.initial_state_headline}</p>
            <p style={S.muted}>触发：{entry.trigger_event}</p>
            {entry.entry_chapter_hint && (
              <p style={S.muted}>切入：{entry.entry_chapter_hint}</p>
            )}
          </div>
        </>
      )}

      {audit.opening_verdict && (
        <>
          <Title>质检</Title>
          <div style={S.card}>
            <p style={S.text}>开局：{audit.opening_verdict} · 原著风险 {audit.canon_risk_score}</p>
          </div>
        </>
      )}
    </>
  )
}
