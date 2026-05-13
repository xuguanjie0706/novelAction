/**
 * RedeemCodesPage — 管理后台兑换码：批量生成、批次概览、码明细与禁用。
 *
 * 数据来源：`/api/v1/admin/redeem-codes/*`（管理员 Bearer）。创作端用户核销走
 * `POST /api/v1/credits/redeem`，与本页独立。
 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CopyOutlined, DownloadOutlined, GiftOutlined, StopOutlined } from '@ant-design/icons'
import { http } from '../api/http'

const { Text, Title } = Typography

/** POST /admin/redeem-codes/batch 响应 */
interface BatchGenerateResponse {
  batch_id: string
  count: number
  credits: number
  note: string | null
  expires_at: string | null
  codes: string[]
}

interface BatchSummary {
  batch_id: string
  credits: number
  note: string | null
  total: number
  active_count: number
  redeemed_count: number
  created_at: string | null
  expires_at: string | null
}

interface RedeemCodeRow {
  id: string
  code: string
  credits: number
  status: string
  batch_id: string
  note: string | null
  redeemed_by: string | null
  redeemed_at: string | null
  expires_at: string | null
  created_at: string | null
}

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '未使用' },
  { value: 'redeemed', label: '已核销' },
  { value: 'disabled', label: '已禁用' },
]

function statusTag(status: string) {
  if (status === 'active') return <Tag color="green">未使用</Tag>
  if (status === 'redeemed') return <Tag color="blue">已核销</Tag>
  if (status === 'disabled') return <Tag color="default">已禁用</Tag>
  return <Tag>{status}</Tag>
}

export default function RedeemCodesPage() {
  const { message } = App.useApp()
  const [genForm] = Form.useForm<{
    count: number
    credits: number
    note?: string
    expires_days?: number | null
  }>()

  const [batches, setBatches] = useState<BatchSummary[]>([])
  const [batchesLoading, setBatchesLoading] = useState(false)

  const [codes, setCodes] = useState<RedeemCodeRow[]>([])
  const [codesLoading, setCodesLoading] = useState(false)
  const [filterBatch, setFilterBatch] = useState<string | undefined>(undefined)
  const [filterStatus, setFilterStatus] = useState<string>('')
  const CODE_LIST_LIMIT = 500

  const [resultOpen, setResultOpen] = useState(false)
  const [lastBatch, setLastBatch] = useState<BatchGenerateResponse | null>(null)
  const [genSubmitting, setGenSubmitting] = useState(false)

  const loadBatches = useCallback(async () => {
    setBatchesLoading(true)
    try {
      const res = await http.get<BatchSummary[]>('/api/v1/admin/redeem-codes/batches')
      setBatches(res.data)
    } catch {
      message.error('加载批次失败')
    } finally {
      setBatchesLoading(false)
    }
  }, [message])

  const loadCodes = useCallback(async () => {
    setCodesLoading(true)
    try {
      const params = new URLSearchParams({
        limit: String(CODE_LIST_LIMIT),
        offset: '0',
      })
      if (filterBatch) params.set('batch_id', filterBatch)
      if (filterStatus) params.set('status', filterStatus)
      const res = await http.get<RedeemCodeRow[]>(`/api/v1/admin/redeem-codes?${params.toString()}`)
      setCodes(res.data)
    } catch {
      message.error('加载兑换码列表失败')
    } finally {
      setCodesLoading(false)
    }
  }, [message, filterBatch, filterStatus])

  useEffect(() => {
    loadBatches()
  }, [loadBatches])

  useEffect(() => {
    loadCodes()
  }, [loadCodes])

  const handleGenerate = async () => {
    setGenSubmitting(true)
    try {
      const v = await genForm.validateFields()
      const body: Record<string, unknown> = {
        count: v.count,
        credits: v.credits,
        note: v.note?.trim() || null,
      }
      if (v.expires_days != null && v.expires_days > 0) {
        body.expires_days = v.expires_days
      }
      const res = await http.post<BatchGenerateResponse>('/api/v1/admin/redeem-codes/batch', body)
      setLastBatch(res.data)
      setResultOpen(true)
      message.success(`已生成 ${res.data.count} 张兑换码`)
      genForm.resetFields(['note', 'expires_days'])
      setFilterBatch(res.data.batch_id)
      setFilterStatus('')
      await loadBatches()
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } }; errorFields?: unknown }
      if (ax.errorFields) return
      const detail = ax.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '生成失败')
    } finally {
      setGenSubmitting(false)
    }
  }

  const copyCodes = (list: string[]) => {
    const text = list.join('\n')
    void navigator.clipboard.writeText(text).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败，请手动选择复制'),
    )
  }

  const downloadCodes = (list: string[], batchId: string) => {
    const blob = new Blob([list.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `redeem-codes-${batchId}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const disableCode = async (row: RedeemCodeRow) => {
    try {
      await http.patch(`/api/v1/admin/redeem-codes/${row.id}/disable`)
      message.success('已禁用')
      loadCodes()
      loadBatches()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '禁用失败')
    }
  }

  const batchColumns: ColumnsType<BatchSummary> = [
    {
      title: '批次 ID',
      dataIndex: 'batch_id',
      ellipsis: true,
      render: (id: string) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => { setFilterBatch(id) }}>
          {id}
        </Button>
      ),
    },
    { title: '面值', dataIndex: 'credits', width: 100, render: (c: number) => `${c.toLocaleString()} 积分` },
    { title: '总数', dataIndex: 'total', width: 70 },
    { title: '未使用', dataIndex: 'active_count', width: 80 },
    { title: '已核销', dataIndex: 'redeemed_count', width: 80 },
    {
      title: '备注',
      dataIndex: 'note',
      ellipsis: true,
      render: (n: string | null) => n || '—',
    },
    {
      title: '创建 / 过期',
      key: 'time',
      width: 200,
      render: (_, r) => (
        <div style={{ fontSize: 12 }}>
          <div>{r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : '—'}</div>
          <Text type="secondary">{r.expires_at ? `过期 ${new Date(r.expires_at).toLocaleString('zh-CN')}` : '永久'}</Text>
        </div>
      ),
    },
  ]

  const codeColumns: ColumnsType<RedeemCodeRow> = [
    {
      title: '兑换码',
      dataIndex: 'code',
      render: (code: string) => (
        <Space>
          <Text code copyable={{ text: code }}>{code}</Text>
        </Space>
      ),
    },
    { title: '面值', dataIndex: 'credits', width: 90, render: (c: number) => c.toLocaleString() },
    { title: '状态', dataIndex: 'status', width: 100, render: statusTag },
    {
      title: '核销信息',
      key: 'rx',
      width: 200,
      render: (_, r) =>
        r.status === 'redeemed' ? (
          <div style={{ fontSize: 12 }}>
            <div>{r.redeemed_at ? new Date(r.redeemed_at).toLocaleString('zh-CN') : '—'}</div>
            <Text type="secondary" ellipsis>{r.redeemed_by ?? '—'}</Text>
          </div>
        ) : (
          '—'
        ),
    },
    {
      title: '操作',
      key: 'act',
      width: 100,
      render: (_, row) =>
        row.status === 'active' ? (
          <Popconfirm
            title="确认禁用？"
            description="禁用后该码无法再被用户兑换。"
            okText="禁用"
            cancelText="取消"
            onConfirm={() => void disableCode(row)}
          >
            <Button size="small" danger icon={<StopOutlined />}>
              禁用
            </Button>
          </Popconfirm>
        ) : null,
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <GiftOutlined style={{ marginRight: 8 }} />
          兑换码管理
        </Title>
        <Space>
          <Button onClick={() => { loadBatches(); loadCodes() }} loading={batchesLoading || codesLoading}>
            刷新
          </Button>
        </Space>
      </div>

      <Card title="批量生成" style={{ marginBottom: 16 }}>
        <Form
          form={genForm}
          layout="inline"
          initialValues={{ count: 10, credits: 1000 }}
          onFinish={() => void handleGenerate()}
        >
          <Form.Item name="count" label="数量" rules={[{ required: true }]}>
            <InputNumber min={1} max={1000} />
          </Form.Item>
          <Form.Item name="credits" label="每张面值" rules={[{ required: true }]}>
            <InputNumber min={1} max={999999999} />
          </Form.Item>
          <Form.Item name="expires_days" label="有效天数">
            <InputNumber min={1} max={3650} placeholder="留空=永久" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="note" label="批次备注">
            <Input placeholder="活动名等" style={{ width: 200 }} maxLength={200} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<GiftOutlined />} loading={genSubmitting}>
              生成
            </Button>
          </Form.Item>
        </Form>
        <Text type="secondary" style={{ fontSize: 12 }}>
          生成后请立即导出或复制保存；创作端用户在「钱包」页输入码即可充值（支持无连字符输入）。
        </Text>
      </Card>

      <Card title="批次概览" style={{ marginBottom: 16 }}>
        <Table
          rowKey="batch_id"
          size="small"
          loading={batchesLoading}
          columns={batchColumns}
          dataSource={batches}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Card title="兑换码明细">
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            style={{ width: 200 }}
            placeholder="按批次筛选"
            allowClear
            showSearch
            optionFilterProp="label"
            value={filterBatch}
            onChange={(v) => { setFilterBatch(v || undefined) }}
            options={batches.map((b) => ({
              value: b.batch_id,
              label: `${b.batch_id.slice(0, 8)}… · ${b.credits}积分×${b.total}`,
            }))}
          />
          <Select
            style={{ width: 140 }}
            value={filterStatus}
            onChange={(v) => { setFilterStatus(v) }}
            options={STATUS_OPTIONS}
          />
        </Space>
        <Table
          rowKey="id"
          size="small"
          loading={codesLoading}
          columns={codeColumns}
          dataSource={codes}
          pagination={codes.length > 20 ? { pageSize: 50, showSizeChanger: true } : false}
        />
        {codes.length >= CODE_LIST_LIMIT && (
          <Text type="warning" style={{ display: 'block', marginTop: 8 }}>
            当前最多展示 {CODE_LIST_LIMIT} 条，请使用批次或状态筛选以缩小范围。
          </Text>
        )}
      </Card>

      <Modal
        title="生成成功"
        open={resultOpen}
        onCancel={() => setResultOpen(false)}
        footer={[
          <Button key="c" icon={<CopyOutlined />} onClick={() => lastBatch && copyCodes(lastBatch.codes)}>
            复制全部
          </Button>,
          <Button
            key="d"
            icon={<DownloadOutlined />}
            onClick={() => lastBatch && downloadCodes(lastBatch.codes, lastBatch.batch_id)}
          >
            下载 TXT
          </Button>,
          <Button key="ok" type="primary" onClick={() => setResultOpen(false)}>
            关闭
          </Button>,
        ]}
        width={560}
      >
        {lastBatch && (
          <div>
            <p>
              批次 <Text code>{lastBatch.batch_id}</Text>，共 <Text strong>{lastBatch.count}</Text> 张，
              每张 <Text strong>{lastBatch.credits.toLocaleString()}</Text> 积分。
            </p>
            <Input.TextArea readOnly rows={12} value={lastBatch.codes.join('\n')} style={{ fontFamily: 'monospace', fontSize: 12 }} />
          </div>
        )}
      </Modal>
    </div>
  )
}
