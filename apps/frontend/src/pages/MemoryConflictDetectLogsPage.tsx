import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, DatePicker, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { DatabaseOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import type { MemoryConflictDetectLogRecord } from '../types/memoryConflictLogs'

const { Text, Title } = Typography

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

const TRIGGER_OPTIONS = [
  { value: '', label: '全部触发' },
  { value: 'manual', label: '手动扫描' },
  { value: 'chapter_debrief', label: '章节复盘后' },
]

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'ok', label: '成功' },
  { value: 'error', label: '失败' },
  { value: 'skipped', label: '跳过（无记忆）' },
]

function triggerLabel(t: string) {
  const m: Record<string, string> = {
    manual: '手动扫描',
    chapter_debrief: '章节复盘后',
  }
  return m[t] || t
}

function statusTag(status: string) {
  if (status === 'ok') return <Tag color="green">成功</Tag>
  if (status === 'error') return <Tag color="red">失败</Tag>
  if (status === 'skipped') return <Tag color="default">跳过</Tag>
  return <Tag>{status}</Tag>
}

function prettyJson(v: unknown) {
  if (v == null) return ''
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

/**
 * 管理后台：记忆冲突检测运行日志（memory_conflict_detect_logs）。
 */
export default function MemoryConflictDetectLogsPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [rows, setRows] = useState<MemoryConflictDetectLogRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<MemoryConflictDetectLogRecord | null>(null)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [projectFilter, setProjectFilter] = useState('')
  const [triggerFilter, setTriggerFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const apiRange = useMemo((): [Dayjs, Dayjs] | null => {
    const a = dateRange?.[0]
    const b = dateRange?.[1]
    if (a && b) return [a, b]
    return null
  }, [dateRange])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const qs = new URLSearchParams()
      qs.set('limit', '1000')
      if (apiRange) {
        qs.set('since', apiRange[0].startOf('day').toISOString())
        qs.set('until', apiRange[1].endOf('day').toISOString())
      }
      const pid = projectFilter.trim()
      if (pid) qs.set('project_id', pid)
      if (triggerFilter) qs.set('trigger', triggerFilter)
      if (statusFilter) qs.set('status', statusFilter)
      const { data } = await http.get<MemoryConflictDetectLogRecord[]>(
        `/api/v1/admin/memory-conflict-logs/?${qs.toString()}`,
      )
      setRows(data)
    } catch {
      message.error('加载记忆冲突检测日志失败')
    } finally {
      setLoading(false)
    }
  }, [message, apiRange, projectFilter, triggerFilter, statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  const errorCount = useMemo(() => rows.filter((r) => r.status === 'error').length, [rows])

  const columns: ColumnsType<MemoryConflictDetectLogRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 168,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 88,
      render: (s: string) => statusTag(s),
    },
    {
      title: '触发',
      dataIndex: 'trigger',
      width: 110,
      render: (t: string) => triggerLabel(t),
    },
    {
      title: '扫描',
      width: 100,
      render: (_: unknown, r) => (
        <Text type="secondary">
          {r.total_chunks_scanned} 条
          {r.conflict_count > 0 && (
            <Text type="danger"> · {r.conflict_count} 冲突</Text>
          )}
        </Text>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 72,
      render: (ms: number) => `${ms}ms`,
    },
    {
      title: '项目',
      dataIndex: 'project_id',
      ellipsis: true,
      render: (id: string) => (
        <Text copyable={{ text: id }} style={{ fontSize: 12 }}>
          {id.slice(0, 8)}…
        </Text>
      ),
    },
    {
      title: 'LLM 记录',
      dataIndex: 'llm_call_log_id',
      width: 100,
      render: (id: string | null) =>
        id ? (
          <Button type="link" size="small" style={{ padding: 0, fontSize: 12 }} onClick={() => navigate('/llm-calls')}>
            {id.slice(0, 8)}…
          </Button>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '操作',
      width: 72,
      render: (_: unknown, row) => (
        <Button type="link" size="small" onClick={() => setDetailRow(row)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Space>
          <DatabaseOutlined style={{ fontSize: 20, color: '#cf1322' }} />
          <Title level={4} style={{ margin: 0 }}>
            记忆冲突检测日志
          </Title>
          <Text type="secondary">
            共 {rows.length} 条
            {errorCount > 0 && (
              <Text type="danger"> · {errorCount} 次失败</Text>
            )}
          </Text>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </div>

      <Space wrap>
        <DatePicker.RangePicker
          value={dateRange}
          onChange={(v) => setDateRange(v)}
          presets={rangePresets}
          allowClear
        />
        <Input
          placeholder="项目 ID"
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          style={{ width: 280 }}
          allowClear
        />
        <Select
          value={triggerFilter}
          onChange={setTriggerFilter}
          options={TRIGGER_OPTIONS}
          style={{ width: 140 }}
        />
        <Select
          value={statusFilter}
          onChange={setStatusFilter}
          options={STATUS_OPTIONS}
          style={{ width: 140 }}
        />
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        columns={columns}
        size="small"
        pagination={{ pageSize: 30, showSizeChanger: true }}
        scroll={{ y: 'calc(100vh - 280px)' }}
      />

      <Modal
        title="检测运行详情"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={720}
      >
        {detailRow && (
          <pre style={{ maxHeight: 480, overflow: 'auto', fontSize: 12, background: '#fafafa', padding: 12 }}>
            {prettyJson(detailRow)}
          </pre>
        )}
      </Modal>
    </div>
  )
}
