/**
 * @file 纪要页：情绪节律图（Step 9.5）与反派行动线（Step 9.8）展示。
 */
import React from 'react'
import type { RecapRegenStep } from '../../hooks/useRecapStepRegen'
import RecapEmptyWithRegen from './RecapEmptyWithRegen'
import type { EmotionArcEntry, VillainArcEntry } from '../../utils/narrativeArcDisplay'
import {
  netBalanceColor,
  netBalanceLabel,
  villainResultColor,
  villainResultLabel,
} from '../../utils/narrativeArcDisplay'

const S = {
  card: {
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: 10,
    padding: '12px 14px',
    marginBottom: 8,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  } as React.CSSProperties,
  label: {
    fontSize: 10,
    fontWeight: 700,
    color: '#9ca3af',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.07em',
    marginBottom: 6,
  } as React.CSSProperties,
  text: { fontSize: 13, color: '#111827', lineHeight: 1.6 } as React.CSSProperties,
  muted: { fontSize: 12, color: '#6b7280', lineHeight: 1.5 } as React.CSSProperties,
  badge: (color: string): React.CSSProperties => ({
    display: 'inline-block',
    fontSize: 11,
    padding: '1px 8px',
    borderRadius: 12,
    border: `1px solid ${color}40`,
    color,
    background: `${color}12`,
    marginLeft: 6,
  }),
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={S.label}>{children}</div>
}

function Card({ children, borderColor }: { children: React.ReactNode; borderColor?: string }) {
  return (
    <div
      style={{
        ...S.card,
        ...(borderColor ? { borderLeftWidth: 3, borderLeftColor: borderColor } : {}),
      }}
    >
      {children}
    </div>
  )
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  if (v == null || v === '') return null
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 5, alignItems: 'baseline' }}>
      <span style={{ fontSize: 11, color: '#9ca3af', width: 72, flexShrink: 0 }}>{k}</span>
      <span style={S.text}>{v}</span>
    </div>
  )
}

interface Props {
  entries: VillainArcEntry[] | EmotionArcEntry[]
  emptyHint: string
  regen?: {
    projectId: string
    step: RecapRegenStep
    onSuccess: () => void | Promise<void>
  }
}

export function VillainArcSection({ entries, emptyHint, regen }: Props) {
  const list = entries as VillainArcEntry[]
  if (list.length === 0) {
    if (regen) {
      return (
        <RecapEmptyWithRegen
          projectId={regen.projectId}
          step={regen.step}
          hint={emptyHint}
          onSuccess={regen.onSuccess}
        />
      )
    }
    return <p style={S.muted}>{emptyHint}</p>
  }

  return (
    <>
      {list.map((v, i) => {
        const title = v.vol_title || `第 ${(v.vol_index ?? i) + 1} 卷`
        const resultColor = villainResultColor(v.vol_result)
        return (
          <Card key={`${v.vol_index ?? i}-${title}`} borderColor={resultColor}>
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
              <strong style={S.text}>{title}</strong>
              {v.villain_name && (
                <span style={{ ...S.muted, marginLeft: 8 }}>{v.villain_name}</span>
              )}
              {v.vol_result && (
                <span style={S.badge(resultColor)}>{villainResultLabel(v.vol_result)}</span>
              )}
            </div>
            <KV k="本卷目标" v={v.vol_goal} />
            <KV k="阻碍" v={v.vol_obstacle} />
            <KV k="关键决策" v={v.vol_key_choice} />
            <KV k="付出代价" v={v.vol_cost} />
            {v.threat_escalation && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
                <SectionTitle>威胁升级</SectionTitle>
                <p style={S.muted}>{v.threat_escalation}</p>
              </div>
            )}
            {v.hidden_move && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
                <SectionTitle>盲区布局</SectionTitle>
                <p style={{ ...S.muted, fontStyle: 'italic' }}>{v.hidden_move}</p>
              </div>
            )}
          </Card>
        )
      })}
    </>
  )
}

export function EmotionArcSection({ entries, emptyHint, regen }: Props) {
  const list = entries as EmotionArcEntry[]
  if (list.length === 0) {
    if (regen) {
      return (
        <RecapEmptyWithRegen
          projectId={regen.projectId}
          step={regen.step}
          hint={emptyHint}
          onSuccess={regen.onSuccess}
        />
      )
    }
    return <p style={S.muted}>{emptyHint}</p>
  }

  return (
    <>
      {list.map((v, i) => {
        const title = v.vol_title || `第 ${(v.vol_index ?? i) + 1} 卷`
        const balanceColor = netBalanceColor(v.net_balance)
        return (
          <Card key={`${v.vol_index ?? i}-${title}`} borderColor={balanceColor}>
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
              <strong style={S.text}>{title}</strong>
              {v.phase && <span style={S.badge('#8b5cf6')}>{v.phase}</span>}
              {v.net_balance && (
                <span style={S.badge(balanceColor)}>{netBalanceLabel(v.net_balance)}</span>
              )}
              {v.dominant_emotion && (
                <span style={{ ...S.muted, marginLeft: 8 }}>{v.dominant_emotion}</span>
              )}
            </div>
            <KV k="情绪收益" v={v.emotional_deposit} />
            <KV k="情绪消耗" v={v.emotional_cost} />
            {v.arc_note && (
              <p style={{ ...S.muted, marginTop: 6, paddingTop: 6, borderTop: '1px solid #f3f4f6' }}>
                总编辑批注：{v.arc_note}
              </p>
            )}
          </Card>
        )
      })}
    </>
  )
}
