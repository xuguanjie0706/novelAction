/**
 * @file BootstrapTimelineDetail — Bootstrap 生成纪要右侧详情面板
 *
 * 职责：
 * - 空态：提示用户点击左侧步骤
 * - 选中步骤后渲染：步骤标题、时序卡、输出摘要卡、步骤专属内容
 * - 特殊渲染：positioning（立项定位字段）/ consistency（问题列表）/
 *             opening_contract（承诺摘要）
 *
 * @param step            当前选中的步骤状态，null 时显示空态
 * @param positioningData 来自 hook 的立项定位数据（positioning 步骤用）
 * @param insights        生成完成后拉取的洞察数据（consistency / opening_contract 用）
 * @param generationStartMs 生成开始时间戳，用于计算偏移展示
 * @param phase           当前阶段
 * @param projectId       生成完成后的项目 ID
 * @param onNavigate      点击「进入工作台」回调
 * @param onCancel        生成中点击「取消」回调
 * @param errorMsg        当前错误信息
 */
import React from 'react'
import { ChevronRight, MousePointerClick } from 'lucide-react'
import type { StepState, Phase } from './hooks/useBootstrapStream'

// ── 工具 ──────────────────────────────────────────────────────

function fmtDuration(ms: number): string {
  const s = ms / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

function fmtOffset(offsetMs: number): string {
  const s = Math.round(offsetMs / 1000)
  return s < 60 ? `+${s}s` : `+${Math.floor(s / 60)}m ${s % 60}s`
}

// ── 通用卡片 ─────────────────────────────────────────────────

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div style={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 10, padding: '12px 14px', marginBottom: 8 }}>
      {title && (
        <div style={{ fontSize: 10, fontWeight: 700, color: '#5a5a78', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 6 }}>
      <span style={{ fontSize: 11, color: '#5a5a78', width: 80, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 13, color: '#e2e2ec', flex: 1 }}>{value}</span>
    </div>
  )
}

// ── 步骤专属内容 ──────────────────────────────────────────────

/** 立项会议 — 展示 positioning JSON 字段 */
function PositioningContent({ data }: { data: Record<string, any> }) {
  const tropes: string[] = Array.isArray(data.tropes) ? data.tropes : []
  const refs: string[] = Array.isArray(data.reference_works) ? data.reference_works : []
  const taboos: string[] = Array.isArray(data.taboo_lines) ? data.taboo_lines : []

  return (
    <>
      <Card title="定位决策">
        {data.target_audience && <Row label="目标读者" value={data.target_audience} />}
        {data.pace_type && <Row label="节奏类型" value={
          data.pace_type === 'fast' ? '⚡ fast · 番茄式爽快' :
          data.pace_type === 'medium' ? '📘 medium · 起点中速' : '🎨 slow · 文笔流'
        } />}
        {data.emotional_arc && <Row label="感情线占比" value={
          { none: '无', low: 'low · 约10%', medium: 'medium · 约25%', high: 'high · 约40%' }[data.emotional_arc as string] ?? data.emotional_arc
        } />}
        {data.face_slap_pattern && <Row label="打脸频率" value={data.face_slap_pattern} />}
        {refs.length > 0 && <Row label="参照作品" value={refs.join(' · ')} />}
      </Card>

      {(tropes.length > 0 || taboos.length > 0) && (
        <Card title="爽点与红线">
          {tropes.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: '#5a5a78', marginBottom: 4 }}>核心爽点</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {tropes.map((t, i) => (
                  <span key={i} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, border: '1px solid #f59e0b50', color: '#f59e0b', background: '#f59e0b10' }}>
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
          {taboos.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: '#5a5a78', marginBottom: 4 }}>禁忌红线</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {taboos.map((t, i) => (
                  <span key={i} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, border: '1px solid #ef444450', color: '#ef4444', background: '#ef444410' }}>
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {data.selling_point && (
        <Card title="封面卖点">
          <p style={{ fontSize: 14, color: '#e2e2ec', lineHeight: 1.6, fontStyle: 'italic' }}>
            「{data.selling_point}」
          </p>
          {data.hook_test && (
            <p style={{ fontSize: 11, color: '#9999b8', marginTop: 6, lineHeight: 1.5 }}>
              {data.hook_test}
            </p>
          )}
        </Card>
      )}

      {(data.market_risk || data.differentiation_durability) && (
        <Card title="风险评估">
          {data.market_risk && <p style={{ fontSize: 12, color: '#9999b8', lineHeight: 1.6, marginBottom: 6 }}>{data.market_risk}</p>}
          {data.differentiation_durability && <p style={{ fontSize: 12, color: '#9999b8', lineHeight: 1.6 }}>{data.differentiation_durability}</p>}
        </Card>
      )}
    </>
  )
}

/** 一致性扫描 — 展示问题列表 */
function ConsistencyContent({ issues }: { issues: any[] }) {
  if (issues.length === 0) {
    return (
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#22c55e' }}>
          <span style={{ fontSize: 16 }}>✓</span>
          <span style={{ fontSize: 13 }}>未检测到一致性问题，可直接开始写作</span>
        </div>
      </Card>
    )
  }

  const severityColor = (s: string) =>
    s === 'high' || s === 'critical' ? '#ef4444' :
    s === 'medium' ? '#f97316' : '#f59e0b'
  const severityLabel = (s: string) =>
    ({ critical: '严重', high: '严重', medium: '中等', low: '轻微' }[s] ?? s)

  return (
    <>
      <div style={{ marginBottom: 8, fontSize: 12, color: '#9999b8' }}>
        发现 <span style={{ color: '#f97316', fontWeight: 600 }}>{issues.length}</span> 处待确认问题，不影响开始写作，建议进入第3章前处理。
      </div>
      {issues.map((issue: any, i: number) => {
        const text = typeof issue === 'string' ? issue : (issue.description || issue.issue || JSON.stringify(issue))
        const sev = issue.severity ?? (i === 0 ? 'high' : i === 1 ? 'medium' : 'low')
        const color = severityColor(sev)
        return (
          <div key={i} style={{ background: '#1a1a24', border: `1px solid #2a2a3a`, borderLeft: `3px solid ${color}`, borderRadius: 8, padding: '10px 12px', marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: 10, background: `${color}20`, color, padding: '1px 6px', borderRadius: 4 }}>
                {severityLabel(sev)}
              </span>
              <span style={{ fontSize: 13, fontWeight: 500, color: '#e2e2ec' }}>
                {typeof issue === 'object' ? (issue.title ?? `问题 ${i + 1}`) : `问题 ${i + 1}`}
              </span>
            </div>
            <p style={{ fontSize: 11, color: '#9999b8', lineHeight: 1.5 }}>{text}</p>
            {issue.suggestion && (
              <p style={{ fontSize: 11, color: '#f97316', marginTop: 4 }}>▸ {issue.suggestion}</p>
            )}
          </div>
        )
      })}
    </>
  )
}

/** 开局追读承诺 — 展示承诺列表 */
function OpeningContractContent({ data }: { data: Record<string, any> }) {
  const promises: any[] = Array.isArray(data.promises) ? data.promises
    : Array.isArray(data.items) ? data.items
    : data.chapter1_hook ? [{ text: data.chapter1_hook }]
    : []

  return (
    <>
      {data.chapter1_hook && (
        <Card title="第1章核心钩子">
          <p style={{ fontSize: 13, color: '#e2e2ec', lineHeight: 1.6, fontStyle: 'italic' }}>
            「{data.chapter1_hook}」
          </p>
        </Card>
      )}
      {promises.length > 0 && (
        <Card title={`追读承诺清单（${promises.length} 条）`}>
          {promises.map((p: any, i: number) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }}>
              <span style={{
                width: 20, height: 20, borderRadius: 4, flexShrink: 0,
                background: i < 2 ? '#ef4444' : i < 4 ? '#f97316' : '#22c55e',
                color: 'white', fontSize: 10, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                P{typeof p === 'object' && p.priority != null ? p.priority : 5 - Math.min(i, 4)}
              </span>
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 12, color: '#e2e2ec', lineHeight: 1.4 }}>
                  {typeof p === 'string' ? p : (p.text || p.content || JSON.stringify(p))}
                </p>
                {typeof p === 'object' && p.type && (
                  <p style={{ fontSize: 10, color: '#5a5a78', marginTop: 2 }}>{p.type}</p>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
      {promises.length === 0 && !data.chapter1_hook && (
        <Card>
          <p style={{ fontSize: 12, color: '#9999b8' }}>承诺数据已写入数据库，前往工作台的"大纲"页查看完整列表。</p>
        </Card>
      )}
    </>
  )
}

// ── 主组件 ────────────────────────────────────────────────────

interface Insights {
  consistency_issues: any[]
  opening_contract: Record<string, any>
}

interface Props {
  step: StepState | null
  positioningData: Record<string, any> | null
  insights: Insights | null
  generationStartMs: number | null
  phase: Phase
  projectId: string | null
  onNavigate: () => void
  onCancel: () => void
  errorMsg: string
}

/**
 * Bootstrap 生成纪要右侧详情面板。
 * 展示选中步骤的时序信息、输出摘要和步骤专属内容。
 */
export default function BootstrapTimelineDetail({
  step, positioningData, insights, generationStartMs,
  phase, projectId, onNavigate, onCancel, errorMsg,
}: Props) {
  const panelStyle: React.CSSProperties = {
    flex: 1, overflowY: 'auto', background: '#13131a',
    scrollbarWidth: 'thin', scrollbarColor: '#2a2a3a transparent',
  }

  // ── 空态 ───────────────────────────────────────────────────
  if (!step) {
    return (
      <div style={panelStyle}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#5a5a78', gap: 8 }}>
          <MousePointerClick size={32} style={{ opacity: 0.3 }} />
          <span style={{ fontSize: 13 }}>点击左侧步骤，查看详细信息</span>
        </div>
      </div>
    )
  }

  // ── 时序计算 ───────────────────────────────────────────────
  const offsetMs = step.startedAt != null && generationStartMs != null
    ? step.startedAt - generationStartMs : null
  const durationMs = step.startedAt != null && step.completedAt != null
    ? step.completedAt - step.startedAt : null

  return (
    <div style={panelStyle}>
      <div style={{ padding: 24, maxWidth: 680 }}>
        {/* ── 标题区 ──────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #2a2a3a' }}>
          <span style={{ fontSize: 28, lineHeight: 1, flexShrink: 0 }}>{step.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e2e2ec', marginBottom: 4 }}>{step.label}</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#9999b8' }}>
              <span style={{
                fontSize: 10, padding: '1px 8px', borderRadius: 4, fontWeight: 700,
                background: `${step.stepColor}20`, color: step.stepColor, border: `1px solid ${step.stepColor}50`,
              }}>
                {step.stepNum}
              </span>
              <span>{step.desc}</span>
            </div>
          </div>
          {/* 耗时 */}
          {durationMs != null && (
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#e2e2ec', fontVariantNumeric: 'tabular-nums' }}>
                {fmtDuration(durationMs)}
              </div>
              <div style={{ fontSize: 10, color: '#5a5a78' }}>耗时</div>
              {offsetMs != null && (
                <div style={{ fontSize: 11, color: '#5a5a78', marginTop: 2 }}>
                  开始于 {fmtOffset(offsetMs)}
                </div>
              )}
            </div>
          )}
          {/* running 中 */}
          {step.status === 'running' && (
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 13, color: step.stepColor, animation: 'pulse 1.5s infinite' }}>生成中…</div>
            </div>
          )}
        </div>

        {/* ── 错误提示 ─────────────────────────────────────── */}
        {step.status === 'error' && (
          <div style={{ background: '#2a0f0f', border: '1px solid #ef444450', borderRadius: 8, padding: '10px 12px', marginBottom: 12, fontSize: 12, color: '#ef4444' }}>
            ⚠ {step.detail || errorMsg || '该步骤生成失败，请检查后端日志'}
          </div>
        )}

        {/* ── 输出摘要卡（通用）──────────────────────────── */}
        {(step.count != null || step.preview) && (
          <Card title="输出摘要">
            {step.count != null && <Row label="生成数量" value={`${step.count} 条`} />}
            {step.preview && <Row label="内容预览" value={<span style={{ color: '#9999b8' }}>{step.preview}</span>} />}
          </Card>
        )}

        {/* ── 步骤专属内容 ─────────────────────────────────── */}
        {step.key === 'positioning' && positioningData && Object.keys(positioningData).length > 0 && (
          <PositioningContent data={positioningData} />
        )}

        {step.key === 'consistency' && insights && (
          <ConsistencyContent issues={insights.consistency_issues} />
        )}

        {step.key === 'opening_contract' && insights && Object.keys(insights.opening_contract ?? {}).length > 0 && (
          <OpeningContractContent data={insights.opening_contract} />
        )}

        {/* pending 态说明 */}
        {step.status === 'pending' && (
          <Card>
            <p style={{ fontSize: 12, color: '#5a5a78' }}>该步骤尚未开始，等待前序步骤完成后自动触发。</p>
          </Card>
        )}

        {/* ── 完成后操作区 ─────────────────────────────────── */}
        {phase === 'done' && projectId && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #2a2a3a' }}>
            <button
              onClick={onNavigate}
              style={{
                width: '100%', padding: '12px 0', background: '#7c6af7',
                color: 'white', fontWeight: 600, fontSize: 14, borderRadius: 12,
                border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
                justifyContent: 'center', gap: 6, transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = '#6b5ce7')}
              onMouseLeave={e => (e.currentTarget.style.background = '#7c6af7')}
            >
              进入工作台
              <ChevronRight size={16} />
            </button>
          </div>
        )}

        {/* ── 生成中取消按钮 ───────────────────────────────── */}
        {phase === 'generating' && (
          <div style={{ marginTop: 12 }}>
            <button
              onClick={onCancel}
              style={{
                width: '100%', padding: '8px 0', background: 'transparent',
                color: '#5a5a78', fontSize: 12, borderRadius: 8,
                border: '1px solid #2a2a3a', cursor: 'pointer', transition: 'color 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = '#9999b8')}
              onMouseLeave={e => (e.currentTarget.style.color = '#5a5a78')}
            >
              取消生成
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
