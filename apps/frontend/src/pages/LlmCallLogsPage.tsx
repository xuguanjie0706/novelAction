import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Modal, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import type { RangePickerProps } from 'antd/es/date-picker'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { http } from '../api/http'
import type { LlmCallRecord } from '../types/llm'

const { Text, Title } = Typography

const rangePresets: RangePickerProps['presets'] = [
  { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: '最近7天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
  { label: '最近30天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
]

export default function LlmCallLogsPage() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<LlmCallRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [detailRow, setDetailRow] = useState<LlmCallRecord | null>(null)
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)

  const resolveOperationKey = (row: LlmCallRecord) => {
    const op = row.context?.operation
    if (typeof op === 'string' && op.trim()) return op.trim()
    const task = row.context?.task
    if (typeof task === 'string' && task.trim()) return task.trim()
    return ''
  }

  const operationLabel = (op?: string) => {
    const m: Record<string, string> = {
      'bootstrap.positioning': 'Bootstrap 立项会议：提炼题材定位与卖点承诺',
      'bootstrap.project': 'Bootstrap 项目初始化：生成项目基础设定与核心故事',
      'bootstrap.settings': 'Bootstrap 世界观总设：生成设定卡',
      'bootstrap.power_systems': 'Bootstrap 力量体系：生成等级、机制与代价',
      'bootstrap.factions': 'Bootstrap 阵营势力：生成组织关系与立场冲突',
      'bootstrap.storylines': 'Bootstrap 故事线：生成主线/支线与推进节奏',
      'bootstrap.characters': 'Bootstrap 人物库：生成核心角色与关系锚点',
      'bootstrap.skills': 'Bootstrap 技能体系：生成技能结构与成长路径',
      'bootstrap.items': 'Bootstrap 道具体系：生成资源、稀有度与用途',
      'bootstrap.volumes': 'Bootstrap 卷章规划：生成卷级结构与章节分布',
      'bootstrap.memory': 'Bootstrap 记忆库：生成可复用事实与约束',
      'bootstrap.relations': 'Bootstrap 人物关系：生成人际网络与动态张力',
      'bootstrap.single_shot': 'Bootstrap 单次全量：一次性生成完整世界蓝图',
      'bootstrap.consistency_scan': 'Bootstrap 一致性扫描：检测设定冲突与结构缺口',
      'bootstrap.ch1_scenes': 'Bootstrap 第一章场景规划：生成开篇场景与节奏节点',
      'bootstrap.vol1_chapters': 'Bootstrap 第一卷章节细化：生成首卷章节拆分与推进线',
      bootstrap_single_shot: 'Bootstrap 单次全量：一次性生成完整世界蓝图',
      bootstrap_complete_settings: 'Bootstrap 设定补全：补齐世界观结构化条目',
      bootstrap_complete_characters: 'Bootstrap 人物补全：补齐角色画像与关系',
      quality_check: '章节质检：检查剧情、人物一致性与设定冲突',
      chapter_coherence_check: '多章节连贯性检测：检查标题匹配与章节衔接',
      chapter_coherence_apply: '连贯性评测修订：按评测结论最小幅度改正文',
      suggest_stream: 'AI 写作建议：流式生成优化建议',
      extract_memory: '记忆提取：从章节抽取可复用记忆点',
      expand_outline: '大纲展开：把卷/节点展开成章节计划',
      plan_full_structure: '全量结构规划：规划卷级结构与篇幅节奏',
      draft_assist_stream: '写作辅助：起笔/续写/重写正文',
      auto_extract_debrief: '自动复盘：提取人物/故事线变化与章节索引',
    }
    if (!op) return '未标注作用'
    if (m[op]) return m[op]
    if (op.startsWith('bootstrap.')) return `Bootstrap 流程任务：${op.replace('bootstrap.', '')}`
    return `未登记作用：${op}`
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

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const qs = new URLSearchParams()
      qs.set('limit', '1000')
      if (apiRange) {
        qs.set('since', apiRange[0].startOf('day').toISOString())
        qs.set('until', apiRange[1].endOf('day').toISOString())
      }
      const { data } = await http.get<LlmCallRecord[]>(`/api/v1/admin/llm-calls/?${qs.toString()}`)
      setRows(data)
    } catch {
      message.error('加载 LLM 调用记录失败')
    } finally {
      setLoading(false)
    }
  }, [message, apiRange])

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

  const hasDateFilter = apiRange != null

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
            共 {rows.length} 条
            {hasDateFilter ? '（所选时间范围内，最多 1000 条）' : '（最多 1000 条）'}
            ，累计 token：{totalTokens}
          </Text>
        </div>
        <Space wrap>
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
              <Text>{operationLabel(resolveOperationKey(detailRow))}</Text>
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
