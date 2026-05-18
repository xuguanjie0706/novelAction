import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { DatabaseOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import type { RagRetrievalLogRecord } from '../types/ragLogs'

const { Text, Title } = Typography

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'rag_query', label: '手动查询' },
  { value: 'draft_context', label: '写章上下文' },
  { value: 'pre_write_warning', label: '写前预警' },
  { value: 'suggest', label: 'AI 建议' },
]

function sourceLabel(source: string) {
  const m: Record<string, string> = {
    rag_query: '手动查询',
    draft_context: '写章上下文',
    pre_write_warning: '写前预警',
    suggest: 'AI 建议',
  }
  return m[source] || source
}

function statusTag(status: string) {
  if (status === 'ok') return <Tag color="green">语义检索</Tag>
  if (status === 'embed_failed') return <Tag color="orange">向量化失败·时序兜底</Tag>
  if (status === 'fallback_recency') return <Tag color="gold">时序兜底</Tag>
  if (status === 'empty_query') return <Tag>空查询</Tag>
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
 * 管理后台：跨项目查看 RAG 记忆检索日志（写章注入 / 写前预警 / 手动查询等）。
 */
export default function RagRetrievalLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<RagRetrievalLogRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<RagRetrievalLogRecord | null>(null)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [projectFilter, setProjectFilter] = useState('')
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
      qs.set('limit', '1000')
      if (apiRange) {
        qs.set('since', apiRange[0].startOf('day').toISOString())
        qs.set('until', apiRange[1].endOf('day').toISOString())
      }
      const pid = projectFilter.trim()
      if (pid) qs.set('project_id', pid)
      if (sourceFilter) qs.set('source', sourceFilter)
      const { data } = await http.get<RagRetrievalLogRecord[]>(`/api/v1/admin/rag-logs/?${qs.toString()}`)
      setRows(data)
    } catch {
      message.error('加载 RAG 检索日志失败')
    } finally {
      setLoading(false)
    }
  }, [message, apiRange, projectFilter, sourceFilter])

  useEffect(() => {
    void load()
  }, [load])

  const degradedCount = useMemo(
    () => rows.filter(r => r.status !== 'ok' && r.status !== 'empty_query').length,
    [rows],
  )

  const columns: ColumnsType<RagRetrievalLogRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 168,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 140,
      render: (s: string) => statusTag(s),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (s: string) => sourceLabel(s),
    },
    {
      title: '查询',
      key: 'query',
      ellipsis: true,
      render: (_, row) => {
        const q = row.input_payload?.query
        return typeof q === 'string' ? q : <Text type="secondary">—</Text>
      },
    },
    {
      title: '命中',
      key: 'hit_count',
      width: 72,
      render: (_, row) => {
        const n = row.output_payload?.hit_count
        return typeof n === 'number' ? n : '—'
      },
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 88,
      render: (v: number) => `${v} ms`,
    },
    {
      title: '作品 ID',
      dataIndex: 'project_id',
      width: 280,
      ellipsis: true,
      render: (t: string) => <Text copyable={{ text: t }}>{t}</Text>,
    },
    {
      title: '章节 ID',
      dataIndex: 'chapter_id',
      width: 200,
      ellipsis: true,
      render: (t?: string | null) =>
        t ? <Text copyable={{ text: t }}>{t.slice(0, 8)}…</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '详情',
      key: 'detail',
      width: 72,
      fixed: 'right',
      render: (_, row) => (
        <Button type="link" onClick={() => setDetailRow(row)}>
          查看
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%', flexWrap: 'wrap' }} align="start">
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <DatabaseOutlined style={{ marginRight: 8 }} />
            RAG 记忆检索日志
          </Title>
          <Text type="secondary">
            共 {rows.length} 条，非语义检索 {degradedCount} 条；与创作端记忆库 RAG 面板同源数据。
          </Text>
        </div>
        <Space wrap>
          <Input
            placeholder="按作品 UUID 筛选"
            allowClear
            style={{ width: 320 }}
            value={projectFilter}
            onChange={e => setProjectFilter(e.target.value)}
            onPressEnter={() => void load()}
          />
          <Select
            style={{ width: 140 }}
            value={sourceFilter}
            options={SOURCE_OPTIONS}
            onChange={setSourceFilter}
          />
          <DatePicker.RangePicker
            value={dateRange}
            presets={rangePresets}
            allowClear
            placeholder={['开始日期', '结束日期']}
            onChange={v => setDateRange(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        </Space>
      </Space>

      <Table<RagRetrievalLogRecord>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100] }}
        scroll={{ x: 1400, y: 'calc(100vh - 320px)' }}
      />

      <Modal
        title="RAG 检索详情"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={960}
      >
        {detailRow && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>状态：</Text> {statusTag(detailRow.status)}
              <Text strong style={{ marginLeft: 16 }}>来源：</Text> {sourceLabel(detailRow.source)}
              <Text strong style={{ marginLeft: 16 }}>耗时：</Text> {detailRow.duration_ms} ms
            </div>
            <div>
              <Text strong>查询（input_payload.query）</Text>
              <pre style={{ maxHeight: 120, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {String(detailRow.input_payload?.query ?? '—')}
              </pre>
            </div>
            {typeof detailRow.output_payload?.answer_hint === 'string' &&
            detailRow.output_payload.answer_hint ? (
              <div>
                <Text strong>摘要（answer_hint）</Text>
                <pre style={{ maxHeight: 200, overflow: 'auto', background: '#fffbe6', padding: 12, borderRadius: 6 }}>
                  {detailRow.output_payload.answer_hint}
                </pre>
              </div>
            ) : null}
            {typeof detailRow.output_payload?.memory_summary === 'string' &&
            detailRow.output_payload.memory_summary ? (
              <div>
                <Text strong>注入 prompt 的记忆摘要</Text>
                <pre style={{ maxHeight: 160, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                  {detailRow.output_payload.memory_summary}
                </pre>
              </div>
            ) : null}
            <div>
              <Text strong>命中列表（output_payload.hits）</Text>
              <pre style={{ maxHeight: 280, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyJson(detailRow.output_payload?.hits ?? [])}
              </pre>
            </div>
            <div>
              <Text strong>完整 input_payload</Text>
              <pre style={{ maxHeight: 160, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyJson(detailRow.input_payload)}
              </pre>
            </div>
            <div>
              <Text strong>完整 output_payload</Text>
              <pre style={{ maxHeight: 200, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyJson(detailRow.output_payload)}
              </pre>
            </div>
          </Space>
        )}
      </Modal>
    </Space>
  )
}
