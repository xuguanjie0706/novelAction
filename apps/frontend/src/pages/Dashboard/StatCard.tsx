/**
 * 通用 KPI 指标卡片组件。
 *
 * @param title      指标名称
 * @param value      主要数值（支持字符串/数字）
 * @param sub        副标题/说明文字
 * @param icon       左侧图标（antd Icon 组件）
 * @param color      图标背景色（CSS 颜色值）
 * @param suffix     数值后缀（如「次」「ms」）
 * @param trend      趋势对比文字（可正可负）
 * @param trendUp    true=正向趋势（绿），false=负向趋势（红）
 */
import { Card, Typography } from 'antd'
import type { ReactNode } from 'react'

const { Text } = Typography

interface StatCardProps {
  title: string
  value: string | number
  sub?: string
  icon: ReactNode
  color: string
  suffix?: string
  trend?: string
  trendUp?: boolean
  loading?: boolean
  onClick?: () => void
}

export default function StatCard({
  title,
  value,
  sub,
  icon,
  color,
  suffix,
  trend,
  trendUp,
  loading,
  onClick,
}: StatCardProps) {
  return (
    <Card
      loading={loading}
      hoverable={!!onClick}
      onClick={onClick}
      bodyStyle={{ padding: '16px 20px' }}
      style={{ borderRadius: 10, height: '100%' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        {/* 图标徽章 */}
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: color + '22',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            color,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>

        {/* 数据区 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {title}
          </Text>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 2 }}>
            <span style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.2, color: '#1a1a2e' }}>
              {typeof value === 'number' ? value.toLocaleString() : value}
            </span>
            {suffix && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {suffix}
              </Text>
            )}
          </div>
          {sub && (
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
              {sub}
            </Text>
          )}
          {trend !== undefined && (
            <Text
              style={{
                fontSize: 12,
                color: trendUp ? '#52c41a' : '#ff4d4f',
                display: 'block',
                marginTop: 4,
              }}
            >
              {trendUp ? '↑' : '↓'} {trend}
            </Text>
          )}
        </div>
      </div>
    </Card>
  )
}
