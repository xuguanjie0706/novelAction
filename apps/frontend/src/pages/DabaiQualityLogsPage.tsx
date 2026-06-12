import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { AuditOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import type { DabaiQualityLogRecord } from '../types/dabaiQualityLogs'

const { Text, Title } = Typography

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'manual', label: '手动质检' },
  { value: 'post_write', label: '写后自动' },
  { value: 'rules', label: '仅规则层' },
]

function sourceLabel(source: string) {
  const m: Record<string, string> = {
    manual: '手动质检',
    post_write: '写后自动',
    rules: '仅规则层',
  }
  return m[source] || source
}

function scoreTag(score: number | null | undefined) {
  if (score == null) return <Tag>—</Tag>
  if (score >= 80) return <Tag color="green">{score}</Tag>
  if (score >= 60) return <Tag color="gold">{score}</Tag>
  return <Tag color="red">{score}</Tag>
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

/** 管理后台：dabai 实验书架质检历史（每次质检一条，可回归对比衔接快照）。 */
export default function DabaiQualityLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<DabaiQualityLogRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<DabaiQualityLogRecord | null>(null)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [projectFilter, setProjectFilter] = useState('')
  const [chapterFilter, setChapterFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')

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
      qs.set('limit', '500')
      if (apiRange) {
        qs.set('since', apiRange[0].startOf('day').toISOString())
        qs.set('until', apiRange[1].endOf('day').toISOString())
      }
      if (projectFilter.trim()) qs.set('project_id', projectFilter.trim())
      if (chapterFilter.trim()) {
        const n = parseInt(chapterFilter.trim(), 10)
        if (!Number.isNaN(n)) qs.set('chapter_number', String(n))
      }
      const res = await http.get<DabaiQualityLogRecord[]>(
        `/api/v1/admin/dabai-quality-logs/?${qs.toString()}`,
      )
      let data = res.data
      if (sourceFilter) data = data.filter(r => r.source === sourceFilter)
      setRows(data)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [apiRange, chapterFilter, message, projectFilter, sourceFilter])

  useEffect(() => {
    void load()
  }, [load])

  const openDetail = async (row: DabaiQualityLogRecord) => {
    try {
      const res = await http.get<DabaiQualityLogRecord>(
        `/api/v1/admin/dabai-quality-logs/${row.id}`,
      )
      setDetailRow(res.data)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载详情失败')
    }
  }

  const columns: ColumnsType<DabaiQualityLogRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: v => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '—'),
    },
    {
      title: '章',
      width: 56,
      dataIndex: 'chapter_number',
      render: v => (v != null ? `第${v}章` : '—'),
    },
    { title: '来源', width: 88, dataIndex: 'source', render: v => sourceLabel(String(v)) },
    { title: '综合', width: 64, dataIndex: 'overall_score', render: v => scoreTag(v as number) },
    { title: '衔接', width: 64, dataIndex: 'continuity_score', render: v => scoreTag(v as number) },
    {
      title: '紧接上文',
      width: 80,
      dataIndex: 'opening_continues_prev_tail',
      render: v => (v === true ? <Tag color="green">是</Tag> : v === false ? <Tag color="red">否</Tag> : '—'),
    },
    {
      title: '章纲位移',
      width: 80,
      dataIndex: 'location_bridge_needed',
      render: v => (v === true ? <Tag color="orange">需要</Tag> : v === false ? <Tag>跳过</Tag> : '—'),
    },
    {
      title: '衔接问题',
      ellipsis: true,
      dataIndex: 'continuity_issue',
      render: v => (v ? <Text type="danger">{String(v)}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: '正文开头',
      ellipsis: true,
      dataIndex: 'content_head_preview',
      render: v => <Text type="secondary">{String(v || '').slice(0, 60)}</Text>,
    },
    {
      title: '操作',
      width: 72,
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => void openDetail(row)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space align="center">
          <AuditOutlined style={{ fontSize: 22, color: '#1677ff' }} />
          <Title level={4} style={{ margin: 0 }}>
            大白文质检历史
          </Title>
        </Space>
        <Text type="secondary">
          实验书架每次质检追加一条记录，含衔接快照（上章末/本章头/章纲 location），便于回归对比规则误报。
        </Text>
        <Space wrap>
          <DatePicker.RangePicker
            presets={rangePresets}
            value={dateRange}
            onChange={v => setDateRange(v)}
          />
          <Input
            placeholder="项目 UUID"
            value={projectFilter}
            onChange={e => setProjectFilter(e.target.value)}
            style={{ width: 280 }}
            allowClear
          />
          <Input
            placeholder="章号"
            value={chapterFilter}
            onChange={e => setChapterFilter(e.target.value)}
            style={{ width: 80 }}
            allowClear
          />
          <Select
            value={sourceFilter}
            onChange={setSourceFilter}
            options={SOURCE_OPTIONS}
            style={{ width: 120 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        </Space>
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 50, showSizeChanger: true }}
        />
      </Space>

      <Modal
        title="质检详情"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={860}
      >
        {detailRow ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Text>
              {detailRow.project_title || detailRow.project_id} · 第{detailRow.chapter_number}章{' '}
              {detailRow.chapter_title || ''}
            </Text>
            <pre style={{ maxHeight: 480, overflow: 'auto', fontSize: 12, background: '#fafafa', padding: 12 }}>
              {prettyJson(detailRow.report)}
            </pre>
          </Space>
        ) : null}
      </Modal>
    </div>
  )
}
