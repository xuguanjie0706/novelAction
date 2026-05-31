/**
 * 纪要页：开局承诺（Bootstrap Step 12）。
 */
import React from 'react'
import {
  OPENING_CONTRACT_FIELDS,
  countOpeningContractEntries,
  formatContractDisplayValue,
  hasContractValue,
  priorityColor,
  resolveOpeningContract,
} from '../../utils/openingContractDisplay'
import RecapEmptyWithRegen from './RecapEmptyWithRegen'
import type { DetailData } from './SectionContent'

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
  tiny: { fontSize: 11, color: '#9ca3af' } as React.CSSProperties,
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={S.label}>{children}</div>
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div style={{ ...S.card, ...style }}>{children}</div>
}

interface Props {
  data: DetailData
  projectId: string
  onDataRefresh: () => void | Promise<void>
}

export default function OpeningContractSection({ data, projectId, onDataRefresh }: Props) {
  const oc = resolveOpeningContract(data.insights, data.project.extra)
  const legacyList: unknown[] = Array.isArray(oc.promises)
    ? oc.promises
    : Array.isArray(oc.items)
      ? oc.items
      : Array.isArray(oc.contracts)
        ? oc.contracts
        : []

  const fieldEntries = OPENING_CONTRACT_FIELDS.filter(f => hasContractValue(oc[f.key]))
  const traps = Array.isArray(oc.opening_traps_to_avoid)
    ? oc.opening_traps_to_avoid.filter(hasContractValue)
    : []
  const total = countOpeningContractEntries(oc)

  if (total === 0) {
    return (
      <RecapEmptyWithRegen
        projectId={projectId}
        step="opening_contract"
        hint="暂无开局承诺数据（Bootstrap Step 12 未写入或生成结果为空）"
        onSuccess={onDataRefresh}
      />
    )
  }

  return (
    <>
      {fieldEntries.map(f => {
        const color = priorityColor(f.priority)
        const text = formatContractDisplayValue(oc[f.key])
        return (
          <Card key={f.key} style={{ borderLeftWidth: 3, borderLeftColor: color }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div style={{
                width: 22, height: 22, borderRadius: 5, background: color,
                color: 'white', fontSize: 10, fontWeight: 700, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>P{f.priority}</div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <SectionTitle>{f.label}</SectionTitle>
                <p style={S.text}>{text}</p>
              </div>
            </div>
          </Card>
        )
      })}

      {traps.length > 0 && (
        <Card style={{ borderLeftWidth: 3, borderLeftColor: '#f59e0b' }}>
          <SectionTitle>开局需规避的坑</SectionTitle>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {traps.map((t, i) => (
              <li key={i} style={{ ...S.text, marginBottom: 6 }}>
                {formatContractDisplayValue(t)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {legacyList.map((p, i) => {
        const prio = typeof p === 'object' && p && 'priority' in p
          ? Number((p as { priority?: number }).priority) || (5 - Math.min(i, 4))
          : 5 - Math.min(i, 4)
        const color = priorityColor(prio)
        const text = formatContractDisplayValue(
          typeof p === 'string' ? p : (p as { text?: string; content?: string }),
        )
        const typeLabel = typeof p === 'object' && p && 'type' in p
          ? formatContractDisplayValue((p as { type?: unknown }).type)
          : ''
        return (
          <Card key={`legacy-${i}`}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div style={{
                width: 22, height: 22, borderRadius: 5, background: color,
                color: 'white', fontSize: 10, fontWeight: 700, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>P{prio}</div>
              <div>
                <p style={S.text}>{text}</p>
                {typeLabel ? <p style={{ ...S.tiny, marginTop: 2 }}>{typeLabel}</p> : null}
              </div>
            </div>
          </Card>
        )
      })}
    </>
  )
}
