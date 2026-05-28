import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, App, Button, DatePicker, Modal, Popconfirm, Space, Spin, Table, Tag, Tooltip, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import { getLlmOperationLabel, getLlmOperationShortLabel } from '../constants/llmOperationLabels'
import type { LlmCallContextIssue, LlmCallListResponse, LlmCallRecord } from '../types/llm'

const { Text, Title } = Typography

const CONTEXT_LIMIT_ERROR_HINTS = [
  'context length',
  'maximum context',
  'context window',
  'too many tokens',
  '上下文长度',
  '超过上下文',
  '超出上下文',
  '上下文超限',
]

function resolveContextIssue(row: LlmCallRecord): LlmCallContextIssue | null {
  if (row.context_issue === 'truncated' || row.context_issue === 'limit_exceeded') {
    return row.context_issue
  }
  const ctx = row.context || {}
  const warnings = ctx.truncation_warnings
  if (ctx.context_truncated || (Array.isArray(warnings) && warnings.length > 0)) {
    return 'truncated'
  }
  if (row.status === 'error' && row.error) {
    const err = row.error.toLowerCase()
    if (CONTEXT_LIMIT_ERROR_HINTS.some((h) => err.includes(h) || row.error!.includes(h))) {
      return 'limit_exceeded'
    }
  }
  return null
}

function truncationWarnings(row: LlmCallRecord): string[] {
  const raw = row.context?.truncation_warnings
  if (!Array.isArray(raw)) return []
  return raw.filter((w): w is string => typeof w === 'string' && w.trim().length > 0)
}

const contextIssueMeta: Record<
  LlmCallContextIssue,
  { label: string; color: string; description: string }
> = {
  truncated: {
    label: '上下文已裁剪',
    color: 'orange',
    description: '部分 prompt 字段因窗口上限被业务侧裁剪，模型未看到完整设定',
  },
  limit_exceeded: {
    label: '上下文超限',
    color: 'red',
    description: '网关返回上下文长度错误，本次请求可能未完整处理',
  },
}

const PAGE_SIZE = 20

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

export default function LlmCallLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<LlmCallRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<LlmCallRecord | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)

  const resolveOperationKey = (row: LlmCallRecord) => {
    const op = row.context?.operation
    if (typeof op === 'string' && op.trim()) return op.trim()
    const task = row.context?.task
    if (typeof task === 'string' && task.trim()) return task.trim()
    return ''
  }

  const prettyText = (v: unknown) => {
    if (v == null) return ''
    if (typeof v === 'string') return v
    try {
      return JSON.stringify(v, null, 2)
    } catch {
      return String(v)
    }
  }

  const apiRange = useMemo((): [Dayjs, Dayjs] | null => {
    const a = dateRange?.[0]
    const b = dateRange?.[1]
    if (a && b) return [a, b]
    return null
  }, [dateRange])

  const load = useCallback(
    async (targetPage: number) => {
      setLoading(true)
      try {
        const qs = new URLSearchParams()
        qs.set('page', String(targetPage))
        qs.set('page_size', String(PAGE_SIZE))
        if (apiRange) {
          qs.set('since', apiRange[0].startOf('day').toISOString())
          qs.set('until', apiRange[1].endOf('day').toISOString())
        }
        const { data } = await http.get<LlmCallListResponse>(`/api/v1/admin/llm-calls/?${qs.toString()}`)
        setRows(data.items)
        setTotal(data.total)
        setPage(data.page)
      } catch {
        message.error('加载 LLM 调用记录失败')
      } finally {
        setLoading(false)
      }
    },
    [message, apiRange],
  )

  useEffect(() => {
    void load(1)
  }, [load])

  const openDetail = async (row: LlmCallRecord) => {
    setDetailRow(row)
    setDetailLoading(true)
    try {
      const { data } = await http.get<LlmCallRecord>(`/api/v1/admin/llm-calls/${row.id}`)
      setDetailRow(data)
    } catch {
      message.error('加载调用详情失败')
      setDetailRow(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const clearLogs = async () => {
    try {
      const { data } = await http.delete<{ deleted: number }>('/api/v1/admin/llm-calls/')
      message.success(`已清空 ${data.deleted} 条记录`)
      setRows([])
      setTotal(0)
      setPage(1)
    } catch {
      message.error('清空失败')
    }
  }

  const totalTokens = useMemo(
    () => rows.reduce((sum, r) => sum + (r.token_usage?.total_tokens || 0), 0),
    [rows],
  )

  const contextIssueStats = useMemo(() => {
    let truncated = 0
    let limitExceeded = 0
    for (const row of rows) {
      const issue = resolveContextIssue(row)
      if (issue === 'truncated') truncated += 1
      if (issue === 'limit_exceeded') limitExceeded += 1
    }
    return { truncated, limitExceeded, total: truncated + limitExceeded }
  }, [rows])

  const hasDateFilter = apiRange != null

  const renderContextIssueTag = (row: LlmCallRecord) => {
    const issue = resolveContextIssue(row)
    if (!issue) return null
    const meta = contextIssueMeta[issue]
    const warnings = truncationWarnings(row)
    const tip =
      warnings.length > 0
        ? `${meta.description}\n\n${warnings.join('\n')}`
        : meta.description
    return (
      <Tooltip title={<span style={{ whiteSpace: 'pre-wrap' }}>{tip}</span>}>
        <Tag color={meta.color}>{meta.label}</Tag>
      </Tooltip>
    )
  }

  const columns: ColumnsType<LlmCallRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: '上下文',
      dataIndex: 'context',
      width: 300,
      render: (ctx: Record<string, unknown>) => (
        <Text style={{ whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(ctx || {}, null, 2)}
        </Text>
      ),
    },
    {
      title: '接口作用',
      key: 'operation',
      width: 300,
      render: (_, row) => {
        const op = resolveOperationKey(row)
        return (
          <Space direction="vertical" size={0}>
            <Tooltip title={op || undefined}>
              <Text strong>{getLlmOperationShortLabel(op)}</Text>
            </Tooltip>
            <Text type="secondary">{getLlmOperationLabel(op)}</Text>
            {op ? (
              <Text type="secondary" copyable={{ text: op }} style={{ fontSize: 11 }}>
                {op}
              </Text>
            ) : null}
          </Space>
        )
      },
    },
    {
      title: '具体接口',
      dataIndex: 'llm_endpoint',
      width: 260,
      ellipsis: true,
      render: (t: string) => <Text copyable={{ text: t }}>{t}</Text>,
    },
    {
      title: 'Token 花费',
      key: 'token_usage',
      width: 180,
      render: (_, row) => {
        const usage = row.token_usage
        return (
          <Space direction="vertical" size={0}>
            <Text>总计：{usage?.total_tokens ?? 0}</Text>
            <Text type="secondary">输入：{usage?.prompt_tokens ?? 0} / 输出：{usage?.completion_tokens ?? 0}</Text>
            {usage?.estimated ? <Tag color="gold">估算</Tag> : <Tag color="green">真实</Tag>}
          </Space>
        )
      },
    },
    {
      title: '模型',
      dataIndex: 'model',
      width: 150,
      ellipsis: true,
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 100,
      render: (v: number) => `${v} ms`,
    },
    {
      title: '状态',
      key: 'status',
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={4}>
          {row.status === 'ok' ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>}
          {renderContextIssueTag(row)}
        </Space>
      ),
    },
    {
      title: '错误信息',
      dataIndex: 'error',
      ellipsis: true,
      render: (v?: string | null) => (v ? <Text type="danger">{v}</Text> : <Text type="secondary">-</Text>),
    },
    {
      title: '详情',
      key: 'detail',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
        <Button type="link" onClick={() => void openDetail(row)}>
          查看
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>LLM 调用记录</Title>
          <Text type="secondary">
            共 {total} 条
            {hasDateFilter ? '（所选时间范围内）' : ''}
            ，本页 token：{totalTokens}
          </Text>
        </div>
        <Space wrap>
          <DatePicker.RangePicker
            value={dateRange}
            presets={rangePresets}
            allowClear
            placeholder={['开始日期', '结束日期']}
            onChange={(v) => {
              setDateRange(v)
              setPage(1)
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load(page)} loading={loading}>
            刷新
          </Button>
          <Popconfirm
            title="确认清空全部调用记录？"
            okText="清空"
            cancelText="取消"
            onConfirm={() => void clearLogs()}
          >
            <Button danger icon={<DeleteOutlined />}>清空记录</Button>
          </Popconfirm>
        </Space>
      </Space>

      {contextIssueStats.total > 0 && (
        <Alert
          type={contextIssueStats.limitExceeded > 0 ? 'error' : 'warning'}
          showIcon
          message={
            contextIssueStats.limitExceeded > 0
              ? '本页存在上下文超限或裁剪的调用'
              : '本页存在 prompt 被裁剪的调用'
          }
          description={
            <Space direction="vertical" size={0}>
              {contextIssueStats.truncated > 0 && (
                <Text>
                  {contextIssueStats.truncated} 条因窗口限制被业务侧裁剪；建议换更大上下文模型或减少注入字段。
                </Text>
              )}
              {contextIssueStats.limitExceeded > 0 && (
                <Text>
                  {contextIssueStats.limitExceeded} 条网关报上下文超限；请缩短输入或升级模型窗口。
                </Text>
              )}
            </Space>
          }
        />
      )}

      <Table<LlmCallRecord>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => void load(p),
        }}
        scroll={{ x: 1900, y: 'calc(100vh - 320px)' }}
      />

      <Modal
        title="LLM 调用详情（全量）"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={1000}
      >
        <Spin spinning={detailLoading}>
        {detailRow && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {(() => {
              const issue = resolveContextIssue(detailRow)
              if (!issue) return null
              const meta = contextIssueMeta[issue]
              const warnings = truncationWarnings(detailRow)
              return (
                <Alert
                  type={issue === 'limit_exceeded' ? 'error' : 'warning'}
                  showIcon
                  message={meta.label}
                  description={
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text>{meta.description}</Text>
                      {warnings.map((w) => (
                        <Text key={w} type="secondary">
                          · {w}
                        </Text>
                      ))}
                    </Space>
                  }
                />
              )
            })()}
            <div>
              <Text strong>接口作用：</Text>
              <Text>{getLlmOperationLabel(resolveOperationKey(detailRow))}</Text>
            </div>
            <div>
              <Text strong>上下文（全量）</Text>
              <pre style={{ maxHeight: 220, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyText(detailRow.context)}
              </pre>
            </div>
            <div>
              <Text strong>输入（全量）</Text>
              <pre style={{ maxHeight: 280, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyText(detailRow.input_payload)}
              </pre>
            </div>
            <div>
              <Text strong>输出（全量）</Text>
              <pre style={{ maxHeight: 280, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {prettyText(detailRow.output_payload)}
              </pre>
            </div>
          </Space>
        )}
        </Spin>
      </Modal>
    </Space>
  )
}
