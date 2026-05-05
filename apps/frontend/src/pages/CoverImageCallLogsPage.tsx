import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Image, Input, Modal, Space, Table, Tag, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { FileImageOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import type { CoverImageCallRecord } from '../types/coverImageCalls'

const { Text, Title } = Typography

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

function statusTag(status: string) {
  if (status === 'ok') return <Tag color="green">成功</Tag>
  if (status === 'decode_error' || status === 'compress_error') return <Tag color="red">本地处理失败</Tag>
  if (status.startsWith('upstream_')) return <Tag color="volcano">网关/上游</Tag>
  return <Tag>{status}</Tag>
}

/**
 * 管理后台：展示创作端「AI 封面生成」调用 cover_image_call_logs，便于对照计费与调试包路径。
 */
export default function CoverImageCallLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<CoverImageCallRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<CoverImageCallRecord | null>(null)
  const [previewBroken, setPreviewBroken] = useState(false)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [projectFilter, setProjectFilter] = useState('')

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
      const { data } = await http.get<CoverImageCallRecord[]>(`/api/v1/admin/cover-image-calls/?${qs.toString()}`)
      setRows(data)
    } catch {
      message.error('加载封面生成记录失败')
    } finally {
      setLoading(false)
    }
  }, [message, apiRange, projectFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPreviewBroken(false)
  }, [detailRow?.id])

  const failCount = useMemo(() => rows.filter((r) => r.status !== 'ok').length, [rows])

  const columns: ColumnsType<CoverImageCallRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 168,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (s: string) => statusTag(s),
    },
    {
      title: '作品 ID',
      dataIndex: 'project_id',
      width: 280,
      ellipsis: true,
      render: (t: string) => <Text copyable={{ text: t }}>{t}</Text>,
    },
    {
      title: '图片模型',
      key: 'model',
      width: 200,
      ellipsis: true,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.provider_name}</Text>
          <Text type="secondary">{row.model_name}</Text>
        </Space>
      ),
    },
    {
      title: '尺寸 / 质量',
      key: 'sq',
      width: 130,
      render: (_, row) => (
        <Text>
          {row.size} · {row.quality}
        </Text>
      ),
    },
    {
      title: '响应',
      dataIndex: 'response_kind',
      width: 90,
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 88,
      render: (v: number) => `${v} ms`,
    },
    {
      title: 'HTTP',
      dataIndex: 'http_status',
      width: 72,
      render: (v: number | null) => (v != null ? v : <Text type="secondary">-</Text>),
    },
    {
      title: '调试目录',
      dataIndex: 'debug_bundle_rel_path',
      width: 220,
      ellipsis: true,
      render: (p: string | null) =>
        p ? <Text copyable={{ text: p }}>{p}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '错误摘要',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v?: string | null) =>
        v ? <Text type="danger">{v.slice(0, 120)}{v.length > 120 ? '…' : ''}</Text> : <Text type="secondary">-</Text>,
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
            <FileImageOutlined style={{ marginRight: 8 }} />
            封面生成记录
          </Title>
          <Text type="secondary">
            共 {rows.length} 条，非成功 {failCount} 条；失败时后端会写入 data/covers/debug/，「调试目录」为相对 apps/backend 的路径。
          </Text>
        </div>
        <Space wrap>
          <Input
            placeholder="按作品 UUID 筛选"
            allowClear
            style={{ width: 320 }}
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            onPressEnter={() => void load()}
          />
          <DatePicker.RangePicker
            value={dateRange}
            presets={rangePresets}
            allowClear
            placeholder={['开始日期', '结束日期']}
            onChange={(v) => setDateRange(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        </Space>
      </Space>

      <Table<CoverImageCallRecord>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100] }}
        scroll={{ x: 1700, y: 'calc(100vh - 320px)' }}
      />

      <Modal
        title="封面生成调用详情"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={960}
      >
        {detailRow && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>图片预览</Text>
              <div style={{ marginTop: 8, textAlign: 'center', background: '#f5f5f5', borderRadius: 8, padding: 12 }}>
                {!previewBroken ? (
                  <Image
                    src={`/api/v1/admin/cover-image-calls/${detailRow.id}/preview`}
                    alt="本次调用预览"
                    style={{ maxHeight: 420, objectFit: 'contain' }}
                    onError={() => setPreviewBroken(true)}
                    preview={{ mask: '放大查看' }}
                  />
                ) : (
                  <Text type="secondary">
                    暂无可预览图片（例如仅返回 data URL、上游失败无调试包、或历史记录未写入 result_cover_url）。
                    新产生的成功记录会带 WebP 路径；失败记录可依赖调试包内 payload 再解码预览。
                  </Text>
                )}
              </div>
            </div>
            <div>
              <Text strong>状态：</Text> {statusTag(detailRow.status)}
              <Text strong style={{ marginLeft: 16 }}>响应类型：</Text> {detailRow.response_kind}
            </div>
            {detailRow.result_cover_url ? (
              <div>
                <Text strong>结果地址（入库用）</Text>
                <div>
                  <Text copyable={{ text: detailRow.result_cover_url }}>{detailRow.result_cover_url}</Text>
                </div>
              </div>
            ) : null}
            <div>
              <Text strong>网关 URL（无密钥）</Text>
              <div>
                <Text copyable={{ text: detailRow.gateway_url }}>{detailRow.gateway_url}</Text>
              </div>
            </div>
            <div>
              <Text strong>调试包路径</Text>
              <div>
                {detailRow.debug_bundle_rel_path ? (
                  <Text copyable={{ text: detailRow.debug_bundle_rel_path }}>{detailRow.debug_bundle_rel_path}</Text>
                ) : (
                  <Text type="secondary">无（成功且已落盘 WebP 时通常为空）</Text>
                )}
              </div>
            </div>
            <div>
              <Text strong>错误信息</Text>
              <pre style={{ maxHeight: 160, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {detailRow.error_message || '—'}
              </pre>
            </div>
            <div>
              <Text strong>提示词（完整）</Text>
              <pre style={{ maxHeight: 280, overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                {detailRow.prompt || '—'}
              </pre>
            </div>
          </Space>
        )}
      </Modal>
    </Space>
  )
}
