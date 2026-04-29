import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, Modal, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { http } from '../api/http'
import type { LlmCallRecord } from '../types/llm'

const { Text, Title } = Typography

export default function LlmCallLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<LlmCallRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<LlmCallRecord | null>(null)

  const operationLabel = (op?: string) => {
    const m: Record<string, string> = {
      quality_check: '章节质检：检查剧情、人物一致性与设定冲突',
      chapter_coherence_check: '多章节连贯性检测：检查标题匹配与章节衔接',
      suggest_stream: 'AI 写作建议：流式生成优化建议',
      extract_memory: '记忆提取：从章节抽取可复用记忆点',
      expand_outline: '大纲展开：把卷/节点展开成章节计划',
      plan_full_structure: '全量结构规划：规划卷级结构与篇幅节奏',
      draft_assist_stream: '写作辅助：起笔/续写/重写正文',
      auto_extract_debrief: '自动复盘：提取人物/故事线变化与章节索引',
    }
    if (!op) return '未标注作用'
    return m[op] ?? `未登记作用：${op}`
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

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<LlmCallRecord[]>('/api/v1/admin/llm-calls/?limit=300')
      setRows(data)
    } catch {
      message.error('加载 LLM 调用记录失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  const clearLogs = async () => {
    try {
      const { data } = await http.delete<{ deleted: number }>('/api/v1/admin/llm-calls/')
      message.success(`已清空 ${data.deleted} 条记录`)
      setRows([])
    } catch {
      message.error('清空失败')
    }
  }

  const totalTokens = useMemo(
    () => rows.reduce((sum, r) => sum + (r.token_usage?.total_tokens || 0), 0),
    [rows],
  )

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
        const op = String(row.context?.operation || '')
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{op || 'unknown'}</Text>
            <Text type="secondary">{operationLabel(op)}</Text>
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
      dataIndex: 'status',
      width: 90,
      render: (v: string) => (v === 'ok' ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>),
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
        <Button type="link" onClick={() => setDetailRow(row)}>
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
            共 {rows.length} 条，累计 token：{totalTokens}
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
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

      <Table<LlmCallRecord>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100] }}
        scroll={{ x: 1900, y: 'calc(100vh - 320px)' }}
      />

      <Modal
        title="LLM 调用详情（全量）"
        open={!!detailRow}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={1000}
      >
        {detailRow && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>接口作用：</Text>
              <Text>{operationLabel(String(detailRow.context?.operation || ''))}</Text>
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
      </Modal>
    </Space>
  )
}
