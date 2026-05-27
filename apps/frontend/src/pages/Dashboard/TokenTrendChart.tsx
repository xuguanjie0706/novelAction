/**
 * 近 7 天 Token 消耗趋势图（SVG 折线面积图 + 调用量柱状图）。
 *
 * 不依赖外部图表库，纯 SVG 实现以避免引入 echarts/recharts 增加 bundle size。
 * 数据来自 DashboardStats.token_trend（7 条按日分桶数据）。
 */
import { Card, Typography } from 'antd'
import type { TokenTrendItem } from '../../types/dashboard'

const { Text } = Typography

interface Props {
  data: TokenTrendItem[]
  loading?: boolean
}

const W = 560
const H = 140
const PAD_L = 48
const PAD_R = 12
const PAD_T = 12
const PAD_B = 28

function formatK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

export default function TokenTrendChart({ data, loading }: Props) {
  if (loading || !data || data.length === 0) {
    return (
      <Card loading={loading} style={{ borderRadius: 10 }}>
        <div style={{ height: 180 }} />
      </Card>
    )
  }

  const maxTokens = Math.max(...data.map((d) => d.tokens), 1)
  const maxCalls = Math.max(...data.map((d) => d.calls), 1)
  const innerW = W - PAD_L - PAD_R
  const innerH = H - PAD_T - PAD_B
  const n = data.length

  const xOf = (i: number) => PAD_L + (i / (n - 1)) * innerW
  const yOfToken = (v: number) => PAD_T + innerH - (v / maxTokens) * innerH
  const yOfCall = (v: number) => PAD_T + innerH - (v / maxCalls) * innerH

  // 折线面积路径（token）
  const tokenPoints = data.map((d, i) => [xOf(i), yOfToken(d.tokens)] as [number, number])
  const areaPath =
    `M${tokenPoints[0][0]},${tokenPoints[0][1]}` +
    tokenPoints
      .slice(1)
      .map(([x, y]) => `L${x},${y}`)
      .join('') +
    `L${tokenPoints[n - 1][0]},${PAD_T + innerH}L${tokenPoints[0][0]},${PAD_T + innerH}Z`

  const linePath =
    `M${tokenPoints[0][0]},${tokenPoints[0][1]}` +
    tokenPoints
      .slice(1)
      .map(([x, y]) => `L${x},${y}`)
      .join('')

  // 调用量折线（calls）
  const callPoints = data.map((d, i) => [xOf(i), yOfCall(d.calls)] as [number, number])
  const callPath =
    `M${callPoints[0][0]},${callPoints[0][1]}` +
    callPoints
      .slice(1)
      .map(([x, y]) => `L${x},${y}`)
      .join('')

  // Y 轴刻度
  const yTicks = [0, 0.5, 1].map((r) => ({
    y: PAD_T + innerH - r * innerH,
    label: formatK(Math.round(r * maxTokens)),
  }))

  return (
    <Card
      style={{ borderRadius: 10 }}
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>近 7 天 Token 趋势</span>
          <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
            <span>
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: '#6366f1',
                  marginRight: 4,
                }}
              />
              Token 消耗
            </span>
            <span>
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: '#10b981',
                  marginRight: 4,
                }}
              />
              调用次数
            </span>
          </div>
        </div>
      }
      bodyStyle={{ padding: '8px 16px 16px' }}
    >
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="tokenGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Y 轴刻度线 */}
        {yTicks.map(({ y, label }) => (
          <g key={label}>
            <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#f0f0f0" strokeWidth={1} />
            <text x={PAD_L - 4} y={y + 4} textAnchor="end" fontSize={9} fill="#aaa">
              {label}
            </text>
          </g>
        ))}

        {/* X 轴日期标签 */}
        {data.map((d, i) => (
          <text
            key={d.date}
            x={xOf(i)}
            y={PAD_T + innerH + 16}
            textAnchor="middle"
            fontSize={9}
            fill="#aaa"
          >
            {d.date.slice(5)}
          </text>
        ))}

        {/* Token 面积 */}
        <path d={areaPath} fill="url(#tokenGrad)" />
        {/* Token 折线 */}
        <path d={linePath} fill="none" stroke="#6366f1" strokeWidth={2} strokeLinejoin="round" />

        {/* 调用量折线 */}
        <path d={callPath} fill="none" stroke="#10b981" strokeWidth={1.5} strokeDasharray="4 2" strokeLinejoin="round" />

        {/* 数据点 */}
        {tokenPoints.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={3} fill="#6366f1" />
        ))}
      </svg>

      {/* 合计文字 */}
      <div style={{ display: 'flex', gap: 24, marginTop: 4 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            7 日 Token 合计
          </Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#6366f1' }}>
            {formatK(data.reduce((s, d) => s + d.tokens, 0))}
          </div>
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            7 日调用合计
          </Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#10b981' }}>
            {data.reduce((s, d) => s + d.calls, 0).toLocaleString()} 次
          </div>
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            7 日错误合计
          </Text>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#ff4d4f' }}>
            {data.reduce((s, d) => s + d.errors, 0).toLocaleString()} 次
          </div>
        </div>
      </div>
    </Card>
  )
}
