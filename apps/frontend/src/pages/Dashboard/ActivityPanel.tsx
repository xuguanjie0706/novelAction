/**
 * 最近活动流面板：Bootstrap 运行记录、LLM 错误日志、记忆冲突事件。
 *
 * 数据来自 DashboardStats.activity 分组。
 */
import type { ReactNode } from 'react'
import { Card, Tag, Timeline, Typography } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ThunderboltOutlined,
  BugOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { ActivityData } from '../../types/dashboard'

const { Text } = Typography

const BOOTSTRAP_STATUS_META: Record<string, { label: string; color: string; icon: ReactNode }> = {
  done: { label: '完成', color: 'success', icon: <CheckCircleOutlined /> },
  running: { label: '进行中', color: 'processing', icon: <ClockCircleOutlined /> },
  failed: { label: '失败', color: 'error', icon: <CloseCircleOutlined /> },
  awaiting_gate: { label: '等待确认', color: 'warning', icon: <ExclamationCircleOutlined /> },
  pending: { label: '待启动', color: 'default', icon: <ClockCircleOutlined /> },
}

function relativeTime(iso: string | null): string {
  if (!iso) return '未知'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} 小时前`
  return `${Math.floor(hrs / 24)} 天前`
}

interface Props {
  data: ActivityData
  loading?: boolean
}

export default function ActivityPanel({ data, loading }: Props) {
  const bootItems = data.recent_bootstraps.map((b) => {
    const meta = BOOTSTRAP_STATUS_META[b.status] ?? { label: b.status, color: 'default', icon: null }
    return {
      dot: (
        <ThunderboltOutlined
          style={{ color: meta.color === 'success' ? '#52c41a' : meta.color === 'error' ? '#ff4d4f' : '#faad14' }}
        />
      ),
      children: (
        <div style={{ marginBottom: 2 }}>
          <Tag color={meta.color as string} style={{ fontSize: 11 }}>
            {meta.label}
          </Tag>
          <Text style={{ fontSize: 12 }}>{b.logline || '（无梗概）'}</Text>
          <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
            {relativeTime(b.created_at)} · {b.mode}
          </Text>
        </div>
      ),
    }
  })

  const errorItems = data.recent_llm_errors.map((e) => ({
    dot: <BugOutlined style={{ color: '#ff4d4f' }} />,
    children: (
      <div style={{ marginBottom: 2 }}>
        <Text type="danger" style={{ fontSize: 12 }}>
          {e.context?.operation ?? '未知操作'}
        </Text>
        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
          {e.model}
        </Text>
        <Text
          type="secondary"
          style={{ fontSize: 11, fontFamily: 'monospace', display: 'block', marginTop: 2 }}
        >
          {e.error.slice(0, 80)}
          {e.error.length > 80 ? '…' : ''}
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {relativeTime(e.created_at)} · {e.duration_ms} ms
        </Text>
      </div>
    ),
  }))

  const conflictItems = data.recent_memory_conflicts.map((c) => ({
    dot: <WarningOutlined style={{ color: '#faad14' }} />,
    children: (
      <div style={{ marginBottom: 2 }}>
        <Tag color="warning" style={{ fontSize: 11 }}>
          {c.conflict_count} 处冲突
        </Tag>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {c.trigger === 'chapter_debrief' ? '章节复盘触发' : '手动触发'}
        </Text>
        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
          {relativeTime(c.created_at)}
        </Text>
      </div>
    ),
  }))

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
      {/* Bootstrap 运行记录 */}
      <Card
        loading={loading}
        title={
          <span>
            <ThunderboltOutlined style={{ color: '#6366f1', marginRight: 6 }} />
            最近生成记录
          </span>
        }
        bodyStyle={{ padding: '12px 16px', maxHeight: 320, overflowY: 'auto' }}
        style={{ borderRadius: 10 }}
        size="small"
      >
        {bootItems.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            暂无记录
          </Text>
        ) : (
          <Timeline items={bootItems} style={{ marginTop: 8 }} />
        )}
      </Card>

      {/* LLM 错误 */}
      <Card
        loading={loading}
        title={
          <span>
            <BugOutlined style={{ color: '#ff4d4f', marginRight: 6 }} />
            最近 AI 调用错误
          </span>
        }
        bodyStyle={{ padding: '12px 16px', maxHeight: 320, overflowY: 'auto' }}
        style={{ borderRadius: 10 }}
        size="small"
      >
        {errorItems.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            近期无错误 ✓
          </Text>
        ) : (
          <Timeline items={errorItems} style={{ marginTop: 8 }} />
        )}
      </Card>

      {/* 记忆冲突 */}
      <Card
        loading={loading}
        title={
          <span>
            <WarningOutlined style={{ color: '#faad14', marginRight: 6 }} />
            记忆冲突事件
          </span>
        }
        bodyStyle={{ padding: '12px 16px', maxHeight: 320, overflowY: 'auto' }}
        style={{ borderRadius: 10 }}
        size="small"
      >
        {conflictItems.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            近期无冲突 ✓
          </Text>
        ) : (
          <Timeline items={conflictItems} style={{ marginTop: 8 }} />
        )}
      </Card>
    </div>
  )
}
